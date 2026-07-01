"""
LivingSpec Pydantic 模型

唯一真相源：所有代码从此读取格式定义。
"""

from typing import Optional, Union
from pydantic import BaseModel, Field


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
    """
    meta: LivingSpecMeta
    confirmed: ConfirmedLayer
    inferred: list[InferredItem] = Field(default_factory=list)
    guardrails: Optional[Guardrails] = None
    solution_pro_hints: Optional[SolutionProHints] = None
    route_recommendation: Optional[str] = None
    # V3: Living Spec 成为唯一输入（叙述为主体 + REQ-ID 索引为附件）
    core_summary: str = ""  # 核心需求摘要（≤5KB），下游 Agent 优先读取，避免 30KB narrative 的 token 开销
    narrative: str = ""  # 完整的用户需求叙述（主体）
    requirement_index: list = Field(default_factory=list)  # REQ-ID 追溯索引（附件）
