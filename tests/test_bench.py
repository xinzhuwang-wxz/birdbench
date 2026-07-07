"""S8 gate: bench runner（tmp_path 造图+manifest，FakeGateway 离线跑）。"""

import json

from birdbench.bench import cell_id, load_manifest, run_bench
from birdbench.core import default_prompt
from birdbench.gateway import FakeGateway
from birdbench.registry import load_registry
from birdbench.schemas import ModelSpec

REG = load_registry()
_SPEC = ModelSpec(alias="fake", model_id="fake/m", provider="fake")


def _setup(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"img-a")
    (tmp_path / "b.jpg").write_bytes(b"img-b")
    m = tmp_path / "m.jsonl"
    m.write_text(
        json.dumps({"id": "i1", "image": "a.jpg", "truth": {"species_code": "coohaw"}})
        + "\n"
        + json.dumps({"id": "i2", "image": "b.jpg", "truth": "norcar"})
        + "\n"
    )
    return m


def _cooper():
    return json.dumps(
        {"predictions": [{"common_name": "Cooper's Hawk", "confidence": 0.9}], "abstain": False}
    )


def test_load_manifest(tmp_path):
    items = load_manifest(_setup(tmp_path))
    assert len(items) == 2
    assert items[0].gold.species_code == "coohaw"  # dict 形式
    assert items[1].gold.species_code == "norcar"  # 字符串形式
    assert items[0].image_path == tmp_path / "a.jpg"


async def test_run_bench_scores_and_writes(tmp_path):
    items = load_manifest(_setup(tmp_path))
    gw = FakeGateway(responses={"fake": _cooper()})
    out = tmp_path / "runs" / "predictions.jsonl"
    recs = await run_bench(items, [_SPEC], gateway=gw, registry=REG, out_path=out)
    by = {r.item_id: r for r in recs}
    # i1 gold=coohaw, 模型说 Cooper's Hawk → A；i2 gold=norcar → 认错种 B
    assert by["i1"].scores["bucket"] == "A" and by["i1"].scores["top1"] is True
    assert by["i2"].scores["bucket"] == "B"
    assert by["i1"].cost_usd == 0.0 and by["i1"].model_resolved == "fake/m"
    assert out.exists() and len(out.read_text().strip().splitlines()) == 2


async def test_call_cache_hit_on_rerun(tmp_path):
    items = load_manifest(_setup(tmp_path))
    gw = FakeGateway(responses={"fake": _cooper()})
    cache = tmp_path / "cache"
    r1 = await run_bench(items, [_SPEC], gateway=gw, registry=REG, cache_dir=cache)
    assert all(not r.cache_hit for r in r1)
    r2 = await run_bench(items, [_SPEC], gateway=gw, registry=REG, cache_dir=cache)
    assert all(r.cache_hit for r in r2)  # 第二次全命中缓存（重跑免费）


def test_cell_id_stable_and_dimension_sensitive():
    p = default_prompt()
    m1 = ModelSpec(alias="a", model_id="p/x", provider="p")
    m2 = ModelSpec(alias="a", model_id="p/y", provider="p")
    assert cell_id("sha1", m1, p) == cell_id("sha1", m1, p)  # 稳定
    assert cell_id("sha1", m1, p) != cell_id("sha1", m2, p)  # 模型变→键变
    assert cell_id("sha1", m1, p) != cell_id("sha2", m1, p)  # 图变→键变
