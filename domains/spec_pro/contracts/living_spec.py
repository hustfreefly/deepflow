"""
LivingSpec Pydantic 模型

唯一真相源:所有代码从此读取格式定义。

新增 SemanticAnchor - 信息守恒的原子实体
      不可变实体:只增不改不删。每一层 LLM 可以引用/追加,但不能修改/删除。
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
    domain_type: Optional[str] = Field(
        default="software",
        description="领域类型标识(software/investment/hardware/business/其他),用于加载对应领域配置"
    )


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
    category: str = Field(default="", description="术语分类，如 technical/business/domain")


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
    benchmark_references: list = Field(default_factory=list, description="基准参考")
    design_delegations: list = Field(default_factory=list, description="设计委托")
    adaptive_requirements: list = Field(default_factory=list, description="自适应需求")
    quality_priorities: list = Field(default_factory=list, description="质量优先级")
    industry_references: list = Field(default_factory=list, description="行业参考")

    @field_validator('users')
    @classmethod
    def validate_users(cls, v):
        """Fix 3: 确保每个 user 都有非空的 role。"""
        if isinstance(v, list):
            for i, user in enumerate(v):
                role = None
                if isinstance(user, dict):
                    role = user.get("role", "")
                elif hasattr(user, "role"):
                    role = user.role
                if role is not None and not str(role).strip():
                    raise ValueError(f"User[{i}] missing 'role': {user}")
        return v


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
    focus_areas: list = Field(default_factory=list, description="关注领域")
    complexity_notes: Optional[str] = Field(default=None, description="复杂度说明")
    priority_dimensions: list[str] = Field(default_factory=list, description="优先级维度")
    layer2_hints: Optional[dict] = Field(default=None, description="Layer 2 约束提示")
    anti_patterns: list[str] = Field(default_factory=list, description="反模式提示")

    @field_validator('focus_areas', mode='before')
    @classmethod
    def coerce_focus_areas(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            result = []
            for item in v:
                if isinstance(item, dict):
                    # 从 dict 中提取 area 或 name 字段
                    result.append(item.get('area', item.get('name', str(item))))
                elif isinstance(item, str):
                    result.append(item)
                else:
                    pass  # 非 str/dict 类型直接跳过（不转换）
            return result
        return v


# ============================================================================
# Semantic Anchors - 信息守恒的原子实体
# ============================================================================

# 建议类别列表（开放枚举，不强制）
SUGGESTED_ANCHOR_CATEGORIES = {
    # 软件域（原有）
    "platform_api", "architecture_principle", "external_system", "technical_constraint",
    # 投资域
    "market_segment", "patent_portfolio", "regulatory_framework", "financial_metric",
    # 硬件域
    "physical_constraint", "material_spec", "manufacturing_process", "thermal_parameter",
    # 商业域
    "business_rule", "compliance_requirement", "partnership_model", "revenue_stream",
}


class SemanticAnchor(BaseModel):
    """
    语义锚点 — 全链路不可变的信息守恒实体
    
    设计原则（AI Native 契约笼子）：
    - LLM 做语义提取（从 narrative 中识别不可抽象化的具体引用）
    - 代码做格式化（写入结构化字段，Pydantic 强制 schema）
    - 全链路透传（每一层只增不改不删）
    
    泛化性：
    - 适用于任何有“具体约束”的项目（关键引用名称、规则、原则）
    - 不适用于抽象哲学概念（“设计优雅”不算 anchor）
    """
    name: str = Field(..., description="具体引用名称，如 sessions_spawn、全LLM控制")
    category: str = Field(..., description="platform_api | architecture_principle | external_system | technical_constraint")
    constraint: str = Field(..., description="对该引用的具体约束描述（必须可操作）")
    source_quote: str = Field(..., description="narrative 中的原文引用（证据）")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="LLM 自评置信度")
    applicable_to: List[str] = Field(default_factory=lambda: ["all"], description="适用的下游 Worker 角色列表，['all'] = 广播")
    category_rationale: Optional[str] = Field(
        default=None,
        description="当 category 不在标准列表中时，解释为什么需要此类别"
    )
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError(f"契约笼子: SemanticAnchor.category 太短: '{v}'")
        if v not in SUGGESTED_ANCHOR_CATEGORIES:
            import logging
            logging.getLogger(__name__).info(
                f"SemanticAnchor.category '{v}' 不在建议列表中，但已接受（开放枚举）"
            )
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
            raise ValueError(f"契约笼子: SemanticAnchor.constraint 太短,不可操作: '{v}'")
        return v.strip()


class LivingSpec(BaseModel):
    """
    Living Spec 完整结构

    core_summary 是 narrative 的压缩版(≤5KB),包含:
    - 项目背景(1-2 句话)
    - 核心目标(列表)
    - 关键约束(列表)
    - 用户画像(1-2 句话)

    下游 Agent 的读取策略:
    1. 先读 core_summary(快速理解全貌)
    2. 按需深入读 narrative 的特定段落
    3. requirement_index 用于 Verification 的 REQ-ID 追溯
    4. semantic_anchors 用于全链路信息守恒(不可变实体)
    """
    meta: LivingSpecMeta
    confirmed: ConfirmedLayer
    inferred: list[InferredItem] = Field(default_factory=list)
    guardrails: Optional[Guardrails] = None
    solution_pro_hints: Optional[SolutionProHints] = None
    route_recommendation: Optional[str] = None
    # Living Spec 成为唯一输入(叙述为主体 + REQ-ID 索引为附件)
    core_summary: str = ""  # 核心需求摘要(≤5KB),下游 Agent 优先读取,避免 30KB narrative 的 token 开销
    narrative: str = ""  # 完整的用户需求叙述(主体)
    requirement_index: list = Field(default_factory=list)  # REQ-ID 追溯索引(附件)
    # Semantic Anchors - 全链路信息守恒实体
    semantic_anchors: list[SemanticAnchor] = Field(default_factory=list, description="不可变语义锚点,全链路透传")
    # 多轮对话摘要
    conversation_digest: Optional[dict] = Field(
        default=None,
        description="多轮对话摘要（summary + key_excerpts）"
    )

    @field_validator('core_summary')
    @classmethod
    def validate_core_summary(cls, v):
        """Fix 3: core_summary 非空时必须满足最小长度（结构性约束，不验证语义）。"""
        if isinstance(v, str) and v.strip() and len(v.strip()) < 10:
            raise ValueError(f"core_summary too short: {len(v.strip())} chars (min 10)")
        return v

    @field_validator('narrative')
    @classmethod
    def validate_narrative(cls, v):
        """Fix 3: narrative 非空时必须满足最小长度（结构性约束，不验证语义）。"""
        if isinstance(v, str) and v.strip() and len(v.strip()) < 20:
            raise ValueError(f"narrative too short: {len(v.strip())} chars (min 20)")
        return v
