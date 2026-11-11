"""OVERLAP_HOLE: a near-zero-lag gap in the cross-correlogram of two nearby units.

Independent neurons fire together at zero lag about as often as at a few
milliseconds' lag. When a sorter fails to resolve spatially and temporally
overlapping spikes, it drops one of them, which carves a hole around zero lag.
The same hole appears when one neuron has been split into two units (they share
a refractory period). Either way, synchrony between these units is wrong.
"""

from __future__ import annotations

from ..bundle import Bundle
from ..config import Thresholds
from ..flags import Flag, NotChecked, Severity
from ..stats import poisson_lower_p
from ._pairs import candidate_pairs, pair_counts
from .split import looks_refractory_split, refractory_stats

CODE = "OVERLAP_HOLE"
TIER = 0
ACTION = "remove"
FIX = (
    "inspect each pair's cross-correlogram and templates; merge pairs whose templates match, "
    "otherwise exclude the pair from synchrony and correlation analyses"
)


def run(bundle: Bundle, th: Thresholds) -> tuple[list[Flag], list[NotChecked]]:
    units = [int(u) for u in bundle.unit_ids if len(bundle.spike_indices(u)) >= th.min_spikes]
    pairs, scope = candidate_pairs(bundle, units, th.overlap_max_distance_um, th.max_pairs, th.max_spike_pairs)
    if pairs is None:
        return [], [NotChecked(CODE, scope)]

    c = th.overlap_center_ms / 1000.0
    f1 = th.overlap_flank_lo_ms / 1000.0
    f2 = th.overlap_flank_hi_ms / 1000.0
    # flank covers f1 <= |lag| <= f2 on both sides: width 2*(f2-f1); centre width 2*c
    scale = c / (f2 - f1)

    counts = pair_counts(bundle, th, pairs)
    tested: list[tuple[int, int, int, float, int]] = []
    underpowered = 0
    for i, (a, b) in enumerate(pairs):
        n_center = int(counts[(True, c)][i])
        n_flank = int(counts[(True, f2)][i] - counts[(False, f1)][i])
        expected = n_flank * scale
        if expected < th.overlap_min_expected:
            underpowered += 1
            continue
        tested.append((a, b, n_center, expected, i))

    alpha = th.overlap_alpha / max(len(tested), 1)  # Bonferroni over tested pairs
    flags: list[Flag] = []
    for a, b, n_center, expected, i in tested:
        ratio = n_center / expected
        if ratio > th.overlap_ratio_warn:
            continue
        p = poisson_lower_p(n_center, expected)
        if p >= alpha:
            continue
        if looks_refractory_split(refractory_stats(bundle, a, b, th, {w: v[i] for w, v in counts.items()}), th, alpha):
            continue  # the whole refractory period is empty: reported as SPLIT_UNIT
        sev = Severity.ERROR if ratio <= th.overlap_ratio_error else Severity.WARNING
        da, db = bundle.depth(a), bundle.depth(b)
        dist = None if da is None or db is None else round(abs(da - db), 1)
        flags.append(
            Flag(
                code=CODE,
                severity=sev,
                units=(a, b),
                message=(
                    f"units {a} and {b} fire within ±{th.overlap_center_ms:g} ms {ratio:.0%} as often "
                    f"as expected from the {th.overlap_flank_lo_ms:g}-{th.overlap_flank_hi_ms:g} ms flanks "
                    f"({n_center} vs {expected:.0f}, p={p:.1e})"
                ),
                consequence=(
                    "zero-lag synchrony between these units is underestimated; either the sorter "
                    "missed overlapping spikes, or the two units are one neuron split in two"
                ),
                fix=(
                    "inspect the pair's cross-correlogram and templates; if the templates match, "
                    "merge them, otherwise exclude this pair from synchrony and correlation analyses"
                ),
                evidence={
                    "center_count": int(n_center),
                    "expected": round(expected, 2),
                    "ratio": round(ratio, 3),
                    "p_value": p,
                    "alpha_bonferroni": alpha,
                    "distance_um": dist,
                    "scope": scope,
                },
            )
        )
    nc: list[NotChecked] = []
    if underpowered:
        nc.append(
            NotChecked(
                CODE,
                f"{underpowered} of {len(pairs)} candidate pairs had too few coincidences to test "
                f"(expected < {th.overlap_min_expected:g} near zero lag)",
                partial=True,
            )
        )
    return flags, nc
