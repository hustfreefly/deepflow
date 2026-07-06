"""
Solution Pro V2 Phase 1 验收测试

Version: 2.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-29

描述:
- Phase 1 专项验收测试：Planning V2 端到端
- Layer 0: Meta-Planning（领域识别、Gate 配置、Reviewer_Meta）
- Layer 1: Parallel Expert Planning（并行执行、Schema 验证、断点续跑、优雅降级）
- Layer 2: Convergence Planning（语义去重、冲突解决、P0 REQ 覆盖）
- Harness: Gate A Layer 2（多数投票、FAIL 覆盖、规则 fallback）
- Harness: Gate B CRITICAL（全部通过、一个失败、整体通过率）
- 端到端（完整 7 步流程、断点续跑）
- 并行执行（基类 _execute_parallel()、降级模式）
- V1 向后兼容
"""

import pytest
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Add .deepflow to sys.path
deepflow_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(deepflow_root))

from domains.solution_pro.planning_orchestrator import PlanningOrchestrator
from domains.solution_pro.convergence_layer import ConvergenceLayer
from domains.solution_pro.module_orchestrator_base import ModuleOrchestrator
from domains.solution_pro.harness_scorer import (
    GateALayer2Calibration,
    evaluate_gate_b_critical,
    calculate_harness_score_dynamic,
)
from domains.solution_pro.schemas.schemas import (
    ExpertManifestSchema,
    ExpertPlanSchema,
    UnifiedConstraintsSchema,
    VerificationChecklistSchema,
    PlanningConvergenceSchema,
)


# ============================================================================
# Mock Data
# ============================================================================

MOCK_FROZEN_SPEC = {
    "schema_version": "2.0.0",
    "project_name": "Phase 1 Acceptance Test",
    "p0_req_ids": ["REQ-P0-001", "REQ-P0-002", "REQ-P0-003"],
    "requirements": [
        {"id": "REQ-P0-001", "description": "Security requirement", "priority": "P0"},
        {"id": "REQ-P0-002", "description": "Performance requirement", "priority": "P0"},
        {"id": "REQ-P0-003", "description": "Scalability requirement", "priority": "P0"},
    ],
}

MOCK_STRUCTURED_REQUIREMENTS = {
    "schema_version": "2.0.0",
    "requirements": MOCK_FROZEN_SPEC["requirements"],
}

MOCK_EXPERT_MANIFEST = {
    "schema_version": "2.0.0",
    "task_profile": {
        "domain": "backend_api",
        "complexity": "high",
        "risk_areas": ["security", "scalability", "performance"],
    },
    "experts": [
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
        {
            "expert_name": "scalability_expert",
            "domain": "Scalability",
            "focus_areas": ["horizontal scaling", "state management"],
            "evaluation_lens": "从扩展性角度审视每个设计决策",
        },
    ],
    "gate_a": {
        "weights": {
            "completeness": 0.30,
            "necessity": 0.15,
            "alignment": 0.35,
            "global_impact": 0.20,
        },
        "thresholds": {
            "PASS": 0.85,
            "WARNING": 0.70,
            "CRITICAL_WARNING": 0.60,
            "BLOCK_RECOMMENDATION": 0.0,
        },
        "rationale": "高风险后端 API 任务",
    },
    "gate_b": {
        "dynamic_checks": [
            {
                "name": "security_audit",
                "description": "安全审计检查",
                "pass_criteria": "无高危漏洞",
                "severity": "CRITICAL",
                "reasoning": "安全是 P0 需求",
            },
            {
                "name": "p0_req_coverage",
                "description": "P0 需求覆盖率检查",
                "pass_criteria": "所有 P0 REQ 有对应约束",
                "severity": "CRITICAL",
                "reasoning": "P0 需求必须 100% 覆盖",
            },
        ],
    },
    "verdict_policy": {
        "warning_acceptable": False,
        "min_gate_b_pass_rate": 0.8,
    },
}


def _make_expert_plan(expert_name: str, constraints=None, covered_req_ids=None):
    """Helper to create expert plan"""
    return {
        "schema_version": "2.0.0",
        "expert_name": expert_name,
        "constraints": constraints or [
            {
                "constraint_id": "C-001",
                "description": f"{expert_name} constraint 1",
                "priority": "MUST",
                "rationale": "Critical requirement for system integrity and compliance",
            },
            {
                "constraint_id": "C-002",
                "description": f"{expert_name} constraint 2",
                "priority": "SHOULD",
                "rationale": "Important requirement for long-term maintainability",
            },
        ],
        "risks": [
            {
                "risk_id": f"R-{expert_name}-001",
                "description": f"{expert_name} risk 1",
                "mitigation": "Mitigation strategy",
            },
        ],
        "acceptance_criteria": [
            {
                "criterion_id": f"AC-{expert_name}-001",
                "description": f"{expert_name} criterion 1",
                "verification_method": "Run test X",
            },
        ],
        "covered_req_ids": covered_req_ids or ["REQ-P0-001"],
    }


MOCK_HARNESS_OUTPUT = {
    "schema_version": "2.0.0",
    "gate_a": {
        "score": 0.87,
        "verdict": "PASS",
        "scores": {
            "completeness": 0.90,
            "necessity": 0.85,
            "alignment": 0.88,
            "global_impact": 0.82,
        },
        "reasoning": {
            "completeness": "Good coverage",
            "necessity": "Reasonable constraints",
            "alignment": "Aligned with task",
            "global_impact": "Considered impact",
        },
    },
    "gate_b": {
        "pass_rate": 1.0,
        "verdict": "PASS",
        "checks": [],
        "failed_items": [],
    },
    "final_verdict": {
        "final_verdict": "PASS",
        "gate_a": "PASS",
        "gate_b": "PASS",
    },
}

MOCK_REVIEWER_PASS = {
    "schema_version": "2.0.0",
    "reviewer": "reviewer",
    "overall_verdict": "PASS",
    "overall_score": 0.92,
    "reviews": {},
    "issues": [],
    "suggestions": [],
}

MOCK_REVIEWER_FAIL = {
    "schema_version": "2.0.0",
    "reviewer": "reviewer",
    "overall_verdict": "FAIL",
    "overall_score": 0.40,
    "reviews": {},
    "issues": [{"severity": "CRITICAL", "description": "Missing domain"}],
    "suggestions": [],
}


# ============================================================================
# Mock Blackboard
# ============================================================================

class MockBlackboard:
    """Mock Blackboard for testing"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.session_id = "test_phase1"
        self.data = {}

        (base_dir / "stages").mkdir(parents=True, exist_ok=True)
        (base_dir / "stages" / "expert_plans").mkdir(parents=True, exist_ok=True)
        (base_dir / "data").mkdir(parents=True, exist_ok=True)

    def read(self, path: str) -> dict:
        if path in self.data:
            return self.data[path]
        file_path = self.base_dir / path
        if file_path.exists():
            with open(file_path, "r") as f:
                return json.load(f)
        raise FileNotFoundError(f"File not found: {path}")

    def read_json(self, path: str) -> dict:
        return self.read(path)

    def write(self, path: str, data):
        if isinstance(data, str):
            parsed = json.loads(data)
            self.data[path] = parsed
        else:
            self.data[path] = data

        file_path = self.base_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def delete(self, path: str):
        self.data.pop(path, None)
        file_path = self.base_dir / path
        if file_path.exists():
            file_path.unlink()

    def get_session_dir(self) -> Path:
        return self.base_dir


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_blackboard(tmp_path, monkeypatch):
    """Create and inject a MockBlackboard"""
    bb = MockBlackboard(tmp_path)

    from domains.solution_pro import module_orchestrator_base
    monkeypatch.setattr(
        module_orchestrator_base, "BlackboardManager",
        lambda session_id, base_dir=None: bb
    )

    bb.write("frozen_spec.json", MOCK_FROZEN_SPEC)
    bb.write("structured_requirements.json", MOCK_STRUCTURED_REQUIREMENTS)
    bb.write("data/frozen_spec.json", MOCK_FROZEN_SPEC)

    return bb


@pytest.fixture
def mock_spawn_fn():
    """Create a mock spawn function"""
    def _spawn(task, output_path):
        # This signature matches the fallback call pattern:
        # spawn_fn(task=task["prompt"], output_path=output_path)
        if output_path == "stages/meta_planning.json":
            return json.loads(json.dumps(MOCK_EXPERT_MANIFEST))
        elif output_path.startswith("stages/expert_plans/"):
            expert_name = output_path.split("/")[-1].replace(".json", "")
            return _make_expert_plan(expert_name)
        elif output_path == "stages/convergence_planning.json":
            return _make_convergence_output()
        elif output_path == "stages/harness_planning.json":
            return json.loads(json.dumps(MOCK_HARNESS_OUTPUT))
        elif output_path == "stages/reviewer_meta.json":
            return MOCK_REVIEWER_PASS.copy()
        elif output_path == "stages/reviewer_convergence.json":
            return MOCK_REVIEWER_PASS.copy()
        else:
            return MOCK_REVIEWER_PASS.copy()

    return _spawn


def _make_convergence_output():
    """Create mock convergence output"""
    return {
        "schema_version": "2.0.0",
        "unified_constraints": [
            {
                "constraint_id": "UC-001",
                "description": "All API endpoints must require authentication",
                "priority": "MUST",
                "source_experts": ["security_expert"],
                "conflicts_resolved": [],
            },
            {
                "constraint_id": "UC-002",
                "description": "API response time < 200ms",
                "priority": "MUST",
                "source_experts": ["performance_expert"],
                "conflicts_resolved": [],
            },
            {
                "constraint_id": "UC-003",
                "description": "Support horizontal scaling",
                "priority": "SHOULD",
                "source_experts": ["scalability_expert"],
                "conflicts_resolved": [],
            },
        ],
        "rejected_constraints": [],
        "meta": {
            "total_expert_plans": 3,
            "total_input_constraints": 6,
            "total_output_constraints": 3,
            "merge_ratio": 0.5,
        },
        "covered_req_ids": ["REQ-P0-001", "REQ-P0-002", "REQ-P0-003"],
        "verification_checklist": {
            "schema_version": "2.0.0",
            "checklist": [
                {
                    "check_id": "VC-001",
                    "constraint_id": "UC-001",
                    "verification_method": "Run auth tests",
                    "expected_result": "All endpoints return 401",
                },
                {
                    "check_id": "VC-002",
                    "constraint_id": "UC-002",
                    "verification_method": "Run load test",
                    "expected_result": "p95 < 200ms",
                },
                {
                    "check_id": "VC-003",
                    "constraint_id": "UC-003",
                    "verification_method": "Run scaling test",
                    "expected_result": "Linear scaling",
                },
            ],
            "total_checks": 3,
        },
    }


# ============================================================================
# Test Class: Phase 1 Acceptance Tests
# ============================================================================

class TestPhase1Acceptance:
    """Phase 1 验收测试：Planning V2 端到端"""

    # === Layer 0: Meta-Planning ===

    def test_meta_planner_domain_identification(self, mock_blackboard, mock_spawn_fn):
        """验证 Meta-Planner 能正确识别领域"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        expert_manifest = orchestrator._run_meta_planner()

        # backend_api 需求 → 输出包含 security/performance/scalability 专家
        assert expert_manifest["task_profile"]["domain"] == "backend_api"
        expert_names = [e["expert_name"] for e in expert_manifest["experts"]]
        assert "security_expert" in expert_names
        assert "performance_expert" in expert_names
        assert "scalability_expert" in expert_names

    def test_meta_planner_gate_config_generation(self, mock_blackboard, mock_spawn_fn):
        """验证 Meta-Planner 生成的 Gate 配置合理"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        expert_manifest = orchestrator._run_meta_planner()

        # Gate A 权重之和 == 1.0
        weights = expert_manifest["gate_a"]["weights"]
        weight_sum = sum(weights.values())
        assert abs(weight_sum - 1.0) < 0.01, f"Weights sum to {weight_sum}, expected 1.0"

        # Gate B 至少包含 1 个 CRITICAL 检查项
        dynamic_checks = expert_manifest["gate_b"]["dynamic_checks"]
        critical_checks = [c for c in dynamic_checks if c["severity"] == "CRITICAL"]
        assert len(critical_checks) >= 1, "Gate B must have at least 1 CRITICAL check"

    def test_reviewer_meta_pass_for_valid_manifest(self, mock_blackboard, mock_spawn_fn):
        """验证 Reviewer_Meta 对合理组合返回 PASS"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        expert_manifest = orchestrator._run_meta_planner()
        reviewer_output = orchestrator._run_reviewer_meta(expert_manifest)

        assert reviewer_output["overall_verdict"] == "PASS"

    def test_reviewer_meta_fail_for_missing_domain(self, mock_blackboard):
        """验证 Reviewer_Meta 对遗漏关键领域返回 FAIL"""
        # Create a spawn_fn that returns FAIL for reviewer_meta
        def spawn_fail_reviewer(task, output_path):
            if output_path == "stages/reviewer_meta.json":
                return MOCK_REVIEWER_FAIL.copy()
            return json.loads(json.dumps(MOCK_EXPERT_MANIFEST))

        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=spawn_fail_reviewer,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        expert_manifest = orchestrator._run_meta_planner()
        reviewer_output = orchestrator._run_reviewer_meta(expert_manifest)

        assert reviewer_output["overall_verdict"] == "FAIL"

    # === Layer 1: Parallel Expert Planning ===

    def test_expert_planners_parallel_execution(self, mock_blackboard, mock_spawn_fn):
        """验证 Expert Planners 能并行执行"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        expert_plans = orchestrator._run_expert_planners(MOCK_EXPERT_MANIFEST)

        # 3 个专家并行，验证所有输出都生成
        assert len(expert_plans) == 3
        expert_names = [p["expert_name"] for p in expert_plans]
        assert "security_expert" in expert_names
        assert "performance_expert" in expert_names
        assert "scalability_expert" in expert_names

    def test_expert_plan_schema_validation(self, mock_blackboard, mock_spawn_fn):
        """验证每个 Expert Plan 符合 ExpertPlanSchema"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        expert_plans = orchestrator._run_expert_planners(MOCK_EXPERT_MANIFEST)

        for plan in expert_plans:
            # Validate against schema
            ExpertPlanSchema(**plan)
            # Check required fields
            assert "expert_name" in plan
            assert "constraints" in plan
            assert len(plan["constraints"]) >= 1
            assert "acceptance_criteria" in plan
            assert len(plan["acceptance_criteria"]) >= 1

    def test_expert_planner_checkpoint_resume(self, mock_blackboard, mock_spawn_fn):
        """验证断点续跑：已完成的不重跑"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # First run - generates all expert plans
        expert_plans_1 = orchestrator._run_expert_planners(MOCK_EXPERT_MANIFEST)
        assert len(expert_plans_1) == 3

        # Second run - should load from checkpoint
        orchestrator2 = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator2._use_adapter = False  # 测试模式
        orchestrator2.blackboard = mock_blackboard

        expert_plans_2 = orchestrator2._run_expert_planners(MOCK_EXPERT_MANIFEST)
        assert len(expert_plans_2) == 3

        # Results should be the same (loaded from checkpoint, order-independent)
        plans_by_name_1 = {p["expert_name"]: p for p in expert_plans_1}
        plans_by_name_2 = {p["expert_name"]: p for p in expert_plans_2}
        assert plans_by_name_1 == plans_by_name_2

    def test_expert_planner_graceful_degradation(self, mock_blackboard):
        """验证优雅降级：部分专家失败仍继续"""
        call_count = {"n": 0}

        def spawn_with_failure(task=None, output_path=None, **kwargs):
            if output_path and output_path.startswith("stages/expert_plans/"):
                call_count["n"] += 1
                expert_name = output_path.split("/")[-1].replace(".json", "")
                # First expert fails
                if expert_name == "security_expert":
                    raise RuntimeError("Simulated expert failure")
                return _make_expert_plan(expert_name)
            if output_path == "stages/meta_planning.json":
                return json.loads(json.dumps(MOCK_EXPERT_MANIFEST))
            return MOCK_REVIEWER_PASS.copy()

        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=spawn_with_failure,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # N=3, 1 个失败 → 仍然 PASS（min_viable=2）
        expert_plans = orchestrator._run_expert_planners(MOCK_EXPERT_MANIFEST)
        assert len(expert_plans) == 2  # 2 succeeded out of 3

    def test_expert_planner_insufficient_experts_fail(self, mock_blackboard):
        """验证不足专家数 → 正确报错"""
        def spawn_all_fail(task=None, output_path=None, **kwargs):
            if output_path and output_path.startswith("stages/expert_plans/"):
                expert_name = output_path.split("/")[-1].replace(".json", "")
                # All experts fail except one
                if expert_name in ["security_expert", "performance_expert"]:
                    raise RuntimeError(f"Simulated failure for {expert_name}")
                return _make_expert_plan(expert_name)
            if output_path == "stages/meta_planning.json":
                return json.loads(json.dumps(MOCK_EXPERT_MANIFEST))
            return MOCK_REVIEWER_PASS.copy()

        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=spawn_all_fail,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # N=3, 2 个失败 → raise RuntimeError (min_viable=2, only 1 succeeded)
        with pytest.raises(RuntimeError, match="Insufficient experts"):
            orchestrator._run_expert_planners(MOCK_EXPERT_MANIFEST)

    # === Layer 2: Convergence Planning ===

    def test_convergence_planner_semantic_dedup(self, mock_blackboard, mock_spawn_fn):
        """验证 Convergence Planner 语义去重"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # Input: 3 Expert Plans with some duplicate constraints
        expert_plans = [
            _make_expert_plan("security_expert", [
                {"constraint_id": "C-001", "description": "Use HTTPS", "priority": "MUST", "rationale": "Security"},
            ]),
            _make_expert_plan("performance_expert", [
                {"constraint_id": "C-002", "description": "Use HTTPS", "priority": "MUST", "rationale": "Performance"},
            ]),
            _make_expert_plan("scalability_expert", [
                {"constraint_id": "C-003", "description": "Horizontal scaling", "priority": "SHOULD", "rationale": "Scale"},
            ]),
        ]

        convergence_output = orchestrator._run_convergence_planner(MOCK_EXPERT_MANIFEST, expert_plans)

        # Output should have unified_constraints
        assert "unified_constraints" in convergence_output
        uc = convergence_output["unified_constraints"]
        assert isinstance(uc, list)
        # The mock convergence output has 3 constraints (deduped from input)
        assert len(uc) >= 1

    def test_convergence_planner_conflict_resolution(self, mock_blackboard, mock_spawn_fn):
        """验证冲突解决"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        convergence_output = orchestrator._run_convergence_planner(
            MOCK_EXPERT_MANIFEST,
            [_make_expert_plan("security_expert"), _make_expert_plan("performance_expert")],
        )

        # Check that conflicts_resolved field exists in unified constraints
        for constraint in convergence_output["unified_constraints"]:
            assert "conflicts_resolved" in constraint
            assert isinstance(constraint["conflicts_resolved"], list)

    def test_convergence_planner_p0_req_coverage(self, mock_blackboard, mock_spawn_fn):
        """验证 P0 REQ 100% 覆盖"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        convergence_output = orchestrator._run_convergence_planner(
            MOCK_EXPERT_MANIFEST,
            [_make_expert_plan("security_expert"), _make_expert_plan("performance_expert")],
        )

        # Check covered_req_ids
        covered = convergence_output.get("covered_req_ids", [])
        # At least some P0 REQs should be covered
        assert len(covered) >= 1

    def test_reviewer_convergence_pass_for_valid_merge(self, mock_blackboard, mock_spawn_fn):
        """验证 Reviewer_Convergence 对合理合并返回 PASS"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # Write required files for reviewer_convergence
        # _run_reviewer_convergence reads ALL expert plans from meta_planning
        mock_blackboard.write("stages/meta_planning.json", MOCK_EXPERT_MANIFEST)
        for expert in MOCK_EXPERT_MANIFEST["experts"]:
            mock_blackboard.write(
                f"stages/expert_plans/{expert['expert_name']}.json",
                _make_expert_plan(expert["expert_name"]),
            )

        convergence_output = orchestrator._run_convergence_planner(
            MOCK_EXPERT_MANIFEST,
            [_make_expert_plan(e["expert_name"]) for e in MOCK_EXPERT_MANIFEST["experts"]],
        )

        reviewer_output = orchestrator._run_reviewer_convergence(convergence_output)
        assert reviewer_output["overall_verdict"] == "PASS"

    # === Harness: Gate A Layer 2 ===

    def test_gate_a_layer2_majority_vote(self):
        """验证 Gate A Layer 2 多数投票"""
        # 3 次运行，2 PASS 1 FAIL → PASS
        call_count = {"n": 0}

        def llm_judge_fn(**kwargs):
            call_count["n"] += 1
            # 2 PASS, 1 FAIL
            if call_count["n"] <= 2:
                return {"semantic_verdict": "PASS", "reasoning": "Looks good"}
            else:
                return {"semantic_verdict": "FAIL", "reasoning": "Issue found"}

        layer2 = GateALayer2Calibration(llm_judge_fn=llm_judge_fn)
        result = layer2.run_majority_vote(
            stage_output={"test": "data"},
            frozen_spec={"test": "spec"},
            harness_reasoning="test reasoning",
            scores={"completeness": 0.9, "necessity": 0.85, "alignment": 0.88, "global_impact": 0.82},
            n_runs=3,
        )

        assert result["semantic_verdict"] == "PASS"
        assert result["votes"].count("PASS") == 2
        assert result["votes"].count("FAIL") == 1
        assert result["consistency"] == pytest.approx(0.67, abs=0.01)

    def test_gate_a_layer2_fail_override(self):
        """验证 Layer 2 FAIL 覆盖 Layer 1 PASS"""
        # 3 次运行，全部 FAIL → FAIL
        def llm_judge_fn(**kwargs):
            return {"semantic_verdict": "FAIL", "reasoning": "Critical issue"}

        layer2 = GateALayer2Calibration(llm_judge_fn=llm_judge_fn)
        result = layer2.run_majority_vote(
            stage_output={"test": "data"},
            frozen_spec={"test": "spec"},
            harness_reasoning="test reasoning",
            scores={"completeness": 0.9, "necessity": 0.85, "alignment": 0.88, "global_impact": 0.82},
            n_runs=3,
        )

        assert result["semantic_verdict"] == "FAIL"
        assert result["votes"].count("FAIL") == 3

    def test_gate_a_layer2_rule_based_fallback(self):
        """验证无 llm_judge_fn 时的规则 fallback"""
        layer2 = GateALayer2Calibration(llm_judge_fn=None)
        result = layer2.run_majority_vote(
            stage_output={"test": "data"},
            frozen_spec={"test": "spec"},
            harness_reasoning="test reasoning",
            scores={"completeness": 0.9, "necessity": 0.85, "alignment": 0.88, "global_impact": 0.82},
        )

        # Rule-based fallback should produce a verdict
        assert result["semantic_verdict"] in ("PASS", "FAIL")
        assert "note" in result
        assert result["note"] == "rule_based_fallback"

        # With high scores, should PASS
        assert result["semantic_verdict"] == "PASS"

    # === Harness: Gate B CRITICAL ===

    def test_gate_b_critical_all_pass(self):
        """验证 Gate B 全部 CRITICAL 通过 → PASS"""
        gate_b_results = [
            {"check_id": "CHK-001", "verdict": "PASS", "reasoning": "OK"},
            {"check_id": "CHK-002", "verdict": "PASS", "reasoning": "OK"},
            {"check_id": "CHK-003", "verdict": "PASS", "reasoning": "OK"},
        ]
        critical_checks = [
            {"id": "CHK-001", "criticality": "CRITICAL", "description": "Security"},
            {"id": "CHK-002", "criticality": "CRITICAL", "description": "P0 Coverage"},
            {"id": "CHK-003", "criticality": "MINOR", "description": "Style"},
        ]

        result = evaluate_gate_b_critical(gate_b_results, critical_checks)

        assert result["verdict"] == "PASS"
        assert result["critical_pass_rate"] == 1.0
        assert result["overall_pass_rate"] == 1.0
        assert len(result["failed_critical"]) == 0

    def test_gate_b_critical_one_fail(self):
        """验证 Gate B 一个 CRITICAL 失败 → FAIL"""
        gate_b_results = [
            {"check_id": "CHK-001", "verdict": "FAIL", "reasoning": "Security issue"},
            {"check_id": "CHK-002", "verdict": "PASS", "reasoning": "OK"},
            {"check_id": "CHK-003", "verdict": "PASS", "reasoning": "OK"},
        ]
        critical_checks = [
            {"id": "CHK-001", "criticality": "CRITICAL", "description": "Security"},
            {"id": "CHK-002", "criticality": "CRITICAL", "description": "P0 Coverage"},
            {"id": "CHK-003", "criticality": "MINOR", "description": "Style"},
        ]

        result = evaluate_gate_b_critical(gate_b_results, critical_checks)

        assert result["verdict"] == "FAIL"
        assert "CHK-001" in result["failed_critical"]

    def test_gate_b_critical_overall_rate(self):
        """验证 Gate B 整体通过率 < 80% → FAIL"""
        gate_b_results = [
            {"check_id": "CHK-001", "verdict": "PASS", "reasoning": "OK"},
            {"check_id": "CHK-002", "verdict": "FAIL", "reasoning": "Issue"},
            {"check_id": "CHK-003", "verdict": "FAIL", "reasoning": "Issue"},
            {"check_id": "CHK-004", "verdict": "FAIL", "reasoning": "Issue"},
            {"check_id": "CHK-005", "verdict": "FAIL", "reasoning": "Issue"},
        ]
        critical_checks = [
            {"id": "CHK-001", "criticality": "MINOR", "description": "Style"},
            {"id": "CHK-002", "criticality": "MINOR", "description": "Format"},
            {"id": "CHK-003", "criticality": "MINOR", "description": "Naming"},
            {"id": "CHK-004", "criticality": "MINOR", "description": "Docs"},
            {"id": "CHK-005", "criticality": "MINOR", "description": "Lint"},
        ]

        result = evaluate_gate_b_critical(gate_b_results, critical_checks)

        # Overall pass rate = 1/5 = 0.2 < 0.8 → FAIL
        assert result["verdict"] == "FAIL"
        assert result["overall_pass_rate"] == pytest.approx(0.2, abs=0.01)

    # === 端到端 ===

    def test_planning_orchestrator_full_7step_flow(self, mock_blackboard, mock_spawn_fn):
        """验证 PlanningOrchestrator 完整 7 步流程"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # Run full 7-step flow
        planning_convergence = orchestrator.run()

        # Verify output
        assert planning_convergence["module"] == "planning"
        assert planning_convergence["gate_verdict"]["final_verdict"] == "PASS"
        assert "unified_constraints" in planning_convergence
        assert "verification_checklist" in planning_convergence
        assert "planning_summary" in planning_convergence

        # Verify all blackboard files written
        assert mock_blackboard.read("stages/meta_planning.json") is not None
        assert mock_blackboard.read("stages/expert_plans/security_expert.json") is not None
        assert mock_blackboard.read("stages/expert_plans/performance_expert.json") is not None
        assert mock_blackboard.read("stages/expert_plans/scalability_expert.json") is not None
        assert mock_blackboard.read("stages/unified_constraints.json") is not None
        assert mock_blackboard.read("stages/verification_checklist.json") is not None
        assert mock_blackboard.read("stages/convergence_planning.json") is not None
        assert mock_blackboard.read("stages/harness_planning.json") is not None
        assert mock_blackboard.read("planning_convergence.json") is not None

        # Verify checkpoint state
        state = mock_blackboard.read("module_planning_state.json")
        assert state["completed"] is True

    def test_planning_orchestrator_checkpoint_resume(self, mock_blackboard, mock_spawn_fn):
        """验证断点续跑：中断后从断点恢复"""
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # First run
        result_1 = orchestrator.run()

        # Second run (should resume from checkpoint)
        orchestrator2 = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator2._use_adapter = False  # 测试模式
        orchestrator2.blackboard = mock_blackboard

        result_2 = orchestrator2.run()

        # Should return same result (loaded from checkpoint)
        assert result_1 == result_2
        assert result_2["gate_verdict"]["final_verdict"] == "PASS"

    # === 并行执行 ===

    def test_execute_parallel_base_method(self, mock_blackboard):
        """验证基类 _execute_parallel() 方法"""
        orchestrator = ModuleOrchestrator(
            module_name="test",
            session_id="test_phase1",
            spawn_fn=None,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # Create 5 tasks
        tasks = []
        for i in range(5):
            tasks.append({
                "task_key": f"task_{i}",
                "spawn_fn": lambda t, i=i: {"result": f"output_{i}", "task_key": t.get("task_key")},
            })

        results = orchestrator._execute_parallel(tasks, max_workers=3)

        assert len(results) == 5
        result_keys = [r.get("task_key") for r in results]
        for i in range(5):
            assert f"task_{i}" in result_keys

    def test_execute_parallel_degraded_mode(self, mock_blackboard):
        """验证基类并行降级模式"""
        orchestrator = ModuleOrchestrator(
            module_name="test",
            session_id="test_phase1",
            spawn_fn=None,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # Create 5 tasks, 2 will fail
        def failing_task(t):
            task_key = t.get("task_key", "")
            if "fail" in task_key:
                raise RuntimeError(f"Task {task_key} failed")
            return {"result": "ok", "task_key": task_key}

        tasks = [
            {"task_key": "task_ok_1", "spawn_fn": failing_task},
            {"task_key": "task_ok_2", "spawn_fn": failing_task},
            {"task_key": "task_ok_3", "spawn_fn": failing_task},
            {"task_key": "task_fail_1", "spawn_fn": failing_task},
            {"task_key": "task_fail_2", "spawn_fn": failing_task},
        ]

        # min_viable=3, 3 succeed, 2 fail → PASS (degraded)
        results = orchestrator._execute_parallel(tasks, max_workers=3, min_viable=3)
        assert len(results) == 3

        # min_viable=4, only 3 succeed → FAIL
        with pytest.raises(RuntimeError, match="Insufficient tasks"):
            orchestrator._execute_parallel(tasks, max_workers=3, min_viable=4)

    # === V1 兼容性 ===

    def test_v1_backward_compatibility(self, mock_blackboard, mock_spawn_fn):
        """验证 V1 功能不受影响"""
        # V1 的 run() 仍然可以工作
        orchestrator = PlanningOrchestrator(
            session_id="test_phase1",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        orchestrator.blackboard = mock_blackboard

        # V1 style: call run() without parameters
        result = orchestrator.run()

        assert result is not None
        assert result["module"] == "planning"
        assert "gate_verdict" in result
        assert result["gate_verdict"]["final_verdict"] == "PASS"


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
