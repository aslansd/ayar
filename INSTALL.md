# Installing ayar

## Just the tool

```bash
pip install ayar
```

That is everything for scanning sorted spikes. ayar needs **Python 3.10 or newer** and two
runtime dependencies, **numpy and scipy**. It needs no account, no GPU and no network.

Verify:

```bash
python -c "import ayar; print(ayar.__version__)"
ayar doctor
```

`ayar doctor` prints the versions, says which optional packages are present and what each
enables, and runs a self-check on a synthetic session:

```
ayar 0.4.0
python 3.13.18 (/path/to/python3)
numpy 2.5.4, scipy 1.18.1
spikeinterface: not installed (SortingAnalyzer input, extra [spikeinterface])
pynwb: not installed (NWB input, extra [nwb])
daftar: not installed (provenance with --daftar, extra [provenance])
self-check: 12/12 planted artifacts found in a 600 s synthetic session -> ok
```

With only the core installed, ayar reads `.npz` bundles, Phy/Kilosort output folders and
IBL ALF folders, and every command except `hybrid` works.

---

## Optional extras

Each extra adds one kind of input or output. Install only what you use.

| Extra | Installs | Enables | Tested with |
|---|---|---|---|
| `ayar[spikeinterface]` | `spikeinterface>=0.101` | reading `SortingAnalyzer` / `Sorting` objects and saved analyzer folders; `ayar hybrid`; `ayar.metrics.from_spikeinterface` | 0.105.4 |
| `ayar[nwb]` | `pynwb>=2.5` | reading NWB units and trials tables (`ayar.from_nwb`, `.nwb` paths) | 4.2.0 |
| `ayar[provenance]` | `daftar>=1.2` | `--daftar` on `scan`, `multiverse` and `compare` | 1.2.0 |
| `ayar[all]` | all three | everything above | |
| `ayar[dev]` | all three plus `pytest` | the full test suite | pytest 9 |

```bash
pip install "ayar[spikeinterface]"
pip install "ayar[nwb]"
pip install "ayar[provenance]"
pip install "ayar[all]"
```

`spikeinterface` is the large one: it pulls in a substantial scientific stack. If you only
need to read a Kilosort folder, you do not need it.

---

## For `ayar hybrid` and the real-sorter example

`ayar hybrid run` and `examples/real_sorters.py` run spike sorters through SpikeInterface.
The sorters are separate installs:

```bash
pip install "ayar[spikeinterface]"
pip install "spikeinterface[tridesclous2,spykingcircus2]" mountainsort5   # CPU sorters
```

These three run on a CPU and were used for the results in the README (mountainsort5 0.5.9).
Kilosort 4 needs a GPU; install it as its own documentation describes and pass
`--sorter kilosort4`. `ayar hybrid make` and `ayar hybrid score` need no sorter at all: you
can sort the hybrid recording with any pipeline you already use.

---

## For the public-data example

`examples/public_sessions.py` downloads one IBL insertion and one DANDI session:

```bash
pip install "ayar[nwb]" ONE-api ibllib dandi
export OPENALYX_USER=<user> OPENALYX_PASSWORD=<password>
python examples/public_sessions.py --out public_results
```

- **IBL needs a free personal account.** Register at
  <https://openalyx.internationalbrainlab.org/signup>. IBL's public server no longer has a
  shared login. Without credentials the script skips IBL and says why in `RESULTS.md`.
- **DANDI needs no account.**
- **Expect about 1.5 GB of downloads** (most of it the IBL spike arrays) and, with 0.5,
  about 15 minutes on a laptop besides the downloads (IBL: scan and audit 5 minutes,
  multiverse 8).
- **Commit the results, never the downloads.** The reports, JSON files and `RESULTS.md` in
  `public_results/` are small (about 3.5 MB) and are what [docs/public_sessions.md](docs/public_sessions.md)
  links to. The downloads go to `public_results/cache/` and `public_results/ONE/`, which
  `.gitignore` excludes; see [PUBLISHING.md](PUBLISHING.md).

Tested with ONE-api 3.6.2, ibllib 4.1.0 and dandi 0.81.0.

---

## For development

```bash
git clone https://github.com/aslansd/ayar.git
cd ayar
pip install -e ".[dev]"
pytest -q
```

See [TESTING.md](TESTING.md) for what the suites cover and what a skip means.

---

## Checking an installation

```bash
ayar doctor
```

It exits 1 if the self-check fails, so it is usable in CI. **An optional package listed as
installed means it imports**, not that every feature built on it works against that
version. The adapter tests run real workloads and will tell you:

```bash
pytest tests/test_adapters.py tests/test_public_readers.py -rs
```

`-rs` prints the reason for each skip. A skip that names a missing package is ordinary.
