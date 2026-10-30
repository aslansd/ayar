"""DUPLICATE_UNIT: one neuron reported as two units.

Template-matching sorters sometimes keep two templates for the same neuron and
assign the same spikes (within a fraction of a millisecond) to both. Distinct
neurons almost never share a large fraction of their spikes at sub-millisecond
lags, even when they are strongly synchronised by common input.
"""

from __future__ import annotations

import math

from ..bundle import Bundle
from ..config import Thresholds
from ..flags import Flag, NotChecked, Severity
from ..stats import has_partner
from ._pairs import candidate_pairs

CODE = "DUPLICATE_UNIT"
ACTION = "merge"
TIER = 0
FIX = "merge each pair (Phy merge, or SpikeInterface remove_redundant_units) and re-run the analysis"


def run(bundle: Bundle, th: Thresholds) -> tuple[list[Flag], list[NotChecked]]:
    units = [int(u) for u in bundle.unit_ids if len(bundle.spike_indices(u)) >= th.min_spikes]
    pairs, scope = candidate_pairs(bundle, units, th.dup_max_distance_um, th.max_pairs)
    if pairs is None:
        return [], [NotChecked(CODE, scope)]
    w = th.dup_window_ms / 1000.0
    T = bundle.duration
    flags: list[Flag] = []
    for a, b in pairs:
        ta, tb = bundle.train(a), bundle.train(b)
        if ta.size <= tb.size:
            small, big, ts, tbig = a, b, ta, tb
        else:
            small, big, ts, tbig = b, a, tb, ta
        hits = int(has_partner(ts, tbig, w).sum())
        frac = hits / ts.size
        if frac < th.dup_fraction_warn:
            continue
        expected = ts.size * (1.0 - math.exp(-(tbig.size / T) * 2 * w))
        ratio = hits / max(expected, 1e-12)
        if ratio < th.dup_min_ratio:
            continue
        sev = Severity.ERROR if frac >= th.dup_fraction_error else Severity.WARNING
        flags.append(
            Flag(
                code=CODE,
                severity=sev,
                units=(big, small),
                message=(
                    f"{frac:.0%} of unit {small}'s spikes have a unit {big} spike within "
                    f"±{th.dup_window_ms:g} ms ({ratio:.0f}x chance): likely one neuron counted twice"
                ),
                consequence=(
                    "inflates the number of neurons, doubles this neuron's weight in population "
                    "averages and decoders, and creates a fake zero-lag correlation"
                ),
                fix=(
                    f"merge unit {small} into unit {big} (Phy merge, or SpikeInterface "
                    "remove_redundant_units) and re-run the analysis"
                ),
                evidence={
                    "shared_fraction": round(frac, 4),
                    "ratio_to_chance": round(ratio, 2),
                    "window_ms": th.dup_window_ms,
                    "n_spikes": {str(big): int(tbig.size), str(small): int(ts.size)},
                    "scope": scope,
                },
            )
        )
    return flags, []
