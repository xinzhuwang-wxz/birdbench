"""名字→speciesCode 确定性解析阶梯（first-hit-wins, LLM 不进路径）。见 DESIGN §5.2。

阶(V0)：NORMALIZE → EXACT_CODE(仅 speciesCode) → EXACT_SCI → EXACT_COM
→ ZH_ALIAS(gz) → SYNONYM(gz) → ROLLUP_SSP(三名→二名)
→ FUZZY_SCI(JaroWinkler,属精确,margin,edit) → CODE_ALIAS(4字母,唯一) → ABSTAIN。
rollup 后处理内建在 registry。stage-0 轻量归一化(gnparser 可后续硬化)。
gazetteer(同义/中文)集合值(多义→弃答)，默认空由 S4 填——本片不阻塞于 S4。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from birdbench.registry import Registry, normalize
from birdbench.schemas import ResolutionOutcome

# 归一化器：凌乱文本 → 干净单一种名 | None（extractor 非 judge）。见 llm_normalize。
NormalizerFn = Callable[[str], Awaitable[str | None]]

try:
    from rapidfuzz.distance import JaroWinkler, Levenshtein

    _HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover
    _HAS_RAPIDFUZZ = False

_SP_RE = re.compile(r"\bsp\b")
_PAREN_RE = re.compile(r"\([^)]*\)")
# 描述性修饰词（V1-1）：模型常给 base 名附这些，打断精确匹配。剥掉回退 base 名。
_MODIFIER_WORDS = frozenset({
    "albino", "leucistic", "melanistic", "xanthochroic", "xanthochromic", "domestic",
    "feral", "juvenile", "nestling", "immature", "subadult", "adult", "male", "female",
    "morph", "variant", "individual", "breed", "form", "eclipse", "nonbreeding",
    "breeding", "molting", "worn", "fledgling", "chick",
})


def _base_names(text: str) -> list[str]:
    """从原文剥描述性修饰，产出 base 名候选（去括号 / 去修饰词），供回退精确匹配。"""
    original = _canon(text)
    out, seen = [], {original}
    for variant in (_PAREN_RE.sub(" ", text), text):  # 先试去括号
        c = _canon(variant)
        stripped = " ".join(t for t in c.split() if t not in _MODIFIER_WORDS)
        for cand in (c, stripped):
            if cand and cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out


@dataclass
class Gazetteer:
    """S4 离线 build 填：同义名 + 中文名 → 种码**集合**（多义→弃答，与 registry 一致）。默认空。"""

    synonym: dict[str, set[str]] = field(default_factory=dict)  # norm(学名/俗名) → {speciesCode}
    zh: dict[str, set[str]] = field(default_factory=dict)  # norm(中文名) → {speciesCode}


def _canon(text: str) -> str:
    c = _SP_RE.sub(" ", normalize(text))  # 去 "sp."/"sp"
    return re.sub(r"\s+", " ", c).strip()


def _unique_species(reg: Registry, codes: set[str]) -> tuple[str | None, bool]:
    """把候选码收敛到种；唯一→(种码, False)，多义→(None, True)。"""
    species = {reg.resolve_to_species(c) for c in codes}
    if len(species) == 1:
        return next(iter(species)), False
    return None, True


def _fuzzy_sci(
    canon: str, reg: Registry, jw_min: float, margin: float, max_edit: int
) -> tuple[str, float] | None:
    """属精确 + JaroWinkler≥jw_min + 次候选 margin + 编辑距离≤max_edit（DESIGN §5.2 阶 5）。"""
    if not _HAS_RAPIDFUZZ or " " not in canon:
        return None
    genus = canon.split()[0]
    scored: list[tuple[float, str, str]] = []
    for name, codes in reg._sci.items():
        if name.split()[0] != genus:  # 属必须精确
            continue
        code, _ = _unique_species(reg, codes)
        if code is None:  # 该名多义 → 不做 fuzzy 目标
            continue
        scored.append((JaroWinkler.similarity(canon, name), name, code))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    best_jw, best_name, best_code = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_jw < jw_min or best_jw - second < margin:  # 阈值 + margin 防近似种误配
        return None
    if Levenshtein.distance(canon, best_name) > max_edit:  # 编辑距离守卫
        return None
    return best_code, min(0.90, max(0.80, best_jw))  # 置信 clamp 到 spec 区间


def resolve(
    text: str,
    registry: Registry,
    gazetteer: Gazetteer | None = None,
    *,
    jw_min: float = 0.92,
    fuzzy_margin: float = 0.05,
    max_edit: int = 2,
) -> ResolutionOutcome:
    """自由文本鸟名 → ResolutionOutcome（命中阶、种码、置信、ambiguous）。"""
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

    if not canon:  # 空/乱码
        return out("NORMALIZE", None, 0.0)

    # 1 EXACT_CODE — 仅 speciesCode（非 4 字母码）；issf 细码经 rollup
    if canon in registry.species:
        return out("EXACT_CODE", canon, 1.0, source="code")
    if canon in registry.rollup:
        return out("EXACT_CODE", registry.resolve_to_species(canon), 1.0, source="code+rollup")

    # 2 EXACT_SCI / 3 EXACT_COM —— 传原文；exact_* 内部归一化，_canon 的去 "sp." 仅供后续阶
    for stage, fn, score in (
        ("EXACT_SCI", registry.exact_scientific, 1.0),
        ("EXACT_COM", registry.exact_common, 0.99),
    ):
        code, amb = fn(text)
        if code:
            return out(stage, code, score, source=stage.split("_")[1].lower())
        if amb:
            return out("ABSTAIN", None, 0.0, ambiguous=True)

    # 3z ZH_ALIAS / 4 SYNONYM —— gazetteer 集合值，多义→弃答
    for stage, mp, score in (("ZH_ALIAS", gz.zh, 0.98), ("SYNONYM", gz.synonym, 0.97)):
        codes = mp.get(canon)
        if codes:
            code, amb = _unique_species(registry, codes)
            if code:
                return out(stage, code, score, source=stage.lower())
            if amb:
                return out("ABSTAIN", None, 0.0, ambiguous=True)

    # 4b MODIFIER_STRIP — 剥描述性修饰(括号/morph/albino…)回退 base 名（V1-1，恢复被冤枉的对答案）
    for base in _base_names(text):
        code, amb = registry.exact_common(base)
        if not code and not amb:
            code, amb = registry.exact_scientific(base)
        if code:
            return out("MODIFIER_STRIP", code, 0.9, source="modifier-strip")
        if amb:
            return out("ABSTAIN", None, 0.0, ambiguous=True)

    # 5a ROLLUP_SSP — 三名 → 二名 → 种
    parts = canon.split()
    if len(parts) >= 3:
        code, amb = registry.exact_scientific(" ".join(parts[:2]))
        if code:
            return out("ROLLUP_SSP", code, 0.95, source="trinomial-strip")
        if amb:
            return out("ABSTAIN", None, 0.0, ambiguous=True)

    # 5b FUZZY_SCI — 属精确、模糊种加词、margin/edit 守卫
    fz = _fuzzy_sci(canon, registry, jw_min, fuzzy_margin, max_edit)
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


_LADDER = [
    "EXACT_CODE", "EXACT_SCI", "EXACT_COM", "ZH_ALIAS", "SYNONYM",
    "MODIFIER_STRIP", "ROLLUP_SSP", "FUZZY_SCI", "CODE_ALIAS", "LLM_NORMALIZE", "ABSTAIN",
]


def trace_resolve(
    text: str, registry: Registry, gazetteer: Gazetteer | None = None
) -> tuple[list[dict], ResolutionOutcome]:
    """解析梯子逐阶 trace（供 UI 透明展示）。以 resolve() 的 stage_fired 为权威，不重实现逻辑。

    返回 (steps, outcome)。steps 每项 {stage, detail, result}：命中阶给出种码，之前的阶标未命中。
    """
    outcome = resolve(text, registry, gazetteer)
    canon = _canon(text)
    fired = outcome.stage_fired
    steps: list[dict] = [{"stage": "NORMALIZE", "detail": f"{text!r} → 去符号/小写/去 sp.",
                          "result": canon or "(空)"}]
    bases = _base_names(text)
    for st in _LADDER:
        if st == "MODIFIER_STRIP" and st == fired:
            hit_base = next((b for b in bases if registry.exact_common(b)[0]
                             or registry.exact_scientific(b)[0]), canon)
            steps.append({"stage": st, "detail": f"剥修饰 → {hit_base!r}",
                          "result": outcome.matched_species_code})
            break
        if st == fired:
            code = outcome.matched_species_code
            steps.append({"stage": st, "detail": "命中" if code else "拿不准 → 弃答，绝不瞎猜",
                          "result": code or "弃答"})
            break
        detail = "剥括号/修饰词后精确匹配" if st == "MODIFIER_STRIP" else "未命中"
        steps.append({"stage": st, "detail": detail, "result": None})
    return steps, outcome


async def resolve_with_normalizer(
    text: str,
    registry: Registry,
    gazetteer: Gazetteer | None = None,
    *,
    normalizer: NormalizerFn | None = None,
    **kw,
) -> ResolutionOutcome:
    """确定性 resolve 先行；仅纯 miss(无码非多义)才调 LLM 归一化尾巴（省钱·extractor 非 judge）。

    LLM 只把凌乱文本擦成干净种名 → 再走同一确定性 exact 解析定码；对错判定仍确定性(code==gold)。
    归一化后仍走 resolve，故绝不让 LLM 直接产 code / 判对错，只提取名字。
    """
    det = resolve(text, registry, gazetteer, **kw)
    if normalizer is None or det.matched_species_code or det.ambiguous:
        return det
    cleaned = await normalizer(text)
    if not cleaned or normalize(cleaned) == normalize(text):
        return det  # LLM 说 NONE 或没改动 → 保留确定性结果（不虚高）
    r2 = resolve(cleaned, registry, gazetteer, **kw)
    if r2.matched_species_code:
        return ResolutionOutcome(
            raw_text=text,
            parsed_canonical=cleaned,
            stage_fired="LLM_NORMALIZE",
            matched_species_code=r2.matched_species_code,
            score=min(r2.score, 0.9),
            ambiguous=False,
            source="llm-normalize",
        )
    return det  # LLM 擦过也解析不出 → 保留原确定性结果
