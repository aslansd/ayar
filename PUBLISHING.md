# Publishing ayar

## The release, start to finish

```bash
pip install build twine
```

**1. Bump the version, in one place.** Since 0.5 the version lives only in
`src/ayar/__init__.py`; `pyproject.toml` reads it from there (`dynamic = ["version"]`):

```bash
# src/ayar/__init__.py
__version__ = "0.5.0"
```

daftar shipped two releases that reported the wrong version because it had two numbers and
only one was bumped. `tests/test_version.py` fails if a second number reappears in
`pyproject.toml`, or if the installed metadata disagrees with `ayar.__version__` (an old
editable install: reinstall with `pip install -e .`).

**2. Write the changelog entry first, not last.** If you cannot say in a paragraph why a
change matters to someone checking a finding, the change is probably not finished.

**3. Verify.**

```bash
pytest -q                                   # 93 passed with [dev]; see TESTING.md
ayar validate --sessions 20 --seed 100      # must print PASS
ayar doctor                                 # self-check ok
grep -rn "^<<<<<<<\|^>>>>>>>\|^=======$" --include="*.py" --include="*.md" --include="*.toml" .
```

The last line must print nothing. 0.4.0 reached GitHub with unresolved merge-conflict
markers in `CHANGELOG.md` and `tests/test_v04.py`; the test file would not even import.

**4. Build and check.**

```bash
rm -rf dist build src/*.egg-info
python -m build
python -m twine check dist/*
tar tzf dist/ayar-*.tar.gz | grep -ciE "public_results|cache|\.html"   # must print 0
```

The last check matters because `public_results/` (from `examples/public_sessions.py`)
holds over a gigabyte of downloaded data. `pyproject.toml` lists exactly what goes into
the sdist (`src`, `tests`, `examples`, `docs` and the top-level documents) and excludes
`public_results`, caches and HTML files, but a check you can see beats a rule you trust.

**5. Test the artifact, not the source tree.** This catches packaging mistakes the tests
cannot see, such as a module missing from the wheel:

```bash
python -m venv /tmp/check
/tmp/check/bin/pip install dist/ayar-*.whl
/tmp/check/bin/python -c "import ayar, importlib.metadata as m; print(ayar.__version__, m.version('ayar'))"
/tmp/check/bin/ayar doctor
```

The two printed versions must be identical.

**6. Upload, then tag.**

```bash
python -m twine upload dist/*
git tag v0.5.0 && git push --tags
```

**7. Confirm.** pip caches the index and PyPI's CDN takes a minute or two:

```bash
pip install --no-cache-dir -U ayar
ayar --version
```

---

## Keeping the repository small

**Never commit downloaded data or build output.** `.gitignore` contains:

```
public_results/cache/      # DANDI downloads (over a gigabyte)
public_results/ONE/        # IBL downloads
dist/                      # wheels and sdists live on PyPI, not in git
build/
*.egg-info/
*.npz                      # sessions from ayar synth and friends
```

The rest of `public_results/` (reports, JSON, `RESULTS.md`, about 3.5 MB) is committed on
purpose: `docs/public_sessions.md` links to it. Each re-run replaces those files, and git
keeps the old ones in history, so re-run and commit them when the results change, not on
every run.

Removing a large file in a later commit does not shrink the repository: git keeps it in
history. That is how `.git` reached about 800 MB during 0.4.0. If it happens again, find
the largest blobs, then remove them from history:

```bash
git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' \
  | awk '$1=="blob"' | sort -k2 -n -r | head -20

cp -r ayar ayar-backup                       # a safety copy, outside git
pip install git-filter-repo
git filter-repo --path public_results/cache --path public_results/ONE --path dist --invert-paths
git remote add origin https://github.com/aslansd/ayar.git
git push --force --all && git push --force --tags
```

Keep backups as a folder copy, not a pushed branch: a pushed backup branch keeps the large
history on GitHub, and GitHub offers to open a pull request for it, which must not be
merged.

---

## Things that have cost time before

- **A version number can never be reused** on PyPI, not even after deleting the release. If
  0.5.0 is wrong, ship 0.5.1.
- **Verify with `pip install --no-cache-dir`.** Without it you may see the previous version
  and conclude the upload failed.
- **Use an API token**, scoped to the project after the first upload (PyPI account settings
  → API tokens). To avoid re-pasting it, put it in `~/.pypirc` with mode 600:

  ```ini
  [pypi]
  username = __token__
  password = pypi-AgEIcHlwaS5vcmc...
  ```

- **Relative links break on PyPI.** The README is rendered on pypi.org, where
  `docs/public_sessions.md` resolves to nothing. Link to files in the repository with full
  GitHub URLs, as the README does now.

---

## On the licence

`LICENSE` contains the full Apache-2.0 text, and `pyproject.toml` declares
`license = "Apache-2.0"` as an SPDX expression. Keep both. Public data used in examples and
in `docs/public_sessions.md` stays with its owners (IBL, DANDI and the original authors):
ayar's repository holds results computed from it, never the data itself.

---

## Before announcing a release publicly

- [ ] `pytest -q` green with `[dev]`, and `ayar validate` prints PASS
- [ ] no merge-conflict markers; sdist contains no data
- [ ] wheel installed into a clean venv; installed version equals `ayar.__version__`
- [ ] README renders correctly on the live PyPI page, links work
- [ ] `examples/public_sessions.py` re-run if detectors or verdicts changed, and
      `docs/public_sessions.md` updated
- [ ] `CHANGELOG.md` entry says what changed for someone checking a finding
- [ ] `git tag && git push --tags`
