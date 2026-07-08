"""V1-8 gate: LLM 名字归一化（extractor 非 judge）。fake 归一化器 + FakeGateway 全离线。

铁律：LLM 只擦名字→再走确定性 exact 定码；对错仍 code==gold。故测"确定性命中不调 LLM(省钱)"、
"None/无改动保留确定性(不虚高)"、"擦过仍解析不出保留确定性"。
"""

from birdbench.gateway import FakeGateway
from birdbench.llm_normalize import make_normalizer
from birdbench.registry import load_registry
from birdbench.resolve import resolve, resolve_with_normalizer
from birdbench.schemas import ModelSpec

REG = load_registry()
_SPEC = ModelSpec(alias="tiny", model_id="fake/tiny", provider="fake")


async def test_normalizer_recovers_deterministic_miss():
    # 确定性解析不出的散文式回答 → LLM 提取干净种名 → 恢复
    text = "It really looks like a Northern Cardinal to me, quite red!"
    assert resolve(text, REG).matched_species_code is None

    async def norm(_):
        return "Northern Cardinal"

    r = await resolve_with_normalizer(text, REG, normalizer=norm)
    assert r.matched_species_code == "norcar"
    assert r.stage_fired == "LLM_NORMALIZE"
    assert r.source == "llm-normalize"


async def test_deterministic_hit_skips_llm():
    called = {"n": 0}

    async def norm(_):
        called["n"] += 1
        return "wrong"

    r = await resolve_with_normalizer("Cooper's Hawk", REG, normalizer=norm)
    assert r.matched_species_code == "coohaw"
    assert r.stage_fired == "EXACT_COM"
    assert called["n"] == 0  # 确定性命中 → 绝不调 LLM（省钱）


async def test_normalizer_none_keeps_abstain():
    async def norm(_):
        return None

    r = await resolve_with_normalizer("qwzzx blorp fzzt", REG, normalizer=norm)
    assert r.matched_species_code is None
    assert r.stage_fired == "ABSTAIN"  # LLM 说 NONE → 不虚高


async def test_normalizer_cleaned_but_unresolvable_keeps_det():
    async def norm(_):
        return "Notabird Fakerson"  # 擦出来也不是真种

    r = await resolve_with_normalizer("blah blah blah", REG, normalizer=norm)
    assert r.matched_species_code is None
    assert r.stage_fired != "LLM_NORMALIZE"  # 保留确定性结果


async def test_no_normalizer_is_pure_deterministic():
    r = await resolve_with_normalizer("Cooper's Hawk", REG, normalizer=None)
    assert r.matched_species_code == "coohaw"


async def test_make_normalizer_extracts_and_caches():
    gw = FakeGateway(responses={"tiny": "Northern Cardinal"})
    norm = make_normalizer(gw, _SPEC)
    assert await norm("Northern Cardinal (yellow xanthochroic morph)") == "Northern Cardinal"
    cache: dict = {}
    norm2 = make_normalizer(gw, _SPEC, cache=cache)
    await norm2("weird bird")
    assert "weird bird" in cache  # 缓存写入（可复现/省钱）


async def test_make_normalizer_none_on_no_species():
    gw = FakeGateway(responses={"tiny": "NONE"})
    norm = make_normalizer(gw, _SPEC)
    assert await norm("a blurry unidentifiable bird") is None


async def test_end_to_end_make_normalizer_recovers():
    gw = FakeGateway(responses={"tiny": "Northern Cardinal"})
    norm = make_normalizer(gw, _SPEC)
    r = await resolve_with_normalizer("a red crested songbird, my guess", REG, normalizer=norm)
    assert r.matched_species_code == "norcar"
    assert r.stage_fired == "LLM_NORMALIZE"
