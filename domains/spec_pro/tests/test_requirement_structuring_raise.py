"""W4-F1: annotate_requirements 失败 → raise（禁止脚本 fallback）。

契约：LLM 语义标注失败必须 fail-closed（raise RuntimeError），
不允许静默降级到纯脚本方案。
"""
import json

import pytest

from domains.spec_pro.requirement_structuring import annotate_requirements


def _confirmed():
    return {
        "objective": "构建智能简历定制系统",
        "capabilities": {
            "always_do": ["保持简历真实性"],
            "should_do": ["支持多模板"],
            "never_do": ["虚构经历"],
        },
    }


def _valid_annotations():
    return [
        {"original_text": "目标: 构建智能简历定制系统", "category": "core_objective", "priority": "P0"},
        {"original_text": "必须做: 保持简历真实性", "category": "capability", "priority": "P0"},
        {"original_text": "应该做: 支持多模板", "category": "capability", "priority": "P1"},
        {"original_text": "禁止做: 虚构经历", "category": "prohibition", "priority": "P0"},
    ]


class TestAnnotationRaise:
    """标注失败场景 → raise RuntimeError，而非返回 None 静默降级"""

    def test_llm_call_exception_raises(self):
        def failing_llm(prompt):
            raise ConnectionError("API timeout")

        with pytest.raises(RuntimeError, match="LLM annotation 调用失败"):
            annotate_requirements({"confirmed": _confirmed()}, failing_llm)

    def test_json_parse_failure_raises(self):
        with pytest.raises(RuntimeError, match="JSON 解析失败"):
            annotate_requirements({"confirmed": _confirmed()}, lambda p: "not json at all")

    def test_schema_validation_failure_raises(self):
        bad = [{"original_text": "目标: 构建智能简历定制系统", "category": "INVALID_CAT", "priority": "P0"}]
        with pytest.raises(RuntimeError, match="Schema 验证失败"):
            annotate_requirements({"confirmed": _confirmed()}, lambda p: json.dumps(bad))

    def test_low_coverage_raises(self):
        partial = [_valid_annotations()[0]]  # 只覆盖 1/4 → coverage 25% < 80%
        with pytest.raises(RuntimeError, match="覆盖率过低"):
            annotate_requirements({"confirmed": _confirmed()}, lambda p: json.dumps(partial))

    def test_success_returns_annotations(self):
        result = annotate_requirements(
            {"confirmed": _confirmed()}, lambda p: json.dumps(_valid_annotations())
        )
        assert result is not None
        assert len(result) == 4

    def test_empty_confirmed_returns_none(self):
        """无可标注内容 = 合法跳过（非失败），保持返回 None"""
        assert annotate_requirements({"confirmed": {}}, lambda p: "[]") is None
        assert annotate_requirements({}, lambda p: "[]") is None
