"""DRIFT_CONFOUND: a unit's firing rate follows its spike amplitude or depth over time.

When the probe moves relative to the tissue, a neuron's spikes shrink toward the
detection threshold and the smallest ones are lost. Its measured rate then falls
although the neuron fires as before. A neuron's true rate changes do not change
its spike amplitude, so a rate that tracks amplitude (or depth) over the session
points to detection loss, not biology.

If the experiment's conditions are ordered in time (block designs, pre/post
sessions), this apparent rate change becomes an apparent condition effect, and
the flag is raised to an error.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import pearsonr, spearmanr

from ..bundle import Bundle
from ..config import Thresholds
from ..flags import Flag, NotChecked, Severity
from ..stats import windowed, windowed_completeness

CODE = "DRIFT_CONFOUND"
ACTION = "restrict"
TIER = 1
FIX = (
    "apply motion correction before sorting (SpikeInterface correct_motion, Kilosort drift "
    "correction), restrict each unit to its stable epoch (listed in the evidence; written by "
    "--export-curation), or exclude it; interleave conditions in future designs"
)


def condition_time_confound(bundle: Bundle) -> tuple[float, str | None]:
    """Largest |r| between a condition indicator and event time, and that condition."""
    ev = bundle.events
    if ev is None or ev.labels is None or len(ev) < 4:
        return 0.0, None
    values = ev.label_values
    if values.size < 2:
        return 0.0, None
    best, best_label = 0.0, None
    t = ev.times
    for v in values:
        ind = (ev.labels == v).astype(float)
        if ind.std() == 0:
            continue
        r = float(np.corrcoef(ind, t)[0, 1])
        if abs(r) > abs(best):
            best, best_label = r, str(v)
        if values.size == 2:
            break  # the two indicators are mirror images
    return best, best_label


def _trend(rates, values, th, min_change, relative):
    ok = np.isfinite(values)
    if ok.sum() < th.drift_min_windows:
        return None
    r, v = rates[ok], values[ok]
    if np.ptp(r) == 0 or np.ptp(v) == 0:
        return None
    rho, p = spearmanr(r, v)
    lo, hi = np.percentile(v, [10, 90])
    change = (hi - lo) / abs(np.median(v)) if relative else (hi - lo)
    return float(rho), float(p), float(change), change >= min_change


def _fade(t, amps, duration, window, th):
    """A unit lost (or found) as its amplitude drifts: steady amplitude trend, then rate collapses."""
    centres, rates, med = windowed(t, amps, duration, window, th.drift_min_spikes_per_window)
    ok = np.isfinite(med)
    if ok.sum() < 4 or np.ptp(med[ok]) == 0:
        return None
    rho, p = spearmanr(centres[ok], med[ok])
    head, tail = med[ok][:2].mean(), med[ok][-2:].mean()
    out = rho <= -th.drift_rho_time
    if not (out or rho >= th.drift_rho_time) or p >= th.drift_alpha:
        return None
    change = (head - tail) / head if out else (tail - head) / tail
    if change < th.drift_min_fade:
        return None
    # the rate where the amplitude was healthy, against the rate at the end it fades toward
    healthy = rates[: max(len(rates) // 3, 1)] if out else rates[-max(len(rates) // 3, 1):]
    ref = float(np.median(healthy))
    edge = float(rates[-1] if out else rates[0])
    if ref <= 0 or edge > th.drift_vanish * ref:
        return None
    good = rates >= (1 - th.drift_stable_loss) * ref * 0.8
    return {"direction": "out" if out else "in", "rho_time": float(rho), "p": float(p),
            "amp_change": float(change), "edge_rate_ratio": edge / ref, "good": good}


def run(bundle: Bundle, th: Thresholds) -> tuple[list[Flag], list[NotChecked]]:
    if not bundle.has_amplitudes and bundle.spike_depths is None:
        return [], [NotChecked(CODE, "needs per-spike amplitudes or depths (tier 1)")]
    window = th.drift_window_s
    if bundle.duration // window < th.drift_min_windows:
        window = bundle.duration / th.drift_min_windows  # shrink windows to fit short sessions
    if window < th.drift_min_window_s:
        return [], [
            NotChecked(
                CODE,
                f"session too short: {bundle.duration:g} s gives fewer than {th.drift_min_windows} "
                f"windows of at least {th.drift_min_window_s:g} s",
            )
        ]
    n_windows = int(round(bundle.duration / window))

    r_conf, conf_label = condition_time_confound(bundle)
    confounded = abs(r_conf) >= th.drift_confound_r

    flags: list[Flag] = []
    skipped = 0
    low_power = 0
    for u in bundle.unit_ids:
        u = int(u)
        t = bundle.train(u)
        if t.size < th.min_spikes:
            skipped += 1
            continue
        evidence: dict = {}
        stable_source = None  # (window edges, good-window mask) used to find the stable epoch
        reasons: list[str] = []
        amps = bundle.unit_amplitudes(u)
        if amps is not None:
            _, rates, med = windowed(t, amps, bundle.duration, window,
                                     th.drift_min_spikes_per_window)
            if np.isfinite(med).sum() >= th.drift_min_windows:
                good = med >= (1 - th.drift_stable_amp_drop) * np.nanmax(med)
                stable_source = (window, good)
            res = _trend(rates, med, th, th.drift_min_amp_change, relative=True)
            if res is not None:
                rho, p, change, big = res
                evidence["amplitude"] = {"rho": round(rho, 3), "p": p, "rel_change": round(change, 3)}
                if rho >= th.drift_rho and p < th.drift_alpha and big:
                    reasons.append(f"rate follows amplitude (rho={rho:.2f}, amplitude range {change:.0%})")
            # detection loss: does the rate follow the share of spikes still above threshold?
            n_win = min(n_windows, t.size // th.drift_completeness_spikes)
            if n_win < th.drift_min_windows:
                low_power += 1
            else:
                rates_c, comp = windowed_completeness(t, amps, bundle.duration, n_win)
                if np.isfinite(comp).sum() >= th.drift_min_windows:
                    # detection completeness is the direct measure: prefer it to amplitude
                    stable_source = (bundle.duration / n_win, comp >= 1 - th.drift_stable_loss)
                ok = np.isfinite(comp)
                if ok.sum() >= th.drift_min_windows and np.ptp(comp[ok]) > 0 and np.ptp(rates_c[ok]) > 0:
                    r, p = pearsonr(rates_c[ok], comp[ok])
                    lost = float(1 - comp[ok].min())
                    span = float(np.ptp(comp[ok]))
                    evidence["completeness"] = {
                        "r": round(float(r), 3), "p": float(p), "max_lost": round(lost, 3),
                        "range": round(span, 3), "windows": int(ok.sum()),
                    }
                    # a detection loss must also be big enough to explain the rate drop
                    # (the estimate saturates at 50 %, so a saturated estimate always qualifies)
                    rr = rates_c[ok]
                    drop = float(1.0 - np.percentile(rr, 10) / max(np.percentile(rr, 90), 1e-12))
                    consistent = lost >= 0.45 or drop <= lost + th.drift_loss_slack
                    evidence["completeness"]["rate_drop"] = round(drop, 3)
                    if (r >= th.drift_rho and p < th.drift_alpha and span >= th.drift_min_completeness_change
                            and consistent):
                        reasons.append(
                            f"rate follows detection loss (r={r:.2f}; up to {lost:.0%} of spikes "
                            f"below threshold in the worst window)"
                        )
            # fade-out / fade-in: a template-matching sorter keeps a fading unit's spikes whole,
            # then loses the unit at once; its amplitude walks steadily one way and it vanishes
            fade = _fade(t, amps, bundle.duration, window, th)
            if fade is not None:
                evidence["fade"] = {k: v for k, v in fade.items() if k != "good"}
                reasons.append(
                    f"amplitude {'fell' if fade['direction'] == 'out' else 'rose'} steadily "
                    f"({fade['amp_change']:.0%}, rho={fade['rho_time']:.2f} over time) and the unit "
                    f"{'vanished' if fade['direction'] == 'out' else 'appeared'} "
                    f"({'last' if fade['direction'] == 'out' else 'first'} window at "
                    f"{fade['edge_rate_ratio']:.0%} of its usual rate)"
                )
                stable_source = (window, fade["good"])
        depths = bundle.unit_spike_depths(u)
        if depths is not None:
            _, rates, med = windowed(t, depths, bundle.duration, window,
                                     th.drift_min_spikes_per_window)
            res = _trend(rates, med, th, th.drift_min_depth_change_um, relative=False)
            if res is not None:
                rho, p, change, big = res
                evidence["depth"] = {"rho": round(rho, 3), "p": p, "range_um": round(change, 1)}
                if abs(rho) >= th.drift_rho and p < th.drift_alpha and big:
                    reasons.append(f"rate follows depth (rho={rho:.2f}, moved {change:.0f} µm)")
        if not reasons:
            continue
        if stable_source is not None:
            w, good = stable_source
            epochs = [(i * w, (i + 1) * w) for i in np.flatnonzero(good)]
            from ..bundle import _normalise_epochs

            ep = _normalise_epochs(epochs, bundle.duration)
            frac = float(np.sum(ep[:, 1] - ep[:, 0]) / bundle.duration) if ep.size else 0.0
            evidence["stable_fraction"] = round(frac, 3)
            if frac >= th.drift_min_stable:
                evidence["stable_epochs"] = [[round(float(a), 3), round(float(b), 3)] for a, b in ep]
        sev = Severity.ERROR if confounded else Severity.WARNING
        consequence = (
            "the unit's rate changes over the session because spikes are lost below the "
            "detection threshold, not because the neuron changed"
        )
        if confounded:
            consequence += (
                f"; conditions are ordered in time (r={r_conf:+.2f} for condition '{conf_label}'), "
                "so this loss shows up as a condition effect"
            )
            evidence["condition_time_r"] = round(r_conf, 3)
        flags.append(
            Flag(
                code=CODE,
                severity=sev,
                units=(u,),
                message=f"unit {u}: " + "; ".join(reasons),
                consequence=consequence,
                fix=(
                    "apply motion correction before sorting (SpikeInterface correct_motion, Kilosort "
                    "drift correction), restrict the unit to the epoch where its amplitude is stable, "
                    "or exclude it; interleave conditions in future designs"
                ),
                evidence=evidence,
            )
        )
    nc = []
    if skipped:
        nc.append(NotChecked(CODE, f"{skipped} unit(s) with fewer than {th.min_spikes} spikes skipped",
                             partial=True))
    if low_power:
        nc.append(NotChecked(
            CODE,
            f"{low_power} unit(s) had too few spikes for the detection-loss test "
            f"(< {th.drift_min_windows} x {th.drift_completeness_spikes}); only amplitude/depth "
            "trends were tested",
            partial=True,
        ))
    return flags, nc
