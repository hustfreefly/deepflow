"""
Solution Pro Schemas

Version: 2.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

描述:
- 集中管理所有 Schema 定义
- Schema（向后兼容）
- Schema（新架构）
"""

from .schemas import (
    # 基础
    V2BaseSchema,
    # Module 1: Planning ExpertManifestSchema,
    ExpertPlanSchema,
    UnifiedConstraintsSchema,
    VerificationChecklistSchema,
    # Module 2: Research
    ResearchExpertSchema,
    ResearchConsolidatorSchema,
    ArchitectureSchema,
    DetailedDesignSchema,
    # Module 3: Review & QC
    ConsolidationSchema,
    HarnessReportSchema,
    FixLoopStateSchema,
    # 收敛点
    PlanningConvergenceSchema,
    ResearchConvergenceSchema,
    FinalConvergenceSchema,
    # 信息契约
    InformationContractSchema,
    # 验证函数
    validate_stage_output,
    get_stage_schema,
    STAGE_SCHEMA_MAP,
)

__all__ = [
    # 基础
    "V2BaseSchema",
    # Module 1
    "ExpertManifestSchema",
    "ExpertPlanSchema",
    "UnifiedConstraintsSchema",
    "VerificationChecklistSchema",
    # Module 2
    "ResearchExpertSchema",
    "ResearchConsolidatorSchema",
    "ArchitectureSchema",
    "DetailedDesignSchema",
    # Module 3
    "ConsolidationSchema",
    "HarnessReportSchema",
    "FixLoopStateSchema",
    # 收敛点
    "PlanningConvergenceSchema",
    "ResearchConvergenceSchema",
    "FinalConvergenceSchema",
    # 信息契约
    "InformationContractSchema",
    # 验证函数
    "validate_stage_output",
    "get_stage_schema",
    "STAGE_SCHEMA_MAP",
]
