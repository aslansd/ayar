"""SPLIT_UNIT: one neuron reported as two units.

Two signatures, either of which is enough:

refractory
    The pair almost never fires within the refractory period of each other
    (±1.5 ms), not just at zero lag, and the merged spike train has no more
    refractory violations than a single neuron would. Two distinct neurons
    have no reason to respect each other's refractory period.
handoff
    One unit fades out as a nearby unit with similar amplitude and rate fades
    in: the sorter lost track of a drifting neuron and started a new unit for it.

A split neuron counted as two inflates N, and a handoff looks like a neuron
that switches off while another switches on (fake remapping or plasticity).
"""

from __future__ import annotations

import numpy as np
from scipy.stats import pearsonr

from ..bundle import Bundle
from ..config import Thresholds
from ..flags import Flag, NotChecked, Severity
from ..metrics import REFRACTORY_S, hill_contamination, isi_violations
from ..stats import count_strictly_within, count_within, poisson_lower_p
from ._pairs import candidate_pairs

CODE = "SPLIT_UNIT"
TIER = 0
ACTION = "merge"
FIX = (
    "merge each pair (Phy merge, SpikeInterface apply_curation with a merge) after checking "
    "that the templates match, then re-run the analysis"
)


def refractory_stats(bundle: Bundle, a: int, b: int, th: Thresholds) -> dict | None:
    """Cross-refractory coincidences of a pair against the 2-10 ms flank expectation.

    Coincidences within ±``dup_window_ms`` are set aside as double detections of the
    same spike (common when a sorter splits a neuron) rather than counted as
    refractory violations. The outer band (1.0-1.5 ms) is tested separately: a
    sorter that discards near-simultaneous spikes empties the centre of the
    correlogram, but only a shared refractory period also empties its edge.
    """
    ta, tb = bundle.train(a), bundle.train(b)
    tr = REFRACTORY_S
    dw = th.dup_window_ms / 1000.0
    edge = th.split_outer_ms / 1000.0
    f1, f2 = th.overlap_flank_lo_ms / 1000.0, th.overlap_flank_hi_ms / 1000.0
    n_flank = count_within(ta, tb, f2) - count_strictly_within(ta, tb, f1)
    per_s = n_flank / (2 * (f2 - f1))  # expected coincidences per second of lag
    expected = per_s * 2 * (tr - dw)
    if expected < th.overlap_min_expected:
        return None
    n_ref = count_strictly_within(ta, tb, tr) - count_within(ta, tb, dw)
    n_outer = count_strictly_within(ta, tb, tr) - count_strictly_within(ta, tb, edge)
    exp_outer = per_s * 2 * (tr - edge)
    n_double = count_within(ta, tb, dw)
    # merged train with double detections counted once
    hi = np.searchsorted(ta, tb + dw, side="right")
    lo = np.searchsorted(ta, tb - dw, side="left")
    merged = np.sort(np.concatenate([ta, tb[hi <= lo]]))
    c_merged = hill_contamination(isi_violations(merged), merged.size, bundle.duration)
    return {
        "n_refractory": int(n_ref),
        "expected": float(expected),
        "ratio": float(n_ref / expected),
        "p": poisson_lower_p(n_ref, expected),
        "outer_ratio": float(n_outer / exp_outer) if exp_outer > 0 else float("nan"),
        "double_detections": int(n_double),
        "merged_contamination": float(c_merged),
    }


def looks_refractory_split(stats: dict | None, th: Thresholds, alpha: float) -> bool:
    return (
        stats is not None
        and stats["ratio"] <= th.split_ratio
        and stats["outer_ratio"] <= th.split_outer_ratio
        and stats["p"] < alpha
        and stats["merged_contamination"] <= th.split_max_merged_contamination
    )


def _active_blocks(active: np.ndarray) -> int:
    return int(np.sum(np.diff(np.concatenate([[0], active.astype(int)])) == 1))


def handoff_stats(bundle: Bundle, a: int, b: int, th: Thresholds) -> dict | None:
    n_win = int(min(th.split_handoff_windows, bundle.duration // th.split_min_window_s))
    if n_win < 6:
        return None
    w = bundle.duration / n_win
    ra = np.bincount(np.clip((bundle.train(a) // w).astype(int), 0, n_win - 1), minlength=n_win) / w
    rb = np.bincount(np.clip((bundle.train(b) // w).astype(int), 0, n_win - 1), minlength=n_win) / w
    if ra.max() == 0 or rb.max() == 0:
        return None
    act_a = ra >= th.split_active_fraction * ra.max()
    act_b = rb >= th.split_active_fraction * rb.max()
    both = int(np.sum(act_a & act_b))
    n_a, n_b = int(act_a.sum()), int(act_b.sum())
    if min(n_a, n_b) < 2 or max(n_a, n_b) > n_win - 2:
        return None
    if np.ptp(ra) == 0 or np.ptp(rb) == 0:
        return None
    r, p = pearsonr(ra, rb)
    rate_ratio = ra[act_a].mean() / rb[act_b].mean()
    out = {
        "r": float(r), "p": float(p), "windows_both_active": both,
        "windows_active": [n_a, n_b], "blocks": [_active_blocks(act_a), _active_blocks(act_b)],
        "rate_ratio": float(rate_ratio), "window_s": round(w, 1),
    }
    aa, ab = bundle.unit_amplitudes(a), bundle.unit_amplitudes(b)
    if aa is not None and ab is not None and aa.size >= 20 and ab.size >= 20:
        first_a = bundle.train(a).mean() < bundle.train(b).mean()
        early, late = (aa, ab) if first_a else (ab, aa)
        k_e, k_l = max(early.size // 5, 10), max(late.size // 5, 10)
        out["amplitude_ratio"] = float(np.median(early[-k_e:]) / np.median(late[:k_l]))
    return out


def looks_handoff(s: dict | None, th: Thresholds) -> bool:
    if s is None:
        return False
    ok = (
        s["r"] <= -th.split_handoff_r
        and s["p"] < th.drift_alpha
        and s["windows_both_active"] <= max(1, int(0.3 * min(s["windows_active"])))
        and max(s["blocks"]) <= 2
        and 1 / th.split_max_ratio <= s["rate_ratio"] <= th.split_max_ratio
    )
    if ok and "amplitude_ratio" in s:
        ok = 1 / th.split_max_amp_ratio <= s["amplitude_ratio"] <= th.split_max_amp_ratio
    return ok


def run(bundle: Bundle, th: Thresholds) -> tuple[list[Flag], list[NotChecked]]:
    units = [int(u) for u in bundle.unit_ids if len(bundle.spike_indices(u)) >= th.min_spikes]
    pairs, scope = candidate_pairs(bundle, units, th.split_max_distance_um, th.max_pairs)
    if pairs is None:
        return [], [NotChecked(CODE, scope)]
    alpha = th.overlap_alpha / max(len(pairs), 1)
    candidates = []
    underpowered = 0
    for a, b in pairs:
        ref = refractory_stats(bundle, a, b, th)
        if ref is None:
            underpowered += 1
        is_ref = looks_refractory_split(ref, th, alpha)
        hand = handoff_stats(bundle, a, b, th)
        is_hand = looks_handoff(hand, th)
        if is_ref or is_hand:
            candidates.append((a, b, ref, is_ref, hand, is_hand))

    # a unit can be handed off to only one other unit: keep the best-matching pair
    def score(c):
        a, b, ref, is_ref, hand, is_hand = c
        if is_ref:
            return -1.0
        return abs(np.log(hand.get("amplitude_ratio", 1.0))) + (1 + hand["r"])

    taken: set[int] = set()
    chosen = []
    for c in sorted(candidates, key=score):
        a, b, ref, is_ref, hand, is_hand = c
        if not is_ref and (a in taken or b in taken):
            continue
        taken.update((a, b))
        chosen.append(c)

    flags: list[Flag] = []
    for a, b, ref, is_ref, hand, is_hand in chosen:
        reasons, evidence = [], {"scope": scope}
        if is_ref:
            reasons.append(
                f"they almost never fire within ±1.5 ms of each other ({ref['n_refractory']} vs "
                f"{ref['expected']:.0f} expected"
                + (f", plus {ref['double_detections']} double detections" if ref["double_detections"] else "")
                + f") and the merged train has {ref['merged_contamination']:.0%} refractory contamination"
            )
            evidence["refractory"] = ref
        if is_hand:
            reasons.append(
                f"one fades out as the other fades in (rate r={hand['r']:.2f}, overlapping in "
                f"{hand['windows_both_active']} of {int(bundle.duration // hand['window_s'])} windows)"
            )
            evidence["handoff"] = hand
        mode = "+".join(m for m, on in (("refractory", is_ref), ("handoff", is_hand)) if on)
        evidence["mode"] = mode
        keep, absorb = (a, b) if bundle.train(a).size >= bundle.train(b).size else (b, a)
        flags.append(
            Flag(
                code=CODE,
                severity=Severity.ERROR if is_ref else Severity.WARNING,
                units=(keep, absorb),
                message=f"units {keep} and {absorb} look like one neuron: " + "; ".join(reasons),
                consequence=(
                    "one neuron is counted twice; a handoff also looks like one neuron switching "
                    "off while another switches on (fake remapping, plasticity or cell loss)"
                ),
                fix=f"merge unit {absorb} into unit {keep} if their templates match, and re-run",
                evidence=evidence,
            )
        )
    nc: list[NotChecked] = []
    tiny = sum(1 for u in bundle.unit_ids if 0 < len(bundle.spike_indices(u)) < th.min_spikes)
    if tiny:
        nc.append(NotChecked(
            CODE,
            f"{tiny} unit(s) with fewer than {th.min_spikes} spikes were not tested; small units are "
            "often fragments of a neuron that another unit already holds",
            partial=True,
        ))
    if underpowered:
        nc.append(NotChecked(
            CODE,
            f"{underpowered} of {len(pairs)} nearby pairs had too few spikes for the refractory test "
            f"(expected < {th.overlap_min_expected:g} within ±1.5 ms); small fragments of a split neuron "
            "can hide here, and longer recordings make them testable",
            partial=True,
        ))
    return flags, nc
