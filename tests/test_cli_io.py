import json

import numpy as np

from ayar import from_phy
from ayar.cli import main


def test_synth_scan_exit_codes(tmp_path, capsys):
    p = tmp_path / "s.npz"
    assert main(["synth", str(p), "--duration", "300"]) == 0
    assert main(["scan", str(p)]) == 1
    assert main(["scan", str(p), "--fail-on", "never"]) == 0
    out = capsys.readouterr().out
    assert "DUPLICATE_UNIT" in out and "summary:" in out


def test_scan_json_and_overrides(tmp_path, capsys):
    p = tmp_path / "s.npz"
    main(["synth", str(p), "--duration", "300"])
    capsys.readouterr()
    rc = main(["scan", str(p), "--format", "json", "--only", "DUPLICATE_UNIT",
               "--set", "dup_fraction_warn=0.99", "--set", "dup_fraction_error=0.995",
               "--finding", "ayar.examples:condition_contrast"])
    data = json.loads(capsys.readouterr().out)
    assert data["flags"] == [] and rc == 0
    assert data["thresholds"]["dup_fraction_warn"] == 0.99
    assert data["finding"]["name"] == "ayar.examples:condition_contrast"


def test_scan_errors_exit_2(tmp_path, capsys):
    assert main(["scan", str(tmp_path / "missing.npz")]) == 2
    p = tmp_path / "s.npz"
    main(["synth", str(p), "--duration", "300"])
    assert main(["scan", str(p), "--set", "nope=1"]) == 2
    assert main(["scan", str(p), "--finding", "ayar.examples:does_not_exist"]) == 2


def test_external_events(tmp_path, capsys):
    p = tmp_path / "s.npz"
    main(["synth", str(p), "--duration", "300"])
    ev = tmp_path / "ev.npz"
    np.savez(ev, times=np.arange(5, 290, 3.0), labels=np.arange(95) % 2)
    assert main(["scan", str(p), "--events", str(ev), "--fail-on", "never"]) == 0
    assert "95 events" in capsys.readouterr().out


def test_from_phy(tmp_path):
    fs = 30000.0
    (tmp_path / "params.py").write_text(f"dat_path = 'x.bin'\nsample_rate = {fs}\n")
    samples = np.array([300, 600, 900, 1200, 1500], dtype=np.uint64)
    np.save(tmp_path / "spike_times.npy", samples)
    np.save(tmp_path / "spike_clusters.npy", np.array([0, 1, 0, 2, 1], dtype=np.int32))
    np.save(tmp_path / "amplitudes.npy", np.array([10, 20, 11, 30, 21], dtype=float))
    (tmp_path / "cluster_group.tsv").write_text("cluster_id\tgroup\n0\tgood\n1\tnoise\n2\tmua\n")
    (tmp_path / "cluster_info.tsv").write_text("cluster_id\tdepth\n0\t100\n1\t200\n2\t300\n")
    b = from_phy(tmp_path)
    assert b.unit_ids.tolist() == [0, 2]
    assert np.allclose(b.train(0), [0.01, 0.03])
    assert b.depth(2) == 300
    assert b.meta["labels"] == {"0": "good", "2": "mua"}
    assert from_phy(tmp_path, include=None).n_units == 3


def test_doctor(capsys):
    assert main(["doctor"]) == 0
    assert "self-check" in capsys.readouterr().out
