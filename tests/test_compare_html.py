import json
import re

import numpy as np
import pytest

import ayar
from ayar import html
from ayar.cli import main
from ayar.compare import compare
from ayar.examples import condition_contrast, zero_lag_synchrony
from ayar.matching import coincidence_matrix, match_units
from ayar.synth import sorter_variants


@pytest.fixture(scope="module")
def variants(session0):
    return sorter_variants(session0, 2, seed=0)


def test_matching_recovers_origin(session0, variants):
    for v in variants:
        m = match_units(session0, v)
        origin = v.meta["origin"]
        assert m.pairs, "nothing matched"
        assert all(a in origin[str(b)] for a, b, _ in m.pairs)
        # every variant unit that kept most of one original unit is matched
        assert len(m.pairs) >= 0.8 * min(session0.n_units, v.n_units)


def test_noise_units_unmatched(session0, variants):
    liberal = next(v for v in variants if v.meta["style"] == "liberal")
    noise = {int(u) for u, o in liberal.meta["origin"].items() if not o}
    m = match_units(session0, liberal)
    assert noise and noise <= set(m.unmatched_b)


def test_coincidence_matrix_counts_once_per_unit():
    a = ayar.Bundle([1.0, 2.0], [0, 0], duration=3)
    b = ayar.Bundle([1.0001, 1.0002, 2.0001], [5, 5, 6], duration=3)
    m = coincidence_matrix(a, b, 0.0004)
    assert m.tolist() == [[1, 1]]  # the A spike at 1.0 counts once for unit 5


def test_compare_verdicts(session0, variants):
    sortings = {"ref": session0, "v1": variants[0], "v2": variants[1]}
    rep = compare(sortings, zero_lag_synchrony)
    assert rep.verdicts["mean_sync_ratio"] == "sorter_dependent"  # duplicates inflate synchrony in ref only
    assert len(rep.consensus_units) >= 40
    same = compare({"a": session0, "b": session0.without([])}, condition_contrast)
    assert set(same.verdicts.values()) == {"consistent"}
    assert all(s.spread == 0 for s in same.summaries)


def test_compare_copies_events_and_checks_inputs(session0, variants):
    v = variants[0].without([])
    v.events = None
    rep = compare({"ref": session0, "v": v}, condition_contrast)
    assert any("events" in n for n in rep.notes)
    with pytest.raises(ValueError):
        compare({"only": session0}, condition_contrast)
    with pytest.raises(KeyError):
        compare({"a": session0, "b": v}, condition_contrast, reference="c")


def test_compare_reference_failure_raises(session0, variants):
    def bad(b):
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError, match="reference"):
        compare({"a": session0, "b": variants[0]}, bad)


def _well_formed(page: str):
    assert page.startswith("<!DOCTYPE html>") and page.rstrip().endswith("</html>")
    assert page.count("<svg") == page.count("</svg>")
    assert "<script src" not in page and "http" not in re.sub(r'xmlns="[^"]+"', "", page.split("<style>")[0])


def test_html_reports(session0, variants):
    rep = ayar.scan(session0, condition_contrast)
    page = html.scan_html(rep, session0)
    _well_formed(page)
    assert page.count("<svg") >= len(rep.flags)  # one evidence plot per flag (plus audit charts)
    assert "SPLIT_UNIT" in page and "data table" in page
    _well_formed(html.scan_html(rep))  # without the bundle: no evidence plots, still valid
    mv = ayar.multiverse(session0, condition_contrast, ["amplitude_cutoff<=0.5,0.1"])
    _well_formed(html.multiverse_html(mv))
    cr = compare({"a": session0, "b": variants[0]}, condition_contrast)
    _well_formed(html.compare_html(cr))


def test_html_escapes_names(session0):
    rep = ayar.scan(session0, lambda b: {"<b>x</b>": 1.0}, detectors=["DUPLICATE_UNIT"],
                    finding_name="<script>alert(1)</script>")
    page = html.scan_html(rep, session0)
    assert "<script>alert" not in page and "&lt;script&gt;" in page


def test_cli_compare_and_html(tmp_path, capsys):
    p = tmp_path / "s.npz"
    assert main(["synth", str(p), "--sorters", "3", "--duration", "300"]) == 0
    files = [str(p), str(tmp_path / "s_sorter2.npz"), str(tmp_path / "s_sorter3.npz")]
    capsys.readouterr()
    out_html = tmp_path / "c.html"
    rc = main(["compare", *files, "--finding", "ayar.examples:zero_lag_synchrony", "--format", "json",
               "--html", str(out_html)])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0 and data["sortings"] == ["s", "s_sorter2", "s_sorter3"]
    assert out_html.exists() and out_html.stat().st_size > 2000
    assert main(["compare", files[0], "--finding", "ayar.examples:zero_lag_synchrony"]) == 2
    assert main(["compare", *files[:2], "--names", "x", "--finding", "ayar.examples:zero_lag_synchrony"]) == 2
    scan_html = tmp_path / "s.html"
    main(["scan", files[0], "--html", str(scan_html), "--fail-on", "never"])
    assert "Evidence" in scan_html.read_text()


def test_daftar_provenance(tmp_path, monkeypatch, capsys):
    pytest.importorskip("daftar")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DAFTAR_DIR", str(tmp_path / ".daftar"))
    p = tmp_path / "s.npz"
    main(["synth", str(p), "--duration", "300"])
    assert main(["scan", str(p), "--daftar", "--fail-on", "never", "--only", "DUPLICATE_UNIT"]) == 0
    import daftar

    runs = list(daftar.RunStore().list_ids())
    assert len(runs) == 1, "expected exactly one daftar run"
