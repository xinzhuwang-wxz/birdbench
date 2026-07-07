# BACKLOG — birdbench v0（= GitHub issues S0–S11）

依赖序垂直切片。每片：小、可独立测、TDD 红→绿→eval 闸门。规格见 `docs/DESIGN.md`。
标签：`ready-for-agent`（纯代码、离线 fake 可测）/ `ready-for-human`（授权/密钥/数据/license）。

| # | 切片 | 验收（done 的证据） | 标签 |
|---|---|---|---|
| **S0** | 骨架 + vendor | uv `pyproject` 可 `uv sync`；`data/taxonomy/` vendor 4 文件 + pinned SHA + `scripts/sync-taxonomy`；CI(ruff+pytest) 绿；`PROVENANCE.md` | ready-for-agent |
| **S1** | schemas | `Prediction`(top-k: common/scientific/rank_hint/confidence/field_marks + abstain) · `ResolutionOutcome` · `RunManifest` · `ModelSpec` · `LeaderboardRow`；全 Pydantic + 单测 | ready-for-agent |
| **S2** | taxonomy registry | 加载 species.jsonl → `speciesCode→{sci,genus,family,order}`；rollup 索引；raw-eBird 多键解析索引；离线单测（含科属种 join 往返） | ready-for-agent |
| **S3** | 解析阶梯 0–3,5,6 | gnparser 归一→精确 code/sci/com→rollup→受限模糊→弃答；**测试对齐 §7 冒烟用例**（Cooper's Hawk✓ / Astur cooperii✓ / 亚种→种✓ / 假名→弃答✓） | ready-for-agent |
| **S4** | 同义 gazetteer(阶 4) | 【坑A】离线 build 名字→code 同义表（Wikidata P1420 / avibase 反查）；`Accipiter cooperii→coohaw` 通过；license 核对（Avibase 不可再分发 → 只建自有事实映射） | **ready-for-human** |
| **S5** | gateway seam | LiteLLM `Router` 薄壳：**`models.toml` 注册表（一家挂多模型、共享 key）**→ Router.model_list；base64 图 + per-call `cost_usd` + per-model mode(TOOLS/JSON_SCHEMA/MD_JSON 兜底) + 价格 overlay(豆包/Qwen-VL/LongCat) + 重试/超时；fake 网关离线单测 | ready-for-agent |
| **S6** | core.predict | `predict(image, model, prompt: PromptSpec)->Prediction`：prompt 来自**注册表**（S12）；俗名优先 + answer-first + 无 CoT 默认 + top-k；Instructor 解码；fake 网关离线测 | ready-for-agent |
| **S7** | score | top-1/k · 目科属种逐级 · LCA 部分分 · Mistake Severity · 四桶分离 · 解析条件 vs 端到端准确率；单测覆盖每桶 | ready-for-agent |
| **S8** | bench CLI | JSONL manifest → async **图×模型×prompt** map-reduce → `predictions.jsonl` + 双缓存；Typer `run/models/prompts/resolve`；**`--models`/`--prompts` 按 alias/版本选（笛卡尔维度）**；小 fixture 端到端离线跑通 | ready-for-agent |
| **S9** | report | 自包含 HTML 榜 + 成本×准确率 Pareto + 逐条 drilldown；bootstrap CI（McNemar 留 v1）；从 predictions.jsonl 确定性重生成 | ready-for-agent |
| **S10** | v0 评测集 | 【坑B】~30 图（稀有 + 易混）；`manifest.jsonl` 带 gold speciesCode + 授权字段；license 备注（iNat CC-BY-NC 内部用）；污染初筛(post-cutoff) | **ready-for-human** |
| **S11** | provider 矩阵 | openai/gemini/qwen-vl/豆包/grok/kimi/glm 接入(+longcat 实验位)，**每家可测多模型**（gpt-4o/4.1/5、qwen-vl-max/qwen3-vl…）；`.env.example` keys；各家各模型冒烟返回可解析 `Prediction`（需真 key + 花钱） | **ready-for-human** |
| **S12** | prompt 注册表 | `prompts/` 外部版本化 prompt 文件（同事可改）；`PromptSpec`(schemas 追加：name/version/system/user_template/params/content_hash)；prompt 成**评测轴**（item×model×**prompt**）；`PredictionRecord`/`LeaderboardRow` 带 `prompt_version`，榜可按 prompt 对比；CLI `prompts` 列版本 + `run --prompts v0,v1`；默认 v0=§5.1 最佳实践 | ready-for-agent |
| **S13** | 单图 identify 产品路径 | `identify(image,model,prompt)->IdentifyResult{prediction, species_code, 科属种, resolution, cost}` + `birdbench identify <img>`；产品端"丢一张图看科属种"一等路径（Web 复用）。V0 | ready-for-agent |

## v1 / v2（路线图，暂不开 issue）
- **v1**：Gradio 拖拽壳 · 校准/弃答指标(AURC/ECE) · McNemar/CI · recoverable-miss 影子回收 · 在线解析兜底(阶 7)。
- **v2**：严谨评测集（~150 图 2×2 分层 + 专家双确认 + 污染控制 + attribution manifest）+ 对外可分发 license 人审。
