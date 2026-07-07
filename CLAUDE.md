# CLAUDE.md — birdbench

Standalone 多模型多模态 API · 鸟类开集识别评测台。完整 spec 见 `docs/DESIGN.md`，切片见 `BACKLOG.md`。

## 这是什么 / 不是什么
- **是**：图 → eBird `speciesCode` + 科属种，跨模型评测准确率 + 成本；产品端可拷走的测试工具。
- **不是**：生产识别主线（那是专用分类器）；**不 import birdwatcher-ai**（只拷/改编薄 seam）；本仓不自建 KB（分类学真源 = pinned bird-taxonomy）。

## 不可协商铁律
1. **Schema 铁律**：每个模型输出必进 `schemas.py` 的 Pydantic 模型，禁自由文本裸奔。
2. **解析路径无 LLM**：名字→code 是确定性阶梯（gnparser + rapidfuzz + 本地 gazetteer/registry）。LLM-as-judge 只离线扩 gazetteer + 人审，绝不进运行时解析或打分裁判（会自我偏袒虚高）。
3. **Library-first**：commodity（模型调用/结构化/名称解析/模糊匹配/评测缓存）直接装库（LiteLLM+Router、Instructor、gnparser、rapidfuzz），锁版 + hash；只手搓薄胶水 + 领域逻辑（解析阶梯、打分、评测集）。
4. **Eval 即闸门**：prompt/模型/打分/解析改动，不过 `score.py` 的评测不合并。
5. **非阻塞 + 成本一等**：评测台高并发用 `litellm.Router`；成本用 per-call `cost_usd` + 自维护价格表（豆包/Qwen-VL 无内置价，否则 None）。
6. **License 红线**：依赖只 Apache/MIT/CC0（禁 AGPL/CC-BY-NC）；数据 CC0/CC-BY（对外再分发的图/表走人审）。新增依赖先核 LICENSE。

## 识别与打分的既定最佳实践（有依据，勿凭直觉推翻，见 DESIGN §5）
- **prompt 俗名为主、学名可选**（强制学名准确率暴跌 40–50pp）；**默认无 CoT**（细粒度识别 CoT 是负收益）。
- 输出 **top-k + rank_hint（允许向上 hedge）+ abstain 通道**。
- 打分：top-k + 目科属种逐级 + **LCA 部分分** + **四桶分离**（对/认错种/解析失败{解析器gap|幻觉}/弃答）+ 解析条件 vs 端到端准确率。
- 评测集**污染控制**是有效性命门（post-cutoff + 剔公开集 + 私有 split）。

## 工作模式
垂直切片（S0–S11），TDD 红→绿→`score.py`/pytest 闸门→独立 reviewer→PR(`Closes #N`)→合并。
**HITL 停手**（→ `ready-for-human`）：依赖/模型/数据 license、真 API key + 花钱、对外可分发的图、schema 跨切片契约。
- 写者≠校验者；同片不改门控测试/eval；main 永远绿。

## 交付形态
单 core（`core.predict`）+ 两薄壳：Typer CLI（评测台）+ Gradio Web（v1，产品端）。JSONL manifest。uv 一条命令 + `.env`。
