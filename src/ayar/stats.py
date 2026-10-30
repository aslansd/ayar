"""Small, exact spike-train statistics shared by detectors and examples."""

from __future__ import annotations

import numpy as np


def count_within(a: np.ndarray, b: np.ndarray, w: float) -> int:
    """Number of pairs (i, j) with |b[j] - a[i]| <= w. Both inputs sorted."""
    if a.size == 0 or b.size == 0:
        return 0
    hi = np.searchsorted(b, a + w, side="right")
    lo = np.searchsorted(b, a - w, side="left")
    return int((hi - lo).sum())


def count_strictly_within(a: np.ndarray, b: np.ndarray, w: float) -> int:
    """Number of pairs with |b[j] - a[i]| < w."""
    if a.size == 0 or b.size == 0:
        return 0
    hi = np.searchsorted(b, a + w, side="left")
    lo = np.searchsorted(b, a - w, side="right")
    return int((hi - lo).sum())


def has_partner(a: np.ndarray, b: np.ndarray, w: float) -> np.ndarray:
    """Boolean per spike of ``a``: is there a ``b`` spike within ±w?"""
    if a.size == 0:
        return np.zeros(0, dtype=bool)
    if b.size == 0:
        return np.zeros(a.size, dtype=bool)
    hi = np.searchsorted(b, a + w, side="right")
    lo = np.searchsorted(b, a - w, side="left")
    return hi > lo


def ccg(a: np.ndarray, b: np.ndarray, bin_s: float, window_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Cross-correlogram counts of b relative to a. Returns (bin_centers, counts)."""
    edges = np.arange(-window_s, window_s + bin_s / 2, bin_s)
    counts = np.zeros(edges.size - 1, dtype=np.int64)
    if a.size == 0 or b.size == 0:
        return (edges[:-1] + edges[1:]) / 2, counts
    lo = np.searchsorted(b, a - window_s, side="left")
    hi = np.searchsorted(b, a + window_s, side="right")
    lags = np.concatenate([b[l:h] - t for t, l, h in zip(a, lo, hi)]) if a.size else np.array([])
    counts, _ = np.histogram(lags, bins=edges)
    return (edges[:-1] + edges[1:]) / 2, counts


def windowed(times: np.ndarray, values: np.ndarray | None, duration: float, window: float,
             min_count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per time window: centre, spike rate (Hz) and median value (NaN if too few spikes)."""
    n_win = max(int(np.floor(duration / window)), 1)
    edges = np.linspace(0.0, n_win * window, n_win + 1)
    idx = np.clip(np.searchsorted(edges, times, side="right") - 1, 0, n_win - 1)
    counts = np.bincount(idx, minlength=n_win)
    rates = counts / window
    med = np.full(n_win, np.nan)
    if values is not None:
        order = np.argsort(idx, kind="stable")
        sorted_idx = idx[order]
        sv = values[order]
        starts = np.searchsorted(sorted_idx, np.arange(n_win), side="left")
        ends = np.searchsorted(sorted_idx, np.arange(n_win), side="right")
        for k, (s, e) in enumerate(zip(starts, ends)):
            if e - s >= min_count:
                med[k] = np.median(sv[s:e])
    centres = (edges[:-1] + edges[1:]) / 2
    return centres, rates, med


def missing_fraction(amplitudes: np.ndarray, n_bins: int = 50) -> float:
    """Fraction of a unit's spikes lost below the detection threshold.

    The amplitude-cutoff estimate (Hill et al. 2011; Allen Institute): the
    amplitude histogram is cut at its low end; the mass in the upper tail beyond
    the point where the density falls back to its height at the cut estimates
    the missing lower tail. Capped at 0.5 (the estimate fails past the peak).
    """
    a = np.asarray(amplitudes, dtype=float)
    if a.size < 2 or np.ptp(a) == 0:
        return float("nan")
    h, e = np.histogram(a, bins=n_bins)
    kernel = np.exp(-0.5 * np.arange(-3, 4) ** 2)
    kernel /= kernel.sum()
    pdf = np.convolve(np.pad(h.astype(float), 3, mode="edge"), kernel, mode="valid")
    width = e[1] - e[0]
    pdf /= pdf.sum() * width
    peak = int(np.argmax(pdf))
    g = peak + int(np.argmin(np.abs(pdf[peak:] - pdf[0])))
    return float(min(pdf[g:].sum() * width, 0.5))


def windowed_completeness(times: np.ndarray, amplitudes: np.ndarray, duration: float,
                          n_windows: int) -> tuple[np.ndarray, np.ndarray]:
    """Per window: spike rate (Hz) and estimated detection completeness (1 - missing)."""
    window = duration / n_windows
    idx = np.clip((times // window).astype(int), 0, n_windows - 1)
    counts = np.bincount(idx, minlength=n_windows)
    rates = counts / window
    comp = np.full(n_windows, np.nan)
    usable = counts >= 30
    if not usable.any():
        return rates, comp
    # the estimate is biased by sample size, so compare windows at equal spike counts
    n_eq = int(counts[usable].min())
    rng = np.random.default_rng(0)
    for k in np.flatnonzero(usable):
        s = amplitudes[idx == k]
        if s.size == n_eq:
            comp[k] = 1.0 - missing_fraction(s)
        else:
            reps = [missing_fraction(rng.choice(s, n_eq, replace=False)) for _ in range(5)]
            comp[k] = 1.0 - float(np.mean(reps))
    return rates, comp


def poisson_lower_p(k: int, mu: float) -> float:
    """P(X <= k) for X ~ Poisson(mu)."""
    from scipy.stats import poisson

    return float(poisson.cdf(k, mu))
