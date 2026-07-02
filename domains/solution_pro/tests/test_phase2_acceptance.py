"""
Phase 2 Acceptance Tests — Solution Pro V2

Tests for:
- ResearchOrchestrator (Phase 2.1)
- ReviewQCOrchestrator (Phase 2.2)
- ConvergenceLayer migration (Phase 2.3)
- ComplianceChecker (Phase 2.4)
- InformationConservationValidator (Phase 2.5)

All tests use mocks — no LLM calls, no file I/O beyond BlackboardManager.
"""

import json
import threading
import uuid
import pytest
from unittest.mock import MagicMock, patch

from domains.solution_pro.research_orchestrator import ResearchOrchestrator, SourceRegistry
from domains.solution_pro.review_qc_orchestrator import ReviewQCOrchestrator
from domains.solution_pro.convergence_layer import ConvergenceLayer
from domains.solution_pro.compliance_checker import (
    ComplianceChecker,
    CheckResult,
    ComplianceReport,
    THRESHOLD_PASS,
    THRESHOLD_WARNING,
)
from domains.solution_pro.information_conservation import InformationConservationValidator
from domains.solution_pro.schemas.schemas import DegradedFinalConvergenceSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_planning_output():
    """Minimal planning output fixture."""
    return {
        "schema_version": "1.0.0",
        "structured_requirements": {
            "requirements": [
                {"req_id": "REQ-001", "priority": "P0", "description": "Core auth"},
                {"req_id": "REQ-002", "priority": "P0", "description": "Data persistence"},
                {"req_id": "REQ-003", "priority": "P1", "description": "Nice-to-have UI"},
            ]
        },
        "unified_constraints": {
            "constraints": [
                {"constraint_id": "C-001", "description": "Latency < 100ms", "priority": "MUST", "source_experts": ["security"]},
                {"constraint_id": "C-002", "description": "Encrypt at rest", "priority": "MUST", "source_experts": ["security", "compliance"]},
            ]
        },
        "planning_summary": {"domain": "backend_api", "risk_areas": ["security", "performance"]},
        "risk_areas": [
            {"name": "security", "focus_areas": ["auth", "encryption"], "lens": "security lens"},
            {"name": "performance", "focus_areas": ["latency"], "lens": "performance lens"},
        ],
    }


def _make_frozen_spec():
    return {
        "schema_version": "1.0.0",
        "topic": "Test Project",
        "domain": "backend_api",
        "solution_type": "api",
        "p0_req_ids": ["REQ-001", "REQ-002"],
    }


# ===========================================================================
# TestPhase2Acceptance
# ===========================================================================

class TestPhase2Acceptance:
    """Phase 2 验收测试"""

    # === ResearchOrchestrator ===

    def test_research_orchestrator_init(self):
        """验证 ResearchOrchestrator 初始化"""
        ro = ResearchOrchestrator(session_id="test-session-001")
        assert ro.module_name == "research"
        assert ro.session_id == "test-session-001"
        assert isinstance(ro.source_registry, SourceRegistry)

    def test_research_stage_sequence(self):
        """验证 5 个 stage 序列"""
        ro = ResearchOrchestrator(session_id="test-session-002")
        stages = ro.stage_sequence()
        assert len(stages) == 5
        names = [s["name"] for s in stages]
        assert names == [
            "knowledge_freshness",
            "expert_config_determination",
            "research_experts_parallel",
            "consolidation",
            "research_convergence",
        ]

    def test_source_registry_thread_safety(self):
        """验证 SourceRegistry 线程安全"""
        registry = SourceRegistry()
        errors = []

        def register_batch(expert_name, count):
            try:
                sources = [{"url": f"https://example.com/{expert_name}/{i}", "title": f"T{i}", "quality": "high"} for i in range(count)]
                registry.register(expert_name, sources)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_batch, args=(f"expert_{i}", 20)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        summary = registry.summary()
        assert summary["total_experts"] == 10
        assert summary["total_sources"] == 200  # 10 experts × 20 sources, all unique URLs

    def test_research_expert_config_dynamic(self):
        """验证动态 Expert 配置（从 risk_areas 生成）"""
        ro = ResearchOrchestrator(session_id="test-session-004")
        planning_output = _make_planning_output()
        frozen_spec = _make_frozen_spec()

        configs = ro._determine_expert_configs(planning_output, frozen_spec)
        # Should have 2 risk area experts + 1 generalist
        assert len(configs) == 3
        expert_names = [c["expert_name"] for c in configs]
        assert "security_expert" in expert_names
        assert "performance_expert" in expert_names
        assert "generalist_expert" in expert_names

    # === ReviewQCOrchestrator ===

    def test_review_qc_orchestrator_init(self):
        """验证 ReviewQCOrchestrator 初始化"""
        rq = ReviewQCOrchestrator(session_id="test-session-010")
        assert rq.module_name == "review_qc"
        assert rq.session_id == "test-session-010"
        assert rq.MAX_FIX_ROUNDS == 3

    def test_review_qc_stage_sequence(self):
        """验证 4 个 stage 序列"""
        rq = ReviewQCOrchestrator(session_id="test-session-011")
        stages = rq.stage_sequence()
        assert len(stages) == 4
        names = [s["name"] for s in stages]
        assert names == ["fix_loop", "harness_check", "final_review", "review_qc_convergence"]

    def test_fix_loop_pass(self):
        """验证 Fix Loop PASS 路径"""
        rq = ReviewQCOrchestrator(session_id="test-session-012")
        planning_output = _make_planning_output()
        # Research output that covers all P0 reqs and constraints
        research_output = {
            "covered_req_ids": ["REQ-001", "REQ-002"],
            "C-001": "latency handled",
            "C-002": "encryption handled",
        }
        result = rq._run_fix_loop(planning_output, research_output)
        assert result["status"] in ("PASS", "MAX_ROUNDS")

    def test_fix_loop_abort_degradation(self):
        """验证 Fix Loop ABORT 降级"""
        rq = ReviewQCOrchestrator(session_id="test-session-013")
        fix_result = {
            "status": "ABORT",
            "round": 2,
            "abort_reason": "Unfixable constraint violation",
            "partial_outputs": [{"partial": True}],
            "diagnosis": "Cannot resolve conflicting constraints",
        }
        degraded = rq._handle_abort_degradation(fix_result)
        assert degraded["status"] == "DEGRADED"
        assert degraded["degradation_flag"] is True
        assert degraded["degradation_reason"] == "Unfixable constraint violation"

    def test_degraded_final_convergence_schema(self):
        """验证 DegradedFinalConvergenceSchema"""
        data = {
            "degradation_reason": "test failure",
            "partial_results": [{"step": 1}],
            "quality_scores": {"degraded": True, "score": 0.0},
            "fix_loop_summary": {"abort_round": 1, "failure_diagnosis": "test"},
        }
        schema = DegradedFinalConvergenceSchema(**data)
        assert schema.status == "DEGRADED"
        assert schema.degradation_flag is True
        assert schema.schema_version == "degraded_final_v1"

    # === ConvergenceLayer 迁移 ===

    def test_converge_module_research(self):
        """验证 Research 模块收敛"""
        mock_bb = MagicMock()
        cl = ConvergenceLayer(module_name="research", blackboard=mock_bb)
        stage_outputs = [
            {"findings": [{"id": "F1", "description": "finding 1"}], "risks": []},
            {"findings": [{"id": "F2", "description": "finding 2"}], "constraints": ["C1"]},
        ]
        result = cl.converge_module("research", stage_outputs)
        assert result["module"] == "research"
        assert result["status"] == "COMPLETE"
        assert "overall_verdict" in result
        assert "gate_a" in result
        assert "gate_b" in result

    def test_converge_module_review_qc(self):
        """验证 Review/QC 模块收敛"""
        mock_bb = MagicMock()
        cl = ConvergenceLayer(module_name="review_qc", blackboard=mock_bb)
        stage_outputs = [
            {"findings": [{"id": "F1"}], "risks": [{"id": "R1"}]},
        ]
        result = cl.converge_module("review_qc", stage_outputs)
        assert result["module"] == "review_qc"
        assert result["status"] == "COMPLETE"

    # === ComplianceChecker ===

    def test_compliance_checker_init(self):
        """验证 ComplianceChecker 初始化"""
        cc = ComplianceChecker()
        assert cc.llm_judge_fn is None
        assert len(cc.checkers) == 5
        assert "D1_D11" in cc.checkers
        assert "D3" in cc.checkers
        assert "D4" in cc.checkers
        assert "D5" in cc.checkers
        assert "D8" in cc.checkers

    def test_compliance_layer1_checks(self):
        """验证 Layer 1 代码检查"""
        cc = ComplianceChecker()
        good_output = {
            "schema_version": "2.0",
            "constraints": ["latency < 100ms"],
            "source": "frozen_spec",
            "req_ids": ["REQ-001"],
        }
        results = cc._run_layer1_checks(good_output)
        assert results["has_schema_version"].passed is True
        assert results["has_constraints"].passed is True
        assert results["has_source_citations"].passed is True
        assert results["no_empty_fields"].passed is True
        assert results["req_ids_format"].passed is True

    def test_compliance_layer2_with_llm(self):
        """验证 Layer 2 LLM 检查"""
        def mock_llm(prompt, temperature):
            return {"score": 0.9, "reasoning": "All good"}

        cc = ComplianceChecker(llm_judge_fn=mock_llm)
        output = {"schema_version": "2.0", "constraints": [], "confidence": 0.9}
        results = cc._run_layer2_checks(output, None)
        assert len(results) == 5
        for name, result in results.items():
            assert isinstance(result, CheckResult)
            assert result.score == 0.9

    def test_compliance_layer2_fallback(self):
        """验证 Layer 2 无 LLM 时的 fallback"""
        cc = ComplianceChecker(llm_judge_fn=None)
        output = {
            "schema_version": "2.0",
            "constraints": [],
            "confidence": 0.8,
            "risk": "some risk",
        }
        results = cc._run_layer2_checks(output, None)
        for name, result in results.items():
            assert isinstance(result, CheckResult)
            assert result.detail == "rule_based_fallback"

    def test_compliance_three_tier_verdict(self):
        """验证三级判定（PASS/WARNING/FAIL）"""
        # PASS
        assert ComplianceChecker._determine_verdict(0.85) == "PASS"
        assert ComplianceChecker._determine_verdict(0.80) == "PASS"
        # WARNING
        assert ComplianceChecker._determine_verdict(0.50) == "WARNING"
        assert ComplianceChecker._determine_verdict(0.79) == "WARNING"
        # FAIL
        assert ComplianceChecker._determine_verdict(0.49) == "FAIL"
        assert ComplianceChecker._determine_verdict(0.0) == "FAIL"

    # === InformationConservation ===

    def test_info_conservation_init(self):
        """验证 InformationConservationValidator 初始化"""
        icv = InformationConservationValidator()
        assert hasattr(icv, "validate")
        assert hasattr(icv, "_check_req_coverage")
        assert hasattr(icv, "_check_constraint_propagation")
        assert hasattr(icv, "_check_source_traceability")

    def test_info_conservation_full_coverage(self):
        """验证 100% 需求覆盖"""
        icv = InformationConservationValidator()
        planning = _make_planning_output()
        research = {"REQ-001": "covered", "REQ-002": "covered", "C-001": "propagated", "C-002": "propagated"}
        review_qc = {"REQ-001": "final", "REQ-002": "final"}
        result = icv.validate(planning, research, review_qc)
        assert result["verdict"] == "PASS"
        assert result["req_coverage"]["rate"] == 1.0
        assert result["constraint_propagation"]["rate"] == 1.0

    def test_info_conservation_safety_floor(self):
        """验证安全底线（req_coverage < 0.5 → FAIL）"""
        icv = InformationConservationValidator()
        planning = _make_planning_output()
        # Only 1 of 2 P0 reqs covered → rate = 0.5, not < 0.5
        research_partial = {"REQ-001": "covered"}
        review_qc = {}
        result = icv.validate(planning, research_partial, review_qc)
        # rate = 0.5, not < 0.5, so safety floor not triggered
        # But score should be low
        assert result["req_coverage"]["rate"] == 0.5

        # Now test with 0 P0 reqs covered → rate = 0.0 < 0.5 → forced FAIL
        research_empty = {"nothing": "here"}
        result2 = icv.validate(planning, research_empty, review_qc)
        assert result2["req_coverage"]["rate"] == 0.0
        assert result2["verdict"] == "FAIL"

    # === 端到端 ===

    def test_research_convergence_generation(self):
        """验证 Research 收敛文件生成"""
        ro = ResearchOrchestrator(session_id=f"test-research-conv-{uuid.uuid4().hex[:8]}")
        consolidated = {
            "schema_version": "1.0.0",
            "consolidated_findings": [{"description": "F1", "tier": 1}],
            "consensus_points": ["point1"],
            "divergence_points": [],
            "consolidated_risks": [{"description": "R1", "tier": 1}],
            "consolidated_recommendations": [{"description": "REC1", "tier": 1}],
            "source_registry_summary": {"total_experts": 2, "total_sources": 5},
            "expert_count": 2,
            "total_input_findings": 4,
            "total_input_risks": 2,
            "total_input_recommendations": 2,
            "covered_req_ids": ["REQ-001"],
        }
        expert_outputs = [
            {"expert_name": "security_expert", "findings": [{"finding_id": "F1"}], "iteration": 1},
            {"expert_name": "performance_expert", "findings": [{"finding_id": "F2"}], "iteration": 1},
        ]
        convergence = ro._generate_research_convergence(consolidated, expert_outputs)
        assert convergence["module"] == "research"
        assert "research_summary" in convergence
        assert "information_conservation" in convergence
        assert "semantic_verification" in convergence
        assert "gate_verdict" in convergence
        assert convergence["_metadata"]["expert_count"] == 2

    def test_review_qc_convergence_generation(self):
        """验证 Review/QC 收敛文件生成"""
        rq = ReviewQCOrchestrator(session_id=f"test-reviewqc-conv-{uuid.uuid4().hex[:8]}")
        final_review = {
            "harness_result": {
                "fix_result": {"round": 1, "status": "PASS"},
                "harness_output": {"status": "PASS", "score": 0.9},
            },
            "final_review": {"verdict": "PASS", "quality_score": 0.9},
        }
        convergence = rq._generate_review_qc_convergence(final_review)
        assert convergence["module"] == "review_qc"
        assert convergence["status"] == "COMPLETE"
        assert convergence["final_verdict"] == "PASS"
        assert convergence["quality_score"] == 0.9
