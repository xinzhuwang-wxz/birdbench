"""校准 + 选择性分类指标（V1-3）。小样本首选阈值/分箱无关的 AUROC_f/Brier/过度自信gap。

置信信号 v1 先用口头 top-1 confidence（基线,近瞎猜）；V1-4 自洽投票率替换成更可靠的。
"""

from __future__ import annotations

from collections import defaultdict

from birdbench.schemas import PredictionRecord

Pair = tuple[float, bool]  # (置信度, top-1 是否正确)


def pairs_by_model(records: list[PredictionRecord]) -> dict[str, list[Pair]]:
    out: dict[str, list[Pair]] = defaultdict(list)
    for r in records:
        if r.prediction and r.prediction.predictions and r.scores:
            conf = r.prediction.predictions[0].confidence
            out[r.model_alias].append((conf, bool(r.scores.get("top1"))))
    return dict(out)


def auroc_correctness(pairs: list[Pair]) -> float:
    """AUROC_f：置信度作为'对/错'分类器的 AUROC。1=完美分开,0.5=瞎猜。小样本最稳。"""
    pos = [c for c, y in pairs if y]
    neg = [c for c, y in pairs if not y]
    if not pos or not neg:
        return 0.5
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def brier(pairs: list[Pair]) -> float:
    return sum((c - y) ** 2 for c, y in pairs) / len(pairs) if pairs else 0.0


def overconfidence_gap(pairs: list[Pair]) -> float:
    """mean(置信) − 准确率。正=过度自信（VLM 典型 23-30pp）。"""
    if not pairs:
        return 0.0
    return sum(c for c, _ in pairs) / len(pairs) - sum(y for _, y in pairs) / len(pairs)


def aurc(pairs: list[Pair]) -> float:
    """选择性风险曲线下面积（按置信降序累积错误率）。越低越好。"""
    if not pairs:
        return 0.0
    s = sorted(pairs, key=lambda x: x[0], reverse=True)
    errs, total = 0, 0.0
    for k, (_, y) in enumerate(s, 1):
        errs += not y
        total += errs / k
    return total / len(s)


def e_aurc(pairs: list[Pair]) -> float:
    """E-AURC = AURC − oracle AURC（去基准准确率→纯排序质量,跨模型可比）。完美排序=0。"""
    if not pairs:
        return 0.0
    n, n_wrong = len(pairs), sum(1 for _, y in pairs if not y)
    oracle, errs = 0.0, 0
    for k in range(1, n + 1):
        if k > n - n_wrong:  # oracle: 对的全排前,错的排后
            errs += 1
        oracle += errs / k
    return aurc(pairs) - oracle / n


def selective_acc_at(pairs: list[Pair], coverage: float) -> float:
    """取最自信的 coverage 比例，其准确率。"""
    if not pairs:
        return 0.0
    s = sorted(pairs, key=lambda x: x[0], reverse=True)
    k = max(1, int(coverage * len(s)))
    return sum(1 for _, y in s[:k] if y) / k


def model_calibration(pairs: list[Pair]) -> dict[str, float]:
    return {
        "auroc_f": auroc_correctness(pairs),
        "brier": brier(pairs),
        "overconf_gap": overconfidence_gap(pairs),
        "aurc": aurc(pairs),
        "e_aurc": e_aurc(pairs),
        "sel_acc_50": selective_acc_at(pairs, 0.5),
        "sel_acc_80": selective_acc_at(pairs, 0.8),
    }
