"""
Tests for frozen_living_md.py — ADR-009 Phase 1 contract fixes.

Covers:
- F1: frontmatter schema_version parsing
- F2: key_decisions table render + parse
- F3: risk_summary table render + parse
- F4: implementation_phases table render + parse
- F5: frontmatter session_id parsing
- Round-trip ≥ 95% retention
- Backward compat: bullet list format still parses
"""

import pytest
import sys
import os

# Add parent dir to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frozen_living_md import (
    render_frozen_spec_md,
    parse_frozen_spec_md,
    validate_frozen_spec_md,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

MINIMAL_FROZEN_SPEC = {
    "schema_version": "2.0.0",
    "session_id": "test_minimal_001",
    "topic": "Minimal Test",
    "solution_type": "architecture",
    "domain": "test",
    "mode": "full",
    "constraints": [
        {"req_id": "REQ-001", "description": "Basic requirement", "priority": "MUST"},
    ],
    "key_decisions": [],
    "risk_summary": [],
    "implementation_phases": [],
    "semantic_anchors": [],
    "covered_req_ids": [],
}

RICH_FROZEN_SPEC = {
    "schema_version": "2.0.0",
    "session_id": "test_frozen_001",
    "topic": "Test Architecture",
    "solution_type": "architecture",
    "domain": "test",
    "mode": "full",
    "constraints": [
        {"req_id": "REQ-001", "description": "Must support high availability", "priority": "MUST"},
        {"req_id": "REQ-002", "description": "Must complete within 30 days", "priority": "SHOULD"},
    ],
    "key_decisions": [
        {"decision": "Use microservices", "rationale": "Scalability", "alternatives": "Monolith (rejected)"},
        {"decision": "Use PostgreSQL", "rationale": "ACID compliance", "alternatives": "MongoDB"},
    ],
    "risk_summary": [
        {"risk": "Context degradation", "severity": "高", "probability": "Medium", "mitigation": "Periodic restart"},
    ],
    "implementation_phases": [
        {"phase": "1", "title": "Foundation", "timeline": "Week 1-2", "estimated_effort": "2 weeks"},
        {"phase": "2", "title": "Core", "timeline": "Week 3-4", "estimated_effort": "2 weeks"},
    ],
    "semantic_anchors": [
        {"name": "HA Pattern", "category": "architecture", "constraint": "REQ-001"},
    ],
    "covered_req_ids": ["REQ-001", "REQ-002"],
}


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestRenderBasic:
    """test_render_basic — 基础渲染，检查 required sections 存在"""

    def test_render_basic(self):
        md = render_frozen_spec_md(MINIMAL_FROZEN_SPEC)
        assert md.startswith("---")
        assert "## meta_info" in md
        assert "## constraints" in md
        assert "## gate_decisions" in md
        assert "## semantic_anchors" in md


class TestParseFrontmatter:
    """test_parse_frontmatter — 验证 schema_version + session_id 解析 (F1+F5)"""

    def test_parse_frontmatter(self):
        md = render_frozen_spec_md(RICH_FROZEN_SPEC)
        result = parse_frozen_spec_md(md)
        assert result.get("schema_version") == "2.0.0", f"Expected '2.0.0', got {result.get('schema_version')}"
        assert result.get("session_id") == "test_frozen_001", f"Expected 'test_frozen_001', got {result.get('session_id')}"


class TestParseKeyDecisionsTable:
    """test_parse_key_decisions_table — 表格格式解析为 list[dict] (F2)"""

    def test_parse_key_decisions_table(self):
        md = render_frozen_spec_md(RICH_FROZEN_SPEC)
        result = parse_frozen_spec_md(md)
        kd = result.get("key_decisions", [])
        assert isinstance(kd, list), f"Expected list, got {type(kd)}"
        assert len(kd) == 2, f"Expected 2 decisions, got {len(kd)}"
        assert isinstance(kd[0], dict), f"Expected dict items, got {type(kd[0])}"
        assert kd[0]["decision"] == "Use microservices"
        assert kd[0]["rationale"] == "Scalability"
        assert kd[0]["alternatives"] == "Monolith (rejected)"


class TestParseRiskSummaryTable:
    """test_parse_risk_summary_table — 表格格式解析为 list[dict] (F3)"""

    def test_parse_risk_summary_table(self):
        md = render_frozen_spec_md(RICH_FROZEN_SPEC)
        result = parse_frozen_spec_md(md)
        rs = result.get("risk_summary", [])
        assert isinstance(rs, list), f"Expected list, got {type(rs)}"
        assert len(rs) == 1, f"Expected 1 risk, got {len(rs)}"
        assert isinstance(rs[0], dict), f"Expected dict items, got {type(rs[0])}"
        assert rs[0]["risk"] == "Context degradation"
        assert rs[0]["severity"] == "高"
        assert rs[0]["probability"] == "Medium"
        assert rs[0]["mitigation"] == "Periodic restart"


class TestParseImplementationPhasesTable:
    """test_parse_implementation_phases_table — 表格格式解析为 list[dict] (F4)"""

    def test_parse_implementation_phases_table(self):
        md = render_frozen_spec_md(RICH_FROZEN_SPEC)
        result = parse_frozen_spec_md(md)
        ip = result.get("implementation_phases", [])
        assert isinstance(ip, list), f"Expected list, got {type(ip)}"
        assert len(ip) == 2, f"Expected 2 phases, got {len(ip)}"
        assert isinstance(ip[0], dict), f"Expected dict items, got {type(ip[0])}"
        assert ip[0]["title"] == "Foundation"
        assert ip[0]["timeline"] == "Week 1-2"


class TestRoundTripMinimal:
    """test_round_trip_minimal — 最小 dict round-trip"""

    def test_round_trip_minimal(self):
        md = render_frozen_spec_md(MINIMAL_FROZEN_SPEC)
        result = parse_frozen_spec_md(md)
        assert result.get("schema_version") == "2.0.0"
        assert result.get("session_id") == "test_minimal_001"
        assert result.get("topic") == "Minimal Test"
        constraints = result.get("constraints", [])
        assert len(constraints) == 1
        assert constraints[0]["req_id"] == "REQ-001"


class TestRoundTripRich:
    """test_round_trip_rich — 丰富 dict round-trip，保留率 ≥ 95%"""

    def test_round_trip_rich(self):
        md = render_frozen_spec_md(RICH_FROZEN_SPEC)
        result = parse_frozen_spec_md(md)

        # Count fields that survived round-trip
        total_fields = 0
        preserved_fields = 0

        # schema_version
        total_fields += 1
        if result.get("schema_version") == RICH_FROZEN_SPEC["schema_version"]:
            preserved_fields += 1

        # session_id
        total_fields += 1
        if result.get("session_id") == RICH_FROZEN_SPEC["session_id"]:
            preserved_fields += 1

        # topic
        total_fields += 1
        if result.get("topic") == RICH_FROZEN_SPEC["topic"]:
            preserved_fields += 1

        # constraints
        total_fields += 1
        orig_constraints = RICH_FROZEN_SPEC["constraints"]
        parsed_constraints = result.get("constraints", [])
        if len(parsed_constraints) == len(orig_constraints):
            preserved_fields += 1
            # Check individual constraint descriptions (no truncation)
            for orig, parsed in zip(orig_constraints, parsed_constraints):
                total_fields += 1
                if parsed.get("description") == orig["description"]:
                    preserved_fields += 1

        # key_decisions
        total_fields += 1
        orig_kd = RICH_FROZEN_SPEC["key_decisions"]
        parsed_kd = result.get("key_decisions", [])
        if len(parsed_kd) == len(orig_kd):
            preserved_fields += 1
            for orig, parsed in zip(orig_kd, parsed_kd):
                total_fields += 1
                if isinstance(parsed, dict) and parsed.get("decision") == orig["decision"]:
                    preserved_fields += 1
                total_fields += 1
                if isinstance(parsed, dict) and parsed.get("rationale") == orig["rationale"]:
                    preserved_fields += 1

        # risk_summary
        total_fields += 1
        orig_rs = RICH_FROZEN_SPEC["risk_summary"]
        parsed_rs = result.get("risk_summary", [])
        if len(parsed_rs) == len(orig_rs):
            preserved_fields += 1
            for orig, parsed in zip(orig_rs, parsed_rs):
                total_fields += 1
                if isinstance(parsed, dict) and parsed.get("risk") == orig["risk"]:
                    preserved_fields += 1
                total_fields += 1
                if isinstance(parsed, dict) and parsed.get("mitigation") == orig["mitigation"]:
                    preserved_fields += 1

        # implementation_phases
        total_fields += 1
        orig_ip = RICH_FROZEN_SPEC["implementation_phases"]
        parsed_ip = result.get("implementation_phases", [])
        if len(parsed_ip) == len(orig_ip):
            preserved_fields += 1
            for orig, parsed in zip(orig_ip, parsed_ip):
                total_fields += 1
                if isinstance(parsed, dict) and parsed.get("title") == orig["title"]:
                    preserved_fields += 1

        # semantic_anchors
        total_fields += 1
        orig_sa = RICH_FROZEN_SPEC["semantic_anchors"]
        parsed_sa = result.get("semantic_anchors", [])
        if len(parsed_sa) == len(orig_sa):
            preserved_fields += 1

        # covered_req_ids
        total_fields += 1
        if result.get("covered_req_ids") == RICH_FROZEN_SPEC["covered_req_ids"]:
            preserved_fields += 1

        retention = preserved_fields / total_fields if total_fields > 0 else 0
        assert retention >= 0.95, f"Round-trip retention {retention:.1%} < 95% ({preserved_fields}/{total_fields})"


class TestRoundTripBackwardCompat:
    """test_round_trip_backward_compat — 旧 bullet list 格式仍可解析"""

    def test_round_trip_backward_compat(self):
        # Simulate old-format MD with bullet lists
        old_md = """---
domain: solution_pro
version: "2.0.0"
session: "old_session_001"
---

## meta_info

| field | value |
|-------|-------|
| topic | Old Format Test |
| solution_type | architecture |

## constraints

| REQ-ID | description | priority |
|--------|-------------|----------|
| REQ-001 | Basic req | MUST |

## key_decisions

- Use microservices for scalability
- Use PostgreSQL for ACID

## risk_summary

- Context degradation risk
- Timeline pressure

## implementation_phases

- Phase 1: Foundation
- Phase 2: Core

## semantic_anchors

<!-- empty -->

## gate_decisions

| check_layer | result | reason |
|-------------|--------|--------|
| L1 (Schema) | PASS | Test |
"""
        result = parse_frozen_spec_md(old_md)
        # Bullet list fallback should produce list[str]
        kd = result.get("key_decisions", [])
        assert isinstance(kd, list)
        assert len(kd) == 2
        assert kd[0] == "Use microservices for scalability"

        rs = result.get("risk_summary", [])
        assert isinstance(rs, list)
        assert len(rs) == 2

        ip = result.get("implementation_phases", [])
        assert isinstance(ip, list)
        assert len(ip) == 2


class TestValidate:
    """test_validate — 校验函数"""

    def test_validate_valid(self):
        md = render_frozen_spec_md(MINIMAL_FROZEN_SPEC)
        passed, errors = validate_frozen_spec_md(md)
        assert passed is True, f"Validation failed: {errors}"
        assert len(errors) == 0

    def test_validate_invalid(self):
        passed, errors = validate_frozen_spec_md("not valid md")
        assert passed is False
        assert len(errors) > 0

    def test_validate_empty(self):
        passed, errors = validate_frozen_spec_md("")
        assert passed is False


class TestEmptyFields:
    """test_empty_fields — 空 semantic_anchors、空 constraints"""

    def test_empty_semantic_anchors(self):
        spec = dict(MINIMAL_FROZEN_SPEC)
        spec["semantic_anchors"] = []
        md = render_frozen_spec_md(spec)
        assert "## semantic_anchors" in md
        assert "<!-- empty -->" in md
        result = parse_frozen_spec_md(md)
        assert result.get("semantic_anchors") == []

    def test_empty_constraints(self):
        spec = dict(MINIMAL_FROZEN_SPEC)
        spec["constraints"] = []
        md = render_frozen_spec_md(spec)
        assert "## constraints" in md
        result = parse_frozen_spec_md(md)
        # Empty constraints: parser may omit key or return empty list
        assert result.get("constraints", []) == [] or result.get("constraints") is None


class TestNoTruncation:
    """Verify that long text is NOT truncated in render (F-truncation fixes)"""

    def test_constraints_no_truncation(self):
        spec = dict(RICH_FROZEN_SPEC)
        long_desc = "A" * 200  # 200 chars, would have been truncated to 100
        spec["constraints"] = [
            {"req_id": "REQ-LONG", "description": long_desc, "priority": "MUST"},
        ]
        md = render_frozen_spec_md(spec)
        assert long_desc in md, "Long constraint description was truncated in render"

    def test_semantic_anchors_no_truncation(self):
        spec = dict(RICH_FROZEN_SPEC)
        long_constraint = "B" * 100  # 100 chars, would have been truncated to 60
        spec["semantic_anchors"] = [
            {"name": "Test", "category": "test", "constraint": long_constraint},
        ]
        md = render_frozen_spec_md(spec)
        assert long_constraint in md, "Long semantic anchor constraint was truncated in render"
