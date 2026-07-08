# 评测集构成（V1-7）

**111 图 / 37 种**（v0 的 26→111，4.3×，统计功效大增）。混合构成：~37 种 × 每种 3 图（不同 iNat 观察=不同个体/角度/羽色），dHash 去重。源：iNaturalist CC research-grade。生成：`scripts/fetch_evalset.py --per-species 3`。

## 分层
| 维度 | 分布 |
|---|---|
| 稀有度 | common 69 · uncommon 36 · rare 6 |
| 易混度 | distinctive 54 · confusable 57（近半硬例）|
| 目 | 9 目；Passeriformes 48 主导（真实多样性）|
| 易混组 | accipiter/dryobates/finch/empidonax/sparrow/chickadee/scaup/yellowlegs 各 6，gull 三路 9 |
| license | cc-by-nc 91 · cc-by 17 · cc0 3 |

## 授权（对齐负责人决策）
私仓 + 只跑推理（不训练/不对外再分发）→ CC-BY-NC 可用。**仅当公开仓库=对外再分发图片时**才需 CC0/CC-BY（届时 20 张 cc-by/cc0 可留，91 张 cc-by-nc 需换）。ATTRIBUTION.md 逐图署名。

## pin 快照纪律的收获
首拉有 4 种解析不到码 → 暴露策展表**过时名**：`Herring Gull`（快照已拆 American/European）、`Common/Hoary Redpoll`（eBird 已合并为单一 Redpoll）。换成快照能解析的名（American Herring Gull + California Gull 三路；Greater/Lesser Yellowlegs 对）。**code-to-code + pin 版本把过时名照了出来。**

## 已知边界（v2）
- **污染**：iNat 公开图或在模型训练集内 → 绝对准确率或偏高，**相对**排名仍有效。彻底 post-cutoff 时间留出待 v2。
- **真值复核**：`verification=inat_research_grade+owner_review_pending`，负责人抽检待办。
- **answerable-only**：iNat research-grade 皆可答；"不可答"（无法定种）样本待 v2。
- **鲁棒性韧性**：fetch 带 503 退避重试 + 暂存-达阈值才替换（防"预清空+拉取失败=删好数据"，曾踩此坑）。
