"""LLM 名字归一化（V1-8）：轻量文字模型把凌乱输出提取成单一干净种名（extractor 非 judge）。见 §5.2。

只提取文本**明确陈述**的种名（或 None，不猜）；temp 0 + 进程内缓存（可复现）。注入
`resolve.resolve_with_normalizer` 的尾巴：确定性解析不了时才调，省钱。对错判定仍确定性(code==gold)——
LLM 绝不产 code / 判对错，只擦名字，故不会有 LLM-as-judge 的自我偏袒虚高。
"""

from __future__ import annotations

from birdbench.gateway import Gateway
from birdbench.resolve import NormalizerFn
from birdbench.schemas import ModelSpec

_SYS = (
    "You normalize a messy bird-species answer into ONE clean name. "
    "Output ONLY the single species common name (English) or scientific name the text asserts, "
    "with color/age/sex/morph modifiers, parentheticals, and 'sp.' removed. "
    "If the text does not clearly assert one single species, output exactly: NONE. "
    "Never guess, infer, or add a species that is not stated. "
    "Output the bare name on one line — no punctuation, quotes, or explanation."
)


def make_normalizer(
    gateway: Gateway, model: ModelSpec, *, cache: dict[str, str | None] | None = None
) -> NormalizerFn:
    """构造异步归一化器：text → 干净种名 | None。temp 0 由 model.params 带；进程内缓存保可复现。"""
    store: dict[str, str | None] = {} if cache is None else cache

    async def _normalize(text: str) -> str | None:
        key = (text or "").strip()
        if not key:
            return None
        if key in store:
            return store[key]
        messages = [{"role": "system", "content": _SYS}, {"role": "user", "content": key}]
        resp = await gateway.complete(messages, model)
        raw = (resp.text or "").strip()
        first = raw.splitlines()[0].strip() if raw else ""
        result = None if (not first or first.upper() == "NONE") else first
        store[key] = result
        return result

    return _normalize
