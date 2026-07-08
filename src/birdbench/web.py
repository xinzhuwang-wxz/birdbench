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
from birdbench.resolve import Gazetteer, resolve, resolve_with_normalizer, trace_resolve
from birdbench.schemas import ModelSpec

# 下拉：(展示标签含 tag, 实际 model_id)。tag 来自 111 图实测。
_MODELS = [
    ("fake/demo（免费·测 UI，不花钱）", "fake/demo"),
    ("qwen3-vl-flash 💰 最便宜", "dashscope/qwen3-vl-flash"),
    ("qwen3-vl-plus", "dashscope/qwen3-vl-plus"),
    ("doubao-lite 🏆 最准确（72%）", "volcengine/doubao-seed-2-0-lite-260428"),
]
_ASSETS = Path(__file__).resolve().parent.parent.parent / "docs" / "assets"
_DEMO_JSON = (
    '{"predictions":[{"common_name":"Northern Cardinal",'
    '"scientific_name":"Cardinalis cardinalis","rank_hint":"species","confidence":0.82,'
    '"field_marks":"red crest, black mask"},'
    '{"common_name":"Summer Tanager","rank_hint":"species","confidence":0.1}],'
    '"abstain":false,"overall_confidence":0.82}'
)
_MEDIA = {".png": "image/png", ".webp": "image/webp"}
_reg: Registry | None = None
_GZ = Gazetteer()
_overlay_cache: dict | None = None


def _registry() -> Registry:
    global _reg
    if _reg is None:
        _reg = load_registry()
    return _reg


def _price_overlay() -> dict:
    """价格 overlay（否则 doubao/qwen 无内置价→成本显示 $0）。"""
    global _overlay_cache
    if _overlay_cache is None:
        p = Path(__file__).resolve().parent.parent.parent / "configs" / "doubao_price_overlay.json"
        try:
            raw = json.loads(p.read_text())
            _overlay_cache = {k: v for k, v in raw.items() if not k.startswith("_")}
        except Exception:  # noqa: BLE001
            _overlay_cache = {}
    return _overlay_cache


def _gateway(
    model_id: str, temperature: float = 0.0, thinking: bool = False
) -> tuple[Gateway, ModelSpec]:
    params: dict = {"temperature": temperature}
    if "doubao" in model_id:  # thinking 仅 doubao 有；实测无益 → 默认关
        params["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}
    spec = ModelSpec(
        alias=model_id, model_id=model_id, provider=model_id.split("/")[0], params=params
    )
    if model_id.startswith("fake") or os.environ.get("BIRDBENCH_REAL") != "1":
        return FakeGateway(responses={spec.alias: _DEMO_JSON}), spec
    from birdbench.gateway import LiteLLMGateway

    return LiteLLMGateway([spec], price_overlay=_price_overlay()), spec


def _fmt_cost(c: float | None) -> str:
    return f"${c:.6f}" if c else "$0（该模型无内置价/已计价为0）"


def _trace_md(res) -> str:
    """完整 trace：模型最初输出 → 提取候选 → top-1 逐阶解析（含具体信息）。"""
    raw = (res.raw_output or "").strip() or "(空)"
    parts = [
        f"#### ① 模型最初输出（{res.model_resolved or '—'}）",
        f"```json\n{raw}\n```",
        "#### ② 提取的候选（parse → SpeciesPrediction）",
    ]
    if res.candidates:
        parts.append("| # | 俗名/学名 | rank_hint | 置信 |\n|---|---|---|---|")
        for i, c in enumerate(res.candidates):
            nm = c.common_name or c.scientific_name or "—"
            parts.append(f"| {i + 1} | {nm} | {c.rank_hint} | {c.confidence:.2f} |")
    else:
        parts.append("（模型弃答或无候选）")
    top = ""
    if res.candidates:
        top = res.candidates[0].common_name or res.candidates[0].scientific_name or ""
    if top:
        steps, outcome = trace_resolve(top, _registry(), _GZ)
        parts.append(f"#### ③ top-1 解析梯子：`{top}` → speciesCode")
        parts.append("| 阶 | 动作 | 结果 |\n|---|---|---|")
        for s in steps:
            r = s["result"] if s["result"] is not None else "—"
            parts.append(f"| {s['stage']} | {s['detail']} | `{r}` |")
        final = outcome.matched_species_code or "弃答"
        tax = f" → {res.order}/{res.family}/{res.genus}" if res.species_code else ""
        parts.append(f"\n→ **最终码 `{final}`**（{outcome.stage_fired}）{tax}")
    return "\n".join(parts)


async def identify_handler(
    image_path: str | None, model_id: str, temperature: float = 0.0, thinking: bool = False
):
    """图+模型+温度+thinking → (科属种卡片, top-k 表, 完整解析 trace)。异常都兜底，不崩。"""
    if not image_path:
        return "（请先上传一张鸟图）", [], ""
    try:
        gw, spec = _gateway(model_id, temperature, thinking)
        media = _MEDIA.get(Path(image_path).suffix.lower(), "image/jpeg")
        res = await identify(
            Path(image_path).read_bytes(), spec, gateway=gw, registry=_registry(), media_type=media
        )
    except Exception as e:  # noqa: BLE001
        return f"⚠️ 出错：{type(e).__name__}: {e}", [], ""
    trace = _trace_md(res)
    if res.abstain:
        return f"**弃答**：{res.abstain_reason}（成本 {_fmt_cost(res.cost_usd)}）", [], trace
    md = (
        f"### {res.common_name}  `{res.species_code}`\n"
        f"- **目/科/属/种**：{res.order} / {res.family} / {res.genus} / {res.scientific_name}\n"
        f"- 解析：{res.resolution_stage}（score {res.resolution_score:.2f}）\n"
        f"- 依据：{res.field_marks or '—'}\n"
        f"- 成本 {_fmt_cost(res.cost_usd)} · {res.latency_ms:.0f}ms · {res.total_tokens} tok\n"
        f"- 模型版本：{res.model_resolved}"
    )
    table = [
        [c.common_name, c.rank_hint, round(c.confidence, 2), c.species_code or "—"]
        for c in res.candidates
    ]
    return md, table, trace


def _render_leaderboard(recs) -> str:
    """PredictionRecord 列表 → HTML 榜（显著性 + 校准）。上传与跑分共用。"""
    from birdbench.report import build_leaderboard, compute_significance, render_html

    rows = build_leaderboard(recs)
    tied = compute_significance(recs, rows)
    for r in rows:
        r.tied_with_best = r.model_alias in tied
    return render_html(rows, calibration=_calib(recs))


def leaderboard_handler(pred_file) -> str:
    """上传 predictions.jsonl → HTML 榜。异常返回提示，不崩。"""
    if not pred_file:
        return "<p>（请上传一个 predictions.jsonl）</p>"
    try:
        from birdbench.schemas import PredictionRecord

        path = pred_file if isinstance(pred_file, str) else pred_file.name
        lines = Path(path).read_text().splitlines()
        recs = [PredictionRecord.model_validate_json(x) for x in lines if x.strip()]
        return _render_leaderboard(recs)
    except Exception as e:  # noqa: BLE001
        return f"<p>⚠️ 解析失败：{type(e).__name__}: {e}</p>"


def run_leaderboard_handler(preds) -> str:
    """FE-3：跑分产出的 predictions → 直接出榜（复用 _render_leaderboard）。"""
    if not preds:
        return "<p>（请先在上面跑分）</p>"
    try:
        return _render_leaderboard(preds)
    except Exception as e:  # noqa: BLE001
        return f"<p>⚠️ 渲染失败：{type(e).__name__}: {e}</p>"


def _calib(recs) -> dict:
    from birdbench.calibration import model_calibration, pairs_by_model

    return {m: model_calibration(ps) for m, ps in pairs_by_model(recs).items()}


# ---- FE-1: 模型配置 ----
_KNOWN_MODELS = [
    ("qwen3-vl-flash 💰 最便宜", "dashscope/qwen3-vl-flash"),
    ("qwen3-vl-plus", "dashscope/qwen3-vl-plus"),
    ("doubao-lite 🏆 最准", "volcengine/doubao-seed-2-0-lite-260428"),
    ("fake/demo（免费）", "fake/demo"),
]


def build_model_specs(
    selected: list[str] | None, temperature: float = 0.0, thinking: bool = False, custom: str = ""
) -> list[ModelSpec]:
    """选中 model_id + 自定义(每行一个) → list[ModelSpec]。会话态不落库；去重，空/非法跳过。"""
    ids: list[str] = []
    for raw in list(selected or []) + (custom or "").splitlines():
        mid = raw.strip()
        if mid and mid not in ids:
            ids.append(mid)
    specs = []
    for mid in ids:
        params: dict = {"temperature": float(temperature)}
        if "doubao" in mid:
            params["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}
        specs.append(ModelSpec(alias=mid, model_id=mid, provider=mid.split("/")[0], params=params))
    return specs


def model_config_handler(selected, temperature, thinking, custom):
    """UI 值 → (摘要表 rows, specs 存 State)。"""
    specs = build_model_specs(selected, temperature, thinking, custom)
    rows = [
        [s.alias, s.params.get("temperature"),
         s.params.get("extra_body", {}).get("thinking", {}).get("type", "—")]
        for s in specs
    ]
    return rows, specs


# ---- FE-2: 批量跑分 ----
_EVALSET = Path(__file__).resolve().parent.parent.parent / "data" / "evalset" / "manifest.jsonl"
_EST_TOKENS = (1500, 150)  # 典型 prompt/completion tokens（v0 实测），供无 spend 估算


def _is_real(specs) -> bool:
    return os.environ.get("BIRDBENCH_REAL") == "1" and any(
        not s.model_id.startswith("fake") for s in specs
    )


def _batch_gateway(specs):
    if _is_real(specs):
        from birdbench.gateway import LiteLLMGateway

        return LiteLLMGateway(specs, price_overlay=_price_overlay())
    return FakeGateway(responses={s.alias: _DEMO_JSON for s in specs})


def _estimate_cost(specs, n_images: int) -> float:
    """启发式估算（不真跑、不花钱）：典型 token × 官方价 × 图数。"""
    ov = _price_overlay()
    total = 0.0
    for s in specs:
        p = ov.get(s.model_id, {})
        per = _EST_TOKENS[0] * p.get("input_cost_per_token", 0) + _EST_TOKENS[1] * p.get(
            "output_cost_per_token", 0
        )
        total += per * n_images
    return total


async def batch_run_handler(specs, n_images, confirm, cap):
    """模型集 × 内置评测集前 N 图 → predictions。真机先估算+cap+确认闸；demo 恒免费。"""
    if not specs:
        return "（请先在上面「确认模型集」）", None
    from birdbench.bench import load_manifest, run_bench

    n = max(1, int(n_images))
    items = load_manifest(_EVALSET)[:n]
    real = _is_real(specs)
    if real:
        est = _estimate_cost(specs, len(items))
        if est > float(cap):
            return f"⚠️ 预计 ${est:.4f} > cap ${cap} → 未跑。减少图数/模型或提高 cap。", None
        if not confirm:
            return f"预计 ${est:.4f}（{len(items)}图×{len(specs)}模型，真机）。勾确认再跑。", None
    try:
        recs = await run_bench(items, specs, gateway=_batch_gateway(specs), registry=_registry())
    except Exception as e:  # noqa: BLE001
        return f"⚠️ 跑分出错：{type(e).__name__}: {e}", None
    cost = sum(r.cost_usd or 0 for r in recs)
    mode = "真机" if real else "demo免费"
    return f"✓ {len(recs)} cells（{len(items)}图×{len(specs)}模型·{mode}）成本 ${cost:.5f}", recs


# ---- FE-4: Prompt 选择/编辑（版本管理）----
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def prompt_choices(prompts_dir=None) -> list[str]:
    from birdbench.prompts import list_prompts

    d = Path(prompts_dir) if prompts_dir else _PROMPTS_DIR
    return [f"{p.name}.{p.version}" for p in list_prompts(d)]


def load_prompt_handler(name_version, prompts_dir=None):
    """选中的 name.version → (原始 md 文本, 元信息)。"""
    d = Path(prompts_dir) if prompts_dir else _PROMPTS_DIR
    if not name_version:
        return "", "（选一个 prompt 版本）"
    f = d / f"{name_version}.md"
    if not f.exists():
        return "", "（文件不存在）"
    from birdbench.prompts import load_prompt_file

    p = load_prompt_file(f)
    return f.read_text(), f"版本 {p.version} · hash {p.content_hash[:8]} · params {p.params}"


def save_prompt_handler(new_name, new_version, content, prompts_dir=None):
    """另存新版本（additive；拒绝覆盖已存在=保护契约默认，满足 HITL）。返回 (状态, choices)。"""
    d = Path(prompts_dir) if prompts_dir else _PROMPTS_DIR
    name, ver = (new_name or "").strip(), (new_version or "").strip()
    if not name or not ver:
        return "（填 name 和 version，如 species_id / v1）", prompt_choices(d)
    if not (content or "").strip():
        return "（内容为空）", prompt_choices(d)
    f = d / f"{name}.{ver}.md"
    if f.exists():
        return f"⚠️ {f.name} 已存在 → 换版本号（UI 不覆盖契约默认，只新增版本）", prompt_choices(d)
    f.write_text(content)
    return f"✓ 已存为新版本 {f.name}", prompt_choices(d)


# ---- FE-5: 单名解析器工具（含 LLM 文字提取，extractor 非 judge）----
_EXTRACT_MODELS = [
    ("doubao 文字（默认·凌乱名清洗）", "volcengine/doubao-seed-2-0-lite-260428"),
    ("qwen-flash 文字", "dashscope/qwen3-vl-flash"),
    ("不用 LLM（纯确定性）", ""),
]


def _build_normalizer(model_id: str):
    """构造文字 LLM 归一化器(extractor)。空/非真机→None(不调 LLM)。只在确定性 miss 时被调，省钱。"""
    if not model_id or os.environ.get("BIRDBENCH_REAL") != "1":
        return None
    from birdbench.gateway import LiteLLMGateway
    from birdbench.llm_normalize import make_normalizer

    params: dict = {"temperature": 0}
    if "doubao" in model_id:
        params["extra_body"] = {"thinking": {"type": "disabled"}}
    prov = model_id.split("/")[0]
    spec = ModelSpec(alias=model_id, model_id=model_id, provider=prov, params=params)
    return make_normalizer(LiteLLMGateway([spec], price_overlay=_price_overlay()), spec)


async def resolve_tool_handler(name: str, extract_model: str = _EXTRACT_MODELS[0][1]) -> str:
    """任意鸟名 → 逐阶 trace + 最终码。凌乱名由文字 LLM 提取(只在确定性 miss 时调)。"""
    if not name or not name.strip():
        return "（输入一个鸟名，如 Cooper's Hawk / 北美红雀 / Cardinalis cardinalis）"
    reg, gz, text = _registry(), _GZ, name.strip()
    norm = _build_normalizer(extract_model)
    if norm is not None:
        outcome = await resolve_with_normalizer(text, reg, gz, normalizer=norm)
    else:
        outcome = resolve(text, reg, gz)
    steps, outcome = trace_resolve(text, reg, gz, outcome=outcome)
    lines = [f"**`{name}`** 逐阶解析：", "| 阶 | 动作 | 结果 |", "|---|---|---|"]
    for s in steps:
        r = s["result"] if s["result"] is not None else "—"
        lines.append(f"| {s['stage']} | {s['detail']} | `{r}` |")
    code = outcome.matched_species_code
    if code:
        tax = _registry().taxonomy_of(code)
        lines.append(f"\n→ **`{code}`**（{outcome.stage_fired}）")
        if tax:
            lines.append(f"{tax.order}/{tax.family_sci}/{tax.genus}/{tax.sci_name}")
    else:
        lines.append(f"\n→ **弃答**（{outcome.stage_fired}）")
    return "\n".join(lines)


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
                    temp = gr.Slider(0.0, 1.0, value=0.0, step=0.1,
                                     label="温度 temperature（实测 0 最优）")
                    think = gr.Checkbox(value=False,
                                        label="thinking（仅 doubao；实测无益，默认关）")
                    btn = gr.Button("识别", variant="primary")
            out_md = gr.Markdown(label="结果")
            headers = ["俗名", "rank_hint", "置信", "code"]
            out_tbl = gr.Dataframe(headers=headers, label="top-k 候选")
            with gr.Accordion("🔍 解析全过程（模型最初输出 → 提取 → 逐阶解析）", open=True):
                out_trace = gr.Markdown()
            btn.click(identify_handler, [img, model, temp, think], [out_md, out_tbl, out_trace],
                      api_name="identify")
        with gr.Tab("排行榜"):
            gr.Markdown("### 📊 当前实测排行榜（n=111 图 × 5 模型，2026-07）")
            lb_png = _ASSETS / "leaderboard.png"
            if lb_png.exists():
                gr.Image(value=str(lb_png), show_label=False, container=False,
                         height=340)
            gr.Markdown(
                "🏆 **doubao-lite** 最准（72%） · 💰 **qwen3-vl-flash** 最便宜"
                "（$0.00011/正确） · doubao 显著甩 qwen ~24pp（CI 不重叠）。"
                "详见 `docs/v1-results-111.md` / benchmark 白皮书。"
            )
            gr.Markdown(
                "---\n#### 传你自己的 `predictions.jsonl` 生成榜\n"
                "**格式**：每行一条 JSON，关键字段——\n"
                "```json\n"
                '{"model_alias":"my-model","item_id":"i0","image_sha256":"x",'
                '"scores":{"bucket":"A","top1":true,"top5":true,"genus":true,'
                '"family":true,"order":true,"lca":1.0},'
                '"cost_usd":0.001,"usage":{"total_tokens":100},"latency_ms":50.0}\n'
                "```"
            )
            sample = _ASSETS / "sample_predictions.jsonl"
            if sample.exists():
                gr.File(value=str(sample), label="⬇️ 下载样例 predictions.jsonl（照此格式）")
            pred = gr.File(label="上传你的 predictions.jsonl", file_types=[".jsonl"])
            lb_btn = gr.Button("生成排行榜", variant="primary")
            lb_html = gr.HTML()
            lb_btn.click(leaderboard_handler, [pred], [lb_html], api_name="leaderboard")
        with gr.Tab("批量评测"):
            gr.Markdown("### ① 模型配置（选哪些模型测 + 参数）")
            mc_select = gr.CheckboxGroup(_KNOWN_MODELS, label="选择模型",
                                         value=["dashscope/qwen3-vl-flash"])
            with gr.Row():
                mc_temp = gr.Slider(0.0, 1.0, value=0.0, step=0.1, label="温度（应用到所有选中）")
                mc_think = gr.Checkbox(value=False, label="thinking（仅 doubao）")
            mc_custom = gr.Textbox(label="自定义 model_id（每行一个，litellm 格式）", lines=2)
            mc_btn = gr.Button("确认模型集", variant="primary")
            mc_table = gr.Dataframe(headers=["alias", "温度", "thinking"], label="已配置模型集")
            mc_state = gr.State([])
            mc_btn.click(model_config_handler, [mc_select, mc_temp, mc_think, mc_custom],
                         [mc_table, mc_state], api_name="model_config")
            gr.Markdown("### ② 跑分（内置 111 图评测集）")
            with gr.Row():
                br_n = gr.Slider(1, 111, value=3, step=1, label="用前 N 张图")
                br_cap = gr.Number(value=1.0, label="成本上限 $（cap）")
                br_confirm = gr.Checkbox(value=False, label="确认花费（真机批量需勾）")
            br_btn = gr.Button("开始跑分", variant="primary")
            br_status = gr.Markdown()
            br_preds = gr.State(None)
            br_btn.click(batch_run_handler, [mc_state, br_n, br_cap, br_confirm],
                         [br_status, br_preds], api_name="batch_run")
            gr.Markdown("### ③ 排行榜（跑完直出：显著性 + 校准 + 成本）")
            br_lb_btn = gr.Button("生成排行榜")
            br_lb = gr.HTML()
            br_lb_btn.click(run_leaderboard_handler, [br_preds], [br_lb],
                           api_name="run_leaderboard")
        with gr.Tab("Prompt"):
            gr.Markdown("### Prompt 版本（同事可编辑·版本管理；不覆盖契约默认，只新增）")
            pr_dd = gr.Dropdown(prompt_choices(), label="选版本")
            pr_view = gr.Button("查看")
            pr_content = gr.Textbox(label="内容（可编辑）", lines=12)
            pr_info = gr.Markdown()
            pr_view.click(load_prompt_handler, [pr_dd], [pr_content, pr_info],
                          api_name="load_prompt")
            gr.Markdown("#### 另存为新版本")
            with gr.Row():
                pr_name = gr.Textbox(label="name", value="species_id")
                pr_ver = gr.Textbox(label="version", placeholder="v1")
            pr_save = gr.Button("另存为新版本", variant="primary")
            pr_status = gr.Markdown()

            def _save(name, ver, content):
                status, choices = save_prompt_handler(name, ver, content)
                return status, gr.update(choices=choices)

            pr_save.click(_save, [pr_name, pr_ver, pr_content], [pr_status, pr_dd])
        with gr.Tab("解析器"):
            gr.Markdown("### 任意鸟名 → speciesCode（逐阶 trace）")
            rt_in = gr.Textbox(label="鸟名（俗名/学名/中文/带修饰）",
                               placeholder="A Victoria Crowned PigeoN")
            rt_extract = gr.Dropdown(_EXTRACT_MODELS, value=_EXTRACT_MODELS[0][1],
                                     label="提取模型（确定性解析不出时用它清洗凌乱名；仅真机生效）")
            rt_btn = gr.Button("解析", variant="primary")
            rt_out = gr.Markdown()
            rt_btn.click(resolve_tool_handler, [rt_in, rt_extract], [rt_out],
                         api_name="resolve_tool")
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
