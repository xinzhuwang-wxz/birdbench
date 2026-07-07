"""S13 gate: 单图 identify（离线 FakeGateway）。"""

import json

from birdbench.core import identify
from birdbench.gateway import FakeGateway
from birdbench.registry import load_registry
from birdbench.schemas import IdentifyResult, ModelSpec

REG = load_registry()
_SPEC = ModelSpec(alias="m", model_id="fake/m", provider="fake")


async def test_identify_top1_taxonomy_and_candidates():
    payload = json.dumps(
        {
            "predictions": [
                {"common_name": "Cooper's Hawk", "confidence": 0.8, "field_marks": "long tail"},
                {"common_name": "Sharp-shinned Hawk", "rank_hint": "genus", "confidence": 0.4},
            ],
            "abstain": False,
        }
    )
    res = await identify(b"img", _SPEC, gateway=FakeGateway(responses={"m": payload}), registry=REG)
    assert isinstance(res, IdentifyResult)
    assert res.species_code == "coohaw"
    assert res.family == "Accipitridae" and res.genus == "Astur"
    assert res.resolution_stage == "EXACT_COM"
    assert res.field_marks == "long tail"
    assert len(res.candidates) == 2 and res.candidates[0].species_code == "coohaw"
    assert res.cost_usd == 0.0 and res.model_resolved == "fake/m"


async def test_identify_abstain():
    payload = json.dumps({"predictions": [], "abstain": True, "abstain_reason": "not_a_bird"})
    res = await identify(b"img", _SPEC, gateway=FakeGateway(responses={"m": payload}), registry=REG)
    assert res.abstain is True and res.abstain_reason == "not_a_bird"
    assert res.species_code is None


async def test_identify_schema_fail():
    gw = FakeGateway(responses={"m": "sorry no"})
    res = await identify(b"img", _SPEC, gateway=gw, registry=REG)
    assert res.schema_valid is False and res.species_code is None
