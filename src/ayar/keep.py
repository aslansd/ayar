"""Restrict a bundle to curated units before scanning: ``--keep "label>=1"``.

A lab analyses the units it curated, so the question it has is how sorting artifacts
among *those* units affect its finding. ``keep`` drops every other unit (and its spikes)
before anything else runs: the detectors, the finding, its audit and its random controls
all see only the kept units.

Metrics come from, in order (later ones win): what ayar computes itself
(:mod:`ayar.metrics`: ``presence_ratio``, ``isi_contamination``, ...), what the reader
found (IBL's ``label``, an NWB file's ``phy_annotations`` or ``quality``), and a table you
pass.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np

from .bundle import Bundle

_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "!=": operator.ne,
        ">": operator.gt, "<": operator.lt}
_KEEP = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(>=|<=|==|!=|>|<)\s*([-+0-9.eE]+|nan|inf)\s*$")


@dataclass(frozen=True)
class KeepRule:
    """Keep units whose ``metric`` ``op`` ``value``; a unit without the metric is dropped."""

    metric: str
    op: str
    value: float

    @classmethod
    def parse(cls, text: str) -> "KeepRule":
        """``"label>=1"`` -> KeepRule('label', '>=', 1.0)."""
        m = _KEEP.match(text)
        if not m:
            raise ValueError(f"cannot parse keep rule {text!r}; expected e.g. 'label>=1' or 'phy_annotations>=2'")
        return cls(m.group(1), m.group(2), float(m.group(3)))

    def passes(self, values: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore"):
            return np.isfinite(values) & _OPS[self.op](values, self.value)

    def __str__(self) -> str:
        return f"{self.metric}{self.op}{self.value:g}"


def unit_metrics(bundle: Bundle) -> dict[str, dict[int, float]]:
    """Metrics the reader stored in ``bundle.meta`` (IBL cluster metrics, NWB unit columns)."""
    out: dict[str, dict[int, float]] = {}
    for key in ("ibl_metrics", "unit_metrics"):
        for name, d in (bundle.meta.get(key) or {}).items():
            out[name] = {int(u): (np.nan if v is None else float(v)) for u, v in d.items()}
    return out


def metric_table(bundle: Bundle, metrics: Mapping[str, Mapping[int, float]] | None = None):
    """Every metric available for ``bundle``: computed, from the reader, then ``metrics``."""
    from .metrics import compute, merge_tables

    return merge_tables(compute(bundle), unit_metrics(bundle), metrics or {})


def keep(bundle: Bundle, rules: Iterable[KeepRule | str],
         metrics: Mapping[str, Mapping[int, float]] | None = None) -> Bundle:
    """The bundle with only the units passing every rule.

    The result's ``meta['kept']`` records the rules and how many units each removed, and
    every report shows it.
    """
    rules = [r if isinstance(r, KeepRule) else KeepRule.parse(r) for r in rules]
    if not rules:
        return bundle
    table = metric_table(bundle, metrics)
    units = np.array([int(u) for u in bundle.unit_ids])
    ok = np.ones(units.size, dtype=bool)
    steps = []
    for r in rules:
        if r.metric not in table:
            raise ValueError(f"cannot keep on '{r.metric}': no such metric (have: {', '.join(sorted(table))})")
        d = table[r.metric]
        vals = np.array([d.get(int(u), np.nan) for u in units], dtype=float)
        p = r.passes(vals)
        steps.append({"rule": str(r), "removed": int((ok & ~p).sum()), "missing": int((ok & ~np.isfinite(vals)).sum())})
        ok &= p
    if not ok.any():
        raise ValueError(f"no unit passes {' and '.join(map(str, rules))}")
    child = bundle.without(units[~ok].tolist()) if (~ok).any() else bundle._subset(
        np.ones(bundle.n_spikes, dtype=bool), np.ones(bundle.n_units, dtype=bool))
    child.meta = dict(bundle.meta)
    child.meta["kept"] = {"rules": [str(r) for r in rules], "units_before": int(units.size),
                          "units_after": int(ok.sum()), "steps": steps}
    return child


def describe(bundle: Bundle) -> str | None:
    """One line on what ``keep`` did to this bundle, or None."""
    k = bundle.meta.get("kept")
    if not k:
        return None
    return f"kept {k['units_after']} of {k['units_before']} units ({' and '.join(k['rules'])})"
