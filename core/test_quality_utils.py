"""
QualityUtils 契约笼子测试

测试策略：
- L1 确定性检查：Pydantic 验证、格式、边界
- 每个函数覆盖：正常路径 + 异常路径 + 边界条件
"""
import pytest
import json

from core.quality_utils import (
    check_schema,
    check_coverage,
    check_anchors,
    aggregate_gate_results,
    CheckResult,
    CoverageResult,
    GateResult,
    QualityUtils,
)


# ============================================================================
# check_schema 测试
# ============================================================================

class TestCheckSchema:
    """check_schema() 契约测试"""
    
    def test_valid_schema(self):
        """Schema 验证通过"""
        data = {"name": "test", "value": 123}
        result = check_schema(data, required_fields=["name", "value"])
        
        assert isinstance(result, CheckResult)
        assert result.check == "schema"
        assert result.passed is True
        assert result.severity == "INFO"
    
    def test_missing_required_field(self):
        """缺失必需字段"""
        data = {"name": "test"}
        result = check_schema(data, required_fields=["name", "value"])
        
        assert result.passed is False
        assert "缺失必需字段" in result.message
        assert "value" in result.message
        assert result.severity == "ERROR"
    
    def test_json_string_input(self):
        """JSON 字符串输入"""
        data = '{"name": "test", "value": 123}'
        result = check_schema(data, required_fields=["name", "value"])
        
        assert result.passed is True
    
    def test_invalid_json_string(self):
        """无效 JSON 字符串"""
        data = '{"name": "test", invalid}'
        result = check_schema(data, required_fields=["name"])
        
        assert result.passed is False
        assert "JSON 解析失败" in result.message
    
    def test_non_dict_input(self):
        """非 dict 输入"""
        data = [1, 2, 3]
        result = check_schema(data, required_fields=["name"])
        
        assert result.passed is False
        assert "数据必须是 dict" in result.message
    
    def test_field_type_check(self):
        """字段类型检查"""
        data = {"name": "test", "value": "not_a_number"}
        result = check_schema(
            data,
            required_fields=["name", "value"],
            field_types={"value": int}
        )
        
        assert result.passed is False
        assert "字段类型错误" in result.message
    
    def test_field_type_check_pass(self):
        """字段类型检查通过"""
        data = {"name": "test", "value": 123}
        result = check_schema(
            data,
            required_fields=["name", "value"],
            field_types={"value": int}
        )
        
        assert result.passed is True
    
    def test_empty_required_fields(self):
        """空必需字段列表"""
        data = {"name": "test"}
        result = check_schema(data, required_fields=[])
        
        assert result.passed is True


# ============================================================================
# check_coverage 测试
# ============================================================================

class TestCheckCoverage:
    """check_coverage() 契约测试"""
    
    def test_full_coverage(self):
        """完全覆盖"""
        requirements = ["REQ-001", "REQ-002", "REQ-003"]
        output = "This covers REQ-001 and REQ-002 and REQ-003"
        result = check_coverage(requirements, output)
        
        assert isinstance(result, CoverageResult)
        assert result.total_reqs == 3
        assert result.covered_reqs == 3
        assert result.coverage_rate == 1.0
        assert result.passed is True
        assert len(result.uncovered) == 0
    
    def test_partial_coverage_pass(self):
        """部分覆盖（>= 阈值）"""
        requirements = ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]
        output = "Covers REQ-001 REQ-002 REQ-003 REQ-004"  # 4/5 = 0.8
        result = check_coverage(requirements, output)
        
        assert result.total_reqs == 5
        assert result.covered_reqs == 4
        assert result.coverage_rate == 0.8
        assert result.passed is True
    
    def test_partial_coverage_fail(self):
        """部分覆盖（< critical_threshold）→ CRITICAL"""
        requirements = ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]
        output = "Covers REQ-001"  # 1/5 = 0.2 < 0.5 (critical)
        result = check_coverage(requirements, output)
        
        assert result.total_reqs == 5
        assert result.covered_reqs == 1
        assert result.coverage_rate == 0.2
        assert result.passed is False  # CRITICAL 阻塞
        assert result.severity == "CRITICAL"
        assert len(result.uncovered) == 4
    
    def test_no_coverage(self):
        """无覆盖"""
        requirements = ["REQ-001", "REQ-002"]
        output = "No requirements mentioned here"
        result = check_coverage(requirements, output)
        
        assert result.total_reqs == 2
        assert result.covered_reqs == 0
        assert result.coverage_rate == 0.0
        assert result.passed is False
    
    def test_empty_requirements(self):
        """空需求列表"""
        requirements = []
        output = "Some output"
        result = check_coverage(requirements, output)
        
        assert result.total_reqs == 0
        assert result.covered_reqs == 0
        assert result.coverage_rate == 0.0
        assert result.passed is False
    
    def test_dict_requirements(self):
        """dict 格式需求"""
        requirements = {
            "REQ-001": "First requirement",
            "REQ-002": "Second requirement",
        }
        output = "Covers REQ-001 and REQ-002"
        result = check_coverage(requirements, output)
        
        assert result.total_reqs == 2
        assert result.covered_reqs == 2
        assert result.passed is True
    
    def test_custom_threshold(self):
        """自定义阈值"""
        requirements = ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]
        output = "Covers REQ-001 REQ-002 REQ-003"  # 3/5 = 0.6
        
        # 自定义 critical_threshold=0.5, warning_threshold=0.7 → 0.6 是 WARNING
        result = check_coverage(requirements, output, critical_threshold=0.5, warning_threshold=0.7)
        assert result.passed is True  # WARNING 不阻塞
        assert result.severity == "WARNING"
        
        # 自定义 critical_threshold=0.7 → 0.6 是 CRITICAL
        result = check_coverage(requirements, output, critical_threshold=0.7, warning_threshold=0.9)
        assert result.passed is False
        assert result.severity == "CRITICAL"
    
    def test_dual_threshold_critical(self):
        """双层阈值：CRITICAL（低于 critical_threshold）"""
        requirements = ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]
        output = "Covers REQ-001"  # 1/5 = 0.2 < 0.5
        result = check_coverage(requirements, output)
        
        assert result.passed is False
        assert result.severity == "CRITICAL"
        assert result.coverage_rate == 0.2
    
    def test_dual_threshold_warning(self):
        """双层阈值：WARNING（在 critical 和 warning 之间）"""
        requirements = ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]
        output = "Covers REQ-001 REQ-002 REQ-003"  # 3/5 = 0.6 (0.5 <= 0.6 < 0.8)
        result = check_coverage(requirements, output)
        
        assert result.passed is True  # WARNING 不阻塞
        assert result.severity == "WARNING"
        assert result.coverage_rate == 0.6
    
    def test_dual_threshold_pass(self):
        """双层阈值：PASS（高于 warning_threshold）"""
        requirements = ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]
        output = "Covers REQ-001 REQ-002 REQ-003 REQ-004"  # 4/5 = 0.8 >= 0.8
        result = check_coverage(requirements, output)
        
        assert result.passed is True
        assert result.severity == "PASS"
        assert result.coverage_rate == 0.8
    
    def test_case_insensitive(self):
        """大小写不敏感"""
        requirements = ["req-001"]
        output = "Covers REQ-001"
        result = check_coverage(requirements, output)
        
        assert result.covered_reqs == 1
        assert result.passed is True


# ============================================================================
# check_anchors 测试
# ============================================================================

class TestCheckAnchors:
    """check_anchors() 契约测试"""
    
    def test_all_anchors_preserved(self):
        """所有锚点保留"""
        anchors = ["anchor1", "anchor2", "anchor3"]
        output = "Contains anchor1 and anchor2 and anchor3"
        result = check_anchors(anchors, output)
        
        assert isinstance(result, CheckResult)
        assert result.check == "anchors"
        assert result.passed is True
        assert "100.0%" in result.message
    
    def test_partial_anchors_preserved_pass(self):
        """部分锚点保留（>= 阈值）"""
        anchors = ["a1", "a2", "a3", "a4", "a5"]
        output = "Contains a1 a2 a3 a4"  # 4/5 = 0.8
        result = check_anchors(anchors, output)
        
        assert result.passed is True
        assert "80.0%" in result.message
    
    def test_partial_anchors_preserved_fail(self):
        """部分锚点保留（< critical_threshold）→ CRITICAL"""
        anchors = ["a1", "a2", "a3", "a4", "a5"]
        output = "Contains a1"  # 1/5 = 0.2 < 0.5 (critical)
        result = check_anchors(anchors, output)
        
        assert result.passed is False  # CRITICAL 阻塞
        assert result.severity == "CRITICAL"
    
    def test_dict_anchors(self):
        """dict 格式锚点"""
        anchors = {"semantic_anchors": ["a1", "a2"]}
        output = "Contains a1 and a2"
        result = check_anchors(anchors, output)
        
        assert result.passed is True
    
    def test_empty_anchors(self):
        """空锚点列表"""
        anchors = []
        output = "Some output"
        result = check_anchors(anchors, output)
        
        assert result.passed is False
        assert "无锚点可检查" in result.message
        assert result.severity == "CRITICAL"  # 空输入视为 CRITICAL
    
    def test_custom_threshold(self):
        """自定义阈值"""
        anchors = ["a1", "a2", "a3", "a4", "a5"]
        output = "Contains a1 a2 a3"  # 3/5 = 0.6
        
        # 自定义 critical_threshold=0.5, warning_threshold=0.7 → 0.6 是 WARNING
        result = check_anchors(anchors, output, critical_threshold=0.5, warning_threshold=0.7)
        assert result.passed is True  # WARNING 不阻塞
        assert result.severity == "WARNING"
        
        # 自定义 critical_threshold=0.7 → 0.6 是 CRITICAL
        result = check_anchors(anchors, output, critical_threshold=0.7, warning_threshold=0.9)
        assert result.passed is False
        assert result.severity == "CRITICAL"
    
    def test_dual_threshold_critical(self):
        """双层阈值：CRITICAL（低于 critical_threshold）"""
        anchors = ["a1", "a2", "a3", "a4", "a5"]
        output = "Contains a1"  # 1/5 = 0.2 < 0.5
        result = check_anchors(anchors, output)
        
        assert result.passed is False
        assert result.severity == "CRITICAL"
    
    def test_dual_threshold_warning(self):
        """双层阈值：WARNING（在 critical 和 warning 之间）"""
        anchors = ["a1", "a2", "a3", "a4", "a5"]
        output = "Contains a1 a2 a3"  # 3/5 = 0.6 (0.5 <= 0.6 < 0.8)
        result = check_anchors(anchors, output)
        
        assert result.passed is True  # WARNING 不阻塞
        assert result.severity == "WARNING"
    
    def test_dual_threshold_pass(self):
        """双层阈值：PASS（高于 warning_threshold）"""
        anchors = ["a1", "a2", "a3", "a4", "a5"]
        output = "Contains a1 a2 a3 a4"  # 4/5 = 0.8 >= 0.8
        result = check_anchors(anchors, output)
        
        assert result.passed is True
        assert result.severity == "PASS"


# ============================================================================
# aggregate_gate_results 测试
# ============================================================================

class TestAggregateGateResults:
    """aggregate_gate_results() 契约测试"""
    
    def test_all_passed(self):
        """全部通过"""
        results = [
            CheckResult(check="schema", passed=True, message="OK"),
            CheckResult(check="anchors", passed=True, message="OK"),
        ]
        gate = aggregate_gate_results(results)
        
        assert isinstance(gate, GateResult)
        assert gate.passed is True
        assert gate.summary["total"] == 2
        assert gate.summary["passed"] == 2
        assert gate.summary["failed"] == 0
    
    def test_some_failed(self):
        """部分失败"""
        results = [
            CheckResult(check="schema", passed=True, message="OK"),
            CheckResult(check="anchors", passed=False, message="FAIL"),
        ]
        gate = aggregate_gate_results(results)
        
        assert gate.passed is False
        assert gate.summary["total"] == 2
        assert gate.summary["passed"] == 1
        assert gate.summary["failed"] == 1
    
    def test_mixed_result_types(self):
        """混合结果类型"""
        results = [
            CheckResult(check="schema", passed=True, message="OK"),
            CoverageResult(
                total_reqs=5,
                covered_reqs=4,
                coverage_rate=0.8,
                uncovered=["REQ-005"],
                passed=True,
            ),
        ]
        gate = aggregate_gate_results(results)
        
        assert gate.passed is True
        assert gate.summary["total"] == 2
        assert gate.summary["passed"] == 2
    
    def test_empty_results(self):
        """空结果列表"""
        results = []
        gate = aggregate_gate_results(results)
        
        assert gate.passed is True
        assert gate.summary["total"] == 0


# ============================================================================
# Pydantic 契约验证测试
# ============================================================================

class TestPydanticContracts:
    """Pydantic 契约验证"""
    
    def test_check_result_severity_validation(self):
        """CheckResult severity 验证"""
        with pytest.raises(ValueError, match="severity 必须是"):
            CheckResult(check="test", passed=True, severity="INVALID")
    
    def test_coverage_result_rate_validation(self):
        """CoverageResult coverage_rate 验证"""
        with pytest.raises(ValueError, match="coverage_rate 不一致"):
            CoverageResult(
                total_reqs=10,
                covered_reqs=5,
                coverage_rate=0.9,  # 应该是 0.5
                uncovered=[],
                passed=True,
            )
    
    def test_gate_result_summary_validation(self):
        """GateResult summary 验证"""
        results = [
            CheckResult(check="test", passed=True, message="OK"),
        ]
        with pytest.raises(ValueError, match="summary 不一致"):
            GateResult(
                passed=True,
                results=results,
                summary={"total": 2, "passed": 1, "failed": 1},  # 应该是 total=1
            )


# ============================================================================
# QualityUtils 类封装测试
# ============================================================================

class TestQualityUtilsClass:
    """QualityUtils 便捷类测试"""
    
    def test_schema(self):
        result = QualityUtils.schema({"name": "test"}, ["name"])
        assert isinstance(result, CheckResult)
    
    def test_coverage(self):
        result = QualityUtils.coverage(["REQ-001"], "REQ-001")
        assert isinstance(result, CoverageResult)
    
    def test_anchors(self):
        result = QualityUtils.anchors(["a1"], "a1")
        assert isinstance(result, CheckResult)
    
    def test_aggregate(self):
        results = [CheckResult(check="test", passed=True, message="OK")]
        gate = QualityUtils.aggregate(results)
        assert isinstance(gate, GateResult)
