# birdbench

**多模型多模态 API · 鸟类开集物种识别评测台**（standalone / 可拷给产品端）

输入一张鸟图 → 让各家多模态大模型（GPT-4o / Gemini / Qwen-VL / 豆包 / Grok / Kimi / GLM …）
开集预测物种 → 确定性解析成 **eBird `speciesCode`** → 由分类学表白送 **科 / 属 / 目** →
跨模型对比**准确率 + 成本**。

两个用途，一套 core：
1. **评测台** —— 固定评测集跑多家模型，产出可复现排行榜（准确率 / 成本 / 延迟）。
2. **产品端测试工具** —— 拖图 / 批量跑，方便同事直接测各家 API。

> **MVP 范围**：图 → `speciesCode` + 科属种。summary/百科**不在 MVP**（有了 `speciesCode` 随时能接回）。
> 分类学真源 = pinned [`bird-taxonomy`](https://github.com/xinzhuwang-wxz/bird-taxonomy)（vendor 进 `data/taxonomy/`）。

## 状态

Bootstrapped。实现按 `BACKLOG.md` / GitHub issues 的 **S0–S11** 垂直切片推进（TDD + eval 闸门）。
完整设计与最佳实践依据见 **[`docs/DESIGN.md`](docs/DESIGN.md)**。

## 快速开始（目标形态，随切片落地）

```bash
uv sync
cp .env.example .env            # 填各家 API key
uv run birdbench models         # 列可用模型
uv run birdbench run data/evalset/manifest.jsonl -o runs/   # 跑评测 → HTML 榜
uv run birdbench resolve "Cooper's Hawk"   # 名字→ebird_code 解析冒烟
# uv run birdbench web          # (v1) Gradio 拖拽台
```

## 布局

```
src/birdbench/
  core.py        predict(image, model, prompt) -> Prediction   ← 唯一模型 I/O
  gateway.py     LiteLLM Router 薄壳（base64 图 + per-call 成本 + 价格 overlay）
  structured.py  Instructor 解码 seam（per-model mode）
  resolve/       名字 → ebird_code 确定性阶梯（gnparser + rapidfuzz + gazetteer + registry）
  score.py       top-k · 目科属种逐级 · LCA 部分分 · 四桶分离
  bench.py       async map-reduce + 双缓存        report.py  HTML 榜 + Pareto + 统计
  schemas.py     Prediction / RunManifest / ResolutionOutcome …
  cli.py (Typer) │ web.py (Gradio, v1)
data/taxonomy/   vendored bird-taxonomy 快照（pinned SHA，见 docs/DESIGN.md）
data/evalset/    manifest.jsonl + images/
```

## License

代码 MIT。数据（vendored eBird/Clements 分类学）为事实性标识符映射，署名见 `data/taxonomy/PROVENANCE.md`。
依赖只用 Apache/MIT/CC0（禁 AGPL / CC-BY-NC）。
