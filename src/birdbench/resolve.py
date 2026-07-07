"""名字→speciesCode 确定性解析阶梯（first-hit-wins, LLM 不进路径）。见 DESIGN §5.2。

阶(V0)：NORMALIZE → EXACT_CODE(仅 speciesCode) → EXACT_SCI → EXACT_COM
→ ZH_ALIAS(gz) → SYNONYM(gz) → ROLLUP_SSP(三名→二名)
→ FUZZY_SCI(rapidfuzz,属精确) → CODE_ALIAS(4字母,唯一) → ABSTAIN。
rollup 后处理内建在 registry。stage-0 轻量归一化(gnparser 可后续硬化)。
gazetteer(同义/中文) 默认空，S4 离线 build 填——本片不阻塞于 S4。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from birdbench.registry import Registry, normalize
from birdbench.schemas import ResolutionOutcome

try:
    from rapidfuzz import fuzz

    _HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover
    _HAS_RAPIDFUZZ = False


@dataclass
class Gazetteer:
    """S4 离线 build 填充：同义名 + 中文名 → 种码。默认空（本片不阻塞于 S4）。"""

    synonym: dict[str, str] = field(default_factory=dict)  # norm(学名/俗名) → speciesCode
    zh: dict[str, str] = field(default_factory=dict)  # norm(中文名) → speciesCode


_SP_RE = re.compile(r"\bsp\b")


def _canon(text: str) -> str:
    c = _SP_RE.sub(" ", normalize(text))  # 去 "sp."/"sp"
    return re.sub(r"\s+", " ", c).strip()


def _fuzzy_sci(canon: str, reg: Registry, threshold: float) -> tuple[str, float] | None:
    """属 token 精确、只模糊种加词的受限模糊（DESIGN §5.2 阶 5）。"""
    if not _HAS_RAPIDFUZZ or " " not in canon:
        return None
    genus = canon.split()[0]
    best_code, best_score = None, 0.0
    for name, codes in reg._sci.items():
        if name.split()[0] != genus:  # 属必须精确
            continue
        score = fuzz.ratio(canon, name)
        if score > best_score:
            species = {reg.resolve_to_species(c) for c in codes}
            if len(species) == 1:
                best_code, best_score = next(iter(species)), score
    if best_code and best_score >= threshold:
        return best_code, best_score / 100.0
    return None


def resolve(
    text: str,
    registry: Registry,
    gazetteer: Gazetteer | None = None,
    *,
    fuzzy_threshold: float = 92.0,
) -> ResolutionOutcome:
    """自由文本鸟名 → ResolutionOutcome（含命中阶、种码、置信、ambiguous）。"""
    gz = gazetteer or Gazetteer()
    canon = _canon(text)

    def out(stage, code=None, score=0.0, *, ambiguous=False, source=None):
        return ResolutionOutcome(
            raw_text=text,
            parsed_canonical=canon,
            stage_fired=stage,
            matched_species_code=code,
            score=score,
            ambiguous=ambiguous,
            source=source,
        )

    if not canon:
        return out("ABSTAIN", None, 0.0)

    # 1 EXACT_CODE — 仅 speciesCode（非 4 字母码）；issf 细码经 rollup
    if canon in registry.species:
        return out("EXACT_CODE", canon, 1.0, source="code")
    if canon in registry.rollup:
        return out("EXACT_CODE", registry.resolve_to_species(canon), 1.0, source="code+rollup")

    # 2 EXACT_SCI / 3 EXACT_COM（含 ambiguous → 弃答）
    for stage, fn, score in (
        ("EXACT_SCI", registry.exact_scientific, 1.0),
        ("EXACT_COM", registry.exact_common, 0.99),
    ):
        code, amb = fn(text)
        if code:
            return out(stage, code, score, source=stage.split("_")[1].lower())
        if amb:
            return out("ABSTAIN", None, 0.0, ambiguous=True)

    # 3z ZH_ALIAS（中文名，测中文模型必需）/ 4 SYNONYM（旧属名/同义名）——gazetteer 由 S4 填
    if canon in gz.zh:
        return out("ZH_ALIAS", registry.resolve_to_species(gz.zh[canon]), 0.98, source="zh")
    if canon in gz.synonym:
        return out("SYNONYM", registry.resolve_to_species(gz.synonym[canon]), 0.97, source="gz")

    # 5a ROLLUP_SSP — 三名 → 二名 → 种（回退）
    parts = canon.split()
    if len(parts) >= 3:
        code, _ = registry.exact_scientific(" ".join(parts[:2]))
        if code:
            return out("ROLLUP_SSP", code, 0.95, source="trinomial-strip")

    # 5b FUZZY_SCI — 属精确、模糊种加词
    fz = _fuzzy_sci(canon, registry, fuzzy_threshold)
    if fz:
        return out("FUZZY_SCI", fz[0], fz[1], source="fuzzy")

    # 6 CODE_ALIAS — 4 字母缩写码，唯一命中才认
    if " " not in canon:
        code, amb = registry.by_code_alias(canon)
        if code:
            return out("CODE_ALIAS", code, 0.70, source="code-alias")
        if amb:
            return out("ABSTAIN", None, 0.0, ambiguous=True)

    return out("ABSTAIN", None, 0.0)
