"""S6 gate: core.predict（离线 FakeGateway；模型 I/O 唯一入口）。"""

from birdbench.core import (
    PredictOutcome,
    build_messages,
    default_prompt,
    parse_prediction,
    predict,
)
from birdbench.gateway import FakeGateway
from birdbench.schemas import ModelSpec, SpeciesPrediction

_VALID = (
    '{"predictions":[{"common_name":"Cooper\'s Hawk","scientific_name":"Astur cooperii",'
    '"rank_hint":"species","confidence":0.8,"field_marks":"long tail"}],'
    '"abstain":false,"overall_confidence":0.8}'
)
_SPEC = ModelSpec(alias="m", model_id="p/m", provider="p")


def test_default_prompt():
    p = default_prompt()
    assert p.version == "v0" and p.content_hash
    assert "COMMON name" in p.system and "JSON" in p.user_template
    assert p.params["cot"] is False and p.params["top_k"] == 5


def test_parse_prediction_valid():
    p = parse_prediction(_VALID)
    assert isinstance(p, SpeciesPrediction)
    assert p.predictions[0].common_name == "Cooper's Hawk"


def test_parse_prediction_markdown_fenced_and_prose():
    p = parse_prediction("Sure! Here you go:\n```json\n" + _VALID + "\n```")
    assert isinstance(p, SpeciesPrediction) and p.overall_confidence == 0.8


def test_parse_prediction_abstain():
    p = parse_prediction('{"predictions":[],"abstain":true,"abstain_reason":"not_a_bird"}')
    assert p.abstain is True and p.abstain_reason == "not_a_bird"


def test_parse_prediction_garbage_returns_none():
    assert parse_prediction("I cannot help with that.") is None
    assert parse_prediction("") is None
    # 越界 confidence → 校验失败 → None
    assert parse_prediction('{"predictions":[{"common_name":"X","confidence":9}]}') is None


def test_build_messages_system_string_and_image():
    msgs = build_messages(b"\x89PNG", default_prompt())
    assert msgs[0]["role"] == "system" and isinstance(msgs[0]["content"], str)
    parts = msgs[1]["content"]
    assert parts[0]["type"] == "text"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_predict_valid_json():
    gw = FakeGateway(responses={"m": _VALID})
    out = await predict(b"img", _SPEC, gateway=gw)
    assert isinstance(out, PredictOutcome)
    assert out.schema_valid is True
    assert out.prediction.predictions[0].scientific_name == "Astur cooperii"
    assert out.response.model_resolved == "p/m"


async def test_predict_garbage_schema_invalid():
    gw = FakeGateway(responses={"m": "no json here"})
    out = await predict(b"img", _SPEC, gateway=gw)
    assert out.schema_valid is False and out.prediction is None
    assert out.raw_output == "no json here"
