# Changelog

## 0.4.0

### New
* **`ayar hybrid`: check ayar on your own recording.** `make` injects known units into a
  recording with SpikeInterface's hybrid generator (some of them fading over the session, the
  way a drifting neuron is lost); you sort it with your own pipeline; `score` reports what the
  sorter did to each injected unit (found, partly found, split, merged, missed) and checks every
  flag that touches an injected unit against the truth. `run` does all three with a
  SpikeInterface sorter. Python: `ayar.hybrid.make / score / score_folder / run`.
* **Stable epochs: drifting units are repaired, not discarded.** `DRIFT_CONFOUND` reports each
  unit's stable epoch (windows where it still detects >= 90 % of its spikes); the finding audit
  restricts the unit to it (`restrict` repair, with matching random controls), and removes the
  unit only if the epoch covers under 30 % of the session.
* **Epoch-aware bundles:** `Bundle.restrict()`, `unit_epochs()`, `in_epochs()`,
  `observed_duration()`; rates and metrics use the observed time; epochs are saved in `.npz`.
  `ayar.examples.condition_contrast` counts only the trials inside a unit's epochs.
* **Curation export** (`ayar scan --export-curation`): SpikeInterface curation format v2
  (merges for error-level duplicates and splits, removals, an `ayar` label per flagged unit,
  stable epochs in `ayar_epochs`), validated and applied with SpikeInterface's own
  `apply_curation`. `--export-phy` writes `cluster_ayar.tsv` for Phy; `--curation` applies a
  curation file before scanning, so a session can be re-scanned after curation.
* **Attribution in `compare`:** for a number that is not consistent across sorters, each unit
  found by only some sortings is left out in turn and the units that move it most are listed
  (text, JSON and HTML).
* **Fade test in `DRIFT_CONFOUND`:** an amplitude that walks steadily down (or up) until the
  unit vanishes (or appears), the way a template-matching sorter loses a drifting neuron.
* **IBL readers:** `ayar.from_ibl()` (IBL `SpikeSortingLoader` output, with trials as
  feedback / stimulus / choice events and IBL's cluster metrics for the multiverse) and
  `ayar.from_alf()` (ALF files on disk; also through `ayar.load()`).
* `ayar.from_nwb(..., shift_negative=True)` for sessions whose spike times start before zero.
* **`examples/public_sessions.py`:** downloads a public IBL insertion (needs a free IBL account,
  read from `OPENALYX_USER` / `OPENALYX_PASSWORD`) and a DANDI session (Steinmetz et al. 2019 by
  default; no account), runs scan, the finding audit and the multiverse, and writes
  `RESULTS.md` plus the HTML reports and curation files.

### Changed
* Merges in the audit and in curation count copies within ±1.25 ms once (time-shifted
  duplicates).

## 0.3.0

### New
* **`ayar compare`: does the finding survive a different spike sorter?** Matches units between
  a reference sorting and each other sorting (agreement within ±0.4 ms, one-to-one Hungarian
  matching, minimum agreement 0.5), recomputes the finding on every sorting and on the
  consensus units, and gives each number a verdict (`consistent`, `sorter_dependent`,
  `sign_unstable`). Python: `ayar.compare(...)`, `ayar.match_units(...)`.
* **Single-file HTML reports** (`--html` on `scan`, `multiverse`, `compare`): inline SVG
  evidence plots for every flag, finding-audit and specification-curve charts, data tables,
  tooltips, light and dark themes; no third-party library and no network access needed.
* **Provenance through daftar** (`--daftar`, extra `ayar[provenance]`): records input hashes,
  thresholds, version and environment, flags, the finding's numbers and verdicts, and report
  files, so runs can be compared with `daftar diff`.
* `ayar synth --sorters N` writes N-1 re-sortings of the synthetic session (conservative and
  liberal styles, units renumbered) for trying `compare`; `ayar.synth.sorter_variants()`.
* `examples/real_sorters.py`: sorts a simulated recording with tridesclous2, spykingcircus2
  and mountainsort5, scans every sorting, checks each flag against the ground truth, and
  compares the sorters (`--reuse` re-scans existing sorter output without sorting again).
* `--events` for `ayar multiverse`.

### Changed
* `SPLIT_UNIT` (refractory signature) sets aside coincidences within ±0.25 ms as double
  detections, requires the 1.0-1.5 ms band to be empty as well (a sorter that discards
  near-simultaneous spikes empties only the centre of the correlogram, which produced a false
  split on MountainSort 5 output), and checks the merged train after removing double
  detections. Nearby pairs too sparse to test are reported as partly checked.
* `DUPLICATE_UNIT` finds time-shifted duplicates (two templates of one neuron aligned up to
  ±1 ms apart) by locating the lag where coincidences pile up; the lag is in the evidence, and
  the audit counts shifted copies once when merging. Warning-level duplicates (20-50 % shared)
  no longer claim "one neuron": they may be a cluster of collision events.
* Units with fewer than `min_spikes` spikes are reported as partly checked by `SPLIT_UNIT`
  (small units are often fragments of a neuron).
* A pair flagged `DUPLICATE_UNIT` is no longer also reported as `SPLIT_UNIT`.
* `ayar doctor` lists what each optional dependency enables.

## 0.2.0

### New
* **`SPLIT_UNIT` detector.** One neuron reported as two units, by two signatures: a pair that
  never fires within ±1.5 ms of each other and merges into a clean train (*refractory*), or one
  unit fading out as a neighbour with matching rate and amplitude fades in (*handoff*).
* **`CONTAMINATION` detector.** Refractory violations converted to a contamination fraction
  (Hill et al. 2011), with the likely source neighbour when one can be identified.
* **`ayar multiverse`.** Recomputes a finding across every combination of curation thresholds
  (firing rate, presence ratio, ISI contamination, amplitude cutoff, or any metric in your own
  table) and reports range, sign agreement, the most influential threshold and a verdict
  (`stable`, `threshold_dependent`, `sign_unstable`).
* **`ayar.metrics`.** Per-unit quality metrics computed from a bundle, read from a CSV/TSV table,
  or taken from a SpikeInterface analyzer's `quality_metrics` and `template_metrics`.
* **SpikeInterface adapter.** `ayar.from_spikeinterface(...)` reads a `SortingAnalyzer` or
  `Sorting` (amplitudes, spike and unit locations, duration); `ayar.load()` opens saved
  analyzer folders and `.zarr` analyzers.
* **NWB adapter.** `ayar.from_nwb(...)` / `ayar.load("x.nwb")` reads the units and trials tables;
  `--trial-label` on the CLI picks the condition column.
* `Bundle.merge(pairs, dedupe_s)`, with chains resolved and duplicate spikes counted once.
* `SynthConfig.clean()` for a synthetic session with no artifacts.
* Optional extras: `ayar[spikeinterface]`, `ayar[nwb]`, `ayar[all]`.

### Changed
* **The finding audit repairs instead of only removing.** Duplicates and splits are merged;
  random controls apply the same repair (merging nearest unflagged neighbours, or removing
  random unflagged units). The text table shows the repair (`merge 2, remove 3`).
* `OVERLAP_HOLE` no longer reports pairs whose whole refractory window is empty; those are
  `SPLIT_UNIT`.
* Flags that describe one cause are reported once (a handed-off unit is not also drifting; a
  contaminated unit's dip with its source is not also an overlap hole).
* `DRIFT_CONFOUND` compares windows at equal spike counts (the amplitude-cutoff estimate is
  biased by sample size), and requires the estimated loss to be large enough to explain the
  rate drop. Short sessions use shorter windows (down to 10 s).
* `ayar.examples.condition_contrast` reports significant units (Welch t-test, p < 0.01):
  `frac_units_enhanced` and `frac_units_suppressed`; it is vectorised.
* Faster `Bundle.without()` and `Bundle.merge()` (no re-sorting, index derived from the parent).

## 0.1.0

First release: bundle format, Phy/Kilosort reader, `DUPLICATE_UNIT`, `OVERLAP_HOLE` and
`DRIFT_CONFOUND` detectors, finding audit with random-drop controls, synthetic sessions with
planted artifacts, `ayar scan | synth | validate | info | doctor`.
