# Roadmap

*Last revised 14 November 2026, against ayar 0.5.0 (§3 done and confirmed on the public sessions).*

Every number below was read from the published package, the PyPI API or a run whose output
is in this repository. Where a number comes from synthetic data, it says so.

---

## Where this stands

**0.5.0** in the repository (0.4.0 on PyPI until it is published). Apache 2.0, two runtime
dependencies (**numpy, scipy**), **105 tests** (80 in 0.4.0), Python 3.10+.
First release 30 October 2026.

| release | published (UTC) | what it added |
|---|---|---|
| 0.1.0 | 30 Oct 2026 12:51 | bundle format, Phy/Kilosort reader, three detectors, finding audit, `synth`, `validate` |
| 0.2.0 | 30 Oct 2026 17:25 | `SPLIT_UNIT`, `CONTAMINATION`, `ayar multiverse`, SpikeInterface and NWB readers |
| 0.3.0 | 31 Oct 2026 04:59 | `ayar compare` across sorters, HTML reports, daftar provenance |
| 0.4.0 | 31 Oct 2026 12:32 | `ayar hybrid`, stable epochs, curation export, IBL readers, first public-data results |

| | Status |
|---|---|
| Five detectors: duplicate, split, overlap hole, contamination, drift | shipped |
| Finding audit with matched random controls; `uncontrolled` when no controls are possible | shipped |
| `scan` · `multiverse` · `compare` · `session` · `hybrid` · `synth` · `validate` · `info` · `doctor` | shipped |
| `--keep` curated units · all-pairs statistics · probes | shipped in 0.5.0 |
| Readers: Phy/Kilosort, SpikeInterface, NWB, IBL (ONE and ALF), plain arrays | shipped |
| HTML reports · SpikeInterface curation export · daftar provenance | shipped |
| Results on public data (one IBL insertion, one DANDI session) | shipped, see [docs/public_sessions.md](docs/public_sessions.md) |
| Ground truth on real tissue | **none yet**: `ayar hybrid` is the tool for it, not yet run on a public raw recording |
| **External users** | **none yet: the thing that actually matters** |

```
tests/test_compare_html.py        10    tests/test_audit.py               6
tests/test_v04.py                 11    tests/test_bundle.py              6  (+4 parametrised)
tests/test_metrics_multiverse.py   9    tests/test_cli_io.py              6
tests/test_split_contamination.py  9    tests/test_adapters.py            6
tests/test_detectors.py            7    tests/test_public_readers.py      4
                                        tests/test_stats.py               2
tests/test_pairstats.py           10    tests/test_version.py             3
tests/test_v05.py                 12
                                                                         --
                                                                        105
```

---

## 1. What the evidence says, and what it does not

There are three levels of evidence, and they should not be confused.

**Synthetic sessions** (`ayar validate --sessions 20 --seed 100`): 236 of 240 planted
artifacts found, no false flags, no alarms on the controls (real synchrony, real rate
changes). This shows the detectors do what they claim. It says nothing about how often
they fire on real recordings, because ayar's own artifacts are cleaner than real ones.

**Real sorters on a simulated recording** (`examples/real_sorters.py`): tridesclous2,
spykingcircus2 and mountainsort5 on a 10-minute, 12-neuron SpikeInterface simulation, every
flag checked against the known spike trains. The ground truth got zero flags; all 6 split
flags were right; 7 of 13 split neurons were caught and the other 6 each had a fragment
too small to test. With `ayar hybrid` on the same recording, all 5 flags that touched an
injected unit were right. Real sorter behaviour, simulated tissue.

**Public data** ([docs/public_sessions.md](docs/public_sessions.md)): an IBL insertion
(1143 units, 72 min) and a Steinmetz et al. 2019 session on DANDI (778 units, 49 min). ayar
ran end to end on both, and the finding audit and multiverse produced sensible, cautious
verdicts. **There is no ground truth**, so the flags there are hypotheses with evidence,
not verified errors.

The gap between the second and third levels is the one that matters: nothing yet
measures ayar's accuracy on real tissue. Closing it is §3.3.

---

## 2. What real data taught

Each of these was found by running ayar on something real, and each would have shipped
unnoticed on synthetic data alone. Worth remembering the next time a feature looks
finished.

- **A sorter discarding near-simultaneous spikes looks like a shared refractory period.**
  MountainSort 5 produced a false split until the split test also required the 1.0-1.5 ms
  band to be empty (0.3.0).
- **Duplicates can be time-shifted.** spykingcircus2 sorted one neuron twice at a 0.37 ms
  offset, invisible to a ±0.25 ms window; the detector now finds the lag first (0.3.0).
- **A template-matching sorter loses a drifting unit all at once.** tridesclous2 kept a
  fading unit's spikes whole, then dropped the unit, so neither rate nor amplitude showed
  gradual loss; the fade test was added for it (0.4.0).
- **A verdict without controls is not a verdict.** On the IBL insertion, 746 of 1143 units
  were flagged, too few clean units were left to draw random controls, and the audit
  reported `sensitive` anyway. It now says `uncontrolled`, and the summary verdict comes
  from the repairs that were controlled (0.4.0).
- **Downloads must be verified.** A truncated DANDI file was reused by the script and
  failed with an HDF5 error; downloads are now size-checked and atomic (0.4.0).

And one about the repository rather than the code: **0.4.0 reached GitHub with unresolved
merge-conflict markers** in `CHANGELOG.md` and `tests/test_v04.py`, and the `.git` folder
grew to about 800 MB from committed public data. Both were fixed before the PyPI upload;
[PUBLISHING.md](PUBLISHING.md) now checks for both.

---

## 3. Next: v0.5, speed and coverage

Ordered by how much each one unblocks. Each has a test of done.

### 3.1 A test that the two version numbers agree — done (0.5.0)

*Done differently:* there is now only one number. `pyproject.toml` reads it from
`src/ayar/__init__.py`, and `tests/test_version.py` checks the installed metadata and that
no second number reappears.


The version lives in `pyproject.toml` and in `src/ayar/__init__.py`. daftar shipped two
releases that reported the wrong version for exactly this reason. Add a test asserting
`ayar.__version__ == importlib.metadata.version("ayar")`.
*Done when:* the test exists and fails if either number is bumped alone.

### 3.2 Pair statistics for all units at once — done (0.5.0)

`ayar.pairstats` counts all pairs in one sweep, exactly as the per-pair searches did.
Re-run on the laptop on 11 November ([docs/public_sessions.md](docs/public_sessions.md)):
the IBL insertion scans with the finding audit in **300.7 s** (was 1438.7 s) with the same
1315 flags, message for message, and the DANDI session gets the duplicate, split and
overlap checks on all 302,253 pairs (54 s). Both tests of done are met; the IBL time is
right at the 5-minute line.

What it showed: tier-0 pair flags need context ayar does not have at tier 0 (which units
are neighbours, which probe), so §3.4 matters more than it did. The drift detector (about
60 s on an IBL-sized session, 370,000 small histograms) is now the slowest part of a scan,
and the multiverse (8 minutes on IBL) the slowest command.


The pair detectors loop over unit pairs. On the IBL insertion the scan and audit took
**24 minutes**, and on the DANDI session, which has no spike depths, the pair detectors did
not run at all: 302,253 pairs exceed the 20,000-pair cap. Counting coincidences for every
pair in one vectorised pass over the sorted spike train (as `ayar.matching` already does
between two sortings) fixes both, and cheaper audit controls fix the rest of the time.
*Done when:* the IBL insertion scans with the finding audit in under 5 minutes on a laptop,
and the DANDI session gets duplicate, split and overlap checks.

### 3.3 Restrict a scan to curated units — done (0.5.0)

`--keep RULE` on every command, `ayar.keep()` in Python; rules on ayar's metrics, the
reader's (IBL `label`, NWB `phy_annotations`) or a table. `examples/public_sessions.py`
scans IBL `label>=1` and Steinmetz `phy_annotations>=2` units next to all units. Run on 14
November ([docs/public_sessions.md](docs/public_sessions.md)): of IBL's 298 good units 64 are
flagged (746 of all 1143), with no contamination errors but 8 duplicate pairs, and on the good
units the audit finds the mean contrast `shifted` (20 % against 15 % for random repairs).


IBL analyses keep units with `label == 1`; most labs curate first. ayar scanned all 1143
clusters, so its headline count mixes units nobody would analyse with units everybody
would. A `--keep "label>=1"` option (reusing the multiverse's rule syntax and the metrics
table) makes the result answer the question a lab actually has.
*Done when:* `docs/public_sessions.md` reports flags among IBL-good units next to all units.

### 3.4 Unit depths from more NWB layouts — done (0.5.0)

The Steinmetz files were written by
[SteinmetzLab/dataToNWB](https://github.com/SteinmetzLab/dataToNWB): `cluster_depths` per
unit, ragged `spike_amps` and `spike_depths`, the probe as `electrode_group`, curation in
`phy_annotations`. ayar 0.4 looked for none of these names. 0.5 reads them (tested on a file
written the same way), keeps units on different probes apart, and `ayar info file.nwb` shows
any file's columns. Confirmed on 14 November: the DANDI file reads at tier 1 with two probes,
and its pair flags fall from 240 overlap holes and 112 splits (tier 0) to 9 and 20.
*Not done:* a check for near-simultaneous spikes shared across probes. ayar never compares
units on different probes now, so shared noise events, which the tier-0 run hinted at, go
unflagged.


The Steinmetz NWB file gave ayar spike times only (tier 0). Its units table probably holds
depth in a column the reader does not know. List the columns of one file, then teach
`from_nwb` the layouts in use on DANDI.
*Done when:* the DANDI session in `docs/public_sessions.md` runs at tier 1.

### 3.5 One session report — done (0.5.0)

`ayar session` (and `ayar.session()`): scans of all and kept units, the multiverse and the
comparison across sorters on one page, with a summary that links to each part. The public
sessions now produce one `ibl.html` and one `dandi.html`.


`scan`, `multiverse` and `compare` each write their own HTML file. One page per session,
with the three as sections, is what a reader wants to open.

---

## 4. Later: ground truth on real tissue

- **`ayar hybrid` on a public raw recording.** IBL raw data is available through ONE.
  Inject units, sort with a real pipeline (Kilosort 4 needs a GPU), score. This is the
  first accuracy number on real tissue, and the most important result ayar does not have.
- **Hybrid units that drift with the probe** (SpikeInterface motion objects), instead of
  stationary templates whose amplitude fades.
- **Thresholds calibrated on hybrids** rather than on synthetic sessions.
- **A small public benchmark**: five to ten sessions across labs and sorters, scanned the
  same way, as a table in the README.

These waited on §3.2: at 24 minutes a session, ten sessions was an afternoon of waiting per
change. With 0.5 it should be minutes; confirm on the public sessions first.

---

## 5. Announcing

- **IBL.** An introduction for `int-brain-lab/ibl-sorter` was drafted on 31 October,
  written as questions about their output rather than claims about it. Record the link
  here once it is posted, and treat any reply as the most valuable feedback available.
- **pyOpenSci** asks for three months of sustained development: from 30 October 2026,
  that is **30 January 2027**. A steady commit history from §3 is what makes that case.
- **The wider community** (SpikeInterface, Neuromatch, SNUFA): after §3.2 and §3.3, when
  results on public data are fast to reproduce and answer the curated-units question.

The rules that held for daftar hold here: post once and never bump; never the same text in
two places on the same day; ask moderators before posting in Slack or Discord; ask for
criticism, not stars; reply to everyone, especially the sceptical.

---

## 6. What signals something

| Signal | What it means |
|---|---|
| Stars, downloads | Almost nothing: bookmarks, mirrors and bots. |
| A reply from a sorter's maintainers | Real: someone who knows the output read the flags. |
| **An issue from a stranger** | **First evidence someone ran it on their own data.** |
| **A flag a user confirms or refutes against their own curation** | The ground truth ayar does not have. |
| **A feature request** | Strongest: they have a use case and want it to fit. |

---

## 7. Not on the list

- **Sorting spikes.** ayar judges what sorters produce; it should never become one.
- **A curation GUI.** Phy and SpikeInterface's tools do this well; ayar exports curations
  for them instead.
- **More unit-level quality metrics.** SpikeInterface, Bombcell and UnitRefine own that
  ground. ayar's metrics exist only to feed its own detectors and the multiverse.
- **A hosted service.** It has to run on a laptop, on an air-gapped cluster, and with no
  account.

---

## 8. The order

1. ~~§3.1, the version test~~ (done).
2. ~~§3.2, all-pairs statistics~~ (done; re-run on public data 11 November).
3. ~~§3.3, §3.4, §3.5~~ (done in 0.5.0, confirmed on the public sessions 14 November);
   publish 0.5.0.
4. Post the IBL introduction, if it is not posted yet.
5. A faster drift detector (now the slowest part of a scan) and multiverse.
6. §4, hybrid on a public raw recording.
7. 30 January 2027: pyOpenSci.

---

## Honest status

The software does what it says on synthetic data, on real sorters' output with a known
answer, and end to end on two public sessions. What it does not have is an accuracy number
on real tissue, or a single user outside the project. The first is §4; the second waits on
someone running it on their own data and opening an issue.
