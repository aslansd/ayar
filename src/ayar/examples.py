"""Example findings: functions of a bundle that return the numbers a paper would report.

Use them as templates for your own. A finding is any ``f(bundle) -> float | dict``;
ayar recomputes it with flagged units removed and tells you whether it holds.

    ayar scan session.npz --finding ayar.examples:condition_contrast
"""

from __future__ import annotations

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
    ra = np.array([_trial_rates(bundle.train(u), ta, *window) for u in units])
    rb = np.array([_trial_rates(bundle.train(u), tb, *window) for u in units])
    diff = rb.mean(axis=1) - ra.mean(axis=1)
    flat = (ra.std(axis=1) + rb.std(axis=1)) == 0
    with np.errstate(invalid="ignore", divide="ignore"):
        p = ttest_ind(rb, ra, axis=1, equal_var=False).pvalue
    p = np.where(flat | ~np.isfinite(p), 1.0, p)
    return {u: (float(d), float(q)) for u, d, q in zip(units, diff, p)}


def condition_contrast(bundle: Bundle, alpha: float = 0.01) -> dict[str, float]:
    """The numbers a paper would report about a two-condition effect.

    ``mean_contrast_hz``        mean rate difference across units
    ``frac_units_enhanced``     fraction of units significantly higher in condition 2
    ``frac_units_suppressed``   fraction of units significantly lower in condition 2
    """
    res = np.array(list(unit_condition_contrast(bundle).values()))
    diff, p = res[:, 0], res[:, 1]
    return {
        "mean_contrast_hz": float(diff.mean()),
        "frac_units_enhanced": float(np.mean((p < alpha) & (diff > 0))),
        "frac_units_suppressed": float(np.mean((p < alpha) & (diff < 0))),
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
