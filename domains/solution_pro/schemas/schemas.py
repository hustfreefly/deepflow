"""
Solution Pro Schema 定义

Version: 2.1.0 (V3.1 架构适配)
Author: DeepFlow Solution Pro
Date: 2026-07-14

描述:
- 集中定义所有 Stage 输出的 Pydantic schema
- 使用 Pydantic V2 BaseModel
- 所有 schema 包含 schema_version 字段
- 提供 validate_stage_output() 统一验证函数

V3.1 架构说明:
- V3.0: Schema 由 Python orchestrator 在运行时调用 model_validate() 做强制验证
- V3.1: Python orchestrator 已删除，Schema 作为格式文档参考
  - 运行时验证由 post_validator.py (L0) 做基础结构检查
  - 语义级 Schema 对齐由对抗 Agent (L2) 在维度 5 检查
  - HarnessCheckV2 是唯一保留生产调用的 Schema (task_builder.py)
"""

from typing import Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime


# ============================================================================
# 基础 Schema（共享字段）
# ============================================================================

class V2BaseSchema(BaseModel):
    """Schema 基类，包含 schema_version 和 timestamp"""
    schema_version: str = Field(default="1.0.0", description="Schema 版本号，遵循 semver")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="生成时间戳")


# ============================================================================
# Domain Categories & Expert Template Registry
# ============================================================================

# 领域分类建议列表（开放枚举，不再强制）
SUGGESTED_DOMAIN_CATEGORIES = [
    # 软件域
    "backend_api", "frontend_ui", "mobile", "data_migration",
    "devops", "ml", "iac", "security", "performance",
    "testing_qa", "accessibility",
    # 投资域
    "due_diligence", "patent_analysis", "market_analysis",
    "financial_projection", "risk_assessment",
    # 硬件域
    "thermal_design", "mechanical_engineering", "electronic_design",
    "material_selection", "manufacturing_process",
    # 商业域
    "market_entry", "competitive_strategy", "compliance_legal",
    "financial_forecast", "partnership",
]
# 兼容现有引用：DOMAIN_CATEGORIES 变为 str 类型别名
DOMAIN_CATEGORIES = str

from domains.solution_pro.config.domain_loader import get_expert_templates

# DEPRECATED: 使用 get_registry_for_domain(domain_id) 替代
# 保留向后兼容，默认加载 software 域
EXPERT_TEMPLATE_REGISTRY: dict[str, list[dict[str, str]]] = get_expert_templates("software")

def get_registry_for_domain(domain_id: str) -> dict[str, list[dict[str, str]]]:
    """获取指定领域的专家模板"""
    return get_expert_templates(domain_id)


# ============================================================================
# Module 1: Planning 三层架构
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
    - p0_constraints: P0 约束列表（传递给 Convergence）
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
    p0_constraints: list[dict] = Field(default_factory=list, description="P0 约束列表（传递给 Convergence）")


class Constraint(BaseModel):
    """约束项（Expert Planner 输出）"""
    constraint_id: str = Field(description="约束 ID（如 C-001）")
    description: str = Field(description="约束描述")
    priority: Literal["MUST", "SHOULD", "MAY"] = Field(description="优先级")
    rationale: str = Field(default="", description="约束理由")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 REQ ID 列表")

    @field_validator("constraint_id")
    def validate_constraint_id_format(cls, v: str) -> str:
        """[Cage P1-5a] 约束ID必须是C-XXX格式"""
        import re
        if not re.match(r"^C-\d{3,}$", v):
            raise ValueError(
                f"[Cage P1-5a] Constraint ID must be C-XXX format (e.g., C-001), got: {v}"
            )
        return v
    
    @field_validator("description")
    def validate_description_min_length(cls, v: str) -> str:
        """[Cage P1-5b] 约束描述不能为空且至少10个字符"""
        if len(v.strip()) < 10:
            raise ValueError(
                f"[Cage P1-5b] Constraint description must be >= 10 chars, got: {len(v)} chars"
            )
        return v
    
    @field_validator("rationale")
    def validate_rationale_min_length(cls, v: str) -> str:
        """[Cage P1-5c] 约束理由必须非空且至少30个字符"""
        if len(v.strip()) < 30:
            raise ValueError(
                f"[Cage P1-5c] Constraint rationale must be >= 30 chars, got: {len(v)} chars"
            )
        return v


class Risk(BaseModel):
    """风险项（Expert Planner 输出）"""
    risk_id: str = Field(description="风险 ID（如 R-001）")
    description: str = Field(description="风险描述")
    mitigation: str = Field(description="缓解措施")
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = Field(default="MEDIUM", description="严重程度")


class AcceptanceCriterion(BaseModel):
    """验收标准（Expert Planner 输出）
    
    容错: 接受 criterion_id 或 criteria_id（LLM 常见混淆）
    """
    model_config = {"populate_by_name": True}
    
    criterion_id: str = Field(description="验收标准 ID（如 AC-001）", alias="criteria_id")
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
    - extensions: 领域特定扩展数据（可选）
    """
    expert_name: str = Field(description="专家名称")
    domain: str = Field(default="", description="专家所属领域")
    focus_areas: list[str] = Field(default_factory=list, description="聚焦的具体方面")
    constraints: list[Constraint] = Field(min_length=1, description="约束集")
    risks: list[Risk] = Field(default_factory=list, description="风险项")
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1, description="验收标准")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")
    extensions: Optional[dict] = Field(default=None, description="领域特定扩展数据")

    @model_validator(mode='after')
    def validate_constraint_id_uniqueness(self) -> 'ExpertPlanSchema':
        """[Cage P1-5d] 约束ID必须唯一"""
        ids = [c.constraint_id for c in self.constraints]
        if len(ids) != len(set(ids)):
            from collections import Counter
            duplicates = {id for id, count in Counter(ids).items() if count > 1}
            raise ValueError(
                f"[Cage P1-5d] Duplicate constraint IDs found: {duplicates}"
            )
        return self
    
    @model_validator(mode='after')
    def validate_must_ratio(self) -> 'ExpertPlanSchema':
        """[Cage P1-5e] MUST约束占比不能超过50%"""
        if not self.constraints:
            return self
        must_count = sum(1 for c in self.constraints if c.priority == "MUST")
        ratio = must_count / len(self.constraints)
        if ratio > 0.5:
            raise ValueError(
                f"[Cage P1-5e] MUST constraints {must_count}/{len(self.constraints)} = {ratio:.1%} > 50%. "
                f"Too many hard constraints reduce flexibility."
            )
        return self
    
    @model_validator(mode='after')
    def validate_p0_coverage(self) -> 'ExpertPlanSchema':
        """[Cage P1-5f] 如果声明了P0 REQ覆盖，必须真实覆盖"""
        if self.covered_req_ids:
            # 检查covered_req_ids格式正确
            for req_id in self.covered_req_ids:
                if not req_id or not req_id.strip():
                    raise ValueError(
                        f"[Cage P1-5f] Empty P0 REQ ID in covered_req_ids"
                    )
        return self


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
    p0_constraints_merged: list[dict] = Field(default_factory=list, description="P0 约束合并结果（传递给 Research）")

    # R2-FIX: _cage_f6_llm_control_scope 和 _cage_f7_threshold_consistency 已删除
    # 原因: UnifiedConstraint 模型未定义 control_flow_type / threshold_value 字段，
    # 这两个验证器永远不会触发实际校验，属于设计残留。


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
    - research_findings (alias: findings): 研究发现
    - technology_recommendations (alias: recommendations): 方案推荐
    - open_questions: 未解决问题
    """
    model_config = {"populate_by_name": True}

    expert_name: str = Field(description="专家名称")
    research_findings: list[dict] = Field(description="研究发现", alias="findings")
    technology_recommendations: list[dict] = Field(default_factory=list, description="方案推荐（选型/工具/方法建议）", alias="recommendations")
    open_questions: list[str] = Field(default_factory=list, description="未解决问题")
    covered_req_ids: list[str] = Field(default_factory=list, description="覆盖的 P0 REQ ID")

    @field_validator("research_findings")
    def validate_findings_count(cls, v: list[dict]) -> list[dict]:
        """[Cage P1-5g] Research findings数量至少3个"""
        if len(v) < 3:
            raise ValueError(
                f"[Cage P1-5g] Research findings count {len(v)} < 3 minimum. "
                f"Each expert must produce at least 3 findings."
            )
        return v
    
    @model_validator(mode='after')
    def validate_findings_quality(self) -> 'ResearchExpertSchema':
        """[Cage P1-5h] Research findings质量检查"""
        findings = self.research_findings or []
        
        # 检查至少50%的finding有evidence或sources
        with_evidence = sum(
            1 for f in findings 
            if f.get("evidence_url") or f.get("sources") or f.get("references")
        )
        if len(findings) > 0 and with_evidence / len(findings) < 0.5:
            raise ValueError(
                f"[Cage P1-5h] Evidence coverage {with_evidence}/{len(findings)} < 50%. "
                f"At least 50% of findings must have evidence/sources."
            )
        
        # 检查至少50%的finding描述>=200字符
        deep_findings = sum(
            1 for f in findings 
            if len(f.get("description", "")) >= 200
        )
        if len(findings) > 0 and deep_findings / len(findings) < 0.5:
            raise ValueError(
                f"[Cage P1-5h] Deep findings {deep_findings}/{len(findings)} < 50%. "
                f"At least 50% of findings must have description >= 200 chars."
            )
        
        # 检查confidence分布
        confidences = []
        for f in findings:
            conf = f.get("confidence")
            if conf is not None and isinstance(conf, (int, float)):
                confidences.append(float(conf))
        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            if avg_conf < 0.3:
                raise ValueError(
                    f"[Cage P1-5h] Average confidence {avg_conf:.2f} < 0.3. "
                    f"Research too speculative."
                )
        
        return self


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


# [TD4 2026-07-13] Deleted dead schemas: ArchitectureSchema, DetailedDesignSchema,
# ConsolidationSchema, HarnessReportSchema, FixLoopStateSchema (zero callers)


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
    risk_areas: list[str] = Field(default_factory=list, description="风险领域列表（从 Planning 传递到 Research）")
    expert_divergence: list[dict] = Field(default_factory=list, description="专家分歧")
    original_references: dict[str, OriginalReference] = Field(default_factory=dict, description="原始引用")
    semantic_verification: SemanticVerification = Field(description="语义等价性验证")
    gate_a_scores: dict = Field(description="Gate A 评分")
    gate_b_results: dict = Field(description="Gate B 结果")
    gate_verdict: dict = Field(description="Gate 判定")
    metadata: dict = Field(default_factory=dict, alias="_metadata", description="元数据")


class GateAScoresSchema(BaseModel):
    """Gate A 评分结构（收紧类型）"""
    score: float = Field(ge=0.0, le=1.0, description="加权总分")
    verdict: Literal["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"] = Field(description="判定结果")
    scores: dict[str, float] = Field(default_factory=dict, description="各维度原始分")
    reasoning: dict[str, str] = Field(default_factory=dict, description="各维度理由")


class GateBResultsSchema(BaseModel):
    """Gate B 结果结构（P1-9 FIX: 支持独立 Gate B 逻辑）"""
    pass_rate: float = Field(ge=0.0, le=1.0, description="通过率")
    verdict: Literal["PASS", "FAIL", "NO_EVALUATION"] = Field(
        description="判定结果 (NO_EVALUATION = no dynamic_checks configured)"
    )
    checks: list[dict] = Field(default_factory=list, description="检查项结果")
    failed_items: list = Field(
        default_factory=list,
        description="失败项 (list[str] or list[dict] with check details)"
    )


class ResearchConvergenceSchema(V2BaseSchema):
    """
    收敛点 2: Research Convergence
    
    包含：
    - research_summary: Research 摘要
    - key_findings: 关键发现
    - design_decisions: 设计决策
    - open_questions: 未解决问题
    - architecture: 方案设计引用
    - detailed_design: 详细设计引用
    - information_conservation: 信息守恒检查
    """
    module: Literal["research"] = Field(default="research")
    research_summary: str = Field(max_length=1000, description="Research 摘要（≤1000字）")
    key_findings: list[dict] = Field(description="关键发现")
    design_decisions: list[dict] = Field(description="设计决策")
    open_questions: list[dict] = Field(default_factory=list, description="未解决问题")
    architecture: dict = Field(description="方案设计引用")
    detailed_design: dict = Field(description="详细设计引用")
    information_conservation: dict = Field(description="信息守恒检查")
    original_references: dict[str, OriginalReference] = Field(default_factory=dict, description="原始引用")
    semantic_verification: SemanticVerification = Field(description="语义等价性验证")
    gate_a_scores: GateAScoresSchema = Field(description="Gate A 评分")
    gate_b_results: GateBResultsSchema = Field(description="Gate B 结果")
    gate_verdict: dict = Field(description="Gate 判定")
    metadata: dict = Field(default_factory=dict, alias="_metadata", description="元数据")


class ConstraintCoverage(BaseModel):
    """约束覆盖率统计
    
    扩展接受: 同时兼容原始字段 (total/covered/ratio/uncovered)
    和 LLM 自然产出的字段 (total_must_constraints/coverage_ratio/uncovered_constraints/verdict)
    """
    # 原始字段
    total: Optional[int] = Field(default=None, ge=0, description="总约束数")
    covered: Optional[int] = Field(default=None, ge=0, description="已覆盖约束数")
    ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="覆盖率 0-1")
    uncovered: Optional[list[str]] = Field(default=None, description="未覆盖的约束 ID 列表")
    # LLM 自然产出字段
    total_must_constraints: Optional[int] = Field(default=None, ge=0, description="MUST 优先级约束总数")
    coverage_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="约束覆盖率")
    uncovered_constraints: Optional[list[str]] = Field(default=None, description="未覆盖的约束列表")
    verdict: Optional[str] = Field(default=None, description="覆盖率判定")


class VerificationStatus(BaseModel):
    """验证状态统计
    
    扩展接受: 同时兼容原始字段 (passed/failed)
    和 LLM 自然产出的分层字段 (layer1_*/layer2_*/overall_verdict)
    """
    # 原始字段
    passed: Optional[int] = Field(default=None, ge=0, description="通过的验证项数")
    failed: Optional[int] = Field(default=None, ge=0, description="失败的验证项数")
    # Layer 1 字段
    layer1_passed: Optional[int] = Field(default=None, ge=0, description="Layer 1 通过数")
    layer1_failed: Optional[int] = Field(default=None, ge=0, description="Layer 1 失败数")
    layer1_total: Optional[int] = Field(default=None, ge=0, description="Layer 1 总数")
    layer1_pass_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Layer 1 通过率")
    # Layer 2 字段
    layer2_passed: Optional[int] = Field(default=None, ge=0, description="Layer 2 通过数")
    layer2_failed: Optional[int] = Field(default=None, ge=0, description="Layer 2 失败数")
    layer2_total: Optional[int] = Field(default=None, ge=0, description="Layer 2 总数")
    layer2_pass_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Layer 2 通过率")
    # Layer 2 语义字段（LLM 自然产出）
    layer2_p0_coverage_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Layer 2 P0 覆盖率")
    layer2_architecture_consistent: Optional[bool] = Field(default=None, description="Layer 2 架构一致性")
    layer2_guardrails_violated: Optional[list[str]] = Field(default_factory=list, description="Layer 2 违反的护栏")
    layer2_information_conservation: Optional[str] = Field(default=None, description="Layer 2 信息守恒判定")
    # 总体判定
    overall_verdict: Optional[str] = Field(default=None, description="总体验证判定")


class FinalSolutionSchema(V2BaseSchema):
    """
    Summary 模块最终输出 schema (final_solution)

    Phase 5b JSON Extractor 产出的结构化元数据。
    契约笼子：确保 final_solution 包含必要的元数据字段，
    下游消费方（如 Final Convergence）能可靠解析。
    """
    schema_version: str = Field(default="2.0.0", description="Schema 版本号")
    session_id: Optional[str] = Field(
        default=None, description="会话 ID"
    )
    constraint_coverage: Optional[ConstraintCoverage] = Field(
        default=None, description="约束覆盖率统计"
    )
    key_decisions: list[dict] = Field(
        default_factory=list, description="关键决策列表"
    )
    implementation_phases: list[dict] = Field(
        default_factory=list, description="实施阶段列表"
    )
    risk_summary: list[dict] = Field(
        default_factory=list, description="风险摘要列表"
    )
    verification_status: Optional[VerificationStatus] = Field(
        default=None, description="验证状态统计"
    )
    document_ref: str = Field(
        default="solution_document", description="关联的方案文档引用"
    )
    full_solution: Optional[Union[str, dict]] = Field(
        default=None, description="完整方案内容（支持 str 或 dict 格式）"
    )
    document_stats: Optional[dict] = Field(
        default=None, description="文档统计信息"
    )
    metadata: Optional[dict] = Field(
        default=None, description="元数据"
    )
    status: Optional[str] = Field(
        default=None, description="状态标识（如 EXTRACTION_FAILED）"
    )
    # --- Ship Pro Gate 期望字段 (V2 2026-07-13) ---
    architecture: Optional[dict] = Field(
        default_factory=dict,
        description="Solution architecture: {components: [...], design_decisions: [...]}"
    )
    covered_req_ids: list[str] = Field(
        default_factory=list, description="Covered requirement IDs"
    )
    semantic_anchors: list[dict] = Field(
        default_factory=list, description="Semantic anchors from living_spec"
    )
    conflict_resolutions: Optional[list[dict]] = Field(
        default_factory=list,
        description="Conflict resolution summaries from research_digest. "
        "Each entry: {conflict_id, description, resolution, rationale}. "
        "Optional — empty list if no conflicts in research_digest."
    )
    # --- FixFlow P1: 信息守恒增强 (2026-07-27) ---
    low_confidence_findings: Optional[list[dict]] = Field(
        default_factory=list,
        description="低置信度发现 (confidence < 0.80)，从 research_digest 提取。"
        "Each entry: {finding_id, title, confidence, reason}."
    )
    open_issues: Optional[list[dict]] = Field(
        default_factory=list,
        description="开放问题列表，从 base_solution 继承。"
        "Each entry: {issue_id, description, priority}."
    )

    @model_validator(mode='after')
    def _cage_fs1_coverage_consistency(self) -> 'FinalSolutionSchema':
        """[Cage FS1] 约束覆盖率内部一致性：covered <= total"""
        cc = self.constraint_coverage
        if cc and cc.covered is not None and cc.total is not None:
            if cc.covered > cc.total:
                raise ValueError(
                    f"[Cage FS1] constraint_coverage.covered ({cc.covered}) > total ({cc.total})"
                )
        return self

    @model_validator(mode='after')
    def _cage_fs2_failed_extraction_check(self) -> 'FinalSolutionSchema':
        """[Cage FS2] 提取失败时必须标注 status"""
        # 检查 constraint_coverage 是否为空（None 或 空对象）
        cc_empty = (
            self.constraint_coverage is None
            or (self.constraint_coverage.total in (None, 0)
                and self.constraint_coverage.covered in (None, 0))
        )
        if (
            not self.key_decisions
            and not self.implementation_phases
            and self.status is None
            and cc_empty
        ):
            raise ValueError(
                "[Cage FS2] final_solution 所有关键字段为空且未标注 status，"
                "疑似提取失败但未声明。请设置 status='EXTRACTION_FAILED'。"
            )
        return self

    @model_validator(mode='after')
    def _cage_fs3_ship_pro_gate_fields(self) -> 'FinalSolutionSchema':
        """[Cage FS3] Ship Pro Gate: 当方案有实质内容时，covered_req_ids 和 semantic_anchors 不能同时为空

        Ship Pro 实际依赖这些字段。仅当方案有实质内容（key_decisions 或 implementation_phases）
        时才触发此检查，避免对空方案或纯 status 标记误报。
        """
        if self.status == 'EXTRACTION_FAILED':
            return self
        # 仅当方案有实质内容时才检查 Ship Pro Gate 字段
        has_content = bool(self.key_decisions) or bool(self.implementation_phases)
        if has_content and not self.covered_req_ids and not self.semantic_anchors:
            raise ValueError(
                "[Cage FS3] Ship Pro Gate 期望 covered_req_ids 和 semantic_anchors 至少有一个非空。"
                "如果提取失败，请设置 status='EXTRACTION_FAILED'。"
            )
        return self



# [TD4 2026-07-13] Deleted dead schema: FinalConvergenceSchema (zero callers outside schemas module)


# ============================================================================
# 信息守恒契约
# ============================================================================

class InformationContractOutput(BaseModel):
    """信息契约输出定义"""
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="输出文件名")
    schema_def: dict = Field(alias="schema", description="JSON Schema")
    required_by: list[str] = Field(description="下游 Stage 或 Pro 名称")
    replaces: Optional[str] = Field(default=None, description="替代的旧输出")


# [TD4 2026-07-13] Deleted dead schemas: InformationContractSchema, ModuleOrchestratorStateSchema,
# TaskBuilderOutputSchema, DegradedFinalConvergenceSchema (zero callers)


# ============================================================================
# 统一验证函数
# ============================================================================

# Stage 名 → Schema 映射
STAGE_SCHEMA_MAP = {
    # Module 1: Planning
    "meta_planning": ExpertManifestSchema,
    "expert_plans": ExpertPlanSchema,
    "convergence_planning": UnifiedConstraintsSchema,
    "unified_constraints": UnifiedConstraintsSchema,
    "verification_checklist": VerificationChecklistSchema,
    
    # Module 2: Research
    "research_experts": ResearchExpertSchema,
    "research_consolidator": ResearchConsolidatorSchema,
    
    # 收敛点
    "planning_convergence": PlanningConvergenceSchema,
    "research_convergence": ResearchConvergenceSchema,
    "final_solution": FinalSolutionSchema,
    # [TD4 2026-07-13] Removed dead: FinalConvergenceSchema (zero callers)
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
    # 收敛点
    "PlanningConvergenceSchema",
    "ResearchConvergenceSchema",
    # Gate 评分结构（P0-16 收紧）
    "GateAScoresSchema",
    "GateBResultsSchema",
    # Domain categories & templates
    "DOMAIN_CATEGORIES",
    "EXPERT_TEMPLATE_REGISTRY",
    # Summary final output
    "FinalSolutionSchema",
    "ConstraintCoverage",
    "VerificationStatus",
    "HarnessCheckV2",
    # 验证函数
    "validate_stage_output",
    "get_stage_schema",
    "STAGE_SCHEMA_MAP",
]
# [TD4 2026-07-13] Removed dead schemas from __all__: ArchitectureSchema, DetailedDesignSchema,
# ConsolidationSchema, HarnessReportSchema, FixLoopStateSchema, FinalConvergenceSchema,
# ModuleOrchestratorStateSchema, TaskBuilderOutputSchema, InformationContractSchema,
# DegradedFinalConvergenceSchema
# [Phase 0a] P0-16: 收紧 ResearchConvergenceSchema gate 类型 + 新增 ModuleOrchestratorStateSchema/TaskBuilderOutputSchema


# =============================================================================
# Research Digest Schema # =============================================================================

class DigestFinding(BaseModel):
    """单个 Research Finding
    
    B3-FIX: 兼容 prompt 输出的 id/title 字段名 + schema 的 finding_id/source_reference。
    prompt 输出: id, title, confidence, relevance, design_implication
    schema 期望: finding_id, expert_id, source_reference, detail
    """
    model_config = {"populate_by_name": True}
    
    finding_id: str = Field(description="Finding ID, e.g. F-001", alias="id")
    expert_id: str = Field(default="", description="来源 Expert")
    title: str = Field(default="", description="Finding 标题")
    confidence: float = Field(ge=0.0, le=1.0, default=0.5, description="置信度 0-1")
    relevance: Literal["HIGH", "MEDIUM", "LOW"] = Field(default="MEDIUM", description="与方案的相关性")
    design_implication: str = Field(default="", description="对方案设计的启示（1-2 句话）")
    source_reference: str = Field(default="", description="来源路径 + section", alias="source")
    detail: str = Field(default="", description="完整分析文本", alias="full_text")

class ResearchDigest(BaseModel):
    """Research Digest — LLM 合成的研究发现摘要
    
    契约笼子：确保 Digest 输出格式一致，Base Synthesizer 可可靠消费。
    """
    schema_version: str = Field(default="1.0.0")
    total_findings: int = Field(default=0, description="总 Finding 数量")
    high_relevance_count: int = Field(default=0, description="HIGH relevance Finding 数量")
    expert_summaries: list[dict] = Field(
        default_factory=list,
        description="每个 Expert 的核心结论摘要 [{expert: name, summary: ...}]"
    )
    findings: list[DigestFinding] = Field(
        default_factory=list,
        description="语义去重后的 Findings 列表"
    )
    conflicts: list[dict] = Field(
        default_factory=list,
        description="Expert 间的语义矛盾 [{finding_a, finding_b, nature}]"
    )
    coverage_map: dict[str, list[str]] = Field(
        default_factory=dict,
        description="约束 → Findings 映射 {constraint_id: [finding_id, ...]}"
    )


# =============================================================================
# Harness Check — 两层防线 + 契约笼子
# =============================================================================

VerdictType = Literal["STRONG", "ADEQUATE", "WEAK", "FAIL"]

VERDICT_SCORE_MAP = {
    "STRONG": 0.95, "ADEQUATE": 0.80, "WEAK": 0.55, "FAIL": 0.25
}  # Fallback only — LLM should provide numeric scores directly


class Evidence(BaseModel):
    """双层证据"""
    structural: str = Field(description="结构性证据：section 编号 / JSON 路径 / REQ-ID")
    semantic: str = Field(description="语义性证据：为什么支持判定")


class SystemGuardrailDimension(BaseModel):
    """Layer 1: 系统级护栏维度"""
    verdict: VerdictType = Field(description="判定")
    evidence: Evidence = Field(description="双层证据")
    unhandled_requirements: list[dict] = Field(default_factory=list, description="未处理的 REQ")
    deferred_requirements: list[dict] = Field(default_factory=list, description="延迟处理的 REQ")
    beyond_spec_items: list[dict] = Field(default_factory=list, description="超出 spec 的内容")


class RoleQualityDimension(BaseModel):
    """Layer 2: 角色级质量维度"""
    verdict: VerdictType = Field(description="判定")
    sub_checks: dict = Field(description="角色化子检查项")
    evidence: Evidence = Field(description="双层证据")


class UnverifiedAssumption(BaseModel):
    """反思：未验证假设"""
    assumption: str = Field(description="假设描述")
    location: str = Field(description="引用输出中的具体位置")
    risk_if_wrong: str = Field(description="如果假设错误的后果")


class DownstreamRisk(BaseModel):
    """反思：下游风险"""
    risk_point: str = Field(description="下游可能卡住的环节")
    location: str = Field(description="引用可能导致歧义的位置")
    mitigation: str = Field(description="缓解措施")


class SkippedRequirement(BaseModel):
    """反思：跳过的需求"""
    req_id: str = Field(description="REQ-ID")
    reason: str = Field(description="跳过原因")


class ReflectionProtocol(BaseModel):
    """结构化反思协议"""
    unverified_assumptions: list[UnverifiedAssumption] = Field(description="未验证假设")
    downstream_risk: DownstreamRisk = Field(description="下游风险")
    skipped_requirements: list[SkippedRequirement] = Field(default_factory=list, description="跳过的需求")


class HarnessCheck(BaseModel):
    """
    Harness Check — 两层防线 + 契约笼子
    
    Layer 1: 系统级护栏（4 维，统一标准，不可角色化）
    Layer 2: 角色级质量检查（角色化子检查）
    Reflection: 结构化反思协议
    """
    layer1_system_guardrails: dict[str, SystemGuardrailDimension] = Field(
        description="Layer 1: completeness/necessity/alignment/global_impact"
    )
    layer2_role_quality: dict[str, RoleQualityDimension] = Field(
        default_factory=dict, description="Layer 2: 角色化子检查"
    )
    reflection: ReflectionProtocol = Field(description="结构化反思协议")
    overall_verdict: Literal["STRONG_PASS", "PASS", "CONDITIONAL", "WARNING", "FAIL"] = Field(
        description="总体判定"
    )
    layer1_verdict: Literal["PASS", "CONDITIONAL", "WARNING", "FAIL"] = Field(
        description="Layer 1 判定"
    )
    layer2_verdict: Optional[Literal["STRONG_PASS", "PASS", "CONDITIONAL_PASS", "NA"]] = Field(
        default=None, description="Layer 2 判定"
    )
    weakest_dimension: Optional[str] = Field(default=None, description="最弱维度")
    improvement_priority: list[str] = Field(default_factory=list, description="改进优先级")

    # ==================== 契约笼子 ====================

    @model_validator(mode='after')
    def _cage_h1_layer1_must_have_4_dims(self) -> 'HarnessCheck':
        """[H1] Layer 1 必须有且仅有 4 个系统级维度"""
        required = {"completeness", "necessity", "alignment", "global_impact"}
        actual = set(self.layer1_system_guardrails.keys())
        missing = required - actual
        if missing:
            raise ValueError(f"[Cage H1] Layer 1 缺少系统级维度: {missing}")
        return self

    @model_validator(mode='after')
    def _cage_h2_p0_red_line(self) -> 'HarnessCheck':
        """[H2] P0 需求遗漏 = FAIL 硬红线"""
        completeness = self.layer1_system_guardrails.get("completeness")
        if completeness and completeness.verdict == "FAIL":
            # 检查是否有 P0 在 unhandled 中
            p0_unhandled = [r for r in completeness.unhandled_requirements 
                          if r.get("priority") == "P0" or r.get("level") == "P0"]
            if p0_unhandled:
                # 这是合理的 FAIL，不 raise
                pass
        return self

    @model_validator(mode='after')
    def _cage_h3_layer1_aggregation(self) -> 'HarnessCheck':
        """[H3] Layer 1 分层聚合规则"""
        verdicts = [d.verdict for d in self.layer1_system_guardrails.values()]
        
        fail_count = verdicts.count("FAIL")
        weak_count = verdicts.count("WEAK")
        
        # 规则 1: 任何 FAIL → overall = FAIL
        if fail_count > 0 and self.overall_verdict not in ["FAIL", "WARNING"]:
            raise ValueError(
                f"[Cage H3] Layer 1 有 FAIL 维度，overall_verdict 必须是 FAIL/WARNING，"
                f"实际: {self.overall_verdict}"
            )
        
        # 规则 2: 2+ WEAK → FAIL
        if weak_count >= 2 and self.overall_verdict not in ["FAIL", "WARNING"]:
            raise ValueError(
                f"[Cage H3] Layer 1 有 {weak_count} 个 WEAK 维度（2+ → FAIL），"
                f"overall_verdict 必须是 FAIL/WARNING，实际: {self.overall_verdict}"
            )
        
        # 规则 3: 1 WEAK → 至少 CONDITIONAL
        if weak_count == 1 and self.overall_verdict in ["STRONG_PASS", "PASS"]:
            raise ValueError(
                f"[Cage H3] Layer 1 有 1 个 WEAK 维度，overall_verdict 不能是 PASS/STRONG_PASS，"
                f"实际: {self.overall_verdict}"
            )
        
        return self

    @model_validator(mode='after')
    def _cage_h4_layer2_cannot_compensate(self) -> 'HarnessCheck':
        """[H4] Layer 1 WEAK/FAIL 不可被 Layer 2 补偿"""
        layer1_verdicts = [d.verdict for d in self.layer1_system_guardrails.values()]
        
        # 如果 Layer 1 有 WEAK 或 FAIL，overall 不能是 STRONG_PASS
        if any(v in ["WEAK", "FAIL"] for v in layer1_verdicts):
            if self.overall_verdict == "STRONG_PASS":
                raise ValueError(
                    "[Cage H4] Layer 1 有 WEAK/FAIL 维度，overall_verdict 不能是 STRONG_PASS"
                )
        
        return self

    @model_validator(mode='after')
    def _cage_h5_anti_complacency(self) -> 'HarnessCheck':
        """[H5] 反自满：禁止所有维度都给 STRONG"""
        layer1_verdicts = [d.verdict for d in self.layer1_system_guardrails.values()]
        
        if all(v == "STRONG" for v in layer1_verdicts):
            # 如果所有维度都是 STRONG，必须有特殊的 justification
            # 检查 reflection 中是否有说明
            has_justification = False
            for assumption in self.reflection.unverified_assumptions:
                if "全部覆盖" in assumption.assumption or "无遗漏" in assumption.assumption:
                    # 这种假设需要有高风险说明
                    if "HIGH" in assumption.risk_if_wrong.upper() or "严重" in assumption.risk_if_wrong:
                        has_justification = True
            
            if not has_justification:
                # 不是 raise，而是强制降级
                if self.overall_verdict == "STRONG_PASS":
                    raise ValueError(
                        "[Cage H5] 所有维度都给 STRONG 需要高风险 justification。"
                        "请在 reflection.unverified_assumptions 中说明，"
                        "或将 overall_verdict 降级为 PASS。"
                    )
        
        return self

    @model_validator(mode='after')
    def _cage_h6_reflection_not_evasive(self) -> 'HarnessCheck':
        """[H6] 反思不能敷衍"""
        evasive_phrases = [
            "没有问题", "一切完备", "全部通过", "没有遗漏",
            "完美", "无需改进", "已完全覆盖"
        ]
        
        # 检查 unverified_assumptions
        for assumption in self.reflection.unverified_assumptions:
            text = assumption.assumption.lower()
            if any(phrase in text for phrase in evasive_phrases):
                raise ValueError(
                    f"[Cage H6] 反思不能敷衍: '{assumption.assumption}' "
                    f"包含敷衍短语。必须引用具体位置和真实风险。"
                )
        
        # 检查 downstream_risk
        risk_text = self.reflection.downstream_risk.risk_point.lower()
        if any(phrase in risk_text for phrase in evasive_phrases):
            raise ValueError(
                f"[Cage H6] 下游风险不能敷衍: '{self.reflection.downstream_risk.risk_point}' "
                f"必须引用具体位置和缓解措施。"
            )
        
        return self

    @model_validator(mode='after')
    def _cage_h7_reflection_mandatory(self) -> 'HarnessCheck':
        """[H7] 反思必须有内容"""
        if not self.reflection.unverified_assumptions:
            raise ValueError(
                "[Cage H7] reflection.unverified_assumptions 不能为空。"
                "必须列出至少 1 个未验证假设。"
            )
        
        if not self.reflection.downstream_risk.risk_point:
            raise ValueError(
                "[Cage H7] reflection.downstream_risk.risk_point 不能为空。"
            )
        
        return self

    @model_validator(mode='after')
    def _cage_h8_necessity_beyond_spec(self) -> 'HarnessCheck':
        """[H8] necessity: 超出 spec 的内容必须标注为 suggestion"""
        necessity = self.layer1_system_guardrails.get("necessity")
        if necessity and necessity.beyond_spec_items:
            for item in necessity.beyond_spec_items:
                item_type = item.get("type", "")
                if item_type not in ["suggestion", "recommendation", "optional"]:
                    if necessity.verdict == "STRONG":
                        raise ValueError(
                            f"[Cage H8] necessity 有超出 spec 的内容 '{item.get('item', '?')}' "
                            f"但未标注为 suggestion/recommendation/optional。"
                            f"当存在未标注的超出 spec 内容时，verdict 不能是 STRONG。"
                        )
        return self


# V2 别名 — harness_scorer.py 和 task_builder.py 使用 HarnessCheckV2 引用
HarnessCheckV2 = HarnessCheck


def validate_harness_check(data: dict) -> tuple[bool, str]:
    """验证 Harness Check 输出"""
    try:
        HarnessCheck(**data)
        return True, ""
    except Exception as e:
        return False, str(e)


def verdict_to_score(verdict: VerdictType) -> float:
    """定性标签 → 数值映射（供 Gate A Layer 2 使用）"""
    return VERDICT_SCORE_MAP.get(verdict, 0.50)
