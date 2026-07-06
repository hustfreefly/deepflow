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
                    if "research_experts" in output_path:
                        stage = "research"
                        task_key = "research"
            
            if "meta" in stage or "meta" in task_key:
                # Meta-Planner for data_pipeline domain
                return {
                    "schema_version": "2.0",
                    "task_profile": {
                        "domain": "data_pipeline",
                        "complexity": "high",
                        "risk_areas": ["p0_requirements", "cross_module_consistency"],
                    },
                    "experts": [
                        {"expert_name": "etl_expert", "domain": "etl", "focus_areas": ["batch data extraction and transformation"], "evaluation_lens": "data consistency and rollback strategies"},
                        {"expert_name": "streaming_expert", "domain": "streaming", "focus_areas": ["real-time stream processing"], "evaluation_lens": "low-latency data pipelines"},
                        {"expert_name": "data_quality_expert", "domain": "data_quality", "focus_areas": ["data validation and quality monitoring"], "evaluation_lens": "data quality and observability"},
                        {"expert_name": "infrastructure_expert", "domain": "infrastructure", "focus_areas": ["data infrastructure and scalability"], "evaluation_lens": "infrastructure scaling and reliability"}
                    ],
                    "gate_a": {
                        "weights": {
                            "completeness": 0.25,
                            "necessity": 0.25,
                            "alignment": 0.25,
                            "global_impact": 0.25,
                        },
                        "rationale": "Balanced across all dimensions for data_pipeline",
                    },
                    "gate_b": {
                        "dynamic_checks": [
                            {
                                "name": "P0 Requirement Coverage",
                                "description": "All P0 requirements must be covered",
                                "pass_criteria": "Each P0 REQ has at least one expert covering it",
                                "severity": "CRITICAL",
                                "reasoning": "P0 requirements are non-negotiable",
                            },
                            {
                                "name": "Domain Specific Check",
                                "description": "Domain-specific validation for data_pipeline",
                                "pass_criteria": "Domain-specific constraints are satisfied",
                                "severity": "CRITICAL",
                                "reasoning": "Domain-specific risks must be addressed",
                            },
                        ]
                    },
                    "verdict_policy": {
                        "warning_acceptable": False,
                        "min_gate_b_pass_rate": 1.0,
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
                        {"constraint_id": "C-001", "description": f"{domain} pipeline constraint", "priority": "MUST"},
                        {"constraint_id": "C-002", "description": f"{domain} data quality constraint", "priority": "SHOULD"},
                    ],
                    "risks": [{"risk_id": f"R-{domain}-001", "description": f"{domain} pipeline risk", "mitigation": "Mitigate"}],
                    "acceptance_criteria": [{"criterion_id": f"AC-{domain}-001", "description": f"{domain} pipeline AC", "verification_method": "Run test X"}],
                    "covered_req_ids": ["REQ-P0-001"],
                    "extensions": {"layer2_score": 0.85},
                }
            elif "convergence" in stage or "convergence" in task_key:
                return {
                    "schema_version": "2.0",
                    "unified_constraints": [
                        {"constraint_id": "C-001", "description": "Domain constraint 1 for data_pipeline", "priority": "MUST", "source_experts": ["expert_1"]},
                        {"constraint_id": "C-002", "description": "Domain constraint 2 for data_pipeline", "priority": "MUST", "source_experts": ["expert_2"]},
                    ],
                    "rejected_constraints": [],
                    "meta": {
                        "total_expert_plans": 4,
                        "total_input_constraints": 8,
                        "total_output_constraints": 2,
                        "merge_ratio": 0.25,
                    },
                    "covered_req_ids": ["REQ-P0-001", "REQ-P0-002"],
                    "verification_checklist": {
                        "checklist": [
                            {"check_id": "V-001", "constraint_id": "C-001", "verification_method": "automated test", "expected_result": "PASS"},
                            {"check_id": "V-002", "constraint_id": "C-002", "verification_method": "automated test", "expected_result": "PASS"},
                        ],
                        "total_checks": 2,
                    },
                }
            elif "harness" in stage or "harness" in task_key:
                return {
                    "schema_version": "2.0",
                    "gate_a": {
                        "scores": {"semantic_similarity": 0.87, "coverage": 0.85, "coherence": 0.88},
                        "reasoning": {"summary": "Gate A passed"},
                    },
                    "gate_b": {
                        "checks": [
                            {"check_id": "P0-001", "check_name": "P0 Requirement Coverage", "verdict": "PASS", "severity": "CRITICAL"},
                            {"check_id": "DOM-001", "check_name": "Domain Specific Check", "verdict": "PASS", "severity": "CRITICAL"},
                        ],
                    },
                    "final_verdict": {
                        "final_verdict": "PASS",
                        "confidence": 0.9,
                    },
                    "overall_verdict": "PASS",
                }
            elif "research" in stage:
                return {
                    "schema_version": "2.0",
                    "report": "## Executive Summary\nResearch summary for the domain.\n\n## Findings\n### F-001: Key finding one\nDetailed description.\n\n### F-002: Key finding two\nDetailed description.\n\n## Confidence\nConfidence score: 0.88\n\n## Related Constraints\n- C-001\n- C-002",
                    "executive_summary": "Research findings for the domain.",
                    "findings": [
                        {"id": "F-001", "description": "Key finding one: comprehensive analysis of data pipeline architecture patterns including stream processing and batch ETL optimization strategies, with emphasis on Apache Kafka and Flink for real-time processing and Spark for batch workloads in production environments", "sources": ["https://example.com"]},
                        {"id": "F-002", "description": "Key finding two: evaluation of data quality frameworks and monitoring systems for ensuring reliability and consistency across pipelines, including Great Expectations and Deequ for automated validation and anomaly detection in large-scale data systems", "sources": ["https://example.com"]},
                        {"id": "F-003", "description": "Key finding three: assessment of infrastructure scaling approaches for high-throughput data processing", "sources": ["https://example.com"]},
                    ],
                    "confidence_score": 0.88,
                    "related_constraints": ["C-001", "C-002"],
                    "covered_req_ids": ["REQ-P0-001"],
                }
            elif "_consolidation_llm" in output_path or ("consolidation" in stage and "research" in output_path):
                return {
                    "schema_version": "2.0",
                    "findings": [
                        {"description": "Key finding one", "tier": 1, "source_experts": ["expert_1"]},
                        {"description": "Key finding two", "tier": 1, "source_experts": ["expert_2"]},
                    ],
                    "consensus_points": ["Point 1", "Point 2"],
                    "divergence_points": [],
                    "risks": [{"description": "Risk one", "tier": 1, "mitigation": "Mitigate"}],
                    "recommendations": [{"description": "Recommendation one", "tier": 1, "rationale": "Rationale"}],
                }
            elif "_digest_output" in output_path or "digest" in task_key:
                return {
                    "schema_version": "2.0",
                    "total_findings": 2,
                    "high_relevance_count": 2,
                    "expert_summaries": {"expert_1": "Summary 1", "expert_2": "Summary 2"},
                    "findings_index": [
                        {
                            "finding_id": "F-001",
                            "expert_id": "expert_1",
                            "title": "Finding one",
                            "confidence": 0.88,
                            "relevance": "HIGH",
                            "design_implication": "Important implication",
                            "source_reference": "expert_1.md#F-001",
                            "detail": "Detailed analysis",
                        },
                        {
                            "finding_id": "F-002",
                            "expert_id": "expert_2",
                            "title": "Finding two",
                            "confidence": 0.85,
                            "relevance": "HIGH",
                            "design_implication": "Another implication",
                            "source_reference": "expert_2.md#F-002",
                            "detail": "Detailed analysis",
                        },
                    ],
                    "findings_detail": [
                        {"finding_id": "F-001", "detail": "Detailed analysis one"},
                        {"finding_id": "F-002", "detail": "Detailed analysis two"},
                    ],
                    "conflicts": [],
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
        # review_qc 模块已整合到 summary，保留旧 key 兼容
        assert result.get("review_qc") is not None or result["summary"] is not None
        
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
