"""S9 gate: report（聚合榜 + bootstrap CI + 自包含 HTML）。"""

from birdbench.report import bootstrap_ci, build_leaderboard, render_html, write_report
from birdbench.schemas import GoldLabel, PredictionRecord, Usage


def _rec(alias, item, bucket, top1, cost, lca=1.0):
    return PredictionRecord(
        run_id="r",
        item_id=item,
        model_alias=alias,
        prompt_version="v0",
        image_sha256="s",
        gold=GoldLabel(species_code="x"),
        scores={
            "bucket": bucket, "top1": top1, "top3": top1, "top5": top1,
            "genus": top1, "family": top1, "order": top1, "lca": lca,
        },
        schema_valid=True,
        cost_usd=cost,
        usage=Usage(total_tokens=100),
        latency_ms=50.0,
    )


def test_build_leaderboard_ranks_by_end_to_end():
    recs = [
        _rec("good", "i1", "A", True, 0.001),
        _rec("good", "i2", "A", True, 0.001),
        _rec("bad", "i1", "B", False, 0.002, lca=0.5),
        _rec("bad", "i2", "C1", False, 0.002, lca=0.0),
    ]
    rows = build_leaderboard(recs)
    assert rows[0].model_alias == "good" and rows[0].rank == 1
    assert rows[0].end_to_end_acc == 1.0
    assert rows[1].model_alias == "bad" and rows[1].rank == 2
    assert rows[0].cost_per_item_usd == 0.001


def test_bootstrap_ci_deterministic_and_bounded():
    ci1 = bootstrap_ci([True] * 8 + [False] * 2, seed=0)
    ci2 = bootstrap_ci([True] * 8 + [False] * 2, seed=0)
    assert ci1 == ci2  # seeded → 确定可复现
    lo, hi = ci1
    assert 0.0 <= lo <= 0.8 <= hi <= 1.0


def test_render_html_selfcontained():
    rows = build_leaderboard([_rec("m1", "i1", "A", True, 0.001)])
    h = render_html(rows)
    assert "<!doctype html>" in h and "m1" in h and "Leaderboard" in h and "<svg" in h


def test_significance_and_ci(tmp_path):
    # good 全对 vs bad 全错（同 12 图）→ McNemar 显著 → bad 不并列；rows 带 Clopper-Pearson CI
    recs = [_rec("good", f"i{k}", "A", True, 0.001) for k in range(12)]
    recs += [_rec("bad", f"i{k}", "B", False, 0.001, lca=0.0) for k in range(12)]
    rows = write_report(recs, tmp_path / "r.html")
    top = rows[0]
    assert top.model_alias == "good"
    assert top.top1_ci_low <= top.top1_species_acc <= top.top1_ci_high
    assert top.tied_with_best is True
    bad = next(r for r in rows if r.model_alias == "bad")
    assert bad.tied_with_best is False  # 与最优显著不同
    assert "★" in (tmp_path / "r.html").read_text()


def test_write_report_unpriced(tmp_path):
    rows = write_report([_rec("m1", "i1", "A", True, None)], tmp_path / "report.html")
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "leaderboard.json").exists()
    assert rows[0].cost_per_item_usd is None  # 全 None → unpriced
