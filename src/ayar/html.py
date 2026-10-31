"""Single-file HTML reports for scan, multiverse and compare.

Everything is inline (CSS, SVG charts, a few lines of JS for tooltips), so the
file can be mailed, attached to a lab notebook or archived next to the data.
Every chart has its data table one click away, light and dark themes follow the
viewer's system setting, and no third-party library is needed.
"""

from __future__ import annotations

import html
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from . import __version__

MAX_EVIDENCE_PLOTS = 60

# ---------------------------------------------------------------- page shell
_CSS = """
.ayar{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--band:#e1e0d9;
--critical:#d03b3b;--warning:#fab219;--good:#0ca30c;--serious:#ec835a;--info:#898781;
font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--page);margin:0}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .ayar{color-scheme:dark;--page:#0d0d0d;
--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--band:#383835}}
:root[data-theme="dark"] .ayar{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--band:#383835}
.ayar main{max-width:1120px;margin:0 auto;padding:28px 24px 64px}
.ayar h1{font-size:22px;margin:0 0 4px}.ayar h2{font-size:17px;margin:32px 0 10px}
.ayar h3{font-size:14px;margin:0 0 6px}.ayar .sub{color:var(--ink2);margin:0 0 18px}
.ayar .tiles{display:flex;gap:12px;flex-wrap:wrap}
.ayar .tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 16px;min-width:130px}
.ayar .tile b{display:block;font-size:26px;font-weight:600}.ayar .tile span{color:var(--ink2);font-size:13px}
.ayar table{border-collapse:collapse;width:100%;background:var(--surface);border:1px solid var(--ring);border-radius:10px;overflow:hidden}
.ayar th,.ayar td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--grid);vertical-align:top}
.ayar th{color:var(--ink2);font-weight:600;font-size:12px}.ayar td.num{text-align:right;font-variant-numeric:tabular-nums}
.ayar tr:last-child td{border-bottom:0}
.ayar .chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;white-space:nowrap}
.ayar .chip i{font-style:normal;display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;
font-size:11px;color:#fff}.ayar .chip.error i{background:var(--critical)}.ayar .chip.warning i{background:var(--warning);color:#0b0b0b}
.ayar .chip.info i{background:var(--info)}.ayar .chip.good i{background:var(--good)}.ayar .chip.serious i{background:var(--serious)}
.ayar .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.ayar .card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px}
.ayar .card p{margin:4px 0 8px;color:var(--ink2);font-size:13px}
.ayar details{margin-top:6px}.ayar summary{cursor:pointer;color:var(--ink2);font-size:12px}
.ayar details table{margin-top:6px;font-size:12px}
.ayar svg text{font:11px system-ui,-apple-system,"Segoe UI",sans-serif;fill:var(--muted)}
.ayar svg .lab{fill:var(--ink2)}.ayar svg .hit{fill:transparent}
.ayar .note{color:var(--ink2);font-size:13px}.ayar code{font-size:12px}
.ayar .legend{display:flex;gap:14px;font-size:12px;color:var(--ink2);margin:2px 0 4px}
.ayar .legend span::before{content:"";display:inline-block;width:14px;height:2px;margin-right:5px;vertical-align:middle;background:var(--k)}
#ayar-tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);
border-radius:8px;padding:6px 9px;font-size:12px;box-shadow:0 2px 10px rgba(0,0,0,.15);display:none;z-index:9}
#ayar-tip div:first-child{font-weight:600}
"""

_JS = """
(function(){var t=document.getElementById('ayar-tip');
document.addEventListener('pointermove',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');
if(!el){t.style.display='none';return}t.textContent='';el.getAttribute('data-tip').split('\\n').forEach(function(l){
var d=document.createElement('div');d.textContent=l;t.appendChild(d)});t.style.display='block';
var x=e.clientX+14,y=e.clientY+14;if(x+t.offsetWidth>innerWidth-8)x=e.clientX-t.offsetWidth-14;
if(y+t.offsetHeight>innerHeight-8)y=e.clientY-t.offsetHeight-14;t.style.left=x+'px';t.style.top=y+'px'});})();
"""


def _page(title: str, subtitle: str, body: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{_e(title)}</title><style>{_CSS}</style></head>"
        f"<body class=\"ayar\"><main><h1>{_e(title)}</h1><p class=\"sub\">{_e(subtitle)} · "
        f"ayar {__version__} · {stamp}</p>{body}</main><div id=\"ayar-tip\"></div>"
        f"<script>{_JS}</script></body></html>"
    )


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _fmt(x, pct: bool = False) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    if pct:
        return f"{x:.0%}"
    ax = abs(x)
    if ax != 0 and (ax < 1e-3 or ax >= 1e5):
        return f"{x:.3g}"
    return f"{x:.4g}"


_CHIP = {
    "error": ("error", "✕", "error"), "warning": ("warning", "!", "warning"), "info": ("info", "i", "info"),
    "robust": ("good", "✓", "robust"), "nonspecific": ("info", "≈", "nonspecific"),
    "shifted": ("serious", "↕", "shifted"), "sensitive": ("error", "!", "sensitive"),
    "flipped": ("error", "⇅", "flipped"), "failed": ("info", "?", "failed"),
    "stable": ("good", "✓", "stable"), "consistent": ("good", "✓", "consistent"),
    "threshold_dependent": ("serious", "↕", "threshold dependent"),
    "sorter_dependent": ("serious", "↕", "sorter dependent"),
    "sign_unstable": ("error", "⇅", "sign unstable"),
}


def _chip(kind: str) -> str:
    cls, icon, label = _CHIP.get(kind, ("info", "i", kind))
    return f"<span class=\"chip {cls}\"><i aria-hidden=\"true\">{icon}</i>{_e(label)}</span>"


def _table(headers: Sequence[str], rows: Iterable[Sequence], num_cols: Iterable[int] = ()) -> str:
    nc = set(num_cols)
    head = "".join(f"<th style=\"text-align:right\">{_e(h)}</th>" if i in nc else f"<th>{_e(h)}</th>"
                   for i, h in enumerate(headers))
    body = []
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            raw = c if isinstance(c, _Raw) else _e(c)
            cells.append(f"<td class=\"num\">{raw}</td>" if i in nc else f"<td>{raw}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


class _Raw(str):
    """Already-escaped HTML that _table should not escape again."""


def _data_table(headers, rows, label="data table") -> str:
    return f"<details><summary>{_e(label)}</summary>{_table(headers, rows, range(1, len(headers)))}</details>"


# --------------------------------------------------------------- svg charts
def _nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=raw)
    start = math.ceil(lo / step) * step
    ticks, v = [], start
    while v <= hi + 1e-9 * step:
        ticks.append(round(v, 12))
        v += step
    return ticks


class _Frame:
    """A plot area with linear x and y scales, axes and gridlines."""

    def __init__(self, xlim, ylim, w=340, h=150, ml=44, mr=12, mt=10, mb=30, xlabel="", ylabel=""):
        self.w, self.h, self.ml, self.mr, self.mt, self.mb = w, h, ml, mr, mt, mb
        x0, x1 = xlim
        y0, y1 = ylim
        if x1 <= x0:
            x1 = x0 + 1
        if y1 <= y0:
            y1 = y0 + 1
        self.xlim, self.ylim = (x0, x1), (y0, y1)
        self.xlabel, self.ylabel = xlabel, ylabel
        self.parts: list[str] = []

    def x(self, v):
        x0, x1 = self.xlim
        return self.ml + (v - x0) / (x1 - x0) * (self.w - self.ml - self.mr)

    def y(self, v):
        y0, y1 = self.ylim
        return self.h - self.mb - (v - y0) / (y1 - y0) * (self.h - self.mt - self.mb)

    def axes(self, xfmt=_fmt, yfmt=_fmt):
        out = []
        for t in _nice_ticks(*self.ylim):
            yy = self.y(t)
            out.append(f'<line x1="{self.ml}" x2="{self.w - self.mr}" y1="{yy:.1f}" y2="{yy:.1f}" '
                       f'stroke="var(--grid)" stroke-width="1"/>')
            out.append(f'<text x="{self.ml - 6}" y="{yy + 3.5:.1f}" text-anchor="end">{_e(yfmt(t))}</text>')
        for t in _nice_ticks(*self.xlim):
            xx = self.x(t)
            out.append(f'<text x="{xx:.1f}" y="{self.h - self.mb + 14}" text-anchor="middle">{_e(xfmt(t))}</text>')
        base = self.y(max(self.ylim[0], 0)) if self.ylim[0] <= 0 <= self.ylim[1] else self.h - self.mb
        out.append(f'<line x1="{self.ml}" x2="{self.w - self.mr}" y1="{base:.1f}" y2="{base:.1f}" '
                   f'stroke="var(--axis)" stroke-width="1"/>')
        if self.xlabel:
            out.append(f'<text class="lab" x="{(self.ml + self.w - self.mr) / 2:.1f}" y="{self.h - 3}" '
                       f'text-anchor="middle">{_e(self.xlabel)}</text>')
        if self.ylabel:
            out.append(f'<text class="lab" x="10" y="{(self.mt + self.h - self.mb) / 2:.1f}" text-anchor="middle" '
                       f'transform="rotate(-90 10 {(self.mt + self.h - self.mb) / 2:.1f})">{_e(self.ylabel)}</text>')
        self.parts[:0] = out

    def svg(self, label: str) -> str:
        return (f'<svg viewBox="0 0 {self.w} {self.h}" width="100%" role="img" aria-label="{_e(label)}" '
                f'style="max-width:{self.w * 1.4:.0f}px">' + "".join(self.parts) + "</svg>")


def bar_chart(centers, counts, *, width, shade=None, xlabel="", ylabel="", label="chart", tip_fmt=None) -> str:
    centers, counts = np.asarray(centers, float), np.asarray(counts, float)
    top = float(counts.max()) if counts.size else 1.0
    fr = _Frame((centers.min() - width / 2, centers.max() + width / 2), (0, top * 1.08 or 1),
                xlabel=xlabel, ylabel=ylabel)
    if shade is not None:
        x0, x1 = fr.x(shade[0]), fr.x(shade[1])
        fr.parts.append(f'<rect x="{x0:.1f}" y="{fr.mt}" width="{x1 - x0:.1f}" height="{fr.h - fr.mt - fr.mb}" '
                        f'fill="var(--band)" opacity=".6"/>')
    for c, v in zip(centers, counts):
        x0 = fr.x(c - width / 2) + 1
        x1 = fr.x(c + width / 2) - 1
        y = fr.y(v)
        tip = tip_fmt(c, v) if tip_fmt else f"{_fmt(v)}\n{_fmt(c)}"
        fr.parts.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(x1 - x0, 1):.1f}" '
                        f'height="{max(fr.y(0) - y, 0):.1f}" rx="1" fill="var(--s1)" data-tip="{_e(tip)}"/>')
    fr.axes()
    return fr.svg(label)


def line_chart(x, series: list[tuple[str, np.ndarray]], *, xlabel="", ylabel="", label="chart",
               ylim=None) -> str:
    x = np.asarray(x, float)
    ys = [np.asarray(y, float) for _, y in series]
    finite = np.concatenate([y[np.isfinite(y)] for y in ys]) if ys else np.array([0.0])
    lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
    if ylim is None:
        pad = (hi - lo) * 0.08 or 1.0
        ylim = (min(0.0, lo) if lo >= 0 else lo - pad, hi + pad)
    fr = _Frame((float(x.min()), float(x.max())), ylim, xlabel=xlabel, ylabel=ylabel)
    colors = ["var(--s1)", "var(--s2)"]
    for k, y in enumerate(ys):
        pts, path = [], []
        for xi, yi in zip(x, y):
            if np.isfinite(yi):
                pts.append(f"{fr.x(xi):.1f},{fr.y(yi):.1f}")
            elif pts:
                path.append(pts)
                pts = []
        if pts:
            path.append(pts)
        for p in path:
            fr.parts.append(f'<polyline points="{" ".join(p)}" fill="none" stroke="{colors[k % 2]}" '
                            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    # hover columns: one hit target per x, listing every series
    if x.size > 1:
        half = (fr.x(x[1]) - fr.x(x[0])) / 2
        for i, xi in enumerate(x):
            tip = "\n".join([f"{xlabel or 'x'} {_fmt(xi)}"] +
                            [f"{name}: {_fmt(float(y[i]))}" for (name, _), y in zip(series, ys)])
            fr.parts.append(f'<rect class="hit" x="{fr.x(xi) - half:.1f}" y="{fr.mt}" width="{2 * half:.1f}" '
                            f'height="{fr.h - fr.mt - fr.mb}" data-tip="{_e(tip)}"/>')
    fr.axes()
    legend = ""
    if len(series) > 1:
        legend = "<div class=\"legend\">" + "".join(
            f'<span style="--k:{colors[k % 2]}">{_e(name)}</span>' for k, (name, _) in enumerate(series)) + "</div>"
    return legend + fr.svg(label)


def dot_strip(labels: Sequence[str], values: Sequence[float], *, bands: Sequence[float | None] | None = None,
              ref: float | None = None, xlabel="", label="chart", pct=False) -> str:
    """One row per label: a dot at the value, an optional gray band from 0 to ``bands[i]``."""
    vals = [v for v in values if v is not None and math.isfinite(v)]
    bvals = [b for b in (bands or []) if b is not None and math.isfinite(b)]
    allv = vals + bvals + ([ref] if ref is not None else []) + [0.0]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.06 or 0.1
    row_h = 24
    w_lab = max(90, min(220, int(7.2 * max((len(s) for s in labels), default=8)) + 16))
    fr = _Frame((lo - pad if lo < 0 else 0, hi + pad), (0, len(labels)), h=row_h * len(labels) + 34,
                ml=w_lab, mt=4, mb=30, w=460, xlabel=xlabel)
    xfmt = (lambda t: f"{t:.0%}") if pct else _fmt
    for t in _nice_ticks(*fr.xlim):
        xx = fr.x(t)
        fr.parts.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{fr.mt}" y2="{fr.h - fr.mb}" stroke="var(--grid)"/>')
        fr.parts.append(f'<text x="{xx:.1f}" y="{fr.h - fr.mb + 14}" text-anchor="middle">{_e(xfmt(t))}</text>')
    if fr.xlabel:
        fr.parts.append(f'<text class="lab" x="{(fr.ml + fr.w - fr.mr) / 2:.1f}" y="{fr.h - 3}" '
                        f'text-anchor="middle">{_e(fr.xlabel)}</text>')
    if ref is not None:
        xx = fr.x(ref)
        fr.parts.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{fr.mt}" y2="{fr.h - fr.mb}" '
                        f'stroke="var(--axis)" stroke-width="1.5" stroke-dasharray="3 3"/>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        cy = fr.mt + row_h * (i + 0.5)
        fr.parts.append(f'<text class="lab" x="{fr.ml - 8}" y="{cy + 4:.1f}" text-anchor="end">{_e(lab)}</text>')
        b = bands[i] if bands else None
        if b is not None and math.isfinite(b):
            x0, x1 = fr.x(0), fr.x(b)
            fr.parts.append(f'<rect x="{min(x0, x1):.1f}" y="{cy - 5:.1f}" width="{abs(x1 - x0):.1f}" height="10" '
                            f'rx="4" fill="var(--band)" data-tip="{_e(f"random controls, 95th percentile{chr(10)}{xfmt(b)}")}"/>')
        if v is not None and math.isfinite(v):
            fr.parts.append(f'<circle cx="{fr.x(v):.1f}" cy="{cy:.1f}" r="5" fill="var(--s1)" stroke="var(--surface)" '
                            f'stroke-width="2" data-tip="{_e(f"{xfmt(v)}{chr(10)}{lab}")}"/>')
    return fr.svg(label)


def spec_curve(values: Sequence[float], ref: float | None, *, ylabel="", label="chart") -> str:
    """Values across universes, sorted: the specification curve."""
    v = np.sort(np.asarray([x for x in values if math.isfinite(x)], float))
    if v.size == 0:
        return "<p class=\"note\">no values</p>"
    allv = np.concatenate([v, [ref] if ref is not None and math.isfinite(ref) else [], [0.0]])
    pad = (allv.max() - allv.min()) * 0.08 or 1.0
    fr = _Frame((0, v.size + 1), (min(allv.min() - pad, 0) if allv.min() < 0 else 0, allv.max() + pad),
                xlabel="universe (sorted by value)", ylabel=ylabel)
    if ref is not None and math.isfinite(ref):
        yy = fr.y(ref)
        fr.parts.append(f'<line x1="{fr.ml}" x2="{fr.w - fr.mr}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="var(--s2)" '
                        f'stroke-width="2" stroke-dasharray="4 3" data-tip="{_e(f"all units, no curation{chr(10)}{_fmt(ref)}")}"/>')
    r = 4 if v.size <= 80 else 3
    for i, x in enumerate(v):
        fr.parts.append(f'<circle cx="{fr.x(i + 1):.1f}" cy="{fr.y(x):.1f}" r="{r}" fill="var(--s1)" '
                        f'stroke="var(--surface)" stroke-width="1.5" data-tip="{_e(f"{_fmt(float(x))}{chr(10)}rank {i + 1} of {v.size}")}"/>')
    fr.axes(xfmt=lambda t: f"{t:.0f}")
    legend = ("<div class=\"legend\"><span style=\"--k:var(--s1)\">each universe</span>"
              "<span style=\"--k:var(--s2)\">all units, no curation</span></div>") if ref is not None else ""
    return legend + fr.svg(label)


# ----------------------------------------------------------- flag evidence
def _evidence(bundle, flag) -> tuple[str, str] | None:
    """(caption, svg) for one flag, drawn from the bundle."""
    from .metrics import REFRACTORY_S
    from .stats import ccg

    code = flag.code
    if code in ("DUPLICATE_UNIT", "OVERLAP_HOLE") or (
            code == "SPLIT_UNIT" and "refractory" in str(flag.evidence.get("mode", "")) and
            "handoff" not in str(flag.evidence.get("mode", ""))):
        a, b = flag.units[:2]
        lags, counts = ccg(bundle.train(a), bundle.train(b), 0.00025, 0.010)
        shade = {"DUPLICATE_UNIT": (-0.25, 0.25), "OVERLAP_HOLE": (-0.5, 0.5),
                 "SPLIT_UNIT": (-REFRACTORY_S * 1e3, REFRACTORY_S * 1e3)}[code]
        svg = bar_chart(lags * 1e3, counts, width=0.25, shade=shade, xlabel=f"lag of unit {b} after unit {a} (ms)",
                        ylabel="spike pairs", label=f"cross-correlogram of units {a} and {b}",
                        tip_fmt=lambda c, v: f"{v:.0f} pairs\nlag {c:+.2f} ms")
        return f"cross-correlogram, units {a} and {b}; shaded: the window the test looks at", svg
    if code == "SPLIT_UNIT":
        a, b = flag.units[:2]
        n = 30
        w = bundle.duration / n
        edges = np.arange(n) * w + w / 2
        ra = np.bincount(np.clip((bundle.train(a) // w).astype(int), 0, n - 1), minlength=n) / w
        rb = np.bincount(np.clip((bundle.train(b) // w).astype(int), 0, n - 1), minlength=n) / w
        svg = line_chart(edges, [(f"unit {a}", ra), (f"unit {b}", rb)], xlabel="time (s)", ylabel="rate (Hz)",
                         label=f"firing rates of units {a} and {b} over the session")
        return f"firing rate over the session: one unit hands over to the other", svg
    if code == "CONTAMINATION":
        u = flag.units[0]
        isi = np.diff(bundle.train(u)) * 1e3
        edges = np.arange(0, 20.5, 0.5)
        counts, _ = np.histogram(isi, bins=edges)
        svg = bar_chart(edges[:-1] + 0.25, counts, width=0.5, shade=(0, REFRACTORY_S * 1e3),
                        xlabel="inter-spike interval (ms)", ylabel="intervals",
                        label=f"ISI histogram of unit {u}", tip_fmt=lambda c, v: f"{v:.0f} intervals\n{c - 0.25:.1f}-{c + 0.25:.1f} ms")
        return f"inter-spike intervals of unit {u}; shaded: the refractory period", svg
    if code == "DRIFT_CONFOUND":
        from .stats import windowed

        u = flag.units[0]
        t = bundle.train(u)
        n = 20
        w = bundle.duration / n
        values = bundle.unit_amplitudes(u)
        what = "median amplitude"
        if values is None:
            values, what = bundle.unit_spike_depths(u), "median depth (µm)"
        centres, rates, med = windowed(t, values, bundle.duration, w, 5)
        s1 = line_chart(centres, [("rate (Hz)", rates)], xlabel="time (s)", ylabel="rate (Hz)",
                        label=f"firing rate of unit {u} over the session")
        s2 = line_chart(centres, [(what, med)], xlabel="time (s)", ylabel=what.split(" (")[0],
                        label=f"{what} of unit {u} over the session")
        return f"unit {u}: rate (top) and {what} (bottom) over the session", s1 + s2
    return None


# ------------------------------------------------------------------ reports
def scan_html(report, bundle=None) -> str:
    b = report.bundle
    tiles = [
        (report.n_errors, "errors"), (report.n_warnings, "warnings"),
        (len({u for f in report.flags for u in f.units}), f"of {b['n_units']} units flagged"),
    ]
    if report.audit is not None:
        bad = sum(v in ("sensitive", "flipped") for v in report.finding_verdicts.values())
        tiles.append((f"{bad}/{len(report.finding_verdicts)}", "finding numbers sensitive or flipped"))
    body = ["<div class=\"tiles\">" + "".join(
        f"<div class=\"tile\"><b>{_e(v)}</b><span>{_e(t)}</span></div>" for v, t in tiles) + "</div>"]

    body.append("<h2>Sorting artifacts</h2>")
    if not report.flags:
        body.append("<p class=\"note\">No sorting artifacts flagged.</p>")
    else:
        rows = [(_Raw(_chip(f.severity.value)), f.code, ", ".join(map(str, f.units)), f.message)
                for f in report.flags]
        body.append(_table(["severity", "detector", "units", "evidence"], rows))
        from .detectors import REGISTRY

        seen: dict[str, list] = {}
        for f in report.flags:
            seen.setdefault(f.code, []).append(f)
        items = "".join(
            f"<div class=\"card\"><h3>{_e(code)} · {len(fl)} flag(s)</h3><p><b>Why it matters:</b> "
            f"{_e(fl[0].consequence)}</p><p><b>Fix:</b> {_e(getattr(REGISTRY.get(code), 'FIX', fl[0].fix))}</p></div>"
            for code, fl in seen.items())
        body.append(f"<h2>What the flags mean</h2><div class=\"cards\">{items}</div>")

        if bundle is not None:
            cards = []
            for f in report.flags[:MAX_EVIDENCE_PLOTS]:
                ev = _evidence(bundle, f)
                if ev is None:
                    continue
                cap, svg = ev
                cards.append(f"<div class=\"card\"><h3>{_chip(f.severity.value)} {_e(f.code)} · units "
                             f"{_e(', '.join(map(str, f.units)))}</h3><p>{_e(cap)}</p>{svg}</div>")
            more = ""
            if len(report.flags) > MAX_EVIDENCE_PLOTS:
                more = f"<p class=\"note\">Plots shown for the first {MAX_EVIDENCE_PLOTS} of {len(report.flags)} flags.</p>"
            body.append(f"<h2>Evidence</h2>{more}<div class=\"cards\">{''.join(cards)}</div>")

    if report.not_checked:
        rows = [("partly checked" if n.partial else "not checked", n.code, n.reason) for n in report.not_checked]
        body.append("<h2>Not checked</h2>" + _table(["status", "detector", "reason"], rows))

    if report.audit is not None:
        body.append(f"<h2>Finding audit: {_e(report.finding_name)}</h2>")
        if not report.audit:
            body.append("<p class=\"note\">Nothing to repair: no units were flagged.</p>")
        else:
            body.append("<p class=\"note\">Each dot is how much a number changes when the flagged units are repaired; "
                        "the gray bar is what the same repair does to random unflagged units (95th percentile).</p>")
            keys = list(dict.fromkeys(r.key for r in report.audit))
            cards = []
            for key in keys:
                rows = [r for r in report.audit if r.key == key]
                svg = dot_strip([r.ablation for r in rows],
                                [r.rel_change if r.rel_change is not None and math.isfinite(r.rel_change) else None
                                 for r in rows],
                                bands=[r.control_q for r in rows], xlabel="relative change", pct=True,
                                label=f"change of {key} after each repair")
                table = _data_table(["flags", "repair", "baseline", "after", "change", "random q95", "verdict"],
                                    [(r.ablation, r.action, _fmt(r.baseline), _fmt(r.value), _fmt(r.rel_change, True),
                                      _fmt(r.control_q, True), r.verdict) for r in rows])
                cards.append(f"<div class=\"card\"><h3>{_e(key)} {_chip(report.finding_verdicts[key])}</h3>"
                             f"<p>baseline {_e(_fmt(report.finding_baseline.get(key)))}</p>{svg}{table}</div>")
            body.append(f"<div class=\"cards\">{''.join(cards)}</div>")

    body.append("<details><summary>thresholds</summary>" + _table(
        ["name", "value"], sorted(report.thresholds.items()), [1]) + "</details>")
    src = b.get("source") or "bundle"
    sub = f"{b['n_units']} units · {b['n_spikes']:,} spikes · {b['duration_s']:g} s · tier {b['tier']} · {src}"
    return _page("ayar scan", sub, "".join(body))


def multiverse_html(mv) -> str:
    tiles = [(mv.n_evaluated, f"of {mv.n_universes} universes evaluated"),
             (mv.units_total, "units before curation"),
             (sum(v != "stable" for v in mv.verdicts.values()), "numbers not stable")]
    body = ["<div class=\"tiles\">" + "".join(
        f"<div class=\"tile\"><b>{_e(v)}</b><span>{_e(t)}</span></div>" for v, t in tiles) + "</div>"]
    body.append(f"<p class=\"note\">Grid: <code>{_e('  '.join(mv.grid))}</code></p>")
    cards = []
    for s in mv.summaries:
        vals = [r["values"].get(s.key, float("nan")) for r in mv.universes]
        curve = spec_curve(vals, s.baseline, ylabel=s.key, label=f"{s.key} across universes")
        infl = dot_strip(list(s.influence), list(s.influence.values()), xlabel="median moves (relative)", pct=True,
                         label=f"which threshold moves {s.key}") if s.influence else ""
        stats = (f"median {_fmt(s.median)} · range {_fmt(s.minimum)} to {_fmt(s.maximum)} · "
                 f"same sign {s.sign_agreement:.0%} · 5-95% spread {s.spread:.0%}")
        cards.append(f"<div class=\"card\"><h3>{_e(s.key)} {_chip(s.verdict)}</h3><p>{_e(stats)}</p>{curve}"
                     f"<h3 style=\"margin-top:10px\">Which threshold matters</h3>{infl}</div>")
    body.append("<h2>Numbers across universes</h2><div class=\"cards\">" + "".join(cards) + "</div>")
    metrics = [r.split("<=")[0].split(">=")[0] for r in mv.grid]
    keys = [s.key for s in mv.summaries]
    rows = [[*(f"{u['levels'][m]:g}" for m in metrics), u["n_units"], *(_fmt(u["values"].get(k)) for k in keys)]
            for u in mv.universes]
    body.append("<h2>Every universe</h2><details><summary>table</summary>" +
                _table([*metrics, "units", *keys], rows, range(len(metrics) + len(keys) + 1)) + "</details>")
    for n in mv.notes:
        body.append(f"<p class=\"note\">note: {_e(n)}</p>")
    return _page("ayar multiverse", mv.finding_name or "finding", "".join(body))


def compare_html(cr) -> str:
    tiles = [(len(cr.names), "sortings"), (len(cr.consensus_units), f"consensus units of {cr.n_units[cr.reference]}"),
             (sum(v != "consistent" for v in cr.verdicts.values()), "numbers not consistent")]
    body = ["<div class=\"tiles\">" + "".join(
        f"<div class=\"tile\"><b>{_e(v)}</b><span>{_e(t)}</span></div>" for v, t in tiles) + "</div>"]
    body.append("<h2>Unit matching</h2>")
    rows = []
    for m in cr.matchings:
        s = m.summary()
        rows.append((f"{m.name_a} vs {m.name_b}", s["n_a"], s["n_b"], s["matched"], s["only_in_a"],
                     s["only_in_b"], _fmt(s["median_agreement"])))
    body.append(_table(["pair", "units A", "units B", "matched", "only in A", "only in B", "median agreement"],
                       rows, range(1, 7)))
    cards = []
    for m in cr.matchings:
        ag = [p[2] for p in m.pairs]
        if ag:
            edges = np.linspace(0.5, 1.0, 11)
            counts, _ = np.histogram(ag, bins=edges)
            svg = bar_chart(edges[:-1] + 0.025, counts, width=0.05, xlabel="agreement", ylabel="matched units",
                            label=f"agreement of matched units, {m.name_a} vs {m.name_b}",
                            tip_fmt=lambda c, v: f"{v:.0f} units\nagreement {c - 0.025:.2f}-{c + 0.025:.2f}")
            cards.append(f"<div class=\"card\"><h3>{_e(m.name_a)} vs {_e(m.name_b)}</h3>"
                         f"<p>agreement of the matched units</p>{svg}</div>")
    body.append("<div class=\"cards\" style=\"margin-top:14px\">" + "".join(cards) + "</div>")
    body.append(f"<h2>Finding across sorters: {_e(cr.finding_name)}</h2><p class=\"note\">The dashed line is the "
                f"reference sorting ({_e(cr.reference)}).</p>")
    cards = []
    for s in cr.summaries:
        labels = list(s.values) + (["consensus"] if s.consensus is not None else [])
        vals = list(s.values.values()) + ([s.consensus] if s.consensus is not None else [])
        svg = dot_strip(labels, vals, ref=s.values.get(cr.reference), xlabel=s.key, label=f"{s.key} per sorting")
        table = _data_table(["sorting", s.key], [(lab, _fmt(v)) for lab, v in zip(labels, vals)])
        attr = ""
        rows = (getattr(cr, "attribution", None) or {}).get(s.key) or []
        if rows:
            top = rows[:8]
            attr = ("<h3 style=\"margin-top:10px\">Units that move it most</h3><p>Each unit found by only some "
                    "sortings, left out of its own sorting in turn: the change in the number.</p>"
                    + dot_strip([f"{r['sorting']} unit {r['unit']}" for r in top], [r["delta"] for r in top],
                                ref=0.0, xlabel=f"change in {s.key} when the unit is left out",
                                label=f"units driving {s.key}"))
        cards.append(f"<div class=\"card\"><h3>{_e(s.key)} {_chip(s.verdict)}</h3><p>spread {s.spread:.0%} · same "
                     f"sign {s.sign_agreement:.0%}</p>{svg}{table}{attr}</div>")
    body.append("<div class=\"cards\">" + "".join(cards) + "</div>")
    for name, err in cr.failed.items():
        body.append(f"<p class=\"note\">failed on {_e(name)}: {_e(err)}</p>")
    for n in cr.notes:
        body.append(f"<p class=\"note\">note: {_e(n)}</p>")
    return _page("ayar compare", ", ".join(cr.names), "".join(body))


def write(path: str | Path, page: str) -> Path:
    path = Path(path)
    path.write_text(page, encoding="utf-8")
    return path
