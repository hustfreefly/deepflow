"""
Tests for domains/spec_pro/spec_living_md.py

契约笼子: round-trip 无损（dict → MD → dict 的核心字段保留率 ≥ 95%）
"""

import json
import pytest
from pathlib import Path

from domains.spec_pro.spec_living_md import (
    render_living_spec_md,
    parse_living_spec_md,
    validate_living_spec_md,
    REQUIRED_SECTIONS,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

MINIMAL_SPEC = {
    "session_id": "test_001",
    "meta": {
        "spec_version": "1.0",
        "domain_type": "software",
        "conversation_rounds": 1,
    },
    "confirmed": {
        "objective": "Build a web API",
        "pain_points": ["slow response", "poor docs"],
        "key_scenarios": ["user login", "data export"],
        "capabilities": {
            "always_do": ["validate input"],
            "should_do": ["log requests"],
            "never_do": ["store passwords"],
        },
        "constraints": {"language": "Python", "framework": "FastAPI"},
    },
}

RICH_SPEC = {
    "session_id": "test_002",
    "meta": {
        "spec_version": "2.1",
        "domain_type": "investment",
        "conversation_rounds": 3,
    },
    "narrative": "建立半导体封装材料投资框架",
    "confirmed": {
        "objective": "建立系统性投资框架",
        "pain_points": ["缺乏系统框架", "信息分散"],
        "terms": ["封装材料", "尽调"],
        "success_metrics": [
            {"metric": "IRR", "target": ">20%", "priority": "P0"},
        ],
        "users": [
            {"role": "投资经理", "count": "5", "key_needs": "决策支持"},
        ],
        "key_scenarios": ["项目筛选", "尽调分析"],
        "capabilities": {
            "always_do": ["行业分析", "竞争格局"],
            "should_do": ["技术趋势"],
            "never_do": ["短期投机"],
        },
        "quality_attributes": [
            {"category": "accuracy", "spec": "数据误差<5%", "priority": "P0"},
        ],
        "constraints": {"fund_size": "1-2亿", "stage_focus": "A轮"},
        "user_directives": [
            {"dimension": "风险偏好", "directive": "保守", "reason": "LP要求"},
        ],
    },
    "inferred": [
        {"description": "需要行业数据库", "confidence": 0.7, "source": "行业分析"},
    ],
    "open_questions": [
        {"id": "Q1", "question": "退出机制？", "blocking": True},
    ],
    "semantic_anchors": [
        {"name": "IRR计算", "category": "metric", "constraint": "年化", "priority": "P0"},
    ],
    "solution_pro_hints": {
        "focus_areas": ["行业分析", "估值模型"],
        "anti_patterns": ["过度简化"],
    },
    "route_recommendation": {
        "suggested_engine": "multi_agent",
        "complexity_score": "7",
    },
}


# ─── Test: render_living_spec_md ─────────────────────────────────────────────

class TestRender:
    def test_minimal_spec(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        assert "## meta_info" in md
        assert "## overview" in md
        assert "## confirmed_reqs" in md
        assert "## capability_boundary" in md
        assert "## constraints" in md
        assert "## gate_decisions" in md

    def test_rich_spec_has_optional_sections(self):
        md = render_living_spec_md(RICH_SPEC)
        assert "## inferred_reqs" in md
        assert "## quality_attrs" in md
        assert "## user_directives" in md
        assert "## open_questions" in md
        assert "## semantic_anchors" in md
        assert "## solution_pro_hints" in md
        assert "## route_recommendation" in md

    def test_frontmatter(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        assert md.startswith("---")
        assert 'domain: spec_pro' in md
        assert 'version: "1.0"' in md
        assert 'session: "test_001"' in md

    def test_non_dict_raises(self):
        with pytest.raises(TypeError, match="must be dict"):
            render_living_spec_md("not a dict")

    def test_empty_dict_renders_required_sections(self):
        md = render_living_spec_md({})
        for section in REQUIRED_SECTIONS:
            assert f"## {section}" in md

    def test_overview_from_objective(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        assert "Build a web API" in md

    def test_overview_from_narrative(self):
        md = render_living_spec_md(RICH_SPEC)
        assert "建立半导体封装材料投资框架" in md or "建立系统性投资框架" in md

    def test_capabilities_table(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        assert "validate input" in md
        assert "store passwords" in md


# ─── Test: parse_living_spec_md ──────────────────────────────────────────────

class TestParse:
    def test_parse_minimal(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        parsed = parse_living_spec_md(md)
        assert parsed["session_id"] == "test_001"
        assert parsed["meta"]["spec_version"] == "1.0"
        assert "confirmed" in parsed

    def test_parse_overview(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        parsed = parse_living_spec_md(md)
        assert "Build a web API" in parsed["confirmed"].get("objective", "")

    def test_parse_capabilities(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        parsed = parse_living_spec_md(md)
        caps = parsed["confirmed"].get("capabilities", {})
        assert "validate input" in caps.get("always_do", [])

    def test_parse_constraints(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        parsed = parse_living_spec_md(md)
        constraints = parsed["confirmed"].get("constraints", {})
        assert constraints.get("language") == "Python"

    def test_non_string_raises(self):
        with pytest.raises(TypeError, match="must be str"):
            parse_living_spec_md(123)


# ─── Test: validate_living_spec_md ──────────────────────────────────────────

class TestValidate:
    def test_valid_md(self):
        md = render_living_spec_md(MINIMAL_SPEC)
        passed, errors = validate_living_spec_md(md)
        assert passed is True
        assert errors == []

    def test_empty_md(self):
        passed, errors = validate_living_spec_md("")
        assert passed is False
        assert any("empty" in e for e in errors)

    def test_missing_frontmatter(self):
        passed, errors = validate_living_spec_md("## meta_info\n| a | b |")
        assert passed is False
        assert any("frontmatter" in e for e in errors)

    def test_missing_required_section(self):
        md = "---\ndomain: spec_pro\n---\n\n## meta_info\n| a | b |\n"
        passed, errors = validate_living_spec_md(md)
        assert passed is False
        assert any("confirmed_reqs" in e or "capability_boundary" in e for e in errors)


# ─── Test: Round-trip ────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_minimal_round_trip(self):
        """dict → MD → dict: 核心字段保留"""
        md = render_living_spec_md(MINIMAL_SPEC)
        parsed = parse_living_spec_md(md)

        # Meta preserved
        assert parsed["meta"]["spec_version"] == MINIMAL_SPEC["meta"]["spec_version"]

        # Objective preserved
        assert "Build a web API" in parsed["confirmed"].get("objective", "")

        # Capabilities preserved
        caps = parsed["confirmed"].get("capabilities", {})
        assert "validate input" in caps.get("always_do", [])

    def test_rich_round_trip(self):
        """Rich dict → MD → dict: 核心字段保留率 ≥ 95%"""
        md = render_living_spec_md(RICH_SPEC)
        parsed = parse_living_spec_md(md)

        # Count preserved fields
        total = 0
        preserved = 0

        # Meta
        total += 1
        if parsed["meta"].get("spec_version") == RICH_SPEC["meta"]["spec_version"]:
            preserved += 1

        # Confirmed.objective
        total += 1
        if RICH_SPEC["confirmed"]["objective"] in parsed["confirmed"].get("objective", ""):
            preserved += 1

        # Confirmed.capabilities
        total += 1
        caps = parsed["confirmed"].get("capabilities", {})
        if "行业分析" in str(caps.get("always_do", [])):
            preserved += 1

        # Confirmed.constraints
        total += 1
        ct = parsed["confirmed"].get("constraints", {})
        if ct.get("fund_size") == "1-2亿":
            preserved += 1

        # Inferred
        total += 1
        if parsed.get("inferred") and len(parsed["inferred"]) > 0:
            preserved += 1

        # Semantic anchors
        total += 1
        if parsed.get("semantic_anchors") and len(parsed["semantic_anchors"]) > 0:
            preserved += 1

        # Solution pro hints
        total += 1
        sph = parsed.get("solution_pro_hints", {})
        if sph:
            preserved += 1

        # Route recommendation
        total += 1
        rr = parsed.get("route_recommendation", {})
        if rr.get("suggested_engine") == "multi_agent":
            preserved += 1

        rate = preserved / total
        assert rate >= 0.95, f"Round-trip preservation rate {rate:.0%} < 95% (preserved {preserved}/{total})"

    def test_real_data_round_trip(self):
        """用真实 living_spec.json 做 round-trip 验证"""
        real_path = Path(__file__).resolve().parent.parent.parent.parent / "blackboard" / "spec_spec_7a9ba5854e284543" / "spec" / "living_spec.json"
        if not real_path.exists():
            pytest.skip(f"Real data not found: {real_path}")

        with open(real_path) as f:
            data = json.load(f)

        md = render_living_spec_md(data)
        parsed = parse_living_spec_md(md)

        # Core fields preserved
        assert parsed["meta"]["spec_version"] == data["meta"]["spec_version"]
        assert "confirmed" in parsed
