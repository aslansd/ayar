"""The ayar bundle: the one input contract every detector reads.

A bundle is the output of *any* spike sorter reduced to what ayar needs:

* ``spike_times`` (seconds) and ``spike_clusters`` (unit id per spike): tier 0
* ``amplitudes`` and/or ``spike_depths`` / ``unit_depths``: tier 1
* ``events`` (trial times, optional condition labels): needed for confound checks

Bundles are saved as plain ``.npz`` files that numpy can read without ayar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

FORMAT_VERSION = 1


class Events:
    """Trial or event times, with an optional condition label per event."""

    def __init__(self, times: Iterable[float], labels: Iterable[Any] | None = None):
        times = np.asarray(times, dtype=float).ravel()
        if not np.all(np.isfinite(times)):
            raise ValueError("event times must be finite")
        order = np.argsort(times, kind="stable")
        self.times = times[order]
        if labels is None:
            self.labels = None
        else:
            labels = np.asarray(labels).ravel()
            if labels.shape[0] != times.shape[0]:
                raise ValueError(
                    f"{labels.shape[0]} event labels for {times.shape[0]} event times"
                )
            self.labels = labels[order]

    def __len__(self) -> int:
        return int(self.times.shape[0])

    @property
    def label_values(self) -> np.ndarray:
        if self.labels is None:
            return np.array([])
        return np.unique(self.labels)

    def __repr__(self) -> str:
        n_lab = len(self.label_values)
        return f"Events(n={len(self)}, labels={n_lab if self.labels is not None else None})"


class Bundle:
    """Sorted spikes plus whatever extra evidence the sorter provides."""

    def __init__(
        self,
        spike_times: Iterable[float],
        spike_clusters: Iterable[int],
        *,
        duration: float | None = None,
        amplitudes: Iterable[float] | None = None,
        spike_depths: Iterable[float] | None = None,
        unit_ids: Iterable[int] | None = None,
        unit_depths: Iterable[float] | Mapping[int, float] | None = None,
        events: Events | tuple | Mapping | None = None,
        meta: Mapping[str, Any] | None = None,
    ):
        st = np.asarray(spike_times, dtype=float).ravel()
        sc = np.asarray(spike_clusters).ravel()
        if st.shape != sc.shape:
            raise ValueError(f"{st.size} spike times but {sc.size} spike clusters")
        if not np.all(np.isfinite(st)):
            raise ValueError("spike times must be finite")
        if st.size and st.min() < 0:
            raise ValueError("spike times must be >= 0 (seconds from session start)")
        sc = sc.astype(np.int64)

        if st.size > 1 and np.any(np.diff(st) < 0):
            order = np.argsort(st, kind="stable")
        else:
            order = np.arange(st.size)  # already sorted: skip the O(n log n) sort
        self.spike_times = st[order]
        self.spike_clusters = sc[order]
        self.amplitudes = self._per_spike(amplitudes, order, "amplitudes")
        self.spike_depths = self._per_spike(spike_depths, order, "spike_depths")

        if unit_ids is None:
            self.unit_ids = np.unique(self.spike_clusters)
        else:
            self.unit_ids = np.unique(np.asarray(list(unit_ids), dtype=np.int64))
            missing = np.setdiff1d(np.unique(self.spike_clusters), self.unit_ids)
            if missing.size:
                raise ValueError(f"spikes belong to units not in unit_ids: {missing[:10].tolist()}")

        self.unit_depths = self._unit_depths(unit_depths)

        last = float(self.spike_times[-1]) if self.spike_times.size else 0.0
        if duration is None:
            duration = last
        if duration < last:
            raise ValueError(f"duration {duration} s is shorter than the last spike at {last} s")
        self.duration = float(duration)

        self.events = self._events(events)
        self.meta: dict[str, Any] = dict(meta or {})
        self._index: dict[int, np.ndarray] | None = None

    # ------------------------------------------------------------------ build
    def _per_spike(self, values, order, name):
        if values is None:
            return None
        v = np.asarray(values, dtype=float).ravel()
        if v.shape[0] != order.shape[0]:
            raise ValueError(f"{name} has {v.shape[0]} values for {order.shape[0]} spikes")
        return v[order]

    def _unit_depths(self, unit_depths):
        if unit_depths is None:
            return None
        if isinstance(unit_depths, Mapping):
            d = np.array([float(unit_depths.get(int(u), np.nan)) for u in self.unit_ids])
        else:
            d = np.asarray(unit_depths, dtype=float).ravel()
            if d.shape[0] != self.unit_ids.shape[0]:
                raise ValueError(
                    f"unit_depths has {d.shape[0]} values for {self.unit_ids.shape[0]} units"
                )
        return d

    @staticmethod
    def _events(events):
        if events is None or isinstance(events, Events):
            return events
        if isinstance(events, Mapping):
            return Events(events["times"], events.get("labels"))
        if isinstance(events, tuple):
            return Events(*events)
        return Events(events)

    def _build_index(self) -> dict[int, np.ndarray]:
        order = np.argsort(self.spike_clusters, kind="stable")  # stable keeps time order
        sorted_c = self.spike_clusters[order]
        starts = np.searchsorted(sorted_c, self.unit_ids, side="left")
        ends = np.searchsorted(sorted_c, self.unit_ids, side="right")
        return {int(u): order[s:e] for u, s, e in zip(self.unit_ids, starts, ends)}

    # ----------------------------------------------------------------- access
    def spike_indices(self, unit: int) -> np.ndarray:
        if self._index is None:
            self._index = self._build_index()
        try:
            return self._index[int(unit)]
        except KeyError:
            raise KeyError(f"no unit {unit} in bundle") from None

    def train(self, unit: int) -> np.ndarray:
        """Sorted spike times (s) of one unit."""
        return self.spike_times[self.spike_indices(unit)]

    def trains(self) -> dict[int, np.ndarray]:
        return {int(u): self.train(u) for u in self.unit_ids}

    def unit_amplitudes(self, unit: int) -> np.ndarray | None:
        if self.amplitudes is None:
            return None
        return self.amplitudes[self.spike_indices(unit)]

    def unit_spike_depths(self, unit: int) -> np.ndarray | None:
        if self.spike_depths is None:
            return None
        return self.spike_depths[self.spike_indices(unit)]

    def depth(self, unit: int) -> float | None:
        """Unit depth (µm) from ``unit_depths``, else the median spike depth."""
        if self.unit_depths is not None:
            i = int(np.searchsorted(self.unit_ids, int(unit)))
            v = float(self.unit_depths[i])
            if np.isfinite(v):
                return v
        d = self.unit_spike_depths(unit)
        if d is not None and d.size:
            return float(np.median(d))
        return None

    def rate(self, unit: int) -> float:
        return len(self.spike_indices(unit)) / self.duration if self.duration > 0 else 0.0

    @property
    def n_units(self) -> int:
        return int(self.unit_ids.shape[0])

    @property
    def n_spikes(self) -> int:
        return int(self.spike_times.shape[0])

    @property
    def has_amplitudes(self) -> bool:
        return self.amplitudes is not None

    @property
    def has_depths(self) -> bool:
        return self.unit_depths is not None or self.spike_depths is not None

    @property
    def tier(self) -> int:
        """0: spike times only. 1: plus amplitudes or depths."""
        return 1 if (self.has_amplitudes or self.has_depths) else 0

    # -------------------------------------------------------------- transform
    def without(self, units: Iterable[int]) -> "Bundle":
        """A new bundle with the given units removed (used by the finding audit)."""
        drop = np.asarray(sorted({int(u) for u in units}), dtype=np.int64)
        keep_unit = ~np.isin(self.unit_ids, drop)
        if self._index is None:
            self._index = self._build_index()
        keep_spk = np.ones(self.n_spikes, dtype=bool)
        for u in drop:
            if int(u) in self._index:
                keep_spk[self._index[int(u)]] = False
        new_pos = np.cumsum(keep_spk) - 1
        child_index = {
            int(u): new_pos[self._index[int(u)]] for u in self.unit_ids[keep_unit]
        }
        # internal fast path: the parent is already validated and sorted
        child = object.__new__(Bundle)
        child.spike_times = self.spike_times[keep_spk]
        child.spike_clusters = self.spike_clusters[keep_spk]
        child.amplitudes = None if self.amplitudes is None else self.amplitudes[keep_spk]
        child.spike_depths = None if self.spike_depths is None else self.spike_depths[keep_spk]
        child.unit_ids = self.unit_ids[keep_unit]
        child.unit_depths = None if self.unit_depths is None else self.unit_depths[keep_unit]
        child.duration = self.duration
        child.events = self.events
        child.meta = self.meta
        child._index = child_index
        return child

    def merge(self, pairs: Iterable[tuple[int, int]], dedupe_s: float = 0.0) -> "Bundle":
        """A new bundle where each ``(keep, absorb)`` pair becomes one unit.

        Chains are resolved (merging b into a and c into b puts all three into a).
        Spikes of an absorbed unit that fall within ``dedupe_s`` of a spike already
        in the merged unit are dropped, so merging a duplicate does not double-count.
        """
        parent: dict[int, int] = {}

        def root(u: int) -> int:
            while parent.get(u, u) != u:
                u = parent[u]
            return u

        for keep, absorb in pairs:
            rk, ra = root(int(keep)), root(int(absorb))
            if rk != ra:
                parent[ra] = rk
        if not parent:
            return self.without([])
        if self._index is None:
            self._index = self._build_index()
        clusters = self.spike_clusters.copy()
        keep_spk = np.ones(self.n_spikes, dtype=bool)
        groups: dict[int, list[int]] = {}
        for u in parent:
            groups.setdefault(root(u), []).append(u)
        for r, members in groups.items():
            base = self.spike_times[self._index[r]]
            for m in members:
                idx = self._index[m]
                if dedupe_s > 0 and base.size and idx.size:
                    t = self.spike_times[idx]
                    hi = np.searchsorted(base, t + dedupe_s, side="right")
                    lo = np.searchsorted(base, t - dedupe_s, side="left")
                    keep_spk[idx[hi > lo]] = False
                clusters[idx] = r
                base = np.sort(np.concatenate([base, self.spike_times[idx][keep_spk[idx]]]))
        absorbed = np.asarray(sorted(parent), dtype=np.int64)
        keep_unit = ~np.isin(self.unit_ids, absorbed)
        child = object.__new__(Bundle)
        child.spike_times = self.spike_times[keep_spk]
        child.spike_clusters = clusters[keep_spk]
        child.amplitudes = None if self.amplitudes is None else self.amplitudes[keep_spk]
        child.spike_depths = None if self.spike_depths is None else self.spike_depths[keep_spk]
        child.unit_ids = self.unit_ids[keep_unit]
        child.unit_depths = None if self.unit_depths is None else self.unit_depths[keep_unit]
        child.duration = self.duration
        child.events = self.events
        child.meta = self.meta
        # derive the child's per-unit index from the parent's instead of re-sorting
        new_pos = np.cumsum(keep_spk) - 1
        child_index: dict[int, np.ndarray] = {}
        for u in child.unit_ids:
            u = int(u)
            parts = [self._index[u]] + [self._index[m] for m in groups.get(u, [])]
            idx = np.concatenate(parts)
            idx = np.sort(idx[keep_spk[idx]])
            child_index[u] = new_pos[idx]
        child._index = child_index
        return child

    def summary(self) -> dict[str, Any]:
        ev = None
        if self.events is not None:
            ev = {
                "n": len(self.events),
                "labels": [str(v) for v in self.events.label_values] if self.events.labels is not None else None,
            }
        return {
            "n_units": self.n_units,
            "n_spikes": self.n_spikes,
            "duration_s": round(self.duration, 3),
            "tier": self.tier,
            "amplitudes": self.has_amplitudes,
            "depths": self.has_depths,
            "events": ev,
            "source": self.meta.get("source"),
        }

    def __repr__(self) -> str:
        return (
            f"Bundle(units={self.n_units}, spikes={self.n_spikes}, "
            f"duration={self.duration:.1f}s, tier={self.tier})"
        )

    # --------------------------------------------------------------------- io
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        if path.suffix != ".npz":
            path = path.with_suffix(".npz")
        arrays: dict[str, np.ndarray] = {
            "format_version": np.array(FORMAT_VERSION),
            "spike_times": self.spike_times,
            "spike_clusters": self.spike_clusters,
            "unit_ids": self.unit_ids,
            "duration": np.array(self.duration),
            "meta_json": np.array(json.dumps(self.meta, default=_json_default)),
        }
        if self.amplitudes is not None:
            arrays["amplitudes"] = self.amplitudes
        if self.spike_depths is not None:
            arrays["spike_depths"] = self.spike_depths
        if self.unit_depths is not None:
            arrays["unit_depths"] = self.unit_depths
        if self.events is not None:
            arrays["event_times"] = self.events.times
            if self.events.labels is not None:
                labels = self.events.labels
                if labels.dtype == object:
                    labels = labels.astype(str)
                arrays["event_labels"] = labels
        np.savez_compressed(path, **arrays)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Bundle":
        with np.load(Path(path), allow_pickle=False) as z:
            version = int(z["format_version"]) if "format_version" in z else 1
            if version > FORMAT_VERSION:
                raise ValueError(
                    f"bundle format {version} is newer than this ayar supports ({FORMAT_VERSION})"
                )
            get = lambda k: z[k] if k in z else None  # noqa: E731
            events = None
            if "event_times" in z:
                events = Events(z["event_times"], get("event_labels"))
            meta = json.loads(str(z["meta_json"])) if "meta_json" in z else {}
            return cls(
                z["spike_times"],
                z["spike_clusters"],
                duration=float(z["duration"]) if "duration" in z else None,
                amplitudes=get("amplitudes"),
                spike_depths=get("spike_depths"),
                unit_ids=get("unit_ids"),
                unit_depths=get("unit_depths"),
                events=events,
                meta=meta,
            )


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")
