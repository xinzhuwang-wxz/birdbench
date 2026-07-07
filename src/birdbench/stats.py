"""统计层：McNemar 精确检验 + Holm 校正 + Clopper-Pearson CI + 显著性簇（V1-2）。

同一小测试集比多分类器 = 配对二值：检验量是分歧对 b+c，不是 n。b+c<25 必用精确二项(非卡方)。
排行榜按显著性呈现：与最优无显著差异的模型并列，不按微小 delta 强排（防"排行榜幻觉"）。
"""

from __future__ import annotations

from dataclasses import dataclass


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """精确二项 CI（小样本比 Wald/bootstrap 更诚实）。"""
    if n == 0:
        return (0.0, 1.0)
    from scipy.stats import beta

    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return (lo, hi)


def mcnemar_exact_p(b: int, c: int) -> float:
    """McNemar 精确二项检验（双尾）。只看分歧格 b(a对b错)/c(a错b对)。b+c=0 → p=1。"""
    n = b + c
    if n == 0:
        return 1.0
    from scipy.stats import binomtest

    return float(binomtest(min(b, c), n, 0.5, alternative="two-sided").pvalue)


def holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni 校正，返回 adjusted p（原序）。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * pvals[i])
        adj[i] = min(1.0, running)
    return adj


@dataclass
class Pairwise:
    a: str
    b: str
    b_wins: int  # a 对 b 错
    c_wins: int  # a 错 b 对
    discordant: int  # b+c
    p_raw: float
    p_holm: float = 0.0
    underpowered: bool = False  # 分歧对 < 10 → 功效不足


def pairwise_mcnemar(
    correct_by_model: dict[str, dict[str, bool]], min_discordant: int = 10
) -> list[Pairwise]:
    """correct_by_model: model → {item_id: top1_correct}。两两 McNemar 精确 + Holm 校正。"""
    models = list(correct_by_model)
    pairs: list[Pairwise] = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            a, b = models[i], models[j]
            ca, cb = correct_by_model[a], correct_by_model[b]
            items = set(ca) & set(cb)
            bw = sum(1 for it in items if ca[it] and not cb[it])
            cw = sum(1 for it in items if not ca[it] and cb[it])
            pairs.append(
                Pairwise(a, b, bw, cw, bw + cw, mcnemar_exact_p(bw, cw),
                         underpowered=(bw + cw) < min_discordant)
            )
    for p, adj in zip(pairs, holm([p.p_raw for p in pairs]), strict=True):
        p.p_holm = adj
    return pairs


def not_sig_diff_from(best: str, pairs: list[Pairwise], alpha: float = 0.05) -> set[str]:
    """与 best 无显著差异（Holm 后 p≥alpha）的模型集合（含 best）= 并列簇。"""
    tied = {best}
    for p in pairs:
        if best in (p.a, p.b) and p.p_holm >= alpha:
            tied.add(p.b if p.a == best else p.a)
    return tied
