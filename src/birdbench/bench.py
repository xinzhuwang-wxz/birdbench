"""评测台 runner：manifest(JSONL) → 图×模型×prompt map-reduce → PredictionRecord[]。见 §5.5/5.7。

调用缓存：cell_id→原始响应（重跑免费）。重打分=对 predictions.jsonl 重跑 score(S9 读它)。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from birdbench.core import default_prompt, parse_prediction, predict
from birdbench.gateway import Gateway
from birdbench.registry import Registry
from birdbench.resolve import Gazetteer, resolve
from birdbench.schemas import GoldLabel, ModelSpec, PredictionRecord, PromptSpec, Usage
from birdbench.score import score_item

_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


@dataclass
class Item:
    item_id: str
    image_path: Path
    gold: GoldLabel
    meta: dict


def _gold_of(r: dict) -> GoldLabel:
    g = r.get("truth") or r.get("gold") or {}
    if isinstance(g, str):
        return GoldLabel(species_code=g)
    return GoldLabel(**g) if g else GoldLabel(species_code="")


def load_manifest(path: str | Path) -> list[Item]:
    p = Path(path)
    items = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        img = Path(r["image"])
        items.append(
            Item(
                item_id=str(r["id"]),
                image_path=img if img.is_absolute() else p.parent / img,
                gold=_gold_of(r),
                meta=r.get("meta", {}),
            )
        )
    return items


def cell_id(image_sha: str, model: ModelSpec, prompt: PromptSpec) -> str:
    """维度内容哈希 = 缓存键（DESIGN §5.7）。"""
    params = json.dumps(model.params, sort_keys=True)
    key = f"{image_sha}|{model.model_id}|{params}|{prompt.content_hash}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _media(path: Path) -> str:
    return _MEDIA.get(path.suffix.lower(), "image/jpeg")


async def run_cell(
    item: Item,
    model: ModelSpec,
    prompt: PromptSpec,
    *,
    gateway: Gateway,
    registry: Registry,
    gazetteer: Gazetteer,
    run_id: str,
    cache_dir: Path | None = None,
) -> PredictionRecord:
    image = item.image_path.read_bytes()
    image_sha = hashlib.sha256(image).hexdigest()
    cid = cell_id(image_sha, model, prompt)
    cache_file = (cache_dir / f"{cid}.json") if cache_dir else None

    cache_hit = False
    if cache_file and cache_file.exists():
        c = json.loads(cache_file.read_text())
        raw, usage, cost = c["raw_output"], Usage(**c["usage"]), c["cost_usd"]
        latency, model_resolved, error = c["latency_ms"], c["model_resolved"], c.get("error")
        cache_hit = True
    else:
        out = await predict(
            image, model, prompt, gateway=gateway, media_type=_media(item.image_path)
        )
        r = out.response
        raw, usage, cost = out.raw_output, r.usage, r.cost_usd
        latency, model_resolved, error = r.latency_ms, r.model_resolved, r.error
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(
                    {
                        "raw_output": raw,
                        "usage": usage.model_dump(),
                        "cost_usd": cost,
                        "latency_ms": latency,
                        "model_resolved": model_resolved,
                        "error": error,
                    }
                )
            )

    pred = parse_prediction(raw)
    abstained = bool(pred and pred.abstain)
    outcomes = []
    if pred and not abstained:
        for cand in pred.predictions:
            name = cand.common_name or cand.scientific_name or ""
            outcomes.append(resolve(name, registry, gazetteer))
    resolved = [o.matched_species_code for o in outcomes]

    scores: dict = {}
    top1_res = outcomes[0] if outcomes else None
    if item.gold.species_code:
        s = score_item(item.gold.species_code, resolved, abstained, registry)
        scores = {
            "bucket": s.bucket,
            "top1": s.top1_correct,
            "top3": s.top3_correct,
            "top5": s.top5_correct,
            "genus": s.genus_correct,
            "family": s.family_correct,
            "order": s.order_correct,
            "lca": s.lca,
        }
        if top1_res is not None:
            top1_res.gold_species_code = item.gold.species_code
            top1_res.resolution_bucket = s.bucket

    return PredictionRecord(
        run_id=run_id,
        cell_id=cid,
        item_id=item.item_id,
        model_alias=model.alias,
        prompt_version=prompt.version,
        prompt_hash=prompt.content_hash,
        image_sha256=image_sha,
        gold=item.gold,
        raw_output=raw,
        prediction=pred,
        schema_valid=pred is not None,
        resolution=top1_res,
        scores=scores,
        latency_ms=latency,
        usage=usage,
        cost_usd=cost,
        model_resolved=model_resolved,
        cache_hit=cache_hit,
        error=error,
    )


async def run_bench(
    items: list[Item],
    models: list[ModelSpec],
    prompts: list[PromptSpec] | None = None,
    *,
    gateway: Gateway,
    registry: Registry,
    gazetteer: Gazetteer | None = None,
    run_id: str = "run",
    concurrency: int = 8,
    cache_dir: Path | None = None,
    out_path: Path | None = None,
) -> list[PredictionRecord]:
    """图×模型×prompt 笛卡尔 map-reduce（并发受 Semaphore 限）。out_path 写 predictions.jsonl。"""
    prompts = prompts or [default_prompt()]
    gz = gazetteer or Gazetteer()
    cells = [(it, m, p) for it in items for m in models for p in prompts]
    sem = asyncio.Semaphore(concurrency)

    async def one(cell):
        async with sem:
            return await run_cell(
                cell[0], cell[1], cell[2], gateway=gateway, registry=registry,
                gazetteer=gz, run_id=run_id, cache_dir=cache_dir,
            )

    records = await asyncio.gather(*[one(c) for c in cells])
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(r.model_dump_json() for r in records) + "\n")
    return list(records)
