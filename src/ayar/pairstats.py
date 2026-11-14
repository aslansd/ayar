"""Coincidence counts for every pair of units at once.

The pair detectors (duplicates, splits, overlap holes, contamination sources) all ask
the same question of many unit pairs: how many spikes of unit *a* fall within some lag
of a spike of unit *b*? Answering it pair by pair costs a search per pair; on a
1000-unit Neuropixels session that is tens of thousands of searches over millions of
spikes.

This module answers it for all pairs in one sweep over the time-sorted spike train:
for k = 1, 2, ... it pairs every spike with the k-th next spike while their gap is at
most the longest lag needed, and adds each pair to a count per lag window. The work is
proportional to the number of spike pairs within that lag, not to the number of unit
pairs.

With depths, pairs are restricted to units within ``max_distance_um`` of each other:
the probe is cut into bands of that width and each band is swept together with the
next one, so only spikes of nearby units are ever paired. Without depths, every pair
is counted, which is what lets sessions without spike depths (many NWB files) get the
pair detectors at all.

All counts are exact: a count is what ``count_within(train(a), train(b), w)`` (an
inclusive window) or ``count_strictly_within`` (a strict one) returns, to the last
spike, including which side of a window bound a lag that equals the bound falls on
(common with sample-quantised times, and the reason the order of a and b can matter).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .bundle import Bundle

Window = tuple  # (inclusive: bool, seconds: float)


def windows_for(th) -> tuple[Window, ...]:
    """The lag windows the pair detectors read, from the thresholds."""
    from .metrics import REFRACTORY_S

    return tuple(sorted({
        (True, th.dup_window_ms / 1000.0),          # duplicates; double detections
        (True, th.dup_max_lag_ms / 1000.0),         # gate for time-shifted duplicates
        (True, th.overlap_center_ms / 1000.0),      # overlap-hole centre
        (False, th.split_outer_ms / 1000.0),        # inner edge of the split outer band
        (False, REFRACTORY_S),                      # refractory window
        (False, th.overlap_flank_lo_ms / 1000.0),   # inner edge of the flanks
        (True, th.overlap_flank_hi_ms / 1000.0),    # outer edge of the flanks
    }, key=lambda x: (x[1], x[0])))


class PairStats:
    """Coincidence counts for every pair among ``units``, looked up per ordered pair.

    ``count(a, b, window)`` and ``counts(pairs)`` return counts from ``a``'s side, as
    ``count_within(train(a), train(b), w)`` would. Pairs the sweep did not cover (too far
    apart in depth, or a unit without a depth) are counted directly.
    """

    def __init__(self, bundle, units, wins, sym, delta, band, scope, n_spike_pairs):
        self.bundle = bundle
        self.units = units
        self.pos = {int(u): i for i, u in enumerate(units)}
        self.wins = wins
        self.col = {w: i for i, w in enumerate(wins)}
        self._sym = sym      # (nu*nu, nw) cumulative counts, key lo*nu+hi, from lo's side
        self._delta = delta  # (nu*nu, nw) correction for hi's side, key hi*nu+lo
        self.band = band
        self.scope = scope
        self.n_spike_pairs = n_spike_pairs

    def _swept(self, ia: np.ndarray, ib: np.ndarray) -> np.ndarray:
        if self.band is None:
            return np.ones(ia.size, dtype=bool)
        ba, bb = self.band[ia], self.band[ib]
        return (ba >= 0) & (bb >= 0) & (np.abs(ba - bb) <= 1)

    def counts(self, pairs) -> dict[Window, np.ndarray]:
        """Counts for a list of ordered pairs (a, b), from a's side, per window."""
        pairs = list(pairs)
        nu = self.units.size
        out = {w: np.zeros(len(pairs), dtype=np.int64) for w in self.wins}
        if not pairs:
            return out
        ia = np.array([self.pos[int(a)] for a, _ in pairs], dtype=np.int64)
        ib = np.array([self.pos[int(b)] for _, b in pairs], dtype=np.int64)
        lo, hi = np.minimum(ia, ib), np.maximum(ia, ib)
        vals = self._sym[lo * nu + hi]
        rev = ia > ib
        if rev.any():
            vals[rev] += self._delta[ia[rev] * nu + ib[rev]]
        swept = self._swept(ia, ib)
        for r, w in enumerate(self.wins):
            out[w][:] = vals[:, r]
        for i in np.flatnonzero(~swept):  # rare: counted directly
            for w, v in _direct(self.bundle, pairs[i][0], pairs[i][1], self.wins).items():
                out[w][i] = v
        return out

    def count(self, a: int, b: int, window: Window) -> int:
        return int(self.counts([(a, b)])[window][0])


def _direct(bundle, a, b, wins) -> dict[Window, int]:
    from .stats import count_strictly_within, count_within

    ta, tb = bundle.train(int(a)), bundle.train(int(b))
    return {w: (count_within if w[0] else count_strictly_within)(ta, tb, w[1]) for w in wins}


def _bands(bundle: Bundle, units: np.ndarray, max_distance_um: float):
    pos = [bundle.position(int(u)) for u in units]
    depth = np.array([np.nan if v is None else v for v in pos])
    ok = np.isfinite(depth)
    band = np.full(units.size, -1, dtype=np.int64)
    if ok.any():
        band[ok] = np.floor((depth[ok] - np.nanmin(depth)) / max_distance_um).astype(np.int64)
    return depth, band


def estimate_spike_pairs(bundle: Bundle, units, max_lag: float, max_distance_um: float | None = None) -> float:
    """Expected number of spike pairs within ``max_lag`` the sweep will visit."""
    units = np.asarray(units)
    n = np.array([bundle.spike_indices(int(u)).size for u in units], dtype=float)
    T = max(bundle.duration, 1e-9)
    if max_distance_um is None or not bundle.has_depths:
        total = n.sum()
        return float(total * (total / T) * max_lag)
    _, band = _bands(bundle, units, max_distance_um)
    est = 0.0
    for b in np.unique(band[band >= 0]):
        sel = (band == b) | (band == b + 1)
        tot = n[sel].sum()
        est += tot * (tot / T) * max_lag
    return float(est)


def _ranks(xp, xo, p_first, wins):
    """First window containing each pair, tested from unit p's side (spike xp, other xo)."""
    nw = len(wins)
    rank = np.full(xp.size, nw, dtype=np.int64)
    for r in range(nw - 1, -1, -1):
        inclusive, w = wins[r]
        if inclusive:
            ok = np.where(p_first, xo <= xp + w, xo >= xp - w)
        else:
            ok = np.where(p_first, xo < xp + w, xo > xp - w)
        rank[ok] = r
    return rank


def compute(bundle: Bundle, units, windows, *, max_distance_um: float | None = None) -> PairStats:
    """Sweep the spike train once and count coincidences for all pairs of ``units``."""
    units = np.asarray(sorted(int(u) for u in units), dtype=np.int64)
    nu = units.size
    wins = sorted(set(windows), key=lambda x: (x[1], x[0]))  # strict before inclusive at equal bounds
    nw = len(wins)
    if nu * nu * nw > 60_000_000:
        raise MemoryError(f"{nu} units: too many for all-pairs statistics")
    max_lag = max(w[1] for w in wins)

    unit_of_spike = np.full(bundle.n_spikes, -1, dtype=np.int32)
    for i, u in enumerate(units):
        unit_of_spike[bundle.spike_indices(int(u))] = i
    keep = unit_of_spike >= 0
    t_all = bundle.spike_times[keep]
    u_all = unit_of_spike[keep]

    spatial = max_distance_um is not None and bundle.has_depths
    if spatial:
        _, band = _bands(bundle, units, max_distance_um)
        band32 = band.astype(np.int32)
        band_of_spike = band32[u_all]
        sweeps = [int(b) for b in np.unique(band[band >= 0])]
        scope = f"pairs within {max_distance_um:g} µm"
    else:
        band = band32 = band_of_spike = None
        sweeps = [None]
        scope = "all pairs (no depths)"

    bounds = np.array([w[1] for w in wins])
    tie_tol = 1e-9  # far above float rounding of times (~1e-12 s), far below a sample (>=1e-5 s)
    size = nu * nu * nw
    sym = np.zeros(size, dtype=np.int64)    # spike pairs by first window, from the lower unit's side
    delta = np.zeros(size, dtype=np.int64)  # higher unit's side minus lower unit's side (ties only)
    buf: list[np.ndarray] = []
    dbuf: list[tuple[np.ndarray, np.ndarray]] = []
    buffered = 0
    n_seen = 0

    def flush():
        nonlocal buffered
        if buf:
            sym[:] += np.bincount(np.concatenate(buf), minlength=size)
            buf.clear()
        if dbuf:
            codes = np.concatenate([c for c, _ in dbuf])
            weights = np.concatenate([w for _, w in dbuf])
            delta[:] += np.rint(np.bincount(codes, weights=weights, minlength=size)).astype(np.int64)
            dbuf.clear()
        buffered = 0

    for b in sweeps:
        if b is None:
            t, u = t_all, u_all
        else:
            sel = (band_of_spike == b) | (band_of_spike == b + 1)
            t, u = t_all[sel], u_all[sel]
        N = t.size
        idx = np.arange(N, dtype=np.int64)
        k = 1
        while idx.size:
            idx = idx[idx < N - k]
            if not idx.size:
                break
            dt = t[idx + k] - t[idx]
            close = dt <= max_lag + tie_tol  # pairs right at the bound are settled exactly below
            idx, dt = idx[close], dt[close]
            if not idx.size:
                break
            ua, ub = u[idx], u[idx + k]
            other = ua != ub
            if b is not None:
                # count a pair in the sweep of its lower band only, so no pair is counted twice
                other &= np.minimum(band32[ua], band32[ub]) == b
            sel = np.flatnonzero(other)
            if sel.size:
                ua_o, ub_o, dt_o = ua[sel], ub[sel], dt[sel]
                lo_u = np.minimum(ua_o, ub_o).astype(np.int64)
                hi_u = np.maximum(ua_o, ub_o).astype(np.int64)
                rank = np.searchsorted(bounds, dt_o, side="left")  # first bound >= lag
                # lags within rounding of a bound: test as count_within does, from each side
                near = np.abs(dt_o - bounds[np.minimum(rank, nw - 1)]) < tie_tol
                near |= np.abs(dt_o - bounds[np.maximum(rank - 1, 0)]) < tie_tol
                if near.any():
                    tt = np.flatnonzero(near)
                    xe = t[idx[sel[tt]]]       # earlier spike (unit ua)
                    xl = t[idx[sel[tt]] + k]   # later spike (unit ub)
                    lo_first = ua_o[tt] < ub_o[tt]  # the lower unit owns the earlier spike
                    xp = np.where(lo_first, xe, xl)
                    xo = np.where(lo_first, xl, xe)
                    r_lo = _ranks(xp, xo, lo_first, wins)
                    r_hi = _ranks(xo, xp, ~lo_first, wins)
                    rank[tt] = r_lo
                    diff = r_lo != r_hi
                    if diff.any():
                        key_hi = hi_u[tt][diff] * nu + lo_u[tt][diff]
                        for rr, wgt in ((r_hi[diff], 1.0), (r_lo[diff], -1.0)):
                            m = rr < nw
                            dbuf.append((key_hi[m] * nw + rr[m], np.full(int(m.sum()), wgt)))
                inw = rank < nw
                n_seen += int(sel.size)
                buf.append(((lo_u * nu + hi_u) * nw + rank)[inw])
                buffered += buf[-1].size
                if buffered > 20_000_000:
                    flush()
            k += 1
        flush()

    sym = np.cumsum(sym.reshape(nu * nu, nw), axis=1)  # first window and every wider one
    delta = np.cumsum(delta.reshape(nu * nu, nw), axis=1)
    return PairStats(bundle, units, wins, sym, delta, band, scope, n_seen)


def for_detectors(bundle: Bundle, th) -> PairStats:
    """All-pairs statistics for the units the pair detectors test, cached on the bundle."""
    units = tuple(int(u) for u in bundle.unit_ids if len(bundle.spike_indices(u)) >= th.min_spikes)
    md = max(th.dup_max_distance_um, th.overlap_max_distance_um, th.split_max_distance_um)
    key = (units, md, windows_for(th))
    cache = bundle.__dict__.setdefault("_pairstats_cache", {})
    if key not in cache:
        cache.clear()  # one set of thresholds at a time is enough
        cache[key] = compute(bundle, units, key[2], max_distance_um=md if bundle.has_depths else None)
    return cache[key]
