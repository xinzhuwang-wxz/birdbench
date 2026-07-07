"""打分（= eval 闸门）。见 DESIGN §5.3：top-k · 目科属种逐级 · LCA 部分分 · 四桶分离 · 两准确率。

打分不调解析（解析在 S3/bench 做完，吃已解析的种码）。分类学距离/科属种由 taxonomy_of 白送。
四桶：A 解析对 / B 认错种(模型账) / C1 解析失败(V0 统归解析器账,C2 幻觉拆分=V1 影子) / D 弃答。
"""

from __future__ import annotations

from dataclasses import dataclass

from birdbench.registry import Registry

_D = 4  # 树最大高度（种→根≈目层），LCA 部分分归一化用


def taxonomic_distance(p: str, t: str, reg: Registry) -> int | None:
    """预测种码 p 与真值 t 的分类学距离（0 同种…4 跨目）。任一落不到种→None。"""
    sp, st = reg.taxonomy_of(p), reg.taxonomy_of(t)
    if sp is None or st is None:
        return None
    if sp.ebird_code == st.ebird_code:
        return 0
    if sp.genus == st.genus:
        return 1
    if sp.family_code == st.family_code:
        return 2
    if sp.order == st.order:
        return 3
    return 4


def lca_score(dist: int | None) -> float:
    """LCA 部分分：1 − 距离/D。同种=1 同属=0.75 同科=0.5 同目=0.25 跨目=0；None→0。"""
    return 0.0 if dist is None else max(0.0, 1.0 - dist / _D)


@dataclass
class ItemScore:
    bucket: str  # A | B | C1 | D
    top1_correct: bool = False
    top3_correct: bool = False
    top5_correct: bool = False
    genus_correct: bool = False
    family_correct: bool = False
    order_correct: bool = False
    lca: float = 0.0
    mistake_height: int | None = None  # 仅认错种时记 LCA 高度（Mistake Severity 用）


def score_item(
    gold_code: str, resolved_top_k: list[str | None], abstained: bool, reg: Registry
) -> ItemScore:
    """一个 item×model 的打分。resolved_top_k = 按序解析出的种码（None=该候选未解析）。"""
    if abstained:
        return ItemScore(bucket="D")

    def hit(k: int) -> bool:
        return gold_code in [c for c in resolved_top_k[:k] if c]

    top1 = resolved_top_k[0] if resolved_top_k else None
    s = ItemScore(
        bucket="C1",  # 默认：top-1 未解析 = 解析失败（V0 统归解析器账）
        top1_correct=top1 == gold_code,
        top3_correct=hit(3),
        top5_correct=hit(5),
    )
    if top1 is None:
        return s  # C1 parse-fail

    gt = reg.taxonomy_of(gold_code)
    pt = reg.taxonomy_of(top1)
    if pt and gt:
        s.genus_correct = pt.genus == gt.genus
        s.family_correct = pt.family_code == gt.family_code
        s.order_correct = pt.order == gt.order
    dist = taxonomic_distance(top1, gold_code, reg)
    s.lca = lca_score(dist)
    if top1 == gold_code:
        s.bucket = "A"
    else:
        s.bucket = "B"  # 认错种（合法码≠真值）= 模型账
        s.mistake_height = dist
    return s


def aggregate(scores: list[ItemScore]) -> dict:
    """聚合成榜指标（DESIGN §5.3）。两准确率隔离模型能力 vs 整条管线。"""
    n = len(scores)
    if n == 0:
        return {"n": 0}
    b = {"A": 0, "B": 0, "C1": 0, "D": 0}
    for s in scores:
        b[s.bucket] = b.get(s.bucket, 0) + 1
    non_abstain = n - b["D"]
    resolved = b["A"] + b["B"]
    mistakes = [s.mistake_height for s in scores if s.mistake_height is not None]

    def frac(pred) -> float:
        return sum(1 for s in scores if pred(s)) / n

    return {
        "n": n,
        "buckets": b,
        "top1_species_acc": frac(lambda s: s.top1_correct),
        "top3_species_acc": frac(lambda s: s.top3_correct),
        "top5_species_acc": frac(lambda s: s.top5_correct),
        "genus_acc": frac(lambda s: s.genus_correct),
        "family_acc": frac(lambda s: s.family_correct),
        "order_acc": frac(lambda s: s.order_correct),
        "lca_score": sum(s.lca for s in scores) / n,
        "mistake_severity": (sum(mistakes) / len(mistakes)) if mistakes else 0.0,
        "abstain_rate": b["D"] / n,
        "parse_fail_rate": (b["C1"] / non_abstain) if non_abstain else 0.0,
        "resolver_conditional_acc": (b["A"] / resolved) if resolved else 0.0,
        "end_to_end_acc": (b["A"] / non_abstain) if non_abstain else 0.0,
    }
