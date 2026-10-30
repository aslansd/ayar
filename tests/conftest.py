import pytest

from ayar.synth import SynthConfig, make_session


@pytest.fixture(scope="session")
def session0():
    return make_session(0)


@pytest.fixture(scope="session")
def session_interleaved():
    return make_session(1, SynthConfig(design="interleaved"))
