"""Regenerate the sample HTML reports in docs/reports/ with the installed ayar.

    python examples/sample_reports.py      # writes docs/reports/{session,scan,multiverse,compare}.html
    python examples/sample_reports.py --out some/dir

The reports come from the synthetic session of the README's "Thirty seconds" section
(`ayar synth demo.npz --sorters 3`), so they show every detector and verdict on data whose
answer is known. ``session.html`` holds all of it on one page (``ayar session``), with a
second scan on the units passing ``presence_ratio>=0.9``. Run it after each release; the version and date are printed in each report.
The work files (demo*.npz) go to a temporary folder and are deleted.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
from pathlib import Path

FINDING = "ayar.examples:condition_contrast"


def run(*args: str) -> None:
    from ayar.cli import main as ayar_main

    # scan, multiverse and compare return 1 when the finding is in trouble; expected here
    with contextlib.redirect_stdout(io.StringIO()):
        code = ayar_main(list(args))
    if code not in (0, 1, None):
        sys.exit(f"ayar {' '.join(args)} failed with status {code}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "docs" / "reports"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        demo = Path(tmp) / "demo.npz"
        run("synth", str(demo), "--sorters", "3")
        run("scan", str(demo), "--finding", FINDING, "--html", str(out / "scan.html"))
        run("multiverse", str(demo), "--finding", FINDING, "--html", str(out / "multiverse.html"))
        run(
            "compare", str(demo), str(Path(tmp) / "demo_sorter2.npz"), str(Path(tmp) / "demo_sorter3.npz"),
            "--names", "main", "conservative", "liberal", "--finding", FINDING,
            "--html", str(out / "compare.html"),
        )
        run(
            "session", str(demo), "--finding", FINDING, "--keep", "presence_ratio>=0.9",
            "--compare", str(Path(tmp) / "demo_sorter2.npz"), str(Path(tmp) / "demo_sorter3.npz"),
            "--names", "main", "conservative", "liberal", "--title", "ayar session: synthetic demo",
            "--html", str(out / "session.html"),
        )
    import ayar

    for name in ("session", "scan", "multiverse", "compare"):
        p = out / f"{name}.html"
        print(f"{p}  ({p.stat().st_size / 1024:.0f} kB, ayar {ayar.__version__})")


if __name__ == "__main__":
    main()
