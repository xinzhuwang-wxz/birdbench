"""S1 gate: 契约的验证 / 序列化 / 约束（Schema 铁律）。含审查后调整。"""

import pytest
from pydantic import ValidationError

from birdbench.schemas import (
    Candidate,
    GoldLabel,
    HumanReview,
    LeaderboardRow,
    ModelSpec,
    PredictionRecord,
    PromptSpec,
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
    assert SpeciesPrediction.model_validate(p.model_dump()) == p
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


def test_prompt_spec():
    ps = PromptSpec(name="species_id", version="v0", content_hash="deadbeef")
    assert ps.version == "v0"
    assert ps.params == {}


def test_gold_label_typed():
    g = GoldLabel(species_code="coohaw", genus="Astur", family="Accipitridae")
    assert g.species_code == "coohaw"
    with pytest.raises(ValidationError):
        GoldLabel()  # species_code required


def test_resolution_outcome_stage_and_bucket():
    r = ResolutionOutcome(
        raw_text="Cooper's Hawk",
        stage_fired="EXACT_COM",
        matched_species_code="coohaw",
        resolution_bucket="A",
    )
    assert r.matched_species_code == "coohaw"
    assert r.ambiguous is False
    with pytest.raises(ValidationError):
        ResolutionOutcome(raw_text="x", stage_fired="BOGUS")
    with pytest.raises(ValidationError):
        ResolutionOutcome(raw_text="x", stage_fired="ABSTAIN", resolution_bucket="Z")


def test_model_spec_no_prompt_fields_and_capabilities():
    m = ModelSpec(alias="gpt-4o", model_id="openai/gpt-4o", provider="openai")
    assert m.structured_mode == "JSON_SCHEMA"
    assert m.supports_vision is True
    # prompt 轴已从 ModelSpec 移除
    assert not hasattr(m, "prompt_version")


def test_prediction_record_prompt_axis_and_gold():
    rec = PredictionRecord(
        run_id="r1",
        item_id="i1",
        model_alias="gpt-4o",
        prompt_version="v1",
        image_sha256="abc",
        gold=GoldLabel(species_code="coohaw"),
        cell_id="cell-hash",
        sample_idx=2,
    )
    assert rec.cost_usd is None  # 不可定价时 None，不是 0
    assert rec.prediction is None
    assert rec.prompt_version == "v1"
    assert rec.gold.species_code == "coohaw"
    assert rec.model_resolved == ""


def test_human_review_hook():
    hr = HumanReview(verdict="model_actually_right", corrected_species_code="coohaw")
    rec = PredictionRecord(
        run_id="r1", item_id="i1", model_alias="m", image_sha256="x", human_review=hr
    )
    assert rec.human_review.verdict == "model_actually_right"
    with pytest.raises(ValidationError):
        HumanReview(verdict="bogus")


def test_run_manifest_carries_models_and_prompts():
    man = RunManifest(
        run_id="r1",
        dataset_id="evalset-v0",
        models=[ModelSpec(alias="gpt-4o", model_id="openai/gpt-4o", provider="openai")],
        prompts=[PromptSpec(name="species_id", version="v0")],
    )
    assert man.models[0].alias == "gpt-4o"
    assert man.prompts[0].version == "v0"
    assert man.geo_mode == "blind"


def test_leaderboard_row_has_prompt_axis_and_top3():
    row = LeaderboardRow(model_alias="gpt-4o", prompt_version="v0", n=30)
    assert row.top3_species_acc == 0.0
    assert row.cost_per_item_usd is None
