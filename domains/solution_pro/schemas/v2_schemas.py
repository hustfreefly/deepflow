"""
Solution Pro V2 Schema 定义

Version: 1.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

描述:
- 集中定义所有 V2 Stage 输出的 Pydantic schema
- 使用 Pydantic V2 BaseModel
- 所有 schema 包含 schema_version 字段
- 提供 validate_stage_output() 统一验证函数
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# ============================================================================
# 基础 Schema（共享字段）
# ============================================================================

class V2BaseSchema(BaseModel):
    """V2 Schema 基类，包含 schema_version 和 timestamp"""
    schema_version: str = Field(default="1.0.0", description="Schema 版本号，遵循 semver")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="生成时间戳")


# ============================================================================
# Module 1: Planning V2 三层架构
# ============================================================================

class ExpertConfig(BaseModel):
    """专家配置（Meta-Planner 输出）"""
    expert_name: str = Field(description="专家标识（如 security, performance, scalability）")
    domain: str = Field(description="专家领域描述")
    focus_areas: list[str] = Field(description="该专家需聚焦的具体方面")
    evaluation_lens: str = Field(description="评估视角（如 '从安全漏洞角度审视每个设计决策'）")


class GateAWeights(BaseModel):
    """Gate A 四维度权重（和必须 = 1.0）"""
    completeness: float = Field(ge=0.0, le=1.0, description="完整性权重")
    necessity: float = Field(ge=0.0, le=1.0, description="必要性权重")
    alignment: float = Field(ge=0.0, le=1.0, description="目标一致性权重")
    global_impact: float = Field(ge=0.0, le=1.0, description="全局影响权重")
    
    @field_validator("global_impact")
    @classmethod
    def validate_weights_sum(cls, v, info):
        """验证四维度权重和 = 1.0"""
        values = info.data
        if "completeness" in values and "necessity" in values and "alignment" in values:
            weight_sum = values["completeness"] + values["necessity"] + values["alignment"] + v
            if abs(weight_sum - 1.0) > 0.01:
                raise ValueError(f"Weights must sum to 1.0, got {weight_sum:.3f}")
        return v


class GateAThresholds(BaseModel):
    """Gate A 阈值（固定值）"""
    PASS: float = Field(default=0.85, description="PASS 阈值")
    WARNING: float = Field(default=0.70, description="WARNING 阈值")
    CRITICAL_WARNING: float = Field(default=0.60, description="CRITICAL_WARNING 阈值")
    BLOCK_RECOMMENDATION: float = Field(default=0.0, description="BLOCK_RECOMMENDATION 阈值")


class GateAConfig(BaseModel):
    """Gate A 配置"""
    weights: GateAWeights = Field(description="四维度动态权重")
    thresholds: GateAThresholds = Field(default_factory=GateAThresholds, description="固定阈值")
    rationale: str = Field(description="权重分配理由")


class DynamicCheck(BaseModel):
    """Gate B 动态检查项"""
    name: str = Field(description="检查项名称")
    description: str = Field(description="检查项描述")
    pass_criteria: str = Field(description="通过标准（Harness Agent 据此判定）")
    severity: Literal["CRITICAL", "MINOR"] = Field(description="严重程度")
    reasoning: str = Field(description="为什么需要这项检查")


class GateBConfig(BaseModel):
    """Gate B 配置"""
    dynamic_checks: list[DynamicCheck] = Field(description="动态检查项列表")


class VerdictPolicy(BaseModel):
    """判定策略"""
    warning_acceptable: bool = Field(default=False, description="WARNING 是否允许通过（高风险任务为 false）")
    min_gate_b_pass_rate: float = Field(default=0.8, ge=0.0, le=1.0, description="Gate B 最低通过率")


class ExpertManifestSchema(V2BaseSchema):
    """
    Meta-Planner 输出 schema
    
    包含：
    - task_profile: 任务领域 + 复杂度
    - experts: 专家列表（N 个）
    - gate_config: Gate A 权重 + Gate B 检查项
    """
    task_profile: dict = Field(description="任务信息", json_schema_extra={
        "properties": {
            "domain": {"type": "string", "description": "任务领域"},
            "complexity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "risk_areas": {"type": "array", "items": {"type": "string"}},
        }
    })
    experts: list[ExpertConfig] = Field(min_length=1, max_length=5, description="专家列表（1-5 个）")
    gate_a: GateAConfig = Field(description="Gate A 配置")
    gate_b: GateBConfig = Field(description="Gate B 配置")
    verdict_policy: VerdictPolicy = Field(default_factory=VerdictPolicy, description="判定策略")


class Constraint(BaseModel):
    """约束项（Expert Planner 输出）"""
    constraint_id: str = Field(description="约束 ID（如 C-001）")
    description: str = Field(description="约束描述")
    priority: Literal["MUST", "SHOULD", "MAY"] = Field(description="优先级")
    rationale: str = Field(default="", description="约束理由（可选）")


class Risk(BaseModel):
    """风险项（Expert Planner 输出）"""
    risk_id: str = Field(description="风险 ID（如 R-001）")
    description: str = Field(description="风险描述")
    mitigation: str = Field(description="缓解措施")


class AcceptanceCriterion(BaseModel):
    """验收标准（Expert Planner 输出）"""
    criterion_id: str = Field(description="验收标准 ID（如 AC-001）")
    description: str = Field(description="验收标准描述")
    verification_method: str = Field(description="验证方法")


class ExpertPlanSchema(V2BaseSchema):
    """
    Expert Planner 输出 schema（统一最小 schema）
    
    包含：
    - constraints: 约束集
    - risks: 风险项
    - acceptance_criteria: 验收标准
    - covered_req_ids: 覆盖的 P0 REQ ID（仅 P0）
    """
    expert_name: str = Field(description="专家名称")
    constraints: list[Constraint] = Field(min_length=1, description="约束集")
    risks: list[Risk] = Field(default_factory=list, description="风险项")
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1, description="验收标准")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")


class UnifiedConstraint(BaseModel):
    """统一约束（Convergence Planner 输出）"""
    constraint_id: str = Field(description="约束 ID")
    description: str = Field(description="约束描述")
    priority: Literal["MUST", "SHOULD", "MAY"] = Field(description="优先级")
    source_experts: list[str] = Field(min_length=1, description="来源专家列表")
    conflicts_resolved: list[str] = Field(default_factory=list, description="已解决的冲突描述")


class UnifiedConstraintsSchema(V2BaseSchema):
    """
    Convergence Planner 输出 schema（统一约束集）
    
    包含：
    - unified_constraints: 合并后的约束集
    - rejected_constraints: 被拒绝的约束（附理由）
    - meta: 统计信息
    """
    unified_constraints: list[UnifiedConstraint] = Field(min_length=1, description="统一约束集")
    rejected_constraints: list[dict] = Field(default_factory=list, description="被拒绝的约束")
    meta: dict = Field(description="统计信息", json_schema_extra={
        "properties": {
            "total_expert_plans": {"type": "integer"},
            "total_input_constraints": {"type": "integer"},
            "total_output_constraints": {"type": "integer"},
            "merge_ratio": {"type": "number"},
        }
    })
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")


class VerificationItem(BaseModel):
    """验证项"""
    check_id: str = Field(description="验证项 ID")
    constraint_id: str = Field(description="关联的约束 ID")
    verification_method: str = Field(description="验证方法")
    expected_result: str = Field(description="预期结果")


class VerificationChecklistSchema(V2BaseSchema):
    """
    验证清单 schema
    
    包含：
    - checklist: 验证项列表
    - total_checks: 总检查数
    """
    checklist: list[VerificationItem] = Field(min_length=1, description="验证项列表")
    total_checks: int = Field(description="总检查数")


# ============================================================================
# Module 2: Research 扩展
# ============================================================================

class ResearchExpertSchema(V2BaseSchema):
    """
    Research Expert 输出 schema
    
    包含：
    - research_findings: 研究发现
    - technology_recommendations: 技术推荐
    - open_questions: 未解决问题
    """
    expert_name: str = Field(description="专家名称")
    research_findings: list[dict] = Field(description="研究发现")
    technology_recommendations: list[dict] = Field(default_factory=list, description="技术推荐")
    open_questions: list[str] = Field(default_factory=list, description="未解决问题")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")


class ResearchConsolidatorSchema(V2BaseSchema):
    """
    Research Consolidator 输出 schema
    
    包含：
    - consolidated_findings: 合并后的研究发现
    - consensus_points: 共识点
    - divergence_points: 分歧点
    """
    consolidated_findings: list[dict] = Field(description="合并后的研究发现")
    consensus_points: list[str] = Field(default_factory=list, description="共识点")
    divergence_points: list[dict] = Field(default_factory=list, description="分歧点")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")


class ArchitectureSchema(V2BaseSchema):
    """
    Architecture Design 输出 schema
    
    包含：
    - architecture_decisions: 架构决策
    - component_diagram: 组件图
    - data_flows: 数据流
    - technology_stack: 技术栈
    """
    architecture_decisions: list[dict] = Field(description="架构决策")
    component_diagram: dict = Field(description="组件图")
    data_flows: list[dict] = Field(default_factory=list, description="数据流")
    technology_stack: list[dict] = Field(default_factory=list, description="技术栈")
    deployment_view: dict = Field(default_factory=dict, description="部署视图")
    p0_req_traceability: dict = Field(default_factory=dict, description="P0 REQ 追溯矩阵")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")


class DetailedDesignSchema(V2BaseSchema):
    """
    Detailed Design 输出 schema
    
    包含：
    - modules: 模块定义
    - apis: API 定义
    - database_schema: 数据库 schema
    - sequence_diagrams: 时序图
    """
    modules: list[dict] = Field(description="模块定义")
    apis: list[dict] = Field(default_factory=list, description="API 定义")
    database_schema: dict = Field(default_factory=dict, description="数据库 schema")
    sequence_diagrams: list[dict] = Field(default_factory=list, description="时序图")
    p0_req_traceability: dict = Field(default_factory=dict, description="P0 REQ 追溯矩阵")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")


# ============================================================================
# Module 3: Review & QC（Fix Loop）
# ============================================================================

class ConsolidationSchema(V2BaseSchema):
    """
    Consolidation 输出 schema
    
    包含：
    - solution_summary: 方案摘要
    - design_decisions: 设计决策
    - implementation_plan: 实施计划
    - risk_register: 风险登记册
    - checklist_results: 验证清单结果
    """
    solution_summary: str = Field(max_length=500, description="方案摘要（≤500字）")
    design_decisions: list[dict] = Field(description="设计决策")
    implementation_plan: dict = Field(description="实施计划")
    risk_register: list[dict] = Field(default_factory=list, description="风险登记册")
    checklist_results: list[dict] = Field(description="验证清单结果")
    p0_req_traceability_matrix: dict = Field(default_factory=dict, description="P0 REQ 追溯矩阵")
    constraint_conservation: dict = Field(default_factory=dict, description="约束守恒检查")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")


class HarnessReportSchema(V2BaseSchema):
    """
    Harness Report 输出 schema
    
    包含：
    - gate_a: Gate A 评分
    - gate_b: Gate B 评分
    - final_verdict: 最终判定
    """
    gate_a: dict = Field(description="Gate A 评分", json_schema_extra={
        "properties": {
            "score": {"type": "number"},
            "verdict": {"type": "string", "enum": ["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]},
        }
    })
    gate_b: dict = Field(description="Gate B 评分", json_schema_extra={
        "properties": {
            "pass_rate": {"type": "number"},
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "failed_items": {"type": "array"},
        }
    })
    final_verdict: dict = Field(description="最终判定", json_schema_extra={
        "properties": {
            "final_verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        }
    })


class FixLoopStateSchema(V2BaseSchema):
    """
    Fix Loop 状态 schema
    
    包含：
    - round: 当前轮次
    - max_rounds: 最大轮次
    - status: 状态
    - fix_history: 修复历史
    """
    round: int = Field(ge=0, le=2, description="当前轮次（0-2）")
    max_rounds: int = Field(default=2, description="最大轮次")
    status: Literal["IDLE", "EVALUATING", "DIAGNOSING", "FIXING", "PASS", "ABORT"] = Field(description="状态")
    last_score: Optional[float] = Field(default=None, description="上次评分")
    fix_history: list[dict] = Field(default_factory=list, description="修复历史")
    frozen_items: list[str] = Field(default_factory=list, description="冻结项（已 PASS）")
    regression_detected: list[dict] = Field(default_factory=list, description="检测到的回归")


# ============================================================================
# 收敛点文件（Module 间通信契约）
# ============================================================================

class OriginalReference(BaseModel):
    """原始引用"""
    path: str = Field(description="文件路径")
    hash: str = Field(description="SHA256 hash")
    size_bytes: int = Field(description="文件大小（字节）")


class SemanticVerification(BaseModel):
    """语义等价性验证结果"""
    verdict: Literal["EQUIVALENT", "PARTIAL", "NOT_EQUIVALENT"] = Field(description="验证结果")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度")
    divergences: list[str] = Field(default_factory=list, description="语义偏离点")


class PlanningConvergenceSchema(V2BaseSchema):
    """
    收敛点 1: Planning Convergence
    
    包含：
    - unified_constraints: 统一约束集
    - verification_checklist: 验证清单
    - planning_summary: Planning 摘要
    - expert_divergence: 专家分歧
    - original_references: 原始引用
    - semantic_verification: 语义等价性验证
    - gate_a_scores: Gate A 评分
    - gate_b_results: Gate B 结果
    - gate_verdict: Gate 判定
    """
    module: Literal["planning"] = Field(default="planning")
    unified_constraints: list[dict] = Field(description="统一约束集")
    verification_checklist: list[dict] = Field(description="验证清单")
    planning_summary: str = Field(max_length=500, description="Planning 摘要（≤500字）")
    expert_divergence: list[dict] = Field(default_factory=list, description="专家分歧")
    original_references: dict[str, OriginalReference] = Field(default_factory=dict, description="原始引用")
    semantic_verification: SemanticVerification = Field(description="语义等价性验证")
    gate_a_scores: dict = Field(description="Gate A 评分")
    gate_b_results: dict = Field(description="Gate B 结果")
    gate_verdict: dict = Field(description="Gate 判定")
    metadata: dict = Field(default_factory=dict, alias="_metadata", description="元数据")


class ResearchConvergenceSchema(V2BaseSchema):
    """
    收敛点 2: Research Convergence
    
    包含：
    - research_summary: Research 摘要
    - key_findings: 关键发现
    - design_decisions: 设计决策
    - open_questions: 未解决问题
    - architecture: 架构设计引用
    - detailed_design: 详细设计引用
    - information_conservation: 信息守恒检查
    """
    module: Literal["research"] = Field(default="research")
    research_summary: str = Field(max_length=1000, description="Research 摘要（≤1000字）")
    key_findings: list[dict] = Field(description="关键发现")
    design_decisions: list[dict] = Field(description="设计决策")
    open_questions: list[dict] = Field(default_factory=list, description="未解决问题")
    architecture: dict = Field(description="架构设计引用")
    detailed_design: dict = Field(description="详细设计引用")
    information_conservation: dict = Field(description="信息守恒检查")
    original_references: dict[str, OriginalReference] = Field(default_factory=dict, description="原始引用")
    semantic_verification: SemanticVerification = Field(description="语义等价性验证")
    gate_a_scores: dict = Field(description="Gate A 评分")
    gate_b_results: dict = Field(description="Gate B 结果")
    gate_verdict: dict = Field(description="Gate 判定")
    metadata: dict = Field(default_factory=dict, alias="_metadata", description="元数据")


class FinalConvergenceSchema(V2BaseSchema):
    """
    收敛点 3: Final Convergence
    
    包含：
    - final_solution: 最终方案引用
    - traceability_matrix: 追溯矩阵
    - quality_report: 质量报告
    - remaining_risks: 剩余风险
    """
    module: Literal["review_qc"] = Field(default="review_qc")
    final_solution: dict = Field(description="最终方案引用")
    traceability_matrix: dict = Field(description="追溯矩阵")
    quality_report: dict = Field(description="质量报告")
    remaining_risks: list[dict] = Field(default_factory=list, description="剩余风险")
    constraint_conservation: dict = Field(description="约束守恒检查")
    original_references: dict[str, OriginalReference] = Field(default_factory=dict, description="原始引用")
    semantic_verification: SemanticVerification = Field(description="语义等价性验证")
    gate_a_scores: dict = Field(description="Gate A 评分")
    gate_b_results: dict = Field(description="Gate B 结果")
    gate_verdict: dict = Field(description="Gate 判定")
    metadata: dict = Field(default_factory=dict, alias="_metadata", description="元数据")


# ============================================================================
# 信息守恒契约
# ============================================================================

class InformationContractOutput(BaseModel):
    """信息契约输出定义"""
    name: str = Field(description="输出文件名")
    schema: dict = Field(description="JSON Schema")
    required_by: list[str] = Field(description="下游 Stage 或 Pro 名称")
    replaces: Optional[str] = Field(default=None, description="替代的旧输出")


class InformationContractSchema(V2BaseSchema):
    """
    信息守恒契约 schema
    
    包含：
    - contracts: 契约列表
    - deprecated_outputs: 已废弃输出
    """
    contracts: list[dict] = Field(description="契约列表")
    deprecated_outputs: list[dict] = Field(default_factory=list, description="已废弃输出")


# ============================================================================
# 统一验证函数
# ============================================================================

# Stage 名 → Schema 映射
STAGE_SCHEMA_MAP = {
    # Module 1: Planning V2
    "meta_planning": ExpertManifestSchema,
    "expert_plans": ExpertPlanSchema,  # 目录，每个文件单独验证
    "convergence_planning": UnifiedConstraintsSchema,
    "unified_constraints": UnifiedConstraintsSchema,
    "verification_checklist": VerificationChecklistSchema,
    
    # Module 2: Research
    "research_experts": ResearchExpertSchema,  # 目录
    "research_consolidator": ResearchConsolidatorSchema,
    "architecture": ArchitectureSchema,
    "detailed_design": DetailedDesignSchema,
    
    # Module 3: Review & QC
    "consolidation": ConsolidationSchema,
    "harness_report": HarnessReportSchema,
    "fix_loop_state": FixLoopStateSchema,
    
    # 收敛点
    "planning_convergence": PlanningConvergenceSchema,
    "research_convergence": ResearchConvergenceSchema,
    "final_convergence": FinalConvergenceSchema,
    
    # 信息契约
    "information_contract": InformationContractSchema,
}


def validate_stage_output(stage_name: str, data: dict) -> tuple[bool, str]:
    """
    统一验证 Stage 输出是否符合 schema
    
    Args:
        stage_name: Stage 名称
        data: Stage 输出数据
    
    Returns:
        (is_valid, error_message)
    """
    schema_class = STAGE_SCHEMA_MAP.get(stage_name)
    if not schema_class:
        return False, f"Unknown stage: {stage_name}"
    
    try:
        schema_class(**data)
        return True, ""
    except Exception as e:
        return False, str(e)


def get_stage_schema(stage_name: str) -> Optional[type[BaseModel]]:
    """获取 Stage 对应的 Schema 类"""
    return STAGE_SCHEMA_MAP.get(stage_name)


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
