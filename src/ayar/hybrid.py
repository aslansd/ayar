"""Tier 2: check ayar on your own recording, with injected units whose answer is known.

ayar's synthetic validation shows the detectors do what they claim on clean,
simulated artifacts. Real tissue is messier. ``ayar hybrid`` answers "how well does
ayar work on *my* probe, brain region and sorter?":

1. ``make``: inject known units into your recording (SpikeInterface's hybrid
   generator). Some injected units *fade*: their amplitude falls over the session,
   so the sorter loses their late spikes, the way a drifting neuron is lost.
2. Sort the hybrid recording with your own pipeline (or let ``run`` call a sorter).
3. ``score``: scan the sorting and check every flag that touches an injected unit
   against the known truth, and report what the sorter did to each injected unit
   (found, split, merged, missed) and whether ayar caught it.

Only injected units have a known answer, so only flags on units that are mostly
injected spikes are scored; the recording's own neurons are left alone.
Needs ``pip install "ayar[spikeinterface]"``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import __version__
from .bundle import Bundle
from .config import DEFAULTS, Thresholds
from .matching import coincidence_matrix

PURITY = 0.8  # a sorted unit "belongs" to an injected unit if this share of its spikes are that unit's


def _si():
    try:
        import spikeinterface.full as si
    except ImportError as e:  # pragma: no cover - depends on environment
        raise ImportError('ayar hybrid needs SpikeInterface: pip install "ayar[spikeinterface]"') from e
    return si


def load_recording(path: str | Path, reader: str | None = None, stream: str | None = None):
    """A SpikeInterface recording from a saved folder (``si.load``) or a named reader."""
    si = _si()
    if reader:
        fn = getattr(si, f"read_{reader}", None)
        if fn is None:
            raise ValueError(f"SpikeInterface has no reader read_{reader}")
        kw = {}
        if stream:
            kw["stream_name" if not stream.isdigit() else "stream_id"] = stream
        return fn(str(path), **kw)
    return si.load(str(path))


# --------------------------------------------------------------------- make
def make(
    recording,
    folder: str | Path,
    *,
    n_units: int = 10,
    n_fading: int = 3,
    fade_to: float = 0.25,
    firing_rate: tuple[float, float] = (4.0, 12.0),
    seed: int = 0,
    max_duration: float | None = None,
) -> Path:
    """Inject ``n_units`` known units into ``recording`` and save the result in ``folder``.

    The first ``n_fading`` injected units fade linearly to ``fade_to`` of their amplitude
    by the end of the session. Writes ``folder/recording`` (SpikeInterface binary folder),
    ``folder/injected.npz`` (the injected spike trains as an ayar bundle) and
    ``folder/hybrid.json`` (what was injected).
    """
    si = _si()
    from spikeinterface.core import generate_sorting
    from spikeinterface.generation import generate_hybrid_recording

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if recording.get_num_segments() != 1:
        raise ValueError("hybrid needs a single-segment recording")
    if max_duration is not None and recording.get_total_duration() > max_duration:
        recording = recording.frame_slice(0, int(max_duration * recording.sampling_frequency))
    fs = recording.sampling_frequency
    T = recording.get_total_duration()
    rng = np.random.default_rng(seed)
    rates = rng.uniform(*firing_rate, n_units)
    sorting = generate_sorting(num_units=n_units, sampling_frequency=fs, durations=[T],
                               firing_rates=rates, refractory_period_ms=2.0, seed=seed)
    sv = sorting.to_spike_vector()
    t = sv["sample_index"] / fs
    amp = 1.0 + 0.05 * rng.standard_normal(sv.size)
    fading = list(range(min(n_fading, n_units)))
    for k in fading:
        sel = sv["unit_index"] == k
        amp[sel] *= 1.0 - (1.0 - fade_to) * t[sel] / T
    hybrid_rec, injected = generate_hybrid_recording(recording, sorting=sorting, amplitude_factor=amp,
                                                     seed=seed)
    hybrid_rec.save(folder=folder / "recording", overwrite=True, verbose=False)
    from .io import from_spikeinterface

    truth = from_spikeinterface(injected, duration=T)
    truth.meta.update({"source": "ayar.hybrid", "fading": [int(truth.unit_ids[k]) for k in fading]})
    truth.save(folder / "injected.npz")
    info = {
        "ayar_version": __version__, "n_units": n_units, "fading_units": truth.meta["fading"],
        "fade_to": fade_to, "firing_rates_hz": [round(float(r), 3) for r in rates], "seed": seed,
        "duration_s": T, "sampling_frequency": fs,
    }
    (folder / "hybrid.json").write_text(json.dumps(info, indent=2))
    return folder


# -------------------------------------------------------------------- score
@dataclass
class InjectedUnit:
    unit: int
    fading: bool
    status: str  # found, partial, split, merged, missed
    pieces: list[int]
    best_agreement: float
    caught: str | None = None  # how ayar reported a split or fade, if it did
    split_flagged: bool = False
    drift_flagged: bool = False


@dataclass
class FlagCheck:
    code: str
    units: list[int]
    severity: str
    verdict: str  # correct, wrong, unscored
    detail: str


@dataclass
class HybridScore:
    sorting: str
    n_sorted_units: int
    injected: list[InjectedUnit]
    flags: list[FlagCheck]
    notes: list[str] = field(default_factory=list)
    version: str = __version__

    def counts(self) -> dict[str, Any]:
        f = [c for c in self.flags if c.verdict != "unscored"]
        by_code: dict[str, dict[str, int]] = {}
        for c in f:
            d = by_code.setdefault(c.code, {"correct": 0, "wrong": 0})
            d[c.verdict] += 1
        split = [u for u in self.injected if u.status == "split"]
        fading = [u for u in self.injected if u.fading and u.pieces]
        return {
            "injected": len(self.injected),
            "status": {s: sum(u.status == s for u in self.injected)
                       for s in ("found", "partial", "split", "merged", "missed")},
            "flags_scored": len(f),
            "flags_correct": sum(c.verdict == "correct" for c in f),
            "by_code": by_code,
            "splits_caught": [sum(u.split_flagged for u in split), len(split)],
            "fades_caught": [sum(u.drift_flagged for u in fading), len(fading)],
            "fades_caught_as_split": sum(u.split_flagged and not u.drift_flagged for u in fading),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"ayar_version": self.version, "sorting": self.sorting, "n_sorted_units": self.n_sorted_units,
                "counts": self.counts(), "injected": [asdict(u) for u in self.injected],
                "flags": [asdict(c) for c in self.flags], "notes": self.notes}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=float)

    def format_text(self) -> str:
        c = self.counts()
        st = c["status"]
        lines = [
            f"ayar {self.version} hybrid score: {self.sorting} ({self.n_sorted_units} sorted units)",
            "",
            f"what the sorter did to the {c['injected']} injected units: {st['found']} found, "
            f"{st['partial']} partly found, {st['split']} split, {st['merged']} merged with other spikes, "
            f"{st['missed']} missed",
            "",
            f"  {'injected':>8}  {'fading':>6}  {'status':<7}  {'sorted unit(s)':<16}  {'agreement':>9}  ayar",
        ]
        for u in self.injected:
            lines.append(f"  {u.unit:>8}  {'yes' if u.fading else '':>6}  {u.status:<7}  "
                         f"{', '.join(map(str, u.pieces)) or '-':<16}  {u.best_agreement:>9.2f}  {u.caught or ''}")
        lines.append("")
        if c["flags_scored"]:
            lines.append(f"flags on injected units: {c['flags_correct']} of {c['flags_scored']} correct")
            for code, d in sorted(c["by_code"].items()):
                lines.append(f"  {code:<16} {d['correct']} correct, {d['wrong']} wrong")
        else:
            lines.append("no flag touched an injected unit")
        sc, sn = c["splits_caught"]
        fc, fn = c["fades_caught"]
        lines.append("")
        extra = c["fades_caught_as_split"]
        lines.append(f"sensitivity: {sc} of {sn} split injected units flagged as split or duplicate; {fc} of {fn} "
                     "fading injected units the sorter kept flagged as drifting"
                     + (f" (and {extra} more caught as a split: the sorter started a new unit as it faded)"
                        if extra else ""))
        wrong = [f for f in self.flags if f.verdict == "wrong"]
        for f in wrong:
            lines.append(f"  wrong: {f.code} {f.units}: {f.detail}")
        for n in self.notes:
            lines.append(f"  note: {n}")
        return "\n".join(lines)


def score(sorted_bundle: Bundle, truth: Bundle, *, report=None, thresholds: Thresholds | None = None,
          name: str = "sorting") -> HybridScore:
    """Score a sorting of a hybrid recording against the injected truth."""
    from .scan import scan

    th = thresholds or DEFAULTS
    if report is None:
        report = scan(sorted_bundle, thresholds=th)
    fading = set(truth.meta.get("fading", []))
    cm = coincidence_matrix(sorted_bundle, truth, th.cmp_delta_ms / 1000.0)
    n_s = np.array([sorted_bundle.spike_indices(u).size for u in sorted_bundle.unit_ids], dtype=float)
    n_t = np.array([truth.spike_indices(u).size for u in truth.unit_ids], dtype=float)
    s_index = {int(u): i for i, u in enumerate(sorted_bundle.unit_ids)}

    owner: dict[int, tuple[int, float]] = {}  # sorted unit -> (injected unit, purity), if it belongs to one
    for i, u in enumerate(sorted_bundle.unit_ids):
        if n_s[i] == 0 or cm.shape[1] == 0:
            continue
        j = int(np.argmax(cm[i]))
        purity = cm[i, j] / n_s[i]
        if purity >= PURITY:
            owner[int(u)] = (int(truth.unit_ids[j]), float(purity))

    flags = report.flags
    injected: list[InjectedUnit] = []
    for j, tu in enumerate(truth.unit_ids):
        tu = int(tu)
        pieces = sorted(u for u, (o, _) in owner.items() if o == tu)
        agr = cm[:, j] / np.maximum(n_s + n_t[j] - cm[:, j], 1)
        best = float(agr.max()) if agr.size else 0.0
        if len(pieces) >= 2:
            status = "split"
        elif pieces and best >= 0.8:
            status = "found"
        elif pieces:
            status = "partial"  # one clean unit holds it, but the sorter lost part of its spikes
        elif cm.size and cm[:, j].max() >= 0.5 * n_t[j]:
            status = "merged"  # most of its spikes sit in a unit dominated by other spikes
        else:
            status = "missed"
        caught, split_hit, drift_hit = None, False, False
        if status == "split":
            ps = set(pieces)
            hits = [f for f in flags if f.code in ("SPLIT_UNIT", "DUPLICATE_UNIT") and set(f.units[:2]) <= ps]
            if hits:
                split_hit = True
                caught = ", ".join(sorted({f.code for f in hits}))
        if pieces:
            hits = [f for f in flags if f.code == "DRIFT_CONFOUND" and f.units[0] in pieces]
            if hits:
                drift_hit = True
                caught = (caught + "; " if caught else "") + "DRIFT_CONFOUND"
        injected.append(InjectedUnit(tu, tu in fading, status, pieces, round(best, 3), caught, split_hit, drift_hit))

    checks: list[FlagCheck] = []
    for f in flags:
        us = [int(u) for u in f.units]
        own = [owner.get(u) for u in us]
        verdict, detail = "unscored", "no unit of this flag is mostly injected spikes"
        if f.code in ("SPLIT_UNIT", "DUPLICATE_UNIT"):
            a, b = us[:2]
            oa, ob = owner.get(a), owner.get(b)
            if oa and ob:
                verdict = "correct" if oa[0] == ob[0] else "wrong"
                detail = f"injected units {oa[0]} and {ob[0]}"
            elif oa or ob:
                o, other = (oa, b) if oa else (ob, a)
                share = cm[s_index[other], list(truth.unit_ids).index(o[0])] / max(n_s[s_index[other]], 1)
                if share < 0.2:
                    verdict, detail = "wrong", f"unit {other} is not injected unit {o[0]} ({share:.0%} shared)"
                else:
                    detail = f"unit {other} partly holds injected unit {o[0]} ({share:.0%})"
        elif f.code == "DRIFT_CONFOUND" and own[0]:
            o = own[0][0]
            verdict = "correct" if o in fading else "wrong"
            detail = f"injected unit {o} {'fades' if o in fading else 'does not fade'}"
        elif f.code == "CONTAMINATION" and own[0]:
            purity = own[0][1]
            verdict = "correct" if purity < 0.95 else "wrong"
            detail = f"{purity:.0%} of the unit's spikes are injected unit {own[0][0]}"
        elif f.code == "OVERLAP_HOLE" and own[0] and own[1]:
            # injected spike trains are independent of each other: a hole between two of them is the sorter's
            verdict = "correct" if own[0][0] != own[1][0] else "wrong"
            detail = (f"injected units {own[0][0]} and {own[1][0]}: independent trains, so the hole is the sorter's"
                      if own[0][0] != own[1][0] else "both halves of one injected unit: a split, not a hole")
        checks.append(FlagCheck(f.code, us, f.severity.value, verdict, detail))

    notes = []
    if not owner:
        notes.append("no sorted unit is mostly injected spikes: did the sorter run on the hybrid recording?")
    return HybridScore(name, sorted_bundle.n_units, injected, checks, notes)


def bundle_from_sorting(sorting, recording) -> Bundle:
    """A tier-1 bundle (amplitudes, depths) from a sorting of the hybrid recording."""
    si = _si()
    from .io import from_spikeinterface

    an = si.create_sorting_analyzer(sorting, recording, sparse=True, format="memory")
    an.compute(["random_spikes", "templates", "spike_amplitudes", "spike_locations", "unit_locations"],
               verbose=False)
    return from_spikeinterface(an)


def score_folder(folder: str | Path, sorting_path: str | Path, *, name: str | None = None,
                 thresholds: Thresholds | None = None) -> HybridScore:
    """Score a sorting (any loadable source) of the hybrid recording saved in ``folder``."""
    si = _si()
    folder = Path(folder)
    truth = Bundle.load(folder / "injected.npz")
    sp = Path(sorting_path)
    if sp.suffix == ".npz":
        sorted_bundle = Bundle.load(sp)
    else:
        try:
            sorting = si.read_sorter_folder(sp)
        except Exception:
            sorting = si.load(sp)
        if hasattr(sorting, "get_extension"):  # a saved analyzer
            from .io import from_spikeinterface

            sorted_bundle = from_spikeinterface(sorting)
        else:
            sorted_bundle = bundle_from_sorting(sorting, si.load(folder / "recording"))
    return score(sorted_bundle, truth, thresholds=thresholds, name=name or sp.name)


def run(
    recording,
    folder: str | Path,
    sorter: str | Callable,
    *,
    sorter_kwargs: dict | None = None,
    thresholds: Thresholds | None = None,
    **make_kwargs,
) -> HybridScore:
    """make + sort (a SpikeInterface sorter name, or ``f(recording) -> sorting``) + score."""
    si = _si()
    folder = Path(make(recording, folder, **make_kwargs))
    hybrid_rec = si.load(folder / "recording")
    if callable(sorter):
        sorting, name = sorter(hybrid_rec), getattr(sorter, "__name__", "sorter")
    else:
        sorting = si.run_sorter(sorter, hybrid_rec, folder=folder / f"sorted_{sorter}",
                                remove_existing_folder=True, verbose=False, **(sorter_kwargs or {}))
        name = sorter
    sorted_bundle = bundle_from_sorting(sorting, hybrid_rec)
    sorted_bundle.save(folder / f"sorted_{name}.npz")
    return score(sorted_bundle, Bundle.load(folder / "injected.npz"), thresholds=thresholds, name=name)
