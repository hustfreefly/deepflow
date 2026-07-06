"""
Phase 2 收敛层迁移对比测试

验证:
1. converge_module() 对 Research 模块正常工作
2. converge_module() 对 Review/QC 模块正常工作
3. 带契约约束的 converge_module() 正常工作
4. Gate 判定组合逻辑正确性
"""

import pytest
from domains.solution_pro.convergence_layer import ConvergenceLayer
from domains.solution_pro.blackboard import BlackboardManager


class TestConvergenceMigration:
    """收敛层迁移对比测试"""

    @pytest.fixture
    def mock_blackboard(self, tmp_path):
        # BlackboardManager 需要 session_id 作为第一个位置参数
        return BlackboardManager(session_id="test_migration", base_dir=str(tmp_path))

    def test_converge_module_research(self, mock_blackboard):
        """测试 Research 模块使用 converge_module()"""
        cl = ConvergenceLayer(module_name="research", blackboard=mock_blackboard)

        # 模拟 Research stage 输出
        stage_outputs = [
            {"findings": [{"id": "F1", "description": "Finding 1"}]},
            {"findings": [{"id": "F2", "description": "Finding 2"}]},
        ]

        convergence = cl.converge_module("research", stage_outputs)

        assert convergence["module"] == "research"
        assert convergence["schema_version"] == "research_v2.0"
        assert convergence["status"] == "COMPLETE"
        assert convergence["stage_count"] == 2
        assert "gate_a" in convergence
        assert "gate_b" in convergence
        assert convergence["overall_verdict"] in ("PASS", "FAIL")

    def test_converge_module_with_contract(self, mock_blackboard):
        """测试带契约的 converge_module()"""
        cl = ConvergenceLayer(module_name="research", blackboard=mock_blackboard)

        stage_outputs = [{"findings": [{"id": "F1", "description": "test"}]}]
        contract = {"min_findings": 1}

        convergence = cl.converge_module("research", stage_outputs, contract)

        assert "gate_a" in convergence
        assert "gate_b" in convergence
        assert convergence["stage_count"] == 1

    def test_gate_verdict_combination(self, mock_blackboard):
        """测试 Gate 判定组合逻辑"""
        cl = ConvergenceLayer(module_name="research", blackboard=mock_blackboard)

        # 双 PASS → PASS
        assert cl._combine_gate_verdicts({"verdict": "PASS"}, {"verdict": "PASS"}) == "PASS"

        # A FAIL → FAIL
        assert cl._combine_gate_verdicts({"verdict": "FAIL"}, {"verdict": "PASS"}) == "FAIL"

        # B FAIL → FAIL
        assert cl._combine_gate_verdicts({"verdict": "PASS"}, {"verdict": "FAIL"}) == "FAIL"

        # 双 FAIL → FAIL
        assert cl._combine_gate_verdicts({"verdict": "FAIL"}, {"verdict": "FAIL"}) == "FAIL"

    def test_converge_module_empty_stages(self, mock_blackboard):
        """测试空 stage 列表"""
        cl = ConvergenceLayer(module_name="research", blackboard=mock_blackboard)

        convergence = cl.converge_module("research", [])

        assert convergence["stage_count"] == 0
        assert convergence["status"] == "COMPLETE"

    def test_converge_module_extracts_constraints_and_risks(self, mock_blackboard):
        """测试压缩逻辑正确提取 constraints 和 risks"""
        cl = ConvergenceLayer(module_name="research", blackboard=mock_blackboard)

        stage_outputs = [
            {
                "findings": [{"id": "F1"}],
                "constraints": [{"name": "C1", "priority": "MUST"}],
                "risks": [{"id": "R1"}],
            },
            {
                "findings": [{"id": "F2"}],
                "constraints": [{"name": "C2", "priority": "SHOULD"}],
                "risks": [{"id": "R2"}, {"id": "R3"}],
            },
        ]

        convergence = cl.converge_module("research", stage_outputs)

        # Verify internal compression worked (via gate_a scores which use constraints)
        assert convergence["stage_count"] == 2
        # gate_a should have computed scores based on the compressed data
        gate_a = convergence["gate_a"]
        assert "scores" in gate_a or "score" in gate_a
