"""S1 gate: 契约的验证 / 序列化 / 约束（Schema 铁律）。"""

import pytest
from pydantic import ValidationError

from birdbench.schemas import (
    Candidate,
    LeaderboardRow,
    ModelSpec,
    PredictionRecord,
    ResolutionOutcome,
    RunManifest,
    SpeciesPrediction,
)


def test_species_prediction_happy_path_and_roundtrip():
    p = SpeciesPrediction(
        predictions=[
            Candidate(
                common_name="Cooper's Hawk", scientific_name="Astur cooperii", confidence=0.8
            ),
            Candidate(common_name="Sharp-shinned Hawk", rank_hint="genus", confidence=0.5),
        ],
        overall_confidence=0.8,
    )
    dumped = p.model_dump()
    assert SpeciesPrediction.model_validate(dumped) == p
    assert p.predictions[1].rank_hint == "genus"
    assert p.abstain is False


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Candidate(common_name="X", confidence=1.5)
    with pytest.raises(ValidationError):
        Candidate(common_name="X", confidence=-0.1)


def test_invalid_rank_hint_rejected():
    with pytest.raises(ValidationError):
        Candidate(common_name="X", confidence=0.5, rank_hint="subspecies")


def test_abstain_prediction():
    p = SpeciesPrediction(abstain=True, abstain_reason="needs_audio")
    assert p.predictions == []
    with pytest.raises(ValidationError):
        SpeciesPrediction(abstain=True, abstain_reason="not_a_valid_reason")


def test_resolution_outcome_stage_enum():
    r = ResolutionOutcome(
        raw_text="Cooper's Hawk", stage_fired="EXACT_COM", matched_species_code="coohaw"
    )
    assert r.matched_species_code == "coohaw"
    with pytest.raises(ValidationError):
        ResolutionOutcome(raw_text="x", stage_fired="BOGUS")


def test_model_spec_alias_and_mode():
    m = ModelSpec(alias="gpt-4o", model_id="openai/gpt-4o", provider="openai")
    assert m.structured_mode == "JSON_SCHEMA"
    m2 = ModelSpec(
        alias="qwen3-vl",
        model_id="dashscope/qwen3-vl-plus",
        provider="dashscope",
        structured_mode="MD_JSON",
    )
    assert m2.provider == "dashscope"


def test_prediction_record_cost_may_be_none():
    rec = PredictionRecord(run_id="r1", model_alias="gpt-4o", item_id="i1", image_sha256="abc")
    assert rec.cost_usd is None  # 不可定价时 None，不是 0
    assert rec.prediction is None


def test_run_manifest_and_leaderboard_row():
    man = RunManifest(run_id="r1", dataset_id="evalset-v0", models=[
        ModelSpec(alias="gpt-4o", model_id="openai/gpt-4o", provider="openai"),
    ])
    assert man.models[0].alias == "gpt-4o"
    row = LeaderboardRow(model_alias="gpt-4o", n=30)
    assert row.cost_per_item_usd is None
