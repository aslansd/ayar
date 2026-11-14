# ayar on public sessions

ayar on real, public spike-sorted data: one IBL Neuropixels insertion and one session of the
Steinmetz et al. 2019 dataset on DANDI.

Generated 2026-11-14 07:57 UTC by `examples/public_sessions.py` with ayar 0.5.0, on a
MacBook Pro. The script's own output is in
[`public_results/`](https://github.com/aslansd/ayar/tree/main/public_results): one HTML report
per session ([IBL](https://htmlpreview.github.io/?https://github.com/aslansd/ayar/blob/main/public_results/ibl.html), [DANDI](https://htmlpreview.github.io/?https://github.com/aslansd/ayar/blob/main/public_results/dandi.html)), the JSON files and `RESULTS.md`.
This page is that `RESULTS.md` with notes added.

## What 0.5.0 adds

Each session is now scanned twice: on all units, and on the units the dataset's authors
analyse (IBL: `label>=1`, units passing all three IBL quality criteria; Steinmetz et al.:
`phy_annotations>=2`). And the DANDI file is now read with its spike amplitudes, depths and
two probes (tier 1); 0.4 and 0.5.0.dev0 read spike times only.

**Among IBL's good units the flags are few, and one finding moves.** Of the 1143 clusters,
746 are flagged; of the 298 good units, 64 are (14 errors, 43 warnings). The 347
contamination errors among all units become none among good units (8 warnings), as they
should: IBL's label already requires a clean refractory period. What remains are 8 duplicate
pairs (two good units holding one neuron, so both enter an analysis), 5 overlap holes, one
split pair and 28 drift warnings. On the good units the mean contrast is -0.88 Hz (-0.20 Hz on all
units), and repairing their flags moves it by 20 %, more than the same repair applied to
random good units (95th percentile 15 %): `shifted`. This is the first public result in which
sorting artifacts among curated units measurably move a finding beyond what removing any units
would do. The fractions of enhanced and suppressed units stay `robust`.

**The DANDI flags shrink once ayar knows where units are.**

| DANDI session, all units | tier 0 (0.5.0.dev0, 11 Nov) | tier 1 (0.5.0) |
|---|---|---|
| duplicates (errors / warnings) | 0 / 7 | none |
| splits | 27 / 85 | 2 / 18 |
| overlap holes | 60 / 180 | 3 / 6 |
| contamination | 179 / 13 | 179 / 13 (likely sources now only same-probe neighbours) |
| drift | not run | 0 / 78 |
| units in at least one flag | 428 of 778 | 299 of 778 |

At tier 0 every pair of units was tested, including units far apart or on the other probe.
With depths and probes, pairs are only tested within 100 µm on the same probe, and most of the
tier-0 pair flags are gone. This is what the 11 November caution expected: those flags were
leads, and most did not survive knowing where the units are. The seven tier-0 duplicate
warnings (up to 1286x chance coincidence at zero lag) were between units ayar no longer
compares: near-simultaneous spikes on distant units point to shared events, such as
electrical noise, rather than to one neuron sorted twice, and ayar does not test for that.
The audit's verdicts on all units hardly change (`nonspecific`, `shifted`, `shifted`); on the
authors' 522 kept units, the two fractions become `robust`.

**The IBL all-unit results are unchanged**: the same 1315 flags as with 0.5.0.dev0 and 0.4.0,
the same audit and multiverse. Scan and audit took 258.6 s (300.7 s on 11 November, 1438.7 s
with 0.4.0).

## Summary

| session | units | flags (errors / warnings) | kept units: flags | finding audit | curation multiverse |
|---|---|---|---|---|---|
| IBL insertion da8dfec1-d265-44e8-84ce-6ae9c109b8bd | 1143 | 534 / 781 | 298 units (`label>=1`): 14 / 43 | mean_contrast_hz: nonspecific, frac_units_enhanced: robust, frac_units_suppressed: nonspecific (combined repair not comparable: too few unflagged units) | mean_contrast_hz: threshold_dependent, frac_units_enhanced: stable, frac_units_suppressed: stable |
| DANDI 000017: sub-Richards/sub-Richards_ses-20171031T120000.nwb | 778 | 184 / 115 | 522 units (`phy_annotations>=2`): 108 / 88 | mean_contrast_hz: nonspecific, frac_units_enhanced: shifted, frac_units_suppressed: shifted | mean_contrast_hz: sign_unstable, frac_units_enhanced: threshold_dependent, frac_units_suppressed: threshold_dependent |

## How to read this

These sessions have no ground truth. A flag is a hypothesis about the sorting, with the
evidence plotted in the HTML report; the finding audit says whether the example finding
would change if the flagged units were repaired, and the multiverse whether it depends on
curation thresholds. The example finding (a two-condition rate contrast) stands in for a
real analysis; with your own finding the same machinery applies.

A verdict is only `sensitive` or `shifted` when the change beats the same repair applied
to random units. When too few units are left to draw such controls (for example when
most units are flagged), the verdict is `uncontrolled`: the number moves, but the audit
cannot say whether the artifact or the sheer number of units removed moves it.

## IBL insertion da8dfec1-d265-44e8-84ce-6ae9c109b8bd

- **Source:** IBL public data (https://openalyx.internationalbrainlab.org), insertion da8dfec1-d265-44e8-84ce-6ae9c109b8bd, session 4ecb5d24-f5cc-402c-be28-9d0f7cb14b3a, probe00 ([link](https://openalyx.internationalbrainlab.org/insertions/da8dfec1-d265-44e8-84ce-6ae9c109b8bd))
- **Data:** 1143 units, 39,835,238 spikes, 4295.95 s, tier 1 (amplitudes, depths)
- **Events:** feedback: correct (1) vs error (-1) trials; -1: 85, 1: 443 trials
- **Run time:** scan + audit 258.6 s, on kept units 68.9 s, multiverse 375.3 s

### Sorting artifacts flagged: all units

| detector | errors | warnings | units involved |
|---|---|---|---|
| `CONTAMINATION` | 347 | 109 | 456 |
| `DRIFT_CONFOUND` | 0 | 136 | 136 |
| `DUPLICATE_UNIT` | 58 | 22 | 120 |
| `OVERLAP_HOLE` | 119 | 509 | 398 |
| `SPLIT_UNIT` | 10 | 5 | 28 |

746 of 1143 units are involved in at least one flag.

Examples (up to three per detector):

- `CONTAMINATION` (error), units 5: 80 refractory violations (<1.5 ms) imply 50%+ of its spikes come from other neurons; likely source: unit 15 (shared refractory dip, ratio 0.57)
- `CONTAMINATION` (error), units 16: 834 refractory violations (<1.5 ms) imply 42% of its spikes come from other neurons; likely source: unit 17 (shared refractory dip, ratio 0.41)
- `CONTAMINATION` (error), units 19: 770 refractory violations (<1.5 ms) imply 37% of its spikes come from other neurons; likely source: unit 8 (shared refractory dip, ratio 0.61)
- `DRIFT_CONFOUND` (warning), units 3: rate follows depth (rho=0.69, moved 11 µm)
- `DRIFT_CONFOUND` (warning), units 4: rate follows amplitude (rho=0.63, amplitude range 18%); rate follows detection loss (r=0.61; up to 50% of spikes below threshold in the worst window)
- `DRIFT_CONFOUND` (warning), units 5: rate follows depth (rho=0.75, moved 14 µm)
- `DUPLICATE_UNIT` (error), units 86, 84: 95% of unit 84's spikes have a unit 86 spike within ±0.25 ms (136x chance): likely one neuron counted twice
- `DUPLICATE_UNIT` (error), units 106, 107: 96% of unit 107's spikes have a unit 106 spike within ±0.25 ms (32x chance): likely one neuron counted twice
- `DUPLICATE_UNIT` (error), units 106, 111: 90% of unit 111's spikes have a unit 106 spike within ±0.25 ms (30x chance): likely one neuron counted twice
- `OVERLAP_HOLE` (error), units 4, 3: units 4 and 3 fire within ±0.5 ms 27% as often as expected from the 2-10 ms flanks (514 vs 1938, p=0.0e+00)
- `OVERLAP_HOLE` (error), units 5, 8: units 5 and 8 fire within ±0.5 ms 29% as often as expected from the 2-10 ms flanks (56 vs 193, p=2.8e-31)
- `OVERLAP_HOLE` (error), units 6, 3: units 6 and 3 fire within ±0.5 ms 24% as often as expected from the 2-10 ms flanks (198 vs 810, p=8.8e-147)
- `SPLIT_UNIT` (error), units 36, 44: units 36 and 44 look like one neuron: they almost never fire within ±1.5 ms of each other (75 vs 372 expected, plus 102 double detections) and the merged train has 4% refractory contamination
- `SPLIT_UNIT` (error), units 208, 960: units 208 and 960 look like one neuron: they almost never fire within ±1.5 ms of each other (9 vs 45 expected, plus 10 double detections) and the merged train has 0% refractory contamination
- `SPLIT_UNIT` (error), units 471, 989: units 471 and 989 look like one neuron: they almost never fire within ±1.5 ms of each other (32 vs 223 expected, plus 5 double detections) and the merged train has 6% refractory contamination

Not checked, or only partly:

- `SPLIT_UNIT`: 14 unit(s) with fewer than 100 spikes were not tested; small units are often fragments of a neuron that another unit already holds
- `SPLIT_UNIT`: 4824 of 34928 nearby pairs had too few spikes for the refractory test (expected < 10 within ±1.5 ms); small fragments of a split neuron can hide here, and longer recordings make them testable
- `OVERLAP_HOLE`: 8225 of 34928 candidate pairs had too few coincidences to test (expected < 10 near zero lag)
- `DRIFT_CONFOUND`: 14 unit(s) with fewer than 100 spikes skipped
- `DRIFT_CONFOUND`: 72 unit(s) had too few spikes for the detection-loss test (< 6 x 100); only amplitude/depth trends were tested

### Sorting artifacts flagged: kept units (`label>=1`)

The units the dataset's authors analyse: 298 of 1143. The scan runs on these units alone, so a flag needs both of its units kept, and the audit's random controls come from kept units.

| detector | errors | warnings | units involved |
|---|---|---|---|
| `CONTAMINATION` | 0 | 8 | 8 |
| `DRIFT_CONFOUND` | 0 | 28 | 28 |
| `DUPLICATE_UNIT` | 8 | 0 | 15 |
| `OVERLAP_HOLE` | 5 | 6 | 20 |
| `SPLIT_UNIT` | 1 | 1 | 4 |

64 of 298 units are involved in at least one flag.

Not checked, or only partly:

- `SPLIT_UNIT`: 32 of 2895 nearby pairs had too few spikes for the refractory test (expected < 10 within ±1.5 ms); small fragments of a split neuron can hide here, and longer recordings make them testable
- `OVERLAP_HOLE`: 139 of 2895 candidate pairs had too few coincidences to test (expected < 10 near zero lag)

### Finding audit: condition_contrast (0-0.5 s after each event), all units

| number | baseline | verdict | repair that sets the verdict: change (random 95th pct) | not comparable with random repairs |
|---|---|---|---|---|
| `mean_contrast_hz` | -0.2023 | **nonspecific** | CONTAMINATION (remove 456): 139% (random 141%) | ALL_FLAGS: 143% |
| `frac_units_enhanced` | 0.2135 | **robust** | DRIFT_CONFOUND (restrict 30, remove 106): 4% (random 4%) | ALL_FLAGS: 14% |
| `frac_units_suppressed` | 0.217 | **nonspecific** | CONTAMINATION (remove 456): 11% (random 12%) | ALL_FLAGS: 15% |

### Finding audit: condition_contrast (0-0.5 s after each event), kept units

| number | baseline | verdict | repair that sets the verdict: change (random 95th pct) | not comparable with random repairs |
|---|---|---|---|---|
| `mean_contrast_hz` | -0.8823 | **shifted** | ALL_FLAGS (merge 10, restrict 13, remove 34): 20% (random 15%) | - |
| `frac_units_enhanced` | 0.198 | **robust** | ALL_FLAGS (merge 10, restrict 13, remove 34): 7% (random 9%) | - |
| `frac_units_suppressed` | 0.3557 | **robust** | CONTAMINATION (remove 8): 2% (no controls) | - |

### Curation multiverse (all units)

216 of 216 universes evaluated (grid: `firing_rate>=0,0.1,0.5,1  presence_ratio>=0,0.5,0.9  isi_contamination<=1,0.25,0.1  amplitude_cutoff<=0.5,0.1  label>=0,0.6,1`).

| number | all units | min | median | max | same sign | verdict | most influential threshold |
|---|---|---|---|---|---|---|---|
| `mean_contrast_hz` | -0.2023 | -0.9521 | -0.6924 | -0.2023 | 100% | **threshold_dependent** | label |
| `frac_units_enhanced` | 0.2135 | 0.1884 | 0.2014 | 0.2238 | 100% | **stable** | firing_rate |
| `frac_units_suppressed` | 0.217 | 0.217 | 0.3231 | 0.3646 | 100% | **stable** | label |

### Files

- `ibl.html`: the session report: every flag with its evidence plot, the audits and the specification curves ([view](https://htmlpreview.github.io/?https://github.com/aslansd/ayar/blob/main/public_results/ibl.html), [file](https://github.com/aslansd/ayar/blob/main/public_results/ibl.html))
- [`ibl_curation.json`](https://github.com/aslansd/ayar/blob/main/public_results/ibl_curation.json): the repairs as a SpikeInterface curation
- [`ibl_scan.json`](https://github.com/aslansd/ayar/blob/main/public_results/ibl_scan.json), [`ibl_kept_scan.json`](https://github.com/aslansd/ayar/blob/main/public_results/ibl_kept_scan.json), [`ibl_multiverse.json`](https://github.com/aslansd/ayar/blob/main/public_results/ibl_multiverse.json): everything above, machine-readable

## DANDI 000017: sub-Richards/sub-Richards_ses-20171031T120000.nwb

- **Source:** DANDI Archive, dandiset 000017, file sub-Richards/sub-Richards_ses-20171031T120000.nwb ([link](https://dandiarchive.org/dandiset/000017))
- **Data:** 778 units, 4,703,292 spikes, 2968.28 s, tier 1 (amplitudes, depths, 2 probes)
- **Events:** trials column 'feedback_type' at 'feedback_time'; -1: 74, 1: 186 trials
- **Run time:** scan + audit 35.2 s, on kept units 27.2 s, multiverse 12.0 s
- **Read from the NWB units table:** amplitudes from `spike_amps`, spike_depths from `spike_depths`, unit_depths from `cluster_depths`, probes from `electrode_group`

### Sorting artifacts flagged: all units

| detector | errors | warnings | units involved |
|---|---|---|---|
| `CONTAMINATION` | 179 | 13 | 192 |
| `DRIFT_CONFOUND` | 0 | 78 | 78 |
| `OVERLAP_HOLE` | 3 | 6 | 17 |
| `SPLIT_UNIT` | 2 | 18 | 40 |

299 of 778 units are involved in at least one flag.

Examples (up to three per detector):

- `CONTAMINATION` (error), units 0: 34 refractory violations (<1.5 ms) imply 34% of its spikes come from other neurons; likely source: unit 86 (shared refractory dip, ratio 0.59)
- `CONTAMINATION` (error), units 2: 29 refractory violations (<1.5 ms) imply 50%+ of its spikes come from other neurons
- `CONTAMINATION` (error), units 11: 24 refractory violations (<1.5 ms) imply 50%+ of its spikes come from other neurons
- `DRIFT_CONFOUND` (warning), units 5: rate follows amplitude (rho=0.68, amplitude range 16%)
- `DRIFT_CONFOUND` (warning), units 10: rate follows depth (rho=0.62, moved 13 µm)
- `DRIFT_CONFOUND` (warning), units 27: rate follows detection loss (r=0.79; up to 50% of spikes below threshold in the worst window)
- `OVERLAP_HOLE` (error), units 136, 75: units 136 and 75 fire within ±0.5 ms 0% as often as expected from the 2-10 ms flanks (0 vs 23, p=1.5e-10)
- `OVERLAP_HOLE` (error), units 676, 671: units 676 and 671 fire within ±0.5 ms 26% as often as expected from the 2-10 ms flanks (10 vs 39, p=4.2e-08)
- `OVERLAP_HOLE` (error), units 751, 431: units 751 and 431 fire within ±0.5 ms 22% as often as expected from the 2-10 ms flanks (7 vs 32, p=7.4e-08)
- `SPLIT_UNIT` (error), units 1, 76: units 1 and 76 look like one neuron: they almost never fire within ±1.5 ms of each other (2 vs 34 expected) and the merged train has 10% refractory contamination
- `SPLIT_UNIT` (error), units 187, 285: units 187 and 285 look like one neuron: they almost never fire within ±1.5 ms of each other (1 vs 206 expected) and the merged train has 3% refractory contamination
- `SPLIT_UNIT` (warning), units 180, 629: units 180 and 629 look like one neuron: one fades out as the other fades in (rate r=-0.78, overlapping in 2 of 20 windows)

Not checked, or only partly:

- `SPLIT_UNIT`: 8883 of 13805 nearby pairs had too few spikes for the refractory test (expected < 10 within ±1.5 ms); small fragments of a split neuron can hide here, and longer recordings make them testable
- `OVERLAP_HOLE`: 11111 of 13805 candidate pairs had too few coincidences to test (expected < 10 near zero lag)
- `DRIFT_CONFOUND`: 178 unit(s) had too few spikes for the detection-loss test (< 6 x 100); only amplitude/depth trends were tested

### Sorting artifacts flagged: kept units (`phy_annotations>=2`)

The units the dataset's authors analyse: 522 of 778. The scan runs on these units alone, so a flag needs both of its units kept, and the audit's random controls come from kept units.

| detector | errors | warnings | units involved |
|---|---|---|---|
| `CONTAMINATION` | 105 | 8 | 113 |
| `DRIFT_CONFOUND` | 0 | 65 | 65 |
| `OVERLAP_HOLE` | 1 | 2 | 6 |
| `SPLIT_UNIT` | 2 | 13 | 30 |

198 of 522 units are involved in at least one flag.

Not checked, or only partly:

- `SPLIT_UNIT`: 3282 of 6194 nearby pairs had too few spikes for the refractory test (expected < 10 within ±1.5 ms); small fragments of a split neuron can hide here, and longer recordings make them testable
- `OVERLAP_HOLE`: 4517 of 6194 candidate pairs had too few coincidences to test (expected < 10 near zero lag)
- `DRIFT_CONFOUND`: 63 unit(s) had too few spikes for the detection-loss test (< 6 x 100); only amplitude/depth trends were tested

### Finding audit: condition_contrast (0-0.5 s after each event), all units

| number | baseline | verdict | repair that sets the verdict: change (random 95th pct) | not comparable with random repairs |
|---|---|---|---|---|
| `mean_contrast_hz` | 0.06613 | **nonspecific** | ALL_FLAGS (merge 20, restrict 18, remove 242): 33% (random 131%) | - |
| `frac_units_enhanced` | 0.1607 | **shifted** | CONTAMINATION (remove 192): 12% (random 8%) | - |
| `frac_units_suppressed` | 0.1028 | **shifted** | CONTAMINATION (remove 192): 17% (random 13%) | - |

### Finding audit: condition_contrast (0-0.5 s after each event), kept units

| number | baseline | verdict | repair that sets the verdict: change (random 95th pct) | not comparable with random repairs |
|---|---|---|---|---|
| `mean_contrast_hz` | 0.04209 | **nonspecific** | ALL_FLAGS (merge 15, restrict 17, remove 152): 107% (random 247%) | - |
| `frac_units_enhanced` | 0.1494 | **robust** | CONTAMINATION (remove 113): 8% (random 11%) | - |
| `frac_units_suppressed` | 0.1245 | **robust** | CONTAMINATION (remove 113): 10% (random 8%) | - |

### Curation multiverse (all units)

72 of 72 universes evaluated (grid: `firing_rate>=0,0.1,0.5,1  presence_ratio>=0,0.5,0.9  isi_contamination<=1,0.25,0.1  amplitude_cutoff<=0.5,0.1`).

| number | all units | min | median | max | same sign | verdict | most influential threshold |
|---|---|---|---|---|---|---|---|
| `mean_contrast_hz` | 0.06613 | -0.3969 | -0.07341 | 0.07871 | 74% | **sign_unstable** | isi_contamination |
| `frac_units_enhanced` | 0.1607 | 0.115 | 0.1598 | 0.2473 | 100% | **threshold_dependent** | amplitude_cutoff |
| `frac_units_suppressed` | 0.1028 | 0.09268 | 0.1688 | 0.25 | 100% | **threshold_dependent** | firing_rate |

### Files

- `dandi.html`: the session report: every flag with its evidence plot, the audits and the specification curves ([view](https://htmlpreview.github.io/?https://github.com/aslansd/ayar/blob/main/public_results/dandi.html), [file](https://github.com/aslansd/ayar/blob/main/public_results/dandi.html))
- [`dandi_curation.json`](https://github.com/aslansd/ayar/blob/main/public_results/dandi_curation.json): the repairs as a SpikeInterface curation
- [`dandi_scan.json`](https://github.com/aslansd/ayar/blob/main/public_results/dandi_scan.json), [`dandi_kept_scan.json`](https://github.com/aslansd/ayar/blob/main/public_results/dandi_kept_scan.json), [`dandi_multiverse.json`](https://github.com/aslansd/ayar/blob/main/public_results/dandi_multiverse.json): everything above, machine-readable

## Reproduce

```
pip install "ayar[nwb]" ONE-api ibllib dandi
export OPENALYX_USER=<user> OPENALYX_PASSWORD=<password>   # free account at openalyx.internationalbrainlab.org/signup
python examples/public_sessions.py --out public_results
```

The downloads (about 1.5 GB) go to `public_results/cache/` and `public_results/ONE/`, which
git ignores; everything else in `public_results/` is the committed output.

History: first run 2026-10-31 with ayar 0.4.0 (commit 8fdd17a); 2026-11-11 with 0.5.0.dev0
(commit bd6ffc3); this run 2026-11-14 with 0.5.0.

Versions: ayar 0.5.0, python 3.11.5, numpy 2.4.6, spikeinterface 0.105.4, pynwb 4.2.0, one 3.6.2, ibllib 4.1.0, dandi 0.81.0
