#!/usr/bin/env bash
# 从 pinned bird-taxonomy 重新 vendor 分类学快照到 data/taxonomy/。
# 用法: scripts/sync-taxonomy.sh [<commit-sha>]
set -euo pipefail

SHA="${1:-87d5735cd36baeacb5833689ab5bf9558c3824b3}"
REPO="https://github.com/xinzhuwang-wxz/bird-taxonomy.git"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/taxonomy"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ clone bird-taxonomy @ $SHA"
git clone --quiet "$REPO" "$TMP/bt"
git -C "$TMP/bt" checkout --quiet "$SHA"

RAW="$(ls "$TMP/bt"/raw/ebird_taxonomy.*.jsonl | head -1)"
mkdir -p "$DEST/raw"
cp "$TMP/bt/data/species.jsonl"      "$DEST/species.jsonl"
cp "$TMP/bt/data/rollup.jsonl"       "$DEST/rollup.jsonl"
cp "$TMP/bt/data/avibase_map.jsonl"  "$DEST/avibase_map.jsonl"
cp "$RAW"                            "$DEST/raw/$(basename "$RAW")"

echo "→ vendored to $DEST (pinned $SHA)"
echo "  记得更新 data/taxonomy/PROVENANCE.md 的 pinned commit + 日期。"
