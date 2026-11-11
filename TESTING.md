# Testing ayar

## The short version

```bash
pip install -e ".[dev]"
pytest -q
```

**93 tests are collected in every environment**; what changes is how many run:

| Environment | Result | Time |
|---|---|---|
| `pip install ayar pytest` (numpy and scipy only) | **82 passed, 11 skipped** | about 1 minute |
| `pip install -e ".[dev]"` (SpikeInterface, pynwb, daftar) | **93 passed** | about 4 minutes |

Both were measured on 11 November 2026 with Python 3.13, against ayar 0.4.0.

Every skip should name a missing optional package:

| Missing | Tests skipped | Where |
|---|---|---|
| `spikeinterface` | 7 | `test_adapters.py` (5), `test_v04.py` (2: curation validation, hybrid scoring) |
| `pynwb` | 3 | `test_adapters.py` (1), `test_public_readers.py` (2) |
| `daftar` | 1 | `test_compare_html.py` (provenance) |

**A skip for any other reason means something is wrong.** Print the reasons with:

```bash
pytest -q -rs
```

---

## The suites

| File | Tests | Needs | What it covers |
|---|---|---|---|
| `test_bundle.py` | 6 (+4 parametrised) | nothing | the bundle: sorting, indexing, save and load, validation errors |
| `test_stats.py` | 2 | nothing | coincidence counts against brute force; the amplitude-cutoff estimate |
| `test_pairstats.py` | 10 | nothing | all-pairs counts equal pair-by-pair counts for every ordered pair (also on a 30 kHz grid, where lags sit on window bounds); tier-0 sessions beyond the old 20,000-pair cap; the spike-pair budget; skipped controls keep verdicts |
| `test_version.py` | 3 | nothing | one version number: installed metadata equals `ayar.__version__`, none in `pyproject.toml` |
| `test_detectors.py` | 7 | nothing | every planted artifact found with no false flags; controls never flagged; drift severity; tier 0; thresholds |
| `test_split_contamination.py` | 9 | nothing | split modes, contamination sources, time-shifted duplicates, merges, one report per cause |
| `test_audit.py` | 6 | nothing | the finding audit: verdicts, failing and malformed findings, loading findings from files |
| `test_metrics_multiverse.py` | 9 | nothing | Hill contamination, presence ratio, metric tables, the multiverse and its CLI |
| `test_compare_html.py` | 10 | (daftar for 1) | unit matching, `compare`, HTML reports, escaping, the CLI, provenance |
| `test_v04.py` | 11 | (SpikeInterface for 2) | epochs and stable-epoch repair, curation export and apply, attribution, uncontrolled verdicts, hybrid scoring |
| `test_public_readers.py` | 4 | (pynwb for 2) | IBL events and readers, NWB negative times, `examples/public_sessions.py` end to end on local files |
| `test_adapters.py` | 6 | SpikeInterface, pynwb | readers against the real libraries |
| `test_cli_io.py` | 6 | nothing | the CLI's exit codes, JSON output, external events, the Phy reader, `doctor` |

`test_adapters.py` is the only suite that can catch an upstream change breaking a reader.
**Re-run it after upgrading SpikeInterface or pynwb**, not only at release:

```bash
pytest tests/test_adapters.py tests/test_public_readers.py -v -rs
```

---

## The validation run

The tests check that the code does what it says. `ayar validate` checks that the detectors
find what they are meant to find, on synthetic sessions with planted artifacts and controls
that must stay unflagged:

```bash
ayar validate --sessions 20 --seed 100
```

Expected for 0.4.0:

```
  detector         planted  found  false ctrl alarms sensitivity precision
  DUPLICATE_UNIT        40     40      0           0        1.00      1.00
  SPLIT_UNIT            60     60      0           0        1.00      1.00
  OVERLAP_HOLE          40     40      0           0        1.00      1.00
  CONTAMINATION         40     39      0           0        0.97      1.00
  DRIFT_CONFOUND        60     57      0           0        0.95      1.00

  finding audit: in 19 session(s) drift manufactured 'suppressed' units; ayar called that
  number SENSITIVE or FLIPPED in 19

  PASS (min sensitivity 0.8, min precision 0.8, no control alarms)
```

It exits 1 on FAIL. **Any change to a detector or to the audit should leave this table
unchanged or better**, and a change in it belongs in the changelog. A drop from 19 to 18 in
the last line is how the 0.4.0 audit change was caught and redesigned before release.

---

## Checks beyond the test suite

These take longer or need downloads, so they are not part of `pytest`. Run them when the
detectors, the audit or a reader change.

**Real sorters with a known answer** (needs SpikeInterface and the CPU sorters, see
[INSTALL.md](INSTALL.md); a few minutes for 2 minutes of recording):

```bash
python examples/real_sorters.py --duration 120 --out real_sorters
python examples/real_sorters.py --duration 120 --out real_sorters --reuse   # re-scan only
```

It prints every flag with whether it was right, judged against the simulated neurons. The
ground truth must get zero flags. The sorters are not deterministic, so counts vary a little
between runs; a *wrong* flag on a pair of different neurons is what to look for.

**Hybrid units in a recording** (`ayar hybrid`): inject units with a known answer, sort,
and score every flag that touches an injected unit:

```bash
ayar hybrid run real_sorters/recording hybrid --sorter tridesclous2 --units 10 --fading 3
```

**Public data** (downloads about 1.5 GB; needs an IBL account, see INSTALL.md):

```bash
python examples/public_sessions.py --out public_results
python examples/public_sessions.py --out public_results --rebuild   # rewrite RESULTS.md only
```

There is no ground truth here: this checks that ayar runs end to end on real data and that
its verdicts stay sensible. After a change that affects verdicts, `--rebuild` regenerates
`RESULTS.md` from the saved outputs without re-running the analysis; anything that changes
the scan itself needs the full run, and `docs/public_sessions.md` updated from it.

---

## Properties worth preserving

Each of these was wrong once. A test now pins it; if a change makes one of these tests fail,
the change is what needs fixing.

1. **Controls are never flagged** (`test_controls_not_flagged`). Real synchrony and real
   rate changes over a session must not look like artifacts.
2. **A verdict needs random controls** (`test_uncontrolled_when_most_units_are_flagged`,
   `test_summary_verdict_ignores_uncontrolled_rows`). With too few clean units to compare
   against, the verdict is `uncontrolled`, never `sensitive`, and it does not decide the
   summary when a controlled repair exists.
3. **One cause, one report** (`test_reconcile_drops_double_reports`). A handed-off unit is
   not also drifting; a duplicate is not also a split; a contaminated unit's dip with its
   source is not also an overlap hole.
4. **Merges count copies once** (`test_merge_chain_and_dedupe`, `test_time_shifted_duplicate`),
   including copies offset by up to a millisecond.
5. **Untestable is not clean** (`test_tiny_units_reported_as_partly_checked`,
   `test_too_many_pairs_without_depths_is_reported`). What ayar could not check is listed
   under *not checked*, never silently passed.
6. **Reports escape what users name** (`test_html_escapes_names`). Finding names and keys
   come from user code and go into HTML.

---

## Before a release

```bash
pytest -q                                   # 93 passed with [dev]
ayar validate --sessions 20 --seed 100      # PASS, table as above
ayar doctor                                 # self-check ok
python -m build && python -m twine check dist/*
```

Then install the built wheel into a clean virtualenv and run `ayar doctor` there. See
[PUBLISHING.md](PUBLISHING.md) for the full sequence.
