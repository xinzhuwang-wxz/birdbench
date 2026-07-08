"""V1-4 gate: 自洽采样聚合。"""

from birdbench.self_consistency import aggregate_samples


def test_unanimous():
    assert aggregate_samples(["a", "a", "a"]) == ("a", 1.0, 0.0)


def test_majority_vote():
    top, frac, ent = aggregate_samples(["a", "a", "b"])
    assert top == "a" and abs(frac - 2 / 3) < 1e-9 and ent > 0


def test_unresolved_counts_in_denominator():
    top, frac, _ = aggregate_samples(["a", "a", None])  # None 计入分母 → 保守
    assert top == "a" and abs(frac - 2 / 3) < 1e-9


def test_all_unresolved_or_empty():
    assert aggregate_samples([None, None]) == (None, 0.0, 0.0)
    assert aggregate_samples([]) == (None, 0.0, 0.0)
