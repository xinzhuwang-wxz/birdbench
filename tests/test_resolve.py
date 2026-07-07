"""S3 gate: 解析阶梯。对齐 DESIGN §5.2 修正 + §7 冒烟用例。"""

from birdbench.registry import load_registry
from birdbench.resolve import Gazetteer, resolve

REG = load_registry()


def _code(text, gz=None):
    return resolve(text, REG, gz).matched_species_code


def test_smoke_exact_common_and_scientific():
    assert _code("Cooper's Hawk") == "coohaw"
    assert _code("Astur cooperii") == "coohaw"  # 现学名
    assert _code("Northern Cardinal") == "norcar"
    assert _code("Cardinalis cardinalis") == "norcar"


def test_stage_labels():
    assert resolve("Cooper's Hawk", REG).stage_fired == "EXACT_COM"
    assert resolve("Astur cooperii", REG).stage_fired == "EXACT_SCI"


def test_exact_code_input():
    r = resolve("coohaw", REG)
    assert r.stage_fired == "EXACT_CODE" and r.matched_species_code == "coohaw"
    # issf 码 → rollup → 种
    r2 = resolve("erthaw1", REG)
    assert r2.stage_fired == "EXACT_CODE" and r2.matched_species_code == "rethaw"


def test_subspecies_name_resolves_to_species():
    assert _code("Buteo jamaicensis borealis") == "rethaw"


def test_synonym_via_injected_gazetteer():
    # 旧属名不在快照，本层 ABSTAIN；注入同义 gazetteer(S4 产物) 后命中
    assert _code("Accipiter cooperii") is None
    gz = Gazetteer(synonym={"accipiter cooperii": "coohaw"})
    r = resolve("Accipiter cooperii", REG, gz)
    assert r.stage_fired == "SYNONYM" and r.matched_species_code == "coohaw"


def test_zh_alias_for_chinese_models():
    # 中文名（Qwen/豆包会吐）：normalize 保留中文；gazetteer.zh 命中
    gz = Gazetteer(zh={"库柏鹰": "coohaw"})
    r = resolve("库柏鹰", REG, gz)
    assert r.stage_fired == "ZH_ALIAS" and r.matched_species_code == "coohaw"


def test_fuzzy_sci_typo_genus_pinned():
    r = resolve("Buteo jamaicencis", REG)  # 拼写变体
    assert r.stage_fired == "FUZZY_SCI" and r.matched_species_code == "rethaw"
    assert 0.9 <= r.score < 1.0


def test_code_alias_ambiguous_abstains():
    # CACA → 21 个物种（critic 实测）→ 唯一命中失败 → 弃答
    r = resolve("CACA", REG)
    assert r.matched_species_code is None
    assert r.ambiguous is True


def test_hallucinated_name_abstains():
    r = resolve("Sparg de Cooper", REG)
    assert r.stage_fired == "ABSTAIN" and r.matched_species_code is None
    assert r.ambiguous is False
