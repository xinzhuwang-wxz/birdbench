# CONTEXT.md — birdbench 领域词汇（ubiquitous language）

动手前先读这里对齐术语。详见 [`docs/benchmark-design.md`](docs/benchmark-design.md)（方法论）与 [`docs/DESIGN.md`](docs/DESIGN.md)（规格）。

## 核心概念

- **开集识别 (open-set)**：模型用自然语言自由说物种名（不给候选选项）。我们评的是这个能力。
- **speciesCode**：eBird 物种的唯一编码（如 `norcar` = Northern Cardinal）。跨语言、唯一、因 pin 版本而稳定 → 评测的锚。
- **code-to-code**：打分 = `预测码 == gold 码`。不比名字字符串、不用 LLM 判等。客观、可复现、无偏。
- **pinned 分类学快照**：vendored 的 `bird-taxonomy`（`data/taxonomy/`，锁 SHA）。gold 与预测锚在同一快照 → 码永不漂移。
- **gold（真值）**：每张测试图的标准答案，存成一个 speciesCode（建集时定，可人审）。

## 解析（resolve）

- **解析器 (resolver)**：把自由文本名映射成 speciesCode 的**确定性 first-hit 梯子**（`resolve.py`）。无 LLM 判对错。
- **解析阶 (ResolutionStage)**：`NORMALIZE → EXACT_CODE → EXACT_SCI → EXACT_COM → ZH_ALIAS → SYNONYM → MODIFIER_STRIP → ROLLUP_SSP → FUZZY_SCI → CODE_ALIAS → LLM_NORMALIZE → EXTERNAL(未实现) → ABSTAIN`。
- **MODIFIER_STRIP**：剥括号/修饰词（albino/morph/domestic…）回退 base 名再精确匹配（V1-1）。
- **ROLLUP_SSP / rollup**：亚种(issf)/三名 → 收敛到种。任一阶出码后一律跑 rollup 后处理。
- **LLM_NORMALIZE（extractor 非 judge）**：确定性 miss 时，用轻量文字 LLM 把凌乱名擦成干净种名，**再走确定性 exact 定码**；对错判定仍 code==gold。LLM 只提取、绝不判对错（V1-8）。
- **ABSTAIN（弃答）**：拿不准就弃答，绝不瞎猜。多义（一名映射多种）即弃答。
- **ambiguous（多义）**：一个名解析到 >1 个不同种码 → 弃答，不静默 first-win。

## 打分（score）

- **四桶 (ResolutionBucket)**：**A** 解析对 / **B** 认错种(模型账) / **C1** 给了名却没解析出码(解析器账) / **C2** 幻觉/非法输出 / **D** 弃答。分开记 → 解析器 bug 不伪装成模型错误。
- **端到端准确率 (end_to_end_acc)** = A / 非弃答：整条管线表现。
- **解析条件准确率 (resolver_conditional_acc)** = A / (A+B)：给定解析出了种，模型判对的比例 → 剔除解析器覆盖，纯看模型区分力。
- **LCA / 分类学距离**：认错种时错到哪一层（同属/同科/同目/跨目）→ 部分分 `1 − 距离/4`。
- **Mistake Severity**：认错种的平均离谱程度（LCA 高度）。

## 评测运行

- **cell / cell_id**：一个评测单元 = 维度的内容哈希（image_sha256 × model_id × params × prompt_hash × sample_idx）= 缓存键。
- **ModelSpec**：一个模型条目（alias / model_id / provider / params）。评测单元是**模型条目**不是"家"；一家可挂多模型共享一把 key。参数含温度、thinking（豆包）等。
- **PromptSpec**：版本化 prompt（`prompts/<name>.<version>.md`，同事可编辑）。prompt 是评测维度。
- **n_samples / 自洽采样**：同图采样 N 次投票；投票率 = 比口头置信更可靠的置信信号（V1-4）。
- **维度 (dimensions)**：模型 × 温度 × thinking × prompt 版本 × 采样数 × 提取器——全部前端可配、后端参数化不硬编码。

## 统计诚实

- **Clopper-Pearson CI**：准确率的精确置信区间（不靠正态近似）。
- **McNemar 精确检验 + Holm 校正**：配对显著性 + 多重比较校正。
- **显著性簇 / tied_with_best**：与榜首无显著差异的模型标为并列 → 不吹假第一。
- **校准 (calibration)**：模型多自信 vs 实际多对（AUROC_f / Brier / 过度自信差 / AURC）。

## 红黄边界

- **红（LLM 工作流）/ 黄（受控 Agent）**：本服务只负责这两块。物种识别主线本该是专用分类器；大模型只在"开集识别"与"内容层"出场。
- **成本 / $/正确**：$/正确 ID = 成本 ÷ 答对数（产品选型主指标）。价为挂牌价，待真实账单校准。
