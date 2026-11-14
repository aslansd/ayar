"""0.5: --keep (curated units), probes, more NWB layouts, the session report, python -m ayar."""

import json
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pytest

import ayar
from ayar import Bundle, KeepRule
from ayar.cli import main


# ----------------------------------------------------------------------------- keep
def test_keep_rule_parsing():
    assert KeepRule.parse("label>=1") == KeepRule("label", ">=", 1.0)
    assert KeepRule.parse(" phy_annotations == 2 ") == KeepRule("phy_annotations", "==", 2.0)
    assert str(KeepRule.parse("isi_contamination<0.1")) == "isi_contamination<0.1"
    with pytest.raises(ValueError):
        KeepRule.parse("label is good")


def test_keep_drops_units_and_records_it():
    b = ayar.make_session(0)
    units = [int(u) for u in b.unit_ids]
    good = {u: float(u % 2) for u in units[:-3]}  # the last three units have no label: dropped
    k = ayar.keep(b, ["label>=1"], metrics={"label": good})
    assert sorted(int(u) for u in k.unit_ids) == [u for u in units[:-3] if u % 2]
    assert not set(np.unique(k.spike_clusters).tolist()) - set(k.unit_ids.tolist())
    kept = k.meta["kept"]
    assert kept["units_before"] == len(units) and kept["units_after"] == k.n_units
    assert kept["steps"][0]["missing"] == 3
    assert "kept" not in b.meta  # the original bundle is untouched
    assert k.summary()["kept"]["rules"] == ["label>=1"]


def test_keep_uses_computed_and_reader_metrics():
    b = ayar.make_session(0)
    k = ayar.keep(b, ["presence_ratio>=0.9"])
    assert 0 < k.n_units < b.n_units
    b.meta["ibl_metrics"] = {"label": {str(int(u)): 1.0 for u in b.unit_ids[:10]}}
    assert ayar.keep(b, ["label>=1"]).n_units == 10
    with pytest.raises(ValueError, match="no such metric"):
        ayar.keep(b, ["bombcell_class>=1"])
    with pytest.raises(ValueError, match="no unit passes"):
        ayar.keep(b, ["firing_rate>=1e9"])


def test_scan_cli_keep(tmp_path, capsys):
    p = ayar.make_session(0).save(tmp_path / "s.npz")
    code = main(["scan", str(p), "--keep", "presence_ratio>=0.9", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code in (0, 1)
    assert out["bundle"]["kept"]["rules"] == ["presence_ratio>=0.9"]
    main(["scan", str(p), "--keep", "presence_ratio>=0.9"])
    assert "kept: " in capsys.readouterr().out


# --------------------------------------------------------------------------- probes
def _two_probe_bundle(probes: bool) -> Bundle:
    # unit 1 duplicates unit 0, but unit 1 is on the other probe at the same depth
    rng = np.random.default_rng(0)
    t0 = np.sort(rng.uniform(0, 300, 3000))
    t1 = np.sort(t0 + rng.normal(0, 5e-5, t0.size))
    t2 = np.sort(rng.uniform(0, 300, 3000))
    t = np.concatenate([t0, t1, t2])
    c = np.repeat([0, 1, 2], [t0.size, t1.size, t2.size])
    amps = np.full(t.size, 80.0)
    return Bundle(np.clip(t, 0, None), c, duration=300.0, amplitudes=amps, unit_depths=[100.0, 100.0, 500.0],
                  unit_probes=["imec0", "imec1", "imec0"] if probes else None)


def test_units_on_different_probes_are_never_paired():
    same = ayar.scan(_two_probe_bundle(False), detectors=["DUPLICATE_UNIT"])
    assert [set(f.units) for f in same.flags] == [{0, 1}]
    apart = ayar.scan(_two_probe_bundle(True), detectors=["DUPLICATE_UNIT"])
    assert apart.flags == []


def test_probes_position_and_round_trip(tmp_path):
    b = _two_probe_bundle(True)
    assert b.probes == ["imec0", "imec1"] and b.probe(1) == "imec1"
    assert b.position(0) == 100.0 and b.position(1) > 1e5
    assert b.summary()["probes"] == 2
    c = Bundle.load(b.save(tmp_path / "p.npz"))
    assert c.probes == b.probes and c.probe(1) == "imec1"
    assert b.without([0]).probe(1) == "imec1"
    one = Bundle([0.1, 0.2], [0, 1], unit_probes=["a", "a"])
    assert one.probes == [] and one.position(0) is None


# ---------------------------------------------------------------------------- NWB
def _steinmetz_nwb(path, T=300.0, n_units=12, seed=0):
    """Laid out like DANDI 000017 (SteinmetzLab/dataToNWB): two probes as electrode groups,
    cluster_depths, ragged spike_amps / spike_depths, phy_annotations, peak_channel."""
    pynwb = pytest.importorskip("pynwb")
    rng = np.random.default_rng(seed)
    nwb = pynwb.NWBFile("s", "id", datetime(2017, 10, 31, 12, tzinfo=timezone.utc))
    dev = nwb.create_device("Neuropixels")
    groups = [nwb.create_electrode_group(f"Probe{k}", "d", "brain", dev) for k in range(2)]
    for g in groups:
        for _ in range(8):
            nwb.add_electrode(x=1.0, y=2.0, z=3.0, location="CA1", group=g, filtering="none", imp=np.nan)
    for name in ("peak_channel", "waveform_duration", "phy_annotations", "cluster_depths", "sampling_rate"):
        nwb.add_unit_column(name, name)
    nwb.add_unit_column("spike_amps", "amps", index=True)
    nwb.add_unit_column("spike_depths", "depths", index=True)
    for i in range(n_units):
        t = np.sort(rng.uniform(0, T, int(rng.integers(300, 800))))
        probe, depth = i % 2, float(100 * (i // 2))
        nwb.add_unit(spike_times=t, electrodes=[probe * 8, probe * 8 + 1], electrode_group=groups[probe],
                     waveform_mean=np.zeros((82, 2)), id=i, phy_annotations=[1, 2, 3][i % 3],
                     peak_channel=probe * 8, waveform_duration=10, cluster_depths=depth, sampling_rate=30000.0,
                     spike_amps=rng.normal(50, 5, t.size), spike_depths=depth + rng.normal(0, 5, t.size))
    nwb.add_trial_column("feedback_type", "1 correct, -1 error")
    for k in range(int(T // 3) - 1):
        nwb.add_trial(start_time=3.0 * k, stop_time=3.0 * k + 2.5, feedback_type=[1, -1][k % 3 == 0])
    with pynwb.NWBHDF5IO(str(path), "w") as io:
        io.write(nwb)
    return path


def test_nwb_steinmetz_layout_reads_at_tier_1(tmp_path):
    p = _steinmetz_nwb(tmp_path / "st.nwb")
    b = ayar.from_nwb(p, trial_label="feedback_type")
    assert b.tier == 1 and b.has_amplitudes and b.spike_depths is not None
    assert b.probes == ["Probe0", "Probe1"]
    assert b.depth(4) == 200.0 and b.probe(4) == "Probe0" and b.probe(5) == "Probe1"
    assert b.meta["nwb_columns"] == {"amplitudes": "spike_amps", "spike_depths": "spike_depths",
                                     "unit_depths": "cluster_depths", "probes": "electrode_group"}
    assert set(b.meta["unit_metrics"]) == {"phy_annotations", "waveform_duration"}
    k = ayar.keep(b, ["phy_annotations>=2"])
    assert k.n_units == 8


def test_nwb_layout_and_info(tmp_path, capsys):
    p = _steinmetz_nwb(tmp_path / "st.nwb")
    lay = ayar.io.nwb_layout(p)
    assert lay["units_columns"]["spike_amps"]["kind"] == "per spike"
    assert lay["units_columns"]["electrode_group"]["example"] == "Probe0"
    assert lay["ayar_reads"]["unit_depths"] == "cluster_depths"
    assert main(["info", str(p)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["tier"] == 1 and out["probes"] == 2 and "phy_annotations" in out["reader_metrics"]


def test_nwb_depth_from_peak_channel(tmp_path):
    pynwb = pytest.importorskip("pynwb")
    nwb = pynwb.NWBFile("s", "id", datetime.now(timezone.utc))
    dev = nwb.create_device("p")
    g = nwb.create_electrode_group("shank", "d", "l", dev)
    for y in (0.0, 20.0, 40.0, 60.0):
        nwb.add_electrode(x=0.0, y=y, z=0.0, location="ctx", group=g, filtering="none", imp=np.nan)
    nwb.add_unit_column("peak_channel", "row in the electrodes table")
    for i, ch in enumerate((3, 1)):
        nwb.add_unit(spike_times=np.sort(np.random.default_rng(i).uniform(0, 10, 50)), peak_channel=ch, id=i)
    path = tmp_path / "pc.nwb"
    with pynwb.NWBHDF5IO(str(path), "w") as io:
        io.write(nwb)
    b = ayar.from_nwb(path)
    assert b.depth(0) == 60.0 and b.depth(1) == 20.0
    assert b.meta["nwb_columns"]["unit_depths"] == "electrodes.y at peak_channel"


# ------------------------------------------------------------------------ session
def test_session_api_and_html(tmp_path):
    from ayar.examples import condition_contrast

    b = ayar.make_session(0)
    other = ayar.make_session(0)
    rep = ayar.session(b, condition_contrast, keep=["presence_ratio>=0.9"], others={"copy": other})
    assert [label.split(" (")[0] for label, _, _ in rep.scans] == ["all units", "kept units"]
    assert rep.multiverse is not None and rep.compare is not None
    page = rep.html()
    for anchor in ('id="scan-1"', 'id="scan-2"', 'id="multiverse"', 'id="compare"', "<h2>Summary</h2>"):
        assert anchor in page
    d = json.loads(rep.to_json())
    assert len(d["scans"]) == 2 and d["scans"][1]["bundle"]["kept"]
    assert rep.exit_code("never") == 0


def test_session_cli(tmp_path, capsys):
    b = ayar.make_session(1)
    p = b.save(tmp_path / "s.npz")
    html, js = tmp_path / "s.html", tmp_path / "s.json"
    code = main(["session", str(p), "--finding", "ayar.examples:condition_contrast", "--keep", "presence_ratio>=0.9",
                 "--no-multiverse", "--html", str(html), "--json", str(js)])
    assert code in (0, 1)
    assert html.read_text().count('class="part"') >= 4  # two sections, each a <section> and an <h2>
    assert json.loads(js.read_text())["multiverse"] is None
    assert "=== scan: kept units" in capsys.readouterr().out


def test_python_m_ayar():
    r = subprocess.run([sys.executable, "-m", "ayar", "--version"], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("ayar ")
