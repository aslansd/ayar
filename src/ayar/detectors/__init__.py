"""Detector registry.

Each detector module exposes ``CODE``, ``TIER``, ``ACTION`` (how the finding audit
neutralises a flag: ``"remove"`` the implicated unit or ``"merge"`` the pair),
``FIX`` and ``run(bundle, thresholds) -> (flags, not_checked)``.
"""

from . import contamination, drift, duplicate, overlap, split

REGISTRY = {m.CODE: m for m in (duplicate, split, overlap, contamination, drift)}

__all__ = ["REGISTRY"]
