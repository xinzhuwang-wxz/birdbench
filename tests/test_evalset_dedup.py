"""V1-7 gate: 评测集图片去重纯逻辑（汉明距离 / 近重复判定）。无 PIL 无网络。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from fetch_evalset import _hamming, _is_dup  # noqa: E402


def test_hamming():
    assert _hamming(0b1010, 0b1010) == 0
    assert _hamming(0b1010, 0b0000) == 2
    assert _hamming(0b1111, 0b0000) == 4


def test_is_dup_threshold():
    seen = [0]
    assert _is_dup(0, seen)  # 完全相同 → 重复
    assert _is_dup(0b111111, seen)  # 6 bit 差 ≤ thresh(6) → 近重复
    assert not _is_dup(0b1111111, seen)  # 7 bit 差 > 6 → 非重复
    assert not _is_dup(0b11111111, [])  # seen 空 → 非重复


def test_is_dup_matches_any_seen():
    seen = [0, (1 << 63)]
    assert _is_dup((1 << 63) | 0b11, seen)  # 与第二个仅 2 bit 差 → 重复
