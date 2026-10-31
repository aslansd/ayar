"""Readers that turn sorter output into an ayar :class:`~ayar.bundle.Bundle`.

Sources: Phy / Kilosort output folders (Kilosort 2-4), SpikeInterface
``SortingAnalyzer`` / ``Sorting`` objects or saved analyzer folders, NWB files
(units and trials tables), and plain arrays. SpikeInterface and pynwb are
imported only when those sources are used.
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


def _int_unit_ids(ids) -> tuple[np.ndarray, dict[str, str] | None]:
    """Map unit ids to integers. Integer-like ids keep their value; others get an index."""
    ids = list(ids)
    try:
        ints = [int(str(u)) for u in ids]
        if len(set(ints)) == len(ints):
            return np.asarray(ints, dtype=np.int64), None
    except ValueError:
        pass
    return np.arange(len(ids), dtype=np.int64), {str(i): str(u) for i, u in enumerate(ids)}


def from_spikeinterface(
    obj,
    *,
    segment_index: int | None = None,
    events: Events | tuple | None = None,
    duration: float | None = None,
) -> Bundle:
    """Read a SpikeInterface ``SortingAnalyzer`` or ``BaseSorting``.

    From an analyzer, ayar also takes per-spike amplitudes (``spike_amplitudes``),
    per-spike depths (``spike_locations``, y) and unit depths (``unit_locations``)
    when those extensions have been computed, plus the recording duration.
    Non-integer unit ids are mapped to integers; the mapping is kept in
    ``bundle.meta['unit_id_map']``.
    """
    analyzer = obj if hasattr(obj, "get_extension") and hasattr(obj, "sorting") else None
    sorting = analyzer.sorting if analyzer is not None else obj
    if not hasattr(sorting, "to_spike_vector"):
        raise TypeError(f"expected a SpikeInterface SortingAnalyzer or Sorting, got {type(obj).__name__}")

    n_seg = sorting.get_num_segments()
    if segment_index is None:
        if n_seg > 1:
            raise ValueError(f"the sorting has {n_seg} segments: pass segment_index=")
        segment_index = 0
    fs = float(sorting.sampling_frequency)

    sv = sorting.to_spike_vector()
    in_seg = sv["segment_index"] == segment_index
    times = sv["sample_index"][in_seg] / fs
    unit_ids, id_map = _int_unit_ids(sorting.get_unit_ids())
    clusters = unit_ids[sv["unit_index"][in_seg]]

    amps = depths = unit_depths = None
    meta: dict = {"source": "spikeinterface", "sample_rate": fs, "segment_index": segment_index}
    if analyzer is not None:
        ext = analyzer.get_extension("spike_amplitudes")
        if ext is not None:
            amps = np.abs(np.asarray(ext.get_data(), dtype=float))[in_seg]
            meta["amplitude_units"] = "µV (absolute peak amplitude)"
        ext = analyzer.get_extension("spike_locations")
        if ext is not None:
            loc = ext.get_data()
            depths = np.asarray(loc["y"] if loc.dtype.names else loc[:, 1], dtype=float)[in_seg]
        ext = analyzer.get_extension("unit_locations")
        if ext is not None:
            unit_depths = np.asarray(ext.get_data(), dtype=float)[:, 1]
        if duration is None:
            duration = analyzer.get_num_samples(segment_index) / fs
    elif duration is None and sorting.has_recording():
        duration = sorting.get_num_samples(segment_index) / fs
    if id_map:
        meta["unit_id_map"] = id_map
    return Bundle(times, clusters, duration=duration, amplitudes=amps, spike_depths=depths,
                  unit_ids=unit_ids, unit_depths=unit_depths, events=events, meta=meta)


def _first_column(table, names):
    cols = set(getattr(table, "colnames", ()))
    for n in names:
        if n in cols:
            return n
    return None


def from_nwb(
    path: str | Path,
    *,
    trial_label: str | None = None,
    event_time_column: str = "start_time",
    amplitude_column: str | None = None,
    depth_column: str | None = None,
    shift_negative: bool = False,
) -> Bundle:
    """Read the units table (and optionally the trials table) of an NWB file.

    ``trial_label`` names a trials-table column to use as the condition label;
    event times come from ``event_time_column`` (default ``start_time``).
    Per-spike amplitudes are read from ``amplitude_column`` (auto-detected:
    ``spike_amplitudes``, ``amplitudes``). Unit depths come from ``depth_column``
    (auto: ``depth``, ``peak_channel_depth``) or the y coordinate of each unit's
    first electrode.
    """
    try:
        from pynwb import NWBHDF5IO
    except ImportError as e:  # pragma: no cover - depends on environment
        raise ImportError("reading NWB needs pynwb: pip install 'ayar[nwb]'") from e

    with NWBHDF5IO(str(path), "r") as io:
        nwb = io.read()
        units = nwb.units
        if units is None or len(units) == 0:
            raise ValueError(f"{path} has no units table")
        uid, id_map = _int_unit_ids(units.id[:])
        trains = [np.asarray(units["spike_times"][i], dtype=float) for i in range(len(units))]
        times = np.concatenate(trains) if trains else np.zeros(0)
        clusters = np.concatenate([np.full(t.size, u) for t, u in zip(trains, uid)]) if trains else np.zeros(0)

        amp_col = amplitude_column or _first_column(units, ["spike_amplitudes", "amplitudes"])
        amps = None
        if amp_col:
            amps = np.abs(np.concatenate([np.asarray(units[amp_col][i], dtype=float) for i in range(len(units))]))

        unit_depths = None
        dcol = depth_column or _first_column(units, ["depth", "peak_channel_depth"])
        if dcol:
            unit_depths = np.asarray(units[dcol][:], dtype=float)
        elif "electrodes" in units.colnames:
            ys = []
            for i in range(len(units)):
                el = units["electrodes"][i]
                try:
                    col = "rel_y" if "rel_y" in el.columns else "y"
                    ys.append(float(np.asarray(el[col])[0]))
                except Exception:
                    ys.append(np.nan)
            if np.isfinite(ys).any():
                unit_depths = np.asarray(ys)

        events = None
        if nwb.trials is not None and len(nwb.trials):
            ev_t = np.asarray(nwb.trials[event_time_column][:], dtype=float)
            labels = np.asarray(nwb.trials[trial_label][:]) if trial_label else None
            events = Events(ev_t, labels)
        elif trial_label:
            raise ValueError(f"{path} has no trials table for trial_label={trial_label!r}")

        meta = {"source": "nwb", "path": str(path), "session_id": getattr(nwb, "session_id", None)}
        if id_map:
            meta["unit_id_map"] = id_map
    if times.size and times.min() < 0:
        if not shift_negative:
            raise ValueError("NWB spike times before session start (negative): pass shift_negative=True "
                             "to shift all times so the session starts at 0")
        offset = -float(times.min())
        times = times + offset
        if events is not None:
            events = Events(events.times + offset, events.labels)
        meta["time_offset_s"] = offset
    return Bundle(times, clusters, amplitudes=amps, unit_ids=uid, unit_depths=unit_depths,
                  events=events, meta=meta)


_IBL_EVENTS = {
    # name: (time column, how to label each trial)
    "feedback": ("feedback_times", "feedbackType"),
    "stimulus": ("stimOn_times", "side"),
    "choice": ("firstMovement_times", "choice"),
}


def _col(table, name):
    if table is None:
        return None
    try:
        v = table[name]
    except (KeyError, IndexError, TypeError):
        return None
    return np.asarray(v)


def ibl_events(trials, event: str = "feedback") -> Events:
    """Events from an IBL trials table (``SessionLoader.trials`` or ``one.load_object(eid, 'trials')``).

    ``feedback``: feedback times labelled correct (1) / error (-1);
    ``stimulus``: stimulus onsets labelled by side (left / right; zero-contrast trials dropped);
    ``choice``: first-movement times labelled by choice (-1 / 1; no-go trials dropped).
    """
    if event not in _IBL_EVENTS:
        raise ValueError(f"event must be one of {sorted(_IBL_EVENTS)}")
    tcol, lcol = _IBL_EVENTS[event]
    times = _col(trials, tcol)
    if times is None:
        raise ValueError(f"trials have no {tcol!r} column")
    times = times.astype(float)
    if lcol == "side":
        left, right = _col(trials, "contrastLeft"), _col(trials, "contrastRight")
        left = np.nan_to_num(left.astype(float)) if left is not None else np.zeros(times.size)
        right = np.nan_to_num(right.astype(float)) if right is not None else np.zeros(times.size)
        labels = np.where(left > 0, "left", np.where(right > 0, "right", ""))
    else:
        labels = _col(trials, lcol)
        if labels is None:
            raise ValueError(f"trials have no {lcol!r} column")
        labels = np.asarray(labels).astype(float)
        labels = np.where(np.isfinite(labels) & (labels != 0), labels, np.nan)
    ok = np.isfinite(times) & np.array([str(x) not in ("", "nan") for x in labels])
    lab = labels[ok]
    if lab.dtype.kind == "f":
        lab = lab.astype(int)
    return Events(times[ok], lab)


def ibl_metrics(clusters) -> dict[str, dict[int, float]]:
    """Per-cluster metrics from an IBL clusters table (``label`` is IBL's 0-1 quality score)."""
    out: dict[str, dict[int, float]] = {}
    if clusters is None:
        return out
    ids = _col(clusters, "cluster_id")
    keys = clusters.keys() if hasattr(clusters, "keys") else []
    for k in keys:
        v = _col(clusters, k)
        if v is None or v.ndim != 1 or k in ("cluster_id", "uuids"):
            continue
        try:
            v = v.astype(float)
        except (TypeError, ValueError):
            continue
        idx = ids if ids is not None and len(ids) == len(v) else np.arange(len(v))
        out[str(k)] = {int(i): float(x) for i, x in zip(idx, v)}
    return out


def from_ibl(spikes, clusters=None, trials=None, *, event: str | None = "feedback",
             duration: float | None = None, meta: dict | None = None) -> Bundle:
    """Read IBL spike sorting (``SpikeSortingLoader.load_spike_sorting()``) into a bundle.

    ``spikes`` needs ``times`` and ``clusters`` and may have ``amps`` (V, stored as µV)
    and ``depths`` (µm). ``trials`` (optional) gives events, see :func:`ibl_events`.
    Cluster metrics, including IBL's ``label``, are kept in ``meta['ibl_metrics']``
    for ``ayar multiverse``.
    """
    times = np.asarray(spikes["times"], dtype=float)
    clus = np.asarray(spikes["clusters"]).astype(np.int64)
    amps = _col(spikes, "amps")
    depths = _col(spikes, "depths")
    ok = np.isfinite(times)
    if times[ok].size and times[ok].min() < 0:
        raise ValueError("IBL spike times before 0 are not expected")
    events = ibl_events(trials, event) if (trials is not None and event) else None
    m = {"source": "ibl", **(meta or {})}
    mt = ibl_metrics(clusters)
    if mt:
        m["ibl_metrics"] = {k: {str(u): v for u, v in d.items()} for k, d in mt.items()}
    return Bundle(times[ok], clus[ok], duration=duration,
                  amplitudes=None if amps is None else np.abs(amps.astype(float)[ok]) * 1e6,
                  spike_depths=None if depths is None else depths.astype(float)[ok],
                  events=events, meta=m)


def from_alf(folder: str | Path, *, trials_folder: str | Path | None = None, event: str | None = "feedback",
             duration: float | None = None) -> Bundle:
    """Read IBL/ALF files from disk: ``spikes.times.npy``, ``spikes.clusters.npy`` and optionally
    ``spikes.amps.npy``, ``spikes.depths.npy``, ``clusters.*.npy`` and (in ``trials_folder``)
    ``_ibl_trials.*.npy`` / ``trials.*.npy``."""
    folder = Path(folder)

    def obj(dirpath, name):
        out = {}
        for f in sorted(Path(dirpath).glob(f"*{name}.*.npy")):
            parts = f.name.split(".")
            i = parts.index(name) if name in parts else len(parts) - 3
            out[parts[i + 1]] = np.load(f, allow_pickle=False)
        return out

    spikes = obj(folder, "spikes")
    if "times" not in spikes or "clusters" not in spikes:
        raise FileNotFoundError(f"{folder} has no spikes.times.npy / spikes.clusters.npy")
    clusters = obj(folder, "clusters") or None
    trials = obj(trials_folder, "trials") if trials_folder else None
    if clusters is not None and "cluster_id" not in clusters:
        n = max(len(v) for v in clusters.values())
        clusters["cluster_id"] = np.arange(n)
    return from_ibl(spikes, clusters, trials or None, event=event, duration=duration,
                    meta={"folder": str(folder)})


def load(path: str | Path, **kwargs) -> Bundle:
    """Load a bundle from a ``.npz`` file, an ``.nwb`` file, a Phy/Kilosort folder,
    or a saved SpikeInterface SortingAnalyzer folder."""
    path = Path(path)
    if path.is_dir():
        if (path / "spike_times.npy").exists():
            return from_phy(path, **kwargs)
        if any(path.glob("*spikes.times.npy")):
            return from_alf(path, **kwargs)
        try:
            import spikeinterface as si  # noqa: F401
            from spikeinterface import load_sorting_analyzer
        except ImportError:
            raise ValueError(f"{path} is not a Phy/Kilosort folder (no spike_times.npy)") from None
        return from_spikeinterface(load_sorting_analyzer(path), **kwargs)
    if path.suffix == ".nwb":
        return from_nwb(path, **kwargs)
    if path.is_dir() and (path / "spikes.times.npy").exists():
        return from_alf(path, **kwargs)
    if path.suffix == ".zarr":
        from spikeinterface import load_sorting_analyzer

        return from_spikeinterface(load_sorting_analyzer(path), **kwargs)
    return Bundle.load(path)
