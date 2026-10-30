"""Command-line interface: ``ayar synth | scan | validate | info | doctor``."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from . import __version__


def _thresholds(args):
    from .config import DEFAULTS

    return DEFAULTS.override_strings(args.set or [])


def _load_kwargs(args) -> dict:
    kw = {}
    if getattr(args, "sample_rate", None):
        kw["sample_rate"] = args.sample_rate
    if getattr(args, "trial_label", None):
        kw["trial_label"] = args.trial_label
    return kw


def cmd_synth(args) -> int:
    from .synth import SynthConfig, make_session

    cfg = SynthConfig(n_units=args.units, duration=args.duration, design=args.design)
    b = make_session(args.seed, cfg)
    path = b.save(args.out)
    t = b.meta["truth"]
    print(f"wrote {path}: {b.n_units} units, {b.n_spikes:,} spikes, {b.duration:g} s, design={args.design}")
    print(f"planted: " + ", ".join(f"{x['code']} {x['units']}" for x in t))
    return 0


def cmd_scan(args) -> int:
    from .audit import load_finding
    from .io import load
    from .render import format_text
    from .scan import scan

    try:
        th = _thresholds(args)
        bundle = load(args.bundle, **_load_kwargs(args))
        if args.events is not None:
            from .bundle import Events
            import numpy as np

            with np.load(args.events, allow_pickle=False) as z:
                bundle.events = Events(z["times"], z["labels"] if "labels" in z else None)
        finding, name = None, None
        if args.finding:
            name, finding = load_finding(args.finding)
        report = scan(bundle, finding, thresholds=th, detectors=args.only, finding_name=name)
    except (FileNotFoundError, ValueError, KeyError, TypeError, ImportError, AttributeError) as e:
        print(f"ayar: error: {e}", file=sys.stderr)
        return 2

    if args.json:
        Path(args.json).write_text(report.to_json())
    if args.format == "json":
        print(report.to_json())
    else:
        print(format_text(report, verbose=args.verbose))
        if args.json:
            print(f"report written to {args.json}")
    return report.exit_code(args.fail_on)


def cmd_multiverse(args) -> int:
    from .audit import load_finding
    from .io import load
    from .multiverse import multiverse

    try:
        th = _thresholds(args)
        bundle = load(args.bundle, **_load_kwargs(args))
        name, finding = load_finding(args.finding)
        table = None
        if args.metrics:
            from .metrics import read_table

            table = read_table(args.metrics, unit_column=args.unit_column, bundle=bundle)
        rep = multiverse(bundle, finding, args.grid or None, metrics=table, thresholds=th,
                         finding_name=name)
    except (FileNotFoundError, ValueError, KeyError, TypeError, ImportError, AttributeError) as e:
        print(f"ayar: error: {e}", file=sys.stderr)
        return 2
    if args.json:
        Path(args.json).write_text(rep.to_json())
    print(rep.to_json() if args.format == "json" else rep.format_text())
    return rep.exit_code(args.fail_on)


def cmd_validate(args) -> int:
    from .synth import SynthConfig
    from .validate import validate

    res = validate(range(args.seed, args.seed + args.sessions), SynthConfig(duration=args.duration),
                   _thresholds(args))
    if args.format == "json":
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(res.format_text())
    ok = res.passed(args.min_sensitivity, args.min_precision)
    if args.format != "json":
        print(f"\n  {'PASS' if ok else 'FAIL'} (min sensitivity {args.min_sensitivity}, "
              f"min precision {args.min_precision}, no control alarms)")
    return 0 if ok else 1


def cmd_info(args) -> int:
    from .io import load

    b = load(args.bundle)
    print(json.dumps(b.summary(), indent=2))
    return 0


def cmd_doctor(args) -> int:
    import numpy
    import scipy

    print(f"ayar {__version__}")
    print(f"python {platform.python_version()} ({sys.executable})")
    print(f"numpy {numpy.__version__}, scipy {scipy.__version__}")
    for mod in ("spikeinterface", "pynwb", "daftar"):
        try:
            m = __import__(mod)
            print(f"{mod} {getattr(m, '__version__', '?')} (adapter planned)")
        except ImportError:
            print(f"{mod}: not installed (optional)")
    from .examples import condition_contrast
    from .scan import scan
    from .synth import make_session

    b = make_session(0)
    r = scan(b, condition_contrast)
    planted = {(t["code"], frozenset(t["units"])) for t in b.meta["truth"]}
    found = {(f.code, frozenset(f.units)) for f in r.flags}
    ok = planted <= found
    print(f"self-check: {len(planted & found)}/{len(planted)} planted artifacts found "
          f"in a 600 s synthetic session -> {'ok' if ok else 'PROBLEM'}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ayar",
        description="Assay your spike-sorted finding before you publish.",
    )
    p.add_argument("--version", action="version", version=f"ayar {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="flag sorting artifacts and audit a finding")
    s.add_argument("bundle", help="a .npz bundle, .nwb file, Phy/Kilosort or SortingAnalyzer folder")
    s.add_argument("--finding", help="your analysis: file.py:func or module:func")
    s.add_argument("--events", help=".npz with 'times' (s) and optional 'labels' arrays")
    s.add_argument("--sample-rate", type=float, help="for Phy folders without params.py")
    s.add_argument("--trial-label", help="NWB: trials-table column holding the condition label")
    s.add_argument("--only", nargs="+", metavar="CODE", help="run only these detectors")
    s.add_argument("--set", action="append", metavar="NAME=VALUE", help="override a threshold")
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("--json", metavar="PATH", help="also write the JSON report here")
    s.add_argument("--fail-on", choices=["error", "warning", "never"], default="error",
                   help="exit 1 when flags reach this severity (default: error)")
    s.add_argument("-v", "--verbose", action="store_true", help="explain every flag")
    s.set_defaults(fn=cmd_scan)

    y = sub.add_parser("synth", help="write a synthetic session with planted artifacts")
    y.add_argument("out", help="output .npz path")
    y.add_argument("--seed", type=int, default=0)
    y.add_argument("--units", type=int, default=40)
    y.add_argument("--duration", type=float, default=600.0)
    y.add_argument("--design", choices=["block", "interleaved"], default="block")
    y.set_defaults(fn=cmd_synth)

    m = sub.add_parser("multiverse", help="recompute a finding across curation thresholds")
    m.add_argument("bundle", help="a .npz bundle, .nwb file, Phy/Kilosort or SortingAnalyzer folder")
    m.add_argument("--finding", required=True, help="your analysis: file.py:func or module:func")
    m.add_argument("--grid", action="append", metavar="RULE",
                   help="e.g. 'isi_contamination<=0.1,0.25,1' (repeatable; default: a standard grid)")
    m.add_argument("--trial-label", help="NWB: trials-table column holding the condition label")
    m.add_argument("--metrics", help="CSV/TSV of per-unit metrics (SpikeInterface, Bombcell, ...)")
    m.add_argument("--unit-column", help="unit id column in --metrics (auto-detected)")
    m.add_argument("--set", action="append", metavar="NAME=VALUE")
    m.add_argument("--format", choices=["text", "json"], default="text")
    m.add_argument("--json", metavar="PATH", help="also write the JSON report (with every universe)")
    m.add_argument("--fail-on", choices=["sign_unstable", "threshold_dependent", "never"],
                   default="sign_unstable")
    m.set_defaults(fn=cmd_multiverse)

    v = sub.add_parser("validate", help="measure detector accuracy on synthetic sessions")
    v.add_argument("--sessions", type=int, default=5)
    v.add_argument("--seed", type=int, default=0)
    v.add_argument("--duration", type=float, default=600.0)
    v.add_argument("--min-sensitivity", type=float, default=0.8)
    v.add_argument("--min-precision", type=float, default=0.8)
    v.add_argument("--set", action="append", metavar="NAME=VALUE")
    v.add_argument("--format", choices=["text", "json"], default="text")
    v.set_defaults(fn=cmd_validate)

    i = sub.add_parser("info", help="summarise a bundle")
    i.add_argument("bundle")
    i.set_defaults(fn=cmd_info)

    d = sub.add_parser("doctor", help="check the installation")
    d.set_defaults(fn=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
