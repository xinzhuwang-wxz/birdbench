"""S2 gate: taxonomy registry（离线、stdlib）。对齐 DESIGN §5.2 修正后的索引规则。"""

from birdbench.registry import load_registry, normalize

REG = load_registry()


def test_species_count_and_taxonomy_join():
    assert len(REG.species) == 11167
    nc = REG.taxonomy_of("norcar")
    assert (nc.genus, nc.family_sci, nc.order) == ("Cardinalis", "Cardinalidae", "Passeriformes")
    ch = REG.taxonomy_of("coohaw")
    assert (ch.genus, ch.family_sci, ch.order) == ("Astur", "Accipitridae", "Accipitriformes")


def test_rollup_postprocess_issf_to_species():
    # erthaw1 是亚种(issf, Buteo jamaicensis borealis) → rollup → rethaw(Red-tailed Hawk 种)
    assert REG.resolve_to_species("erthaw1") == "rethaw"
    sp = REG.taxonomy_of("erthaw1")
    assert sp is not None and sp.ebird_code == "rethaw" and sp.genus == "Buteo"
    # 种码本身 rollup 是 no-op
    assert REG.resolve_to_species("norcar") == "norcar"


def test_exact_common_and_scientific():
    assert REG.exact_common("Cooper's Hawk") == ("coohaw", False)
    assert REG.exact_common("Northern Cardinal") == ("norcar", False)
    assert REG.exact_scientific("Astur cooperii") == ("coohaw", False)  # 现学名
    assert REG.exact_scientific("Cardinalis cardinalis") == ("norcar", False)


def test_subspecies_name_resolves_via_issf_then_rollup():
    # 亚种学名（issf 索引）→ issf 码 → rollup → 种码
    assert REG.exact_scientific("Buteo jamaicensis borealis") == ("rethaw", False)


def test_old_genus_name_not_resolved_here():
    # Accipiter cooperii(旧属名)不在快照 → 本层 UNRESOLVED（留给 S4 同义 gazetteer）
    assert REG.exact_scientific("Accipiter cooperii") == (None, False)


def test_unknown_name_unresolved():
    assert REG.exact_common("Sparg de Cooper") == (None, False)


def test_index_invariant_only_species_and_issf():
    # 索引里每个 code 都必须能落到一个种（不含 slash/spuh/hybrid 等悬空码）
    for index in (REG._com, REG._sci, REG._code_alias):
        for codes in index.values():
            for c in codes:
                assert REG.taxonomy_of(c) is not None, f"index code {c} 落不到种"


def test_normalize():
    assert normalize("Cooper's Hawk") == "coopers hawk"
    assert normalize("  Astur   cooperii ") == "astur cooperii"
