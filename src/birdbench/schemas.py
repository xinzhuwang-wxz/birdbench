"""birdbench 契约（Schema 铁律：所有模型输出 / 评测记录进 Pydantic）。见 docs/DESIGN.md §5。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- 枚举（受控词表）--------------------------------------------------------
RankHint = Literal["species", "genus", "family", "order"]
AbstainReason = Literal[
    "image_quality",
    "occlusion_angle",
    "needs_audio",
    "multiple_individuals",
    "out_of_expertise",
    "not_a_bird",
]
ResolutionStage = Literal[
    "NORMALIZE",
    "EXACT_CODE",
    "EXACT_SCI",
    "EXACT_COM",
    "SYNONYM",
    "ROLLUP_SSP",
    "FUZZY_SCI",
    "EXTERNAL",
    "ABSTAIN",
]
StructuredMode = Literal["TOOLS", "JSON_SCHEMA", "JSON_OBJECT", "MD_JSON"]


# --- VLM 输出（模型产出的结构化契约）---------------------------------------
class Candidate(BaseModel):
    """VLM 的一个候选猜测（top-k 之一）。允许 hedge 到属/科/目（rank_hint）。"""

    common_name: str
    scientific_name: str | None = None
    rank_hint: RankHint = "species"
    confidence: float = Field(ge=0.0, le=1.0)
    field_marks: str | None = None


class SpeciesPrediction(BaseModel):
    """VLM 结构化输出。abstain 通道与"猜错"分开（选择性分类）。"""

    predictions: list[Candidate] = Field(default_factory=list)
    abstain: bool = False
    abstain_reason: AbstainReason | None = None
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# --- 解析记账（区分模型账 vs 解析器账，见 DESIGN §5.3 四桶）----------------
class ResolutionOutcome(BaseModel):
    """一次 名字→speciesCode 解析的确定性结局。"""

    raw_text: str
    parsed_canonical: str | None = None
    stage_fired: ResolutionStage
    matched_species_code: str | None = None
    match_type: ResolutionStage | None = None
    score: float = 1.0
    source: str | None = None
    candidates_considered: list[str] = Field(default_factory=list)
    gold_species_code: str | None = None


# --- 模型条目 / 用量 --------------------------------------------------------
class ModelSpec(BaseModel):
    """一个模型条目（一家可有多条，共享 key）。alias = 选择 / 排行键。"""

    alias: str
    model_id: str  # litellm id, e.g. "openai/gpt-4o"
    provider: str
    params: dict = Field(default_factory=dict)
    structured_mode: StructuredMode = "JSON_SCHEMA"
    prompt_version: str = "v0"
    prompt_hash: str = ""


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0


# --- 评测产物 ---------------------------------------------------------------
class PredictionRecord(BaseModel):
    """评测台一行 = 一个 (item × model)。predictions.jsonl 每行一条。"""

    run_id: str
    model_alias: str
    item_id: str
    image_sha256: str
    expected: dict = Field(default_factory=dict)  # gold {species_code, ...}
    raw_output: str = ""
    prediction: SpeciesPrediction | None = None  # None => 结构化输出失败
    schema_valid: bool = False
    resolution: ResolutionOutcome | None = None
    scores: dict = Field(default_factory=dict)
    latency_ms: float = 0.0
    usage: Usage = Field(default_factory=Usage)
    cost_usd: float | None = None  # None => 不可定价（价格表缺）
    cache_hit: bool = False
    attempt: int = 1
    error: str | None = None
    ts: datetime | None = None


class RunManifest(BaseModel):
    """一次评测运行的可复现头（run 级）。"""

    run_id: str
    created_at: datetime | None = None
    git_sha: str = ""
    harness_version: str = "0.0.0"
    scorer_version: str = "0.0.0"
    dataset_id: str
    dataset_version: str = ""
    dataset_sha256: str = ""
    n_items: int = 0
    models: list[ModelSpec] = Field(default_factory=list)


class LeaderboardRow(BaseModel):
    """榜的一行（按 model alias）。"""

    model_alias: str
    n: int
    rank: int = 0
    top1_species_acc: float = 0.0
    top5_species_acc: float = 0.0
    genus_acc: float = 0.0
    family_acc: float = 0.0
    order_acc: float = 0.0
    lca_score: float = 0.0
    resolver_conditional_acc: float = 0.0
    end_to_end_acc: float = 0.0
    abstain_rate: float = 0.0
    parse_fail_rate: float = 0.0
    schema_valid_rate: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    cost_per_item_usd: float | None = None
    cost_per_correct_usd: float | None = None
    total_tokens: int = 0
