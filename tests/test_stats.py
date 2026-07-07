"""V1-2 gate: 统计层（McNemar 精确 + Holm + Clopper-Pearson + 显著性簇）。"""

from birdbench.stats import (
    clopper_pearson,
    holm,
    mcnemar_exact_p,
    not_sig_diff_from,
    pairwise_mcnemar,
)


def test_clopper_pearson():
    lo, hi = clopper_pearson(8, 10)
    assert 0.0 <= lo <= 0.8 <= hi <= 1.0
    assert clopper_pearson(0, 0) == (0.0, 1.0)
    assert clopper_pearson(10, 10)[1] == 1.0
    assert clopper_pearson(0, 10)[0] == 0.0


def test_mcnemar_exact():
    assert mcnemar_exact_p(0, 0) == 1.0
    assert mcnemar_exact_p(10, 0) < 0.05  # 强不对称 → 显著
    assert mcnemar_exact_p(5, 5) > 0.5  # 对称 → 不显著


def test_holm():
    adj = holm([0.01, 0.04, 0.03])
    assert all(0.0 <= a <= 1.0 for a in adj)
    assert abs(adj[0] - 0.03) < 1e-9  # 最小 p 0.01 × 3 = 0.03
    assert adj[1] >= 0.04 and adj[2] >= 0.03  # 校正后 ≥ 原始


def test_pairwise_and_tied_cluster():
    items = [f"i{k}" for k in range(20)]
    correct = {
        "A": {it: True for it in items},  # 全对
        "B": {it: False for it in items},  # 全错
        "C": {it: (k % 2 == 0) for k, it in enumerate(items)},  # 一半
    }
    pairs = pairwise_mcnemar(correct)
    ab = next(p for p in pairs if {p.a, p.b} == {"A", "B"})
    assert ab.discordant == 20 and ab.p_holm < 0.05
    tied = not_sig_diff_from("A", pairs)
    assert "B" not in tied  # B 与 A 显著不同 → 不并列


def test_underpowered_flag():
    # 分歧对少 → 标 underpowered
    correct = {"X": {"i0": True, "i1": False}, "Y": {"i0": True, "i1": True}}
    pairs = pairwise_mcnemar(correct)
    assert pairs[0].underpowered is True  # discordant=1 < 10
