import numpy as np
import pytest

from ayar import Bundle, Events


def small():
    return Bundle(
        [0.3, 0.1, 0.2, 0.5],
        [2, 1, 1, 2],
        amplitudes=[30, 10, 20, 50],
        duration=1.0,
        events=Events([0.4, 0.2], ["b", "a"]),
        meta={"source": "test"},
    )


def test_sorted_and_indexed():
    b = small()
    assert b.spike_times.tolist() == [0.1, 0.2, 0.3, 0.5]
    assert b.train(1).tolist() == [0.1, 0.2]
    assert b.unit_amplitudes(2).tolist() == [30, 50]
    assert b.events.times.tolist() == [0.2, 0.4]
    assert b.events.labels.tolist() == ["a", "b"]
    assert b.tier == 1 and b.n_units == 2


def test_roundtrip(tmp_path):
    b = small()
    p = b.save(tmp_path / "x.npz")
    c = Bundle.load(p)
    assert np.array_equal(c.spike_times, b.spike_times)
    assert np.array_equal(c.amplitudes, b.amplitudes)
    assert c.events.labels.tolist() == ["a", "b"]
    assert c.meta == {"source": "test"}
    assert c.duration == 1.0


def test_roundtrip_synthetic(tmp_path, session0):
    c = Bundle.load(session0.save(tmp_path / "s.npz"))
    assert c.n_spikes == session0.n_spikes
    assert c.meta["truth"] == session0.meta["truth"]


def test_without():
    b = small().without([2])
    assert b.unit_ids.tolist() == [1]
    assert b.n_spikes == 2
    assert b.amplitudes.tolist() == [10, 20]


def test_empty_unit_kept():
    b = Bundle([0.1], [1], unit_ids=[1, 7], duration=1)
    assert b.train(7).size == 0


@pytest.mark.parametrize(
    "kwargs, msg",
    [
        (dict(spike_times=[0.1, 0.2], spike_clusters=[1]), "spike clusters"),
        (dict(spike_times=[-1.0], spike_clusters=[1]), ">= 0"),
        (dict(spike_times=[0.5], spike_clusters=[1], duration=0.1), "shorter"),
        (dict(spike_times=[0.5], spike_clusters=[1], unit_ids=[2]), "not in unit_ids"),
        (dict(spike_times=[0.5], spike_clusters=[1], amplitudes=[1, 2]), "amplitudes"),
    ],
)
def test_validation(kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        Bundle(kwargs.pop("spike_times"), kwargs.pop("spike_clusters"), **kwargs)
