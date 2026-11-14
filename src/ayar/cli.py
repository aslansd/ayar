"""Command-line interface: ``ayar scan | multiverse | compare | hybrid | synth | validate | info | doctor``."""

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


def _apply_keep(args, bundle, table=None):
    """``--keep`` rules (and ``--metrics`` for them) applied to a freshly loaded bundle."""
    if not getattr(args, "keep", None):
        return bundle
    from .keep import keep

    if table is None and getattr(args, "metrics", None):
        from .metrics import read_table

        table = read_table(args.metrics, unit_column=getattr(args, "unit_column", None), bundle=bundle)
    return keep(bundle, args.keep, metrics=table)


def _events_from(path):
    import numpy as np

    from .bundle import Events

    with np.load(path, allow_pickle=False) as z:
        return Events(z["times"], z["labels"] if "labels" in z else None)


def _outputs(args, report, html_fn) -> list[str]:
    """Write --json / --html files; return the paths written."""
    written = []
    if args.json:
        Path(args.json).write_text(report.to_json())
        written.append(args.json)
    if args.html:
        from . import html

        html.write(args.html, html_fn())
        written.append(args.html)
    return written


def _daftar_check(args) -> bool:
    if not getattr(args, "daftar", False):
        return False
    from . import provenance

    if not provenance.available():
        print('ayar: daftar is not installed; run `pip install "ayar[provenance]"` (not recorded)',
              file=sys.stderr)
        return False
    return True


_ERRORS = (FileNotFoundError, ValueError, KeyError, TypeError, ImportError, AttributeError, RuntimeError)


def cmd_synth(args) -> int:
    from .synth import SynthConfig, make_session, sorter_variants

    cfg = SynthConfig(n_units=args.units, duration=args.duration, design=args.design)
    b = make_session(args.seed, cfg)
    path = b.save(args.out)
    t = b.meta["truth"]
    print(f"wrote {path}: {b.n_units} units, {b.n_spikes:,} spikes, {b.duration:g} s, design={args.design}")
    print(f"planted: " + ", ".join(f"{x['code']} {x['units']}" for x in t))
    if args.sorters > 1:
        for v in sorter_variants(b, args.sorters - 1, seed=args.seed):
            vp = v.save(path.with_name(f"{path.stem}_sorter{v.meta['variant'] + 2}.npz"))
            print(f"wrote {vp}: {v.n_units} units, {v.meta['style']} re-sorting (units renumbered)")
    return 0


def cmd_scan(args) -> int:
    from . import provenance
    from .audit import load_finding
    from .io import load
    from .render import format_text
    from .scan import scan

    track = _daftar_check(args)
    try:
        th = _thresholds(args)
        bundle = load(args.bundle, **_load_kwargs(args))
        if args.events is not None:
            bundle.events = _events_from(args.events)
        if args.curation:
            from .curation import apply as apply_curation

            bundle = apply_curation(bundle, args.curation)
        bundle = _apply_keep(args, bundle)
        finding, name = None, None
        if args.finding:
            name, finding = load_finding(args.finding)
        inputs = [args.bundle] + [x for x in (args.events, args.curation, args.metrics) if x]
        with provenance.tracked("ayar scan", {"bundle": str(args.bundle), "finding": name,
                                              "detectors": args.only, "keep": args.keep, **th.to_dict()},
                                inputs, enabled=track) as run:
            report = scan(bundle, finding, thresholds=th, detectors=args.only, finding_name=name)
            written = _outputs(args, report, lambda: __import__("ayar.html").html.scan_html(report, bundle))
            if args.export_curation:
                from .curation import write_spikeinterface

                written.append(str(write_spikeinterface(report, bundle, args.export_curation,
                                                        include_warnings=args.curate_warnings)))
            if args.export_phy:
                from .curation import to_phy

                written.append(str(to_phy(report, bundle, args.export_phy)))
            provenance.log_scan(run, report)
            provenance.add_outputs(run, written)
    except _ERRORS as e:
        print(f"ayar: error: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(report.to_json())
    else:
        print(format_text(report, verbose=args.verbose))
        for w in written:
            print(f"report written to {w}")
    return report.exit_code(args.fail_on)


def cmd_multiverse(args) -> int:
    from . import provenance
    from .audit import load_finding
    from .io import load
    from .multiverse import multiverse

    track = _daftar_check(args)
    try:
        th = _thresholds(args)
        bundle = load(args.bundle, **_load_kwargs(args))
        if args.events is not None:
            bundle.events = _events_from(args.events)
        name, finding = load_finding(args.finding)
        table = None
        if args.metrics:
            from .metrics import read_table

            table = read_table(args.metrics, unit_column=args.unit_column, bundle=bundle)
        bundle = _apply_keep(args, bundle, table)
        inputs = [args.bundle] + [x for x in (args.events, args.metrics) if x]
        with provenance.tracked("ayar multiverse", {"bundle": str(args.bundle), "finding": name,
                                                    "grid": args.grid, "keep": args.keep, **th.to_dict()},
                                inputs, enabled=track) as run:
            rep = multiverse(bundle, finding, args.grid or None, metrics=table, thresholds=th,
                             finding_name=name)
            written = _outputs(args, rep, lambda: __import__("ayar.html").html.multiverse_html(rep))
            provenance.log_multiverse(run, rep)
            provenance.add_outputs(run, written)
    except _ERRORS as e:
        print(f"ayar: error: {e}", file=sys.stderr)
        return 2
    print(rep.to_json() if args.format == "json" else rep.format_text())
    if args.format != "json":
        for w in written:
            print(f"report written to {w}")
    return rep.exit_code(args.fail_on)


def cmd_session(args) -> int:
    from . import provenance
    from .audit import load_finding
    from .io import load
    from .session import session

    track = _daftar_check(args)
    try:
        th = _thresholds(args)
        bundle = load(args.bundle, **_load_kwargs(args))
        if args.events is not None:
            bundle.events = _events_from(args.events)
        table = None
        if args.metrics:
            from .metrics import read_table

            table = read_table(args.metrics, unit_column=args.unit_column, bundle=bundle)
        finding, name = None, None
        if args.finding:
            name, finding = load_finding(args.finding)
        others = {}
        if args.compare:
            names = args.names or []
            if names and len(names) != len(args.compare) + 1:
                raise ValueError(f"--names needs {len(args.compare) + 1} names: this sorting and each --compare")
            if not names:
                names = ["main"] + [Path(p).stem or Path(p).name for p in args.compare]
            for n, p in zip(names[1:], args.compare):
                others[n] = load(p, **_load_kwargs(args))
                if args.events is not None:
                    others[n].events = bundle.events
        main_name = (args.names or ["main"])[0]
        inputs = [args.bundle, *(args.compare or [])] + [x for x in (args.events, args.metrics) if x]
        with provenance.tracked("ayar session", {"bundle": str(args.bundle), "finding": name, "keep": args.keep,
                                                 "grid": args.grid, **th.to_dict()}, inputs, enabled=track) as run:
            rep = session(bundle, finding, keep=args.keep, metrics=table, grid=args.grid or None,
                          multiverse=not args.no_multiverse, others=others, name=main_name, thresholds=th,
                          finding_name=name, title=args.title or f"ayar session: {Path(args.bundle).name}")
            written = _outputs(args, rep, rep.html)
            provenance.log_scan(run, rep.main)
            provenance.add_outputs(run, written)
    except _ERRORS as e:
        print(f"ayar: error: {e}", file=sys.stderr)
        return 2
    print(rep.to_json() if args.format == "json" else rep.format_text())
    if args.format != "json":
        for w in written:
            print(f"report written to {w}")
    return rep.exit_code(args.fail_on)


def cmd_compare(args) -> int:
    from . import provenance
    from .audit import load_finding
    from .compare import compare
    from .io import load

    track = _daftar_check(args)
    try:
        th = _thresholds(args)
        names = args.names or []
        if names and len(names) != len(args.sortings):
            raise ValueError(f"{len(names)} names for {len(args.sortings)} sortings")
        if not names:
            names = [Path(p).stem if Path(p).suffix else Path(p).name for p in args.sortings]
            if len(set(names)) < len(names):
                names = [f"{n}_{i + 1}" for i, n in enumerate(names)]
        sortings = {n: _apply_keep(args, load(p, **_load_kwargs(args))) for n, p in zip(names, args.sortings)}
        if args.events is not None:
            ev = _events_from(args.events)
            for b in sortings.values():
                b.events = ev
        name, finding = load_finding(args.finding)
        inputs = list(args.sortings) + ([args.events] if args.events else [])
        with provenance.tracked("ayar compare", {"sortings": dict(zip(names, map(str, args.sortings))),
                                                 "finding": name, "reference": args.reference, **th.to_dict()},
                                inputs, enabled=track) as run:
            rep = compare(sortings, finding, reference=args.reference, thresholds=th, finding_name=name)
            written = _outputs(args, rep, lambda: __import__("ayar.html").html.compare_html(rep))
            provenance.log_compare(run, rep)
            provenance.add_outputs(run, written)
    except _ERRORS as e:
        print(f"ayar: error: {e}", file=sys.stderr)
        return 2
    print(rep.to_json() if args.format == "json" else rep.format_text())
    if args.format != "json":
        for w in written:
            print(f"report written to {w}")
    return rep.exit_code(args.fail_on)


def _hybrid_out(args, sc) -> int:
    if args.json:
        Path(args.json).write_text(sc.to_json())
    print(sc.to_json() if args.format == "json" else sc.format_text())
    return 0


def cmd_hybrid(args) -> int:
    try:
        from . import hybrid

        th = _thresholds(args)
        if args.hybrid_cmd == "score":
            sc = hybrid.score_folder(args.folder, args.sorting, name=args.name, thresholds=th)
            return _hybrid_out(args, sc)
        rec = hybrid.load_recording(args.recording, args.reader, args.stream)
        kw = dict(n_units=args.units, n_fading=args.fading, fade_to=args.fade_to, seed=args.seed,
                  max_duration=args.max_duration)
        if args.hybrid_cmd == "make":
            out = hybrid.make(rec, args.folder, **kw)
            print(f"hybrid recording written to {out / 'recording'} ({args.units} injected units, "
                  f"{args.fading} fading); truth in {out / 'injected.npz'}")
            print(f"sort {out / 'recording'} with your pipeline, then: ayar hybrid score {out} SORTING")
            return 0
        sc = hybrid.run(rec, args.folder, args.sorter, thresholds=th, **kw)
        return _hybrid_out(args, sc)
    except _ERRORS as e:
        print(f"ayar: error: {e}", file=sys.stderr)
        return 2


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

    from .keep import unit_metrics

    try:
        b = load(args.bundle)
    except _ERRORS as e:
        b = None
        err = e
    out = {} if b is None else dict(b.summary())
    if b is not None:
        out["reader_metrics"] = sorted(unit_metrics(b))  # usable in --keep and --grid
        if b.meta.get("nwb_columns") is not None:
            out["nwb_columns_read"] = b.meta["nwb_columns"]
    if str(args.bundle).endswith(".nwb"):
        from .io import nwb_layout

        out["nwb_layout"] = nwb_layout(args.bundle)  # what the file holds, even if it did not load
    if b is None and "nwb_layout" not in out:
        print(f"ayar: error: {err}", file=sys.stderr)
        return 2
    if b is None:
        out["error"] = str(err)
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_doctor(args) -> int:
    import numpy
    import scipy

    print(f"ayar {__version__}")
    print(f"python {platform.python_version()} ({sys.executable})")
    print(f"numpy {numpy.__version__}, scipy {scipy.__version__}")
    for mod, use in (("spikeinterface", "SortingAnalyzer input, extra [spikeinterface]"),
                     ("pynwb", "NWB input, extra [nwb]"),
                     ("daftar", "provenance with --daftar, extra [provenance]")):
        try:
            m = __import__(mod)
            print(f"{mod} {getattr(m, '__version__', '?')}: {use}")
        except ImportError:
            print(f"{mod}: not installed ({use})")
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
    s.add_argument("--keep", action="append", metavar="RULE",
                   help="scan only units passing RULE, e.g. 'label>=1' (IBL) or 'phy_annotations>=2'; repeatable")
    s.add_argument("--metrics", help="CSV/TSV of per-unit metrics for --keep")
    s.add_argument("--unit-column", help="unit id column in --metrics (auto-detected)")
    s.add_argument("--set", action="append", metavar="NAME=VALUE", help="override a threshold")
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("--json", metavar="PATH", help="also write the JSON report here")
    s.add_argument("--html", metavar="PATH", help="also write a single-file HTML report with evidence plots")
    s.add_argument("--daftar", action="store_true", help="record the run with daftar (provenance)")
    s.add_argument("--export-curation", metavar="PATH",
                   help="write a SpikeInterface curation JSON (merges, removals, labels, stable epochs)")
    s.add_argument("--curate-warnings", action="store_true",
                   help="also act on warning-level flags in --export-curation (default: errors only)")
    s.add_argument("--export-phy", metavar="PATH", help="write cluster_ayar.tsv (a Phy column) here")
    s.add_argument("--curation", metavar="PATH",
                   help="apply a curation JSON (ayar's or SpikeInterface's) before scanning",)
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
    y.add_argument("--sorters", type=int, default=1,
                   help="also write N-1 re-sortings of the session, for trying `ayar compare`")
    y.set_defaults(fn=cmd_synth)

    m = sub.add_parser("multiverse", help="recompute a finding across curation thresholds")
    m.add_argument("bundle", help="a .npz bundle, .nwb file, Phy/Kilosort or SortingAnalyzer folder")
    m.add_argument("--finding", required=True, help="your analysis: file.py:func or module:func")
    m.add_argument("--grid", action="append", metavar="RULE",
                   help="e.g. 'isi_contamination<=0.1,0.25,1' (repeatable; default: a standard grid)")
    m.add_argument("--trial-label", help="NWB: trials-table column holding the condition label")
    m.add_argument("--metrics", help="CSV/TSV of per-unit metrics (SpikeInterface, Bombcell, ...)")
    m.add_argument("--unit-column", help="unit id column in --metrics (auto-detected)")
    m.add_argument("--keep", action="append", metavar="RULE",
                   help="scan only units passing RULE, e.g. 'label>=1' (IBL) or 'phy_annotations>=2'; repeatable")
    m.add_argument("--set", action="append", metavar="NAME=VALUE")
    m.add_argument("--format", choices=["text", "json"], default="text")
    m.add_argument("--json", metavar="PATH", help="also write the JSON report (with every universe)")
    m.add_argument("--html", metavar="PATH", help="also write a single-file HTML report")
    m.add_argument("--events", help=".npz with 'times' (s) and optional 'labels' arrays")
    m.add_argument("--daftar", action="store_true", help="record the run with daftar (provenance)")
    m.add_argument("--fail-on", choices=["sign_unstable", "threshold_dependent", "never"],
                   default="sign_unstable")
    m.set_defaults(fn=cmd_multiverse)

    c = sub.add_parser("compare", help="recompute a finding across sorters, with unit matching")
    c.add_argument("sortings", nargs="+", help="two or more sortings of one recording (any loadable source)")
    c.add_argument("--finding", required=True, help="your analysis: file.py:func or module:func")
    c.add_argument("--names", nargs="+", help="a name per sorting (default: file names)")
    c.add_argument("--reference", help="the sorting to match the others against (default: the first)")
    c.add_argument("--events", help=".npz with 'times' and optional 'labels', applied to every sorting")
    c.add_argument("--trial-label", help="NWB: trials-table column holding the condition label")
    c.add_argument("--keep", action="append", metavar="RULE",
                   help="use only units in every sorting passing RULE, e.g. 'label>=1' (IBL) or 'phy_annotations>=2'; repeatable")
    c.add_argument("--set", action="append", metavar="NAME=VALUE")
    c.add_argument("--format", choices=["text", "json"], default="text")
    c.add_argument("--json", metavar="PATH")
    c.add_argument("--html", metavar="PATH", help="also write a single-file HTML report")
    c.add_argument("--daftar", action="store_true", help="record the run with daftar (provenance)")
    c.add_argument("--fail-on", choices=["sign_unstable", "sorter_dependent", "never"], default="sign_unstable")
    c.set_defaults(fn=cmd_compare)

    h = sub.add_parser("hybrid", help="check ayar on your own recording with injected units of known truth")
    hs = h.add_subparsers(dest="hybrid_cmd", required=True)
    for name, helptext in (("make", "inject known units into a recording and save it"),
                           ("run", "make, sort with a SpikeInterface sorter, and score"),
                           ("score", "score a sorting of a hybrid recording made by `ayar hybrid make`")):
        x = hs.add_parser(name, help=helptext)
        if name == "score":
            x.add_argument("folder", help="the folder written by `ayar hybrid make`")
            x.add_argument("sorting", help="sorter output folder, saved SortingAnalyzer, or ayar .npz")
            x.add_argument("--name", help="a name for the sorting in the report")
        else:
            x.add_argument("recording", help="a SpikeInterface-loadable recording (folder), or a path for --reader")
            x.add_argument("folder", help="output folder")
            x.add_argument("--reader", help="SpikeInterface reader, e.g. spikeglx, openephys, nwb")
            x.add_argument("--stream", help="stream name or id for the reader, e.g. imec0.ap")
            x.add_argument("--units", type=int, default=10, help="injected units (default 10)")
            x.add_argument("--fading", type=int, default=3, help="of which fade over the session (default 3)")
            x.add_argument("--fade-to", type=float, default=0.25, help="final amplitude of fading units")
            x.add_argument("--seed", type=int, default=0)
            x.add_argument("--max-duration", type=float, help="use only the first N seconds")
            if name == "run":
                x.add_argument("--sorter", required=True, help="a SpikeInterface sorter name, e.g. kilosort4")
        if name != "make":
            x.add_argument("--set", action="append", metavar="NAME=VALUE")
            x.add_argument("--format", choices=["text", "json"], default="text")
            x.add_argument("--json", metavar="PATH")
        else:
            x.add_argument("--set", action="append", metavar="NAME=VALUE")
        x.set_defaults(fn=cmd_hybrid)

    v = sub.add_parser("validate", help="measure detector accuracy on synthetic sessions")
    v.add_argument("--sessions", type=int, default=5)
    v.add_argument("--seed", type=int, default=0)
    v.add_argument("--duration", type=float, default=600.0)
    v.add_argument("--min-sensitivity", type=float, default=0.8)
    v.add_argument("--min-precision", type=float, default=0.8)
    v.add_argument("--set", action="append", metavar="NAME=VALUE")
    v.add_argument("--format", choices=["text", "json"], default="text")
    v.set_defaults(fn=cmd_validate)

    se = sub.add_parser("session", help="scan (all and curated units), multiverse and comparison: one report")
    se.add_argument("bundle", help="a .npz bundle, .nwb file, Phy/Kilosort or SortingAnalyzer folder")
    se.add_argument("--finding", help="your analysis: file.py:func or module:func")
    se.add_argument("--keep", action="append", metavar="RULE",
                    help="also scan only units passing RULE, e.g. 'label>=1'; the multiverse and comparison use them")
    se.add_argument("--metrics", help="CSV/TSV of per-unit metrics (for --keep and --grid)")
    se.add_argument("--unit-column", help="unit id column in --metrics (auto-detected)")
    se.add_argument("--grid", action="append", metavar="RULE", help="multiverse rule, e.g. 'presence_ratio>=0.5,0.9'")
    se.add_argument("--no-multiverse", action="store_true", help="skip the multiverse")
    se.add_argument("--compare", nargs="+", metavar="SORTING", help="other sortings of the same recording")
    se.add_argument("--names", nargs="+", help="names: this sorting, then each --compare sorting")
    se.add_argument("--events", help=".npz with 'times' (s) and optional 'labels' arrays")
    se.add_argument("--trial-label", help="NWB: trials-table column holding the condition label")
    se.add_argument("--sample-rate", type=float, help="for Phy folders without params.py")
    se.add_argument("--title", help="page title")
    se.add_argument("--set", action="append", metavar="NAME=VALUE")
    se.add_argument("--format", choices=["text", "json"], default="text")
    se.add_argument("--json", metavar="PATH", help="also write everything as JSON")
    se.add_argument("--html", metavar="PATH", help="write the session report here")
    se.add_argument("--daftar", action="store_true", help="record the run with daftar (provenance)")
    se.add_argument("--fail-on", choices=["error", "warning", "never"], default="error",
                    help="judged on the curated scan when --keep is given")
    se.set_defaults(fn=cmd_session)

    i = sub.add_parser("info", help="summarise a bundle")
    i.add_argument("bundle", help="anything ayar loads; for .nwb files also lists the units table's columns")
    i.set_defaults(fn=cmd_info)

    d = sub.add_parser("doctor", help="check the installation")
    d.set_defaults(fn=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
