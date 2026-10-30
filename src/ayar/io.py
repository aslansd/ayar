"""Readers that turn sorter output into an ayar :class:`~ayar.bundle.Bundle`.

v0.1 reads Phy / Kilosort output folders (Kilosort 2-4) and plain arrays.
SpikeInterface and NWB adapters are planned for v0.2.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable

import numpy as np

from .bundle import Bundle, Events


def from_arrays(spike_times, spike_clusters, **kwargs) -> Bundle:
    """Build a bundle from arrays already in memory. Times are in seconds."""
    return Bundle(spike_times, spike_clusters, **kwargs)


def _read_sample_rate(folder: Path) -> float | None:
    params = folder / "params.py"
    if not params.exists():
        return None
    m = re.search(r"^\s*sample_rate\s*=\s*([0-9.eE+-]+)", params.read_text(), re.M)
    return float(m.group(1)) if m else None


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _cluster_labels(folder: Path) -> dict[int, str]:
    """Curated labels win over Kilosort's automatic ones."""
    labels: dict[int, str] = {}
    for name, col in (("cluster_KSLabel.tsv", "KSLabel"), ("cluster_group.tsv", "group")):
        p = folder / name
        if p.exists():
            for row in _read_tsv(p):
                if row.get("cluster_id") not in (None, "") and row.get(col):
                    labels[int(row["cluster_id"])] = row[col].strip()
    return labels


def _cluster_depths(folder: Path) -> dict[int, float]:
    p = folder / "cluster_info.tsv"
    out: dict[int, float] = {}
    if p.exists():
        for row in _read_tsv(p):
            cid = row.get("cluster_id") or row.get("id")
            if cid not in (None, "") and row.get("depth") not in (None, ""):
                out[int(cid)] = float(row["depth"])
    return out


def from_phy(
    folder: str | Path,
    *,
    sample_rate: float | None = None,
    include: Iterable[str] | None = ("good", "mua"),
    events: Events | tuple | None = None,
    duration: float | None = None,
) -> Bundle:
    """Read a Phy / Kilosort output folder.

    ``include`` keeps units whose curated (or Kilosort) label is in the set;
    pass ``None`` to keep every cluster. Units without any label are kept.
    Spike depths come from ``spike_positions.npy`` (Kilosort 4) when present,
    unit depths from ``cluster_info.tsv`` (written by Phy).
    """
    folder = Path(folder)
    st_path = folder / "spike_times.npy"
    if not st_path.exists():
        raise FileNotFoundError(f"{st_path} not found: is this a Phy/Kilosort folder?")
    fs = sample_rate or _read_sample_rate(folder)
    if fs is None:
        raise ValueError("sample rate unknown: pass sample_rate= or provide params.py")

    samples = np.load(st_path).ravel()
    clu_path = folder / "spike_clusters.npy"
    if not clu_path.exists():
        clu_path = folder / "spike_templates.npy"
    clusters = np.load(clu_path).ravel().astype(np.int64)
    times = samples.astype(float) / fs

    amps = np.load(folder / "amplitudes.npy").ravel() if (folder / "amplitudes.npy").exists() else None
    depths = None
    pos_path = folder / "spike_positions.npy"
    if pos_path.exists():
        pos = np.load(pos_path)
        if pos.ndim == 2 and pos.shape[1] >= 2:
            depths = pos[:, 1].astype(float)

    labels = _cluster_labels(folder)
    keep = np.ones(times.shape[0], dtype=bool)
    if include is not None and labels:
        allowed = {s.lower() for s in include}
        bad = [c for c, lab in labels.items() if lab.lower() not in allowed]
        keep = ~np.isin(clusters, bad)

    unit_depth_map = _cluster_depths(folder)
    unit_ids = np.unique(clusters[keep])
    unit_depths = None
    if unit_depth_map:
        unit_depths = {int(u): unit_depth_map.get(int(u), np.nan) for u in unit_ids}

    return Bundle(
        times[keep],
        clusters[keep],
        duration=duration,
        amplitudes=None if amps is None else amps[keep],
        spike_depths=None if depths is None else depths[keep],
        unit_ids=unit_ids,
        unit_depths=unit_depths,
        events=events,
        meta={
            "source": "phy",
            "folder": str(folder),
            "sample_rate": fs,
            "labels": {str(k): v for k, v in labels.items() if k in set(unit_ids.tolist())},
            "amplitude_units": "kilosort template scaling (arbitrary)",
        },
    )


def load(path: str | Path, **kwargs) -> Bundle:
    """Load a bundle from a ``.npz`` file or a Phy/Kilosort folder."""
    path = Path(path)
    if path.is_dir():
        return from_phy(path, **kwargs)
    return Bundle.load(path)
