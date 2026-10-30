"""CONTAMINATION: a unit that holds spikes from more than one neuron.

A single neuron cannot fire twice within its refractory period, so refractory
violations measure how many of a unit's spikes come from other neurons
(Hill et al. 2011). ayar also looks for the *source*: a neighbouring unit whose
spikes respect a shared refractory period with this one, i.e. whose spikes
were partly misassigned here.

A contaminated unit inherits part of its neighbour's tuning and correlations.
"""

from __future__ import annotations

from scipy.stats import poisson

from ..bundle import Bundle
from ..config import Thresholds
from ..flags import Flag, NotChecked, Severity
from ..metrics import REFRACTORY_S, hill_contamination, isi_violations
from ..stats import count_strictly_within, count_within
from ._pairs import candidate_pairs

CODE = "CONTAMINATION"
TIER = 0
ACTION = "remove"
FIX = (
    "re-curate the unit (split it in Phy, or exclude it); if a source unit is named, check "
    "whether the two should be re-sorted together"
)


def _likely_source(bundle: Bundle, u: int, neighbours: list[int], th: Thresholds) -> tuple[int, float] | None:
    tu = bundle.train(u)
    f1, f2 = th.overlap_flank_lo_ms / 1000.0, th.overlap_flank_hi_ms / 1000.0
    best = None
    for v in neighbours:
        tv = bundle.train(v)
        n_flank = count_within(tu, tv, f2) - count_strictly_within(tu, tv, f1)
        expected = n_flank * REFRACTORY_S / (f2 - f1)
        if expected < th.overlap_min_expected:
            continue
        n = count_strictly_within(tu, tv, REFRACTORY_S)
        if poisson.cdf(n, expected) < th.drift_alpha:
            ratio = n / expected
            if best is None or ratio < best[1]:
                best = (v, ratio)
    return best


def run(bundle: Bundle, th: Thresholds) -> tuple[list[Flag], list[NotChecked]]:
    units = [int(u) for u in bundle.unit_ids if len(bundle.spike_indices(u)) >= th.min_spikes]
    T = bundle.duration
    flags: list[Flag] = []
    neighbours: dict[int, list[int]] = {}
    pairs, _ = candidate_pairs(bundle, units, th.overlap_max_distance_um, th.max_pairs)
    if pairs is not None:
        for a, b in pairs:
            neighbours.setdefault(a, []).append(b)
            neighbours.setdefault(b, []).append(a)

    for u in units:
        t = bundle.train(u)
        nv = isi_violations(t)
        if nv < th.contam_min_violations:
            continue
        c = hill_contamination(nv, t.size, T)
        if c < th.contam_warn:
            continue
        # is the violation count beyond what a barely contaminated unit would show?
        c0 = th.contam_warn / 2
        mu0 = 2 * REFRACTORY_S * t.size ** 2 * c0 * (1 - c0) / T
        p = float(poisson.sf(nv - 1, mu0))
        if p >= th.drift_alpha:
            continue
        src = _likely_source(bundle, u, neighbours.get(u, []), th) if pairs is not None else None
        msg = (
            f"unit {u}: {nv} refractory violations (<{REFRACTORY_S * 1e3:g} ms) imply "
            f"{c:.0%}{'+' if c >= 0.5 else ''} of its spikes come from other neurons"
        )
        evidence = {"isi_violations": nv, "contamination": round(c, 4), "p": p, "n_spikes": int(t.size)}
        if src is not None:
            msg += f"; likely source: unit {src[0]} (shared refractory dip, ratio {src[1]:.2f})"
            evidence["likely_source"] = int(src[0])
            evidence["source_ratio"] = round(src[1], 3)
        flags.append(
            Flag(
                code=CODE,
                severity=Severity.ERROR if c >= th.contam_error else Severity.WARNING,
                units=(u,),
                message=msg,
                consequence=(
                    "the unit mixes several neurons, so its tuning, rate changes and correlations "
                    "are partly another neuron's"
                ),
                fix=FIX,
                evidence=evidence,
            )
        )
    return flags, []
