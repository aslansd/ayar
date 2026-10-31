"""Per-unit quality metrics, computed from a bundle or read from a table.

These are the usual curation metrics (as in SpikeInterface, Allen and IBL
pipelines), computed with no dependency beyond numpy. ayar uses them for the
CONTAMINATION detector and for the curation-threshold multiverse; you can also
pass your own table (SpikeInterface ``quality_metrics``, Bombcell, ...).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping

import numpy as np

from .bundle import Bundle
from .stats import missing_fraction

#: refractory period and censored period used for ISI violations (s)
REFRACTORY_S = 0.0015
CENSORED_S = 0.0


def isi_violations(train: np.ndarray, refractory: float = REFRACTORY_S, censored: float = CENSORED_S) -> int:
    """Number of inter-spike intervals shorter than ``refractory`` (and >= ``censored``)."""
    if train.size < 2:
        return 0
    isi = np.diff(train)
    return int(np.sum((isi < refractory) & (isi >= censored)))


def hill_contamination(n_violations: int, n_spikes: int, duration: float,
                       refractory: float = REFRACTORY_S, censored: float = CENSORED_S) -> float:
    """Fraction of a unit's spikes that come from other neurons (Hill et al. 2011).

    Solves ``n_v = 2 (t_r - t_c) N^2 c (1 - c) / T`` for ``c``; returns 0.5 when the
    violations exceed what any contamination can explain (c(1-c) > 1/4).
    """
    if n_spikes < 2 or duration <= 0:
        return float("nan")
    k = n_violations * duration / (2.0 * (refractory - censored) * n_spikes ** 2)
    if k >= 0.25:
        return 0.5
    return float((1.0 - np.sqrt(1.0 - 4.0 * k)) / 2.0)


def presence_ratio(train: np.ndarray, duration: float, n_bins: int = 100) -> float:
    """Fraction of ``n_bins`` equal time bins containing at least one spike."""
    if duration <= 0:
        return float("nan")
    if train.size == 0:
        return 0.0
    idx = np.clip((train / duration * n_bins).astype(int), 0, n_bins - 1)
    return float(np.unique(idx).size / n_bins)


def _presence_in_epochs(train: np.ndarray, epochs: np.ndarray, n_bins: int = 100) -> float:
    total = float(np.sum(epochs[:, 1] - epochs[:, 0]))
    if total <= 0:
        return float("nan")
    # map observed time onto [0, total) so the bins cover only time the unit was recorded
    offs = np.concatenate([[0.0], np.cumsum(epochs[:, 1] - epochs[:, 0])[:-1]])
    i = np.clip(np.searchsorted(epochs[:, 0], train, side="right") - 1, 0, len(epochs) - 1)
    mapped = train - epochs[i, 0] + offs[i]
    return presence_ratio(mapped, total, n_bins)


METRIC_NAMES = (
    "n_spikes", "firing_rate", "presence_ratio", "isi_violations", "isi_contamination",
    "amplitude_median", "amplitude_cutoff",
)


def compute(bundle: Bundle) -> dict[str, dict[int, float]]:
    """Compute every metric for every unit: ``{metric: {unit_id: value}}``."""
    out: dict[str, dict[int, float]] = {m: {} for m in METRIC_NAMES}
    for u in bundle.unit_ids:
        u = int(u)
        t = bundle.train(u)
        T = bundle.observed_duration(u)  # a unit restricted to epochs is judged on its epochs
        nv = isi_violations(t)
        out["n_spikes"][u] = float(t.size)
        out["firing_rate"][u] = t.size / T if T > 0 else float("nan")
        out["presence_ratio"][u] = _presence_in_epochs(t, bundle.unit_epochs(u))
        out["isi_violations"][u] = float(nv)
        out["isi_contamination"][u] = hill_contamination(nv, t.size, T)
        a = bundle.unit_amplitudes(u)
        if a is not None and a.size:
            out["amplitude_median"][u] = float(np.median(a))
            out["amplitude_cutoff"][u] = missing_fraction(a) if a.size >= 30 else float("nan")
    return {k: v for k, v in out.items() if v}


def read_table(path: str | Path, unit_column: str | None = None,
               bundle: Bundle | None = None) -> dict[str, dict[int, float]]:
    """Read a CSV/TSV metrics table (one row per unit) into ``{metric: {unit_id: value}}``.

    The unit column is auto-detected (``unit_id``, ``cluster_id``, ``id``, or an unnamed
    first column as written by pandas). Original unit ids are translated through
    ``bundle.meta['unit_id_map']`` when the bundle came from a source with string ids.
    Non-numeric columns are ignored.
    """
    path = Path(path)
    delim = "\t" if path.suffix in (".tsv", ".tab") else ","
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=delim))
    if not rows:
        raise ValueError(f"{path} has no rows")
    cols = list(rows[0].keys())
    ucol = unit_column
    if ucol is None:
        for c in ("unit_id", "cluster_id", "unit_ids", "id", ""):
            if c in cols:
                ucol = c
                break
    if ucol is None:
        raise ValueError(f"cannot find the unit column in {path}; pass unit_column=")
    reverse = {}
    if bundle is not None and bundle.meta.get("unit_id_map"):
        reverse = {orig: int(i) for i, orig in bundle.meta["unit_id_map"].items()}
    out: dict[str, dict[int, float]] = {}
    for row in rows:
        raw = row[ucol].strip()
        if raw in reverse:
            uid = reverse[raw]
        else:
            try:
                uid = int(float(raw))
            except ValueError:
                raise ValueError(f"unit id {raw!r} in {path} is not an integer and has no mapping") from None
        for c in cols:
            if c == ucol:
                continue
            try:
                out.setdefault(c, {})[uid] = float(row[c])
            except (TypeError, ValueError):
                continue
    return {k: v for k, v in out.items() if np.isfinite(list(v.values())).any()}


def from_spikeinterface(analyzer) -> dict[str, dict[int, float]]:
    """Metrics from a SortingAnalyzer's ``quality_metrics`` (and ``template_metrics``) extensions."""
    from .io import _int_unit_ids

    uid, _ = _int_unit_ids(analyzer.sorting.get_unit_ids())
    out: dict[str, dict[int, float]] = {}
    for name in ("quality_metrics", "template_metrics"):
        ext = analyzer.get_extension(name)
        if ext is None:
            continue
        df = ext.get_data()
        for col in df.columns:
            try:
                vals = np.asarray(df[col], dtype=float)
            except (TypeError, ValueError):
                continue
            out[col] = {int(u): float(v) for u, v in zip(uid, vals)}
    if not out:
        raise ValueError("the analyzer has no quality_metrics or template_metrics extension computed")
    return out


def merge_tables(*tables: Mapping[str, Mapping[int, float]]) -> dict[str, dict[int, float]]:
    """Later tables override earlier ones, metric by metric."""
    out: dict[str, dict[int, float]] = {}
    for t in tables:
        for k, v in t.items():
            out[k] = dict(v)
    return out
