import numpy as np

import ayar
from ayar import Bundle, Severity
from ayar.synth import SynthConfig, make_session


def found(report, code):
    return {frozenset(f.units) for f in report.by_code(code)}


def truth(bundle, code):
    return {frozenset(t["units"]) for t in bundle.meta["truth"] if t["code"] == code}


def test_planted_artifacts_found(session0):
    rep = ayar.scan(session0)
    for code in ("DUPLICATE_UNIT", "OVERLAP_HOLE", "DRIFT_CONFOUND"):
        assert truth(session0, code) <= found(rep, code), code
    planted = set().union(*(truth(session0, c) for c in ("DUPLICATE_UNIT", "OVERLAP_HOLE", "DRIFT_CONFOUND")))
    flagged = {frozenset(f.units) for f in rep.flags}
    assert flagged == planted  # no false alarms


def test_controls_not_flagged(session0, session_interleaved):
    for b in (session0, session_interleaved):
        rep = ayar.scan(b)
        flagged_units = {u for f in rep.flags for u in f.units}
        for c in b.meta["controls"]:
            assert not set(c["units"]) & flagged_units, c


def test_drift_is_error_only_when_conditions_ordered_in_time(session0, session_interleaved):
    blocks = ayar.scan(session0).by_code("DRIFT_CONFOUND")
    inter = ayar.scan(session_interleaved).by_code("DRIFT_CONFOUND")
    assert blocks and all(f.severity is Severity.ERROR for f in blocks)
    assert inter and all(f.severity is Severity.WARNING for f in inter)


def test_tier0_drift_not_checked(session0):
    b = Bundle(session0.spike_times, session0.spike_clusters, duration=session0.duration)
    rep = ayar.scan(b)
    assert not rep.by_code("DRIFT_CONFOUND")
    assert any(n.code == "DRIFT_CONFOUND" and not n.partial for n in rep.not_checked)
    # pair detectors still run on spike times alone
    assert truth(session0, "DUPLICATE_UNIT") <= found(rep, "DUPLICATE_UNIT")


def test_too_many_pairs_without_depths_is_reported():
    rng = np.random.default_rng(0)
    n = 30
    t = np.sort(rng.uniform(0, 100, n * 200))
    c = rng.integers(0, n, t.size)
    rep = ayar.scan(Bundle(t, c, duration=100), thresholds=ayar.DEFAULTS.override(max_pairs=10))
    codes = {x.code for x in rep.not_checked}
    assert {"DUPLICATE_UNIT", "OVERLAP_HOLE"} <= codes


def test_independent_units_are_clean():
    rng = np.random.default_rng(3)
    cfg = SynthConfig(n_duplicates=0, n_holes=0, n_drifting=0, n_sync_controls=0, n_rate_controls=0)
    b = make_session(5, cfg)
    assert ayar.scan(b).flags == []
    del rng


def test_thresholds_change_outcome(session0):
    strict = ayar.DEFAULTS.override(dup_fraction_warn=0.99, dup_fraction_error=0.995)
    assert not ayar.scan(session0, thresholds=strict, detectors=["DUPLICATE_UNIT"]).flags
