#!/usr/bin/env python3
"""S10/V1-7：从 iNaturalist 拉 CC research-grade 鸟照，配 gold speciesCode 建评测集。见 §6。

混合构成：~34 种 × 每种 ~N 图（不同观察=不同个体/角度/羽色），保持稀有度×易混度分层。
dHash 去重（丢近重复照）。按俗名解析 speciesCode+科属种 → iNat 查 CC 观察 → 下载 →
写 manifest.jsonl + ATTRIBUTION.md。用法: fetch_evalset.py [--smoke] [--per-species N] [--limit K]。
CC-BY-NC 仅私仓非商用（对外分发换 CC0/CC-BY，v2）。**污染警示**：iNat 公开图或在模型训练集内。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from birdbench.registry import load_registry  # noqa: E402
from birdbench.resolve import resolve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "data" / "evalset"
IMAGES = EVAL / "images"

# 混合策展（俗名可靠 → registry 解析出码/学名）。tags: rarity / confusability / group
CURATED = [
    # 常见 × 易辨（sanity 地板）
    ("Mallard", "common", "distinctive", None),
    ("House Sparrow", "common", "distinctive", None),
    ("Northern Cardinal", "common", "distinctive", None),
    ("American Robin", "common", "distinctive", None),
    ("Blue Jay", "common", "distinctive", None),
    ("American Crow", "common", "distinctive", None),
    ("Canada Goose", "common", "distinctive", None),
    ("Rock Pigeon", "common", "distinctive", None),
    ("American Goldfinch", "common", "distinctive", None),
    ("Northern Flicker", "common", "distinctive", None),
    # 易混对（同科/同属，压 §7 路径）
    ("Cooper's Hawk", "common", "confusable", "accipiter"),
    ("Sharp-shinned Hawk", "common", "confusable", "accipiter"),
    ("Downy Woodpecker", "common", "confusable", "dryobates"),
    ("Hairy Woodpecker", "common", "confusable", "dryobates"),
    ("House Finch", "common", "confusable", "finch"),
    ("Purple Finch", "uncommon", "confusable", "finch"),
    ("Least Flycatcher", "uncommon", "confusable", "empidonax"),
    ("Willow Flycatcher", "uncommon", "confusable", "empidonax"),
    ("Song Sparrow", "common", "confusable", "sparrow"),
    ("Savannah Sparrow", "common", "confusable", "sparrow"),
    ("Black-capped Chickadee", "common", "confusable", "chickadee"),
    ("Carolina Chickadee", "common", "confusable", "chickadee"),
    # 稀有/受限 × 易辨（长尾 + OOD）
    ("Painted Bunting", "uncommon", "distinctive", None),
    ("Vermilion Flycatcher", "uncommon", "distinctive", None),
    ("Roseate Spoonbill", "uncommon", "distinctive", None),
    ("Wood Duck", "common", "distinctive", None),
    ("Pileated Woodpecker", "uncommon", "distinctive", None),
    ("Belted Kingfisher", "common", "distinctive", None),
    ("Snowy Owl", "rare", "distinctive", None),
    ("Great Gray Owl", "rare", "distinctive", None),
    # 稀有 × 易混（最难格）。gull/redpoll 旧名已被快照拆分/合并 → 换快照能解析的名
    ("American Herring Gull", "common", "confusable", "gull"),
    ("Ring-billed Gull", "common", "confusable", "gull"),
    ("California Gull", "uncommon", "confusable", "gull"),
    ("Greater Scaup", "uncommon", "confusable", "scaup"),
    ("Lesser Scaup", "uncommon", "confusable", "scaup"),
    ("Greater Yellowlegs", "uncommon", "confusable", "yellowlegs"),
    ("Lesser Yellowlegs", "uncommon", "confusable", "yellowlegs"),
]

_UA = "birdbench-evalset/0.2 (research eval; CC media)"
_API = "https://api.inaturalist.org/v1/observations"


# ---- 纯逻辑（可离线测，不碰 PIL/网络）----
def _hamming(a: int, b: int) -> int:
    """两个 dHash 的汉明距离（不同 bit 数）。"""
    return bin(a ^ b).count("1")


def _is_dup(h: int, seen: list[int], thresh: int = 6) -> bool:
    """h 与已留任一图汉明距离 ≤ thresh → 近重复。"""
    return any(_hamming(h, s) <= thresh for s in seen)


def _dhash(data: bytes) -> int | None:
    """差分哈希：9×8 灰度，逐行相邻像素比较 → 64-bit。PIL 懒加载。失败返回 None。"""
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("L").resize((9, 8))
        px = list(img.getdata())
        bits = 0
        for row in range(8):
            for col in range(8):
                left = px[row * 9 + col]
                right = px[row * 9 + col + 1]
                bits = (bits << 1) | (1 if left > right else 0)
        return bits
    except Exception:
        return None


# ---- 网络 ----
def _get(url: str, retries: int = 5) -> dict:
    """带指数退避重试（应对 503/代理连接限流）。全失败才抛。"""
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(2 * (2**i), 30))  # 2,4,8,16,30
    raise last if last else RuntimeError("unreachable")


def fetch_candidates(names: list[str], want: int) -> list[dict]:
    """查 iNat：不同观察(≈不同个体) → 候选照片记录列表（≥want，留 buffer 供去重/失败）。"""
    for name in names:  # 先俗名(稳定,抗属重分类)后学名
        q = urllib.parse.urlencode({
            "taxon_name": name,
            "quality_grade": "research",
            "photo_license": "cc-by,cc-by-nc,cc0",
            "per_page": max(want * 3, 8),
            "order_by": "votes",
            "order": "desc",
        })
        d = _get(f"{_API}?{q}")
        results = d.get("results") or []
        out = []
        for r in results:
            if not r.get("photos"):
                continue
            p = r["photos"][0]
            out.append({
                "obs_id": r.get("id"),
                "photo_url": (p.get("url") or "").replace("square", "medium"),
                "license": p.get("license_code"),
                "attribution": p.get("attribution"),
                "observer": (r.get("user") or {}).get("login"),
                "observed_on": r.get("observed_on"),
                "uploaded_on": (r.get("created_at") or "")[:10],
            })
        if out:
            return out
    return []


def _download(url: str, retries: int = 4) -> bytes | None:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            time.sleep(min(2 * (2**i), 20))
    return None


def _ext(data: bytes) -> str:
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="只拉前 3 种验证流程")
    ap.add_argument("--per-species", type=int, default=3, help="每种目标图数")
    ap.add_argument("--limit", type=int, default=0, help="只取前 K 种")
    args = ap.parse_args()

    reg = load_registry()
    # 写暂存区，达阈值才原子替换 images/（防"预清空后拉取失败=删了好数据"）
    stage = EVAL / "_staging_images"
    if stage.exists():
        for f in stage.glob("*"):
            f.unlink()
    stage.mkdir(parents=True, exist_ok=True)
    targets = CURATED[:3] if args.smoke else (CURATED[: args.limit] if args.limit else CURATED)

    rows, attrib, skipped, seen_hashes = [], [], [], []
    for common, rarity, confus, group in targets:
        ro = resolve(common, reg)
        code = ro.matched_species_code
        tax = reg.taxonomy_of(code) if code else None
        if not code or not tax:
            skipped.append((common, "解析不到种码"))
            continue
        try:
            cands = fetch_candidates([common, tax.sci_name], args.per_species)
        except Exception as e:  # noqa: BLE001
            skipped.append((common, f"iNat 查询失败 {e}"))
            continue
        kept = 0
        for cand in cands:
            if kept >= args.per_species:
                break
            data = _download(cand["photo_url"])
            if not data:
                continue
            h = _dhash(data)
            if h is not None and _is_dup(h, seen_hashes):
                continue  # 近重复照，丢
            if h is not None:
                seen_hashes.append(h)
            idx = kept
            item_id = f"{code}-{idx}"
            ext = _ext(data)
            (stage / f"{item_id}.{ext}").write_bytes(data)
            rows.append({
                "id": item_id,
                "image": f"images/{item_id}.{ext}",
                "truth": {
                    "species_code": code, "genus": tax.genus,
                    "family": tax.family_sci, "order": tax.order,
                },
                "meta": {
                    "common_name": common, "scientific_name": tax.sci_name,
                    "rarity_tier": rarity, "confusability_tier": confus,
                    "confusable_group": group, "source": "inaturalist",
                    "source_obs_id": cand["obs_id"], "license": cand["license"],
                    "observer": cand["observer"], "observed_on": cand["observed_on"],
                    "uploaded_on": cand["uploaded_on"],
                    "verification": "inat_research_grade+owner_review_pending",
                },
            })
            attrib.append(
                f"- **{common}** ({tax.sci_name}, `{item_id}`): {cand['attribution']} "
                f"— iNat obs {cand['obs_id']}, {cand['license']}"
            )
            kept += 1
            time.sleep(0.7)  # 对 iNat 礼貌
        print(f"  {common:24s} → {code:8s} 留 {kept}/{args.per_species} 图")
        if kept == 0:
            skipped.append((common, "无 CC research-grade 照片(或全去重)"))

    n_sp = len({r["truth"]["species_code"] for r in rows})
    expected = len(targets)
    if n_sp < max(3, int(0.7 * expected)):  # 拉太少(多半限流) → 中止,保留现有 images/ 不动
        print(
            f"\n⚠️ 只拉到 {len(rows)} 图/{n_sp} 种(期望~{expected}) <70% → 中止，"
            f"**保留现有 images/ 不动**。暂存 {stage}。跳过 {len(skipped)} 例(多为限流)。"
        )
        return
    # 达阈值 → 原子替换 images/
    if IMAGES.exists():
        for f in IMAGES.glob("*"):
            f.unlink()
    IMAGES.mkdir(parents=True, exist_ok=True)
    for f in stage.glob("*"):
        f.rename(IMAGES / f.name)
    stage.rmdir()
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    (EVAL / "manifest.jsonl").write_text(lines + "\n")
    (EVAL / "ATTRIBUTION.md").write_text(
        "# 评测集图片授权与署名（iNaturalist, CC）\n\n"
        "CC-BY-NC 仅私仓内部非商用评测；对外再分发须换 CC0/CC-BY（v2 人审）。真值待负责人复核。\n"
        "**污染警示**：iNat 公开图可能已在模型训练集内 → 绝对准确率或偏高；"
        "跨模型**相对**排名仍有效。彻底的时间留出(post-cutoff)需 v2。\n\n"
        + "\n".join(attrib) + "\n"
    )
    print(f"\n{len(rows)} 图 / {n_sp} 种 → {EVAL/'manifest.jsonl'}；跳过 {len(skipped)}: {skipped}")


if __name__ == "__main__":
    main()
