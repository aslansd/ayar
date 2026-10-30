"""The finding audit: does the user's result survive removing the flagged units?

The user's finding is any function ``f(bundle) -> float | dict[str, float]``.
For each detector that raised flags, ayar removes the implicated units, recomputes
the finding, and compares the change with *random-drop controls*: the same number
of unflagged units removed at random. A change is only blamed on the artifact if
it is larger than what dropping arbitrary units does.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .bundle import Bundle
from .config import Thresholds
from .flags import AuditRow, Flag

FindingFn = Callable[[Bundle], Any]


@dataclass
class Action:
    """How the audit neutralises flags: units to remove and (keep, absorb) pairs to merge."""

    removes: set[int] = field(default_factory=set)
    merges: list[tuple[int, int]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.removes) + len(self.merges)

    @property
    def units(self) -> set[int]:
        return set(self.removes) | {u for p in self.merges for u in p}

    def describe(self) -> str:
        parts = []
        if self.merges:
            parts.append(f"merge {len(self.merges)}")
        if self.removes:
            parts.append(f"remove {len(self.removes)}")
        return ", ".join(parts)

    def apply(self, bundle: Bundle, dedupe_s: float) -> Bundle:
        b = bundle.merge(self.merges, dedupe_s) if self.merges else bundle
        present = set(int(u) for u in b.unit_ids)
        return b.without(self.removes & present)

    def __or__(self, other: "Action") -> "Action":
        return Action(self.removes | other.removes, self.merges + other.merges)


def action_for(flag: Flag) -> Action:
    """Merge for DUPLICATE/SPLIT, otherwise remove (the second unit of a pair, or the unit)."""
    from .detectors import REGISTRY

    kind = getattr(REGISTRY.get(flag.code), "ACTION", "remove")
    if kind == "merge" and len(flag.units) >= 2:
        return Action(merges=[(int(flag.units[0]), int(flag.units[1]))])
    if len(flag.units) >= 2:
        return Action(removes={int(flag.units[1])})
    return Action(removes={int(u) for u in flag.units})


def units_to_drop(flag: Flag) -> set[int]:
    """Units a flag implicates for removal (kept for backwards compatibility)."""
    a = action_for(flag)
    return set(a.removes) | {p[1] for p in a.merges}


def _random_action(template: Action, pool: np.ndarray, bundle: Bundle, rng,
                   depth: dict[int, float | None] | None = None) -> Action | None:
    """Same operations as ``template`` on random unflagged units (merges pair near neighbours)."""
    need = len(template.removes) + 2 * len(template.merges)
    if pool.size < need:
        return None
    avail = list(rng.permutation(pool))
    merges = []
    if depth is None and bundle.has_depths and template.merges:
        depth = {int(u): bundle.depth(int(u)) for u in pool}
    for _ in template.merges:
        a = int(avail.pop())
        if depth is not None and depth[a] is not None:
            b = min(avail, key=lambda v: abs((depth[int(v)] or 0.0) - depth[a]))
            avail.remove(b)
        else:
            b = avail.pop()
        merges.append((a, int(b)))
    removes = {int(avail.pop()) for _ in template.removes}
    return Action(removes, merges)


def call_finding(fn: FindingFn, bundle: Bundle) -> dict[str, float]:
    out = fn(bundle)
    if isinstance(out, dict):
        items = out.items()
    else:
        items = [("value", out)]
    res: dict[str, float] = {}
    for k, v in items:
        try:
            res[str(k)] = float(v)
        except (TypeError, ValueError):
            raise TypeError(
                f"finding must return a number or a dict of numbers; {k!r} is {type(v).__name__}"
            ) from None
    return res


def _rel(new: float, base: float) -> float:
    if not (math.isfinite(new) and math.isfinite(base)):
        return math.inf
    return abs(new - base) / max(abs(base), 1e-12)


def _flipped(new: float, base: float) -> bool:
    return base != 0 and new != 0 and math.copysign(1, new) != math.copysign(1, base)


def _verdict(rel, new, base, ctrl_q, flip_rate, th) -> str:
    beyond = ctrl_q is None or rel > ctrl_q
    if _flipped(new, base) and (flip_rate is None or flip_rate < 1 - th.audit_control_quantile):
        return "flipped"
    if rel < th.audit_robust:
        return "robust"
    if not beyond:
        return "nonspecific"
    if rel >= th.audit_sensitive:
        return "sensitive"
    return "shifted"


def audit(
    bundle: Bundle,
    finding: FindingFn,
    flags: list[Flag],
    th: Thresholds,
) -> tuple[dict[str, float], list[AuditRow]]:
    baseline = call_finding(finding, bundle)
    dedupe = th.dup_window_ms / 1000.0

    groups: dict[str, Action] = {}
    for f in flags:
        groups[f.code] = groups.get(f.code, Action()) | action_for(f)
    if len(groups) > 1:
        total = Action()
        for a in groups.values():
            total = total | a
        groups["ALL_FLAGS"] = total

    flagged_any = set().union(*(a.units for a in groups.values())) if groups else set()
    pool = np.array([int(u) for u in bundle.unit_ids if int(u) not in flagged_any])
    rng = np.random.default_rng(th.audit_seed)
    depth = {int(u): bundle.depth(int(u)) for u in pool} if bundle.has_depths else None

    rows: list[AuditRow] = []
    for name, action in groups.items():
        k = action.size
        try:
            value = call_finding(finding, action.apply(bundle, dedupe))
        except Exception as e:  # the user's function may not cope with fewer units
            for key, base in baseline.items():
                rows.append(AuditRow(key, name, k, base, None, None, None, None, "failed",
                                     f"finding raised {type(e).__name__}: {e}", action.describe()))
            continue

        controls: list[dict[str, float]] = []
        note = ""
        if th.audit_controls > 0:
            for _ in range(th.audit_controls):
                ctrl = _random_action(action, pool, bundle, rng, depth)
                if ctrl is None:
                    note = f"no random controls: only {pool.size} unflagged units for {action.describe()}"
                    break
                try:
                    controls.append(call_finding(finding, ctrl.apply(bundle, dedupe)))
                except Exception:
                    pass

        for key, base in baseline.items():
            new = value.get(key, math.nan)
            rel = _rel(new, base)
            ctrl_rel = [_rel(c[key], base) for c in controls if key in c]
            ctrl_q = float(np.quantile(ctrl_rel, th.audit_control_quantile)) if ctrl_rel else None
            flip_rate = (
                float(np.mean([_flipped(c[key], base) for c in controls if key in c]))
                if ctrl_rel else None
            )
            rows.append(
                AuditRow(
                    key=key,
                    ablation=name,
                    n_dropped=k,
                    baseline=base,
                    value=new,
                    rel_change=rel,
                    control_q=ctrl_q,
                    control_flip_rate=flip_rate,
                    verdict=_verdict(rel, new, base, ctrl_q, flip_rate, th),
                    note=note,
                    action=action.describe(),
                )
            )
    return baseline, rows


def load_finding(spec: str) -> tuple[str, FindingFn]:
    """Resolve ``path/to/file.py:func`` or ``package.module:func``."""
    if ":" not in spec:
        raise ValueError(f"finding must look like file.py:func or module:func, got {spec!r}")
    target, func = spec.rsplit(":", 1)
    if target.endswith(".py") or Path(target).exists():
        path = Path(target).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        mod_name = f"_ayar_finding_{path.stem}"
        spec_obj = importlib.util.spec_from_file_location(mod_name, path)
        if spec_obj is None or spec_obj.loader is None:
            raise ImportError(f"cannot import {path}")
        module = importlib.util.module_from_spec(spec_obj)
        sys.modules[mod_name] = module
        spec_obj.loader.exec_module(module)
    else:
        module = importlib.import_module(target)
    fn = getattr(module, func, None)
    if not callable(fn):
        raise AttributeError(f"{target} has no callable {func!r}")
    return f"{Path(target).name if target.endswith('.py') else target}:{func}", fn
