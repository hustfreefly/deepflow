"""
Ship Pro — Gate 契约笼子负向测试 (D4-FIX)

覆盖 Codex DryRun 发现的缺陷注入场景:
- B1: GateResult passed 字段 bool 类型守卫
- B2: CompletenessGate verdict 内部一致性校验
- B1-ext: InformationConservationGate / HarnessV3 truthy string
"""
import pytest
from domains.ship_pro.contracts.gates import (
    GateResult,
    CompletenessGate,
    InformationConservationGate,
    HarnessV3,
)


class TestGateResultBoolGuard:
    """B1: GateResult.passed 必须是 bool"""

    def test_string_false_becomes_false(self):
        r = GateResult(passed="false", issues=[])
        assert r.passed is False
        assert isinstance(r.passed, bool)

    def test_string_true_becomes_true(self):
        r = GateResult(passed="true", issues=[])
        assert r.passed is True
        assert isinstance(r.passed, bool)

    def test_int_zero_becomes_false(self):
        r = GateResult(passed=0, issues=[])
        assert r.passed is False
        assert isinstance(r.passed, bool)

    def test_int_one_becomes_true(self):
        r = GateResult(passed=1, issues=[])
        assert r.passed is True
        assert isinstance(r.passed, bool)

    def test_none_becomes_false(self):
        r = GateResult(passed=None, issues=[])
        assert r.passed is False
        assert isinstance(r.passed, bool)

    def test_bool_false_stays_false(self):
        r = GateResult(passed=False, issues=[])
        assert r.passed is False

    def test_bool_true_stays_true(self):
        r = GateResult(passed=True, issues=[])
        assert r.passed is True


class TestCompletenessGateConsistency:
    """B2: CompletenessGate 确定性二次校验"""

    def test_low_coverage_forces_fail(self):
        """coverage_rate < 0.8 → 强制 passed=False"""
        result = CompletenessGate.check({}, {}, {
            "completeness": {
                "passed": True,
                "coverage_rate": 0.5,
                "issues": [],
            }
        })
        assert result.passed is False
        assert any("B2" in i for i in result.issues)

    def test_critical_issue_forces_fail(self):
        """CRITICAL issue → 强制 passed=False"""
        result = CompletenessGate.check({}, {}, {
            "completeness": {
                "passed": True,
                "coverage_rate": 0.9,
                "issues": [{"severity": "CRITICAL", "description": "D5 missing"}],
            }
        })
        assert result.passed is False
        assert any("B2" in i for i in result.issues)

    def test_high_coverage_no_critical_passes(self):
        """coverage_rate >= 0.8 + no CRITICAL → 信任 LLM passed"""
        result = CompletenessGate.check({}, {}, {
            "completeness": {
                "passed": True,
                "coverage_rate": 0.9,
                "issues": [{"severity": "MINOR", "description": "small thing"}],
            }
        })
        assert result.passed is True

    def test_llm_says_false_stays_false(self):
        """LLM 说 False → 保持 False（不反向覆盖）"""
        result = CompletenessGate.check({}, {}, {
            "completeness": {
                "passed": False,
                "coverage_rate": 0.95,
                "issues": [],
            }
        })
        assert result.passed is False

    def test_zero_coverage_forces_fail(self):
        """coverage_rate = 0 → 强制 fail"""
        result = CompletenessGate.check({}, {}, {
            "completeness": {
                "passed": True,
                "coverage_rate": 0.0,
                "issues": [],
            }
        })
        assert result.passed is False


class TestInformationConservationTruthyString:
    """B1-ext: InformationConservationGate truthy string"""

    def test_string_false_becomes_false(self):
        result = InformationConservationGate.check({}, {}, {
            "info_conservation": {"passed": "false", "issues": []}
        })
        assert result.passed is False
        assert isinstance(result.passed, bool)


class TestHarnessV3TruthyString:
    """B1-ext: HarnessV3 truthy string"""

    def test_string_false_becomes_false(self):
        wps = [
            {"id": f"W{i}", "acceptance_criteria": ["a", "b"]}
            for i in range(3)
        ]
        result = HarnessV3.check(
            {"work_packages": wps},
            {"harness_v3": {"passed": "false", "score": 0, "issues": []}}
        )
        assert result.passed is False
        assert isinstance(result.passed, bool)

    def test_int_zero_becomes_false(self):
        wps = [
            {"id": f"W{i}", "acceptance_criteria": ["a", "b"]}
            for i in range(3)
        ]
        result = HarnessV3.check(
            {"work_packages": wps},
            {"harness_v3": {"passed": 0, "score": 0, "issues": []}}
        )
        assert result.passed is False
        assert isinstance(result.passed, bool)
