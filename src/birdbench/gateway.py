"""模型访问层：LiteLLM Router 薄壳 + 图片 helper + 价格 overlay。见 DESIGN §5.4。

顶层不 import litellm（懒加载）→ 离线用 FakeGateway 可测；真机 LiteLLMGateway 走 Router。
真实约束：图片一律 base64 data URL；Doubao 要求 ≥14px；无内置价模型 cost=None→价格 overlay。
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Protocol

from birdbench.schemas import ModelSpec, Usage


# --- 图片 / 文本内容块（base64 data URL 跨全家唯一通用；Kimi 强制不支持远程 URL）---
def image_part(data: bytes, media_type: str = "image/jpeg") -> dict:
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


@dataclass
class ModelResponse:
    """一次模型调用的结构化结果。cost_usd=None 表示不可定价（价格表缺）。"""

    text: str
    usage: Usage = field(default_factory=Usage)
    cost_usd: float | None = None
    latency_ms: float = 0.0
    model_resolved: str = ""  # API 实际返回的模型版本（钉快照，alias 会漂移）
    error: str | None = None


class Gateway(Protocol):
    async def complete(self, messages: list[dict], spec: ModelSpec) -> ModelResponse: ...


class FakeGateway:
    """离线 fake：按 model alias 返回预置文本，不碰网络。测试 + 降级用。"""

    def __init__(self, responses: dict | None = None, default: str = "{}") -> None:
        self._responses = responses or {}  # value: str 或 list（list 循环取,模拟采样）
        self._default = default
        self._calls: dict[str, int] = {}

    async def complete(self, messages: list[dict], spec: ModelSpec) -> ModelResponse:
        v = self._responses.get(spec.alias, self._default)
        if isinstance(v, list):
            i = self._calls.get(spec.alias, 0)
            self._calls[spec.alias] = i + 1
            text = v[i % len(v)] if v else self._default
        else:
            text = v
        return ModelResponse(
            text=text,
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            cost_usd=0.0,
            latency_ms=1.0,
            model_resolved=spec.model_id,
        )


def build_router_model_list(specs: list[ModelSpec]) -> list[dict]:
    """ModelSpec[] → litellm Router 的 model_list（一条=一个 deployment）。"""
    out = []
    for s in specs:
        params = {"model": s.model_id, **s.params}
        out.append({"model_name": s.alias, "litellm_params": params})
    return out


def register_price_overlay(overlay: dict) -> bool:
    """把自维护价格表灌进 litellm（无内置价模型否则 cost=None）。返回是否成功。"""
    try:
        import litellm

        litellm.register_model(overlay)
        return True
    except Exception:  # litellm 缺席或价格表异常 → 降级 cost=None（非阻塞铁律）
        return False


def _extract_usage(u: object) -> Usage:
    def g(name: str) -> int:
        return int(getattr(u, name, 0) or 0)

    details = getattr(u, "completion_tokens_details", None)
    reasoning = int(getattr(details, "reasoning_tokens", 0) or 0) if details else 0
    return Usage(
        prompt_tokens=g("prompt_tokens"),
        completion_tokens=g("completion_tokens"),
        total_tokens=g("total_tokens"),
        reasoning_tokens=reasoning,
    )


class LiteLLMGateway:
    """真机：litellm.Router（限流/failover）+ 成本/用量/延迟/快照。CI 不跑（需 key）。"""

    def __init__(
        self,
        specs: list[ModelSpec],
        *,
        price_overlay: dict | None = None,
        num_retries: int = 3,
        timeout: float = 60.0,
    ) -> None:
        import litellm
        from litellm import Router

        if price_overlay:
            litellm.register_model(price_overlay)
        self._router = Router(
            model_list=build_router_model_list(specs), num_retries=num_retries, timeout=timeout
        )

    async def complete(self, messages: list[dict], spec: ModelSpec) -> ModelResponse:
        import litellm

        t0 = time.monotonic()
        try:
            resp = await self._router.acompletion(model=spec.alias, messages=messages)
        except Exception as e:  # 优雅降级：单 cell error，不崩整轮（DESIGN §5.4）
            return ModelResponse(
                text="", cost_usd=None, latency_ms=(time.monotonic() - t0) * 1000.0,
                model_resolved=spec.model_id, error=str(e),
            )
        latency = (time.monotonic() - t0) * 1000.0
        text = resp.choices[0].message.content or ""
        try:
            cost = litellm.completion_cost(resp)
        except Exception:
            cost = None  # 无内置价 → None（非 0）
        return ModelResponse(
            text=text,
            usage=_extract_usage(resp.usage),
            cost_usd=cost,
            latency_ms=latency,
            model_resolved=getattr(resp, "model", "") or spec.model_id,
        )
