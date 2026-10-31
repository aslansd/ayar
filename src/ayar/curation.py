"""Turn a scan into a curation proposal you can review and apply.

``to_spikeinterface`` writes SpikeInterface's curation format (version 2): every
flagged unit gets an ``ayar`` label naming its flags, error-level duplicates and
splits become merges, and units ayar would remove become ``removed``. Apply it with
``spikeinterface.curation.apply_curation(sorting_or_analyzer, curation)``.

``to_phy`` writes ``cluster_ayar.tsv``, which Phy shows as an extra column.

This is a *proposal*: review it (the HTML report shows the evidence) before applying.
Stable epochs for drifting units have no field in the SpikeInterface format, so they
are written next to it in ``ayar_epochs``, which SpikeInterface ignores.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .bundle import Bundle
from .flags import Report, Severity


def _original_id(bundle: Bundle, unit: int):
    m = bundle.meta.get("unit_id_map")
    if m:
        return m.get(str(unit), unit)
    return int(unit)


def plan(report: Report, *, include_warnings: bool = False) -> dict[str, Any]:
    """Decide merges, removals, epochs and labels from a report's flags (ayar unit ids)."""
    from .audit import action_for

    labels: dict[int, set[str]] = {}
    merges: list[tuple[int, int]] = []
    removes: set[int] = set()
    epochs: dict[int, list] = {}
    for f in report.flags:
        for u in f.units:
            labels.setdefault(int(u), set()).add(f.code)
        if f.severity is not Severity.ERROR and not include_warnings:
            continue
        a = action_for(f)
        if f.code in ("DUPLICATE_UNIT", "SPLIT_UNIT"):
            merges.extend(a.merges)
        elif f.code == "DRIFT_CONFOUND":
            epochs.update({int(u): [list(map(float, e)) for e in ep] for u, ep in a.restricts.items()})
            removes |= a.removes
        elif f.code == "CONTAMINATION":
            removes |= a.removes
        # OVERLAP_HOLE: a pair-level problem for synchrony analyses, not a reason to drop a unit

    # merge groups (union-find), so chains become one group
    parent: dict[int, int] = {}

    def root(u):
        while parent.get(u, u) != u:
            u = parent[u]
        return u

    for keep, absorb in merges:
        rk, ra = root(keep), root(absorb)
        if rk != ra:
            parent[ra] = rk
    groups: dict[int, list[int]] = {}
    for u in list(parent):
        groups.setdefault(root(u), [root(u)])
        groups[root(u)].append(u)
    merge_groups = [sorted(set(g)) for g in groups.values()]
    in_merge = {u for g in merge_groups for u in g}
    removes -= in_merge  # a merged unit is repaired, not dropped
    return {
        "labels": {u: sorted(c) for u, c in labels.items()},
        "merges": merge_groups,
        "removed": sorted(removes),
        "epochs": {u: ep for u, ep in epochs.items() if u not in removes},
    }


def to_spikeinterface(report: Report, bundle: Bundle, *, include_warnings: bool = False) -> dict[str, Any]:
    """A SpikeInterface curation dict (format version 2) plus an ``ayar_epochs`` sidecar."""
    p = plan(report, include_warnings=include_warnings)
    from .detectors import REGISTRY

    oid = lambda u: _original_id(bundle, u)  # noqa: E731
    cur: dict[str, Any] = {
        "format_version": "2",
        "unit_ids": [oid(u) for u in bundle.unit_ids],
        "label_definitions": {
            "ayar": {"name": "ayar", "label_options": sorted(REGISTRY) + ["clean"], "exclusive": False},
        },
        "manual_labels": [{"unit_id": oid(u), "labels": {"ayar": codes}} for u, codes in sorted(p["labels"].items())],
        "merges": [{"unit_ids": [oid(u) for u in g]} for g in p["merges"]],
        "removed": [oid(u) for u in p["removed"]],
    }
    if p["epochs"]:
        cur["ayar_epochs"] = {str(oid(u)): ep for u, ep in p["epochs"].items()}
    return cur


def to_phy(report: Report, bundle: Bundle, path: str | Path) -> Path:
    """Write ``cluster_ayar.tsv`` (cluster_id, ayar): Phy shows it as a column."""
    path = Path(path)
    if path.is_dir():
        path = path / "cluster_ayar.tsv"
    labels = plan(report)["labels"]
    with path.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["cluster_id", "ayar"])
        for u in bundle.unit_ids:
            w.writerow([_original_id(bundle, int(u)), ",".join(labels.get(int(u), [])) or "clean"])
    return path


def write_spikeinterface(report: Report, bundle: Bundle, path: str | Path, *, include_warnings: bool = False) -> Path:
    path = Path(path)
    path.write_text(json.dumps(to_spikeinterface(report, bundle, include_warnings=include_warnings), indent=2))
    return path


def apply_epochs(bundle: Bundle, curation: dict[str, Any]) -> Bundle:
    """Restrict a bundle's units to the ``ayar_epochs`` of a curation dict (ayar or original ids)."""
    eps = curation.get("ayar_epochs") or {}
    if not eps:
        return bundle
    reverse = {str(v): int(k) for k, v in (bundle.meta.get("unit_id_map") or {}).items()}
    mapped = {reverse.get(str(k), None) if reverse else int(k): v for k, v in eps.items()}
    present = {int(u) for u in bundle.unit_ids}
    return bundle.restrict({u: v for u, v in mapped.items() if u is not None and u in present})


def apply(bundle: Bundle, curation: dict[str, Any] | str | Path, *, dedupe_s: float = 0.00125) -> Bundle:
    """Apply a curation (ayar's export, or any SpikeInterface v2 curation) to a bundle.

    Merges and removals use the sorter's original unit ids when the bundle has a
    ``unit_id_map``; ``ayar_epochs`` restrict units to their stable epochs. Merged
    copies within ``dedupe_s`` are counted once.
    """
    if not isinstance(curation, dict):
        curation = json.loads(Path(curation).read_text())
    reverse = {str(v): int(k) for k, v in (bundle.meta.get("unit_id_map") or {}).items()}

    def to_ayar(u):
        if reverse:
            if str(u) not in reverse:
                raise KeyError(f"curation names unit {u!r}, which is not in the bundle")
            return reverse[str(u)]
        return int(u)

    present = {int(u) for u in bundle.unit_ids}
    pairs = []
    for m in curation.get("merges") or []:
        ids = [to_ayar(u) for u in (m["unit_ids"] if isinstance(m, dict) else m)]
        ids = [u for u in ids if u in present]
        pairs.extend((ids[0], other) for other in ids[1:])
    b = bundle.merge(pairs, dedupe_s) if pairs else bundle
    b = apply_epochs(b, curation)
    removed = {to_ayar(u) for u in curation.get("removed") or []}
    return b.without(removed & {int(u) for u in b.unit_ids})
