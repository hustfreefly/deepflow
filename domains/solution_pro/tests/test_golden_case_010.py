"""
Golden Case 010 — Frontend/Mobile App Architecture

验证 Planning/Research/ReviewQC 能处理非后端场景（移动端 App）
"""
import pytest
import json
from pathlib import Path

from domains.solution_pro.master_orchestrator import MasterOrchestrator
from domains.solution_pro.blackboard import BlackboardManager


class TestGoldenCase010:
    """Golden Case 010: Frontend/Mobile App E2E"""
    
    @pytest.fixture
    def tmp_blackboard(self, tmp_path):
        return BlackboardManager(session_id="golden_case_010", base_dir=str(tmp_path))
    
    @pytest.fixture
    def mobile_app_spawn_fn(self):
        """Mock spawn_fn for mobile app scenario"""
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
                # Meta-Planner for mobile app domain
                return {
                    "schema_version": "2.0",
                    "domain": "mobile_app",
                    "experts": [
                        {"expert_name": "ios_expert", "domain": "ios"},
                        {"expert_name": "android_expert", "domain": "android"},
                        {"expert_name": "ux_expert", "domain": "ux_design"},
                        {"expert_name": "security_expert", "domain": "security"},
                    ],
                    "gate_a_config": {"weights": {"layer1": 0.5, "layer2": 0.5}},
                    "gate_b_config": {
                        "critical_checks": [
                            {"check_id": "P0_REQ_COVERAGE", "method": "code"},
                            {"check_id": "MOBILE_PLATFORM_COMPATIBILITY", "method": "code"},
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
                        {"constraint_id": f"C-{domain}-001", "description": f"{domain} mobile constraint", "priority": "MUST"},
                        {"constraint_id": f"C-{domain}-002", "description": f"{domain} performance constraint", "priority": "SHOULD"},
                    ],
                    "risks": [{"risk_id": f"R-{domain}-001", "description": f"{domain} mobile risk", "mitigation": "Mitigate"}],
                    "acceptance_criteria": [{"criterion_id": f"AC-{domain}-001", "description": f"{domain} mobile AC"}],
                    "covered_req_ids": ["REQ-P0-001"],
                    "extensions": {"layer2_score": 0.85},
                }
            elif "convergence" in stage or "convergence" in task_key:
                return {
                    "schema_version": "2.0",
                    "unified_constraints": {
                        "constraints": [
                            {"constraint_id": "C-001", "description": "iOS native constraint", "priority": "MUST", "source_experts": ["ios_expert"]},
                            {"constraint_id": "C-002", "description": "Android native constraint", "priority": "MUST", "source_experts": ["android_expert"]},
                            {"constraint_id": "C-003", "description": "UX design constraint", "priority": "MUST", "source_experts": ["ux_expert"]},
                            {"constraint_id": "C-004", "description": "Security constraint", "priority": "MUST", "source_experts": ["security_expert"]},
                        ],
                        "risk_areas": ["ios", "android", "ux", "security"],
                    },
                    "verification_checklist": {"items": [
                        {"item_id": "V-001", "description": "iOS App Store compliance"},
                        {"item_id": "V-002", "description": "Android Play Store compliance"},
                        {"item_id": "V-003", "description": "Cross-platform UX consistency"},
                    ]},
                    "structured_requirements": {"requirements": [
                        {"req_id": "REQ-P0-001", "description": "Cross-platform mobile app", "priority": "P0"},
                        {"req_id": "REQ-P0-002", "description": "Offline-first architecture", "priority": "P0"},
                    ]},
                    "semantic_verification": {"verdict": "PASS", "reasoning": "All mobile domains covered"},
                }
            elif "harness" in stage or "harness" in task_key:
                return {
                    "schema_version": "2.0",
                    "gate_a_result": {"verdict": "PASS", "score": 0.87, "layer2_calibrated": True},
                    "gate_b_result": {"verdict": "PASS", "critical_pass_rate": 1.0},
                }
            elif "research" in stage:
                return {
                    "schema_version": "2.0",
                    "findings": [
                        {"id": "F-001", "description": "React Native vs Flutter comparison", "sources": ["https://example.com"]},
                        {"id": "F-002", "description": "Mobile offline-first patterns", "sources": ["https://example.com"]},
                    ],
                    "confidence_score": 0.88,
                }
            elif "review" in stage or "fix" in stage:
                return {"schema_version": "2.0", "verdict": "PASS", "quality_score": 0.86}
            else:
                return {"status": "PASS"}
        
        return _spawn
    
    def test_mobile_app_e2e(self, tmp_blackboard, mobile_app_spawn_fn):
        """E2E: Mobile App Architecture - 验证 Pipeline 能处理移动端场景"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=mobile_app_spawn_fn,
        )
        
        result = master.run(
            user_input="Design a cross-platform mobile banking app with offline-first architecture",
            config={
                "topic": "Mobile Banking App",
                "solution_type": "architecture",
                "domain": "mobile_app",
            },
        )
        
        # Pipeline 应该完成
        assert result["status"] == "COMPLETE", f"Pipeline failed: {result}"
        assert result["planning"] is not None
        assert result["research"] is not None
        assert result["review_qc"] is not None
        
        # 验证 final_report
        assert result["final_report"] is not None
        assert result["final_report"]["topic"] == "Mobile Banking App"
    
    def test_mobile_app_degradation_behavior(self, tmp_blackboard, mobile_app_spawn_fn):
        """移动端测试：验证降级行为"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=mobile_app_spawn_fn,
        )
        
        result = master.run(
            user_input="Mobile app test",
            config={
                "topic": "Mobile App Test",
                "domain": "mobile_app",
            },
        )
        
        # Pipeline 应该完成
        assert result["status"] == "COMPLETE"
        # 验证 final_report 存在
        assert result["final_report"] is not None
    
    def test_mobile_app_final_report_structure(self, tmp_blackboard, mobile_app_spawn_fn):
        """移动端测试：验证最终报告结构"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=mobile_app_spawn_fn,
        )
        
        result = master.run(
            user_input="Mobile app structure test",
            config={"topic": "Mobile App Structure", "domain": "mobile_app"},
        )
        
        # 验证最终报告结构
        assert result["final_report"] is not None
        assert "planning_summary" in result["final_report"]
        assert "research_summary" in result["final_report"]
        assert "quality_assessment" in result["final_report"]
