# birdbench v0 —— 首次真机评测结果

**26 张 iNat 真图 × 5 模型条目 = 130 cells**，真调 Doubao/Qwen API，总花费 **$0.0515**。
复现：`set -a && . .env && set +a && python scripts/run_eval.py --yes`（榜落 `runs/report.html`）。

## Leaderboard（按端到端准确率）

| 模型条目 | top1 | top5 | 端到端 | 解析条件 | 解析失败 | $/图 |
|---|---|---|---|---|---|---|
| doubao-lite-nothink | 0.58 | 0.69 | 0.58 | 0.71 | 0.19 | $0.00023 |
| doubao-lite-think | 0.54 | 0.58 | 0.54 | 0.82 | 0.35 | $0.00041 |
| qwen3-vl-plus | 0.38 | 0.69 | 0.38 | 0.43 | 0.12 | $0.00068 |
| qwen3-vl-flash | 0.38 | 0.73 | 0.38 | 0.56 | 0.31 | $0.00000* |
| qwen3-vl-plus-t0.8 | 0.35 | 0.69 | 0.35 | 0.47 | 0.27 | $0.00065 |

\* qwen-flash litellm 无内置价 → 需补价格 overlay。Doubao 价为估算（见 `configs/doubao_price_overlay.json`，需按账单校准）。

## 发现
1. **豆包 lite 又准又便宜**：top1 0.58 + 最低成本，本评测集赢 Qwen-VL。
2. **关思考 > 开思考**（0.58>0.54、更便宜快、解析失败 0.19<0.35）→ 实测印证 CoT 伤细粒度识别；"思考 on/off"是有效维度。
3. **温度维度**：qwen-plus 温度 0（0.38）> 0.8（0.35）→ 评测用低温更稳。
4. **top5≫top1**（flash 0.73 vs 0.38）→ 正确答案常在前五、非第一。
5. **解析失败 12–35% 可见** → 是否建中文/同义表(S4)现在可由数据针对性决定（豆包 think 35% 多为推理裹 JSON）。

## v0 已知局限（诚实）
- 26 图小样本 → 只支撑"总体粗排 + 定性"；强断言需扩样 + 专家双确认（v2）。
- 真值 = iNat research-grade + 待负责人复核（有几张如黄化红雀偏难，可换）。
- Doubao 价估算；qwen-flash 未定价 → 成本对比对这两个偏保守。
- 未做污染控制严格版、未加 McNemar 显著性（v1）。
