"""Detector registry. Each detector exposes ``CODE``, ``TIER`` and ``run(bundle, thresholds)``."""

from . import drift, duplicate, overlap

REGISTRY = {m.CODE: m for m in (duplicate, overlap, drift)}

__all__ = ["REGISTRY"]
