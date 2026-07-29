"""
Track B: gate_input_conservation 测试

测试覆盖：
1. Gate：MUST missing → raise ValueError
2. Gate：SHOULD missing → declared_gaps 显式记录
3. Gate：全覆盖 → PASS
4. Gate：要素提取 LLM 调用失败 → raise（fail-closed）
5. Gate：Judge LLM 调用失败 → raise（fail-closed）
6. raw_user_input.txt 持久化验证
"""

import sys as _sys
from pathlib import Path as _Path

_p = _Path(__file__).resolve()
_r = next((d for d in _p.parents if (d / 'core' / 'blackboard').is_dir()), None)
if _r and str(_r) not in _sys.path:
    _sys.path.insert(0, str(_r))

import json
import pytest
from unittest.mock import MagicMock

from domains.spec_pro.contracts.gate_input_conservation import (
    gate_input_conservation,
    extract_input_elements,
    judge_element_conservation,
    _parse_llm_json,
)


# ============================================================================
# Test helpers
# ============================================================================

def _make_llm_call(responses: list) -> MagicMock:
    """创建一个按顺序返回 responses 的 mock LLM call"""
    mock = MagicMock(side_effect=responses)
    return mock


SAMPLE_USER_INPUT = "2.5D封装设计团队组建框架：面向CoWoS-S/L的PDK驱动型团队（两年路线图）"

SAMPLE_ELEMENTS_ALL_COVERED = [
    {"id": "E1", "element": "CoWoS-S", "category": "technology", "criticality": "MUST"},
    {"id": "E2", "element": "CoWoS-L", "category": "technology", "criticality": "MUST"},
    {"id": "E3", "element": "PDK驱动型团队", "category": "organization_principle", "criticality": "MUST"},
    {"id": "E4", "element": "两年路线图", "category": "timeline_constraint", "criticality": "MUST"},
]

SAMPLE_LIVING_SPEC_FULL = {
    "topic": "2.5D封装设计团队组建",
    "confirmed": {
        "objective": "组建面向CoWoS-S/L的PDK驱动型团队，两年路线图",
    },
    "core_summary": "涵盖CoWoS-S和CoWoS-L双平台，PDK驱动型组织原则，24个月路线图",
    "semantic_anchors": [
        {"name": "CoWoS-S", "category": "technology"},
        {"name": "CoWoS-L", "category": "technology"},
        {"name": "PDK驱动型", "category": "organization_principle"},
    ],
    "requirement_index": [
        {"id": "REQ-001", "description": "CoWoS-S/L 双平台"},
        {"id": "REQ-002", "description": "PDK驱动型团队"},
        {"id": "REQ-003", "description": "两年路线图"},
    ],
    "narrative": "本方案覆盖CoWoS-S和CoWoS-L，采用PDK驱动型组织，规划24个月路线图",
}


# ============================================================================
# Test 1: 全覆盖 → PASS
# ============================================================================

class TestFullCoverage:
    def test_all_elements_covered_returns_pass(self):
        """所有要素 COVERED → passed=True, declared_gaps=[]"""
        # Layer 1: 返回要素清单
        extract_response = json.dumps({
            "input_elements": SAMPLE_ELEMENTS_ALL_COVERED
        })

        # Layer 2: 全部 COVERED
        judge_response = json.dumps({
            "conservation_results": [
                {"id": "E1", "element": "CoWoS-S", "status": "COVERED", "evidence": "living_spec 明确提及"},
                {"id": "E2", "element": "CoWoS-L", "status": "COVERED", "evidence": "living_spec 明确提及"},
                {"id": "E3", "element": "PDK驱动型团队", "status": "COVERED", "evidence": "semantic_anchors 包含"},
                {"id": "E4", "element": "两年路线图", "status": "COVERED", "evidence": "narrative 提及 24 个月"},
            ],
            "conservation_rate": 1.0,
        })

        llm_call = _make_llm_call([extract_response, judge_response])

        result = gate_input_conservation(
            user_input=SAMPLE_USER_INPUT,
            living_spec=SAMPLE_LIVING_SPEC_FULL,
            llm_call=llm_call,
        )

        assert result["passed"] is True
        assert result["declared_gaps"] == []
        assert result["conservation_rate"] == 1.0
        assert len(result["elements"]) == 4
        assert llm_call.call_count == 2


# ============================================================================
# Test 2: MUST missing → raise ValueError
# ============================================================================

class TestMustMissing:
    def test_must_element_missing_raises_value_error(self):
        """MUST 要素 MISSING → raise ValueError（HARD_BLOCK）"""
        elements_with_must = [
            {"id": "E1", "element": "CoWoS-S", "category": "technology", "criticality": "MUST"},
            {"id": "E2", "element": "CoWoS-L", "category": "technology", "criticality": "MUST"},
            {"id": "E3", "element": "PDK驱动型团队", "category": "organization_principle", "criticality": "MUST"},
        ]

        extract_response = json.dumps({"input_elements": elements_with_must})

        # E2 (CoWoS-L) is MISSING — this is MUST
        judge_response = json.dumps({
            "conservation_results": [
                {"id": "E1", "element": "CoWoS-S", "status": "COVERED", "evidence": "提及"},
                {"id": "E2", "element": "CoWoS-L", "status": "MISSING", "evidence": "未提及"},
                {"id": "E3", "element": "PDK驱动型团队", "status": "COVERED", "evidence": "提及"},
            ],
            "conservation_rate": 0.67,
        })

        llm_call = _make_llm_call([extract_response, judge_response])

        with pytest.raises(ValueError, match="MUST.*缺失|HARD_BLOCK"):
            gate_input_conservation(
                user_input=SAMPLE_USER_INPUT,
                living_spec=SAMPLE_LIVING_SPEC_FULL,
                llm_call=llm_call,
            )


# ============================================================================
# Test 3: SHOULD missing → declared_gaps
# ============================================================================

class TestShouldMissing:
    def test_should_element_missing_declared_gaps(self):
        """SHOULD 要素 MISSING → declared_gaps 显式记录，不阻断"""
        elements_with_should = [
            {"id": "E1", "element": "CoWoS-S", "category": "technology", "criticality": "MUST"},
            {"id": "E2", "element": "成本优化建议", "category": "quality_attribute", "criticality": "SHOULD"},
        ]

        extract_response = json.dumps({"input_elements": elements_with_should})

        # E2 (SHOULD) is MISSING
        judge_response = json.dumps({
            "conservation_results": [
                {"id": "E1", "element": "CoWoS-S", "status": "COVERED", "evidence": "提及"},
                {"id": "E2", "element": "成本优化建议", "status": "MISSING", "evidence": "未提及"},
            ],
            "conservation_rate": 0.5,
        })

        llm_call = _make_llm_call([extract_response, judge_response])

        result = gate_input_conservation(
            user_input=SAMPLE_USER_INPUT,
            living_spec=SAMPLE_LIVING_SPEC_FULL,
            llm_call=llm_call,
        )

        assert result["passed"] is True  # SHOULD missing 不阻断
        assert len(result["declared_gaps"]) == 1
        assert result["declared_gaps"][0]["id"] == "E2"
        assert result["declared_gaps"][0]["criticality"] == "SHOULD"


# ============================================================================
# Test 4: LLM 调用失败 → raise（fail-closed）
# ============================================================================

class TestFailClosed:
    def test_extract_llm_failure_raises(self):
        """Layer 1 要素提取 LLM 调用失败 → raise（fail-closed）"""
        llm_call = MagicMock(side_effect=RuntimeError("API timeout"))

        with pytest.raises(ValueError, match="fail-closed|LLM 调用失败"):
            extract_input_elements(
                user_input=SAMPLE_USER_INPUT,
                llm_call=llm_call,
            )

    def test_judge_llm_failure_raises(self):
        """Layer 2 Judge LLM 调用失败 → raise（fail-closed）"""
        llm_call = MagicMock(side_effect=ConnectionError("Network error"))

        elements = SAMPLE_ELEMENTS_ALL_COVERED

        with pytest.raises(ValueError, match="fail-closed|LLM 调用失败"):
            judge_element_conservation(
                elements=elements,
                living_spec=SAMPLE_LIVING_SPEC_FULL,
                llm_call=llm_call,
            )

    def test_extract_empty_response_raises(self):
        """Layer 1 LLM 返回空 → raise（fail-closed）"""
        llm_call = MagicMock(return_value="")

        with pytest.raises(ValueError, match="fail-closed|空输出"):
            extract_input_elements(
                user_input=SAMPLE_USER_INPUT,
                llm_call=llm_call,
            )

    def test_extract_invalid_json_raises(self):
        """Layer 1 LLM 返回非法 JSON → raise（fail-closed）"""
        llm_call = MagicMock(return_value="This is not JSON at all, just random text")

        with pytest.raises(ValueError, match="fail-closed|JSON 解析失败"):
            extract_input_elements(
                user_input=SAMPLE_USER_INPUT,
                llm_call=llm_call,
            )

    def test_gate_full_llm_failure_raises(self):
        """gate_input_conservation 中 LLM 失败 → raise（整个 gate fail-closed）"""
        llm_call = MagicMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(ValueError, match="fail-closed"):
            gate_input_conservation(
                user_input=SAMPLE_USER_INPUT,
                living_spec=SAMPLE_LIVING_SPEC_FULL,
                llm_call=llm_call,
            )


# ============================================================================
# Test 5: JSON 解析工具
# ============================================================================

class TestParseLlmJson:
    def test_direct_json(self):
        raw = '{"key": "value"}'
        assert _parse_llm_json(raw) == {"key": "value"}

    def test_json_in_code_block(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _parse_llm_json(raw) == {"key": "value"}

    def test_json_with_prefix_text(self):
        raw = 'Here is the result:\n{"key": "value"}'
        assert _parse_llm_json(raw) == {"key": "value"}

    def test_invalid_returns_none(self):
        raw = "No JSON here"
        assert _parse_llm_json(raw) is None


# ============================================================================
# Test 6: 边界条件
# ============================================================================

class TestEdgeCases:
    def test_empty_user_input_raises(self):
        """空 user_input → raise"""
        llm_call = MagicMock()
        with pytest.raises(ValueError, match="过短"):
            extract_input_elements(user_input="", llm_call=llm_call)

    def test_zero_elements_from_llM_raises(self):
        """LLM 返回空要素列表 → raise（fail-closed）"""
        llm_call = MagicMock(return_value='{"input_elements": []}')
        with pytest.raises(ValueError, match="0 个要素"):
            extract_input_elements(user_input=SAMPLE_USER_INPUT, llm_call=llm_call)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
