# ayar

**Assay your spike-sorted finding before you publish.**

*Ayar* (Persian عیار, Turkish *ayar*, Azerbaijani *əyar*) is the fineness of gold: how much of
it is the real thing. `ayar` asks the same question of a result built on sorted spikes:
how much of it is neuroscience, and how much is the spike sorter?

Tools such as SpikeInterface quality metrics, Bombcell and UnitRefine judge **units**.
`ayar` judges the **finding**. It reads the output of any sorter (Kilosort, MountainSort,
SpyKING CIRCUS, ... via Phy folders or a plain `.npz` bundle), flags sorting artifacts
that can manufacture or hide an effect, then re-computes *your* analysis without the
flagged units and tells you whether your numbers survive.

`ayar` does not sort spikes and does not prove a finding is right. It tests whether
specific, known artifacts can explain it.

```
pip install ayar
```

Python 3.10+, depends only on numpy and scipy, runs on a CPU.

## Thirty seconds

```bash
ayar synth demo.npz                                  # a session with planted artifacts
ayar scan demo.npz --finding ayar.examples:condition_contrast
```

```
ERROR   DRIFT_CONFOUND  unit 16: rate follows detection loss (r=0.94; up to 50% of spikes
                        below threshold in the worst window)
ERROR   DUPLICATE_UNIT  95% of unit 41's spikes have a unit 17 spike within ±0.25 ms (229x
                        chance): likely one neuron counted twice
ERROR   OVERLAP_HOLE    units 42 and 43 fire within ±0.5 ms 13% as often as expected from
                        the 2-10 ms flanks (37 vs 295, p=1.6e-80)
...
finding audit: ayar.examples:condition_contrast
  number                 remove units flagged by    n    baseline   after   change  random-drop q95  verdict
  frac_units_suppressed  DRIFT_CONFOUND             3        0.06       0     100%               6%  SENSITIVE
  mean_contrast_hz       DUPLICATE_UNIT             2       2.277    2.05      10%               8%  ROBUST
  ...
  frac_units_suppressed: SENSITIVE - depends on the flagged units beyond what random removals explain
```

In this synthetic block-design session, every "suppressed" unit was a drifting unit losing
spikes below threshold: there was no suppression at all.

On your own data:

```bash
ayar scan path/to/kilosort_output/ --finding my_analysis.py:main --events events.npz
```

`ayar scan` exits with status 1 when it finds an error-level artifact or a finding that is
SENSITIVE or FLIPPED, so it can gate a pipeline or CI job (`--fail-on warning|never`).

## Your finding is a function

A finding is any function of a bundle that returns a number or a dict of numbers: the
numbers you would put in a paper.

```python
import ayar

def main(bundle):
    trains = bundle.trains()                     # {unit_id: spike times in s}
    ev = bundle.events                           # ev.times, ev.labels
    ...
    return {"decoding_accuracy": acc, "frac_tuned": frac}

report = ayar.scan(ayar.load("kilosort_output/"), finding=main)
print(report)
report.finding_verdicts        # {'decoding_accuracy': 'robust', 'frac_tuned': 'sensitive'}
report.to_json()
```

For each detector that raised flags, `ayar` removes the implicated units (the duplicate
copy, one unit of each hole pair, the drifting unit), recomputes the finding, and compares
the change with **random-drop controls**: the same number of *unflagged* units removed at
random, 20 times. A change counts against the artifact only if it is bigger than what
dropping arbitrary units does.

| verdict | meaning |
|---|---|
| `robust` | changes by less than 10 % |
| `nonspecific` | changes, but no more than random removals (95th percentile) |
| `shifted` | moves beyond random removals, by 10-25 % |
| `sensitive` | moves beyond random removals, by 25 % or more |
| `flipped` | changes sign, which random removals almost never do |
| `failed` | your function raised an error on the reduced bundle |

`ayar.examples` has two finding templates: `condition_contrast` (two-condition rate effect)
and `zero_lag_synchrony` (synchrony between neighbouring units).

## Detectors

| code | needs | what it catches | why it matters |
|---|---|---|---|
| `DUPLICATE_UNIT` | spike times | two units sharing most spikes within ±0.25 ms, far above chance | one neuron counted twice: inflated N, double weight in averages and decoders, fake zero-lag correlation |
| `OVERLAP_HOLE` | spike times (depths restrict to neighbours) | a gap near zero lag in a nearby pair's cross-correlogram, tested against the 2-10 ms flanks (Poisson, Bonferroni) | the sorter dropped overlapping spikes, or one neuron was split in two: synchrony is underestimated |
| `DRIFT_CONFOUND` | amplitudes or depths | firing rate that tracks spike amplitude, depth, or estimated detection loss (amplitude-cutoff per window) over the session | apparent rate changes are spikes lost below threshold; raised to **error** when conditions are ordered in time, because the loss then looks like a condition effect |

Each flag carries a code, a severity, the units, the evidence, why it matters and a fix.
Every threshold is named and can be overridden (`--set dup_window_ms=0.4`, or
`ayar.DEFAULTS.override(...)`). When a check cannot run, or runs on only some units,
`ayar` says so under *not checked* instead of guessing.

## Evidence tiers

* **Tier 0: spike times.** Duplicate and overlap detectors run (all pairs, capped at 20,000
  pairs).
* **Tier 1: plus amplitudes and/or depths.** Pair tests are restricted to neighbouring units
  (100 µm), and the drift detector runs.
* **Tier 2: plus the raw recording** (hybrid ground truth, re-sorting). Planned.

## Input: the bundle

```python
b = ayar.from_phy("kilosort4_output/")            # spike_times/clusters/amplitudes/positions, labels
b = ayar.from_arrays(times_s, clusters, amplitudes=amps, spike_depths=depths,
                     events=ayar.Events(trial_times, trial_labels))
b.save("session.npz")                             # plain npz, readable with numpy alone
```

`from_phy` keeps units labelled `good` or `mua` (curated labels win over Kilosort's), reads
depths from `spike_positions.npy` (Kilosort 4) or `cluster_info.tsv` (Phy), and takes the
sample rate from `params.py`.

## Self-validation

`ayar validate` plants artifacts in synthetic sessions, together with **controls** that
must not be flagged: pairs driven by genuine common input (a real cross-correlogram peak)
and units whose true rate ramps over the session at constant amplitude. Then it scores
every detector.

```
ayar validate --sessions 20 --seed 100

  detector         planted  found  false ctrl alarms sensitivity precision
  DUPLICATE_UNIT        40     40      0           0        1.00      1.00
  OVERLAP_HOLE          40     40      0           0        1.00      1.00
  DRIFT_CONFOUND        60     55      1           0        0.92      0.98

  finding audit: in 19 session(s) drift manufactured 'suppressed' units; ayar called that
  number SENSITIVE or FLIPPED in 19
```

These numbers are measured on ayar's own synthetic data, whose artifacts are cleaner than
real ones. They show that the detectors do what they claim, not how often they fire on real
recordings.

## Limitations (v0.1)

* Research prototype. Thresholds are calibrated on synthetic sessions, not yet on public
  datasets with ground truth.
* Drift is detected per unit from rate-amplitude-depth co-variation. Units with few spikes
  (fewer than ~600) get only the weaker amplitude/depth trend test and are reported as
  partly checked.
* The finding audit removes units; it does not yet repair them (merge duplicates, restrict
  drifting units to their stable epoch).
* `OVERLAP_HOLE` cannot yet tell missed overlaps from a split unit; both are reported.
* The audit calls your function about 20 times per detector. Use `--set audit_controls=0`
  to skip controls when the function is slow.

## Roadmap

* **v0.2**: SpikeInterface `SortingAnalyzer` and NWB adapters; `SPLIT_UNIT` and
  `CONTAMINATION_TUNING` detectors; curation-threshold multiverse.
* **v0.3**: multiverse across sorters (Kilosort 4, MountainSort 5, SpyKING CIRCUS 2) with
  unit matching; single-file HTML report; provenance through
  [daftar](https://pypi.org/project/daftar/).
* **v0.4**: validation on public recordings (IBL, Allen, DANDI).

## Family

`ayar` sits with [daftar](https://pypi.org/project/daftar/) (provenance),
[raftaar](https://pypi.org/project/raftaar/), [tarjuman](https://pypi.org/project/tarjuman/)
(NeuroML to Jaxley), [miras](https://pypi.org/project/miras/) (study-design
identifiability), [baghban](https://pypi.org/project/baghban/) (Bonsai workflow checks) and
[ayna](https://pypi.org/project/ayna/) (are your inferred dynamics real?).

## Author

Aslan Satary Dizaji

## License

Apache 2.0
