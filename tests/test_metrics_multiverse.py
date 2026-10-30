import json

import numpy as np
import pytest

import ayar
from ayar.cli import main
from ayar.examples import condition_contrast
from ayar.metrics import compute, hill_contamination, presence_ratio, read_table
from ayar.multiverse import Rule, multiverse


def test_hill_contamination():
    assert hill_contamination(0, 1000, 100) == 0
    # c = 0.2 -> n_v = 2 * 0.0015 * N^2 * 0.16 / T
    nv = round(2 * 0.0015 * 10000 ** 2 * 0.16 / 100)
    assert abs(hill_contamination(nv, 10000, 100) - 0.2) < 0.005
    assert hill_contamination(10 ** 6, 1000, 100) == 0.5


def test_presence_ratio():
    assert presence_ratio(np.array([0.5]), 100) == 0.01
    assert presence_ratio(np.linspace(0, 99.9, 1000), 100) == 1.0


def test_compute_metrics(session0):
    m = compute(session0)
    assert set(m) >= {"firing_rate", "presence_ratio", "isi_contamination", "amplitude_cutoff"}
    contaminated = [t["units"][0] for t in session0.meta["truth"] if t["code"] == "CONTAMINATION"]
    assert all(m["isi_contamination"][u] > 0.1 for u in contaminated)


def test_read_table_with_string_ids(tmp_path):
    b = ayar.Bundle([0.1, 0.2], [0, 1], duration=1, meta={"unit_id_map": {"0": "a", "1": "b"}})
    p = tmp_path / "m.csv"
    p.write_text(",snr,kind\na,5.0,x\nb,2.5,y\n")
    t = read_table(p, bundle=b)
    assert t == {"snr": {0: 5.0, 1: 2.5}}


def test_rule_parse():
    r = Rule.parse("isi_contamination<=0.1, 0.25,1")
    assert (r.metric, r.op, r.levels) == ("isi_contamination", "<=", [0.1, 0.25, 1.0])
    with pytest.raises(ValueError):
        Rule.parse("snr > 3")
    assert r.passes(np.array([0.05, 0.2, np.nan]), 0.1).tolist() == [True, False, True]


def test_multiverse_finds_threshold_dependence(session0):
    mv = multiverse(session0, condition_contrast)
    v = mv.verdicts
    assert v["mean_contrast_hz"] == "stable"
    assert v["frac_units_suppressed"] == "sign_unstable"
    assert mv.n_evaluated == mv.n_universes == 72
    s = next(s for s in mv.summaries if s.key == "frac_units_suppressed")
    assert s.most_influential == "amplitude_cutoff"
    assert mv.exit_code() == 1


def test_multiverse_drops_unknown_metric_and_skips_tiny(session0):
    mv = multiverse(session0, condition_contrast,
                    ["snr>=3", "firing_rate>=0,1000"], thresholds=ayar.DEFAULTS.override(mv_min_units=5))
    assert any("snr" in n for n in mv.notes)
    assert mv.n_skipped == 1 and mv.n_evaluated == 1
    with pytest.raises(ValueError):
        multiverse(session0, condition_contrast, ["snr>=3"])


def test_multiverse_external_metrics(session0):
    ext = {"snr": {int(u): float(u % 5) for u in session0.unit_ids}}
    mv = multiverse(session0, condition_contrast, ["snr>=0,2,4"], metrics=ext)
    assert [r["n_units"] for r in mv.universes] == sorted([r["n_units"] for r in mv.universes], reverse=True)


def test_cli_multiverse(tmp_path, capsys):
    p = tmp_path / "s.npz"
    main(["synth", str(p)])
    capsys.readouterr()
    rc = main(["multiverse", str(p), "--finding", "ayar.examples:condition_contrast",
               "--grid", "amplitude_cutoff<=0.5,0.1", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert rc in (0, 1) and data["counts"]["universes"] == 2
    assert {u["levels"]["amplitude_cutoff"] for u in data["universes"]} == {0.5, 0.1}
    assert main(["multiverse", str(p), "--finding", "ayar.examples:condition_contrast",
                 "--grid", "amplitude_cutoff<=0.5,0.1", "--fail-on", "never"]) == 0
    assert main(["multiverse", str(p), "--finding", "ayar.examples:condition_contrast",
                 "--grid", "nonsense"]) == 2
