"""生成排行榜图表到 docs/assets/（顶刊级；web 与飞书文档共用）。数据=v1 111图实测。

用法: .venv-web/bin/python scripts/make_charts.py（需 matplotlib）。改数据后重跑刷新。
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
    "figure.dpi": 220, "savefig.dpi": 220, "savefig.bbox": "tight", "axes.axisbelow": True,
})
BLUE, ORANGE, GREEN, VERM, GRAY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#8a8a8a"
OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

# (name, top1, ci_lo, ci_hi, A, B, C1, D, $/item, $/correct, tier)
M = [
    ("doubao-lite-nothink", 0.72, 0.63, 0.80, 80, 25, 6, 0, 0.00025, 0.00035, 1),
    ("doubao-lite-think", 0.71, 0.62, 0.79, 79, 24, 8, 0, 0.00051, 0.00072, 1),
    ("qwen3-vl-plus", 0.48, 0.38, 0.57, 53, 42, 16, 0, 0.00069, 0.00144, 2),
    ("qwen3-vl-plus-t0.8", 0.47, 0.37, 0.57, 52, 39, 20, 0, 0.00068, 0.00145, 2),
    ("qwen3-vl-flash", 0.47, 0.37, 0.57, 52, 42, 17, 0, 0.00005, 0.00011, 2),
]


def leaderboard() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    order = sorted(M, key=lambda m: m[1])
    names = [m[0] for m in order]
    acc = [m[1] for m in order]
    lo = [m[1] - m[2] for m in order]
    hi = [m[3] - m[1] for m in order]
    colors = [BLUE if m[10] == 1 else ORANGE for m in order]
    y = range(len(order))
    ax.barh(y, acc, xerr=[lo, hi], color=colors, edgecolor="white", height=0.62,
            error_kw=dict(ecolor="#333", elinewidth=1.2, capsize=4))
    for i, m in enumerate(order):
        ax.text(m[1] + max(hi) + 0.015, i, f"{m[1]:.2f}", va="center", fontweight="bold")
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.set_xlabel("Top-1 species accuracy (95% CI)")
    ax.set_xlim(0, 0.95)
    ax.set_title("birdbench leaderboard  ·  n=111 images", fontweight="bold", loc="left")
    ax.legend(handles=[Patch(color=BLUE, label="Tier 1 (Doubao)"),
                       Patch(color=ORANGE, label="Tier 2 (Qwen)")],
              loc="lower right", frameon=False, fontsize=9.5)
    fig.savefig(OUT / "leaderboard.png")
    plt.close(fig)


def pareto() -> None:
    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    front = {"doubao-lite-nothink", "qwen3-vl-flash"}
    for m in M:
        f = m[0] in front
        ax.scatter(m[9], m[1], s=150 if f else 90, color=(GREEN if f else GRAY),
                   edgecolor="black", linewidth=1.1, zorder=3, marker="o" if f else "X")
        ax.annotate(m[0], (m[9], m[1]), xytext=(m[9] * 1.06, m[1] + 0.012),
                    fontweight="bold" if f else "normal", fontsize=9)
    fr = sorted([m for m in M if m[0] in front], key=lambda x: x[9])
    ax.plot([fr[0][9], fr[1][9]], [fr[0][1], fr[1][1]], "--", color=GREEN, linewidth=1.3)
    ax.set_xscale("log")
    ax.set_xlabel("Cost per correct ID (USD, log)  →  cheaper is left")
    ax.set_ylabel("Top-1 accuracy")
    ax.set_ylim(0.4, 0.8)
    ax.set_title("Cost-accuracy Pareto frontier", fontweight="bold", loc="left")
    fig.savefig(OUT / "pareto.png")
    plt.close(fig)


def buckets() -> None:
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    order = sorted(M, key=lambda m: m[4])
    names = [m[0] for m in order]
    a = [m[4] for m in order]
    b = [m[5] for m in order]
    c = [m[6] for m in order]
    y = range(len(order))
    ax.barh(y, a, color=GREEN, height=0.62, label="A correct", edgecolor="white")
    ax.barh(y, b, left=a, color=VERM, height=0.62, label="B wrong species", edgecolor="white")
    ax.barh(y, c, left=[x + z for x, z in zip(a, b, strict=True)], color=GRAY, height=0.62,
            label="C1 resolver miss", edgecolor="white")
    ax.set_yticks(list(y))
    ax.set_yticklabels(names)
    ax.set_xlabel("Images (n=111)")
    ax.set_xlim(0, 111)
    ax.set_title("Where errors come from  ·  four-bucket split", fontweight="bold", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), frameon=False, ncol=3)
    fig.subplots_adjust(bottom=0.26)
    fig.savefig(OUT / "buckets.png")
    plt.close(fig)


if __name__ == "__main__":
    leaderboard()
    pareto()
    buckets()
    print("charts →", OUT)
