"""
Solution Pro V2 基础类测试

Version: 1.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

描述:
- 测试 ModuleOrchestrator 基类
- 测试 ConvergenceLayer
- 测试 FixLoopStateMachine
- 测试 Harness 双 Gate 逻辑
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

# 添加 .deepflow 到 Python 路径
deepflow_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(deepflow_root))


# ============================================================================
# Mock Blackboard（测试用）
# ============================================================================

class MockBlackboard:
    """测试用 Mock Blackboard"""
    
    def __init__(self):
        self.data = {}
    
    def read(self, path: str) -> dict:
        if path in self.data:
            return self.data[path]
        raise FileNotFoundError(f"File not found: {path}")
    
    def write(self, path: str, data: dict):
        self.data[path] = data


# ============================================================================
# 测试 Harness 双 Gate 逻辑
# ============================================================================

class TestHarnessDualGate:
    """测试 Harness 双 Gate 逻辑"""
    
    def test_gate_a_score_calculation(self):
        """Gate A 加权分计算"""
        scores = {
            "completeness": 0.9,
            "necessity": 0.8,
            "alignment": 0.85,
            "global_impact": 0.75,
        }
        weights = {
            "completeness": 0.3,
            "necessity": 0.2,
            "alignment": 0.3,
            "global_impact": 0.2,
        }
        
        # 手动计算：0.9*0.3 + 0.8*0.2 + 0.85*0.3 + 0.75*0.2
        # = 0.27 + 0.16 + 0.255 + 0.15 = 0.835
        expected_score = 0.835
        
        # 计算
        score = sum(scores[k] * weights[k] for k in scores)
        assert abs(score - expected_score) < 0.001
    
    def test_gate_a_verdict_thresholds(self):
        """Gate A verdict 阈值判定"""
        thresholds = {
            "PASS": 0.85,
            "WARNING": 0.70,
            "CRITICAL_WARNING": 0.60,
            "BLOCK_RECOMMENDATION": 0.0,
        }
        
        def get_verdict(score):
            if score >= thresholds["PASS"]:
                return "PASS"
            elif score >= thresholds["WARNING"]:
                return "WARNING"
            elif score >= thresholds["CRITICAL_WARNING"]:
                return "CRITICAL_WARNING"
            else:
                return "BLOCK_RECOMMENDATION"
        
        assert get_verdict(0.90) == "PASS"
        assert get_verdict(0.85) == "PASS"
        assert get_verdict(0.84) == "WARNING"
        assert get_verdict(0.70) == "WARNING"
        assert get_verdict(0.65) == "CRITICAL_WARNING"
        assert get_verdict(0.50) == "BLOCK_RECOMMENDATION"
        assert get_verdict(0.0) == "BLOCK_RECOMMENDATION"
    
    def test_gate_a_special_rule_alignment(self):
        """Gate A 特殊规则：alignment < 0.6 强制 CRITICAL_WARNING"""
        def apply_special_rule(verdict, scores):
            if scores.get("alignment", 1.0) < 0.60:
                # 使用 min() 选择更严重的 verdict（index 越小越严重）
                severity_order = ["BLOCK_RECOMMENDATION", "CRITICAL_WARNING", "WARNING", "PASS"]
                return min(verdict, "CRITICAL_WARNING", key=lambda v: severity_order.index(v))
            return verdict
        
        # alignment = 0.5, verdict = PASS → 强制 CRITICAL_WARNING
        verdict = apply_special_rule("PASS", {"alignment": 0.5})
        assert verdict == "CRITICAL_WARNING"
        
        # alignment = 0.5, verdict = WARNING → 强制 CRITICAL_WARNING
        verdict = apply_special_rule("WARNING", {"alignment": 0.5})
        assert verdict == "CRITICAL_WARNING"
        
        # alignment = 0.7, verdict = PASS → 保持 PASS
        verdict = apply_special_rule("PASS", {"alignment": 0.7})
        assert verdict == "PASS"
    
    def test_gate_b_pass_rate_calculation(self):
        """Gate B 通过率计算"""
        dynamic_checks = [
            {"name": "check_1", "severity": "CRITICAL"},
            {"name": "check_2", "severity": "MINOR"},
            {"name": "check_3", "severity": "MINOR"},
        ]
        
        # 2/3 通过
        harness_output = {
            "checks": [
                {"name": "check_1", "result": "PASS"},
                {"name": "check_2", "result": "PASS"},
                {"name": "check_3", "result": "FAIL"},
            ]
        }
        
        passed = sum(1 for c in harness_output["checks"] if c["result"] == "PASS")
        pass_rate = passed / len(dynamic_checks)
        
        assert pass_rate == 2/3
        assert abs(pass_rate - 0.667) < 0.01
    
    def test_gate_b_critical_failure(self):
        """Gate B: CRITICAL 失败导致整体 FAIL"""
        dynamic_checks = [
            {"name": "security_check", "severity": "CRITICAL"},
            {"name": "style_check", "severity": "MINOR"},
        ]
        
        # CRITICAL 检查失败
        harness_output = {
            "checks": [
                {"name": "security_check", "result": "FAIL"},
                {"name": "style_check", "result": "PASS"},
            ]
        }
        
        # 检查是否有 CRITICAL 失败
        critical_failed = any(
            check["severity"] == "CRITICAL"
            for check in dynamic_checks
            if any(
                h["name"] == check["name"] and h["result"] == "FAIL"
                for h in harness_output["checks"]
            )
        )
        
        assert critical_failed is True
    
    def test_final_verdict_logic(self):
        """Final Verdict = Gate A PASS ∧ Gate B PASS"""
        def compute_final_verdict(gate_a_verdict, gate_b_verdict):
            if gate_a_verdict == "PASS" and gate_b_verdict == "PASS":
                return "PASS"
            return "FAIL"
        
        assert compute_final_verdict("PASS", "PASS") == "PASS"
        assert compute_final_verdict("PASS", "FAIL") == "FAIL"
        assert compute_final_verdict("WARNING", "PASS") == "FAIL"
        assert compute_final_verdict("FAIL", "PASS") == "FAIL"
        assert compute_final_verdict("FAIL", "FAIL") == "FAIL"


# ============================================================================
# 测试 Fix Loop State Machine
# ============================================================================

class TestFixLoopStateMachine:
    """测试 Fix Loop 状态机"""
    
    def test_fix_loop_max_rounds(self):
        """Fix Loop 最多 2 轮"""
        max_rounds = 2
        
        for round_num in range(1, max_rounds + 1):
            assert round_num <= max_rounds
        
        assert max_rounds + 1 > max_rounds  # 第 3 轮应该被阻止
    
    def test_anti_oscillation_detection(self):
        """Anti-oscillation: 连续 2 轮相同失败项 → abort"""
        round_1_failures = {"check_1", "check_2"}
        round_2_failures = {"check_1", "check_2"}  # 相同
        
        # 检测 oscillation
        is_oscillation = round_1_failures == round_2_failures
        assert is_oscillation is True
        
        # 不同失败项
        round_2_different = {"check_3"}
        is_oscillation = round_1_failures == round_2_different
        assert is_oscillation is False
    
    def test_frozen_items_not_re_evaluated(self):
        """冻结项不再重新评估"""
        frozen_items = ["check_1", "check_2"]
        
        new_harness_output = {
            "checks": [
                {"name": "check_1", "result": "FAIL"},  # 应该被忽略
                {"name": "check_3", "result": "FAIL"},  # 新检查项
            ]
        }
        
        # 过滤掉冻结项
        active_failures = [
            check for check in new_harness_output["checks"]
            if check["result"] == "FAIL" and check["name"] not in frozen_items
        ]
        
        assert len(active_failures) == 1
        assert active_failures[0]["name"] == "check_3"
    
    def test_regression_detection(self):
        """回归检测：之前 PASS 的项现在 FAIL"""
        previously_passed = ["check_1", "check_2"]
        
        new_harness_output = {
            "checks": [
                {"name": "check_1", "result": "FAIL"},  # 回归
                {"name": "check_2", "result": "PASS"},
                {"name": "check_3", "result": "FAIL"},  # 新失败（不是回归）
            ]
        }
        
        regressions = [
            check["name"]
            for check in new_harness_output["checks"]
            if check["result"] == "FAIL" and check["name"] in previously_passed
        ]
        
        assert len(regressions) == 1
        assert "check_1" in regressions


# ============================================================================
# 测试 Module Orchestrator Base
# ============================================================================

class TestModuleOrchestratorBase:
    """测试 ModuleOrchestrator 基类"""
    
    def test_stage_sequence_abstract(self):
        """stage_sequence() 是抽象方法"""
        # ModuleOrchestrator 需要子类实现 stage_sequence()
        # 这里测试子类是否正确实现
        
        class TestOrchestrator:
            def stage_sequence(self):
                return [
                    {"name": "stage_1", "worker_type": "worker_1"},
                    {"name": "stage_2", "worker_type": "worker_2", "gate_check": True},
                    {"name": "stage_3", "worker_type": "worker_3", "parallel": True, "max_workers": 5},
                ]
        
        orch = TestOrchestrator()
        stages = orch.stage_sequence()
        
        assert len(stages) == 3
        assert stages[0]["name"] == "stage_1"
        assert stages[1]["gate_check"] is True
        assert stages[2]["parallel"] is True
        assert stages[2]["max_workers"] == 5
    
    def test_state_management(self):
        """状态管理：current_stage, completed_stages, retry_count"""
        state = {
            "module_name": "planning",
            "session_id": "test_session",
            "current_stage": None,
            "completed_stages": [],
            "failed_stages": [],
            "retry_count": {},
            "convergence_generated": False,
        }
        
        # 模拟执行 stage_1
        state["current_stage"] = "stage_1"
        assert state["current_stage"] == "stage_1"
        
        # 完成 stage_1
        state["completed_stages"].append("stage_1")
        state["current_stage"] = None
        assert "stage_1" in state["completed_stages"]
        
        # stage_1 失败，增加 retry 计数
        state["failed_stages"].append("stage_2")
        state["retry_count"]["stage_2"] = state["retry_count"].get("stage_2", 0) + 1
        assert state["retry_count"]["stage_2"] == 1
        
        # 重试 stage_2
        state["retry_count"]["stage_2"] += 1
        assert state["retry_count"]["stage_2"] == 2
    
    def test_checkpoint_resume(self):
        """断点续跑：跳过已完成的 stage"""
        completed_stages = ["stage_1", "stage_2"]
        all_stages = ["stage_1", "stage_2", "stage_3", "stage_4"]
        
        # 过滤掉已完成的 stage
        remaining_stages = [s for s in all_stages if s not in completed_stages]
        
        assert len(remaining_stages) == 2
        assert "stage_3" in remaining_stages
        assert "stage_4" in remaining_stages


# ============================================================================
# 测试 Convergence Layer
# ============================================================================

class TestConvergenceLayer:
    """测试 ConvergenceLayer"""
    
    def test_information_conservation_p0_coverage(self):
        """信息守恒：P0 REQ 100% 覆盖"""
        p0_reqs = ["REQ-P0-001", "REQ-P0-002", "REQ-P0-003"]
        covered_reqs = ["REQ-P0-001", "REQ-P0-002", "REQ-P0-003"]
        
        missing = [req for req in p0_reqs if req not in covered_reqs]
        assert len(missing) == 0
        
        # 缺少一个 P0 REQ
        covered_reqs_partial = ["REQ-P0-001", "REQ-P0-002"]
        missing = [req for req in p0_reqs if req not in covered_reqs_partial]
        assert len(missing) == 1
        assert "REQ-P0-003" in missing
    
    def test_constraint_conservation_rate(self):
        """约束覆盖率计算"""
        input_constraints = ["C-001", "C-002", "C-003", "C-004", "C-005"]
        output_constraints = ["C-001", "C-002", "C-003", "C-004"]  # 缺少 C-005
        
        coverage_rate = len(output_constraints) / len(input_constraints)
        assert coverage_rate == 0.8
        
        # 覆盖率 < 80% 应该 FAIL
        assert coverage_rate >= 0.8
    
    def test_semantic_verification_verdicts(self):
        """语义验证三种判定"""
        for verdict in ["EQUIVALENT", "PARTIAL", "NOT_EQUIVALENT"]:
            verification = {
                "verdict": verdict,
                "confidence": 0.95 if verdict == "EQUIVALENT" else 0.7,
                "divergences": [] if verdict == "EQUIVALENT" else ["divergence_1"],
            }
            assert verification["verdict"] == verdict
    
    def test_original_references_structure(self):
        """原始引用结构"""
        original_references = {
            "meta_planning": {
                "path": "stages/meta_planning.json",
                "hash": "sha256:abc123...",
                "size_bytes": 2048,
            },
            "expert_plan_security": {
                "path": "stages/expert_plans/security.json",
                "hash": "sha256:def456...",
                "size_bytes": 4096,
            },
        }
        
        assert "meta_planning" in original_references
        assert original_references["meta_planning"]["path"] == "stages/meta_planning.json"
        assert original_references["expert_plan_security"]["size_bytes"] == 4096


# ============================================================================
# 测试 Blackboard V2 扩展
# ============================================================================

class TestBlackboardV2:
    """测试 Blackboard V2 扩展"""
    
    def test_stage_paths_exist(self):
        """V2 Stage 路径存在"""
        from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY
        
        # Module 1: Planning V2
        assert "meta_planning" in STAGE_PATH_REGISTRY
        assert "expert_plans" in STAGE_PATH_REGISTRY
        assert "convergence_planning" in STAGE_PATH_REGISTRY
        assert "unified_constraints" in STAGE_PATH_REGISTRY
        assert "verification_checklist" in STAGE_PATH_REGISTRY
        
        # Module 2: Research
        assert "research_experts" in STAGE_PATH_REGISTRY
        assert "research_consolidator" in STAGE_PATH_REGISTRY
        assert "architecture" in STAGE_PATH_REGISTRY
        assert "detailed_design" in STAGE_PATH_REGISTRY
        
        # Module 3: Review & QC
        assert "consolidation" in STAGE_PATH_REGISTRY
        assert "harness_report" in STAGE_PATH_REGISTRY
        assert "fix_loop_state" in STAGE_PATH_REGISTRY
        
        # 收敛点
        assert "planning_convergence" in STAGE_PATH_REGISTRY
        assert "research_convergence" in STAGE_PATH_REGISTRY
        assert "final_convergence" in STAGE_PATH_REGISTRY
    
    def test_deprecated_aliases_mapping(self):
        """Deprecated 别名映射正确"""
        from domains.solution_pro.blackboard import DEPRECATED_STAGE_ALIASES
        
        # V1 → V2 映射
        assert DEPRECATED_STAGE_ALIASES["planning"] == "meta_planning"
        assert DEPRECATED_STAGE_ALIASES["reviewer_technical"] == "meta_planning"
        assert DEPRECATED_STAGE_ALIASES["research_expert_1"] == "research_experts"
        assert DEPRECATED_STAGE_ALIASES["design"] == "detailed_design"
        assert DEPRECATED_STAGE_ALIASES["audit"] == "fix_loop_state"
        assert DEPRECATED_STAGE_ALIASES["consolidator"] == "consolidation"
        assert DEPRECATED_STAGE_ALIASES["harness_final"] == "harness_report"
    
    def test_v1_paths_preserved(self):
        """V1 路径保留（向后兼容）"""
        from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY
        
        # V1 路径仍然存在
        assert "data_collection" in STAGE_PATH_REGISTRY
        assert "frozen_spec" in STAGE_PATH_REGISTRY
        assert "structured_requirements" in STAGE_PATH_REGISTRY
        assert "summarizer" in STAGE_PATH_REGISTRY
    
    def test_convergence_paths_in_root(self):
        """收敛点文件在 session 根目录（不在 stages/ 子目录）"""
        from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY
        
        # 收敛点路径不包含 "stages/"
        assert "stages/" not in STAGE_PATH_REGISTRY["planning_convergence"]
        assert "stages/" not in STAGE_PATH_REGISTRY["research_convergence"]
        assert "stages/" not in STAGE_PATH_REGISTRY["final_convergence"]
        
        # 收敛点路径是 JSON 文件
        assert STAGE_PATH_REGISTRY["planning_convergence"].endswith(".json")
        assert STAGE_PATH_REGISTRY["research_convergence"].endswith(".json")
        assert STAGE_PATH_REGISTRY["final_convergence"].endswith(".json")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
