"""S5 gate: 网关薄壳（离线 FakeGateway + helpers；真机 LiteLLMGateway 需 key,CI 不跑）。"""

from birdbench.gateway import (
    FakeGateway,
    ModelResponse,
    build_router_model_list,
    image_part,
    register_price_overlay,
    text_part,
)
from birdbench.schemas import ModelSpec


def test_image_part_base64_data_url():
    part = image_part(b"\x89PNG\r\n", media_type="image/png")
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")


def test_text_part():
    assert text_part("hi") == {"type": "text", "text": "hi"}


async def test_fake_gateway_returns_canned():
    gw = FakeGateway(responses={"gpt-4o": '{"ok":1}'})
    spec = ModelSpec(alias="gpt-4o", model_id="openai/gpt-4o", provider="openai")
    r = await gw.complete([text_part("x")], spec)
    assert isinstance(r, ModelResponse)
    assert r.text == '{"ok":1}'
    assert r.cost_usd == 0.0
    assert r.model_resolved == "openai/gpt-4o"


async def test_fake_gateway_default():
    gw = FakeGateway(default="{}")
    r = await gw.complete([], ModelSpec(alias="x", model_id="p/x", provider="p"))
    assert r.text == "{}"


def test_build_router_model_list_maps_specs():
    specs = [
        ModelSpec(
            alias="doubao-pro",
            model_id="volcengine/doubao-seed-2-1-pro-260628",
            provider="volcengine",
        ),
        ModelSpec(
            alias="qwen-vl",
            model_id="dashscope/qwen3-vl-plus",
            provider="dashscope",
            params={"temperature": 0},
        ),
    ]
    ml = build_router_model_list(specs)
    assert ml[0]["model_name"] == "doubao-pro"
    assert ml[0]["litellm_params"]["model"] == "volcengine/doubao-seed-2-1-pro-260628"
    assert ml[1]["litellm_params"]["temperature"] == 0
    assert ml[1]["litellm_params"]["model"] == "dashscope/qwen3-vl-plus"


def test_register_price_overlay_is_safe():
    # litellm 缺席或价格表异常都不崩，返回 bool（离线=False，装了=True）
    ok = register_price_overlay(
        {"volcengine/doubao-x": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}}
    )
    assert ok in (True, False)
