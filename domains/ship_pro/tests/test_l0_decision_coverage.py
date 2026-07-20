"""
L0 确定性决策覆盖检查 — 单元测试

测试 PipelineDesigner.verify_decision_coverage() 契约笼子。
"""
import pytest
from ..pipeline_designer import PipelineDesigner


class TestVerifyDecisionCoverage:
    """verify_decision_coverage 静态方法测试"""

    def test_all_decisions_covered(self):
        """全部决策被覆盖 → 不 raise"""
        planner_output = {
            "workers": [
                {"role": "W1", "relevant_decisions": ["D1: 使用 Redis 缓存", "D2: 异步队列"]},
                {"role": "W2", "relevant_decisions": ["D3: 采用分层架构"]},
            ]
        }
        solution_pro_input = {
            "key_decisions": [
                "D1: 使用 Redis 缓存层提升性能",
                "D2: 异步队列处理耗时任务",
                "D3: 采用分层架构模式",
            ]
        }
        # 不应 raise
        PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input)

    def test_decision_completely_unassigned(self):
        """决策完全未分配 → raise ValueError"""
        planner_output = {
            "workers": [
                {"role": "W1", "relevant_decisions": ["D1: 使用 Redis 缓存"]},
                {"role": "W2", "relevant_decisions": []},
            ]
        }
        solution_pro_input = {
            "key_decisions": [
                "D1: 使用 Redis 缓存层提升性能",
                "D5: Fallback chain + charset-normalizer 处理编码",
            ]
        }
        with pytest.raises(ValueError, match="契约笼子 L0"):
            PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input)

    def test_partial_decisions_uncovered(self):
        """部分决策未分配 → raise ValueError"""
        planner_output = {
            "workers": [
                {"role": "W1", "relevant_decisions": ["D1: 使用 Redis"]},
                {"role": "W2", "relevant_decisions": ["D2: 异步处理"]},
            ]
        }
        solution_pro_input = {
            "key_decisions": [
                "D1: 使用 Redis 缓存",
                "D2: 异步队列处理",
                "D3: 分层架构设计",
                "D4: 日志审计追踪",
            ]
        }
        with pytest.raises(ValueError, match="契约笼子 L0"):
            PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input)

    def test_no_key_decisions(self):
        """无 key_decisions → 不 raise"""
        planner_output = {
            "workers": [
                {"role": "W1", "relevant_decisions": []},
            ]
        }
        solution_pro_input = {"key_decisions": []}
        PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input)

        # 也测试 key_decisions 字段不存在的情况
        solution_pro_input_no_key = {}
        PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input_no_key)

    def test_decision_format_dict(self):
        """决策格式为 dict → 正确处理"""
        planner_output = {
            "workers": [
                {"role": "W1", "relevant_decisions": ["使用 Redis 缓存层提升性能"]},
                {"role": "W2", "relevant_decisions": ["异步队列处理耗时任务"]},
            ]
        }
        solution_pro_input = {
            "key_decisions": [
                {"description": "使用 Redis 缓存层提升性能", "id": "D1"},
                {"decision": "异步队列处理耗时任务", "id": "D2"},
            ]
        }
        # 不应 raise
        PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input)

    def test_reverse_substring_match(self):
        """反向子串匹配: Worker 的 ref 是决策原文的子串 → 算覆盖"""
        planner_output = {
            "workers": [
                {"role": "W1", "relevant_decisions": ["Redis 缓存层"]},
            ]
        }
        solution_pro_input = {
            "key_decisions": ["使用 Redis 缓存层提升性能"],
        }
        # "Redis 缓存层" 是 "使用 Redis 缓存层提升性能" 的子串 → 反向匹配应通过
        PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input)

    def test_empty_workers(self):
        """有决策但无 Worker → raise"""
        planner_output = {"workers": []}
        solution_pro_input = {"key_decisions": ["D1: 某个决策"]}
        with pytest.raises(ValueError, match="契约笼子 L0"):
            PipelineDesigner.verify_decision_coverage(planner_output, solution_pro_input)
