"""
Spec Pro 契约层 (Contract Layer)

Pydantic 模型作为唯一真相源 (Single Source of Truth)。

从此处自动生成:
1. JSON Schema → schemas/ 目录
2. Gate 字段检查清单 → gates.py 引用

用法:
    from domains.spec_pro.contracts import LivingSpec, RoundResult

    # 验证数据
    validated = LivingSpec(**data)

    # 生成 Schema
    schema = LivingSpec.model_json_schema()
"""

from domains.spec_pro.contracts.living_spec import (
    LivingSpec,
    LivingSpecMeta,
    ConfirmedLayer,
    Capabilities,
    RisksAndAssumptions,
    QualityAttribute,
    User,
    SuccessMetric,
    InferredItem,
    Guardrails,
    SolutionProHints,
)

from domains.spec_pro.contracts.round_result import (
    RoundResult,
    Quality,
    DimensionScores,
    Question,
)

from domains.spec_pro.contracts.quality_report import (
    QualityReport,
    Dimension,
)

from domains.spec_pro.contracts.conversation_log import (
    ConversationLog,
    ConversationRound,
)

from domains.spec_pro.contracts.quality_trajectory import (
    QualityTrajectory,
    TrajectoryPoint,
)

__all__ = [
    # LivingSpec
    "LivingSpec",
    "LivingSpecMeta",
    "ConfirmedLayer",
    "Capabilities",
    "RisksAndAssumptions",
    "QualityAttribute",
    "User",
    "SuccessMetric",
    "InferredItem",
    "Guardrails",
    "SolutionProHints",
    # RoundResult
    "RoundResult",
    "Quality",
    "DimensionScores",
    "Question",
    # QualityReport
    "QualityReport",
    "Dimension",
    # ConversationLog
    "ConversationLog",
    "ConversationRound",
    # QualityTrajectory
    "QualityTrajectory",
    "TrajectoryPoint",
]
