"""契约测试 - quality_gate模块.

验证QualityGate是否符合cage/quality_gate.yaml契约规范.
"""

import pytest
from quality_gate import QualityGate, GateDecision, ConvergenceResult, QualityReport


class TestQualityGateContract:
    """契约测试集."""

    def test_init_default_config(self) -> None:
        """T1: 默认配置初始化."""
        gate = QualityGate()
        config = gate.get_config()
        assert "weights" in config
        assert "thresholds" in config
        assert len(config["weights"]) == 4
        assert abs(sum(config["weights"].values()) - 1.0) < 0.01

    def test_init_custom_config(self) -> None:
        """T2: 自定义配置初始化."""
        config = {
            "weights": {"accuracy": 0.4, "completeness": 0.3, "depth": 0.2, "elegance": 0.1},
            "thresholds": {"auto_pass": 0.90, "hitl": 0.75, "dimension": 0.60},
        }
        gate = QualityGate(config)
        assert gate.get_config() == config

    def test_init_invalid_weights(self) -> None:
        """T3: 无效权重配置应抛出ValueError."""
        with pytest.raises(ValueError, match="权重"):
            QualityGate({"weights": {"accuracy": 0.3, "completeness": 0.3, "depth": 0.3, "elegance": 0.3}})

    def test_init_invalid_dimension(self) -> None:
        """T4: 无效维度应抛出ValueError."""
        with pytest.raises(ValueError, match="无效维度"):
            QualityGate({"weights": {"invalid": 1.0}})

    def test_evaluate_empty_content_raises(self) -> None:
        """T5: 空内容应抛出ValueError."""
        gate = QualityGate()
        with pytest.raises(ValueError, match="不能为空"):
            gate.evaluate("")

    def test_evaluate_invalid_dimension_raises(self) -> None:
        """T6: 无效维度应抛出ValueError."""
        gate = QualityGate()
        with pytest.raises(ValueError, match="无效维度"):
            gate.evaluate("内容", dimensions=["invalid"])

    def test_evaluate_returns_quality_report(self) -> None:
        """T7: 返回QualityReport类型."""
        gate = QualityGate()
        report = gate.evaluate("# 测试内容\n\n结论:通过")
        assert isinstance(report, QualityReport)
        assert hasattr(report, "overall_score")
        assert hasattr(report, "dimensions")
        assert hasattr(report, "decision")
        assert hasattr(report, "reasoning")

    def test_evaluate_all_dimensions(self) -> None:
        """T8: 评估全部4维."""
        gate = QualityGate()
        report = gate.evaluate("# 标题\n\n结论:好\n\n## 分析\n原因:优化\n建议:改进")
        assert len(report.dimensions) == 4
        for dim in ["accuracy", "completeness", "depth", "elegance"]:
            assert dim in report.dimensions

    def test_evaluate_partial_dimensions(self) -> None:
        """T9: 评估部分维度."""
        gate = QualityGate()
        report = gate.evaluate("内容", dimensions=["accuracy", "completeness"])
        assert len(report.dimensions) == 2
        assert "accuracy" in report.dimensions
        assert "completeness" in report.dimensions

    def test_evaluate_4d_weighted_sum(self) -> None:
        """T10: 加权计算总分."""
        gate = QualityGate()
        score = gate.evaluate_4d(0.9, 0.8, 0.7, 0.6)
        assert abs(score - 0.8) < 0.01

    def test_evaluate_4d_clamp_out_of_range(self) -> None:
        """T11: 超出范围自动裁剪."""
        gate = QualityGate()
        score1 = gate.evaluate_4d(1.5, 0.8, 0.7, 0.6)
        assert score1 <= 1.0
        score2 = gate.evaluate_4d(-0.5, 0.8, 0.7, 0.6)
        assert score2 >= 0.0

    def test_gate_decision_pass(self) -> None:
        """T12: 高分通过."""
        gate = QualityGate()
        decision = gate.gate_decision(0.90, threshold=0.85)
        assert decision == GateDecision.PASS

    def test_gate_decision_hitl(self) -> None:
        """T13: 中等分数触发HITL."""
        gate = QualityGate()
        decision = gate.gate_decision(0.75, threshold=0.85)
        assert decision == GateDecision.HITL

    def test_gate_decision_reject(self) -> None:
        """T14: 低分拒绝."""
        gate = QualityGate()
        decision = gate.gate_decision(0.60, threshold=0.85)
        assert decision == GateDecision.REJECT

    def test_gate_decision_0_100_scale(self) -> None:
        """T15: 支持0-100分数自动转换."""
        gate = QualityGate()
        decision = gate.gate_decision(90.0, threshold=0.85)
        assert decision == GateDecision.PASS

    def test_check_convergence_insufficient_data(self) -> None:
        """T16: 数据不足返回converged=False."""
        gate = QualityGate()
        result = gate.check_convergence([0.5, 0.6], window=3)
        assert isinstance(result, ConvergenceResult)
        assert result.converged is False
        assert result.variance is None

    def test_check_convergence_detected(self) -> None:
        """T17: 检测收敛成功."""
        gate = QualityGate()
        scores = [0.80, 0.81, 0.80, 0.81, 0.80]
        result = gate.check_convergence(scores, window=3, threshold=0.05)
        assert result.converged is True
        assert result.variance is not None

    def test_check_convergence_not_detected(self) -> None:
        """T18: 未收敛."""
        gate = QualityGate()
        scores = [0.50, 0.70, 0.90, 0.60, 0.80]
        result = gate.check_convergence(scores, window=3, threshold=0.01)
        assert result.converged is False

    def test_check_convergence_invalid_window(self) -> None:
        """T19: 无效window抛出ValueError."""
        gate = QualityGate()
        with pytest.raises(ValueError, match="window"):
            gate.check_convergence([0.5], window=0)

    def test_hitl_trigger_true(self) -> None:
        """T20: 低于阈值触发HITL."""
        gate = QualityGate()
        assert gate.hitl_trigger(0.60, human_threshold=0.70) is True

    def test_hitl_trigger_false(self) -> None:
        """T21: 高于阈值不触发HITL."""
        gate = QualityGate()
        assert gate.hitl_trigger(0.80, human_threshold=0.70) is False

    def test_hitl_trigger_0_100_scale(self) -> None:
        """T22: 支持0-100分数."""
        gate = QualityGate()
        assert gate.hitl_trigger(60.0, human_threshold=0.70) is True

    def test_get_config_returns_dict(self) -> None:
        """T23: 返回配置字典."""
        gate = QualityGate()
        config = gate.get_config()
        assert isinstance(config, dict)
        assert "weights" in config
        assert "thresholds" in config

    def test_get_config_returns_copy(self) -> None:
        """T24: 返回副本不影响原配置."""
        gate = QualityGate()
        config1 = gate.get_config()
        config1["weights"]["accuracy"] = 0.1
        config2 = gate.get_config()
        assert config2["weights"]["accuracy"] != 0.1

    def test_reset_history_clears_scores(self) -> None:
        """T25: 清空历史得分记录."""
        gate = QualityGate()
        gate.evaluate("内容")
        gate.reset_history()
        report = gate.evaluate("新内容")
        assert report is not None

    def test_quality_report_all_passed(self) -> None:
        """T26: 检查所有维度通过."""
        report = QualityReport(
            overall_score=0.9,
            dimensions={"accuracy": 0.9, "completeness": 0.8, "depth": 0.7, "elegance": 0.6},
            decision=GateDecision.PASS,
            reasoning="通过",
        )
        assert report.all_passed is True

    def test_quality_report_not_all_passed(self) -> None:
        """T27: 部分维度未通过."""
        report = QualityReport(
            overall_score=0.5,
            dimensions={"accuracy": 0.5, "completeness": 0.5, "depth": 0.5, "elegance": 0.5},
            decision=GateDecision.REJECT,
            reasoning="拒绝",
        )
        assert report.all_passed is False
        assert len(report.failed_dimensions) == 4

    def test_quality_report_failed_dimensions(self) -> None:
        ""        """T28: 返回失败维度列表."""
        report = QualityReport(
            overall_score=0.7,
            dimensions={"accuracy": 0.7, "completeness": 0.5, "depth": 0.7, "elegance": 0.5},
            decision=GateDecision.HITL,
            reasoning="待确认",
        )
        failed = report.failed_dimensions
        assert "completeness" in failed
        assert "elegance" in failed
        assert "accuracy" not in failed

    def test_boundary_empty_content(self) -> None:
        """B1: 内容为空→ValueError."""
        gate = QualityGate()
        with pytest.raises(ValueError):
            gate.evaluate("")

    def test_boundary_invalid_dimension(self) -> None:
        """B2: 无效维度→ValueError."""
        gate = QualityGate()
        with pytest.raises(ValueError):
            gate.evaluate("内容", dimensions=["invalid_dim"])

    def test_boundary_clamp_score(self) -> None:
        """B3: 得分超出范围自动裁剪."""
        gate = QualityGate()
        score = gate.evaluate_4d(1.5, 0.8, 0.7, 0.6)
        assert 0.0 <= score <= 1.0

    def test_boundary_empty_scores(self) -> None:
        """B4: scores为空列表→converged=False."""
        gate = QualityGate()
        result = gate.check_convergence([], window=3)
        assert result.converged is False
        assert result.variance is None

    def test_boundary_invalid_window(self) -> None:
        """B5: window<=0→ValueError."""
        gate = QualityGate()
        with pytest.raises(ValueError):
            gate.check_convergence([0.5, 0.6, 0.7], window=0)
