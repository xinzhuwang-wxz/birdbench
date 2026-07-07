"""报告：predictions.jsonl → 按 (model,prompt) 聚合榜 + 自包含 HTML（表+Pareto）。见 §5.5。

榜从 predictions.jsonl 确定性重生成。bootstrap CI 已加；McNemar 两两显著性留 V1。
"""

from __future__ import annotations

import html
import json
import random
from collections import defaultdict
from pathlib import Path

from birdbench.schemas import LeaderboardRow, PredictionRecord
from birdbench.score import ItemScore, aggregate


def load_predictions(path: str | Path) -> list[PredictionRecord]:
    lines = Path(path).read_text().splitlines()
    return [PredictionRecord.model_validate_json(x) for x in lines if x.strip()]


def _pctl(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    f = int(k)
    return xs[f] if f + 1 >= len(xs) else xs[f] + (k - f) * (xs[f + 1] - xs[f])


def bootstrap_ci(flags: list[bool], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """准确率的 95% bootstrap CI（seeded → 确定性可复现）。"""
    if not flags:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(flags)
    means = sorted(sum(flags[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot)])


def _to_itemscore(sc: dict) -> ItemScore:
    return ItemScore(
        bucket=sc["bucket"],
        top1_correct=sc["top1"],
        top3_correct=sc["top3"],
        top5_correct=sc["top5"],
        genus_correct=sc["genus"],
        family_correct=sc["family"],
        order_correct=sc["order"],
        lca=sc["lca"],
    )


def build_leaderboard(records: list[PredictionRecord]) -> list[LeaderboardRow]:
    """按 (model_alias, prompt_version) 聚合成榜行，按端到端准确率降序 + rank。"""
    groups: dict[tuple[str, str], list[PredictionRecord]] = defaultdict(list)
    for r in records:
        groups[(r.model_alias, r.prompt_version)].append(r)

    rows: list[LeaderboardRow] = []
    for (alias, pver), recs in groups.items():
        scored = [r for r in recs if r.scores]
        agg = aggregate([_to_itemscore(r.scores) for r in scored])
        costs = [r.cost_usd for r in recs if r.cost_usd is not None]
        a_count = agg.get("buckets", {}).get("A", 0)
        lat = [r.latency_ms for r in recs]
        rows.append(
            LeaderboardRow(
                model_alias=alias,
                prompt_version=pver,
                n=agg.get("n", 0),
                top1_species_acc=agg.get("top1_species_acc", 0.0),
                top3_species_acc=agg.get("top3_species_acc", 0.0),
                top5_species_acc=agg.get("top5_species_acc", 0.0),
                genus_acc=agg.get("genus_acc", 0.0),
                family_acc=agg.get("family_acc", 0.0),
                order_acc=agg.get("order_acc", 0.0),
                lca_score=agg.get("lca_score", 0.0),
                resolver_conditional_acc=agg.get("resolver_conditional_acc", 0.0),
                end_to_end_acc=agg.get("end_to_end_acc", 0.0),
                abstain_rate=agg.get("abstain_rate", 0.0),
                parse_fail_rate=agg.get("parse_fail_rate", 0.0),
                schema_valid_rate=(sum(r.schema_valid for r in recs) / len(recs)) if recs else 0.0,
                latency_p50_ms=_pctl(lat, 0.5),
                latency_p95_ms=_pctl(lat, 0.95),
                cost_per_item_usd=(sum(costs) / len(costs)) if costs else None,
                cost_per_correct_usd=(sum(costs) / a_count) if costs and a_count else None,
                total_tokens=sum(r.usage.total_tokens for r in recs),
            )
        )
    rows.sort(key=lambda r: r.end_to_end_acc, reverse=True)
    for i, r in enumerate(rows):
        r.rank = i + 1
    return rows


def _pareto_svg(rows: list[LeaderboardRow]) -> str:
    """成本×准确率散点（x=cost/item, y=端到端准确率）。cost=None 的画在 x=0。"""
    pts = [(r.cost_per_item_usd or 0.0, r.end_to_end_acc, r.model_alias) for r in rows]
    if not pts:
        return "<p>(无数据)</p>"
    xmax = max(p[0] for p in pts) or 1.0
    w, h, pad = 420, 260, 40
    dots = []
    for x, y, label in pts:
        cx = pad + (x / xmax) * (w - 2 * pad)
        cy = h - pad - y * (h - 2 * pad)
        dots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#3b82f6"/>'
            f'<text x="{cx + 7:.1f}" y="{cy:.1f}" font-size="10">{html.escape(label)}</text>'
        )
    return (
        f'<svg width="{w}" height="{h}" style="border:1px solid #ccc">'
        f'<text x="{w / 2}" y="{h - 8}" font-size="10" text-anchor="middle">cost/item →</text>'
        f'<text x="12" y="{h / 2}" font-size="10" transform="rotate(-90 12 {h / 2})">acc →</text>'
        + "".join(dots)
        + "</svg>"
    )


_COLS = [
    ("rank", "#"), ("model_alias", "model"), ("prompt_version", "prompt"), ("n", "n"),
    ("top1_species_acc", "top1"), ("top5_species_acc", "top5"), ("genus_acc", "genus"),
    ("family_acc", "family"), ("lca_score", "LCA"), ("resolver_conditional_acc", "解析条件"),
    ("end_to_end_acc", "端到端"), ("abstain_rate", "弃答"), ("parse_fail_rate", "解析失败"),
    ("schema_valid_rate", "schema✓"), ("latency_p50_ms", "p50ms"),
    ("cost_per_item_usd", "$/item"), ("total_tokens", "tokens"),
]


def render_html(rows: list[LeaderboardRow], *, title: str = "birdbench leaderboard") -> str:
    def cell(r: LeaderboardRow, key: str) -> str:
        v = getattr(r, key)
        if v is None:
            return "unpriced"
        if isinstance(v, float):
            return f"{v:.3f}" if key != "cost_per_item_usd" else f"{v:.5f}"
        return str(v)

    head = "".join(f"<th>{html.escape(lbl)}</th>" for _, lbl in _COLS)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell(r, k))}</td>" for k, _ in _COLS) + "</tr>"
        for r in rows
    )
    return (
        f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>"
        "<style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse}"
        "td,th{border:1px solid #ddd;padding:4px 8px;text-align:right}"
        "td:nth-child(2),th:nth-child(2){text-align:left}h2{margin-top:24px}</style>"
        f"<h1>{html.escape(title)}</h1>"
        f"<h2>成本 × 准确率 (Pareto)</h2>{_pareto_svg(rows)}"
        f"<h2>Leaderboard（按端到端准确率）</h2><table><tr>{head}</tr>{body}</table>"
    )


def write_report(records: list[PredictionRecord], out_path: str | Path) -> list[LeaderboardRow]:
    rows = build_leaderboard(records)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_html(rows))
    (p.parent / "leaderboard.json").write_text(
        json.dumps([r.model_dump() for r in rows], ensure_ascii=False, indent=2)
    )
    return rows
