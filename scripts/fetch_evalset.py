#!/usr/bin/env python3
"""S10：从 iNaturalist 拉 CC 授权 research-grade 鸟照，配 gold speciesCode 建评测集。见 §6。

按俗名挑种 → registry 解析出 speciesCode+学名+科属种 → iNat 查最优 CC 观察 →
下载图(按 magic bytes 定扩展名) → 写 manifest.jsonl + ATTRIBUTION.md（授权/署名/溯源）。
用法: fetch_evalset.py [--smoke] [--limit N]。CC-BY-NC 仅私仓内部（对外换 CC0/CC-BY,v2）。
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

# 2×2-lite 策展（俗名可靠 → registry 解析出码/学名）。tags: rarity / confusability / group
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
    # 易混对（同科/同属，压 §7 路径）
    ("Cooper's Hawk", "common", "confusable", "accipiter"),
    ("Sharp-shinned Hawk", "common", "confusable", "accipiter"),
    ("Downy Woodpecker", "common", "confusable", "dryobates"),
    ("Hairy Woodpecker", "common", "confusable", "dryobates"),
    ("House Finch", "common", "confusable", "finch"),
    ("Purple Finch", "uncommon", "confusable", "finch"),
    ("Least Flycatcher", "uncommon", "confusable", "empidonax"),
    ("Willow Flycatcher", "uncommon", "confusable", "empidonax"),
    # 稀有/受限 × 易辨（长尾 + OOD）
    ("Painted Bunting", "uncommon", "distinctive", None),
    ("Vermilion Flycatcher", "uncommon", "distinctive", None),
    ("Roseate Spoonbill", "uncommon", "distinctive", None),
    ("Wood Duck", "common", "distinctive", None),
    ("Pileated Woodpecker", "uncommon", "distinctive", None),
    ("Belted Kingfisher", "common", "distinctive", None),
    ("Snowy Owl", "rare", "distinctive", None),
    ("Great Gray Owl", "rare", "distinctive", None),
    # 稀有 × 易混（最难格）
    ("Herring Gull", "common", "confusable", "gull"),
    ("Ring-billed Gull", "common", "confusable", "gull"),
    ("Greater Scaup", "uncommon", "confusable", "scaup"),
    ("Lesser Scaup", "uncommon", "confusable", "scaup"),
    ("Common Redpoll", "rare", "confusable", "redpoll"),
    ("Hoary Redpoll", "rare", "confusable", "redpoll"),
]

_UA = "birdbench-evalset/0.1 (research eval; CC media)"
_API = "https://api.inaturalist.org/v1/observations"


def _ext(data: bytes) -> str:
    """按 magic bytes 定真实扩展名（iNat 有 jpg/png/webp）。"""
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_one(names: list[str]) -> dict | None:
    r = None
    for name in names:  # 先俗名(稳定,抗属重分类)后学名
        q = urllib.parse.urlencode(
            {
                "taxon_name": name,
                "quality_grade": "research",
                "photo_license": "cc-by,cc-by-nc,cc0",
                "per_page": 1,
                "order_by": "votes",
                "order": "desc",
            }
        )
        d = _get(f"{_API}?{q}")
        r = (d.get("results") or [None])[0]
        if r and r.get("photos"):
            break
    if not r or not r.get("photos"):
        return None
    p = r["photos"][0]
    return {
        "obs_id": r.get("id"),
        "photo_url": (p.get("url") or "").replace("square", "medium"),
        "license": p.get("license_code"),
        "attribution": p.get("attribution"),
        "observer": (r.get("user") or {}).get("login"),
        "observed_on": r.get("observed_on"),
        "uploaded_on": (r.get("created_at") or "")[:10],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="只拉前 3 个验证流程")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    reg = load_registry()
    IMAGES.mkdir(parents=True, exist_ok=True)
    targets = CURATED[:3] if args.smoke else (CURATED[: args.limit] if args.limit else CURATED)

    rows, attrib, skipped = [], [], []
    for common, rarity, confus, group in targets:
        ro = resolve(common, reg)
        code = ro.matched_species_code
        tax = reg.taxonomy_of(code) if code else None
        if not code or not tax:
            skipped.append((common, "解析不到种码"))
            continue
        try:
            got = fetch_one([common, tax.sci_name])
        except Exception as e:
            skipped.append((common, f"iNat 查询失败 {e}"))
            continue
        if not got:
            skipped.append((common, "无 CC research-grade 照片"))
            continue
        try:
            req = urllib.request.Request(got["photo_url"], headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
        except Exception as e:
            skipped.append((common, f"下载失败 {e}"))
            continue
        ext = _ext(data)
        img_path = IMAGES / f"{code}.{ext}"
        img_path.write_bytes(data)
        rows.append(
            {
                "id": code,
                "image": f"images/{code}.{ext}",
                "truth": {
                    "species_code": code,
                    "genus": tax.genus,
                    "family": tax.family_sci,
                    "order": tax.order,
                },
                "meta": {
                    "common_name": common,
                    "scientific_name": tax.sci_name,
                    "rarity_tier": rarity,
                    "confusability_tier": confus,
                    "confusable_group": group,
                    "source": "inaturalist",
                    "source_obs_id": got["obs_id"],
                    "license": got["license"],
                    "observer": got["observer"],
                    "observed_on": got["observed_on"],
                    "uploaded_on": got["uploaded_on"],
                    "verification": "inat_research_grade+owner_review_pending",
                },
            }
        )
        attrib.append(
            f"- **{common}** ({tax.sci_name}, `{code}`): {got['attribution']} "
            f"— iNat obs {got['obs_id']}, {got['license']}"
        )
        print(f"  ✓ {common:22s} → {code:8s} {img_path.stat().st_size}B  {got['license']}")
        time.sleep(1.0)  # 对 iNat 礼貌

    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    (EVAL / "manifest.jsonl").write_text(lines + "\n")
    (EVAL / "ATTRIBUTION.md").write_text(
        "# 评测集图片授权与署名（iNaturalist, CC）\n\n"
        "CC-BY-NC 仅私仓内部非商用评测；对外再分发须换 CC0/CC-BY（v2 人审）。真值待负责人复核。\n\n"
        + "\n".join(attrib)
        + "\n"
    )
    print(f"\n{len(rows)} 图 → {EVAL/'manifest.jsonl'}；跳过 {len(skipped)}: {skipped}")


if __name__ == "__main__":
    main()
