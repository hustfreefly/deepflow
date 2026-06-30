"""
Golden Case 012 — DevOps / Infrastructure Architecture

验证 Planning/Research/ReviewQC 能处理运维/DevOps 场景
"""
import pytest
import json
from pathlib import Path

from domains.solution_pro.master_orchestrator import MasterOrchestrator
from domains.solution_pro.blackboard import BlackboardManager


class TestGoldenCase012:
    """Golden Case 012: DevOps / Infrastructure Architecture E2E"""
    
    @pytest.fixture
    def tmp_blackboard(self, tmp_path):
        return BlackboardManager(session_id="golden_case_012", base_dir=str(tmp_path))
    
    @pytest.fixture
    def devops_spawn_fn(self):
        """Mock spawn_fn for DevOps/infrastructure scenario"""
        def _spawn(task=None, output_path=None, **kwargs):
            # 兼容新旧两种调用方式
            if isinstance(task, dict):
                stage = task.get("stage", "")
                task_key = task.get("task_key", stage)
            else:
                stage = ""
                task_key = ""
                if output_path:
                    stage = output_path.split("/")[-1].replace(".json", "")
                    task_key = stage
            
            if "meta" in stage or "meta" in task_key:
                # Meta-Planner for DevOps/infrastructure domain
                return {
                    "schema_version": "2.0",
                    "domain": "devops",
                    "experts": [
                        {"expert_name": "kubernetes_expert", "domain": "kubernetes"},
                        {"expert_name": "ci_cd_expert", "domain": "ci_cd"},
                        {"expert_name": "monitoring_expert", "domain": "monitoring"},
                        {"expert_name": "security_expert", "domain": "security"},
                    ],
                    "gate_a_config": {"weights": {"layer1": 0.5, "layer2": 0.5}},
                    "gate_b_config": {
                        "critical_checks": [
                            {"check_id": "P0_REQ_COVERAGE", "method": "code"},
                            {"check_id": "INFRASTRUCTURE_RELIABILITY", "method": "code"},
                        ]
                    },
                }
            elif "expert" in stage or "expert" in task_key:
                expert_name = task_key if "_" in task_key else "general"
                domain = expert_name.replace("_expert", "")
                return {
                    "schema_version": "2.0",
                    "expert_name": expert_name,
                    "domain": domain,
                    "constraints": [
                        {"constraint_id": f"C-{domain}-001", "description": f"{domain} infrastructure constraint", "priority": "MUST"},
                        {"constraint_id": f"C-{domain}-002", "description": f"{domain} reliability constraint", "priority": "SHOULD"},
                    ],
                    "risks": [{"risk_id": f"R-{domain}-001", "description": f"{domain} infrastructure risk", "mitigation": "Mitigate"}],
                    "acceptance_criteria": [{"criterion_id": f"AC-{domain}-001", "description": f"{domain} infrastructure AC"}],
                    "covered_req_ids": ["REQ-P0-001"],
                    "extensions": {"layer2_score": 0.85},
                }
            elif "convergence" in stage or "convergence" in task_key:
                return {
                    "schema_version": "2.0",
                    "unified_constraints": {
                        "constraints": [
                            {"constraint_id": "C-001", "description": "Kubernetes orchestration constraint", "priority": "MUST", "source_experts": ["kubernetes_expert"]},
                            {"constraint_id": "C-002", "description": "CI/CD pipeline constraint", "priority": "MUST", "source_experts": ["ci_cd_expert"]},
                            {"constraint_id": "C-003", "description": "Monitoring and alerting constraint", "priority": "MUST", "source_experts": ["monitoring_expert"]},
                            {"constraint_id": "C-004", "description": "Security compliance constraint", "priority": "MUST", "source_experts": ["security_expert"]},
                        ],
                        "risk_areas": ["kubernetes", "ci_cd", "monitoring", "security"],
                    },
                    "verification_checklist": {"items": [
                        {"item_id": "V-001", "description": "Kubernetes cluster reliability"},
                        {"item_id": "V-002", "description": "CI/CD pipeline automation"},
                        {"item_id": "V-003", "description": "Monitoring coverage"},
                    ]},
                    "structured_requirements": {"requirements": [
                        {"req_id": "REQ-P0-001", "description": "Infrastructure as Code", "priority": "P0"},
                        {"req_id": "REQ-P0-002", "description": "Zero-downtime deployments", "priority": "P0"},
                    ]},
                    "semantic_verification": {"verdict": "PASS", "reasoning": "All DevOps domains covered"},
                }
            elif "harness" in stage or "harness" in task_key:
                return {
                    "schema_version": "2.0",
                    "gate_a_result": {"verdict": "PASS", "score": 0.90, "layer2_calibrated": True},
                    "gate_b_result": {"verdict": "PASS", "critical_pass_rate": 1.0},
                }
            elif "research" in stage:
                return {
                    "schema_version": "2.0",
                    "findings": [
                        {"id": "F-001", "description": "GitOps best practices with ArgoCD", "sources": ["https://example.com"]},
                        {"id": "F-002", "description": "Observability stack patterns", "sources": ["https://example.com"]},
                    ],
                    "confidence_score": 0.89,
                }
            elif "review" in stage or "fix" in stage:
                return {"schema_version": "2.0", "verdict": "PASS", "quality_score": 0.89}
            else:
                return {"status": "PASS"}
        
        return _spawn
    
    def test_devops_e2e(self, tmp_blackboard, devops_spawn_fn):
        """E2E: DevOps Infrastructure - 验证 Pipeline 能处理 DevOps 场景"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=devops_spawn_fn,
        )
        
        result = master.run(
            user_input="Design a cloud infrastructure automation platform with Kubernetes and CI/CD",
            config={
                "topic": "Cloud Infrastructure Automation Platform",
                "solution_type": "architecture",
                "domain": "devops",
            },
        )
        
        # Pipeline 应该完成
        assert result["status"] == "COMPLETE", f"Pipeline failed: {result}"
        assert result["planning"] is not None
        assert result["research"] is not None
        assert result["review_qc"] is not None
        
        # 验证 final_report
        assert result["final_report"] is not None
        assert result["final_report"]["topic"] == "Cloud Infrastructure Automation Platform"
    
    def test_devops_degradation_behavior(self, tmp_blackboard, devops_spawn_fn):
        """DevOps 测试：验证降级行为"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=devops_spawn_fn,
        )
        
        result = master.run(
            user_input="DevOps test",
            config={
                "topic": "DevOps Test",
                "domain": "devops",
            },
        )
        
        # Pipeline 应该完成
        assert result["status"] == "COMPLETE"
        # 验证 final_report 存在
        assert result["final_report"] is not None
    
    def test_devops_final_report_structure(self, tmp_blackboard, devops_spawn_fn):
        """DevOps 测试：验证最终报告结构"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=devops_spawn_fn,
        )
        
        result = master.run(
            user_input="DevOps structure test",
            config={"topic": "DevOps Structure", "domain": "devops"},
        )
        
        # 验证最终报告结构
        assert result["final_report"] is not None
        assert "planning_summary" in result["final_report"]
        assert "research_summary" in result["final_report"]
        assert "quality_assessment" in result["final_report"]
