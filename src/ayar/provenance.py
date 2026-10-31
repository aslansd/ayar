"""Optional provenance through daftar (``pip install "ayar[provenance]"``).

With ``--daftar``, ``ayar scan``, ``multiverse`` and ``compare`` record a daftar
run: the input files (hashed), ayar's thresholds and version, the environment and
git state (captured by daftar), the flags, the finding's numbers and verdicts,
and any report files written. Two runs can then be compared with ``daftar diff``,
for example before and after re-curating a session.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


def available() -> bool:
    try:
        import daftar  # noqa: F401
    except ImportError:
        return False
    return True


@contextmanager
def tracked(label: str, params: dict[str, Any], inputs: Iterable[str | Path] = (), enabled: bool = True):
    """Yield a daftar run, or ``None`` when tracking is off or daftar is missing."""
    if not enabled or not available():
        yield None
        return
    import daftar

    with daftar.track(label, params=params, tags=["ayar"]) as run:
        for path in inputs:
            p = Path(path)
            if p.is_file():
                run.add_input(p)
            elif p.is_dir():
                for f in sorted(p.iterdir()):
                    if f.is_file() and f.stat().st_size < 2_000_000_000:
                        run.add_input(f)
        yield run


def _log(run, key: str, value: Any) -> None:
    if run is not None:
        run.log_result(key, value)


def log_scan(run, report) -> None:
    if run is None:
        return
    _log(run, "errors", report.n_errors)
    _log(run, "warnings", report.n_warnings)
    _log(run, "flags", sorted(f"{f.severity.value}:{f.code}:{'-'.join(map(str, f.units))}" for f in report.flags))
    for k, v in (report.finding_baseline or {}).items():
        _log(run, f"finding.{k}", v)
    for k, v in report.finding_verdicts.items():
        _log(run, f"verdict.{k}", v)


def log_multiverse(run, mv) -> None:
    if run is None:
        return
    _log(run, "universes_evaluated", mv.n_evaluated)
    for s in mv.summaries:
        _log(run, f"finding.{s.key}.median", s.median)
        _log(run, f"finding.{s.key}.spread", s.spread)
        _log(run, f"verdict.{s.key}", s.verdict)


def log_compare(run, cr) -> None:
    if run is None:
        return
    _log(run, "consensus_units", len(cr.consensus_units))
    for m in cr.matchings:
        _log(run, f"matched.{m.name_b}", len(m.pairs))
    for s in cr.summaries:
        for name, v in s.values.items():
            _log(run, f"finding.{s.key}.{name}", v)
        _log(run, f"verdict.{s.key}", s.verdict)


def add_outputs(run, paths: Iterable[str | Path | None]) -> None:
    if run is None:
        return
    for p in paths:
        if p and Path(p).exists():
            run.add_output(Path(p))
