"""Match units between two sortings of the same recording.

Agreement between unit *a* of sorting A and unit *b* of sorting B is
``m / (n_a + n_b - m)``, where ``m`` is the number of spikes of *a* that have a
spike of *b* within ±``delta`` (0.4 ms by default). This is the score used by
SpikeInterface's ``compare_two_sorters`` and SpikeForest. Units are matched
one-to-one by maximising total agreement (Hungarian algorithm); pairs below
``min_agreement`` are left unmatched.

The coincidence counting is vectorised over all spikes at once, so matching two
sortings with hundreds of units and millions of spikes takes seconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from .bundle import Bundle


@dataclass
class Matching:
    """One-to-one unit matching from sorting A (reference) to sorting B."""

    name_a: str
    name_b: str
    units_a: np.ndarray
    units_b: np.ndarray
    agreement: np.ndarray  # [len(units_a), len(units_b)]
    pairs: list[tuple[int, int, float]] = field(default_factory=list)

    @property
    def matched_a(self) -> set[int]:
        return {a for a, _, _ in self.pairs}

    @property
    def matched_b(self) -> set[int]:
        return {b for _, b, _ in self.pairs}

    @property
    def unmatched_a(self) -> list[int]:
        m = self.matched_a
        return [int(u) for u in self.units_a if int(u) not in m]

    @property
    def unmatched_b(self) -> list[int]:
        m = self.matched_b
        return [int(u) for u in self.units_b if int(u) not in m]

    def best_partner(self, unit_a: int) -> tuple[int, float] | None:
        """B unit with the highest agreement for ``unit_a``, matched or not."""
        i = int(np.searchsorted(self.units_a, unit_a))
        if i >= self.units_a.size or self.units_a[i] != unit_a or self.units_b.size == 0:
            return None
        j = int(np.argmax(self.agreement[i]))
        return int(self.units_b[j]), float(self.agreement[i, j])

    def summary(self) -> dict:
        return {
            "a": self.name_a, "b": self.name_b,
            "n_a": int(self.units_a.size), "n_b": int(self.units_b.size),
            "matched": len(self.pairs),
            "only_in_a": len(self.unmatched_a), "only_in_b": len(self.unmatched_b),
            "median_agreement": float(np.median([p[2] for p in self.pairs])) if self.pairs else None,
        }


def coincidence_matrix(a: Bundle, b: Bundle, delta_s: float = 0.0004) -> np.ndarray:
    """``m[i, j]``: spikes of A's i-th unit with a spike of B's j-th unit within ±delta."""
    ua, ub = a.unit_ids, b.unit_ids
    m = np.zeros((ua.size, ub.size), dtype=np.int64)
    if a.n_spikes == 0 or b.n_spikes == 0:
        return m
    ia = np.searchsorted(ua, a.spike_clusters)
    ib_all = np.searchsorted(ub, b.spike_clusters)
    tb = b.spike_times
    lo = np.searchsorted(tb, a.spike_times - delta_s, side="left")
    hi = np.searchsorted(tb, a.spike_times + delta_s, side="right")
    width = hi - lo
    max_w = int(width.max()) if width.size else 0
    # each A spike counts at most once per B unit
    seen = np.full((a.n_spikes, max(max_w, 1)), -1, dtype=np.int64)
    for k in range(max_w):
        has = width > k
        rows = np.flatnonzero(has)
        cols = ib_all[lo[has] + k]
        dup = np.zeros(rows.size, dtype=bool)
        for kk in range(k):
            dup |= seen[rows, kk] == cols
        seen[rows, k] = cols
        keep = ~dup
        np.add.at(m, (ia[rows[keep]], cols[keep]), 1)
    return m


def match_units(
    a: Bundle,
    b: Bundle,
    *,
    delta_s: float = 0.0004,
    min_agreement: float = 0.5,
    name_a: str = "A",
    name_b: str = "B",
) -> Matching:
    m = coincidence_matrix(a, b, delta_s)
    na = np.array([a.spike_indices(u).size for u in a.unit_ids], dtype=float)
    nb = np.array([b.spike_indices(u).size for u in b.unit_ids], dtype=float)
    denom = na[:, None] + nb[None, :] - m
    with np.errstate(invalid="ignore", divide="ignore"):
        agr = np.where(denom > 0, m / denom, 0.0)
    pairs: list[tuple[int, int, float]] = []
    if agr.size:
        rows, cols = linear_sum_assignment(-agr)
        for i, j in zip(rows, cols):
            if agr[i, j] >= min_agreement:
                pairs.append((int(a.unit_ids[i]), int(b.unit_ids[j]), float(agr[i, j])))
    return Matching(name_a, name_b, a.unit_ids.copy(), b.unit_ids.copy(), agr, pairs)
