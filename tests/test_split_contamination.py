import numpy as np

import ayar
from ayar import Bundle
from ayar.scan import reconcile


def by_code(rep, code):
    return {frozenset(f.units): f for f in rep.by_code(code)}


def test_split_modes(session0):
    rep = ayar.scan(session0, detectors=["SPLIT_UNIT"])
    flags = by_code(rep, "SPLIT_UNIT")
    for t in session0.meta["truth"]:
        if t["code"] == "SPLIT_UNIT":
            f = flags[frozenset(t["units"])]
            assert t["mode"] in f.evidence["mode"]


def test_overlap_defers_refractory_splits_to_split(session0):
    rep = ayar.scan(session0)
    split_pairs = {frozenset(t["units"]) for t in session0.meta["truth"]
                   if t["code"] == "SPLIT_UNIT" and t["mode"] == "refractory"}
    assert split_pairs and not split_pairs & set(by_code(rep, "OVERLAP_HOLE"))


def _abrupt_handoff(seed=0, T=600.0):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(0, T, int(10 * T)))
    t = t[np.concatenate([[True], np.diff(t) > 0.002])]
    a, b = t[t < T / 2], t[t >= T / 2]
    other = np.sort(rng.uniform(0, T, 3000))
    times = np.concatenate([a, b, other])
    clus = np.concatenate([np.zeros(a.size), np.ones(b.size), np.full(other.size, 2)]).astype(int)
    amps = np.concatenate([rng.normal(100, 10, a.size), rng.normal(98, 10, b.size), rng.normal(150, 10, other.size)])
    depth = {0: 500.0, 1: 515.0, 2: 520.0}
    return Bundle(times, clus, duration=T, amplitudes=amps, unit_depths=depth)


def test_abrupt_handoff_found_without_refractory_evidence():
    rep = ayar.scan(_abrupt_handoff(), detectors=["SPLIT_UNIT"])
    f = by_code(rep, "SPLIT_UNIT")[frozenset((0, 1))]
    assert f.evidence["mode"] == "handoff"
    assert f.severity is ayar.Severity.WARNING


def test_contamination_names_its_source(session0):
    rep = ayar.scan(session0, detectors=["CONTAMINATION"])
    flags = by_code(rep, "CONTAMINATION")
    named = 0
    for t in session0.meta["truth"]:
        if t["code"] == "CONTAMINATION":
            f = flags[frozenset(t["units"])]
            assert 0.1 <= f.evidence["contamination"] <= 0.5
            named += f.evidence.get("likely_source") == t["source"]
    assert named >= 1


def test_reconcile_drops_double_reports():
    split = ayar.Flag("SPLIT_UNIT", ayar.Severity.WARNING, (1, 2), "", "", "", {"mode": "handoff"})
    drift = ayar.Flag("DRIFT_CONFOUND", ayar.Severity.ERROR, (2,), "", "", "")
    other = ayar.Flag("DRIFT_CONFOUND", ayar.Severity.ERROR, (5,), "", "", "")
    contam = ayar.Flag("CONTAMINATION", ayar.Severity.ERROR, (7,), "", "", "", {"likely_source": 8})
    hole = ayar.Flag("OVERLAP_HOLE", ayar.Severity.ERROR, (8, 7), "", "", "")
    out = reconcile([split, drift, other, contam, hole])
    assert out == [split, other, contam]


def test_merge_chain_and_dedupe():
    b = Bundle([0.1, 0.10005, 0.3, 0.5, 0.7], [1, 2, 2, 3, 4], amplitudes=[1, 2, 3, 4, 5], duration=1)
    m = b.merge([(1, 2), (2, 3)], dedupe_s=0.00025)
    assert m.unit_ids.tolist() == [1, 4]
    assert m.train(1).tolist() == [0.1, 0.3, 0.5]  # 0.10005 was a duplicate of 0.1
    assert m.unit_amplitudes(1).tolist() == [1, 3, 4]
    assert b.merge([]).n_spikes == b.n_spikes


def test_audit_merges_duplicates(session0):
    rep = ayar.scan(session0, ayar.examples.condition_contrast, detectors=["DUPLICATE_UNIT"])
    assert all(r.action.startswith("merge") for r in rep.audit)
