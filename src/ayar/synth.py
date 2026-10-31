"""Synthetic sorted sessions with planted sorting artifacts and known ground truth.

Every artifact ayar detects has a generator here, together with *controls*:
real biology that looks superficially similar and must not be flagged.

Planted artifacts
    DUPLICATE_UNIT   a copy of a (task-responsive) unit sharing 80 % of its spikes
    SPLIT_UNIT       one neuron handed from one unit to a neighbour mid-session
                     (handoff), or divided between two units by amplitude (refractory)
    OVERLAP_HOLE     a nearby, high-rate pair where the sorter dropped 85 % of
                     the second unit's spikes that overlapped the first's
    CONTAMINATION    a unit whose spikes are 30 % misassigned from a responsive neighbour
    DRIFT_CONFOUND   units whose amplitude decays toward the detection threshold,
                     so late spikes are lost and the rate falls

Controls (must stay unflagged)
    synchrony        nearby pairs driven by shared input (CCG peak, ±2 ms jitter)
    rate_change      units whose true rate ramps over the session at constant amplitude
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .bundle import Bundle, Events


@dataclass
class SynthConfig:
    n_units: int = 40
    duration: float = 600.0
    n_duplicates: int = 2
    n_holes: int = 2
    n_drifting: int = 3
    n_sync_controls: int = 2
    n_rate_controls: int = 2
    n_splits_handoff: int = 2
    n_splits_refractory: int = 1
    n_contaminated: int = 2
    n_responsive: int = 10
    response_gain_hz: float = 10.0
    response_window: float = 0.5
    n_trials: int = 200
    design: str = "block"  # "block" (conditions ordered in time) or "interleaved"
    threshold: float = 50.0
    probe_length_um: float = 3840.0

    @classmethod
    def clean(cls, **kwargs) -> "SynthConfig":
        """A session with no planted artifacts and no controls (override any field)."""
        zero = dict(n_duplicates=0, n_holes=0, n_drifting=0, n_sync_controls=0, n_rate_controls=0,
                    n_splits_handoff=0, n_splits_refractory=0, n_contaminated=0)
        zero.update(kwargs)
        return cls(**zero)


def _poisson_refractory(rate: float, t0: float, t1: float, rng, refractory: float = 0.002) -> np.ndarray:
    if rate <= 0 or t1 <= t0:
        return np.zeros(0)
    mean_isi = 1.0 / rate
    if mean_isi <= refractory:
        raise ValueError(f"rate {rate} Hz is too high for a {refractory * 1e3:g} ms refractory period")
    lam = 1.0 / (mean_isi - refractory)
    n = int((t1 - t0) * rate * 1.2 + 50)
    out = []
    t = t0 + rng.exponential(1 / lam)
    while t < t1:
        isi = refractory + rng.exponential(1 / lam, size=n)
        ts = t + np.concatenate([[0.0], np.cumsum(isi)])
        out.append(ts[ts < t1])
        t = ts[-1] + refractory + rng.exponential(1 / lam)
        if ts[-1] >= t1:
            break
    return np.concatenate(out) if out else np.zeros(0)


def _enforce_refractory(t: np.ndarray, refractory: float = 0.0015) -> np.ndarray:
    t = np.sort(t)
    if t.size < 2:
        return t
    keep = np.ones(t.size, dtype=bool)
    last = t[0]
    for i in range(1, t.size):
        if t[i] - last < refractory:
            keep[i] = False
        else:
            last = t[i]
    return t[keep]


def make_session(seed: int = 0, config: SynthConfig | None = None) -> Bundle:
    """Generate one sorted session. Ground truth is in ``bundle.meta['truth']``."""
    cfg = config or SynthConfig()
    rng = np.random.default_rng(seed)
    T = cfg.duration
    thr = cfg.threshold

    # ---- trials --------------------------------------------------------
    spacing = (T - 10.0) / cfg.n_trials
    trial_t = 5.0 + spacing * np.arange(cfg.n_trials) + rng.uniform(0, 0.3 * spacing, cfg.n_trials)
    if cfg.design == "block":
        labels = (np.arange(cfg.n_trials) >= cfg.n_trials // 2).astype(int)
    elif cfg.design == "interleaved":
        labels = rng.permutation(np.arange(cfg.n_trials) % 2)
    else:
        raise ValueError("design must be 'block' or 'interleaved'")

    units: list[dict] = []

    def add(times, depth, amp0, role, amp_fn=None, depth_fn=None):
        units.append(dict(id=len(units), times=np.sort(times), depth=depth, amp0=amp0,
                          role=role, amp_fn=amp_fn, depth_fn=depth_fn))
        return units[-1]

    # ---- plain units ---------------------------------------------------
    for _ in range(cfg.n_units):
        rate = float(np.clip(rng.lognormal(np.log(6.0), 0.6), 1.0, 30.0))
        add(_poisson_refractory(rate, 0, T, rng), rng.uniform(0, cfg.probe_length_um),
            rng.uniform(80, 250), "plain")

    plain_ids = list(range(cfg.n_units))
    rng.shuffle(plain_ids)
    need = cfg.n_responsive + cfg.n_drifting + cfg.n_rate_controls
    if need > cfg.n_units:
        raise ValueError(f"n_units={cfg.n_units} is too small for {need} special units")
    responsive = plain_ids[: cfg.n_responsive]
    drifting = plain_ids[cfg.n_responsive: cfg.n_responsive + cfg.n_drifting]
    rate_ctrl = plain_ids[cfg.n_responsive + cfg.n_drifting: need]

    # responsive units fire extra spikes after condition-1 trials (a real effect)
    for uid in responsive:
        u = units[uid]
        extra = []
        for t0 in trial_t[labels == 1]:
            k = rng.poisson(cfg.response_gain_hz * cfg.response_window)
            extra.append(t0 + rng.uniform(0, cfg.response_window, k))
        u["times"] = _enforce_refractory(np.concatenate([u["times"], *extra]))
        u["role"] = "responsive"

    # drifting units: amplitude decays toward the threshold; sub-threshold spikes are lost
    for uid in drifting:
        u = units[uid]
        u["amp0"] = rng.uniform(70, 110)
        k = 1 - 0.95 * thr / u["amp0"]
        u["amp_fn"] = (lambda a0, kk: (lambda t: a0 * (1 - kk * t / T)))(u["amp0"], k)
        u["depth_fn"] = (lambda d0: (lambda t: d0 + 40.0 * t / T))(u["depth"])
        u["role"] = "drifting"

    # rate controls: true rate ramps 0.4x -> 1.6x, amplitude constant
    for uid in rate_ctrl:
        u = units[uid]
        r0 = max(len(u["times"]) / T, 3.0)
        cand = _poisson_refractory(1.6 * r0, 0, T, rng)
        keep = rng.random(cand.size) < (0.4 + 1.2 * cand / T) / 1.6
        u["times"] = cand[keep]
        u["role"] = "rate_control"

    truth: list[dict] = []
    controls: list[dict] = []

    # ---- duplicates (of responsive units, so they also bias the finding) ----
    for i in range(cfg.n_duplicates):
        src = units[responsive[i % len(responsive)]]
        shared = src["times"][rng.random(src["times"].size) < 0.8]
        shared = shared + rng.normal(0, 5e-5, shared.size)
        own = _poisson_refractory(0.3, 0, T, rng)
        times = _enforce_refractory(np.clip(np.concatenate([shared, own]), 0, T))
        dup = add(times, src["depth"] + 15.0, src["amp0"] * 0.7, "duplicate")
        truth.append({"code": "DUPLICATE_UNIT", "units": [src["id"], dup["id"]]})

    # ---- overlap holes ---------------------------------------------------
    for _ in range(cfg.n_holes):
        d = rng.uniform(100, cfg.probe_length_um - 100)
        a = add(_poisson_refractory(rng.uniform(15, 25), 0, T, rng), d, rng.uniform(120, 250), "hole")
        tb = _poisson_refractory(rng.uniform(15, 25), 0, T, rng)
        ta = a["times"]
        hi = np.searchsorted(ta, tb + 5e-4, side="right")
        lo = np.searchsorted(ta, tb - 5e-4, side="left")
        overlapped = hi > lo
        lost = overlapped & (rng.random(tb.size) < 0.85)
        b = add(tb[~lost], d + 20.0, rng.uniform(80, 200), "hole")
        truth.append({"code": "OVERLAP_HOLE", "units": [a["id"], b["id"]]})

    for uid in drifting:
        truth.append({"code": "DRIFT_CONFOUND", "units": [uid]})

    # ---- split units: one neuron handed from unit A to unit B as the probe drifts ----
    for _ in range(cfg.n_splits_handoff):
        d = rng.uniform(100, cfg.probe_length_um - 100)
        t = _poisson_refractory(rng.uniform(8, 15), 0, T, rng)
        t_switch = rng.uniform(0.35, 0.65) * T
        p_b = np.clip((t - t_switch) / 60.0 + 0.5, 0, 1)
        to_b = rng.random(t.size) < p_b
        a0 = rng.uniform(100, 200)
        a = add(t[~to_b], d, a0, "split_handoff")
        b = add(t[to_b], d + 15.0, a0 * 0.95, "split_handoff")
        truth.append({"code": "SPLIT_UNIT", "units": [a["id"], b["id"]], "mode": "handoff"})

    # ---- split units: one neuron's spikes divided between two units by amplitude ----
    for _ in range(cfg.n_splits_refractory):
        d = rng.uniform(100, cfg.probe_length_um - 100)
        t = _poisson_refractory(rng.uniform(15, 25), 0, T, rng)
        to_b = rng.random(t.size) < 0.5
        a0 = rng.uniform(120, 220)
        a = add(t[~to_b], d, a0 * 1.1, "split_refractory")
        b = add(t[to_b], d + 10.0, a0 * 0.9, "split_refractory")
        truth.append({"code": "SPLIT_UNIT", "units": [a["id"], b["id"]], "mode": "refractory"})

    # ---- contamination: a unit that also holds spikes misassigned from a responsive neighbour ----
    for i in range(cfg.n_contaminated):
        src = units[responsive[(cfg.n_duplicates + i) % len(responsive)]]
        own = _poisson_refractory(rng.uniform(3, 8), 0, T, rng)
        frac = 0.3  # share of the contaminated unit's spikes that belong to the source
        n_take = min(int(own.size * frac / (1 - frac)), src["times"].size // 2)
        take = np.zeros(src["times"].size, dtype=bool)
        take[rng.choice(src["times"].size, n_take, replace=False)] = True
        stolen = src["times"][take]
        src["times"] = src["times"][~take]
        c = add(np.sort(np.concatenate([own, stolen])), src["depth"] + 20.0, rng.uniform(90, 180),
                "contaminated")
        truth.append({"code": "CONTAMINATION", "units": [c["id"]], "source": src["id"]})

    # ---- synchrony controls ----------------------------------------------
    for _ in range(cfg.n_sync_controls):
        d = rng.uniform(100, cfg.probe_length_um - 100)
        common = _poisson_refractory(2.0, 0, T, rng)
        pair = []
        for off in (0.0, 25.0):
            own = _poisson_refractory(5.0, 0, T, rng)
            jit = common + rng.normal(0, 0.002, common.size)
            t = _enforce_refractory(np.clip(np.concatenate([own, jit]), 0, T))
            pair.append(add(t, d + off, rng.uniform(100, 200), "sync_control")["id"])
        controls.append({"kind": "synchrony", "units": pair})
    for uid in rate_ctrl:
        controls.append({"kind": "rate_change", "units": [uid]})

    # ---- amplitudes, depths, detection threshold ---------------------------
    all_t, all_c, all_a, all_d = [], [], [], []
    for u in units:
        t = u["times"]
        mean_amp = u["amp_fn"](t) if u["amp_fn"] else np.full(t.size, u["amp0"])
        amp = mean_amp * (1 + 0.12 * rng.standard_normal(t.size))
        det = amp >= thr
        dep = (u["depth_fn"](t) if u["depth_fn"] else np.full(t.size, u["depth"])) + rng.normal(0, 5, t.size)
        all_t.append(t[det]); all_a.append(amp[det]); all_d.append(dep[det])
        all_c.append(np.full(int(det.sum()), u["id"]))

    return Bundle(
        np.concatenate(all_t),
        np.concatenate(all_c),
        duration=T,
        amplitudes=np.concatenate(all_a),
        spike_depths=np.concatenate(all_d),
        unit_ids=np.arange(len(units)),
        events=Events(trial_t, labels),
        meta={
            "source": "ayar.synth",
            "seed": seed,
            "config": asdict(cfg),
            "truth": truth,
            "controls": controls,
            "roles": {str(u["id"]): u["role"] for u in units},
        },
    )


def sorter_variants(bundle: Bundle, n: int = 2, seed: int = 0) -> list[Bundle]:
    """Re-sortings of a synthetic session, the way a different spike sorter might produce them.

    Variants alternate between two styles:

    ``conservative``
        drops most low-amplitude units, misses 8 % of spikes, and merges the
        session's planted duplicates and split units (a different sorter would
        not have made those mistakes)
    ``liberal``
        keeps every unit, splits two high-rate units in two, and adds three
        low-amplitude noise units

    Every variant jitters spike times by ~0.05 ms and renumbers its units, so units
    must be matched before sortings can be compared. ``meta['origin']`` maps each
    variant unit to the original unit(s) it came from.
    """
    out = []
    truth = bundle.meta.get("truth", [])
    for k in range(n):
        rng = np.random.default_rng(seed * 1000 + k)
        style = "conservative" if k % 2 == 0 else "liberal"
        times = bundle.spike_times.copy()
        clus = bundle.spike_clusters.copy()
        amps = None if bundle.amplitudes is None else bundle.amplitudes.copy()
        deps = None if bundle.spike_depths is None else bundle.spike_depths.copy()
        origin: dict[int, list[int]] = {int(u): [int(u)] for u in bundle.unit_ids}
        keep = np.ones(times.size, dtype=bool)
        next_id = int(bundle.unit_ids.max()) + 1 if bundle.n_units else 0

        if style == "conservative":
            for t in truth:
                if t["code"] in ("DUPLICATE_UNIT", "SPLIT_UNIT"):
                    a, b = t["units"]
                    if t["code"] == "DUPLICATE_UNIT":
                        keep &= clus != b  # the copy is simply not there
                    else:
                        clus[clus == b] = a
                    origin[a] = origin.get(a, [a]) + [b]
                    origin.pop(b, None)
            if amps is not None:
                for u in list(origin):
                    a = amps[clus == u]
                    if a.size and np.median(a) < 100 and rng.random() < 0.7:
                        keep &= clus != u
                        origin.pop(u)
            keep &= rng.random(times.size) >= 0.08
        else:
            rates = {int(u): bundle.spike_indices(u).size for u in bundle.unit_ids}
            for u in sorted(rates, key=rates.get, reverse=True)[:2]:
                idx = np.flatnonzero(clus == u)
                half = idx[rng.random(idx.size) < 0.5]
                clus[half] = next_id
                origin[next_id] = [u]
                next_id += 1
            extra_t, extra_c, extra_a, extra_d = [], [], [], []
            for _ in range(3):
                t = np.sort(rng.uniform(0, bundle.duration, int(2.0 * bundle.duration)))
                extra_t.append(t)
                extra_c.append(np.full(t.size, next_id))
                extra_a.append(rng.uniform(50, 70, t.size))
                extra_d.append(np.full(t.size, rng.uniform(0, 3840)) + rng.normal(0, 5, t.size))
                origin[next_id] = []
                next_id += 1
            times = np.concatenate([times, *extra_t])
            clus = np.concatenate([clus, *extra_c])
            keep = np.concatenate([keep, np.ones(sum(x.size for x in extra_t), dtype=bool)])
            if amps is not None:
                amps = np.concatenate([amps, *extra_a])
            if deps is not None:
                deps = np.concatenate([deps, *extra_d])

        times = np.clip(times + rng.normal(0, 5e-5, times.size), 0, bundle.duration)
        old_ids = sorted(origin)
        new_ids = rng.permutation(len(old_ids)) + 100 * (k + 1)
        remap = dict(zip(old_ids, new_ids.tolist()))
        keep &= np.isin(clus, old_ids)
        clus_new = np.array([remap[int(c)] for c in clus[keep]], dtype=np.int64)
        out.append(Bundle(
            times[keep], clus_new, duration=bundle.duration,
            amplitudes=None if amps is None else amps[keep],
            spike_depths=None if deps is None else deps[keep],
            unit_ids=sorted(remap.values()),
            events=bundle.events,
            meta={
                "source": "ayar.synth.sorter_variants", "style": style, "variant": k,
                "origin": {str(remap[u]): v for u, v in origin.items()},
            },
        ))
    return out
