import pytest

import ayar
from ayar.audit import load_finding
from ayar.examples import condition_contrast, zero_lag_synchrony


def test_drift_made_suppression_is_sensitive(session0):
    rep = ayar.scan(session0, condition_contrast)
    assert rep.finding_baseline["frac_units_suppressed"] > 0
    assert rep.finding_verdicts["frac_units_suppressed"] in ("sensitive", "flipped")
    assert rep.exit_code() == 1


def test_overlap_and_duplicates_bias_synchrony(session0):
    rep = ayar.scan(session0, zero_lag_synchrony, detectors=["DUPLICATE_UNIT"])
    row = next(r for r in rep.audit if r.ablation == "DUPLICATE_UNIT")
    assert row.value < row.baseline  # duplicates inflate zero-lag synchrony
    assert row.verdict in ("sensitive", "shifted")


def test_scalar_finding_and_no_flags():
    b = ayar.make_session(5, ayar.SynthConfig.clean())
    rep = ayar.scan(b, lambda bb: float(bb.n_units))
    assert rep.audit == []
    assert rep.finding_baseline == {"value": float(b.n_units)}
    assert rep.exit_code() == 0


def test_failing_finding(session0):
    def fragile(b):
        if b.n_units < session0.n_units:
            raise RuntimeError("needs every unit")
        return 1.0

    rep = ayar.scan(session0, fragile, detectors=["DUPLICATE_UNIT"])
    assert all(r.verdict == "failed" for r in rep.audit)


def test_bad_return_type(session0):
    with pytest.raises(TypeError, match="number"):
        ayar.scan(session0, lambda b: {"x": "high"}, detectors=["DUPLICATE_UNIT"])


def test_load_finding(tmp_path):
    f = tmp_path / "mine.py"
    f.write_text("def analysis(bundle):\n    return {'n': bundle.n_units}\n")
    name, fn = load_finding(f"{f}:analysis")
    assert name == "mine.py:analysis" and callable(fn)
    name, fn = load_finding("ayar.examples:condition_contrast")
    assert fn is condition_contrast
    with pytest.raises(ValueError):
        load_finding("no_colon")
