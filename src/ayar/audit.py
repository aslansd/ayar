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
from typing import Any, Callable

import numpy as np

from .bundle import Bundle
from .config import Thresholds
from .flags import AuditRow, Flag

FindingFn = Callable[[Bundle], Any]


def units_to_drop(flag: Flag) -> set[int]:
    """The units whose removal neutralises a flag.

    Pair flags list the unit to keep first, so the second unit is dropped
    (for duplicates, the smaller copy). Single-unit flags drop the unit.
    """
    if len(flag.units) >= 2:
        return {int(flag.units[1])}
    return {int(u) for u in flag.units}


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


def audit(
    bundle: Bundle,
    finding: FindingFn,
    flags: list[Flag],
    th: Thresholds,
) -> tuple[dict[str, float], list[AuditRow]]:
    baseline = call_finding(finding, bundle)

    groups: dict[str, set[int]] = {}
    for f in flags:
        groups.setdefault(f.code, set()).update(units_to_drop(f))
    if len(groups) > 1:
        groups["ALL_FLAGS"] = set().union(*groups.values())

    flagged_any = set().union(*groups.values()) if groups else set()
    pool = np.array([int(u) for u in bundle.unit_ids if int(u) not in flagged_any])
    rng = np.random.default_rng(th.audit_seed)

    rows: list[AuditRow] = []
    for name, drop in groups.items():
        k = len(drop)
        try:
            value = call_finding(finding, bundle.without(drop))
        except Exception as e:  # the user's function may not cope with fewer units
            for key, base in baseline.items():
                rows.append(AuditRow(key, name, k, base, None, None, None, None, "failed",
                                     f"finding raised {type(e).__name__}: {e}"))
            continue

        controls: list[dict[str, float]] = []
        note = ""
        if th.audit_controls > 0 and pool.size >= k and k > 0:
            for _ in range(th.audit_controls):
                pick = rng.choice(pool, size=k, replace=False)
                try:
                    controls.append(call_finding(finding, bundle.without(pick.tolist())))
                except Exception:
                    pass
        elif th.audit_controls > 0:
            note = f"no random-drop controls: only {pool.size} unflagged units for {k} drops"

        for key, base in baseline.items():
            new = value.get(key, math.nan)
            rel = _rel(new, base)
            ctrl_rel = [_rel(c[key], base) for c in controls if key in c]
            ctrl_q = float(np.quantile(ctrl_rel, th.audit_control_quantile)) if ctrl_rel else None
            flip_rate = (
                float(np.mean([_flipped(c[key], base) for c in controls if key in c]))
                if ctrl_rel else None
            )
            beyond = ctrl_q is None or rel > ctrl_q
            if _flipped(new, base) and (flip_rate is None or flip_rate < 1 - th.audit_control_quantile):
                verdict = "flipped"
            elif rel < th.audit_robust:
                verdict = "robust"
            elif not beyond:
                verdict = "nonspecific"
            elif rel >= th.audit_sensitive:
                verdict = "sensitive"
            else:
                verdict = "shifted"
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
                    verdict=verdict,
                    note=note,
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
