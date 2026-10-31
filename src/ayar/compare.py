"""Sorter multiverse: does the finding survive a different spike sorter?

Sort the same recording with several sorters (or parameter sets), give ayar the
outputs and your finding. ayar matches units between the reference sorting and
each other sorting, recomputes the finding on every sorting and on the
*consensus* units (reference units that every other sorting also found), and
reports how far each number moves between sorters.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import numpy as np

from . import __version__
from .audit import FindingFn, call_finding
from .bundle import Bundle
from .config import DEFAULTS, Thresholds
from .matching import Matching, match_units


@dataclass
class CompareSummary:
    key: str
    values: dict[str, float]
    consensus: float | None
    median: float
    spread: float
    sign_agreement: float
    consensus_change: float | None
    verdict: str


@dataclass
class CompareReport:
    reference: str
    names: list[str]
    n_units: dict[str, int]
    matchings: list[Matching]
    consensus_units: list[int]
    summaries: list[CompareSummary]
    notes: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    finding_name: str | None = None
    attribution: dict[str, list[dict]] = field(default_factory=dict)
    version: str = __version__

    @property
    def verdicts(self) -> dict[str, str]:
        return {s.key: s.verdict for s in self.summaries}

    def exit_code(self, fail_on: str = "sign_unstable") -> int:
        if fail_on == "never":
            return 0
        bad = {"sign_unstable"} if fail_on == "sign_unstable" else {"sign_unstable", "sorter_dependent"}
        return 1 if any(v in bad for v in self.verdicts.values()) else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ayar_version": self.version,
            "finding": self.finding_name,
            "reference": self.reference,
            "sortings": self.names,
            "n_units": self.n_units,
            "matching": [
                {**m.summary(), "pairs": [[a, b, round(s, 4)] for a, b, s in m.pairs],
                 "only_in_a": m.unmatched_a, "only_in_b": m.unmatched_b}
                for m in self.matchings
            ],
            "consensus_units": self.consensus_units,
            "summaries": [asdict(s) for s in self.summaries],
            "attribution": self.attribution,
            "failed": self.failed,
            "notes": self.notes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=float)

    def format_text(self) -> str:
        f = lambda x: "n/a" if x is None or not math.isfinite(x) else f"{x:.4g}"  # noqa: E731
        lines = [
            f"ayar {self.version} compare" + (f": {self.finding_name}" if self.finding_name else ""),
            "sortings: " + ", ".join(f"{n} ({self.n_units[n]} units)" for n in self.names)
            + f"; reference {self.reference}",
            "",
            "unit matching (agreement >= threshold, one-to-one):",
        ]
        for m in self.matchings:
            s = m.summary()
            med = "-" if s["median_agreement"] is None else f"{s['median_agreement']:.2f}"
            lines.append(
                f"  {m.name_a} vs {m.name_b}: {s['matched']} matched (median agreement {med}), "
                f"{s['only_in_a']} only in {m.name_a}, {s['only_in_b']} only in {m.name_b}"
            )
        lines.append(f"  consensus: {len(self.consensus_units)} of {self.n_units[self.reference]} "
                     f"{self.reference} units are found by every sorting")
        lines.append("")
        if self.summaries:
            wk = max(len(s.key) for s in self.summaries)
            cols = self.names + ["consensus"]
            w = max(10, *(len(c) for c in cols))
            lines.append(f"  {'number':<{wk}}  " + "  ".join(f"{c:>{w}}" for c in cols)
                         + f"  {'spread':>7}  {'same sign':>9}  verdict")
            for s in self.summaries:
                vals = [f(s.values.get(n)) for n in self.names] + [f(s.consensus)]
                lines.append(f"  {s.key:<{wk}}  " + "  ".join(f"{v:>{w}}" for v in vals)
                             + f"  {s.spread:>7.0%}  {s.sign_agreement:>9.0%}  {s.verdict.upper()}")
            lines.append("")
            for key, rows in self.attribution.items():
                if rows:
                    top = ", ".join(f"{r['sorting']} unit {r['unit']} ({r['delta']:+.3g})" for r in rows[:5])
                    lines.append(f"  {key}: units outside the consensus that move it most when left out: {top}")
            if any(self.attribution.values()):
                lines.append("")
            for v, text in _VERDICTS.items():
                if v in self.verdicts.values():
                    lines.append(f"  {v.upper()}: {text}")
        for name, err in self.failed.items():
            lines.append(f"  failed on {name}: {err}")
        for n in self.notes:
            lines.append(f"  note: {n}")
        return "\n".join(lines)


_VERDICTS = {
    "consistent": "every sorting gives the same sign and the values stay within the spread threshold",
    "sorter_dependent": "the sign holds, but the size of the number depends on the sorter",
    "sign_unstable": "the number changes sign, or vanishes, depending on the sorter",
}


def _sign(x: float) -> int:
    return 0 if x == 0 else (1 if x > 0 else -1)


def compare(
    sortings: Mapping[str, Bundle],
    finding: FindingFn,
    *,
    reference: str | None = None,
    thresholds: Thresholds | None = None,
    finding_name: str | None = None,
    attribute: bool = True,
    max_attributed_units: int = 40,
) -> CompareReport:
    """Recompute ``finding`` on several sortings of one recording and on their consensus units.

    With ``attribute``, numbers that are not consistent across sorters are traced to units:
    each unit that only part of the sortings found is left out of its own sorting in turn,
    and the units whose removal moves the number most are listed.
    """
    th = thresholds or DEFAULTS
    names = list(sortings)
    if len(names) < 2:
        raise ValueError("compare needs at least two sortings")
    ref = reference or names[0]
    if ref not in sortings:
        raise KeyError(f"reference {ref!r} is not one of {names}")
    names = [ref] + [n for n in names if n != ref]
    notes: list[str] = []

    bundles = dict(sortings)
    ref_events = bundles[ref].events
    for n in names[1:]:
        if bundles[n].events is None and ref_events is not None:
            b = bundles[n].without([])
            b.events = ref_events
            bundles[n] = b
            notes.append(f"{n} has no events: using the reference's events (same recording)")
        if abs(bundles[n].duration - bundles[ref].duration) > 1.0:
            notes.append(f"{n} lasts {bundles[n].duration:g} s but {ref} lasts {bundles[ref].duration:g} s: "
                         "are these sortings of the same recording?")

    matchings = [
        match_units(bundles[ref], bundles[n], delta_s=th.cmp_delta_ms / 1000.0,
                    min_agreement=th.cmp_min_agreement, name_a=ref, name_b=n)
        for n in names[1:]
    ]
    consensus = set(int(u) for u in bundles[ref].unit_ids)
    for m in matchings:
        consensus &= m.matched_a
    consensus_units = sorted(consensus)

    values: dict[str, dict[str, float]] = {}
    failed: dict[str, str] = {}
    for n in names:
        try:
            values[n] = call_finding(finding, bundles[n])
        except Exception as e:
            failed[n] = f"{type(e).__name__}: {e}"
    if ref in failed:
        raise RuntimeError(f"the finding failed on the reference sorting {ref}: {failed[ref]}")

    cons_vals: dict[str, float] = {}
    if len(consensus_units) >= th.mv_min_units:
        drop = [int(u) for u in bundles[ref].unit_ids if int(u) not in consensus]
        try:
            cons_vals = call_finding(finding, bundles[ref].without(drop))
        except Exception as e:
            failed["consensus"] = f"{type(e).__name__}: {e}"
    else:
        notes.append(f"only {len(consensus_units)} consensus units (< {th.mv_min_units}): consensus not evaluated")

    summaries: list[CompareSummary] = []
    for key in values[ref]:
        per = {n: values[n][key] for n in names if n in values and key in values[n]}
        allv = list(per.values()) + ([cons_vals[key]] if key in cons_vals else [])
        arr = np.array([v for v in allv if math.isfinite(v)])
        if arr.size == 0:
            continue
        med = float(np.median(arr))
        spread = float((arr.max() - arr.min()) / max(abs(med), 1e-12))
        ref_sign = _sign(per[ref]) or _sign(med)
        agree = float(np.mean([_sign(v) == ref_sign for v in arr]))
        cons = cons_vals.get(key)
        cons_change = None if cons is None else abs(cons - per[ref]) / max(abs(per[ref]), 1e-12)
        if agree < 1.0:
            verdict = "sign_unstable"
        elif spread >= th.cmp_spread:
            verdict = "sorter_dependent"
        else:
            verdict = "consistent"
        summaries.append(CompareSummary(key, per, cons, med, spread, agree, cons_change, verdict))

    attribution: dict[str, list[dict]] = {}
    shaky = [sm.key for sm in summaries if sm.verdict != "consistent"]
    if attribute and shaky:
        unmatched: dict[str, list[int]] = {ref: sorted(set(int(u) for u in bundles[ref].unit_ids) - consensus)}
        for m in matchings:
            unmatched[m.name_b] = m.unmatched_b
        rows: dict[str, list[dict]] = {k: [] for k in shaky}
        budget = max_attributed_units
        for n, units in unmatched.items():
            if n not in values:
                continue
            for u in units[:budget]:
                try:
                    v = call_finding(finding, bundles[n].without([u]))
                except Exception:
                    continue
                for k in shaky:
                    if k in v and k in values[n]:
                        rows[k].append({"sorting": n, "unit": int(u), "delta": float(values[n][k] - v[k])})
        for k in shaky:
            attribution[k] = sorted(rows[k], key=lambda r: -abs(r["delta"]))[:10]
        n_total = sum(len(u) for u in unmatched.values())
        if n_total > max_attributed_units * len(unmatched):
            notes.append(f"attribution checked at most {max_attributed_units} unmatched units per sorting")

    return CompareReport(
        reference=ref,
        names=names,
        n_units={n: bundles[n].n_units for n in names},
        matchings=matchings,
        consensus_units=consensus_units,
        summaries=summaries,
        notes=notes,
        failed=failed,
        finding_name=finding_name or getattr(finding, "__name__", None),
        attribution=attribution,
    )
