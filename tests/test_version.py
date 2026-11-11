"""The version lives in one place (src/ayar/__init__.py); everything else must agree with it."""

import importlib.metadata
import re
from pathlib import Path

import ayar


def test_installed_metadata_matches_the_package():
    # pyproject.toml reads the version from __init__.py, so the two can only differ
    # if the installed copy is stale: reinstall (pip install -e .) after a bump
    assert importlib.metadata.version("ayar") == ayar.__version__


def test_pyproject_has_no_second_version_number():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text()
    assert re.search(r'^version\s*=', text, re.M) is None, "set the version only in src/ayar/__init__.py"
    assert 'dynamic = ["version"]' in text


def test_version_is_a_release_number():
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+|rc\d+)?", ayar.__version__)
