"""Adapters against the real libraries; skipped when they are not installed."""

from datetime import datetime, timezone

import numpy as np
import pytest

import ayar


@pytest.fixture(scope="module")
def si_objects():
    si = pytest.importorskip("spikeinterface.full")
    rec, sorting = si.generate_ground_truth_recording(durations=[30.0], num_units=6, seed=0)
    an = si.create_sorting_analyzer(sorting, rec, sparse=True, format="memory")
    an.compute(["random_spikes", "templates", "noise_levels", "spike_amplitudes",
                "spike_locations", "unit_locations", "quality_metrics"], verbose=False)
    return sorting, an


def test_from_spikeinterface_analyzer(si_objects):
    sorting, an = si_objects
    b = ayar.from_spikeinterface(an)
    assert b.tier == 1 and b.n_units == 6 and b.duration == pytest.approx(30.0)
    assert (b.amplitudes >= 0).all()
    uid = sorting.get_unit_ids()[2]
    assert np.allclose(b.train(int(uid)), sorting.get_unit_spike_train(uid, return_times=True))
    assert b.depth(0) is not None


def test_from_spikeinterface_sorting_and_scan(si_objects):
    sorting, _ = si_objects
    b = ayar.from_spikeinterface(sorting)
    assert b.tier == 0
    ayar.scan(b)  # runs end to end


def test_spikeinterface_metrics(si_objects):
    from ayar.metrics import from_spikeinterface

    _, an = si_objects
    m = from_spikeinterface(an)
    assert "firing_rate" in m and len(m["firing_rate"]) == 6


def test_saved_analyzer_folder(si_objects, tmp_path):
    si = pytest.importorskip("spikeinterface.full")
    sorting, an = si_objects
    an.save_as(folder=tmp_path / "an", format="binary_folder")
    b = ayar.load(tmp_path / "an")
    assert b.n_units == 6 and b.has_amplitudes


def test_string_unit_ids():
    pytest.importorskip("spikeinterface")
    from spikeinterface.core import NumpySorting

    s = NumpySorting.from_samples_and_labels([np.array([10, 20, 30])], [np.array(["x", "y", "x"])], 1000.0)
    b = ayar.from_spikeinterface(s)
    assert b.meta["unit_id_map"] == {"0": "x", "1": "y"}
    assert b.train(0).tolist() == [0.01, 0.03]


def test_from_nwb(tmp_path):
    pynwb = pytest.importorskip("pynwb")
    nwb = pynwb.NWBFile("s", "id", datetime.now(timezone.utc))
    dev = nwb.create_device("probe")
    grp = nwb.create_electrode_group("shank", "d", "loc", dev)
    for y in (0.0, 20.0, 40.0):
        nwb.add_electrode(x=0.0, y=y, z=0.0, location="ctx", group=grp)
    nwb.add_unit_column("spike_amplitudes", "amps", index=True)
    rng = np.random.default_rng(0)
    for i in range(3):
        nwb.add_unit(spike_times=np.sort(rng.uniform(0, 30, 200)),
                     spike_amplitudes=rng.uniform(50, 100, 200), electrodes=[i], id=10 + i)
    nwb.add_trial_column("condition", "c")
    for k in range(10):
        nwb.add_trial(start_time=k * 3.0, stop_time=k * 3 + 1.0, condition="ab"[k % 2])
    path = tmp_path / "t.nwb"
    with pynwb.NWBHDF5IO(str(path), "w") as io:
        io.write(nwb)
    b = ayar.load(path, trial_label="condition")
    assert b.unit_ids.tolist() == [10, 11, 12]
    assert b.depth(12) == 40.0 and b.has_amplitudes
    assert b.events.label_values.tolist() == ["a", "b"]
