"""
LivingSpec Pydantic 模型

唯一真相源：所有代码从此读取格式定义。

新增 SemanticAnchor — 信息守恒的原子实体
      不可变实体：只增不改不删。每一层 LLM 可以引用/追加，但不能修改/删除。
"""

from typing import Optional, Union, List
from pydantic import BaseModel, Field, field_validator


class LivingSpecMeta(BaseModel):
    """Living Spec 元数据"""
    engine: str = "spec_pro"
    version: str = "2.1"
    spec_version: int = 1
    scenario: str = "genesis"
    mode: str = "standard"
    created_at: str
    updated_at: str
    conversation_rounds: int = 0
    quality_score: Union[int, float] = 0
    quality_level: str = "C"


class SuccessMetric(BaseModel):
    """成功指标"""
    metric: str
    target: str


class User(BaseModel):
    """用户角色"""
    role: str
    count: Optional[str] = None
    key_needs: Optional[str] = None
    regions: Optional[list[str]] = None


class Capabilities(BaseModel):
    """能力分层"""
    always_do: list[str] = Field(default_factory=list)
    should_do: list[str] = Field(default_factory=list)
    never_do: list[str] = Field(default_factory=list)


class QualityAttribute(BaseModel):
    """质量属性"""
    category: str
    spec: str
    priority: str = "P1"


class RisksAndAssumptions(BaseModel):
    """风险与假设"""
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class Term(BaseModel):
    """术语定义"""
    name: str
    definition: str


class ConfirmedLayer(BaseModel):
    """已确认层"""
    objective: str = ""
    pain_points: list[str] = Field(default_factory=list)
    success_metrics: list[SuccessMetric] = Field(default_factory=list)
    users: list[User] = Field(default_factory=list)
    key_scenarios: list[str] = Field(default_factory=list)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    quality_attributes: list[QualityAttribute] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    integration: dict = Field(default_factory=dict)
    risks_and_assumptions: RisksAndAssumptions = Field(default_factory=RisksAndAssumptions)
    terms: list[Term] = Field(default_factory=list)
    user_directives: list[dict] = Field(default_factory=list)


class InferredItem(BaseModel):
    """推断项"""
    id: str
    dimension: str
    content: str
    confidence: float
    basis: str = ""
    status: str = "pending"


class Guardrails(BaseModel):
    """护栏"""
    always_do: list[str] = Field(default_factory=list)
    never_do: list[str] = Field(default_factory=list)
    ask_first: list[str] = Field(default_factory=list)


class SolutionProHints(BaseModel):
    """下游提示"""
    focus_areas: list[str] = Field(default_factory=list)
    complexity_notes: list[str] = Field(default_factory=list)
    priority_dimensions: list[str] = Field(default_factory=list)


# ============================================================================
# Semantic Anchors — 信息守恒的原子实体
# ============================================================================

class SemanticAnchor(BaseModel):
    """
    语义锚点 — 全链路不可变的信息守恒实体
    
    设计原则（AI Native 契约笼子）：
    - LLM 做语义提取（从 narrative 中识别不可抽象化的具体引用）
    - 代码做格式化（写入结构化字段，Pydantic 强制 schema）
    - 全链路透传（每一层只增不改不删）
    
    泛化性：
    - 适用于任何有"具体技术约束"的项目（API 名、工具名、架构原则）
    - 不适用于抽象哲学概念（"设计优雅"不算 anchor）
    """
    name: str = Field(..., description="具体引用名称，如 sessions_spawn、全LLM控制")
    category: str = Field(..., description="platform_api | architecture_principle | external_system | technical_constraint")
    constraint: str = Field(..., description="对该引用的具体约束描述（必须可操作）")
    source_quote: str = Field(..., description="narrative 中的原文引用（证据）")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="LLM 自评置信度")
    applicable_to: List[str] = Field(default_factory=lambda: ["all"], description="适用的下游 Worker 角色列表，['all'] = 广播")
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        valid = {"platform_api", "architecture_principle", "external_system", "technical_constraint"}
        if v not in valid:
            raise ValueError(f"契约笼子: SemanticAnchor.category 必须是 {valid} 之一，实际: {v}")
        return v
    
    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError(f"契约笼子: SemanticAnchor.name 不能为空或太短: '{v}'")
        return v.strip()
    
    @field_validator("constraint")
    @classmethod
    def validate_constraint_actionable(cls, v):
        if len(v.strip()) < 5:
            raise ValueError(f"契约笼子: SemanticAnchor.constraint 太短，不可操作: '{v}'")
        return v.strip()


class LivingSpec(BaseModel):
    """
    Living Spec 完整结构

    core_summary 是 narrative 的压缩版（≤5KB），包含：
    - 项目背景（1-2 句话）
    - 核心目标（列表）
    - 关键约束（列表）
    - 用户画像（1-2 句话）

    下游 Agent 的读取策略：
    1. 先读 core_summary（快速理解全貌）
    2. 按需深入读 narrative 的特定段落
    3. requirement_index 用于 Verification 的 REQ-ID 追溯
    4. semantic_anchors 用于全链路信息守恒（不可变实体）
    """
    meta: LivingSpecMeta
    confirmed: ConfirmedLayer
    inferred: list[InferredItem] = Field(default_factory=list)
    guardrails: Optional[Guardrails] = None
    solution_pro_hints: Optional[SolutionProHints] = None
    route_recommendation: Optional[str] = None
    # Living Spec 成为唯一输入（叙述为主体 + REQ-ID 索引为附件）
    core_summary: str = ""  # 核心需求摘要（≤5KB），下游 Agent 优先读取，避免 30KB narrative 的 token 开销
    narrative: str = ""  # 完整的用户需求叙述（主体）
    requirement_index: list = Field(default_factory=list)  # REQ-ID 追溯索引（附件）
    # Semantic Anchors — 全链路信息守恒实体
    semantic_anchors: list[SemanticAnchor] = Field(default_factory=list, description="不可变语义锚点，全链路透传")
