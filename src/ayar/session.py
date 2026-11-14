"""One report per session: scan (all units and, with ``keep``, curated units), the
multiverse over curation thresholds, and optionally the comparison across sorters.

    rep = ayar.session(bundle, my_finding, keep=["label>=1"], others={"ks4": other_bundle})
    rep.write_html("session.html")

``ayar session`` does the same from the command line.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from . import __version__
from .bundle import Bundle
from .config import DEFAULTS, Thresholds


@dataclass
class SessionReport:
    scans: list[tuple[str, Any, Bundle]]  # (label, Report, bundle scanned)
    multiverse: Any = None
    compare: Any = None
    title: str = "ayar session"
    notes: list[str] = field(default_factory=list)
    version: str = __version__

    @property
    def main(self):
        """The scan the session is judged on: curated units when there are any, else all."""
        return self.scans[-1][1]

    def exit_code(self, fail_on: str = "error") -> int:
        return self.main.exit_code(fail_on)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ayar_version": self.version,
            "title": self.title,
            "scans": [{"label": label, **rep.to_dict()} for label, rep, _ in self.scans],
            "multiverse": None if self.multiverse is None else self.multiverse.to_dict(),
            "compare": None if self.compare is None else self.compare.to_dict(),
            "notes": self.notes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def format_text(self) -> str:
        from .render import format_text

        parts = []
        for label, rep, _ in self.scans:
            parts.append(f"=== scan: {label} ===\n" + format_text(rep))
        if self.multiverse is not None:
            parts.append("=== multiverse ===\n" + self.multiverse.format_text())
        if self.compare is not None:
            parts.append("=== across sorters ===\n" + self.compare.format_text())
        parts.extend(f"note: {n}" for n in self.notes)
        return "\n\n".join(parts)

    def html(self) -> str:
        from .html import session_html

        sub = self.scans[0][1].bundle.get("source") or "bundle"
        return session_html(title=self.title, subtitle=str(sub), scans=self.scans,
                            multiverse=self.multiverse, compare=self.compare)

    def write_html(self, path: str | Path) -> Path:
        from .html import write

        return write(path, self.html())


def session(
    bundle: Bundle,
    finding: Callable | None = None,
    *,
    keep: list[str] | None = None,
    metrics: Mapping[str, Mapping[int, float]] | None = None,
    grid: list[str] | None = None,
    multiverse: bool = True,
    others: Mapping[str, Bundle] | None = None,
    name: str = "this sorting",
    thresholds: Thresholds | None = None,
    finding_name: str | None = None,
    title: str = "ayar session",
) -> SessionReport:
    """Scan, multiverse and comparison of one session, for one HTML page.

    With ``keep``, the scan runs twice: on all units, and on the units passing the rules
    (the units a lab analyses); the multiverse and the comparison use the curated units.
    """
    from .compare import compare as compare_fn
    from .keep import keep as keep_fn
    from .multiverse import multiverse as multiverse_fn
    from .scan import scan

    th = thresholds or DEFAULTS
    scans = [("all units", scan(bundle, finding, thresholds=th, finding_name=finding_name), bundle)]
    work = bundle
    if keep:
        work = keep_fn(bundle, keep, metrics=metrics)
        k = work.meta["kept"]
        label = f"kept units ({' and '.join(k['rules'])}: {k['units_after']} of {k['units_before']})"
        scans.append((label, scan(work, finding, thresholds=th, finding_name=finding_name), work))
    rep = SessionReport(scans, title=title)
    if finding is not None and multiverse:
        try:
            rep.multiverse = multiverse_fn(work, finding, grid, metrics=metrics, thresholds=th,
                                           finding_name=finding_name)
        except ValueError as e:
            rep.notes.append(f"multiverse not run: {e}")
    if finding is not None and others:
        sortings = {name: work}
        for n, b in others.items():
            sortings[n] = keep_fn(b, keep, metrics=None) if keep else b
        rep.compare = compare_fn(sortings, finding, reference=name, thresholds=th, finding_name=finding_name)
    return rep
