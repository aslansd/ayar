# ayar

**Assay your spike-sorted finding before you publish.**

*Ayar* (Persian عیار, Turkish *ayar*, Azerbaijani *əyar*) is the fineness of gold: how much of
it is the real thing. `ayar` asks the same question of a result built on sorted spikes:
how much of it is neuroscience, and how much is the spike sorter?

Tools such as SpikeInterface quality metrics, Bombcell and UnitRefine judge **units**.
`ayar` judges the **finding**. It reads the output of any sorter (Kilosort, MountainSort,
SpyKING CIRCUS, ... through Phy folders, SpikeInterface, NWB or a plain `.npz` bundle) and
answers three questions:

1. **`ayar scan`**: which sorting artifacts are in this session, and does my result survive
   repairing them?
2. **`ayar multiverse`**: does my result depend on the curation thresholds I happened to
   choose?
3. **`ayar compare`**: does my result survive a different spike sorter?

and helps you act on the answer and check it:

4. **`ayar scan --export-curation`**: the repairs as a curation file that SpikeInterface
   applies directly (merges, removals, labels, stable epochs for drifting units).
5. **`ayar hybrid`**: how well does `ayar` work on *your* recording? Inject units with a known
   answer, sort, and score every flag against the truth.

Each analysis can write a single-file HTML report with the evidence plotted (`--html`) and record
itself with [daftar](https://pypi.org/project/daftar/) (`--daftar`).

`ayar` does not sort spikes and does not prove a finding is right. It tests whether
specific, known artifacts, arbitrary curation choices or the choice of sorter can explain it.

```
pip install ayar                    # numpy + scipy only
pip install "ayar[spikeinterface]"  # to read SortingAnalyzer objects and folders
pip install "ayar[nwb]"             # to read NWB files
pip install "ayar[provenance]"      # to record runs with daftar
```

Python 3.10+, runs on a CPU.

## Thirty seconds

```bash
ayar synth demo.npz --sorters 3     # a session with planted artifacts, plus two re-sortings
ayar scan demo.npz --finding ayar.examples:condition_contrast --html scan.html
ayar multiverse demo.npz --finding ayar.examples:condition_contrast
ayar compare demo.npz demo_sorter2.npz demo_sorter3.npz --names main conservative liberal \
    --finding ayar.examples:condition_contrast
```

```
ERROR   CONTAMINATION   unit 52: 24 refractory violations (<1.5 ms) imply 28% of its spikes
                        come from other neurons
ERROR   DRIFT_CONFOUND  unit 16: rate follows detection loss (r=0.95; up to 50% of spikes
                        below threshold in the worst window)
ERROR   DUPLICATE_UNIT  95% of unit 41's spikes have a unit 17 spike within ±0.25 ms (229x
                        chance): likely one neuron counted twice
ERROR   SPLIT_UNIT      units 50 and 51 look like one neuron: they almost never fire within
                        ±1.5 ms of each other (0 vs 151 expected) and the merged train has
                        0% refractory contamination
WARNING SPLIT_UNIT      units 46 and 47 look like one neuron: one fades out as the other
                        fades in (rate r=-0.99, overlapping in 1 of 20 windows)
...
finding audit: ayar.examples:condition_contrast
  number                 flags           repair                         baseline   after  change  random q95  verdict
  frac_units_suppressed  DRIFT_CONFOUND  restrict 2, remove 1            0.08621  0.03509     59%          2%  SENSITIVE
  frac_units_suppressed  SPLIT_UNIT      merge 3                         0.08621  0.05455     37%          5%  SENSITIVE
  frac_units_suppressed  ALL_FLAGS       merge 5, restrict 2, remove 5   0.08621        0    100%         21%  SENSITIVE
  ...
```

```
ayar 0.4.0 multiverse: ayar.examples:condition_contrast
72 universes; 72 evaluated, 0 skipped (too few units), 0 failed; 58 units before curation

  number                  all units      min   median      max  same sign  spread  verdict
  mean_contrast_hz            1.933    1.773    2.047    2.341       100%     26%  STABLE
  frac_units_suppressed     0.08621        0  0.04701  0.09091        83%    191%  SIGN_UNSTABLE

  frac_units_suppressed: most sensitive to amplitude_cutoff (median moves 108% across its levels)
```

```
ayar 0.4.0 compare: ayar.examples:condition_contrast
  main vs conservative: 47 matched (median agreement 0.92), 11 only in main, 1 only in conservative
  main vs liberal: 58 matched (median agreement 1.00), 0 only in main, 5 only in liberal
  consensus: 47 of 58 main units are found by every sorting

  number                       main  conservative       liberal     consensus  spread  same sign  verdict
  mean_contrast_hz            1.933         1.843         1.769         1.739     11%       100%  CONSISTENT
  frac_units_suppressed     0.08621       0.02083       0.07937       0.06383     91%       100%  SORTER_DEPENDENT

  frac_units_suppressed: units outside the consensus that move it most when left out: main unit 9 (+0.016),
  main unit 34 (+0.016), ...
```

In this synthetic block-design session there is no suppression at all. Every "suppressed"
unit is a drifting unit losing spikes below threshold, or the first half of a neuron the
sorter split in two. The scan finds both causes, the multiverse shows the effect only
appears when units with large amplitude cutoff are kept, and a more conservative re-sorting
shrinks it fourfold, and `compare` traces the difference to units 9 and 34, two of the
drifting units. The condition effect itself (`mean_contrast_hz`) holds in all three.

On your own data:

```bash
ayar scan kilosort_output/ --finding my_analysis.py:main --events events.npz
ayar scan session.nwb --finding my_analysis.py:main --trial-label condition
ayar multiverse analyzer_folder/ --finding my_analysis.py:main --metrics bombcell_metrics.csv \
    --grid "isi_contamination<=0.1,0.25,1" --grid "presence_ratio>=0.5,0.9"
ayar compare ks4_output/ ms5_analyzer/ sc2_analyzer/ --names ks4 ms5 sc2 \
    --finding my_analysis.py:main --events events.npz --html compare.html
```

All three commands exit with status 1 when the finding is in trouble (scan: an error-level
flag or a SENSITIVE/FLIPPED number; multiverse and compare: a SIGN_UNSTABLE number), so they
can gate a pipeline. Use `--fail-on` to change this.

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

b = ayar.load("kilosort_output/")
print(ayar.scan(b, finding=main))
print(ayar.multiverse(b, main).format_text())
```

`ayar.examples` has two templates: `condition_contrast` (a two-condition rate effect) and
`zero_lag_synchrony` (synchrony between neighbouring units).

## The finding audit

For each detector that raised flags, `ayar scan` **repairs** the implicated units, recomputes
the finding, and compares the change with **random controls**: the same repair applied 20
times to random *unflagged* units.

| detector | repair |
|---|---|
| `DUPLICATE_UNIT`, `SPLIT_UNIT` | merge the pair (copies within ±1.25 ms counted once) |
| `DRIFT_CONFOUND` | restrict the unit to its **stable epoch** (the windows where it still detects ≥ 90 % of its spikes); remove it if that is under 30 % of the session |
| `OVERLAP_HOLE` | remove one unit of the pair |
| `CONTAMINATION` | remove the unit |

A random merge joins a unit with its nearest unflagged neighbour, and a random restriction
keeps a random block of an unflagged unit as long as the flagged unit's stable epoch, so a
repair is only blamed on the artifact if it moves the finding more than the same repair on
arbitrary units does.

A restricted unit keeps only its spikes inside the epoch, and its rate is computed over the
epoch. A finding that averages over trials should skip the trials outside it:
`bundle.in_epochs(unit, trial_starts, trial_stops)` gives the mask, as
`ayar.examples.condition_contrast` does.

| verdict | meaning |
|---|---|
| `robust` | changes by less than 10 % |
| `nonspecific` | changes, but no more than random repairs (95th percentile) |
| `shifted` | moves beyond random repairs, by 10-25 % |
| `sensitive` | moves beyond random repairs, by 25 % or more |
| `flipped` | changes sign, which random repairs almost never do |
| `uncontrolled` | changes, but too few units are left to draw random controls, so the audit cannot tell the artifact from the number of units repaired |
| `failed` | your function raised an error on the repaired bundle |

Controls come from unflagged units. In raw, uncurated sortings, where most units may be flagged,
a single detector's controls also draw on units flagged by *other* detectors; the combined
`ALL_FLAGS` repair can then be `uncontrolled`.

## Detectors

| code | needs | what it catches | why it matters |
|---|---|---|---|
| `DUPLICATE_UNIT` | spike times | two units sharing most spikes within ±0.25 ms, far above chance | one neuron counted twice: inflated N, double weight, fake zero-lag correlation |
| `SPLIT_UNIT` | spike times (amplitudes help) | *refractory*: a pair that never fires within ±1.5 ms of each other, out to the edge of that window, and merges into a clean train (double detections within ±0.25 ms are set aside); *handoff*: one unit fades out as a neighbour with matching rate and amplitude fades in | one neuron counted twice; a handoff looks like a cell switching off while another switches on (fake remapping, plasticity, cell loss) |
| `OVERLAP_HOLE` | spike times (depths restrict to neighbours) | a gap within ±0.5 ms in a nearby pair's cross-correlogram, tested against the 2-10 ms flanks | the sorter dropped overlapping spikes: synchrony is underestimated |
| `CONTAMINATION` | spike times | refractory violations implying that a share of a unit's spikes come from other neurons (Hill et al. 2011), and the likely source neighbour | the unit mixes neurons, so its tuning and correlations are partly another cell's |
| `DRIFT_CONFOUND` | amplitudes or depths | firing rate that tracks spike amplitude, depth, or estimated detection loss over the session; or an amplitude that walks steadily down (or up) until the unit vanishes (or appears), which is how a template-matching sorter loses a drifting neuron | apparent rate changes are spikes lost below threshold, or a neuron lost to drift; an **error** when conditions are ordered in time, because the loss then looks like a condition effect |

When two detectors see one cause, it is reported once: a unit that is handed off is not also
reported as drifting, a contaminated unit's dip with its own source is not also reported as an
overlap hole, and a duplicate is not also reported as a split. Each flag carries a code, a severity, the units, the evidence, why it
matters and a fix. Every threshold is named and can be overridden (`--set split_ratio=0.2`,
or `ayar.DEFAULTS.override(...)`). Checks that cannot run, or run on only some units, are
listed under *not checked* instead of being guessed.

## The curation multiverse

`ayar multiverse` recomputes the finding for every combination of curation thresholds in a
grid, and reports per number the range across universes, the share with the same sign, and
which threshold moves it most.

The default grid has 72 universes:

```
firing_rate>=0,0.1,0.5,1  presence_ratio>=0,0.5,0.9  isi_contamination<=1,0.25,0.1  amplitude_cutoff<=0.5,0.1
```

`ayar` computes these metrics itself (`ayar.metrics.compute`). You can add or override metrics
with a CSV/TSV table (`--metrics`: SpikeInterface `quality_metrics`, Bombcell, your own; one
row per unit) or `ayar.metrics.from_spikeinterface(analyzer)`, and use any column in a rule.
Units missing a metric are not curated on it.

| verdict | meaning |
|---|---|
| `stable` | the 5-95 % range is under 50 % of the median and the sign never changes |
| `threshold_dependent` | the sign holds, but the size depends on the thresholds |
| `sign_unstable` | the number changes sign, or vanishes, in more than 10 % of universes |

## Across sorters

Sort the same recording with two or more sorters, or one sorter with different settings, and
hand `ayar compare` the outputs. It

1. **matches units** between the reference (the first sorting, or `--reference`) and each other
   sorting. Agreement between two units is `matched spikes / (n_a + n_b - matched)`, with spikes
   matched within ±0.4 ms, the score used by SpikeInterface and SpikeForest. Units are paired
   one-to-one by maximising total agreement, and pairs below 0.5 are left unmatched;
2. recomputes the finding on **every sorting** and on the **consensus units**: reference units
   that every other sorting also found;
3. reports per number the value in each sorting, the spread, whether the sign holds, and a
   verdict;
4. for a number that is not consistent, **traces it to units**: each unit found by only some
   sortings is left out of its own sorting in turn, and the units whose removal moves the
   number most are listed. On the demo session, the two units it names first for the inflated
   synchrony are exactly the two planted duplicates.

| verdict | meaning |
|---|---|
| `consistent` | every sorting gives the same sign and the values stay within 25 % of the median |
| `sorter_dependent` | the sign holds, but the size depends on the sorter |
| `sign_unstable` | the number changes sign, or vanishes, depending on the sorter |

```python
rep = ayar.compare({"ks4": ayar.load("ks4/"), "ms5": ayar.load("ms5.zarr")}, main)
m = ayar.match_units(bundle_a, bundle_b)     # Matching: .pairs, .unmatched_a, .agreement
```

Events are copied from the reference to sortings that have none (they are the same
recording). Matching two sortings with hundreds of units and millions of spikes takes about a
second.

## Reports and provenance

`--html report.html` on `scan`, `multiverse` or `compare` writes one self-contained file: no
internet, no plotting library, light and dark themes, a tooltip on every mark, and the data
table behind every chart. The scan report plots the evidence for each flag (cross-correlograms
for duplicates, splits and holes; firing-rate handoffs; ISI histograms for contamination; rate
and amplitude over time for drift), and the finding audit as change-versus-random-controls
charts. The multiverse report draws a specification curve per number; the compare report draws
each number across sorters and the agreement of matched units.

`--daftar` records the run with [daftar](https://pypi.org/project/daftar/): input hashes,
thresholds, ayar's version and environment, every flag, the finding's numbers and verdicts, and
the report files. `daftar diff` then shows what changed between two runs, for example before and
after re-curating a session.

## Input

```python
b = ayar.load("kilosort4_output/")                # Phy / Kilosort folder
b = ayar.load("analyzer_folder/")                 # saved SpikeInterface SortingAnalyzer
b = ayar.from_spikeinterface(analyzer)            # in memory: Sorting or SortingAnalyzer
b = ayar.load("session.nwb", trial_label="condition")
b = ayar.from_arrays(times_s, clusters, amplitudes=amps, spike_depths=depths,
                     events=ayar.Events(trial_times, trial_labels))
b.save("session.npz")                             # plain npz, readable with numpy alone
```

* **IBL**: `ayar.from_ibl(spikes, clusters, trials)` takes `SpikeSortingLoader` output; trials
  become events (`feedback`, `stimulus` or `choice`), and IBL's quality `label` is available to
  the multiverse. `ayar.load()` also opens ALF folders (`spikes.times.npy`, ...).
* **Phy / Kilosort**: keeps units labelled `good` or `mua` (curated labels win over
  Kilosort's), depths from `spike_positions.npy` (Kilosort 4) or `cluster_info.tsv`.
* **SpikeInterface**: amplitudes from `spike_amplitudes`, depths from `spike_locations` and
  `unit_locations`, duration from the recording. String unit ids are mapped to integers
  (`bundle.meta["unit_id_map"]`).
* **NWB**: the units table (`spike_times`, optional `spike_amplitudes`, depth from a `depth`
  column or the unit's electrode) and the trials table for events; `shift_negative=True` for
  sessions whose spike times start before zero.

## Acting on the flags: curation export

```bash
ayar scan sorting/ --export-curation curation.json --export-phy sorting/ --html report.html
```

`curation.json` is SpikeInterface's curation format (version 2): every flagged unit gets an
`ayar` label listing its flags, error-level duplicates and splits become **merges**, units with
error-level contamination or no stable epoch become **removed**, and drifting units' stable
epochs go in an `ayar_epochs` field (SpikeInterface ignores it). Overlap holes are labelled but
not acted on: they matter for synchrony analyses, not for keeping a unit. `--curate-warnings`
also acts on warnings. `cluster_ayar.tsv` shows the labels as a column in Phy.

It is a proposal: check it against the report's evidence, then apply it.

```python
from spikeinterface.curation import apply_curation
curated = apply_curation(sorting_analyzer, json.load(open("curation.json")))
```

```bash
ayar scan sorting/ --curation curation.json --finding my_analysis.py:main   # re-scan after
```

`ayar` applies the same file itself (merges, removals and stable epochs) with `--curation`,
so the scan, the finding audit and the multiverse can be re-run on the curated units.

## Is ayar right on my data? `ayar hybrid`

The synthetic validation below shows the detectors work on clean, simulated artifacts. Real
tissue is messier. `ayar hybrid` checks `ayar` on **your** recording, probe and sorter:

```bash
# inject 10 known units (3 of them fading over the session) and sort with your own pipeline
ayar hybrid make my_recording/ hybrid/ --units 10 --fading 3
#   ... sort hybrid/recording with Kilosort, the GUI, your cluster: anything ...
ayar hybrid score hybrid/ hybrid_sorted/

# or let SpikeInterface run the sorter
ayar hybrid run raw/ hybrid/ --reader spikeglx --stream imec0.ap --sorter kilosort4 --max-duration 1800
```

The injected units come from SpikeInterface's hybrid generator. A *fading* unit's amplitude
falls to a quarter by the end of the session, so the sorter loses its late spikes, the way a
drifting neuron is lost. `score` then reports what the sorter did to each injected unit (found,
split, merged with other spikes, missed), and checks every flag that touches an injected unit
against the truth: a split or duplicate is right if both units hold the same injected unit, a
drift flag is right if the unit fades, an overlap hole between two injected units is right
because their spike trains are independent. Flags on the recording's own neurons have no known
answer and are not scored.

## Evidence tiers

* **Tier 0: spike times.** Duplicate, split, overlap and contamination detectors run (all
  pairs, capped at 20,000 pairs).
* **Tier 1: plus amplitudes and/or depths.** Pair tests are restricted to neighbouring units
  (100 µm), handoff splits check amplitude continuity, and the drift detector runs.
* **Tier 2: plus the raw recording.** `ayar hybrid` injects units with a known answer into the
  recording and scores `ayar` against them (below).

## Self-validation

`ayar validate` plants every artifact in synthetic sessions, together with **controls** that
must not be flagged: pairs driven by genuine common input (a real cross-correlogram peak) and
units whose true rate ramps over the session at constant amplitude.

```
ayar validate --sessions 20 --seed 100

  detector         planted  found  false ctrl alarms sensitivity precision
  DUPLICATE_UNIT        40     40      0           0        1.00      1.00
  SPLIT_UNIT            60     60      0           0        1.00      1.00
  OVERLAP_HOLE          40     40      0           0        1.00      1.00
  CONTAMINATION         40     39      0           0        0.97      1.00
  DRIFT_CONFOUND        60     57      0           0        0.95      1.00

  finding audit: in 19 session(s) drift manufactured 'suppressed' units; ayar called that
  number SENSITIVE or FLIPPED in 19
```

In these sessions `CONTAMINATION` named the true source unit for 23 of 37 contaminated units
and never named a wrong one. A 300-unit, 30-minute session takes about 50 s for a full scan
with the audit, and 10 s for the default multiverse, on a laptop CPU.

These numbers are measured on ayar's own synthetic data, whose artifacts are cleaner than
real ones. They show that the detectors do what they claim, not how often they fire on real
recordings.

## A first check on real sorters

`examples/real_sorters.py` simulates a 32-channel recording with SpikeInterface (12 neurons,
known spike trains), sorts it with three real sorters at their default settings, scans every
sorting, and checks each flag against which neuron each sorted unit really belongs to. One
10-minute run:

| sorting | units | neurons well detected | flags | checked against the truth |
|---|---|---|---|---|
| ground truth | 12 | 12 | 0 | no false flags on clean units |
| tridesclous2 | 14 | 11 | 1 contamination | the unit is 85 % one neuron |
| spykingcircus2 | 15 | 11 | 2 contamination, 1 duplicate | the units are 59 % and 84 % one neuron; the duplicate is one neuron sorted twice at a 0.37 ms offset |
| mountainsort5 | 28 | 2 | 6 splits, 1 duplicate, 45 overlap holes | all 6 splits correct; the duplicate warning is a 103-spike cluster of collision events (its shared spikes are real, it is not one neuron); every hole is between different neurons, where the sorter discarded near-simultaneous spikes |

**Hybrid check.** The same 10-minute recording with 10 units injected by `ayar hybrid` (3 of
them fading to a quarter of their amplitude), sorted by two of the sorters:

| sorter | injected units | flags on injected units | caught |
|---|---|---|---|
| tridesclous2 | 6 found, 2 partly found, 1 split, 1 missed | 3, all correct (2 drift, 1 split) | the 1 split unit; all 3 fading units (2 as drifting, 1 as the split the sorter made as it faded) |
| spykingcircus2 | 6 found, 1 partly found, 1 merged, 2 missed | 2, both correct (drift) | both fading units the sorter kept |

Building the hybrid check exposed a drift pattern the detector had missed: tridesclous2 kept a
fading unit's spikes whole while their amplitude fell, then lost the unit at once, so neither
its rate nor its amplitude distribution showed gradual loss. The fade test (amplitude walking
steadily one way, then the unit vanishing) was added for it.

What it missed: the sorters split 13 neurons into pieces; `ayar` flagged 7 of them (6 as
splits, 1 as a duplicate) and missed 6. In every miss one piece was a small fragment (23 to
298 spikes) that is too sparse to test in 10 minutes, and `ayar` lists such units and pairs
under *partly checked* rather than calling them clean. The sorters are not
deterministic, so a re-run gives somewhat different sortings. This is one simulated recording;
it is a check on real sorter behaviour, not a validation on real tissue. Run `ayar hybrid` on
your own recordings for that.

## On public data

`examples/public_sessions.py` downloads one public IBL probe insertion (from IBL's public
server) and one session of the Steinmetz et al. 2019 Neuropixels dataset (DANDI 000017), runs
`scan` with the finding audit and `multiverse` on each (feedback: correct vs error trials), and
writes `RESULTS.md` with the reports, ready to read or share:

```bash
pip install "ayar[nwb]" ONE-api ibllib dandi
export OPENALYX_USER=<user> OPENALYX_PASSWORD=<password>    # free account: openalyx.internationalbrainlab.org/signup
python examples/public_sessions.py --out public_results      # about 1.5 GB; about 30 minutes
```

IBL's public server now asks every user to register (free); without credentials the script
skips IBL, says why in `RESULTS.md`, and still runs the DANDI session, which needs no account.

Pick another session with `--ibl-pid` or `--dandiset` / `--dandi-asset`; `--ibl-local` and
`--nwb-local` reuse files already downloaded. IBL data is read with `ayar.from_ibl()` (the
output of IBL's `SpikeSortingLoader`) or `ayar.from_alf()` (ALF files on disk), DANDI data
with `ayar.from_nwb()`.

### Results: one IBL insertion and one DANDI session

The full report is in [docs/public_sessions.md](https://github.com/aslansd/ayar/blob/main/docs/public_sessions.md). In short:

| | IBL insertion `da8dfec1` (probe00) | DANDI 000017 (Steinmetz et al. 2019), `sub-Richards` 2017-10-31 |
|---|---|---|
| data | 1143 units, 39.8 M spikes, 72 min; amplitudes and depths (tier 1) | 778 units, 4.7 M spikes, 49 min; spike times only (tier 0) |
| flags | 456 contamination, 80 duplicates, 15 splits, 136 drift (warnings), 628 overlap holes; 746 units in at least one flag | 192 contamination; pair detectors and drift not run (no depths or amplitudes) |
| finding audit (feedback: correct vs error) | `nonspecific`, `robust`, `nonspecific` | `robust` for the mean contrast; `shifted` for the fractions of enhanced and suppressed units |
| curation multiverse | the mean contrast is `threshold_dependent` (-0.20 Hz with all units, -0.69 median, down to -0.95), driven most by IBL's quality label | the mean contrast is `sign_unstable` (+0.07 Hz with all units, negative in 20 of 36 universes), driven most by the ISI-contamination threshold |
| run time (laptop) | scan + audit 24 min, multiverse 6 min | 4 s and 5 s |

What it shows:

* **Raw sortings are full of flags.** IBL publishes every cluster, not only its good units, so
  most units being flagged is expected; the IBL flags agree in kind with what is known about
  the sorter (template duplicates, and overlap holes from its removal of near-simultaneous
  spikes). There is no ground truth here, so these are hypotheses, with the evidence for each
  in the HTML report.
* **The finding audit holds back where it should.** In the IBL session, removing the 456
  contaminated units moves the mean contrast by 139 %, but so does removing 456 random units
  (141 %): the number is fragile to *any* change of unit set, not to contamination as such, and
  the verdict is `nonspecific`, not `sensitive`. The combined repair (600 units removed) had too
  few clean units left to compare with, and is reported as not comparable.
* **The multiverse finds the fragility.** Both mean contrasts depend on curation thresholds;
  in the DANDI session its sign does.
* **Real data found two bugs**, fixed in this release: a truncated download that the script
  reused, and audit verdicts reported as `sensitive` when no random controls were possible.

## Limitations (v0.4)

* Research prototype. Thresholds are calibrated on synthetic sessions; on public data (above)
  ayar has run, but without ground truth its flags there are unverified.
* Speed: a 1143-unit, 40 M-spike session took 24 minutes for the scan and finding audit on a
  laptop. Use `--set audit_controls=5`, or scan without `--finding`, for a quick look.
* Without depths (tier 0), the pair detectors (duplicates, splits, overlap holes) test every
  pair, and refuse to when there are more than 20,000 pairs (about 200 units); they then say so
  under *not checked*. Many NWB files on DANDI have no spike depths.
* Units with few spikes (fewer than ~600) get only the weaker drift trend test, and
  contamination needs at least 5 refractory violations; both are reported as partly checked
  or simply not flagged.
* A handoff split is ambiguous with real biology (one cell silenced as a neighbour starts
  firing); it is a warning, and amplitude continuity is required when amplitudes exist.
* Restricting a drifting unit to its stable epoch only helps findings that respect epochs
  (`bundle.in_epochs`); a finding that ignores them sees the unit as silent outside its epoch.
* `ayar hybrid` injects stationary templates (only their amplitude fades); it does not move
  injected units with the probe's own drift.
* The audit calls your function about 20 times per detector, and the multiverse once per
  universe. Use `--set audit_controls=0`, or a smaller `--grid`, when it is slow.
* Pair tests need enough coincidences: in short recordings, small fragments of a split neuron
  cannot be tested and are counted under *partly checked*.
* `compare` matches units to the reference only; a unit found by two non-reference sorters but
  not the reference does not enter the consensus.

## Roadmap

* **v0.5**: speed (pair statistics for all units at once, cheaper audit controls), so large
  sessions take minutes and tier-0 sessions get the pair detectors; reading unit depths from
  more NWB layouts; `ayar hybrid` on a public raw recording; one session report that merges
  scan, multiverse and compare.

See [CHANGELOG.md](https://github.com/aslansd/ayar/blob/main/CHANGELOG.md) for what changed in each release.

## Family

`ayar` sits with [daftar](https://pypi.org/project/daftar/) (provenance),
[raftaar](https://pypi.org/project/raftaar/) (robot demonstration datasets),
[tarjuman](https://pypi.org/project/tarjuman/) (NeuroML to Jaxley),
[miras](https://pypi.org/project/miras/) (study-design identifiability),
[baghban](https://pypi.org/project/baghban/) (Bonsai workflow checks) and
[ayna](https://pypi.org/project/ayna/) (are your inferred dynamics real?).

## Author

Aslan Satary Dizaji

## License

Apache 2.0
