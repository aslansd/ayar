"""Named, overridable thresholds. Every number a detector uses lives here."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any, Iterable


@dataclass(frozen=True)
class Thresholds:
    # shared
    min_spikes: int = 100
    """Units with fewer spikes are skipped by every detector."""
    max_pairs: int = 20000
    """Pair detectors refuse (and say so) to test more pairs than this without depths."""

    # DUPLICATE_UNIT
    dup_window_ms: float = 0.25
    dup_fraction_warn: float = 0.2
    dup_fraction_error: float = 0.5
    dup_min_ratio: float = 10.0
    dup_max_distance_um: float = 100.0
    dup_max_lag_ms: float = 1.0
    """Duplicates may be offset by up to this lag (templates of one neuron aligned differently)."""

    # OVERLAP_HOLE
    overlap_center_ms: float = 0.5
    overlap_flank_lo_ms: float = 2.0
    overlap_flank_hi_ms: float = 10.0
    overlap_ratio_warn: float = 0.6
    overlap_ratio_error: float = 0.3
    overlap_min_expected: float = 10.0
    overlap_alpha: float = 1e-3
    overlap_max_distance_um: float = 100.0

    # SPLIT_UNIT
    split_max_distance_um: float = 100.0
    split_ratio: float = 0.3
    """Cross-refractory (±1.5 ms) coincidences at most this share of the flank expectation."""
    split_outer_ms: float = 1.0
    split_outer_ratio: float = 0.25
    """The 1.0-1.5 ms band must be this empty too: discarded overlaps empty only the centre."""
    split_max_merged_contamination: float = 0.1
    split_handoff_windows: int = 20
    split_min_window_s: float = 20.0
    split_active_fraction: float = 0.2
    split_handoff_r: float = 0.5
    split_max_ratio: float = 2.0
    split_max_amp_ratio: float = 1.25

    # CONTAMINATION
    contam_warn: float = 0.1
    contam_error: float = 0.2
    contam_min_violations: int = 5

    # DRIFT_CONFOUND
    drift_window_s: float = 60.0
    drift_min_windows: int = 6
    drift_min_window_s: float = 10.0
    drift_min_spikes_per_window: int = 5
    drift_rho: float = 0.6
    drift_alpha: float = 0.01
    drift_min_amp_change: float = 0.15
    drift_min_depth_change_um: float = 10.0
    drift_min_completeness_change: float = 0.15
    drift_loss_slack: float = 0.25
    """The rate drop may exceed the estimated detection loss by at most this much."""
    drift_completeness_spikes: int = 100
    """Target spikes per window for the completeness (amplitude-cutoff) test."""
    drift_confound_r: float = 0.3

    # curation multiverse
    mv_min_units: int = 5
    mv_sign_agreement: float = 0.9
    mv_spread: float = 0.5

    # sorter comparison
    cmp_delta_ms: float = 0.4
    """Two spikes from different sortings match if they are within this lag."""
    cmp_min_agreement: float = 0.5
    cmp_spread: float = 0.25

    # finding audit
    audit_robust: float = 0.10
    audit_sensitive: float = 0.25
    audit_controls: int = 20
    audit_control_quantile: float = 0.95
    audit_seed: int = 0

    def override(self, **kwargs: Any) -> "Thresholds":
        known = {f.name for f in fields(self)}
        unknown = set(kwargs) - known
        if unknown:
            raise KeyError(f"unknown threshold(s): {', '.join(sorted(unknown))}")
        return replace(self, **kwargs)

    def override_strings(self, items: Iterable[str]) -> "Thresholds":
        """Apply ``name=value`` strings, e.g. from ``ayar scan --set``."""
        types = {f.name: f.type for f in fields(self)}
        kw: dict[str, Any] = {}
        for item in items:
            if "=" not in item:
                raise ValueError(f"expected name=value, got {item!r}")
            k, v = (s.strip() for s in item.split("=", 1))
            if k not in types:
                raise KeyError(f"unknown threshold: {k}")
            kw[k] = int(v) if types[k] in (int, "int") else float(v)
        return self.override(**kw)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULTS = Thresholds()
