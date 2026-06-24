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
    """Living Spec 完整结构"""
    meta: LivingSpecMeta
    confirmed: ConfirmedLayer
    inferred: list[InferredItem] = Field(default_factory=list)
    guardrails: Optional[Guardrails] = None
    solution_pro_hints: Optional[SolutionProHints] = None
    route_recommendation: Optional[str] = None
