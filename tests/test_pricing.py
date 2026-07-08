"""V1-6 gate: 价格 overlay 必须覆盖 models.json 里每个真机模型（防 qwen-flash cost=0 回归）。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_overlay_covers_every_configured_model():
    overlay = json.loads((ROOT / "configs/doubao_price_overlay.json").read_text())
    models = json.loads((ROOT / "configs/models.json").read_text())
    for m in models:
        mid = m["model_id"]
        assert mid in overlay, f"{mid} 无价格 overlay → cost 会记成 0/None（qwen-flash 曾如此）"
        p = overlay[mid]
        assert p["input_cost_per_token"] > 0, f"{mid} 输入价须 > 0"
        assert p["output_cost_per_token"] > 0, f"{mid} 输出价须 > 0"
        assert p.get("litellm_provider"), f"{mid} 缺 litellm_provider"


def test_exchange_rate_documented():
    overlay = json.loads((ROOT / "configs/doubao_price_overlay.json").read_text())
    assert overlay.get("_exchange_rate_cny_per_usd", 0) > 0  # 汇率显式可审计
