"""All-pairs coincidence counts (ayar.pairstats) and the pair detectors that read them."""

from itertools import permutations

import numpy as np
import pytest

import ayar
from ayar import Bundle
from ayar.pairstats import _direct, compute, estimate_spike_pairs, for_detectors, windows_for

W = windows_for(ayar.DEFAULTS)


def _quantised(b: Bundle, fs: float | None) -> Bundle:
    t = b.spike_times if fs is None else np.round(b.spike_times * fs) / fs
    return Bundle(t, b.spike_clusters, duration=b.duration, amplitudes=b.amplitudes, spike_depths=b.spike_depths)


@pytest.mark.parametrize("fs", [None, 30000.0])
@pytest.mark.parametrize("max_distance", [None, 100.0])
def test_counts_match_pair_by_pair_counting(fs, max_distance):
    # every ordered pair, including pairs farther apart than the sweep covers (counted directly);
    # with times on a 30 kHz grid many lags sit exactly on a window bound
    b = _quantised(ayar.make_session(0), fs)
    units = [int(u) for u in b.unit_ids]
    ps = compute(b, units, W, max_distance_um=max_distance)
    pairs = list(permutations(units, 2))
    got = ps.counts(pairs)
    for i, (a, c) in enumerate(pairs):
        for w, v in _direct(b, a, c, W).items():
            assert got[w][i] == v, (a, c, w)


def test_lags_on_a_bound_depend_on_the_side_as_in_count_within():
    # two units on a 30 kHz grid, 30 samples (1 ms) apart: whether "1 ms" counts as within 1 ms
    # depends on float rounding of t + w vs t - w, and pairstats must agree with count_within
    fs = 30000.0
    t1 = np.arange(1, 2001) * 0.05
    t1 = np.round(t1 * fs) / fs
    t2 = np.round((t1 + 0.001) * fs) / fs
    t = np.concatenate([t1, t2])
    c = np.concatenate([np.zeros(t1.size, int), np.ones(t2.size, int)])
    b = Bundle(t, c, duration=101.0)
    ps = compute(b, [0, 1], W)
    for a, d in ((0, 1), (1, 0)):
        direct = _direct(b, a, d, W)
        assert all(ps.count(a, d, w) == v for w, v in direct.items())


def test_detector_cache_is_reused():
    b = ayar.make_session(1)
    assert for_detectors(b, ayar.DEFAULTS) is for_detectors(b, ayar.DEFAULTS)


def test_spike_pair_estimate_is_close_for_poisson_trains():
    rng = np.random.default_rng(0)
    t = np.sort(rng.uniform(0, 200, 40_000))
    c = rng.integers(0, 20, t.size)
    b = Bundle(t, c, duration=200)
    units = [int(u) for u in b.unit_ids]
    est = estimate_spike_pairs(b, units, 0.010)
    seen = compute(b, units, W).n_spike_pairs
    assert 0.8 < seen / est < 1.2


def _tier0_with_duplicate(n_units=250, seed=0):
    rng = np.random.default_rng(seed)
    T = 300.0
    trains = [np.sort(rng.uniform(0, T, int(rng.integers(300, 900)))) for _ in range(n_units)]
    trains.append(np.sort(trains[0] + rng.normal(0, 5e-5, trains[0].size)))  # a duplicate of unit 0
    t = np.concatenate(trains)
    c = np.concatenate([np.full(x.size, i) for i, x in enumerate(trains)])
    return Bundle(t, c, duration=T)


def test_tier0_session_with_many_units_gets_pair_detectors():
    # 251 units, 31,375 pairs: more than the old 20,000-pair limit, no depths
    b = _tier0_with_duplicate()
    rep = ayar.scan(b)
    nc = {x.code for x in rep.not_checked if not x.partial}
    assert not nc & {"DUPLICATE_UNIT", "SPLIT_UNIT", "OVERLAP_HOLE"}
    dups = [set(f.units) for f in rep.by_code("DUPLICATE_UNIT")]
    assert {0, 250} in dups


def test_spike_pair_budget_is_reported():
    b = _tier0_with_duplicate(60)
    rep = ayar.scan(b, thresholds=ayar.DEFAULTS.override(max_spike_pairs=1e3))
    reasons = {x.code: x.reason for x in rep.not_checked}
    assert "DUPLICATE_UNIT" in reasons and "max_spike_pairs" in reasons["DUPLICATE_UNIT"]


def test_robust_repairs_skip_control_reruns_but_keep_verdicts():
    from ayar.examples import condition_contrast

    b = ayar.make_session(2)
    fast = ayar.scan(b, condition_contrast)
    full = ayar.scan(b, condition_contrast, thresholds=ayar.DEFAULTS.override(audit_controls_when_robust=1))
    assert [(r.ablation, r.key, r.verdict) for r in fast.audit] == [(r.ablation, r.key, r.verdict) for r in full.audit]
    assert fast.finding_verdicts == full.finding_verdicts
    for r, s in zip(fast.audit, full.audit):
        if r.control_q is None and s.control_q is not None:
            assert r.verdict == "robust" and "not run" in r.note
        else:  # non-robust repairs: the same controls (same random stream)
            assert r.control_q == s.control_q
