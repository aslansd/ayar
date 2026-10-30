"""Run every applicable detector on a bundle and, optionally, audit a finding."""

from __future__ import annotations

from typing import Iterable

from . import __version__
from .audit import FindingFn, audit
from .bundle import Bundle
from .config import DEFAULTS, Thresholds
from .detectors import REGISTRY
from .flags import Flag, NotChecked, Report


def scan(
    bundle: Bundle,
    finding: FindingFn | None = None,
    *,
    thresholds: Thresholds | None = None,
    detectors: Iterable[str] | None = None,
    finding_name: str | None = None,
) -> Report:
    """Scan ``bundle`` for sorting artifacts.

    If ``finding`` is given (``f(bundle) -> number | dict``), also report whether
    each of its numbers survives removing the flagged units.
    """
    th = thresholds or DEFAULTS
    codes = list(detectors) if detectors is not None else list(REGISTRY)
    unknown = set(codes) - set(REGISTRY)
    if unknown:
        raise KeyError(f"unknown detector(s): {', '.join(sorted(unknown))}")

    flags: list[Flag] = []
    not_checked: list[NotChecked] = []
    for code in codes:
        f, n = REGISTRY[code].run(bundle, th)
        flags.extend(f)
        not_checked.extend(n)
    flags.sort(key=lambda f: (f.severity.rank, f.code, f.units))

    report = Report(
        bundle=bundle.summary(),
        flags=flags,
        not_checked=not_checked,
        thresholds=th.to_dict(),
        version=__version__,
    )
    if finding is not None:
        baseline, rows = audit(bundle, finding, flags, th)
        report.audit = rows
        report.finding_baseline = baseline
        report.finding_name = finding_name or getattr(finding, "__name__", "finding")
    return report
