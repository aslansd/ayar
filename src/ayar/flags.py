"""Structured results: flags (artifacts found), not-checked notes, and the report."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


@dataclass
class Flag:
    """One sorting artifact that can distort a finding."""

    code: str
    severity: Severity
    units: tuple[int, ...]
    message: str
    consequence: str
    fix: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["units"] = list(self.units)
        return d


@dataclass
class NotChecked:
    """A check that could not run, or ran only partly. ayar reports these instead of guessing."""

    code: str
    reason: str
    partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditRow:
    """How one number of the user's finding moves when flagged units are removed."""

    key: str
    ablation: str
    n_dropped: int
    baseline: float
    value: float | None
    rel_change: float | None
    control_q: float | None
    control_flip_rate: float | None
    verdict: str
    note: str = ""
    action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


VERDICT_ORDER = ["flipped", "sensitive", "shifted", "nonspecific", "robust", "failed"]


@dataclass
class Report:
    bundle: dict[str, Any]
    flags: list[Flag]
    not_checked: list[NotChecked]
    thresholds: dict[str, Any]
    audit: list[AuditRow] | None = None
    finding_name: str | None = None
    finding_baseline: dict[str, float] | None = None
    version: str = ""

    @property
    def n_errors(self) -> int:
        return sum(f.severity is Severity.ERROR for f in self.flags)

    @property
    def n_warnings(self) -> int:
        return sum(f.severity is Severity.WARNING for f in self.flags)

    @property
    def finding_verdicts(self) -> dict[str, str]:
        """Worst verdict per finding key across ablations."""
        out: dict[str, str] = {}
        for row in self.audit or []:
            cur = out.get(row.key)
            if cur is None or VERDICT_ORDER.index(row.verdict) < VERDICT_ORDER.index(cur):
                out[row.key] = row.verdict
        return out

    def exit_code(self, fail_on: str = "error") -> int:
        """1 if anything at or above ``fail_on`` severity, or a finding is flipped/sensitive."""
        if fail_on == "never":
            return 0
        bad = self.n_errors > 0 or any(
            v in ("flipped", "sensitive") for v in self.finding_verdicts.values()
        )
        if fail_on == "warning":
            bad = bad or self.n_warnings > 0
        return 1 if bad else 0

    def by_code(self, code: str) -> list[Flag]:
        return [f for f in self.flags if f.code == code]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ayar_version": self.version,
            "bundle": self.bundle,
            "summary": {
                "errors": self.n_errors,
                "warnings": self.n_warnings,
                "finding_verdicts": self.finding_verdicts,
            },
            "flags": [f.to_dict() for f in self.flags],
            "not_checked": [n.to_dict() for n in self.not_checked],
            "finding": None
            if self.audit is None
            else {
                "name": self.finding_name,
                "baseline": self.finding_baseline,
                "audit": [r.to_dict() for r in self.audit],
            },
            "thresholds": self.thresholds,
        }

    def to_json(self, **kw: Any) -> str:
        return json.dumps(self.to_dict(), indent=2, default=float, **kw)

    def __str__(self) -> str:
        from .render import format_text

        return format_text(self)
