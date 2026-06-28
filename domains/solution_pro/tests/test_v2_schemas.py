"""
Solution Pro V2 Schema 测试

Version: 1.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

描述:
- 测试所有 V2 Schema 的验证逻辑
- 测试 validate_stage_output() 函数
- 测试 Gate A 权重和验证
"""

import pytest
import sys
from pathlib import Path

# 添加 .deepflow 到 Python 路径
deepflow_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(deepflow_root))

from domains.solution_pro.schemas.v2_schemas import (
    ExpertManifestSchema,
    ExpertPlanSchema,
    UnifiedConstraintsSchema,
    VerificationChecklistSchema,
    PlanningConvergenceSchema,
    GateAWeights,
    DynamicCheck,
    validate_stage_output,
    get_stage_schema,
)


class TestGateAWeights:
    """测试 Gate A 权重验证"""
    
    def test_valid_weights_sum_to_one(self):
        """权重和 = 1.0 应该通过验证"""
        weights = GateAWeights(
            completeness=0.3,
            necessity=0.2,
            alignment=0.3,
            global_impact=0.2,
        )
        assert weights.completeness == 0.3
        assert weights.necessity == 0.2
        assert weights.alignment == 0.3
        assert weights.global_impact == 0.2
    
    def test_invalid_weights_sum_not_one(self):
        """权重和 ≠ 1.0 应该抛出 ValueError"""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            GateAWeights(
                completeness=0.3,
                necessity=0.3,
                alignment=0.3,
                global_impact=0.3,  # 总和 = 1.2
            )
    
    def test_weights_boundary_zero(self):
        """权重 = 0.0 应该通过（允许某维度权重为 0）"""
        weights = GateAWeights(
            completeness=0.0,
            necessity=0.0,
            alignment=1.0,
            global_impact=0.0,
        )
        assert weights.alignment == 1.0
    
    def test_weights_range_validation(self):
        """权重必须在 [0.0, 1.0] 范围内"""
        with pytest.raises(ValueError):
            GateAWeights(
                completeness=1.5,  # 超出范围
                necessity=0.0,
                alignment=0.0,
                global_impact=0.0,
            )


class TestExpertManifestSchema:
    """测试 ExpertManifestSchema"""
    
    def test_valid_manifest(self):
        """有效的 Meta-Planner 输出"""
        manifest = ExpertManifestSchema(
            task_profile={
                "domain": "backend_api",
                "complexity": "high",
                "risk_areas": ["security", "scalability"],
            },
            experts=[
                {
                    "expert_name": "security_expert",
                    "domain": "Security",
                    "focus_areas": ["OWASP Top 10", "authentication"],
                    "evaluation_lens": "从安全漏洞角度审视每个设计决策",
                },
                {
                    "expert_name": "performance_expert",
                    "domain": "Performance",
                    "focus_areas": ["latency", "throughput"],
                    "evaluation_lens": "从性能瓶颈角度审视每个设计决策",
                },
            ],
            gate_a={
                "weights": {
                    "completeness": 0.3,
                    "necessity": 0.2,
                    "alignment": 0.3,
                    "global_impact": 0.2,
                },
                "thresholds": {
                    "PASS": 0.85,
                    "WARNING": 0.70,
                    "CRITICAL_WARNING": 0.60,
                    "BLOCK_RECOMMENDATION": 0.0,
                },
                "rationale": "高风险任务，强调完整性和目标一致性",
            },
            gate_b={
                "dynamic_checks": [
                    {
                        "name": "security_audit",
                        "description": "安全审计检查",
                        "pass_criteria": "无高危漏洞",
                        "severity": "CRITICAL",
                        "reasoning": "安全是 P0 需求",
                    },
                ],
            },
            verdict_policy={
                "warning_acceptable": False,
                "min_gate_b_pass_rate": 0.8,
            },
        )
        
        assert manifest.task_profile["domain"] == "backend_api"
        assert len(manifest.experts) == 2
        assert manifest.gate_a.weights.completeness == 0.3
    
    def test_expert_count_validation(self):
        """专家数量必须在 [1, 5] 范围内"""
        # 0 个专家应该失败
        with pytest.raises(ValueError):
            ExpertManifestSchema(
                task_profile={"domain": "test", "complexity": "low"},
                experts=[],  # 空列表
                gate_a={
                    "weights": {"completeness": 1.0, "necessity": 0.0, "alignment": 0.0, "global_impact": 0.0},
                    "rationale": "test",
                },
                gate_b={"dynamic_checks": []},
            )
        
        # 6 个专家应该失败
        with pytest.raises(ValueError):
            ExpertManifestSchema(
                task_profile={"domain": "test", "complexity": "low"},
                experts=[
                    {"expert_name": f"expert_{i}", "domain": "test", "focus_areas": [], "evaluation_lens": "test"}
                    for i in range(6)
                ],
                gate_a={
                    "weights": {"completeness": 1.0, "necessity": 0.0, "alignment": 0.0, "global_impact": 0.0},
                    "rationale": "test",
                },
                gate_b={"dynamic_checks": []},
            )


class TestExpertPlanSchema:
    """测试 ExpertPlanSchema"""
    
    def test_valid_expert_plan(self):
        """有效的 Expert Planner 输出"""
        plan = ExpertPlanSchema(
            expert_name="security_expert",
            constraints=[
                {
                    "constraint_id": "C-001",
                    "description": "所有 API 必须使用 HTTPS",
                    "priority": "MUST",
                    "rationale": "防止中间人攻击",
                },
                {
                    "constraint_id": "C-002",
                    "description": "密码必须使用 bcrypt 加密",
                    "priority": "MUST",
                    "rationale": "防止密码泄露",
                },
            ],
            risks=[
                {
                    "risk_id": "R-001",
                    "description": "SQL 注入风险",
                    "mitigation": "使用参数化查询",
                },
            ],
            acceptance_criteria=[
                {
                    "criterion_id": "AC-001",
                    "description": "通过 OWASP ZAP 扫描",
                    "verification_method": "运行 OWASP ZAP 扫描，无高危漏洞",
                },
            ],
            covered_req_ids=["REQ-P0-001"],
        )
        
        assert plan.expert_name == "security_expert"
        assert len(plan.constraints) == 2
        assert plan.constraints[0].priority == "MUST"
        assert "REQ-P0-001" in plan.covered_req_ids
    
    def test_minimum_constraints_required(self):
        """至少需要 1 个约束"""
        with pytest.raises(ValueError):
            ExpertPlanSchema(
                expert_name="test",
                constraints=[],  # 空列表
                acceptance_criteria=[
                    {"criterion_id": "AC-001", "description": "test", "verification_method": "test"}
                ],
            )


class TestUnifiedConstraintsSchema:
    """测试 UnifiedConstraintsSchema"""
    
    def test_valid_unified_constraints(self):
        """有效的 Convergence Planner 输出"""
        constraints = UnifiedConstraintsSchema(
            unified_constraints=[
                {
                    "constraint_id": "UC-001",
                    "description": "所有 API 必须使用 HTTPS",
                    "priority": "MUST",
                    "source_experts": ["security_expert"],
                    "conflicts_resolved": [],
                },
                {
                    "constraint_id": "UC-002",
                    "description": "响应时间 < 200ms",
                    "priority": "SHOULD",
                    "source_experts": ["performance_expert", "scalability_expert"],
                    "conflicts_resolved": ["performance_expert 要求 100ms，scalability_expert 要求 500ms，取折中值 200ms"],
                },
            ],
            rejected_constraints=[
                {
                    "constraint_id": "RC-001",
                    "description": "使用 GraphQL",
                    "reason": "与现有 REST API 不兼容",
                },
            ],
            meta={
                "total_expert_plans": 3,
                "total_input_constraints": 15,
                "total_output_constraints": 2,
                "merge_ratio": 0.13,
            },
            covered_req_ids=["REQ-P0-001", "REQ-P0-002"],
        )
        
        assert len(constraints.unified_constraints) == 2
        assert constraints.meta["merge_ratio"] == 0.13
        assert len(constraints.rejected_constraints) == 1


class TestValidateStageOutput:
    """测试 validate_stage_output() 函数"""
    
    def test_validate_valid_meta_planning(self):
        """验证有效的 Meta-Planner 输出"""
        data = {
            "task_profile": {
                "domain": "backend_api",
                "complexity": "medium",
                "risk_areas": ["security"],
            },
            "experts": [
                {
                    "expert_name": "security_expert",
                    "domain": "Security",
                    "focus_areas": ["OWASP"],
                    "evaluation_lens": "安全视角",
                },
            ],
            "gate_a": {
                "weights": {
                    "completeness": 0.25,
                    "necessity": 0.25,
                    "alignment": 0.25,
                    "global_impact": 0.25,
                },
                "rationale": "均衡权重",
            },
            "gate_b": {
                "dynamic_checks": [],
            },
        }
        
        is_valid, error = validate_stage_output("meta_planning", data)
        assert is_valid is True
        assert error == ""
    
    def test_validate_invalid_stage_name(self):
        """验证未知的 Stage 名称"""
        is_valid, error = validate_stage_output("unknown_stage", {})
        assert is_valid is False
        assert "Unknown stage" in error
    
    def test_validate_invalid_data(self):
        """验证无效的数据"""
        data = {
            "task_profile": "invalid",  # 应该是 dict
            "experts": [],  # 空列表
            "gate_a": {},
            "gate_b": {},
        }
        
        is_valid, error = validate_stage_output("meta_planning", data)
        assert is_valid is False
        assert error != ""


class TestGetStageSchema:
    """测试 get_stage_schema() 函数"""
    
    def test_get_known_schema(self):
        """获取已知 Stage 的 Schema"""
        schema = get_stage_schema("meta_planning")
        assert schema == ExpertManifestSchema
    
    def test_get_unknown_schema(self):
        """获取未知 Stage 的 Schema"""
        schema = get_stage_schema("unknown_stage")
        assert schema is None


class TestPlanningConvergenceSchema:
    """测试 PlanningConvergenceSchema"""
    
    def test_valid_planning_convergence(self):
        """有效的 Planning 收敛点输出"""
        convergence = PlanningConvergenceSchema(
            unified_constraints=[
                {
                    "constraint_id": "UC-001",
                    "description": "使用 HTTPS",
                    "priority": "MUST",
                },
            ],
            verification_checklist=[
                {
                    "check_id": "VC-001",
                    "constraint_id": "UC-001",
                    "verification_method": "检查 API 文档",
                    "expected_result": "所有端点使用 HTTPS",
                },
            ],
            planning_summary="Planning 摘要：设计了安全的后端 API",
            expert_divergence=[],
            original_references={},
            semantic_verification={
                "verdict": "EQUIVALENT",
                "confidence": 0.95,
                "divergences": [],
            },
            gate_a_scores={"score": 0.9, "verdict": "PASS"},
            gate_b_results={"pass_rate": 1.0, "verdict": "PASS"},
            gate_verdict={"final_verdict": "PASS"},
            metadata={"module": "planning", "stage_count": 5},
        )
        
        assert convergence.module == "planning"
        assert convergence.semantic_verification.verdict == "EQUIVALENT"
        assert convergence.gate_verdict["final_verdict"] == "PASS"
    
    def test_semantic_verification_verdicts(self):
        """测试语义验证的三种判定"""
        for verdict in ["EQUIVALENT", "PARTIAL", "NOT_EQUIVALENT"]:
            convergence = PlanningConvergenceSchema(
                unified_constraints=[],
                verification_checklist=[],
                planning_summary="test",
                semantic_verification={
                    "verdict": verdict,
                    "confidence": 0.8,
                    "divergences": [],
                },
                gate_a_scores={},
                gate_b_results={},
                gate_verdict={},
            )
            assert convergence.semantic_verification.verdict == verdict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
