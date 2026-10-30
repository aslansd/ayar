"""Self-validation: how well do the detectors find artifacts planted in synthetic data?"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .config import Thresholds
from .examples import condition_contrast
from .scan import scan
from .synth import SynthConfig, make_session


@dataclass
class CodeScore:
    planted: int = 0
    detected: int = 0
    false: int = 0
    control_alarms: int = 0

    @property
    def sensitivity(self) -> float | None:
        return self.detected / self.planted if self.planted else None

    @property
    def precision(self) -> float | None:
        n = self.detected + self.false
        return self.detected / n if n else None


@dataclass
class ValidationResult:
    seeds: list[int]
    scores: dict[str, CodeScore] = field(default_factory=dict)
    audit_hits: int = 0
    audit_runs: int = 0

    def passed(self, min_sensitivity: float = 0.8, min_precision: float = 0.8) -> bool:
        for s in self.scores.values():
            if s.sensitivity is not None and s.sensitivity < min_sensitivity:
                return False
            if s.precision is not None and s.precision < min_precision:
                return False
            if s.control_alarms:
                return False
        if self.audit_runs and self.audit_hits / self.audit_runs < min_sensitivity:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "seeds": self.seeds,
            "detectors": {
                c: {
                    "planted": s.planted, "detected": s.detected, "false": s.false,
                    "control_alarms": s.control_alarms,
                    "sensitivity": s.sensitivity, "precision": s.precision,
                }
                for c, s in self.scores.items()
            },
            "audit": {"drift_finding_caught": self.audit_hits, "runs": self.audit_runs},
        }

    def format_text(self) -> str:
        f = lambda x: "-" if x is None else f"{x:.2f}"  # noqa: E731
        lines = [
            f"ayar validate: {len(self.seeds)} synthetic sessions (seeds {self.seeds[0]}-{self.seeds[-1]})",
            "",
            f"  {'detector':<16} {'planted':>7} {'found':>6} {'false':>6} {'ctrl alarms':>11} "
            f"{'sensitivity':>11} {'precision':>9}",
        ]
        for c, s in self.scores.items():
            lines.append(
                f"  {c:<16} {s.planted:>7} {s.detected:>6} {s.false:>6} {s.control_alarms:>11} "
                f"{f(s.sensitivity):>11} {f(s.precision):>9}"
            )
        lines.append("")
        lines.append(
            f"  finding audit: in {self.audit_runs} session(s) drift manufactured 'suppressed' units; "
            f"ayar called that number SENSITIVE or FLIPPED in {self.audit_hits}"
        )
        return "\n".join(lines)


def validate(
    seeds: Iterable[int] = range(5),
    config: SynthConfig | None = None,
    thresholds: Thresholds | None = None,
) -> ValidationResult:
    seeds = list(seeds)
    res = ValidationResult(seeds=seeds)
    for seed in seeds:
        b = make_session(seed, config)
        rep = scan(b, condition_contrast, thresholds=thresholds)
        truth: dict[str, set[frozenset]] = {}
        for t in b.meta["truth"]:
            truth.setdefault(t["code"], set()).add(frozenset(t["units"]))
        ctrl_pairs = {frozenset(c["units"]) for c in b.meta["controls"] if c["kind"] == "synchrony"}
        ctrl_units = {u for c in b.meta["controls"] if c["kind"] == "rate_change" for u in c["units"]}

        from .detectors import REGISTRY

        for code in REGISTRY:
            s = res.scores.setdefault(code, CodeScore())
            planted = truth.get(code, set())
            s.planted += len(planted)
            found = {frozenset(f.units) for f in rep.by_code(code)}
            s.detected += len(found & planted)
            false = found - planted
            s.false += len(false)
            s.control_alarms += sum(1 for p in false if p in ctrl_pairs or p & ctrl_units)

        # audit: only count sessions where drift really manufactured "suppressed" units,
        # i.e. removing the *true* drifting units changes the number substantially
        drift_units = {u for p in truth.get("DRIFT_CONFOUND", set()) for u in p}
        if drift_units and rep.finding_baseline is not None:
            base = rep.finding_baseline["frac_units_suppressed"]
            clean = condition_contrast(b.without(drift_units))["frac_units_suppressed"]
            th = thresholds or Thresholds()
            if abs(base - clean) / max(abs(base), 1e-12) >= th.audit_sensitive:
                res.audit_runs += 1
                rows = [r for r in rep.audit or [] if r.ablation == "DRIFT_CONFOUND"
                        and r.key == "frac_units_suppressed"]
                if any(r.verdict in ("sensitive", "flipped") for r in rows):
                    res.audit_hits += 1
    return res
