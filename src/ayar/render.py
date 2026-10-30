"""Plain-text rendering of a :class:`~ayar.flags.Report`."""

from __future__ import annotations

import math
import textwrap

from .flags import Report

_WRAP = 92


def _fmt(x: float | None) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    ax = abs(x)
    if ax != 0 and (ax < 1e-3 or ax >= 1e5):
        return f"{x:.3g}"
    return f"{x:.4g}"


def _wrap(text: str, indent: str) -> str:
    return textwrap.fill(text, _WRAP, initial_indent=indent, subsequent_indent=indent)


def format_text(report: Report, verbose: bool = False) -> str:
    b = report.bundle
    lines: list[str] = []
    extras = [n for n, on in (("amplitudes", b["amplitudes"]), ("depths", b["depths"])) if on]
    ev = b.get("events")
    ev_txt = ""
    if ev:
        ev_txt = f", {ev['n']} events" + (f" ({len(ev['labels'])} conditions)" if ev.get("labels") else "")
    lines.append(f"ayar {report.version}")
    lines.append(
        f"bundle: {b['n_units']} units, {b['n_spikes']:,} spikes, {b['duration_s']:g} s, "
        f"tier {b['tier']}" + (f" ({', '.join(extras)})" if extras else "") + ev_txt
    )
    lines.append("")

    if not report.flags:
        lines.append("no sorting artifacts flagged")
    for f in report.flags:
        head = f"{f.severity.value.upper():<8}{f.code:<16}"
        lines.append(_wrap(f.message, " " * len(head)).replace(" " * len(head), head, 1))
        if verbose:
            lines.append(_wrap("why it matters: " + f.consequence, " " * 24))
            lines.append(_wrap("fix: " + f.fix, " " * 24))

    if report.flags and not verbose:
        from .detectors import REGISTRY

        lines.append("")
        seen: dict[str, list] = {}
        for f in report.flags:
            seen.setdefault(f.code, []).append(f)
        for code, fl in seen.items():
            units = sorted({u for f in fl for u in f.units})
            lines.append(f"{code} ({len(fl)} flag(s), units {', '.join(map(str, units))})")
            lines.append(_wrap("why it matters: " + fl[0].consequence, "    "))
            fix = getattr(REGISTRY.get(code), "FIX", fl[0].fix)
            lines.append(_wrap("fix: " + fix, "    "))
    if report.not_checked:
        lines.append("")
        for n in report.not_checked:
            tag = "partly checked" if n.partial else "not checked"
            lines.append(_wrap(f"{tag}: {n.code}: {n.reason}", "  "))

    if report.audit is not None:
        lines.append("")
        lines.append(f"finding audit: {report.finding_name}")
        if not report.audit:
            lines.append("  nothing to remove: no units were flagged")
            for k, v in (report.finding_baseline or {}).items():
                lines.append(f"  {k} = {_fmt(v)}")
        else:
            w_key = max(len(r.key) for r in report.audit)
            w_abl = max(len(r.ablation) for r in report.audit)
            lines.append(
                f"  {'number':<{w_key}}  {'remove units flagged by':<{max(w_abl, 23)}}  "
                f"{'n':>3}  {'baseline':>10}  {'after':>10}  {'change':>8}  {'random-drop q95':>15}  verdict"
            )
            for r in report.audit:
                ch = "n/a" if r.rel_change is None or not math.isfinite(r.rel_change) else f"{r.rel_change:.0%}"
                cq = "-" if r.control_q is None else f"{r.control_q:.0%}"
                lines.append(
                    f"  {r.key:<{w_key}}  {r.ablation:<{max(w_abl, 23)}}  {r.n_dropped:>3}  "
                    f"{_fmt(r.baseline):>10}  {_fmt(r.value):>10}  {ch:>8}  {cq:>15}  {r.verdict.upper()}"
                )
                if r.note:
                    lines.append(_wrap(r.note, "    "))
            lines.append("")
            for key, v in report.finding_verdicts.items():
                lines.append(f"  {key}: {_VERDICT_TEXT[v]}")

    lines.append("")
    lines.append(f"summary: {report.n_errors} error(s), {report.n_warnings} warning(s)")
    return "\n".join(lines)


_VERDICT_TEXT = {
    "robust": "ROBUST - changes by less than the robust threshold when flagged units are removed",
    "nonspecific": "NONSPECIFIC - changes, but no more than removing the same number of random units",
    "shifted": "SHIFTED - moves more than random removals do, but stays below the sensitive threshold",
    "sensitive": "SENSITIVE - depends on the flagged units beyond what random removals explain",
    "flipped": "FLIPPED - changes sign when the flagged units are removed",
    "failed": "FAILED - the finding function raised an error on the reduced bundle",
}
