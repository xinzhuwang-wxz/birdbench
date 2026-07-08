# V1 · M3 里程碑 verify（V1-8 归一化 + V1-5 Web）

日期：2026-07-08。基准：**pin 快照 code-to-code**（gold 与预测都解析到同一 bird-taxonomy 快照的 speciesCode）。

## V1-5 Gradio Web — 压测 STABLE
qa-tester 编程级人类模拟（gradio_client 打真实 `/gradio_api` 端点 = 浏览器点击同一路径）：

- **14/14 PASS**。识别×3模型/PNG分支/空输入/非图对抗/排行榜valid·malformed·empty·错类型 全兜底。
- 并发 30 identify：**100% 成功，p50 0.47s / p95 0.80s**，0 猝死。
- 服务端日志 3 个 traceback 全是 Gradio 框架对**故意对抗输入**的捕获（PIL.UnidentifiedImageError / 错文件类型），**0 应用级未捕获异常**，收尾 `/`+`/config` 仍 200。
- 注：浏览器扩展未连接 → 像素级自动化改为编程级模拟（等价前端操作）。

## V1-8 LLM 名字归一化 — extractor 非 judge，真机验证通过
便宜文字模型（doubao-lite-nothink，temp0，thinking off）跑 v0 真实数据：

| 集 | 结果 | 结论 |
|---|---|---|
| MISS（v0 真实解析器漏 9 条）| 救回 gold **0/9**，虚高 **0/9** | 归一化正确**提取模型所述的种**，绝不翻成 gold ✓ |
| 正控（合成·明确说了 gold 但凌乱 3 条）| 救回 **3/3** | 救回机制**真的有效**（模型确实凌乱说出 gold 时）✓ |

**核心保证达成**：LLM 只擦名字→再走确定性 exact 定码；对错仍 code==gold。无 LLM-as-judge 自我偏袒虚高。

## 关键修正（对着 pin 快照重看 MISS 集）
"解析器漏"分两类，**解析器行为其实是对的**：

1. **真·多义 → 弃答正确**：`Northern Goshawk`（快照拆成 American/Eurasian Goshawk）、`Herring Gull`（American/European）。老名跨多码，弃答对。
2. **模型认错种**：白化知更鸟(gold amerob)被认成 `Common Blackbird`/`White Thrush`/`Leucistic Blackbird`。与 gold 无关。
3. **唯一可补 1:1 别名**：`Common Blackbird`→eurbla。但**补了不涨准确率**（该图模型本就认错种），只把桶 C1→B 正确归类。

→ 26 图硬集的准确率天花板是**模型真的认错难例**（白化/亚成/拆分种），**非解析器欠账**。pin 版本 + 四桶分离把这照清楚了。

## 产物 / 后续
- V1-8 默认关（opt-in `--normalizer-model`）→ 不改默认行为；真机验证证明安全（不虚高）。
- 别名 overlay 降级为**诊断质量**改进（非准确率杠杆）→ #24（只补 1:1，真·多义保持弃答）。
- 仍需人：#20 成本校准（真账单）、#22 评测集扩容（授权决策）。
