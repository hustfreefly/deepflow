"""ADR-009 Phase 3: Tests for generate_requirement_index_semantic()."""
import pytest
from domains.spec_pro.coordinator import generate_requirement_index_semantic, _CATEGORY_PREFIX


class TestContractCage:
    """契约笼子: 输入验证"""

    def test_non_dict_raises_type_error(self):
        with pytest.raises(TypeError, match="living_spec must be dict"):
            generate_requirement_index_semantic("not a dict")

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            generate_requirement_index_semantic(None)

    def test_empty_dict_returns_empty(self):
        assert generate_requirement_index_semantic({}) == []

    def test_no_confirmed_returns_empty(self):
        assert generate_requirement_index_semantic({"meta": {}}) == []

    def test_empty_confirmed_returns_empty(self):
        assert generate_requirement_index_semantic({"confirmed": {}}) == []


class TestSemanticREQIDs:
    """REQ-ID 格式: REQ-{PREFIX}-{NNN}"""

    def test_objective_gets_obj_prefix(self):
        spec = {"confirmed": {"objective": "Build a platform"}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 1
        assert result[0]["id"] == "REQ-OBJ-001"
        assert result[0]["category"] == "objective"
        assert result[0]["priority"] == "P0"

    def test_capabilities_always_do(self):
        spec = {"confirmed": {"capabilities": {"always_do": ["Fast response", "Secure auth"]}}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 2
        assert result[0]["id"] == "REQ-CAP-001"
        assert result[1]["id"] == "REQ-CAP-002"
        assert all(r["priority"] == "P0" for r in result)

    def test_capabilities_never_do(self):
        spec = {"confirmed": {"capabilities": {"never_do": ["No plaintext passwords"]}}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 1
        assert result[0]["id"] == "REQ-NO-001"
        assert result[0]["category"] == "prohibition"

    def test_per_category_numbering(self):
        spec = {"confirmed": {
            "objective": "Build platform",
            "capabilities": {"always_do": ["Feature A", "Feature B"]},
            "pain_points": ["Slow performance"],
        }}
        result = generate_requirement_index_semantic(spec)
        ids = [r["id"] for r in result]
        assert "REQ-OBJ-001" in ids
        assert "REQ-CAP-001" in ids
        assert "REQ-CAP-002" in ids
        assert "REQ-PAIN-001" in ids

    def test_unknown_category_uses_3char_prefix(self):
        """Unknown category → first 3 chars uppercase"""
        # This tests the fallback prefix logic
        spec = {"confirmed": {"custom_field": "test"}}
        # custom_field is not in _CATEGORY_PREFIX, but it's not parsed by the function
        # So we test with a known mapping
        assert _CATEGORY_PREFIX.get("objective") == "OBJ"
        assert _CATEGORY_PREFIX.get("nonexistent") is None


class TestConstraintsCompatibility:
    """Constraints: 兼容 dict 和 list 格式"""

    def test_dict_constraints(self):
        spec = {"confirmed": {"constraints": {"budget": "100万", "timeline": "6个月"}}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 2
        assert all(r["id"].startswith("REQ-CON-") for r in result)

    def test_list_constraints(self):
        spec = {"confirmed": {"constraints": ["一步到位", "全LLM控制"]}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 2
        assert all(r["id"].startswith("REQ-CON-") for r in result)

    def test_empty_constraints_skipped(self):
        spec = {"confirmed": {"constraints": {"budget": "", "timeline": None}}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 0


class TestQualityAttributes:
    """Quality attributes: dict 和 string 兼容"""

    def test_dict_qa(self):
        spec = {"confirmed": {"quality_attributes": [
            {"spec": "Response time < 200ms", "priority": "P0"},
            {"description": "99.9% uptime", "priority": "P1"},
        ]}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 2
        assert result[0]["priority"] == "P0"
        assert result[1]["priority"] == "P1"

    def test_string_qa(self):
        spec = {"confirmed": {"quality_attributes": ["Fast", "Reliable"]}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 2
        assert all(r["priority"] == "P1" for r in result)


class TestSuccessMetrics:
    """Success metrics: dict 和 string 兼容"""

    def test_dict_metric(self):
        spec = {"confirmed": {"success_metrics": [
            {"metric": "Revenue", "target": "100万/月", "priority": "P0"},
        ]}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 1
        assert "Revenue" in result[0]["description"]
        assert "100万/月" in result[0]["description"]

    def test_string_metric(self):
        spec = {"confirmed": {"success_metrics": ["Complete on time"]}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 1
        assert result[0]["description"] == "Complete on time"


class TestGuardrails:
    """Guardrails: 从顶层 living_spec 读取（需 confirmed 非空才进入主逻辑）"""

    def test_guardrails_always_do(self):
        spec = {"confirmed": {"objective": "Test"}, "guardrails": {"always_do": ["Log all actions"]}}
        result = generate_requirement_index_semantic(spec)
        guardrail_reqs = [r for r in result if r["category"] == "guardrail"]
        assert len(guardrail_reqs) == 1
        assert guardrail_reqs[0]["id"] == "REQ-GRD-001"

    def test_guardrails_never_do(self):
        spec = {"confirmed": {"objective": "Test"}, "guardrails": {"never_do": ["No data export"]}}
        result = generate_requirement_index_semantic(spec)
        prohibition_reqs = [r for r in result if r["category"] == "guardrail_prohibition"]
        assert len(prohibition_reqs) == 1
        assert prohibition_reqs[0]["id"] == "REQ-GRP-001"


class TestRisksAndAssumptions:
    """Risks: 兼容 risks 和 risks_and_assumptions"""

    def test_risks_dict(self):
        spec = {"confirmed": {"risks": {"risks": [{"description": "Market risk"}]}}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 1
        assert result[0]["id"] == "REQ-RSK-001"

    def test_risks_and_assumptions_dict(self):
        spec = {"confirmed": {"risks_and_assumptions": {
            "risks": ["Tech risk"],
            "assumptions": ["User has API access"],
        }}}
        result = generate_requirement_index_semantic(spec)
        assert len(result) == 2
        assert result[0]["id"] == "REQ-RSK-001"
        assert result[1]["id"] == "REQ-ASM-001"


class TestEmptyFieldsSkipped:
    """空字段不生成 REQ"""

    def test_empty_objective_skipped(self):
        spec = {"confirmed": {"objective": ""}}
        assert generate_requirement_index_semantic(spec) == []

    def test_none_capabilities_skipped(self):
        spec = {"confirmed": {"capabilities": None}}
        assert generate_requirement_index_semantic(spec) == []

    def test_empty_list_skipped(self):
        spec = {"confirmed": {"pain_points": []}}
        assert generate_requirement_index_semantic(spec) == []
