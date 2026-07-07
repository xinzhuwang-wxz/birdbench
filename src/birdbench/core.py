"""core.predict：图 → SpeciesPrediction（唯一模型 I/O）。见 DESIGN §5.1/5.4/5.6。

prompt 俗名优先·answer-first·无 CoT 默认·top-k·JSON 输出。gateway 返回原文 → 容错解析成 schema。
默认 prompt 内置（V0）；S12 把它外置成 prompts/ 可编辑文件。模型调用只在此文件出现。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass

from birdbench.gateway import Gateway, ModelResponse, image_part, text_part
from birdbench.schemas import ModelSpec, PromptSpec, SpeciesPrediction

_DEFAULT_SYSTEM = (
    "You are an expert ornithologist. Identify the bird in the image and give your best "
    "guesses as a ranked list. Prefer the English COMMON name (scientific name optional). "
    "If unsure of the exact species, hedge to genus/family/order via rank_hint. "
    "Answer directly, without step-by-step reasoning."
)
_DEFAULT_USER = (
    "Identify the bird. Respond ONLY with JSON of this shape:\n"
    '{"predictions":[{"common_name":str,"scientific_name":str|null,'
    '"rank_hint":"species|genus|family|order","confidence":0-1,"field_marks":str|null}],'
    '"abstain":false,"abstain_reason":null,"overall_confidence":0-1}\n'
    "Give up to 5 ranked predictions (most likely first). "
    "If it is not a bird or is unidentifiable, set abstain=true."
)


def default_prompt() -> PromptSpec:
    """V0 默认 prompt：优先读 prompts/species_id.v0.md（同事可编辑）；无文件则内置兜底。"""
    from birdbench.prompts import load_prompt

    loaded = load_prompt("species_id", "v0")
    if loaded is not None:
        return loaded
    body = _DEFAULT_SYSTEM + "\n" + _DEFAULT_USER
    return PromptSpec(
        name="species_id",
        version="v0",
        content_hash=hashlib.sha256(body.encode()).hexdigest()[:12],
        system=_DEFAULT_SYSTEM,
        user_template=_DEFAULT_USER,
        params={"top_k": 5, "cot": False, "ask_scientific": True},
    )


def _json_candidates(text: str) -> Iterator[str]:
    yield text  # 1) 整体（干净 JSON）
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)  # 2) markdown 围栏内
    if m:
        yield m.group(1)
    start, end = text.find("{"), text.rfind("}")  # 3) 首 { 到末 }
    if start != -1 and end > start:
        yield text[start : end + 1]


def parse_prediction(text: str) -> SpeciesPrediction | None:
    """容错解析：整体→围栏→花括号 逐一试校验。失败→None（安全，绝不误判）。"""
    if not text:
        return None
    for candidate in _json_candidates(text):
        try:
            return SpeciesPrediction.model_validate(json.loads(candidate))
        except Exception:
            continue
    return None


def build_messages(
    image: bytes, prompt: PromptSpec, *, media_type: str = "image/jpeg"
) -> list[dict]:
    return [
        {"role": "system", "content": prompt.system},  # Doubao 要求 system 为纯字符串
        {
            "role": "user",
            "content": [text_part(prompt.user_template), image_part(image, media_type)],
        },
    ]


@dataclass
class PredictOutcome:
    prediction: SpeciesPrediction | None  # None => 结构化解码失败
    raw_output: str
    schema_valid: bool
    response: ModelResponse  # cost/usage/latency/model_resolved/error


async def predict(
    image: bytes,
    model: ModelSpec,
    prompt: PromptSpec | None = None,
    *,
    gateway: Gateway,
    media_type: str = "image/jpeg",
) -> PredictOutcome:
    """图 + 模型 + prompt → PredictOutcome（结构化预测 + 调用元数据）。"""
    p = prompt or default_prompt()
    resp = await gateway.complete(build_messages(image, p, media_type=media_type), model)
    pred = parse_prediction(resp.text)
    return PredictOutcome(
        prediction=pred, raw_output=resp.text, schema_valid=pred is not None, response=resp
    )
