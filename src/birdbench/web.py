"""Gradio Web 壳（V1-5）：产品端拖拽台。薄壳复用 core.identify + report；UI 无状态。见 §5.5。

默认 demo 模式（FakeGateway，不花钱不需 key，便于压测/演示）；BIRDBENCH_REAL=1 且有 key → 真机。
handler 全 try/except 兜底 → UI 绝不崩（压测稳定性）。内部鉴权在 launch(auth=...)。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from birdbench.core import identify
from birdbench.gateway import FakeGateway, Gateway
from birdbench.registry import Registry, load_registry
from birdbench.schemas import ModelSpec

_MODELS = ["fake/demo", "dashscope/qwen3-vl-plus", "volcengine/doubao-seed-2-0-lite-260428"]
_DEMO_JSON = (
    '{"predictions":[{"common_name":"Northern Cardinal",'
    '"scientific_name":"Cardinalis cardinalis","rank_hint":"species","confidence":0.82,'
    '"field_marks":"red crest, black mask"},'
    '{"common_name":"Summer Tanager","rank_hint":"species","confidence":0.1}],'
    '"abstain":false,"overall_confidence":0.82}'
)
_MEDIA = {".png": "image/png", ".webp": "image/webp"}
_reg: Registry | None = None


def _registry() -> Registry:
    global _reg
    if _reg is None:
        _reg = load_registry()
    return _reg


def _gateway(model_id: str) -> tuple[Gateway, ModelSpec]:
    spec = ModelSpec(alias=model_id, model_id=model_id, provider=model_id.split("/")[0])
    if model_id.startswith("fake") or os.environ.get("BIRDBENCH_REAL") != "1":
        return FakeGateway(responses={spec.alias: _DEMO_JSON}), spec
    from birdbench.gateway import LiteLLMGateway

    return LiteLLMGateway([spec]), spec


async def identify_handler(image_path: str | None, model_id: str):
    """图 + 模型 → (科属种卡片 markdown, top-k 表)。任何异常都返回错误信息，不崩。"""
    if not image_path:
        return "（请先上传一张鸟图）", []
    try:
        gw, spec = _gateway(model_id)
        media = _MEDIA.get(Path(image_path).suffix.lower(), "image/jpeg")
        res = await identify(
            Path(image_path).read_bytes(), spec, gateway=gw, registry=_registry(), media_type=media
        )
    except Exception as e:  # noqa: BLE001
        return f"⚠️ 出错：{type(e).__name__}: {e}", []
    if res.abstain:
        return f"**弃答**：{res.abstain_reason}（成本 ${res.cost_usd}）", []
    md = (
        f"### {res.common_name}  `{res.species_code}`\n"
        f"- **目/科/属/种**：{res.order} / {res.family} / {res.genus} / {res.scientific_name}\n"
        f"- 解析：{res.resolution_stage}（score {res.resolution_score:.2f}）\n"
        f"- 依据：{res.field_marks or '—'}\n"
        f"- 成本 ${res.cost_usd} · {res.latency_ms:.0f}ms · {res.total_tokens} tok\n"
        f"- 模型版本：{res.model_resolved}"
    )
    table = [
        [c.common_name, c.rank_hint, round(c.confidence, 2), c.species_code or "—"]
        for c in res.candidates
    ]
    return md, table


def leaderboard_handler(pred_file) -> str:
    """上传 predictions.jsonl → HTML 榜。异常返回提示，不崩。"""
    if not pred_file:
        return "<p>（请上传一个 predictions.jsonl）</p>"
    try:
        from birdbench.report import build_leaderboard, compute_significance, render_html
        from birdbench.schemas import PredictionRecord

        path = pred_file if isinstance(pred_file, str) else pred_file.name
        lines = Path(path).read_text().splitlines()
        recs = [PredictionRecord.model_validate_json(x) for x in lines if x.strip()]
        rows = build_leaderboard(recs)
        tied = compute_significance(recs, rows)
        for r in rows:
            r.tied_with_best = r.model_alias in tied
        return render_html(rows, calibration=_calib(recs))
    except Exception as e:  # noqa: BLE001
        return f"<p>⚠️ 解析失败：{type(e).__name__}: {e}</p>"


def _calib(recs) -> dict:
    from birdbench.calibration import model_calibration, pairs_by_model

    return {m: model_calibration(ps) for m, ps in pairs_by_model(recs).items()}


def build_app():
    import gradio as gr

    real = os.environ.get("BIRDBENCH_REAL") == "1"
    mode = "**真机**（花钱）" if real else "**demo**（FakeGateway，不花钱）"
    with gr.Blocks(title="birdbench — 鸟类识别评测台") as demo:
        gr.Markdown(f"# 🐦 birdbench\n模式：{mode}")
        with gr.Tab("单图识别"):
            with gr.Row():
                img = gr.Image(type="filepath", label="鸟图（拖拽/上传）")
                with gr.Column():
                    model = gr.Dropdown(_MODELS, value="fake/demo", label="模型")
                    btn = gr.Button("识别", variant="primary")
            out_md = gr.Markdown(label="结果")
            headers = ["俗名", "rank_hint", "置信", "code"]
            out_tbl = gr.Dataframe(headers=headers, label="top-k 候选")
            btn.click(identify_handler, [img, model], [out_md, out_tbl], api_name="identify")
        with gr.Tab("排行榜"):
            pred = gr.File(label="predictions.jsonl", file_types=[".jsonl"])
            lb_btn = gr.Button("生成排行榜", variant="primary")
            lb_html = gr.HTML()
            lb_btn.click(leaderboard_handler, [pred], [lb_html], api_name="leaderboard")
    return demo


def main() -> None:
    app = build_app()
    auth = None
    user, pw = os.environ.get("BIRDBENCH_WEB_USER"), os.environ.get("BIRDBENCH_WEB_PASS")
    if user and pw:
        auth = (user, pw)
    port = int(os.environ.get("BIRDBENCH_WEB_PORT", "7860"))
    app.launch(server_name="127.0.0.1", server_port=port, auth=auth)


if __name__ == "__main__":
    main()


def sample_predictions_jsonl() -> str:
    """样例 predictions.jsonl（供测试/演示排行榜）。"""
    rows = []
    for alias, ok in [("m-good", True), ("m-bad", False)]:
        for i in range(6):
            rows.append(json.dumps({
                "run_id": "demo", "item_id": f"i{i}", "model_alias": alias,
                "image_sha256": "x", "schema_valid": True,
                "prediction": {"predictions": [{"common_name": "X", "confidence": 0.8}]},
                "scores": {"bucket": "A" if ok else "B", "top1": ok, "top3": ok, "top5": ok,
                           "genus": ok, "family": ok, "order": ok, "lca": 1.0 if ok else 0.0},
                "cost_usd": 0.001, "usage": {"total_tokens": 100}, "latency_ms": 50.0,
            }))
    return "\n".join(rows) + "\n"
