"""自洽采样聚合（V1-4）：N 次采样的 resolved 种码 → 多数投票 + 投票率(置信) + 语义熵。见 research。

投票率 = 比口头置信度更可靠的置信信号（喂 V1-3）。语义熵 O(N)（"同义"=speciesCode 相等）。
"""

from __future__ import annotations

import math
from collections import Counter


def aggregate_samples(codes: list[str | None]) -> tuple[str | None, float, float]:
    """N 次采样解析出的种码 → (vote_top1, vote_fraction, semantic_entropy)。None=该样本未解析。

    vote_fraction 用总样本数(含未解析)为分母 → 保守；semantic_entropy 归一化到 [0,1]（0=全一致）。
    """
    n = len(codes)
    resolved = [c for c in codes if c]
    if not resolved:
        return (None, 0.0, 0.0)
    counts = Counter(resolved)
    vote_top1, top_count = counts.most_common(1)[0]
    vote_fraction = top_count / n
    total = len(resolved)
    ent = -sum((c / total) * math.log2(c / total) for c in counts.values())
    max_ent = math.log2(len(counts)) if len(counts) > 1 else 1.0
    return (vote_top1, vote_fraction, ent / max_ent if max_ent > 0 else 0.0)
