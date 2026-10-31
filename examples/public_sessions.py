"""Run ayar on public IBL and DANDI sessions and write the results as RESULTS.md.

Downloads one public IBL probe insertion (through IBL's public server, openalyx)
and one session of a public DANDI dataset (by default the Steinmetz et
al. 2019 Neuropixels dataset, dandiset 000017). For each, it runs

* ``ayar scan`` with a finding (feedback: correct vs error trials, when the
  session has trials) and the finding audit,
* ``ayar multiverse`` over the default curation grid (plus IBL's own quality
  label for the IBL session),

and writes, in ``--out``:

* ``RESULTS.md``: a summary of everything below, ready to read or to paste,
* ``<session>_scan.html`` / ``_multiverse.html``: the reports with the evidence,
* ``<session>_scan.json`` / ``_multiverse.json`` / ``_curation.json``.

Needs internet access to openalyx.internationalbrainlab.org and dandiarchive.org.
IBL's public server now needs a free personal account (register at
https://openalyx.internationalbrainlab.org/signup); DANDI needs none:

    pip install "ayar[nwb]" ONE-api ibllib dandi
    export OPENALYX_USER=<your user> OPENALYX_PASSWORD=<your password>
    python examples/public_sessions.py --out public_results

Downloads about 0.5-1 GB. Takes a few minutes on a laptop.
Already downloaded? ``--ibl-local ALF_FOLDER [--ibl-trials TRIALS_FOLDER]`` and
``--nwb-local FILE.nwb`` skip the downloads.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import ayar
from ayar import html
from ayar.curation import write_spikeinterface
from ayar.examples import condition_contrast
from ayar.multiverse import DEFAULT_GRID, Rule

# The insertion IBL itself uses in its open-data integration test
# (ibllib/tests/integration/test_open_alyx.py).
IBL_PID = "da8dfec1-d265-44e8-84ce-6ae9c109b8bd"
DANDISET = "000017"  # Steinmetz et al. 2019, Nature: Neuropixels, units + trials
OPENALYX = "https://openalyx.internationalbrainlab.org"


# ------------------------------------------------------------------ loading
def load_ibl(pid: str, cache: Path, event: str):
    from brainbox.io.one import SessionLoader, SpikeSortingLoader
    from one.api import ONE

    user, password = os.getenv("OPENALYX_USER"), os.getenv("OPENALYX_PASSWORD")
    if not user or not password:
        raise RuntimeError(
            "IBL's public server needs a (free) personal account: register at "
            f"{OPENALYX}/signup, then set OPENALYX_USER and OPENALYX_PASSWORD and run again "
            "(or pass --skip-ibl)")
    one = ONE(base_url=OPENALYX, silent=True, cache_dir=str(cache), username=user, password=password)
    ssl = SpikeSortingLoader(pid=pid, one=one)
    spikes, clusters, channels = ssl.load_spike_sorting()
    if not spikes:
        spikes, clusters, channels = ssl.load_spike_sorting(spike_sorter="pykilosort")
    clusters = SpikeSortingLoader.merge_clusters(spikes, clusters, channels)
    eid, probe = one.pid2eid(pid)
    trials = None
    try:
        sl = SessionLoader(one=one, eid=eid)
        sl.load_trials()
        trials = sl.trials
    except Exception as e:  # sessions without a trials table still get scanned
        print(f"  no trials for {eid}: {e}")
    b = ayar.from_ibl(spikes, clusters, trials, event=event if trials is not None else None,
                      meta={"pid": pid, "eid": str(eid), "probe": probe})
    info = {
        "title": f"IBL insertion {pid}",
        "source": f"IBL public data ({OPENALYX}), insertion {pid}, session {eid}, {probe}",
        "link": f"{OPENALYX}/insertions/{pid}",
        "events": f"feedback: correct (1) vs error (-1) trials" if b.events is not None else None,
    }
    metrics = ayar.io.ibl_metrics(clusters)
    return b, metrics, info


def _pick_trial_columns(path: Path):
    """A two-valued trial column to compare (feedback/reward/response...) and its time column."""
    import pynwb

    with pynwb.NWBHDF5IO(str(path), "r") as io:
        nwb = io.read()
        tr = nwb.trials
        if tr is None or len(tr) == 0:
            return None, None
        cols = list(tr.colnames)
        two = []
        for c in cols:
            try:
                v = np.asarray(tr[c][:])
            except Exception:
                continue
            if v.ndim != 1:
                continue
            vals = [x for x in np.unique(v.astype(str)) if x not in ("nan", "", "None")]
            if len(vals) == 2:
                two.append(c)
        prefer = ("feedback", "reward", "correct", "response", "choice", "outcome")
        label = next((c for p in prefer for c in two if p in c.lower()), two[0] if two else None)
        times = [c for c in cols if c.endswith(("_time", "_times")) and c not in ("start_time", "stop_time")]
        tcol = next((c for p in ("feedback", "reward", "response", "go_cue", "stim") for c in times
                     if p in c.lower()), "start_time")
        return label, tcol


def load_dandi(dandiset: str, asset_path: str | None, max_gb: float, cache: Path, local: Path | None):
    if local is None:
        from dandi.dandiapi import DandiAPIClient

        with DandiAPIClient() as client:
            ds = client.get_dandiset(dandiset)
            assets = [a for a in ds.get_assets() if a.path.endswith(".nwb")]
            if asset_path:
                assets = [a for a in assets if a.path == asset_path]
                if not assets:
                    raise SystemExit(f"{asset_path} is not in dandiset {dandiset}")
            else:
                ok = sorted((a for a in assets if 50e6 <= a.size <= max_gb * 1e9), key=lambda a: a.size)
                if not ok:
                    raise SystemExit(f"no NWB file between 50 MB and {max_gb} GB in dandiset {dandiset}")
                assets = ok
            asset = assets[0]
            local = cache / "dandi" / dandiset / asset.path
            local.parent.mkdir(parents=True, exist_ok=True)
            if not local.exists():
                print(f"  downloading {asset.path} ({asset.size / 1e6:.0f} MB)")
                asset.download(local)
            name = asset.path
    else:
        name = local.name
    label, tcol = _pick_trial_columns(local)
    kw = {"shift_negative": True}
    if label:
        kw.update(trial_label=label, event_time_column=tcol)
    b = ayar.from_nwb(local, **kw)
    info = {
        "title": f"DANDI {dandiset}: {name}",
        "source": f"DANDI Archive, dandiset {dandiset}, file {name}",
        "link": f"https://dandiarchive.org/dandiset/{dandiset}",
        "events": f"trials column '{label}' at '{tcol}'" if label else None,
    }
    return b, {}, info


# ----------------------------------------------------------------- analysis
def rate_finding(bundle):
    r = np.array([bundle.rate(u) for u in bundle.unit_ids])
    return {"mean_rate_hz": float(r.mean()), "frac_units_above_1hz": float(np.mean(r > 1.0))}


def analyse(key: str, bundle, metrics: dict, info: dict, out: Path, multiverse: bool) -> dict:
    two_conditions = bundle.events is not None and bundle.events.labels is not None and \
        bundle.events.label_values.size == 2
    finding = condition_contrast if two_conditions else rate_finding
    fname = "condition_contrast (0-0.5 s after each event)" if two_conditions else "firing rates"
    res = {"key": key, **info, "summary": bundle.summary(), "finding": fname}
    if two_conditions:
        res["condition_counts"] = {str(v): int(np.sum(bundle.events.labels == v))
                                   for v in bundle.events.label_values}

    t = time.time()
    rep = ayar.scan(bundle, finding, finding_name=fname)
    res["scan_s"] = round(time.time() - t, 1)
    (out / f"{key}_scan.json").write_text(rep.to_json())
    html.write(out / f"{key}_scan.html", html.scan_html(rep, bundle))
    write_spikeinterface(rep, bundle, out / f"{key}_curation.json")
    res["scan"] = rep.to_dict()

    if multiverse:
        grid = list(DEFAULT_GRID)
        if "label" in metrics:
            grid.append(Rule("label", ">=", [0.0, 0.6, 1.0]))  # IBL quality: 1 = passes all 3 IBL criteria
        t = time.time()
        mv = ayar.multiverse(bundle, finding, grid, metrics=metrics, finding_name=fname)
        res["multiverse_s"] = round(time.time() - t, 1)
        (out / f"{key}_multiverse.json").write_text(mv.to_json())
        html.write(out / f"{key}_multiverse.html", html.multiverse_html(mv))
        res["multiverse"] = mv.to_dict()
    return res


# ------------------------------------------------------------------ report
def _f(x):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if not np.isfinite(x):
            return "n/a"
        return f"{x:.4g}"
    return str(x)


def session_md(r: dict) -> str:
    s, sc = r["summary"], r["scan"]
    L = [f"## {r['title']}", "", f"- **Source:** {r['source']} ([link]({r['link']}))",
         f"- **Data:** {s['n_units']} units, {s['n_spikes']:,} spikes, {s['duration_s']:g} s, tier {s['tier']} "
         f"({'amplitudes' if s['amplitudes'] else 'no amplitudes'}, {'depths' if s['depths'] else 'no depths'})",
         f"- **Events:** {r['events'] or 'none (the finding is firing rates)'}"
         + (f"; {', '.join(f'{k}: {v}' for k, v in r['condition_counts'].items())} trials"
            if r.get("condition_counts") else ""),
         f"- **Run time:** scan + audit {r['scan_s']} s" + (f", multiverse {r['multiverse_s']} s" if "multiverse_s" in r else ""),
         ""]
    flags = sc["flags"]
    L += ["### Sorting artifacts flagged", ""]
    if not flags:
        L += ["None.", ""]
    else:
        codes = sorted({f["code"] for f in flags})
        L += ["| detector | errors | warnings | units involved |", "|---|---|---|---|"]
        for c in codes:
            fl = [f for f in flags if f["code"] == c]
            units = {u for f in fl for u in f["units"]}
            L.append(f"| `{c}` | {sum(f['severity'] == 'error' for f in fl)} | "
                     f"{sum(f['severity'] == 'warning' for f in fl)} | {len(units)} |")
        n_flagged = len({u for f in flags for u in f["units"]})
        L += ["", f"{n_flagged} of {s['n_units']} units are involved in at least one flag.", "",
              "Examples (up to three per detector):", ""]
        for c in codes:
            for f in [f for f in flags if f["code"] == c][:3]:
                msg = f["message"]
                for u in f["units"]:  # the message often starts with "unit N: " already
                    if msg.startswith(f"unit {u}: "):
                        msg = msg[len(f"unit {u}: "):]
                L.append(f"- `{c}` ({f['severity']}), units {', '.join(map(str, f['units']))}: {msg}")
        L.append("")
    if sc["not_checked"]:
        L += ["Not checked, or only partly:", ""]
        L += [f"- `{n['code']}`: {n['reason']}" for n in sc["not_checked"]]
        L.append("")

    fd = sc.get("finding")
    if fd and fd.get("audit") is not None:
        L += [f"### Finding audit: {r['finding']}", ""]
        verdicts = sc["summary"]["finding_verdicts"]
        if not fd["audit"]:
            L += ["Nothing to repair.", ""]
        else:
            L += ["| number | baseline | verdict | largest change from a repair (vs random 95th pct) |",
                  "|---|---|---|---|"]
            for key, base in fd["baseline"].items():
                rows = [a for a in fd["audit"] if a["key"] == key and a["rel_change"] is not None]
                big = max(rows, key=lambda a: a["rel_change"] if np.isfinite(a["rel_change"]) else -1, default=None)
                ctrl = "" if big is None or big["control_q"] is None else f" (random {big['control_q']:.0%})"
                eff = f"{big['ablation']} ({big['action']}): {big['rel_change']:.0%}{ctrl}" if big else ""
                L.append(f"| `{key}` | {_f(base)} | **{verdicts.get(key, 'n/a')}** | {eff} |")
            L.append("")

    mv = r.get("multiverse")
    if mv:
        L += ["### Curation multiverse", "",
              f"{mv['counts']['evaluated']} of {mv['counts']['universes']} universes evaluated "
              f"(grid: `{'  '.join(mv['grid'])}`).", "",
              "| number | all units | min | median | max | same sign | verdict | most influential threshold |",
              "|---|---|---|---|---|---|---|---|"]
        for k in mv["summaries"]:
            infl = max(k["influence"], key=k["influence"].get) if k["influence"] else "n/a"
            L.append(f"| `{k['key']}` | {_f(k['baseline'])} | {_f(k['minimum'])} | {_f(k['median'])} | "
                     f"{_f(k['maximum'])} | {k['sign_agreement']:.0%} | **{k['verdict']}** | {infl} |")
        L += [""] + [f"- note: {n}" for n in mv["notes"]] + ([""] if mv["notes"] else [])

    L += ["### Files", "", f"- [{r['key']}_scan.html]({r['key']}_scan.html): every flag with its evidence plot",
          f"- [{r['key']}_curation.json]({r['key']}_curation.json): the repairs as a SpikeInterface curation"]
    if mv:
        L.append(f"- [{r['key']}_multiverse.html]({r['key']}_multiverse.html): the specification curves")
    L.append("")
    return "\n".join(L)


def write_md(results: list[dict], failures: dict, out: Path, argv: str) -> Path:
    vers = {"ayar": ayar.__version__, "python": platform.python_version(), "numpy": np.__version__}
    for mod in ("spikeinterface", "pynwb", "one", "ibllib", "dandi"):
        try:
            vers[mod] = __import__(mod).__version__
        except Exception:
            pass
    L = ["# ayar on public sessions", "",
         f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by "
         f"`examples/public_sessions.py` with ayar {ayar.__version__}.", "",
         "## Summary", ""]
    if results:
        L += ["| session | units | flags (errors / warnings) | finding audit | curation multiverse |",
              "|---|---|---|---|---|"]
        for r in results:
            sc = r["scan"]
            fv = ", ".join(f"{k}: {v}" for k, v in sc["summary"]["finding_verdicts"].items()) or "nothing to repair"
            mv = ", ".join(f"{k['key']}: {k['verdict']}" for k in r["multiverse"]["summaries"]) if r.get("multiverse") else "not run"
            L.append(f"| {r['title']} | {r['summary']['n_units']} | {sc['summary']['errors']} / "
                     f"{sc['summary']['warnings']} | {fv} | {mv} |")
        L.append("")
    for k, err in failures.items():
        L += [f"- **{k} failed:** `{err.strip().splitlines()[-1]}`", ""]
    L += ["## How to read this", "",
          "These sessions have no ground truth. A flag is a hypothesis about the sorting, with the",
          "evidence plotted in the HTML report; the finding audit says whether the example finding",
          "would change if the flagged units were repaired, and the multiverse whether it depends on",
          "curation thresholds. The example finding (a two-condition rate contrast) stands in for a",
          "real analysis; with your own finding the same machinery applies.", ""]
    L += [session_md(r) for r in results]
    L += ["## Reproduce", "", "```", f"python examples/public_sessions.py {argv}".rstrip(), "```", "",
          "Versions: " + ", ".join(f"{k} {v}" for k, v in vers.items()), ""]
    path = out / "RESULTS.md"
    path.write_text("\n".join(L))
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", default="public_results")
    p.add_argument("--cache", default=None, help="download cache (default: OUT/cache)")
    p.add_argument("--ibl-pid", default=IBL_PID, help="IBL probe insertion id")
    p.add_argument("--ibl-event", default="feedback", choices=["feedback", "stimulus", "choice"])
    p.add_argument("--ibl-local", help="read IBL/ALF spikes from this folder instead of downloading")
    p.add_argument("--ibl-trials", help="ALF folder with trials.*.npy, for --ibl-local")
    p.add_argument("--dandiset", default=DANDISET)
    p.add_argument("--dandi-asset", help="path of the NWB file in the dandiset (default: the smallest one)")
    p.add_argument("--max-gb", type=float, default=1.0, help="largest NWB file to download (default 1 GB)")
    p.add_argument("--nwb-local", help="read this NWB file instead of downloading")
    p.add_argument("--skip-ibl", action="store_true")
    p.add_argument("--skip-dandi", action="store_true")
    p.add_argument("--no-multiverse", action="store_true")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache) if args.cache else out / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    results, failures = [], {}
    jobs = []
    if not args.skip_ibl:
        jobs.append(("ibl", lambda: (ayar.from_alf(args.ibl_local, trials_folder=args.ibl_trials, event=args.ibl_event),
                                     {}, {"title": f"IBL (local) {args.ibl_local}", "source": f"local ALF folder {args.ibl_local}",
                                          "link": OPENALYX, "events": "feedback: correct vs error" if args.ibl_trials else None})
                     if args.ibl_local else load_ibl(args.ibl_pid, cache, args.ibl_event)))
    if not args.skip_dandi:
        jobs.append(("dandi", lambda: load_dandi(args.dandiset, args.dandi_asset, args.max_gb, cache,
                                                 Path(args.nwb_local) if args.nwb_local else None)))
    for key, loader in jobs:
        print(f"== {key}: loading")
        try:
            bundle, metrics, info = loader()
            if key == "ibl" and not metrics:
                metrics = {k: {int(u): v for u, v in d.items()} for k, d in bundle.meta.get("ibl_metrics", {}).items()}
            print(f"   {bundle}; analysing")
            results.append(analyse(key, bundle, metrics, info, out, not args.no_multiverse))
            print(f"   done: {results[-1]['scan']['summary']}")
        except SystemExit:
            raise
        except Exception:
            failures[key] = traceback.format_exc()
            print(failures[key])
    argv = " ".join(a for a in os.sys.argv[1:])
    path = write_md(results, failures, out, argv)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
