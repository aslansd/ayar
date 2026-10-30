import numpy as np

from ayar.stats import count_strictly_within, count_within, has_partner, missing_fraction


def brute(a, b, w, strict=False):
    d = np.abs(b[None, :] - a[:, None])
    return int((d < w).sum() if strict else (d <= w).sum())


def test_counts_match_brute_force():
    rng = np.random.default_rng(1)
    for _ in range(20):
        a = np.sort(rng.uniform(0, 1, rng.integers(0, 60)))
        b = np.sort(rng.uniform(0, 1, rng.integers(0, 60)))
        for w in (0.001, 0.01, 0.1):
            assert count_within(a, b, w) == brute(a, b, w)
            assert count_strictly_within(a, b, w) == brute(a, b, w, strict=True)
            expect = int((np.abs(b[None] - a[:, None]) <= w).any(1).sum()) if a.size and b.size else 0
            assert int(has_partner(a, b, w).sum()) == expect


def test_missing_fraction():
    rng = np.random.default_rng(0)
    full = rng.normal(100, 12, 20000)
    assert missing_fraction(full) < 0.03
    cut = full[full > 100 - 12 * 0.5]  # ~31 % removed
    assert 0.2 < missing_fraction(cut) <= 0.5
