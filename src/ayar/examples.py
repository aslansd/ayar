"""Example findings: functions of a bundle that return the numbers a paper would report.

Use them as templates for your own. A finding is any ``f(bundle) -> float | dict``;
ayar recomputes it with flagged units repaired and tells you whether it holds.

When ayar repairs a drifting unit by restricting it to its stable epoch, a finding
that averages over trials should skip the trials outside that epoch:
``bundle.in_epochs(unit, start_times, stop_times)`` gives the mask (see
``unit_condition_contrast``).

    ayar scan session.npz --finding ayar.examples:condition_contrast
"""

from __future__ import annotations

import warnings

import numpy as np

from .bundle import Bundle
from .stats import count_strictly_within, count_within


def _trial_rates(train: np.ndarray, times: np.ndarray, w0: float, w1: float) -> np.ndarray:
    hi = np.searchsorted(train, times + w1, side="left")
    lo = np.searchsorted(train, times + w0, side="left")
    return (hi - lo) / (w1 - w0)


def unit_condition_contrast(
    bundle: Bundle, window: tuple[float, float] = (0.0, 0.5)
) -> dict[int, tuple[float, float]]:
    """Per unit: (rate difference in Hz, Welch t-test p) for the second condition minus the first."""
    from scipy.stats import ttest_ind

    ev = bundle.events
    if ev is None or ev.labels is None or ev.label_values.size != 2:
        raise ValueError("condition_contrast needs events with exactly two condition labels")
    a, b = ev.label_values
    ta, tb = ev.times[ev.labels == a], ev.times[ev.labels == b]
    units = [int(u) for u in bundle.unit_ids]
    ra = np.array([_trial_rates(bundle.train(u), ta, *window) for u in units], dtype=float)
    rb = np.array([_trial_rates(bundle.train(u), tb, *window) for u in units], dtype=float)
    # units restricted to stable epochs count only the trials they were recorded for
    for i, u in enumerate(units):
        if u in bundle.epochs:
            ra[i, ~bundle.in_epochs(u, ta + window[0], ta + window[1])] = np.nan
            rb[i, ~bundle.in_epochs(u, tb + window[0], tb + window[1])] = np.nan
    na, nb = np.isfinite(ra).sum(axis=1), np.isfinite(rb).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        diff = np.nanmean(rb, axis=1) - np.nanmean(ra, axis=1)
        flat = (np.nanstd(ra, axis=1) + np.nanstd(rb, axis=1)) == 0
        p = ttest_ind(rb, ra, axis=1, equal_var=False, nan_policy="omit").pvalue
    p = np.where(flat | ~np.isfinite(np.asarray(p, dtype=float)), 1.0, np.asarray(p, dtype=float))
    few = (na < 2) | (nb < 2)
    diff = np.where(few, np.nan, diff)
    p = np.where(few, 1.0, p)
    return {u: (float(d), float(q)) for u, d, q in zip(units, diff, p)}


def condition_contrast(bundle: Bundle, alpha: float = 0.01) -> dict[str, float]:
    """The numbers a paper would report about a two-condition effect.

    ``mean_contrast_hz``        mean rate difference across units
    ``frac_units_enhanced``     fraction of units significantly higher in condition 2
    ``frac_units_suppressed``   fraction of units significantly lower in condition 2
    """
    res = np.array(list(unit_condition_contrast(bundle).values()))
    diff, p = res[:, 0], res[:, 1]
    ok = np.isfinite(diff)  # units with too few trials inside their epochs are left out
    diff, p = diff[ok], p[ok]
    return {
        "mean_contrast_hz": float(diff.mean()) if diff.size else float("nan"),
        "frac_units_enhanced": float(np.mean((p < alpha) & (diff > 0))) if diff.size else float("nan"),
        "frac_units_suppressed": float(np.mean((p < alpha) & (diff < 0))) if diff.size else float("nan"),
    }


def zero_lag_synchrony(bundle: Bundle, max_distance_um: float = 100.0, window_ms: float = 1.0) -> dict[str, float]:
    """Mean ratio of ±window coincidences to their 2-10 ms flank expectation, over nearby pairs."""
    w = window_ms / 1000.0
    f1, f2 = 0.002, 0.010
    units = [int(u) for u in bundle.unit_ids if bundle.train(u).size >= 100]
    depth = {u: bundle.depth(u) for u in units}
    ratios = []
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            if depth[a] is not None and depth[b] is not None and abs(depth[a] - depth[b]) > max_distance_um:
                continue
            ta, tb = bundle.train(a), bundle.train(b)
            flank = count_within(ta, tb, f2) - count_strictly_within(ta, tb, f1)
            expected = flank * w / (f2 - f1)
            if expected >= 5:
                ratios.append(count_within(ta, tb, w) / expected)
    return {"mean_sync_ratio": float(np.mean(ratios)) if ratios else float("nan")}
