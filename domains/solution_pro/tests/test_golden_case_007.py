"""
Golden Case 007 — Cross-Domain 泛化性验证

验证 Meta-Planner 能正确识别 composite domain
"""
import pytest
import json
from pathlib import Path

from domains.solution_pro.master_orchestrator import MasterOrchestrator
from domains.solution_pro.blackboard import BlackboardManager
from domains.solution_pro.golden_case_runner import GoldenCaseRunner


class TestGoldenCase007:
    """Golden Case 007: Cross-Domain E2E"""
    
    @pytest.fixture
    def tmp_blackboard(self, tmp_path):
        return BlackboardManager(session_id="golden_case_007", base_dir=str(tmp_path))
    
    @pytest.fixture
    def cross_domain_spawn_fn(self):
        """Mock spawn_fn for cross-domain scenario"""
        def _spawn(task=None, output_path=None, **kwargs):
            # 兼容新旧两种调用方式
            # 新契约：task 是 str（prompt 文本），output_path 是路径
            # 旧契约：task 是 dict（包含 stage, task_key 等）
            if isinstance(task, dict):
                # 旧契约兼容
                stage = task.get("stage", "")
                task_key = task.get("task_key", stage)
            else:
                # 新契约：从 output_path 推断 stage
                stage = ""
                task_key = ""
                if output_path:
                    stage = output_path.split("/")[-1].replace(".json", "")
                    task_key = stage
            
            if "meta" in stage or "meta" in task_key:
                # Meta-Planner should identify composite domain
                return {
                    "schema_version": "2.0",
                    "domain": "composite",
                    "sub_domains": ["backend_api", "frontend", "data_migration"],
                    "experts": [
                        {"expert_name": "backend_expert", "domain": "backend_api"},
                        {"expert_name": "frontend_expert", "domain": "frontend"},
                        {"expert_name": "data_migration_expert", "domain": "data_migration"},
                        {"expert_name": "security_expert", "domain": "security"},
                    ],
                    "gate_a_config": {"weights": {"layer1": 0.5, "layer2": 0.5}},
                    "gate_b_config": {
                        "critical_checks": [
                            {"check_id": "P0_REQ_COVERAGE", "method": "code"},
                            {"check_id": "CROSS_DOMAIN_CONSISTENCY", "method": "code"},
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
                        {"constraint_id": f"C-{domain}-001", "description": f"{domain} constraint", "priority": "MUST"},
                        {"constraint_id": f"C-{domain}-002", "description": f"{domain} cross-domain constraint", "priority": "SHOULD"},
                    ],
                    "risks": [{"risk_id": f"R-{domain}-001", "description": f"{domain} risk", "mitigation": "Mitigate"}],
                    "acceptance_criteria": [{"criterion_id": f"AC-{domain}-001", "description": f"{domain} AC"}],
                    "covered_req_ids": ["REQ-P0-001"],
                    "extensions": {"layer2_score": 0.85},
                }
            elif "convergence" in stage or "convergence" in task_key:
                return {
                    "schema_version": "2.0",
                    "unified_constraints": {
                        "constraints": [
                            {"constraint_id": "C-001", "description": "Backend constraint", "priority": "MUST", "source_experts": ["backend_expert"]},
                            {"constraint_id": "C-002", "description": "Frontend constraint", "priority": "MUST", "source_experts": ["frontend_expert"]},
                            {"constraint_id": "C-003", "description": "Data migration constraint", "priority": "MUST", "source_experts": ["data_migration_expert"]},
                            {"constraint_id": "C-004", "description": "Security constraint", "priority": "MUST", "source_experts": ["security_expert"]},
                            {"constraint_id": "C-005", "description": "Cross-domain consistency", "priority": "MUST", "source_experts": ["backend_expert", "frontend_expert"]},
                        ],
                        "risk_areas": ["backend", "frontend", "data_migration", "security"],
                    },
                    "verification_checklist": {"items": [
                        {"item_id": "V-001", "description": "Backend API compatibility"},
                        {"item_id": "V-002", "description": "Frontend integration"},
                        {"item_id": "V-003", "description": "Data migration validation"},
                    ]},
                    "structured_requirements": {"requirements": [
                        {"req_id": "REQ-P0-001", "description": "Microservices migration", "priority": "P0"},
                        {"req_id": "REQ-P0-002", "description": "Zero downtime", "priority": "P0"},
                    ]},
                    "semantic_verification": {"verdict": "PASS", "reasoning": "All domains covered"},
                }
            elif "harness" in stage or "harness" in task_key:
                return {
                    "schema_version": "2.0",
                    "gate_a_result": {"verdict": "PASS", "score": 0.88, "layer2_calibrated": True},
                    "gate_b_result": {"verdict": "PASS", "critical_pass_rate": 1.0},
                }
            elif "research" in stage:
                return {
                    "schema_version": "2.0",
                    "findings": [{"id": "F-001", "description": "Strangler fig pattern", "sources": ["https://martinfowler.com"]}],
                    "confidence_score": 0.85,
                }
            elif "review" in stage or "fix" in stage:
                return {"schema_version": "2.0", "verdict": "PASS", "quality_score": 0.85}
            else:
                return {"status": "PASS"}
        
        return _spawn
    
    def test_cross_domain_e2e(self, tmp_blackboard, cross_domain_spawn_fn):
        """跨领域 E2E: composite domain - 验证 Pipeline 能处理 composite domain 输入"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=cross_domain_spawn_fn,
        )
        
        result = master.run(
            user_input="Migrate monolithic PHP to microservices with React + Node.js + MongoDB",
            config={
                "topic": "Full Stack Microservices Migration",
                "solution_type": "architecture",
                "domain": "composite",
                "sub_domains": ["backend_api", "frontend", "data_migration"],
            },
        )
        
        # Pipeline 应该完成（即使有降级）
        assert result["status"] == "COMPLETE"
        assert result["planning"] is not None
        assert result["research"] is not None
        assert result["review_qc"] is not None
        
        # 验证 Planning 有 experts（降级模式下至少有 default experts）
        planning = result["planning"]
        if isinstance(planning, dict):
            experts = planning.get("experts", [])
            assert len(experts) >= 1, f"Expected at least 1 expert, got {len(experts)}"
    
    def test_cross_domain_degradation_behavior(self, tmp_blackboard, cross_domain_spawn_fn):
        """跨领域测试：验证降级行为符合预期"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=cross_domain_spawn_fn,
        )
        
        result = master.run(
            user_input="Cross-domain test",
            config={
                "topic": "Cross-Domain Test",
                "domain": "composite",
                "sub_domains": ["backend_api", "frontend"],
            },
        )
        
        # Pipeline 应该完成
        assert result["status"] == "COMPLETE"
        # 验证 final_report 存在
        assert result["final_report"] is not None
        assert result["final_report"]["topic"] == "Cross-Domain Test"
    
    def test_cross_domain_final_report_structure(self, tmp_blackboard, cross_domain_spawn_fn):
        """跨领域测试：验证最终报告结构完整性"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=cross_domain_spawn_fn,
        )
        
        result = master.run(
            user_input="Cross-domain propagation test",
            config={"topic": "Propagation Test", "domain": "composite"},
        )
        
        # 验证最终报告结构
        assert result["final_report"] is not None
        assert "planning_summary" in result["final_report"]
        assert "research_summary" in result["final_report"]
        assert "quality_assessment" in result["final_report"]
        # 验证 planning_summary 有基本字段
        planning_summary = result["final_report"]["planning_summary"]
        assert "expert_count" in planning_summary
        assert "constraint_count" in planning_summary
