"""IBL/ALF and NWB readers used by examples/public_sessions.py, and the script itself (offline)."""

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

import ayar
from ayar.io import ibl_events, ibl_metrics


def _trials():
    return {
        "feedback_times": np.array([1.0, 2.0, np.nan, 4.0]),
        "feedbackType": np.array([1.0, -1.0, 1.0, -1.0]),
        "stimOn_times": np.array([0.5, 1.5, 2.5, 3.5]),
        "contrastLeft": np.array([0.25, np.nan, 0.0, np.nan]),
        "contrastRight": np.array([np.nan, 1.0, np.nan, 0.5]),
        "firstMovement_times": np.array([0.7, 1.7, 2.7, 3.7]),
        "choice": np.array([1.0, -1.0, 0.0, 1.0]),
    }


def test_ibl_events():
    fb = ibl_events(_trials(), "feedback")
    assert fb.times.tolist() == [1.0, 2.0, 4.0] and fb.labels.tolist() == [1, -1, -1]
    st = ibl_events(_trials(), "stimulus")
    assert st.labels.tolist() == ["left", "right", "right"]  # zero-contrast trial dropped
    ch = ibl_events(_trials(), "choice")
    assert ch.times.tolist() == [0.7, 1.7, 3.7]  # no-go dropped
    with pytest.raises(ValueError):
        ibl_events(_trials(), "nope")


def test_from_ibl_and_alf(tmp_path, session0):
    spikes = {"times": session0.spike_times, "clusters": session0.spike_clusters,
              "amps": session0.amplitudes * 1e-6, "depths": session0.spike_depths}
    clusters = {"label": np.linspace(0, 1, int(session0.unit_ids.max()) + 1)}
    b = ayar.from_ibl(spikes, clusters, _trials())
    assert b.tier == 1 and np.allclose(b.amplitudes, session0.amplitudes)
    assert "label" in b.meta["ibl_metrics"]
    assert ibl_metrics(clusters)["label"][0] == 0.0
    for k, v in spikes.items():
        np.save(tmp_path / f"spikes.{k}.npy", v)
    np.save(tmp_path / "clusters.label.npy", clusters["label"])
    t = tmp_path / "trials"
    t.mkdir()
    for k, v in _trials().items():
        np.save(t / f"_ibl_trials.{k}.npy", v)
    a = ayar.load(tmp_path, trials_folder=t)
    assert a.n_spikes == session0.n_spikes and len(a.events) == 3


def test_nwb_negative_times(tmp_path):
    pynwb = pytest.importorskip("pynwb")
    nwb = pynwb.NWBFile("s", "id", datetime.now(timezone.utc))
    nwb.add_unit(spike_times=np.array([-1.0, 0.5, 2.0]), id=1)
    path = tmp_path / "n.nwb"
    with pynwb.NWBHDF5IO(str(path), "w") as io:
        io.write(nwb)
    with pytest.raises(ValueError, match="shift_negative"):
        ayar.from_nwb(path)
    b = ayar.from_nwb(path, shift_negative=True)
    assert b.train(1).tolist() == [0.0, 1.5, 3.0] and b.meta["time_offset_s"] == 1.0


def test_public_sessions_script_offline(tmp_path, session0, monkeypatch):
    pynwb = pytest.importorskip("pynwb")
    alf, tr = tmp_path / "alf", tmp_path / "trials"
    alf.mkdir(), tr.mkdir()
    np.save(alf / "spikes.times.npy", session0.spike_times)
    np.save(alf / "spikes.clusters.npy", session0.spike_clusters)
    np.save(alf / "spikes.amps.npy", session0.amplitudes * 1e-6)
    np.save(alf / "spikes.depths.npy", session0.spike_depths)
    ev = session0.events
    np.save(tr / "_ibl_trials.feedback_times.npy", ev.times + 0.3)
    np.save(tr / "_ibl_trials.feedbackType.npy", np.where(ev.labels == 1, 1.0, -1.0))
    nwb = pynwb.NWBFile("s", "id", datetime.now(timezone.utc))
    for u in session0.unit_ids[:12]:
        nwb.add_unit(spike_times=session0.train(u), id=int(u))
    nwb.add_trial_column("feedback_type", "f")
    for t, lab in zip(ev.times, ev.labels):
        nwb.add_trial(start_time=float(t), stop_time=float(t) + 1, feedback_type=float(lab))
    with pynwb.NWBHDF5IO(str(tmp_path / "s.nwb"), "w") as io:
        io.write(nwb)

    script = Path(__file__).resolve().parents[1] / "examples" / "public_sessions.py"
    spec = importlib.util.spec_from_file_location("public_sessions", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "res"
    monkeypatch.setattr(sys, "argv", ["public_sessions.py", "--out", str(out), "--ibl-local", str(alf),
                                      "--ibl-trials", str(tr), "--nwb-local", str(tmp_path / "s.nwb"),
                                      "--no-multiverse"])
    mod.main()
    md = (out / "RESULTS.md").read_text()
    assert "## IBL (local)" in md and "## DANDI" in md and "failed" not in md
    assert (out / "ibl_scan.html").exists() and (out / "dandi_curation.json").exists()
    assert (out / "ibl_info.json").exists()
    (out / "RESULTS.md").unlink()
    monkeypatch.setattr(sys, "argv", ["public_sessions.py", "--out", str(out), "--rebuild"])
    mod.main()
    assert "## IBL (local)" in (out / "RESULTS.md").read_text()
