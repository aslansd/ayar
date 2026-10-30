"""Curation multiverse: does the finding depend on which quality thresholds you chose?

Every lab curates units with thresholds (ISI violations below x, presence ratio
above y, ...), and the choice is rarely justified. ``ayar multiverse`` recomputes
your finding for every combination of plausible thresholds and reports how far
the numbers move, whether their sign holds, and which threshold matters most.
"""

from __future__ import annotations

import itertools
import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np

from . import __version__
from .audit import FindingFn, call_finding
from .bundle import Bundle
from .config import DEFAULTS, Thresholds
from .metrics import compute as compute_metrics
from .metrics import merge_tables

_RULE = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(>=|<=)\s*([^\s].*)$")


@dataclass
class Rule:
    """Keep units whose ``metric`` is ``op`` each of ``levels`` (one level per universe)."""

    metric: str
    op: str
    levels: list[float]

    def __post_init__(self):
        if self.op not in (">=", "<="):
            raise ValueError(f"operator must be >= or <=, got {self.op!r}")
        if not self.levels:
            raise ValueError(f"rule on {self.metric} has no levels")

    @classmethod
    def parse(cls, text: str) -> "Rule":
        """``"isi_contamination<=0.1,0.25,1"`` -> Rule('isi_contamination', '<=', [0.1, 0.25, 1.0])."""
        m = _RULE.match(text)
        if not m:
            raise ValueError(f"cannot parse rule {text!r}; expected e.g. 'presence_ratio>=0.5,0.9'")
        return cls(m.group(1), m.group(2), [float(x) for x in m.group(3).split(",") if x.strip()])

    def passes(self, values: np.ndarray, level: float) -> np.ndarray:
        """NaN (metric unavailable for a unit) passes: ayar does not curate on missing data."""
        with np.errstate(invalid="ignore"):
            ok = values >= level if self.op == ">=" else values <= level
        return ok | np.isnan(values)

    def __str__(self) -> str:
        return f"{self.metric}{self.op}{','.join(f'{x:g}' for x in self.levels)}"


DEFAULT_GRID = (
    Rule("firing_rate", ">=", [0.0, 0.1, 0.5, 1.0]),
    Rule("presence_ratio", ">=", [0.0, 0.5, 0.9]),
    Rule("isi_contamination", "<=", [1.0, 0.25, 0.1]),
    Rule("amplitude_cutoff", "<=", [0.5, 0.1]),
)


@dataclass
class KeySummary:
    key: str
    baseline: float
    n: int
    median: float
    minimum: float
    maximum: float
    q05: float
    q95: float
    sign_agreement: float
    spread: float
    influence: dict[str, float]
    verdict: str

    @property
    def most_influential(self) -> str | None:
        if not self.influence:
            return None
        return max(self.influence, key=lambda k: self.influence[k])


@dataclass
class MultiverseReport:
    grid: list[str]
    n_universes: int
    n_evaluated: int
    n_skipped: int
    n_failed: int
    units_total: int
    universes: list[dict[str, Any]]
    summaries: list[KeySummary]
    notes: list[str] = field(default_factory=list)
    finding_name: str | None = None
    version: str = __version__

    @property
    def verdicts(self) -> dict[str, str]:
        return {s.key: s.verdict for s in self.summaries}

    def exit_code(self, fail_on: str = "sign_unstable") -> int:
        if fail_on == "never":
            return 0
        bad = {"sign_unstable"} if fail_on == "sign_unstable" else {"sign_unstable", "threshold_dependent"}
        return 1 if any(v in bad for v in self.verdicts.values()) else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ayar_version": self.version,
            "finding": self.finding_name,
            "grid": self.grid,
            "counts": {
                "universes": self.n_universes, "evaluated": self.n_evaluated,
                "skipped_too_few_units": self.n_skipped, "failed": self.n_failed,
                "units_total": self.units_total,
            },
            "summaries": [asdict(s) for s in self.summaries],
            "universes": self.universes,
            "notes": self.notes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=float)

    def format_text(self) -> str:
        f = lambda x: "n/a" if x is None or not math.isfinite(x) else f"{x:.4g}"  # noqa: E731
        lines = [
            f"ayar {self.version} multiverse" + (f": {self.finding_name}" if self.finding_name else ""),
            f"grid: {'  '.join(self.grid)}",
            f"{self.n_universes} universes; {self.n_evaluated} evaluated, {self.n_skipped} skipped "
            f"(too few units), {self.n_failed} failed; {self.units_total} units before curation",
            "",
        ]
        if not self.summaries:
            lines.append("no universe could be evaluated")
        else:
            wk = max(len(s.key) for s in self.summaries)
            lines.append(
                f"  {'number':<{wk}}  {'all units':>10}  {'min':>10}  {'median':>10}  {'max':>10}  "
                f"{'same sign':>9}  {'spread':>7}  verdict"
            )
            for s in self.summaries:
                lines.append(
                    f"  {s.key:<{wk}}  {f(s.baseline):>10}  {f(s.minimum):>10}  {f(s.median):>10}  "
                    f"{f(s.maximum):>10}  {s.sign_agreement:>9.0%}  {s.spread:>7.0%}  {s.verdict.upper()}"
                )
            lines.append("")
            for s in self.summaries:
                mi = s.most_influential
                if mi is not None:
                    lines.append(
                        f"  {s.key}: most sensitive to {mi} (median moves {s.influence[mi]:.0%} across its levels)"
                    )
            lines.append("")
            for v, text in _VERDICTS.items():
                if v in self.verdicts.values():
                    lines.append(f"  {v.upper()}: {text}")
        for n in self.notes:
            lines.append(f"  note: {n}")
        return "\n".join(lines)


_VERDICTS = {
    "stable": "the 5-95 % range across universes is small and the sign never changes",
    "threshold_dependent": "the sign holds, but the size of the number depends on the curation thresholds",
    "sign_unstable": "the number changes sign, or vanishes (reaches zero), under some plausible thresholds",
}


def _summaries(rows, baseline, grid, keys, th) -> list[KeySummary]:
    out = []
    for key in keys:
        vals = np.array([r["values"].get(key, np.nan) for r in rows], dtype=float)
        ok = np.isfinite(vals)
        if not ok.any():
            continue
        v = vals[ok]
        med = float(np.median(v))
        q05, q95 = (float(x) for x in np.percentile(v, [5, 95]))
        ref = med if med != 0 else (baseline.get(key) or 0.0)
        sign_ref = math.copysign(1, ref) if ref != 0 else 0
        sign_agree = float(np.mean(np.sign(v) == sign_ref)) if sign_ref != 0 else float(np.mean(v == 0))
        spread = (q95 - q05) / max(abs(med), 1e-12)
        influence = {}
        for rule in grid:
            meds = []
            for level in rule.levels:
                sel = [vals[i] for i, r in enumerate(rows) if r["levels"][rule.metric] == level and ok[i]]
                if sel:
                    meds.append(float(np.median(sel)))
            if len(meds) >= 2:
                influence[str(rule.metric)] = (max(meds) - min(meds)) / max(abs(med), 1e-12)
        if sign_agree < th.mv_sign_agreement:
            verdict = "sign_unstable"
        elif spread >= th.mv_spread:
            verdict = "threshold_dependent"
        else:
            verdict = "stable"
        out.append(KeySummary(
            key=key, baseline=baseline.get(key, float("nan")), n=int(ok.sum()), median=med,
            minimum=float(v.min()), maximum=float(v.max()), q05=q05, q95=q95,
            sign_agreement=sign_agree, spread=float(spread), influence=influence, verdict=verdict,
        ))
    return out


def multiverse(
    bundle: Bundle,
    finding: FindingFn,
    grid: Iterable[Rule | str] | None = None,
    *,
    metrics: Mapping[str, Mapping[int, float]] | None = None,
    thresholds: Thresholds | None = None,
    finding_name: str | None = None,
) -> MultiverseReport:
    """Recompute ``finding`` for every combination of curation thresholds in ``grid``.

    ``metrics`` (``{metric: {unit_id: value}}``) adds to or overrides the metrics ayar
    computes itself (see :mod:`ayar.metrics`), e.g. a SpikeInterface or Bombcell table.
    Rules on metrics that are unavailable are dropped with a note.
    """
    th = thresholds or DEFAULTS
    rules = [r if isinstance(r, Rule) else Rule.parse(r) for r in (grid if grid is not None else DEFAULT_GRID)]
    table = merge_tables(compute_metrics(bundle), metrics or {})
    notes: list[str] = []
    units = [int(u) for u in bundle.unit_ids]
    usable = []
    for r in rules:
        if r.metric not in table:
            notes.append(f"dropped rule {r}: metric '{r.metric}' unavailable "
                         f"(have: {', '.join(sorted(table))})")
            continue
        usable.append(r)
    if not usable:
        raise ValueError("no usable rule: none of the grid's metrics is available")

    values = {r.metric: np.array([table[r.metric].get(u, np.nan) for u in units], dtype=float) for r in usable}
    baseline = call_finding(finding, bundle)
    keys = list(baseline)

    rows: list[dict[str, Any]] = []
    n_skipped = n_failed = 0
    combos = list(itertools.product(*(r.levels for r in usable)))
    for combo in combos:
        keep = np.ones(len(units), dtype=bool)
        for r, level in zip(usable, combo):
            keep &= r.passes(values[r.metric], level)
        levels = {r.metric: level for r, level in zip(usable, combo)}
        n_keep = int(keep.sum())
        if n_keep < th.mv_min_units:
            n_skipped += 1
            continue
        drop = [u for u, k in zip(units, keep) if not k]
        try:
            vals = call_finding(finding, bundle.without(drop))
        except Exception as e:
            n_failed += 1
            if n_failed == 1:
                notes.append(f"finding failed in some universes, e.g. {type(e).__name__}: {e}")
            continue
        rows.append({"levels": levels, "n_units": n_keep, "values": vals})

    return MultiverseReport(
        grid=[str(r) for r in usable],
        n_universes=len(combos),
        n_evaluated=len(rows),
        n_skipped=n_skipped,
        n_failed=n_failed,
        units_total=len(units),
        universes=rows,
        summaries=_summaries(rows, baseline, usable, keys, th),
        notes=notes,
        finding_name=finding_name or getattr(finding, "__name__", None),
    )
