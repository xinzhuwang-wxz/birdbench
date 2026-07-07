"""S7 gate: 打分（合成分类树，确定性）。DESIGN §5.3。"""

from birdbench.registry import Registry, Species
from birdbench.score import aggregate, lca_score, score_item, taxonomic_distance


def _reg(*species):
    return Registry(
        species={s.ebird_code: s for s in species}, rollup={}, com_index={}, sci_index={}
    )


# 分类树：a/a2 同属；b 同科异属；c 同目异科；e 跨目
A = Species("a", "G1 s1", "G1", "F1", "f1", "O1")
A2 = Species("a2", "G1 s2", "G1", "F1", "f1", "O1")
B = Species("b", "G2 s1", "G2", "F1", "f1", "O1")
C = Species("c", "G4 s1", "G4", "F3", "f3", "O1")
E = Species("e", "G3 s1", "G3", "F2", "f2", "O2")
REG = _reg(A, A2, B, C, E)


def test_taxonomic_distance():
    assert taxonomic_distance("a", "a", REG) == 0
    assert taxonomic_distance("a", "a2", REG) == 1
    assert taxonomic_distance("a", "b", REG) == 2
    assert taxonomic_distance("a", "c", REG) == 3
    assert taxonomic_distance("a", "e", REG) == 4
    assert taxonomic_distance("a", "missing", REG) is None


def test_lca_score():
    assert lca_score(0) == 1.0
    assert lca_score(1) == 0.75
    assert lca_score(2) == 0.5
    assert lca_score(3) == 0.25
    assert lca_score(4) == 0.0
    assert lca_score(None) == 0.0


def test_score_item_correct():
    s = score_item("a", ["a"], False, REG)
    assert s.bucket == "A" and s.top1_correct and s.lca == 1.0
    assert s.genus_correct and s.family_correct and s.order_correct
    assert s.mistake_height is None


def test_score_item_wrong_same_genus():
    s = score_item("a", ["a2"], False, REG)
    assert s.bucket == "B" and not s.top1_correct
    assert s.genus_correct and s.lca == 0.75 and s.mistake_height == 1


def test_score_item_abstain_and_parse_fail():
    assert score_item("a", [], True, REG).bucket == "D"
    pf = score_item("a", [None], False, REG)
    assert pf.bucket == "C1" and not pf.top1_correct and pf.lca == 0.0


def test_score_item_topk_hit_at_rank2():
    s = score_item("a", ["a2", "a"], False, REG)  # top-1 认了近亲 → B，但 top3/5 命中
    assert s.top1_correct is False and s.top3_correct and s.top5_correct
    assert s.bucket == "B"


def test_aggregate_buckets_and_two_accuracies():
    scores = [
        score_item("a", ["a"], False, REG),  # A
        score_item("a", ["b"], False, REG),  # B（同科）
        score_item("a", [None], False, REG),  # C1
        score_item("a", [], True, REG),  # D
    ]
    agg = aggregate(scores)
    assert agg["buckets"] == {"A": 1, "B": 1, "C1": 1, "C2": 0, "D": 1}
    assert agg["top1_species_acc"] == 0.25
    assert agg["abstain_rate"] == 0.25
    assert abs(agg["parse_fail_rate"] - 1 / 3) < 1e-9  # C1/非弃答
    assert agg["resolver_conditional_acc"] == 0.5  # A/(A+B)
    assert abs(agg["end_to_end_acc"] - 1 / 3) < 1e-9  # A/非弃答
