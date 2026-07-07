#!/usr/bin/env python3
"""S11：真机跑评测（LiteLLM → 各家 provider）。先估成本 + cap 检查，再全量出榜。

用法: `set -a && . .env && set +a` 后 `python scripts/run_eval.py [--cap 5] [--yes]`。
先不加 --yes 只估算；估算 ≤ cap 且确认后加 --yes 全量。Doubao 价为估算(需按账单校准)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from birdbench.bench import load_manifest, run_bench  # noqa: E402
from birdbench.gateway import LiteLLMGateway  # noqa: E402
from birdbench.registry import load_registry  # noqa: E402
from birdbench.report import write_report  # noqa: E402
from birdbench.resolve import Gazetteer  # noqa: E402
from birdbench.schemas import ModelSpec  # noqa: E402


def _env_aliases() -> None:
    if os.environ.get("ARK_API_KEY"):
        os.environ.setdefault("VOLCENGINE_API_KEY", os.environ["ARK_API_KEY"])
    if os.environ.get("QWEN_BASE_URL"):
        os.environ.setdefault("DASHSCOPE_API_BASE", os.environ["QWEN_BASE_URL"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=5.0)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--yes", action="store_true", help="估算 ≤ cap 后全量跑")
    args = ap.parse_args()

    _env_aliases()
    raw = json.loads((ROOT / "configs/doubao_price_overlay.json").read_text())
    overlay = {k: v for k, v in raw.items() if not k.startswith("_")}
    specs = [ModelSpec(**m) for m in json.loads((ROOT / "configs/models.json").read_text())]
    reg = load_registry()
    gz = Gazetteer()
    items = load_manifest(ROOT / "data/evalset/manifest.jsonl")
    gw = LiteLLMGateway(specs, price_overlay=overlay)
    n_cells = len(items) * len(specs)

    print(f"=== 估算：1 图 × {len(specs)} 模型 ===")
    est = await run_bench(
        items[:1], specs, gateway=gw, registry=reg, gazetteer=gz,
        run_id="estimate", concurrency=args.concurrency,
    )
    for r in est:
        print(f"  {r.model_alias:18s} ${r.cost_usd} {r.latency_ms:.0f}ms ok={r.schema_valid}")
    priced = [r.cost_usd for r in est if r.cost_usd]
    est_cell = (sum(priced) / len(priced)) if priced else 0.0
    projected = est_cell * n_cells
    unpriced = sum(1 for r in est if not r.cost_usd)
    print(f"  单价均值 ${est_cell:.5f} × {n_cells} = ${projected:.3f} (unpriced {unpriced})")
    if projected > args.cap:
        print(f"✗ ${projected:.2f} > cap ${args.cap} → 中止")
        return
    print(f"✓ ${projected:.3f} ≤ cap ${args.cap}")
    if not args.yes:
        print("（确认后加 --yes 全量跑）")
        return

    print(f"\n=== 全量：{len(items)} 图 × {len(specs)} 模型 = {n_cells} cells ===")
    recs = await run_bench(
        items, specs, gateway=gw, registry=reg, gazetteer=gz, run_id="v0",
        concurrency=args.concurrency, cache_dir=ROOT / ".cache",
        out_path=ROOT / "runs/predictions.jsonl",
    )
    rows = write_report(recs, ROOT / "runs/report.html")
    total = sum(r.cost_usd for r in recs if r.cost_usd)
    print(f"完成 {len(recs)} cells，有价成本合计 ${total:.4f} → runs/report.html\n")
    hdr = f"{'model':22s} top1  top5  端到端 解析条件 弃答  解析失败 $/item"
    print(hdr)
    for r in rows:
        cpi = f"${r.cost_per_item_usd:.5f}" if r.cost_per_item_usd is not None else "unpriced"
        print(
            f"{r.model_alias:22s} {r.top1_species_acc:.2f}  {r.top5_species_acc:.2f}  "
            f"{r.end_to_end_acc:.2f}   {r.resolver_conditional_acc:.2f}    "
            f"{r.abstain_rate:.2f}  {r.parse_fail_rate:.2f}   {cpi}"
        )


if __name__ == "__main__":
    asyncio.run(main())
