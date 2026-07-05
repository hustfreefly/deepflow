"""
Planning Orchestrator Tests

Version: 2.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

Description:
- Test PlanningOrchestrator (Module 1)
- Test Meta-Planner (Layer 0)
- Test Expert Planners (Layer 1)
- Test Convergence Planner (Layer 2)
- Test Harness Agent (Gate A + Gate B)
- Test planning_convergence.json generation
"""

import pytest
import json
import sys
from pathlib import Path

# Add .deepflow to sys.path
deepflow_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(deepflow_root))

from domains.solution_pro.planning_orchestrator import PlanningOrchestrator


class MockBlackboard:
    """Mock Blackboard for testing"""
    
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.session_id = "test_session"
        self.data = {}
        
        # Ensure stages directory exists
        (base_dir / "stages").mkdir(parents=True, exist_ok=True)
        (base_dir / "stages" / "expert_plans").mkdir(parents=True, exist_ok=True)
    
    def read(self, path: str) -> dict:
        if path in self.data:
            return self.data[path]
        
        # Try to read from file
        file_path = self.base_dir / path
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        
        raise FileNotFoundError(f"File not found: {path}")
    
    def read_json(self, path: str, default=None) -> dict:
        """兼容 _adapted_spawn 的 read_json 调用"""
        try:
            return self.read(path)
        except FileNotFoundError:
            return default or {}

    def write(self, path: str, data: dict):
        self.data[path] = data
        
        # Also write to file
        file_path = self.base_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)


class TestPlanningOrchestrator:
    """Test PlanningOrchestrator"""
    
    @pytest.fixture
    def mock_blackboard(self, tmp_path, monkeypatch):
        """Create mock blackboard"""
        mock_bb = MockBlackboard(tmp_path)
        
        # Patch BlackboardManager to return our mock
        from domains.solution_pro import module_orchestrator_base
        
        def mock_bb_factory(session_id, base_dir=None):
            return mock_bb
        
        monkeypatch.setattr(module_orchestrator_base, "BlackboardManager", mock_bb_factory)
        
        # Write input files
        frozen_spec = {
            "schema_version": "2.0.0",
            "project_name": "Test Project",
            "p0_req_ids": ["REQ-P0-001", "REQ-P0-002"],
            "requirements": [
                {"id": "REQ-P0-001", "description": "Security requirement", "priority": "P0"},
                {"id": "REQ-P0-002", "description": "Performance requirement", "priority": "P0"},
            ],
        }
        mock_bb.write("frozen_spec.json", frozen_spec)
        
        structured_requirements = {
            "schema_version": "2.0.0",
            "requirements": frozen_spec["requirements"],
        }
        mock_bb.write("structured_requirements.json", structured_requirements)
        
        return mock_bb
    
    @pytest.fixture
    def mock_spawn_fn(self):
        """Create mock spawn function"""
        def spawn_fn(task, output_path):
            # Return mock output based on output_path
            if output_path == "stages/meta_planning.json":
                return {
                    "schema_version": "2.0.0",
                    "task_profile": {
                        "domain": "backend_api",
                        "complexity": "high",
                        "risk_areas": ["security", "scalability"],
                    },
                    "experts": [
                        {
                            "expert_name": "security_expert",
                            "domain": "Security",
                            "focus_areas": ["OWASP Top 10"],
                            "evaluation_lens": "Security perspective",
                        },
                        {
                            "expert_name": "performance_expert",
                            "domain": "Performance",
                            "focus_areas": ["latency", "throughput"],
                            "evaluation_lens": "Performance perspective",
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
                        "rationale": "High risk task",
                    },
                    "gate_b": {
                        "dynamic_checks": [
                            {
                                "name": "security_audit",
                                "description": "Security audit",
                                "pass_criteria": "No high-risk vulnerabilities",
                                "severity": "CRITICAL",
                                "reasoning": "Security is P0",
                            },
                        ],
                    },
                    "verdict_policy": {
                        "warning_acceptable": False,
                        "min_gate_b_pass_rate": 0.8,
                    },
                }
            
            elif output_path.startswith("stages/expert_plans/"):
                expert_name = output_path.split("/")[-1].replace(".json", "")
                return {
                    "schema_version": "2.0.0",
                    "expert_name": expert_name,
                    "constraints": [
                        {
                            "constraint_id": "C-001",
                            "description": f"{expert_name} constraint 1",
                            "priority": "MUST",
                            "rationale": "Critical requirement",
                        },
                    ],
                    "risks": [
                        {
                            "risk_id": "R-001",
                            "description": f"{expert_name} risk 1",
                            "mitigation": "Mitigation strategy",
                        },
                    ],
                    "acceptance_criteria": [
                        {
                            "criterion_id": "AC-001",
                            "description": f"{expert_name} criterion 1",
                            "verification_method": "Run test X",
                        },
                    ],
                    "covered_req_ids": ["REQ-P0-001"],
                }
            
            elif output_path == "stages/convergence_planning.json":
                return {
                    "schema_version": "2.0.0",
                    "unified_constraints": [
                        {
                            "constraint_id": "UC-001",
                            "description": "Unified constraint 1",
                            "priority": "MUST",
                            "source_experts": ["security_expert"],
                            "conflicts_resolved": [],
                        },
                    ],
                    "rejected_constraints": [],
                    "meta": {
                        "total_expert_plans": 2,
                        "total_input_constraints": 2,
                        "total_output_constraints": 1,
                        "merge_ratio": 0.5,
                    },
                    "covered_req_ids": ["REQ-P0-001"],
                    "verification_checklist": {
                        "schema_version": "2.0.0",
                        "checklist": [
                            {
                                "check_id": "VC-001",
                                "constraint_id": "UC-001",
                                "verification_method": "Verify constraint",
                                "expected_result": "Pass",
                            },
                        ],
                        "total_checks": 1,
                    },
                }
            
            elif output_path == "stages/harness_planning.json":
                return {
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
                        "reasoning": {},
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
            
            else:
                # Reviewer outputs
                return {
                    "schema_version": "2.0.0",
                    "reviewer": "reviewer",
                    "overall_verdict": "PASS",
                    "overall_score": 0.92,
                    "reviews": {},
                    "issues": [],
                    "suggestions": [],
                }
        
        return spawn_fn
    
    def test_init(self, mock_blackboard):
        """Test PlanningOrchestrator initialization"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=None,
        )
        
        assert orchestrator.session_id == "test_session"
        assert orchestrator.module_name == "planning"
    
    def test_run_meta_planner(self, mock_blackboard, mock_spawn_fn):
        """Test Meta-Planner (Layer 0)"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        expert_manifest = orchestrator._run_meta_planner()
        
        assert expert_manifest["task_profile"]["domain"] == "backend_api"
        assert expert_manifest["task_profile"]["complexity"] == "high"
        assert len(expert_manifest["experts"]) == 2
        assert expert_manifest["gate_a"]["weights"]["completeness"] == 0.30
        
        # Check blackboard
        saved_manifest = mock_blackboard.read("stages/meta_planning.json")
        assert saved_manifest == expert_manifest
    
    def test_run_expert_planners(self, mock_blackboard, mock_spawn_fn):
        """Test Expert Planners (Layer 1)"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        # First run Meta-Planner
        expert_manifest = orchestrator._run_meta_planner()
        
        # Then run Expert Planners
        expert_plans = orchestrator._run_expert_planners(expert_manifest)
        
        assert len(expert_plans) == 2
        expert_names = {p["expert_name"] for p in expert_plans}
        assert expert_names == {"security_expert", "performance_expert"}
        
        # Check blackboard
        saved_plan_1 = mock_blackboard.read("stages/expert_plans/security_expert.json")
        assert saved_plan_1["expert_name"] == "security_expert"
    
    def test_run_convergence_planner(self, mock_blackboard, mock_spawn_fn):
        """Test Convergence Planner (Layer 2)"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        # First run Meta-Planner and Expert Planners
        expert_manifest = orchestrator._run_meta_planner()
        expert_plans = orchestrator._run_expert_planners(expert_manifest)
        
        # Then run Convergence Planner
        convergence_output = orchestrator._run_convergence_planner(expert_manifest, expert_plans)
        
        assert "unified_constraints" in convergence_output
        assert "verification_checklist" in convergence_output
        assert len(convergence_output["unified_constraints"]) == 1
        
        # Check blackboard
        saved_constraints = mock_blackboard.read("stages/unified_constraints.json")
        assert saved_constraints == convergence_output["unified_constraints"]
    
    def test_run_harness_agent(self, mock_blackboard, mock_spawn_fn):
        """Test Harness Agent (Gate A + Gate B)"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        # First run Meta-Planner, Expert Planners, and Convergence Planner
        expert_manifest = orchestrator._run_meta_planner()
        expert_plans = orchestrator._run_expert_planners(expert_manifest)
        convergence_output = orchestrator._run_convergence_planner(expert_manifest, expert_plans)
        
        # Then run Harness Agent
        harness_output = orchestrator._run_harness_agent(convergence_output, expert_manifest)
        
        assert harness_output["gate_a"]["verdict"] == "PASS"
        assert harness_output["gate_b"]["verdict"] == "PASS"
        assert harness_output["final_verdict"]["final_verdict"] == "PASS"
        
        # Check blackboard
        saved_harness = mock_blackboard.read("stages/harness_planning.json")
        assert saved_harness == harness_output
    
    def test_generate_planning_convergence(self, mock_blackboard, mock_spawn_fn):
        """Test planning_convergence.json generation"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        # First run all steps
        expert_manifest = orchestrator._run_meta_planner()
        expert_plans = orchestrator._run_expert_planners(expert_manifest)
        convergence_output = orchestrator._run_convergence_planner(expert_manifest, expert_plans)
        harness_output = orchestrator._run_harness_agent(convergence_output, expert_manifest)
        
        # Then generate planning_convergence.json
        planning_convergence = orchestrator._generate_planning_convergence(
            expert_manifest,
            convergence_output,
            harness_output,
        )
        
        assert planning_convergence["module"] == "planning"
        assert planning_convergence["gate_verdict"]["final_verdict"] == "PASS"
        assert "planning_summary" in planning_convergence
        assert "original_references" in planning_convergence
        
        # Check blackboard
        saved_convergence = mock_blackboard.read("planning_convergence.json")
        assert saved_convergence == planning_convergence
    
    def test_full_run(self, mock_blackboard, mock_spawn_fn):
        """Test full Planning module run"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        # Run full module
        planning_convergence = orchestrator.run()
        
        assert planning_convergence["module"] == "planning"
        assert planning_convergence["gate_verdict"]["final_verdict"] == "PASS"
        
        # Check all blackboard files
        assert mock_blackboard.read("stages/meta_planning.json") is not None
        assert mock_blackboard.read("stages/expert_plans/security_expert.json") is not None
        assert mock_blackboard.read("stages/expert_plans/performance_expert.json") is not None
        assert mock_blackboard.read("stages/unified_constraints.json") is not None
        assert mock_blackboard.read("stages/verification_checklist.json") is not None
        assert mock_blackboard.read("stages/harness_planning.json") is not None
        assert mock_blackboard.read("planning_convergence.json") is not None
        
        # Check checkpoint
        state = mock_blackboard.read("module_planning_state.json")
        assert state["completed"] is True
    
    def test_resume_from_checkpoint(self, mock_blackboard, mock_spawn_fn):
        """Test resume from checkpoint"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        # First run
        planning_convergence_1 = orchestrator.run()
        
        # Second run (should resume from checkpoint)
        planning_convergence_2 = orchestrator.run()
        
        # Should return same result
        assert planning_convergence_1 == planning_convergence_2
    
    def test_helper_methods(self, mock_blackboard, mock_spawn_fn):
        """Test helper methods"""
        orchestrator = PlanningOrchestrator(
            session_id="test_session",
            spawn_fn=mock_spawn_fn,
        )
        orchestrator._use_adapter = False  # 测试模式
        
        # Test _count_priorities
        constraints = [
            {"priority": "MUST"},
            {"priority": "MUST"},
            {"priority": "SHOULD"},
            {"priority": "MAY"},
        ]
        priority_str = orchestrator._count_priorities(constraints)
        assert "MUST: 2" in priority_str
        assert "SHOULD: 1" in priority_str
        assert "MAY: 1" in priority_str
        
        # Test _compute_hash
        data = {"key": "value"}
        hash_str = orchestrator._compute_hash(data)
        assert hash_str.startswith("sha256:")
        
        # Test _get_timestamp
        timestamp = orchestrator._get_timestamp()
        assert "T" in timestamp  # ISO format


class TestPlanningOrchestratorIntegration:
    """Integration tests for PlanningOrchestrator"""
    
    def test_gate_a_score_calculation(self):
        """Test Gate A score calculation"""
        # Gate A weights
        weights = {
            "completeness": 0.30,
            "necessity": 0.15,
            "alignment": 0.35,
            "global_impact": 0.20,
        }
        
        # Gate A scores
        scores = {
            "completeness": 0.90,
            "necessity": 0.85,
            "alignment": 0.88,
            "global_impact": 0.82,
        }
        
        # Calculate weighted score
        weighted_score = sum(scores[k] * weights[k] for k in scores)
        
        assert weighted_score == pytest.approx(0.87, abs=0.01)
        
        # Check verdict
        if weighted_score >= 0.85:
            verdict = "PASS"
        elif weighted_score >= 0.70:
            verdict = "WARNING"
        elif weighted_score >= 0.60:
            verdict = "CRITICAL_WARNING"
        else:
            verdict = "BLOCK_RECOMMENDATION"
        
        assert verdict == "PASS"
    
    def test_gate_b_pass_rate_calculation(self):
        """Test Gate B pass rate calculation"""
        checks = [
            {"result": "PASS"},
            {"result": "PASS"},
            {"result": "FAIL"},
        ]
        
        passed = sum(1 for c in checks if c["result"] == "PASS")
        pass_rate = passed / len(checks)
        
        assert pass_rate == pytest.approx(0.67, abs=0.01)
    
    def test_final_verdict_logic(self):
        """Test final verdict logic"""
        # Both PASS
        gate_a = "PASS"
        gate_b = "PASS"
        final = "PASS" if (gate_a == "PASS" and gate_b == "PASS") else "FAIL"
        assert final == "PASS"
        
        # Gate A FAIL
        gate_a = "WARNING"
        gate_b = "PASS"
        final = "PASS" if (gate_a == "PASS" and gate_b == "PASS") else "FAIL"
        assert final == "FAIL"
        
        # Gate B FAIL
        gate_a = "PASS"
        gate_b = "FAIL"
        final = "PASS" if (gate_a == "PASS" and gate_b == "PASS") else "FAIL"
        assert final == "FAIL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
