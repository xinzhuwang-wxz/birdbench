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
# 解析阶梯的阶（见 DESIGN §5.2）。CODE_ALIAS = 4 字母缩写码（唯一命中才认）；ZH_ALIAS = 中文名。
ResolutionStage = Literal[
    "NORMALIZE",
    "EXACT_CODE",
    "EXACT_SCI",
    "EXACT_COM",
    "ZH_ALIAS",
    "SYNONYM",
    "MODIFIER_STRIP",
    "ROLLUP_SSP",
    "CODE_ALIAS",
    "FUZZY_SCI",
    "EXTERNAL",
    "ABSTAIN",
]
# 四桶分离（DESIGN §5.3）：A 解析对 / B 认错种(模型账) / C1 解析器覆盖漏洞 / C2 模型幻觉 / D 弃答。
ResolutionBucket = Literal["A", "B", "C1", "C2", "D"]
StructuredMode = Literal["TOOLS", "JSON_SCHEMA", "JSON_OBJECT", "MD_JSON"]
GeoMode = Literal["blind", "aware"]
HumanVerdict = Literal["confirm", "model_actually_right", "gold_wrong", "good_hard_case"]


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


# --- prompt（一等评测轴，DESIGN §5.6）--------------------------------------
class PromptSpec(BaseModel):
    """外部可编辑、版本化的 prompt。content_hash 用于复现 + 缓存键。"""

    name: str
    version: str
    content_hash: str = ""
    system: str = ""
    user_template: str = ""
    params: dict = Field(default_factory=dict)  # top_k / ask_scientific / cot / few_shot / geo


# --- 真值标签（typed，非裸 dict）-------------------------------------------
class GoldLabel(BaseModel):
    species_code: str
    genus: str = ""
    family: str = ""
    order: str = ""


# --- 解析记账（区分模型账 vs 解析器账，DESIGN §5.3 四桶）-------------------
class ResolutionOutcome(BaseModel):
    """一次 名字→speciesCode 解析的确定性结局。"""

    raw_text: str
    parsed_canonical: str | None = None
    stage_fired: ResolutionStage  # 哪一阶命中
    matched_species_code: str | None = None
    resolution_bucket: ResolutionBucket | None = None  # 相对 gold 的四桶归因（打分时填）
    score: float = 1.0  # 解析置信度（阶越靠后越低）
    source: str | None = None
    candidates_considered: list[str] = Field(default_factory=list)
    ambiguous: bool = False  # 归一化名映射到 >1 种码 → 弃答
    gold_species_code: str | None = None


# --- 模型条目 / 用量 --------------------------------------------------------
class ModelSpec(BaseModel):
    """一个模型条目（一家可有多条，共享 key）。alias = 选择 / 排行键。prompt 不在此（正交轴）。"""

    alias: str
    model_id: str  # litellm id, e.g. "openai/gpt-4o"
    provider: str
    params: dict = Field(default_factory=dict)
    structured_mode: StructuredMode = "JSON_SCHEMA"
    supports_vision: bool = True  # 能力声明；不支持则 runner 优雅跳过
    supports_json_schema: bool = True


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0


class HumanReview(BaseModel):
    """数据飞轮 hook：同事在结果表上的人审/纠错，未来喂回评测集。"""

    verdict: HumanVerdict | None = None
    corrected_species_code: str | None = None
    note: str = ""
    reviewer: str = ""


# --- 评测产物 ---------------------------------------------------------------
class PredictionRecord(BaseModel):
    """评测台一行 = 一个实验单元 cell (item × model × prompt × sample)。predictions.jsonl 每行。"""

    run_id: str
    cell_id: str = ""  # 维度内容哈希 = 缓存键（DESIGN §5.5/§5.7）
    item_id: str
    model_alias: str
    prompt_version: str = "v0"  # prompt 轴（DESIGN §5.6）
    prompt_hash: str = ""
    sample_idx: int = 0  # 自洽采样维度（DESIGN §5.7 N3）
    image_sha256: str
    gold: GoldLabel | None = None
    raw_output: str = ""
    prediction: SpeciesPrediction | None = None  # None => 结构化输出失败
    schema_valid: bool = False
    resolution: ResolutionOutcome | None = None
    scores: dict = Field(default_factory=dict)
    latency_ms: float = 0.0
    usage: Usage = Field(default_factory=Usage)
    cost_usd: float | None = None  # None => 不可定价（价格表缺）
    model_resolved: str = ""  # API 实际返回的模型版本（钉快照，DESIGN §5.7 N5）
    cache_hit: bool = False
    attempt: int = 1
    error: str | None = None
    human_review: HumanReview | None = None
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
    prompts: list[PromptSpec] = Field(default_factory=list)  # prompt 也是评测轴
    geo_mode: GeoMode = "blind"  # v0 默认盲测（DESIGN §6）


class LeaderboardRow(BaseModel):
    """榜的一行（某个 groupby 视图，通常按 (model_alias, prompt_version)）。"""

    model_alias: str
    prompt_version: str = "v0"
    n: int = 0
    rank: int = 0
    top1_species_acc: float = 0.0
    top1_ci_low: float = 0.0  # Clopper-Pearson 95% CI（V1-2）
    top1_ci_high: float = 0.0
    tied_with_best: bool = False  # 与最优模型无显著差异（Holm 校正后）
    top3_species_acc: float = 0.0
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


# --- 产品端单图 identify（DESIGN §5.6 / S13）------------------------------
class IdentifyCandidate(BaseModel):
    common_name: str
    scientific_name: str | None = None
    rank_hint: RankHint = "species"
    confidence: float = 0.0
    species_code: str | None = None  # 解析出的码
    resolution_stage: ResolutionStage | None = None


class IdentifyResult(BaseModel):
    """产品端「丢图看科属种」的一等输出（CLI 卡片/--json/v1 web 复用）。无 summary。"""

    model_alias: str
    abstain: bool = False
    abstain_reason: AbstainReason | None = None
    # top-1（科属种）
    species_code: str | None = None
    common_name: str | None = None
    order: str = ""
    family: str = ""
    genus: str = ""
    scientific_name: str = ""
    resolution_stage: ResolutionStage | None = None
    resolution_score: float = 0.0
    ambiguous: bool = False
    field_marks: str = ""
    candidates: list[IdentifyCandidate] = Field(default_factory=list)  # top-k + hedge 透明度
    # 成本/性能（横比各家 API 用）
    cost_usd: float | None = None
    latency_ms: float = 0.0
    total_tokens: int = 0
    model_resolved: str = ""
    schema_valid: bool = True
    raw_output: str = ""
