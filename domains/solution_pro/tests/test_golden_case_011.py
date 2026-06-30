"""
Golden Case 011 — Data Pipeline / ETL Architecture

验证 Planning/Research/ReviewQC 能处理数据分析/ETL 场景
"""
import pytest
import json
from pathlib import Path

from domains.solution_pro.master_orchestrator import MasterOrchestrator
from domains.solution_pro.blackboard import BlackboardManager


class TestGoldenCase011:
    """Golden Case 011: Data Pipeline / ETL Architecture E2E"""
    
    @pytest.fixture
    def tmp_blackboard(self, tmp_path):
        return BlackboardManager(session_id="golden_case_011", base_dir=str(tmp_path))
    
    @pytest.fixture
    def data_pipeline_spawn_fn(self):
        """Mock spawn_fn for data pipeline/ETL scenario"""
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
                # Meta-Planner for data pipeline domain
                return {
                    "schema_version": "2.0",
                    "domain": "data_pipeline",
                    "experts": [
                        {"expert_name": "etl_expert", "domain": "etl"},
                        {"expert_name": "streaming_expert", "domain": "streaming"},
                        {"expert_name": "data_quality_expert", "domain": "data_quality"},
                        {"expert_name": "infrastructure_expert", "domain": "infrastructure"},
                    ],
                    "gate_a_config": {"weights": {"layer1": 0.5, "layer2": 0.5}},
                    "gate_b_config": {
                        "critical_checks": [
                            {"check_id": "P0_REQ_COVERAGE", "method": "code"},
                            {"check_id": "DATA_PIPELINE_RELIABILITY", "method": "code"},
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
                        {"constraint_id": f"C-{domain}-001", "description": f"{domain} pipeline constraint", "priority": "MUST"},
                        {"constraint_id": f"C-{domain}-002", "description": f"{domain} data quality constraint", "priority": "SHOULD"},
                    ],
                    "risks": [{"risk_id": f"R-{domain}-001", "description": f"{domain} pipeline risk", "mitigation": "Mitigate"}],
                    "acceptance_criteria": [{"criterion_id": f"AC-{domain}-001", "description": f"{domain} pipeline AC"}],
                    "covered_req_ids": ["REQ-P0-001"],
                    "extensions": {"layer2_score": 0.85},
                }
            elif "convergence" in stage or "convergence" in task_key:
                return {
                    "schema_version": "2.0",
                    "unified_constraints": {
                        "constraints": [
                            {"constraint_id": "C-001", "description": "ETL batch processing constraint", "priority": "MUST", "source_experts": ["etl_expert"]},
                            {"constraint_id": "C-002", "description": "Real-time streaming constraint", "priority": "MUST", "source_experts": ["streaming_expert"]},
                            {"constraint_id": "C-003", "description": "Data quality constraint", "priority": "MUST", "source_experts": ["data_quality_expert"]},
                            {"constraint_id": "C-004", "description": "Infrastructure scalability constraint", "priority": "MUST", "source_experts": ["infrastructure_expert"]},
                        ],
                        "risk_areas": ["etl", "streaming", "data_quality", "infrastructure"],
                    },
                    "verification_checklist": {"items": [
                        {"item_id": "V-001", "description": "Batch processing reliability"},
                        {"item_id": "V-002", "description": "Stream processing latency"},
                        {"item_id": "V-003", "description": "Data lineage tracking"},
                    ]},
                    "structured_requirements": {"requirements": [
                        {"req_id": "REQ-P0-001", "description": "Real-time data ingestion", "priority": "P0"},
                        {"req_id": "REQ-P0-002", "description": "Data quality validation", "priority": "P0"},
                    ]},
                    "semantic_verification": {"verdict": "PASS", "reasoning": "All data pipeline domains covered"},
                }
            elif "harness" in stage or "harness" in task_key:
                return {
                    "schema_version": "2.0",
                    "gate_a_result": {"verdict": "PASS", "score": 0.89, "layer2_calibrated": True},
                    "gate_b_result": {"verdict": "PASS", "critical_pass_rate": 1.0},
                }
            elif "research" in stage:
                return {
                    "schema_version": "2.0",
                    "findings": [
                        {"id": "F-001", "description": "Apache Kafka vs Pulsar comparison", "sources": ["https://example.com"]},
                        {"id": "F-002", "description": "Data lakehouse architecture patterns", "sources": ["https://example.com"]},
                    ],
                    "confidence_score": 0.87,
                }
            elif "review" in stage or "fix" in stage:
                return {"schema_version": "2.0", "verdict": "PASS", "quality_score": 0.88}
            else:
                return {"status": "PASS"}
        
        return _spawn
    
    def test_data_pipeline_e2e(self, tmp_blackboard, data_pipeline_spawn_fn):
        """E2E: Data Pipeline Architecture - 验证 Pipeline 能处理数据分析场景"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=data_pipeline_spawn_fn,
        )
        
        result = master.run(
            user_input="Design a real-time data analytics platform with batch and streaming processing",
            config={
                "topic": "Real-time Data Analytics Platform",
                "solution_type": "technical",
                "domain": "data_pipeline",
            },
        )
        
        # Pipeline 应该完成
        assert result["status"] == "COMPLETE", f"Pipeline failed: {result}"
        assert result["planning"] is not None
        assert result["research"] is not None
        assert result["review_qc"] is not None
        
        # 验证 final_report
        assert result["final_report"] is not None
        assert result["final_report"]["topic"] == "Real-time Data Analytics Platform"
    
    def test_data_pipeline_degradation_behavior(self, tmp_blackboard, data_pipeline_spawn_fn):
        """数据管道测试：验证降级行为"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=data_pipeline_spawn_fn,
        )
        
        result = master.run(
            user_input="Data pipeline test",
            config={
                "topic": "Data Pipeline Test",
                "domain": "data_pipeline",
            },
        )
        
        # Pipeline 应该完成
        assert result["status"] == "COMPLETE"
        # 验证 final_report 存在
        assert result["final_report"] is not None
    
    def test_data_pipeline_final_report_structure(self, tmp_blackboard, data_pipeline_spawn_fn):
        """数据管道测试：验证最终报告结构"""
        master = MasterOrchestrator(
            blackboard=tmp_blackboard,
            spawn_fn=data_pipeline_spawn_fn,
        )
        
        result = master.run(
            user_input="Data pipeline structure test",
            config={"topic": "Data Pipeline Structure", "domain": "data_pipeline"},
        )
        
        # 验证最终报告结构
        assert result["final_report"] is not None
        assert "planning_summary" in result["final_report"]
        assert "research_summary" in result["final_report"]
        assert "quality_assessment" in result["final_report"]
