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
from ..stats import has_partner, peak_lag
from ._pairs import candidate_pairs, pair_counts

CODE = "DUPLICATE_UNIT"
ACTION = "merge"
TIER = 0
FIX = "merge each pair (Phy merge, or SpikeInterface remove_redundant_units) and re-run the analysis"


def run(bundle: Bundle, th: Thresholds) -> tuple[list[Flag], list[NotChecked]]:
    units = [int(u) for u in bundle.unit_ids if len(bundle.spike_indices(u)) >= th.min_spikes]
    pairs, scope = candidate_pairs(bundle, units, th.dup_max_distance_um, th.max_pairs, th.max_spike_pairs)
    if pairs is None:
        return [], [NotChecked(CODE, scope)]
    w = th.dup_window_ms / 1000.0
    max_lag = th.dup_max_lag_ms / 1000.0
    T = bundle.duration
    n_spk = {u: len(bundle.spike_indices(u)) for u in units}
    # each pair from its smaller unit's side, as below
    ordered = [(a, b) if n_spk[a] <= n_spk[b] else (b, a) for a, b in pairs]
    counts = pair_counts(bundle, th, ordered)
    n_lag, n_w = counts[(True, max_lag)], counts[(True, w)]
    flags: list[Flag] = []
    for i, (small, big) in enumerate(ordered):
        # A spike with a partner within ±w is at least one coincidence within ±w, and the
        # shifted search below only runs when coincidences within ±max_lag reach the warning
        # share: pairs below both cannot reach it and are skipped without touching their trains.
        if max(n_lag[i], n_w[i]) < th.dup_fraction_warn * n_spk[small]:
            continue
        ts, tbig = bundle.train(small), bundle.train(big)
        # duplicates may be time-shifted (two templates of one neuron aligned differently):
        # find where coincidences pile up within ±dup_max_lag, then count around that lag
        lag = 0.0
        if n_lag[i] >= th.dup_fraction_warn * ts.size:
            lag, _ = peak_lag(ts, tbig, max_lag)
        hits = int(has_partner(ts + lag, tbig, w).sum())
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
                    f"±{th.dup_window_ms:g} ms" + (f" of a {lag * 1e3:+.2f} ms offset" if abs(lag) > w else "")
                    + f" ({ratio:.0f}x chance): "
                    + ("likely one neuron counted twice" if sev is Severity.ERROR else
                       "these spikes are counted twice; unit "
                       f"{small} may be a duplicate, or a cluster of collision events shared with other units")
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
                    "lag_ms": round(lag * 1e3, 3),
                    "n_spikes": {str(big): int(tbig.size), str(small): int(ts.size)},
                    "scope": scope,
                },
            )
        )
    return flags, []
