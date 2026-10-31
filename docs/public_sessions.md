# ayar on public sessions

The first run of ayar on real, public spike-sorted data: one IBL Neuropixels insertion and one session of the Steinmetz et al. 2019 dataset on DANDI.

Generated 2026-10-31 11:59 UTC by `examples/public_sessions.py` with ayar 0.4.0.

## Summary

| session | units | flags (errors / warnings) | finding audit | curation multiverse |
|---|---|---|---|---|
| IBL insertion da8dfec1-d265-44e8-84ce-6ae9c109b8bd | 1143 | 534 / 781 | mean_contrast_hz: nonspecific, frac_units_enhanced: robust, frac_units_suppressed: nonspecific (combined repair not comparable: too few unflagged units) | mean_contrast_hz: threshold_dependent, frac_units_enhanced: stable, frac_units_suppressed: stable |
| DANDI 000017: sub-Richards/sub-Richards_ses-20171031T120000.nwb | 778 | 179 / 13 | mean_contrast_hz: robust, frac_units_enhanced: shifted, frac_units_suppressed: shifted | mean_contrast_hz: sign_unstable, frac_units_enhanced: stable, frac_units_suppressed: threshold_dependent |

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
- **Run time:** scan + audit 1438.7 s, multiverse 353.2 s

### Sorting artifacts flagged

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

### Finding audit: condition_contrast (0-0.5 s after each event)

| number | baseline | verdict | repair that sets the verdict: change (random 95th pct) | not comparable with random repairs |
|---|---|---|---|---|
| `mean_contrast_hz` | -0.2023 | **nonspecific** | CONTAMINATION (remove 456): 139% (random 141%) | ALL_FLAGS: 143% |
| `frac_units_enhanced` | 0.2135 | **robust** | DRIFT_CONFOUND (restrict 30, remove 106): 4% (random 4%) | ALL_FLAGS: 14% |
| `frac_units_suppressed` | 0.217 | **nonspecific** | CONTAMINATION (remove 456): 11% (random 12%) | ALL_FLAGS: 15% |

### Curation multiverse

216 of 216 universes evaluated (grid: `firing_rate>=0,0.1,0.5,1  presence_ratio>=0,0.5,0.9  isi_contamination<=1,0.25,0.1  amplitude_cutoff<=0.5,0.1  label>=0,0.6,1`).

| number | all units | min | median | max | same sign | verdict | most influential threshold |
|---|---|---|---|---|---|---|---|
| `mean_contrast_hz` | -0.2023 | -0.9521 | -0.6924 | -0.2023 | 100% | **threshold_dependent** | label |
| `frac_units_enhanced` | 0.2135 | 0.1884 | 0.2014 | 0.2238 | 100% | **stable** | firing_rate |
| `frac_units_suppressed` | 0.217 | 0.217 | 0.3231 | 0.3646 | 100% | **stable** | label |

### Files

The HTML reports (every flag with its evidence plot, the specification curves) and the JSON and curation files are written next to `RESULTS.md` when you run the script; they are not included here (the IBL scan report alone is 0.7 MB).

## DANDI 000017: sub-Richards/sub-Richards_ses-20171031T120000.nwb

- **Source:** DANDI Archive, dandiset 000017, file sub-Richards/sub-Richards_ses-20171031T120000.nwb ([link](https://dandiarchive.org/dandiset/000017))
- **Data:** 778 units, 4,703,292 spikes, 2968.28 s, tier 0 (no amplitudes, no depths)
- **Events:** trials column 'feedback_type' at 'feedback_time'; -1: 74, 1: 186 trials
- **Run time:** scan + audit 4.2 s, multiverse 5.4 s

### Sorting artifacts flagged

| detector | errors | warnings | units involved |
|---|---|---|---|
| `CONTAMINATION` | 179 | 13 | 192 |

192 of 778 units are involved in at least one flag.

Examples (up to three per detector):

- `CONTAMINATION` (error), units 0: 34 refractory violations (<1.5 ms) imply 34% of its spikes come from other neurons
- `CONTAMINATION` (error), units 2: 29 refractory violations (<1.5 ms) imply 50%+ of its spikes come from other neurons
- `CONTAMINATION` (error), units 11: 24 refractory violations (<1.5 ms) imply 50%+ of its spikes come from other neurons

Not checked, or only partly:

- `DUPLICATE_UNIT`: 302253 unit pairs and no depths to restrict them; add amplitudes/depths (tier 1) or raise max_pairs
- `SPLIT_UNIT`: 302253 unit pairs and no depths to restrict them; add amplitudes/depths (tier 1) or raise max_pairs
- `OVERLAP_HOLE`: 302253 unit pairs and no depths to restrict them; add amplitudes/depths (tier 1) or raise max_pairs
- `DRIFT_CONFOUND`: needs per-spike amplitudes or depths (tier 1)

### Finding audit: condition_contrast (0-0.5 s after each event)

| number | baseline | verdict | repair that sets the verdict: change (random 95th pct) | not comparable with random repairs |
|---|---|---|---|---|
| `mean_contrast_hz` | 0.06613 | **robust** | CONTAMINATION (remove 192): 2% (random 65%) | - |
| `frac_units_enhanced` | 0.1607 | **shifted** | CONTAMINATION (remove 192): 12% (random 8%) | - |
| `frac_units_suppressed` | 0.1028 | **shifted** | CONTAMINATION (remove 192): 17% (random 12%) | - |

### Curation multiverse

36 of 36 universes evaluated (grid: `firing_rate>=0,0.1,0.5,1  presence_ratio>=0,0.5,0.9  isi_contamination<=1,0.25,0.1`).

| number | all units | min | median | max | same sign | verdict | most influential threshold |
|---|---|---|---|---|---|---|---|
| `mean_contrast_hz` | 0.06613 | -0.1321 | -0.01908 | 0.07871 | 56% | **sign_unstable** | isi_contamination |
| `frac_units_enhanced` | 0.1607 | 0.115 | 0.135 | 0.1796 | 100% | **stable** | isi_contamination |
| `frac_units_suppressed` | 0.1028 | 0.09268 | 0.1588 | 0.2139 | 100% | **threshold_dependent** | firing_rate |

- note: dropped rule amplitude_cutoff<=0.5,0.1: metric 'amplitude_cutoff' unavailable (have: firing_rate, isi_contamination, isi_violations, n_spikes, presence_ratio)

### Files

The HTML reports (every flag with its evidence plot, the specification curves) and the JSON and curation files are written next to `RESULTS.md` when you run the script; they are not included here (the IBL scan report alone is 0.7 MB).

## Reproduce

```
pip install "ayar[nwb]" ONE-api ibllib dandi
export OPENALYX_USER=<user> OPENALYX_PASSWORD=<password>   # free account at openalyx.internationalbrainlab.org/signup
python examples/public_sessions.py --out public_results
```

This page was produced by that command on 2026-10-31 (on a MacBook Pro, Python 3.11), then rewritten with
`--rebuild` after a fix to how the finding audit summarises repairs that have no random controls; the
analysis itself was not re-run and no number changed.

Versions: ayar 0.4.0, python 3.11.5, numpy 2.4.6, spikeinterface 0.105.4, pynwb 4.2.0, one 3.6.2, ibllib 4.1.0, dandi 0.81.0 (the run on the laptop)
