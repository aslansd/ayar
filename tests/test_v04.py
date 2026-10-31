import json

import numpy as np
import pytest

import ayar
from ayar import Bundle
from ayar.audit import Action, action_for
from ayar.cli import main
from ayar.curation import apply, plan, to_phy, to_spikeinterface
from ayar.examples import condition_contrast, zero_lag_synchrony
from ayar.synth import sorter_variants


# ------------------------------------------------------------------ epochs
def test_restrict_and_epochs():
    b = Bundle([1, 2, 3, 6, 7, 8.5], [0, 0, 0, 0, 1, 1], duration=10)
    r = b.restrict({0: [(0, 2.5), (5.5, 7)]})
    assert r.train(0).tolist() == [1, 2, 6]
    assert r.train(1).tolist() == [7, 8.5]  # untouched
    assert r.observed_duration(0) == pytest.approx(4.0)
    assert r.rate(0) == pytest.approx(3 / 4.0)
    assert r.in_epochs(0, [1.0, 3.0, 6.0]).tolist() == [True, False, True]
    assert r.in_epochs(0, [2.0], until=[2.6]).tolist() == [False]  # interval leaves the epoch
    assert r.in_epochs(1, [9.9]).tolist() == [True]
    rr = r.restrict({0: [(0, 1.5)]})  # intersects
    assert rr.unit_epochs(0).tolist() == [[0, 1.5]]


def test_epochs_survive_save_without_merge(tmp_path):
    b = Bundle([1, 2, 3, 6], [0, 0, 1, 1], duration=10).restrict({0: [(0, 5)]})
    c = Bundle.load(b.save(tmp_path / "e.npz"))
    assert c.unit_epochs(0).tolist() == [[0, 5]] and 1 not in c.epochs
    assert b.without([1]).epochs.keys() == {0}
    assert 0 not in b.merge([(1, 0)]).epochs  # unit 1 was observed everywhere, so is the merge


def test_condition_contrast_respects_epochs(session0):
    u = int(session0.unit_ids[0])
    full = ayar.examples.unit_condition_contrast(session0)[u]
    # keep only the first half: in the block design that is condition 0 only -> too few trials
    half = session0.restrict({u: [(0, session0.duration / 2 - 10)]})
    d, p = ayar.examples.unit_condition_contrast(half)[u]
    assert np.isfinite(full[0]) and np.isnan(d) and p == 1.0


# -------------------------------------------------------------- drift repair
def test_drift_flags_carry_stable_epochs(session0):
    rep = ayar.scan(session0, condition_contrast, detectors=["DRIFT_CONFOUND"])
    restricted = [f for f in rep.flags if "stable_epochs" in f.evidence]
    assert restricted, "no stable epochs found"
    for f in restricted:
        ep = f.evidence["stable_epochs"]
        assert ep[0][0] == 0.0  # synthetic drift starts clean and degrades
        assert isinstance(action_for(f), Action) and action_for(f).restricts
    assert any(r.action.startswith("restrict") for r in rep.audit)
    assert rep.finding_verdicts["frac_units_suppressed"] in ("sensitive", "flipped")
    json.dumps(rep.to_dict(), default=float)  # epochs serialise


# ------------------------------------------------------------------ curation
def test_curation_plan_and_roundtrip(session0, tmp_path):
    rep = ayar.scan(session0)
    p = plan(rep)
    truth_merges = {frozenset(t["units"]) for t in session0.meta["truth"]
                    if t["code"] == "DUPLICATE_UNIT" or (t["code"] == "SPLIT_UNIT" and t["mode"] == "refractory")}
    assert {frozenset(g) for g in p["merges"]} == truth_merges
    assert p["epochs"] and not (set(p["epochs"]) & set(p["removed"]))
    cur = to_spikeinterface(rep, session0)
    assert cur["format_version"] == "2" and len(cur["unit_ids"]) == session0.n_units
    after = apply(session0, cur)
    assert after.n_units == session0.n_units - sum(len(g) - 1 for g in p["merges"]) - len(p["removed"])
    assert set(after.epochs) == set(p["epochs"])
    rescan = ayar.scan(after)
    assert not rescan.by_code("DUPLICATE_UNIT") and not rescan.by_code("DRIFT_CONFOUND")
    tsv = to_phy(rep, session0, tmp_path)
    assert tsv.read_text().splitlines()[0] == "cluster_id\tayar"


def test_curation_valid_for_spikeinterface(session0):
    pytest.importorskip("spikeinterface")
    from spikeinterface.curation import validate_curation_dict

    validate_curation_dict(to_spikeinterface(ayar.scan(session0), session0))


def test_cli_export_and_apply(tmp_path, capsys):
    p = tmp_path / "s.npz"
    main(["synth", str(p)])
    cur = tmp_path / "c.json"
    assert main(["scan", str(p), "--export-curation", str(cur), "--export-phy", str(tmp_path),
                 "--fail-on", "never"]) == 0
    assert json.loads(cur.read_text())["merges"]
    assert (tmp_path / "cluster_ayar.tsv").exists()
    capsys.readouterr()
    main(["scan", str(p), "--curation", str(cur), "--format", "json", "--fail-on", "never"])
    after = json.loads(capsys.readouterr().out)
    assert after["summary"]["errors"] < 9


# ------------------------------------------------------------- attribution
def test_compare_attribution_finds_duplicates(session0):
    v1, v2 = sorter_variants(session0, 2)
    rep = ayar.compare({"main": session0, "a": v1, "b": v2}, zero_lag_synchrony)
    top = {(r["sorting"], r["unit"]) for r in rep.attribution["mean_sync_ratio"][:2]}
    dups = {("main", t["units"][1]) for t in session0.meta["truth"] if t["code"] == "DUPLICATE_UNIT"}
    assert top == dups
    consistent = ayar.compare({"a": session0, "b": session0.without([])}, condition_contrast)
    assert consistent.attribution == {}


# ------------------------------------------------------------------- hybrid
def test_hybrid_scoring_with_a_known_sorting(tmp_path):
    si = pytest.importorskip("spikeinterface.full")
    from spikeinterface.core import NumpySorting

    from ayar import hybrid

    rec, _ = si.generate_ground_truth_recording(durations=[300.0], num_units=4, seed=2, num_channels=16)
    rec = rec.save(folder=tmp_path / "rec", verbose=False)

    def fake_sorter(hrec):  # the truth, with one unit split in two and one duplicated
        truth = ayar.Bundle.load(tmp_path / "h" / "injected.npz")
        fs = hrec.sampling_frequency
        rng = np.random.default_rng(0)
        ts, ls = [], []
        for k, u in enumerate(truth.unit_ids):
            t = truth.train(u)
            if k == 3:
                half = rng.random(t.size) < 0.5
                ts += [t[half], t[~half]]
                ls += [np.full(half.sum(), 100), np.full((~half).sum(), 101)]
            elif k == 4:
                c = t[rng.random(t.size) < 0.9] + 0.0003
                ts += [t, c]
                ls += [np.full(t.size, 200), np.full(c.size, 201)]
            else:
                ts.append(t)
                ls.append(np.full(t.size, int(u)))
        t, lab = np.concatenate(ts), np.concatenate(ls)
        o = np.argsort(t)
        return NumpySorting.from_samples_and_labels([np.round(t[o] * fs).astype(int)], [lab[o]], fs)

    sc = hybrid.run(rec, tmp_path / "h", fake_sorter, n_units=6, n_fading=2, firing_rate=(15, 20), seed=1)
    c = sc.counts()
    assert c["status"]["split"] == 2 and c["status"]["found"] == 4
    assert c["splits_caught"] == [2, 2]
    assert c["flags_scored"] >= 2 and c["flags_correct"] == c["flags_scored"]
    again = hybrid.score_folder(tmp_path / "h", tmp_path / "h" / "sorted_fake_sorter.npz")
    assert again.counts() == c
