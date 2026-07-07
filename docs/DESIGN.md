# birdbench — 设计与最佳实践（可执行 spec）

> 本文件是每个切片实现者的规格来源。决策均有调研依据（见文末引用）与**真实数据验证**（见 §7）。

## 1. 目标

一个 **standalone** 的多模型多模态 API 评测台，两个用途共享一套 core：

- **评测台**：固定评测集 × 多家模型 → 可复现排行榜（准确率 / 成本 / 延迟）。
- **产品端测试工具**：方便同事拖图/批量测各家 API。交付方式 = 整仓拷走，`uv run` 一条命令起。

**非目标 / 边界**：
- **不是**生产物种识别主线（那是专用分类器）。这里是**开集 VLM 识别的测量台**。
- **不 import** birdwatcher-ai（保持独立可拷）；只**拷/改编**其薄 seam（LiteLLM 图片+成本、Instructor 解码、schema 模板）。
- 分类学真源 = pinned bird-taxonomy，vendor 进仓；**本仓不自建知识库**。

## 2. 范围（MVP）

**图 → eBird `speciesCode` + 科/属/目。** 就这些。

- `speciesCode` 是唯一答案；科/属/目由 `speciesCode` 查 `species.jsonl` **白送**（不用模型单独预测）。
- **summary / 百科不在 MVP**（有了 `speciesCode` 以后随时能接 bird-taxonomy 的 KB）。
- 开集：**不给模型候选名单**，模型自由生成名字，由确定性代码解析回 `speciesCode`。

## 3. 数据模型与来源

分类学真源 = [`bird-taxonomy`](https://github.com/xinzhuwang-wxz/bird-taxonomy)，**vendor 快照**进 `data/taxonomy/`，记 pinned commit SHA + `scripts/sync-taxonomy` 重拉脚本。需要的 4 个文件（已验证在位）：

| 文件 | 内容 | 用途 |
|---|---|---|
| `data/species.jsonl` | 11,167 种；`ebird_code · sci_name · genus · family_sci · family_code · order · taxon_order` | **身份真源**；科属种 join |
| `raw/ebird_taxonomy.<date>.jsonl` | 17,891 taxa；含 `speciesCode · comName · sciName · com/sciNameCodes` | **解析主索引**（俗名/学名/缩写码 → code） |
| `data/rollup.jsonl` | 4,120；`ebird_code(细) → reports_as_ebird_code(种)` | 亚种/issf/form → 种收敛 |
| `data/avibase_map.jsonl` | 8,785；`ebird_code → avibase_id` | 概念锚（同义构建辅助，非直接名→码） |

> `ebird_code` 是**不透明主键**——不许解析它的字符（尾数字是 eBird 的碰撞消歧，非分类学信息）。要 rank 读 `genus`/`family_sci`/`order` 列。

## 4. 管线

```
图片 → [VLM 开集预测: 俗名(主)+学名(辅)+top-k]
     → [确定性解析阶梯] → speciesCode
                          ├─ species.jsonl 查 → 科/属/目（白送）
                          └─ [打分 vs gold speciesCode]
     → [聚合] → 排行榜(准确率/成本/延迟) + HTML/Pareto
```

## 5. 最佳实践决策（有依据，勿凭直觉推翻）

### ⚠️ 三个反直觉、承重的发现
1. **让模型吐俗名，不是学名。** 学名是 VLM 语料 OOD，强制学名准确率暴跌 40–50pp；俗名再解析回码，准确率高 2–5×。→ prompt **俗名为主、学名可选**，解析层两者都吃。（VLM4Bio；Prompting Scientific Names 2310.09929）
2. **CoT 对细粒度识别是负收益**（平均 −3~6pp）。→ 默认 **answer-first、短输出**；CoT 设成 A/B 开关，不设默认。（arXiv 2601.06993）
3. **数据污染是评测有效性命门**：某鸟类基准测试集与 BioCLIP-2 训练集重叠 56.5%。→ 评测集**优先用各模型训练截止日之后上传的图** + 剔除 CUB/NABirds/iNat/TreeOfLife 成员 + 留私有 split。（RealBirdID 2603.27033）

### 5.1 VLM 输出 schema（进 `schemas.py`，Schema 铁律）
```jsonc
{
  "abstain": false,
  "abstain_reason": null,          // image_quality|occlusion_angle|needs_audio|multiple_individuals|out_of_expertise|not_a_bird
  "predictions": [                 // top-k(建议 k=5)，置信度降序
    { "rank_hint": "species",      // species|genus|family|order —允许向上 hedge，不逼它猜到种
      "common_name": "Green-winged Teal",   // 主字段（最易解析）
      "scientific_name": "Anas crecca",     // 辅，可空
      "confidence": 0.72,          // [0,1]
      "field_marks": "chestnut head, green eye-patch" }   // ≤1句，可空
  ],
  "overall_confidence": 0.72
}
```
- 允许诚实 hedge 到属/科（`rank_hint`），据此给分层部分分，别把诚实的属级答案判 0。
- 想测 CoT 时加**独立**长推理字段做 A/B，别塞进主答案路径。

### 5.2 解析阶梯（`resolve/`，确定性，first-hit-wins，LLM 不进解析路径）
基于一个预建的**多键 registry 索引**（全部归一化：小写/去标点/去命名人/去 "sp."）。

| 阶 | 匹配 | 类型 | 置信 | 弃答规则 |
|---|---|---|---|---|
| 0 | gnparser 归一化 | — | — | 乱码且无 comName 命中 → 跳到弃答 |
| 1 | 精确 eBird code / com/sciNameCodes | EXACT_CODE | 1.0 | — |
| 2 | 精确学名(canonical binomial) | EXACT_SCI | 1.0 | — |
| 3 | 精确俗名 | EXACT_COM | 0.99 | 俗名映射到 >1 code → **弃答**，不猜 |
| 4 | 同义/属重分类 gazetteer | SYNONYM | 0.97 | 仅当唯一命中一个 registry code |
| 5 | 亚种 rollup | ROLLUP_SSP | 0.95 | cardinality==3 → 去种加词 → rollup 表 → 种码 |
| 6 | 受限模糊(rapidfuzz) | FUZZY_SCI | 0.80–0.90 | **属 token 必须精确**；仅模糊种加词；JW≥0.92 且 编辑距离≤2 且 与次候选 margin≥0.05；**绝不模糊俗名** |
| 7 | (可选)在线 GBIF/GNverifier 兜底 | EXTERNAL | ≤0.85 | 缓存+超时；仅 EXACT+SPECIES；结果再过 2/4 阶落码；不在 registry → 弃答 |
| 8 | 弃答 | ABSTAIN | — | 一等结局，记原文+最佳被拒候选+原因；**绝不静默给错码** |

**复用 vs 自搓**：gnparser(MIT)、rapidfuzz(MIT) 直接装；**当前 `speciesCode` 映射必须本地自持**（外部服务的 eBird 源冻结在 v2019，认不了 Accipiter→Astur 这类新变更）；GBIF/GN/Avibase/Wikidata **离线**用来 build gazetteer，不在运行时热路径；**LLM-as-judge 判等价踢出解析路径**（自我偏袒虚高 10–25%），仅离线扩 gazetteer + 人审。

### 5.3 打分（`score.py`，= eval 闸门）
真值 gold code = t，预测解析码 = p。
- **硬准确率**：top-1 / top-3 / top-5 species accuracy（精确 `speciesCode`）。
- **逐级准确率**：`order_acc / family_acc / genus_acc / species_acc`（都由 join 白送）——对应产品面的"科属种"。
- **LCA 部分分（主综合分）**：`1 − LCA高度(p,t)/D`。同种=1、同属≈0.75、同科≈0.5、同目≈0.25、跨目≈0。
- **Mistake Severity**：**仅错样本上**取 LCA 高度均值（与部分分分开报，否则奖励保守模型）。
- **校准/选择性分类**（v1）：AURC/E-AURC + ECE + reliability diagram；可答/不可答弃答分离 AUC。**不拿模型口头置信度当真值**（VLM 过度自信），只用它做 risk-coverage 排序信号。

**四桶分离（最关键，`ResolutionOutcome` 记账）**：

| 桶 | 判定 | 归属 |
|---|---|---|
| A 解析对✓ | 解析出码且命中 | 分子 |
| B 认错种 | 解析出**合法**码但 ≠t | **模型账** |
| C 解析失败 | 给了名但映不到码 → 拆 C1 解析器覆盖漏洞 / C2 模型幻觉 | C1 解析器账 / C2 模型账 |
| D 弃答 | abstain 或"看不出" | 只进 coverage/弃答指标 |

报**两个准确率**：**解析条件准确率** A/(A+B)（隔离模型能力） vs **端到端准确率** A/(A+B+C…)（整条管线）；差值 = 解析器成本。单列 **parse-fail rate** 拆 C1/C2。

### 5.4 模型访问层（`gateway.py` / `structured.py`）
- **复用 LiteLLM**（2025-26 多供应商事实标准），但评测台补两处：
  - **`litellm.Router`**（每 deployment rpm/tpm/max_parallel/cooldown/fallback）——高并发打多家必需。
  - **自维护价格表 `litellm.register_model(...)`**——豆包/Qwen-VL max·plus·2.5-vl/LongCat/部分 Kimi **无内置价，`completion_cost` 返回 None**；否则 `cost_usd` 一直是 None、成本按天花板高估。
- **图片一律 base64 `data:` URL**（唯一跨全家通；Kimi 强制、不支持远程 URL）。
- **system 传纯字符串**（豆包火山方舟硬约束）。
- **结构化 mode per-model**：默认 `TOOLS`/`JSON_SCHEMA`；LongCat / Qwen-`-thinking` / 不确定家降级 **`MD_JSON`**；**永不给 Qwen-thinking 发 json_schema**；Gemini 视觉+结构化走原生 `response_schema`。
- **供应链**：pin 依赖版本 + hash（LiteLLM 曾被投毒）。

**模型注册表（一家可测多模型 — 一等概念）**：评测单元是**模型条目**，不是"家"。一个 provider 下可挂**任意多个模型，共享同一把 API key**（key 是 per-provider，模型是 per-entry）。用一份 `models.toml` 注册：
```toml
[[model]]                        # 同一家可有多条
alias = "gpt-4o"
litellm = "openai/gpt-4o"        # LiteLLM id（前缀 = 路由到哪家）
provider = "openai"              # 决定用哪把 key + 限流组
[model.params]
temperature = 0
max_tokens = 1024
structured_mode = "json_schema"  # per-model：TOOLS|JSON_SCHEMA|JSON_OBJECT|MD_JSON

[[model]]
alias = "gpt-4.1-mini"
litellm = "openai/gpt-4.1-mini"
provider = "openai"              # 同家、共用 OPENAI_API_KEY

[[model]]
alias = "qwen3-vl-plus"
litellm = "dashscope/qwen3-vl-plus"
provider = "dashscope"
[model.params]
structured_mode = "json_object"  # 非 thinking 版
```
- `Router.model_list` 从注册表构建：**每条 = 一个 deployment**，带各自 rpm/tpm/structured_mode/价格 overlay。
- `ModelSpec`（schema）= 一个模型条目；一次 run 携带 `list[ModelSpec]`，**可含同家多条**。
- CLI `--models gpt-4o,gpt-4.1-mini,qwen3-vl-plus` 按 **alias** 选子集；榜按 **alias** 排行（不是按 provider）；`cost_usd`/延迟/准确率**逐模型**统计。

下表是**家级**能力约束（编码/JSON/定价），同家所有模型共享：

**Provider × 能力矩阵**（facet B 调研，v0 接入）：

| 家 | 视觉模型 | LiteLLM 前缀 | 图编码 | JSON | 内置价 |
|---|---|---|---|---|---|
| OpenAI | gpt-4o/4.1/5.x | `openai/` | data URL+url | json_schema strict | ✅ |
| Gemini | 2.5-flash/pro | `gemini/` | base64(兼容层) | 原生 response_schema | ✅ |
| Qwen-VL | qwen-vl-max/plus, qwen2.5/3-vl | `dashscope/` | data URL+url | json_object/schema(非thinking) | ⚠部分 |
| 豆包 Doubao | 1.5-vision-pro, seed-2.0 | `volcengine/<ep>` | data URL+url, **system=str** | json(beta) | ❌需overlay |
| Grok | grok-2-vision, grok-4.x | `xai/` | data URL+url(仅jpg/png) | json_schema(grok-4) | ✅(3+) |
| Kimi | moonshot-*-vision, k2.5 | `moonshot/` | **仅 base64** | json_object/schema | ⚠部分 |
| GLM | glm-4v/4.5v/4.6v | `zai/` | url+base64 | response_format(VL 需实测) | ✅ |
| LongCat | Flash-Omni | `openai/`+api_base | 契约待实测 | 未知 | ❌需overlay·实验位 |

### 5.5 评测引擎与交付
- **自己写 ~300 行 async map-reduce**（不引重框架；已有 LiteLLM 成本 + Instructor 校验）。**不用 LangGraph**（确定性单遍 map-reduce，纯 asyncio）。
- **双缓存**：调用缓存（内容寻址 → 重跑免费）+ 打分缓存（改指标不重调）。
- **统计**：bootstrap 置信区间 + Holm 校正 McNemar 两两比较；**成本×准确率 Pareto** 是决策视图。
- **交付 = 单 core + 两薄壳**：`core.predict()` 唯一模型 I/O；**Typer CLI**（可复现评测台，吃 JSONL manifest）+ **Gradio Web**（v1，拖拽多图/多选模型/结果表/导出）。**JSONL manifest**（非 CSV），CSV 仅人看榜导出。
- **打包**：uv `[project.scripts]` + `.env`（pydantic-settings）；Docker 兜底。依赖闭包刻意最小。

## 6. 评测集（v0 轻 → v2 严谨）
- **v0**：~30 张手挑图（稀有 + 易混两维），`manifest.jsonl` 带 gold `speciesCode` + 授权字段。内部用 iNat CC-BY-NC 可；**对外再分发须降 CC0/CC-BY → 人审**（license 红线）。
- **v2**：~150 图 / ~40 簇，2×2（稀有×易混）分层每格~35，组内铺开性别/年龄/色型；同属姊妹种 ∩ 混淆矩阵高混淆对；专家双确认 + 分歧仲裁；污染控制（post-cutoff + 剔公开集 + 私有 split）；attribution manifest。
- 每图元数据：source/license/attribution · gold speciesCode + 科属种 · confusable_group/rarity_tier/confusability_tier · sex/age/plumage · geo(lat/lng/date, 公平处理 geo-prior) · quality_tags · verification · leakage。

## 7. 已验证证据（真数据冒烟，非空谈）
`.venv/bin/python` 对真实 `raw/ebird_taxonomy.2026-07-04.jsonl`（17,891 taxa）跑解析：

| 输入 | 结果 | 证明 |
|---|---|---|
| `Cooper's Hawk`(俗名) | → `coohaw` | 阶 3 ✓ |
| `Astur cooperii`(现学名) | → `coohaw` | 阶 2 ✓（快照用现名） |
| `Accipiter cooperii`(旧属名) | → **UNRESOLVED** | **证明阶 4 同义 overlay 必需** |
| `Buteo jamaicensis borealis`(亚种) | → `erthaw1`(亚种码) | **证明阶 5 rollup 必需**（收敛到种） |
| `Sparg de Cooper`(假名) | → UNRESOLVED | 幻觉正确落弃答 ✓ |

**遗留坑**：阶 4 同义 gazetteer 本地数据不足（`avibase_map` 只单向 code→avibase），需**单独 build**（Wikidata P1420 等）—— 已列为 S4，标 `ready-for-human`。

## 8. 关键引用
VLM4Bio [2408.16176](https://arxiv.org/abs/2408.16176) · RealBirdID [2603.27033](https://arxiv.org/html/2603.27033) · Prompting Scientific Names [2310.09929](https://arxiv.org/pdf/2310.09929) · CoT hurts FGVC [2601.06993](https://arxiv.org/html/2601.06993v1) · Making Better Mistakes [1912.09393](https://arxiv.org/pdf/1912.09393) · iNaturalist [1707.06642](https://arxiv.org/abs/1707.06642) · Nature 多档 [s41598-025-34944-x](https://www.nature.com/articles/s41598-025-34944-x) · gnparser [repo](https://github.com/gnames/gnparser) · GN eBird 源#187 v2019 [link](https://verifier.globalnames.org/data_sources/187) · LiteLLM Router [docs](https://docs.litellm.ai/docs/routing) · 自定义定价 [docs](https://docs.litellm.ai/docs/sdk_custom_pricing) · Inspect AI [link](https://inspect.aisi.org.uk/) · promptfoo [repo](https://github.com/promptfoo/promptfoo) · Gradio [pypi](https://pypi.org/project/gradio/) · uv [docs](https://docs.astral.sh/uv/)

## 9. 纪律（carried over）
Schema 铁律（模型输出全进 Pydantic）· library-first（commodity 直接装库，不手搓）· eval 即闸门 · 非阻塞 · license 红线（依赖 Apache/MIT/CC0；数据 CC0/CC-BY，禁 AGPL/CC-BY-NC 对外）· 解析路径无 LLM · 写者≠校验者。
