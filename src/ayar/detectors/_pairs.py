"""Which unit pairs a pair detector should test."""

from __future__ import annotations

from itertools import combinations

import numpy as np

from ..bundle import Bundle


def candidate_pairs(
    bundle: Bundle, units: list[int], max_distance_um: float, max_pairs: int, max_spike_pairs: float = float("inf")
) -> tuple[list[tuple[int, int]] | None, str]:
    """Pairs within ``max_distance_um`` when depths are known, else all pairs.

    Returns ``(None, reason)`` when, without depths, there are more than ``max_pairs``
    unit pairs or the all-pairs sweep would visit more than ``max_spike_pairs`` spike pairs.
    """
    if bundle.has_depths:
        depths = {u: bundle.position(u) for u in units}
        known = [u for u in units if depths[u] is not None and np.isfinite(depths[u])]
        known.sort(key=lambda u: depths[u])
        pairs: list[tuple[int, int]] = []
        d = np.array([depths[u] for u in known])
        for i, u in enumerate(known):
            j_end = int(np.searchsorted(d, d[i] + max_distance_um, side="right"))
            pairs.extend((u, known[j]) for j in range(i + 1, j_end))
        return pairs, f"pairs within {max_distance_um:g} µm"
    n = len(units) * (len(units) - 1) // 2
    if n > max_pairs:
        return None, (
            f"{n} unit pairs and no depths to restrict them; add amplitudes/depths "
            f"(tier 1) or raise max_pairs"
        )
    if max_spike_pairs != float("inf"):
        from ..pairstats import estimate_spike_pairs

        est = estimate_spike_pairs(bundle, units, 0.010)
        if est > max_spike_pairs:
            return None, (
                f"about {est:.1e} coincident spike pairs to count across {n} unit pairs and no "
                "depths to restrict them; add amplitudes/depths (tier 1) or raise max_spike_pairs"
            )
    return list(combinations(units, 2)), "all pairs (no depths)"


def pair_counts(bundle: Bundle, th, pairs: list[tuple[int, int]]):
    """Coincidence counts per window for ordered ``pairs`` (shared all-pairs sweep)."""
    from ..pairstats import for_detectors

    return for_detectors(bundle, th).counts(pairs)
