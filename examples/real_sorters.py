"""Run ayar on the output of real spike sorters, checked against ground truth.

Simulates a 32-channel recording with SpikeInterface (12 neurons, known spike
trains), sorts it with tridesclous2, spykingcircus2 and mountainsort5 at their
default settings, then:

1. scans each sorting with ``ayar scan`` and checks every flag against the truth
   (which neuron each sorted unit really belongs to), and
2. compares the sortings with ``ayar compare``, using the truth as reference.

Needs:  pip install "ayar[spikeinterface]" "spikeinterface[tridesclous2,spykingcircus2]" mountainsort5
Takes a few minutes on a laptop CPU.

    python examples/real_sorters.py [--duration 120] [--out real_sorters]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

import ayar
from ayar.compare import compare
from ayar.matching import coincidence_matrix

SORTERS = ["tridesclous2", "spykingcircus2", "mountainsort5"]


def truth_of(bundle, truth, purity=0.8):
    """Sorted unit -> (truth neuron it mostly belongs to, share of its spikes)."""
    cm = coincidence_matrix(bundle, truth)
    n = np.array([bundle.spike_indices(u).size for u in bundle.unit_ids])
    out = {}
    for i, u in enumerate(bundle.unit_ids):
        j = int(cm[i].argmax())
        out[int(u)] = (int(truth.unit_ids[j]), float(cm[i, j] / max(n[i], 1)))
    return out


def judge(flag, owner):
    """Is a flag right, given which neuron each unit belongs to?"""
    if flag.code in ("DUPLICATE_UNIT", "SPLIT_UNIT"):
        a, b = flag.units[:2]
        if owner[a][0] == owner[b][0]:
            return f"correct (both neuron {owner[a][0]})"
        return (f"different neurons: unit {a} is {owner[a][1]:.0%} neuron {owner[a][0]}, "
                f"unit {b} is {owner[b][1]:.0%} neuron {owner[b][0]}")
    if flag.code == "CONTAMINATION":
        u = flag.units[0]
        return f"unit is {owner[u][1]:.0%} one neuron"
    if flag.code == "OVERLAP_HOLE":
        a, b = flag.units[:2]
        return "different neurons" if owner[a][0] != owner[b][0] else "same neuron"
    return ""


def main() -> None:
    import spikeinterface.full as si

    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=float, default=120.0)
    p.add_argument("--out", default="real_sorters")
    p.add_argument("--reuse", action="store_true",
                   help="read existing sorter output in --out instead of sorting again")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(exist_ok=True)

    rec, gt = si.generate_ground_truth_recording(durations=[args.duration], num_units=12, seed=1,
                                                 num_channels=32)
    if args.reuse and (out / "recording").exists():
        rec = si.load(out / "recording")
    else:
        rec = si.common_reference(si.bandpass_filter(rec))
        rec = rec.save(folder=out / "recording", overwrite=True, verbose=False)

    def to_bundle(sorting):
        an = si.create_sorting_analyzer(sorting, rec, sparse=True, format="memory")
        an.compute(["random_spikes", "templates", "spike_amplitudes", "spike_locations", "unit_locations"],
                   verbose=False)
        return ayar.from_spikeinterface(an)

    bundles = {"truth": to_bundle(gt)}
    for name in SORTERS:
        if args.reuse and (out / name).exists():
            s = si.read_sorter_folder(out / name)
        else:
            s = si.run_sorter(name, rec, folder=out / name, remove_existing_folder=True, verbose=False)
        well = len(si.compare_sorter_to_ground_truth(gt, s).get_well_detected_units(0.8))
        print(f"{name}: {len(s.unit_ids)} units, {well} of {len(gt.unit_ids)} neurons well detected")
        bundles[name] = to_bundle(s)

    truth = bundles["truth"]
    for name, b in bundles.items():
        owner = truth_of(b, truth)
        pieces = defaultdict(list)
        for u, (t, share) in owner.items():
            if share >= 0.8:
                pieces[t].append(u)
        split = {t: us for t, us in pieces.items() if len(us) > 1}
        rep = ayar.scan(b)
        print(f"\n== {name}: {b.n_units} units, {len(rep.flags)} flags"
              + (f"; neurons really split: {split}" if split else ""))
        for f in rep.flags:
            print(f"  {f.code:<15} units {f.units}: {judge(f, owner)}")
        for n in rep.not_checked:
            print(f"  ({'partly checked' if n.partial else 'not checked'}: {n.code}: {n.reason})")

    def rates(b):
        r = np.array([b.rate(u) for u in b.unit_ids])
        return {"n_units": float(b.n_units), "mean_rate_hz": float(r.mean())}

    print()
    print(compare(bundles, rates).format_text())
    print()
    print(compare(bundles, ayar.examples.zero_lag_synchrony).format_text())


if __name__ == "__main__":
    main()
