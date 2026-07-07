"""S3 gate: 解析阶梯。对齐 DESIGN §5.2 修正 + §7 冒烟 + M1 review 修复。"""

from birdbench.registry import Registry, Species, load_registry
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
    r2 = resolve("erthaw1", REG)  # issf 码 → rollup → 种
    assert r2.stage_fired == "EXACT_CODE" and r2.matched_species_code == "rethaw"


def test_subspecies_name_resolves_to_species():
    assert _code("Buteo jamaicensis borealis") == "rethaw"


def test_trinomial_strip_rollup_ssp():
    # 假三名（不在 issf 索引）→ 去种加词 → 二名种
    r = resolve("Cardinalis cardinalis zzzznotreal", REG)
    assert r.stage_fired == "ROLLUP_SSP" and r.matched_species_code == "norcar"


def test_synonym_via_injected_gazetteer():
    assert _code("Accipiter cooperii") is None  # 旧属名，本层不认（留 S4）
    gz = Gazetteer(synonym={"accipiter cooperii": {"coohaw"}})
    r = resolve("Accipiter cooperii", REG, gz)
    assert r.stage_fired == "SYNONYM" and r.matched_species_code == "coohaw"


def test_zh_alias_for_chinese_models():
    gz = Gazetteer(zh={"库柏鹰": {"coohaw"}})
    r = resolve("库柏鹰", REG, gz)
    assert r.stage_fired == "ZH_ALIAS" and r.matched_species_code == "coohaw"


def test_gazetteer_ambiguous_abstains():
    gz = Gazetteer(synonym={"mystery bird": {"coohaw", "norcar"}})
    r = resolve("mystery bird", REG, gz)
    assert r.matched_species_code is None and r.ambiguous is True


def test_fuzzy_sci_typo_genus_pinned():
    r = resolve("Buteo jamaicencis", REG)  # 拼写变体
    assert r.stage_fired == "FUZZY_SCI" and r.matched_species_code == "rethaw"
    assert 0.80 <= r.score <= 0.90  # clamp 到 spec 区间


def test_code_alias_ambiguous_abstains():
    r = resolve("CACA", REG)  # → 21 种（critic 实测）→ 弃答
    assert r.matched_species_code is None and r.ambiguous is True


def test_code_alias_unique_success():
    uniq = None
    for tok, codes in REG._code_alias.items():
        if " " in tok or tok in REG.species or tok in REG.rollup:
            continue
        if REG._com.get(tok) or REG._sci.get(tok):
            continue
        if len({REG.resolve_to_species(c) for c in codes}) == 1:
            uniq = tok
            break
    assert uniq is not None
    r = resolve(uniq, REG)
    assert r.stage_fired == "CODE_ALIAS" and r.matched_species_code is not None


def test_modifier_strip_recovers_correct():
    # 描述性修饰(括号/morph/albino…)打断精确匹配 → 剥掉回退 base 名（V1-1，恢复被冤枉的对答案）
    assert _code("Northern Cardinal (yellow variant)") == "norcar"
    assert _code("American Crow (leucistic individual)") == "amecro"
    assert _code("Rock Pigeon (Feral Pigeon)") == "rocpig"
    r = resolve("Northern Cardinal (yellow xanthochroic morph)", REG)
    assert r.stage_fired == "MODIFIER_STRIP" and r.matched_species_code == "norcar"


def test_modifier_strip_leading_word():
    assert _code("Albino American Robin") == "amerob"  # 前缀 albino 剥掉 → American Robin


def test_modifier_strip_no_overreach():
    # 真·不同/含糊名不该被误剥成别的种 → 弃答不乱猜
    assert resolve("Black Owl", REG).matched_species_code is None


def test_hallucinated_name_abstains():
    r = resolve("Sparg de Cooper", REG)
    assert r.stage_fired == "ABSTAIN" and r.matched_species_code is None
    assert r.ambiguous is False


def test_empty_input_normalize():
    assert resolve("", REG).stage_fired == "NORMALIZE"
    assert resolve("   ", REG).stage_fired == "NORMALIZE"
    assert resolve("", REG).matched_species_code is None


def test_fuzzy_margin_rejects_near_ties():
    # 查询与两个同属种都很近（差最后一字母）→ margin<0.05 → 拒配 → 弃答（HIGH 修复）
    sp = {
        "x1": Species("x1", "Parus abcde", "Parus", "Paridae", "parid1", "Passeriformes"),
        "x2": Species("x2", "Parus abcdf", "Parus", "Paridae", "parid1", "Passeriformes"),
    }
    reg = Registry(species=sp, rollup={}, com_index={}, sci_index={
        "parus abcde": {"x1"}, "parus abcdf": {"x2"}})
    r = resolve("Parus abcdx", reg)
    assert r.matched_species_code is None and r.stage_fired == "ABSTAIN"


def test_ambiguous_common_name_abstains_synthetic():
    # 真实数据 0 碰撞，合成验证 ambiguity 安全网
    sp = {
        "a": Species("a", "Genus speciesa", "Genus", "Fam", "fam1", "Ord"),
        "b": Species("b", "Genus speciesb", "Genus", "Fam", "fam1", "Ord"),
    }
    reg = Registry(species=sp, rollup={}, com_index={"shared name": {"a", "b"}}, sci_index={})
    assert reg.exact_common("shared name") == (None, True)
    r = resolve("Shared Name", reg)
    assert r.matched_species_code is None and r.ambiguous is True
