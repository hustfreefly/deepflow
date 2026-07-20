"""
Tests for domains/solution_pro/solution_living_md.py

契约笼子: round-trip 无损（dict → MD → dict 核心字段保留率 ≥ 90%）
"""

import json
import pytest
from pathlib import Path

from domains.solution_pro.solution_living_md import (
    render_final_solution_md,
    parse_final_solution_md,
    validate_final_solution_md,
    REQUIRED_SECTIONS,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

MINIMAL_SOLUTION = {
    "schema_version": "2.0.0",
    "key_decisions": [
        {"decision": "Use FastAPI", "rationale": "Async + fast", "alternatives": "Flask (rejected)"},
    ],
    "implementation_phases": [
        {"phase": 0, "title": "Setup", "timeline": "Week 1", "estimated_effort": "1 week",
         "tasks": ["Init project", "Setup CI"], "verification": "Project builds"},
    ],
    "metadata": {"session_id": "test_001"},
}

RICH_SOLUTION = {
    "schema_version": "3.0.0",
    "constraint_coverage": {
        "total": 89, "covered": 89, "ratio": 1.0, "uncovered": [],
        "breakdown": {"MUST": {"total": 31, "passed": 31}, "SHOULD": {"total": 58, "passed": 58}},
    },
    "key_decisions": [
        {"decision": "Fold Mapping", "rationale": "depth_limit=2", "alternatives": "Spatial nesting"},
        {"decision": "Context Budget", "rationale": "Prevents degradation", "alternatives": "Single shared"},
    ],
    "implementation_phases": [
        {"phase": 0, "title": "Infrastructure", "timeline": "Week 1", "estimated_effort": "1 week",
         "tasks": ["Blackboard", "Controller"], "verification": "Can spawn worker"},
        {"phase": 1, "title": "Core Loop", "timeline": "Week 2-3", "estimated_effort": "2 weeks",
         "tasks": ["Domain Loop", "Stall detection"], "verification": "E2E task"},
    ],
    "risk_summary": [
        {"risk": "Context degradation", "severity": "高", "probability": "High",
         "impact": "High", "mitigation": "Periodic restart + LCM"},
    ],
    "verification_status": {
        "passed": 31, "failed": 0, "total_checks": 31,
        "layer1_checklist": "31/31 PASS",
    },
    "document_ref": "solution_document",
    "metadata": {
        "session_id": "test_rich", "date": "2026-07-19",
        "status": "Production-Ready",
    },
}


# ─── Test: render ────────────────────────────────────────────────────────────

class TestRender:
    def test_minimal(self):
        md = render_final_solution_md(MINIMAL_SOLUTION)
        assert "## meta_info" in md
        assert "## overview" in md
        assert "## key_decisions" in md
        assert "## implementation_phases" in md

    def test_rich_has_optional(self):
        md = render_final_solution_md(RICH_SOLUTION)
        assert "## requirement_coverage" in md
        assert "## risk_summary" in md
        assert "## verification_status" in md

    def test_frontmatter(self):
        md = render_final_solution_md(MINIMAL_SOLUTION)
        assert md.startswith("---")
        assert "domain: solution_pro" in md

    def test_double_encoded_json(self):
        """Handle str input (double-encoded JSON)"""
        json_str = json.dumps(MINIMAL_SOLUTION)
        md = render_final_solution_md(json_str)
        assert "## meta_info" in md

    def test_non_dict_raises(self):
        with pytest.raises(TypeError, match="must be dict"):
            render_final_solution_md(123)

    def test_empty_dict_renders_required(self):
        md = render_final_solution_md({})
        for s in REQUIRED_SECTIONS:
            assert f"## {s}" in md


# ─── Test: parse ─────────────────────────────────────────────────────────────

class TestParse:
    def test_parse_minimal(self):
        md = render_final_solution_md(MINIMAL_SOLUTION)
        parsed = parse_final_solution_md(md)
        assert parsed.get("schema_version") == "2.0.0"
        assert parsed.get("metadata", {}).get("session_id") == "test_001"

    def test_parse_decisions(self):
        md = render_final_solution_md(RICH_SOLUTION)
        parsed = parse_final_solution_md(md)
        decisions = parsed.get("key_decisions", [])
        assert len(decisions) >= 1
        assert "Fold Mapping" in decisions[0].get("decision", "")

    def test_parse_phases(self):
        md = render_final_solution_md(RICH_SOLUTION)
        parsed = parse_final_solution_md(md)
        phases = parsed.get("implementation_phases", [])
        assert len(phases) >= 1

    def test_non_string_raises(self):
        with pytest.raises(TypeError, match="must be str"):
            parse_final_solution_md(123)


# ─── Test: validate ──────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_md(self):
        md = render_final_solution_md(MINIMAL_SOLUTION)
        passed, errors = validate_final_solution_md(md)
        assert passed is True, f"errors: {errors}"

    def test_empty_md(self):
        passed, errors = validate_final_solution_md("")
        assert passed is False

    def test_missing_frontmatter(self):
        passed, errors = validate_final_solution_md("## meta_info\n| a | b |")
        assert passed is False


# ─── Test: Round-trip ────────────────────────────────────────────────────────

class TestMultiWordHeaders:
    """BUG-001 regression: multi-word ## headers should parse correctly."""

    def test_multi_word_headers_normalize_to_snake_case(self):
        from domains.solution_pro.solution_living_md import _parse_md_sections
        body = "## Key Decisions\n\nsome content\n\n## Implementation Phases\n\nphase info"
        sections = _parse_md_sections(body)
        assert "key_decisions" in sections, f"Expected key_decisions, got keys: {list(sections.keys())}"
        assert "implementation_phases" in sections
        assert "some content" in sections["key_decisions"]
        assert "phase info" in sections["implementation_phases"]

    def test_snake_case_headers_still_work(self):
        """Backward compatibility: render produces snake_case, must still parse."""
        from domains.solution_pro.solution_living_md import _parse_md_sections
        body = "## key_decisions\n\ntable data\n\n## risk_summary\n\nrisk data"
        sections = _parse_md_sections(body)
        assert "key_decisions" in sections
        assert "risk_summary" in sections

    def test_parse_final_solution_with_multi_word_headers(self):
        """BUG-001 E2E: parse_final_solution_md should extract data from Agent-generated MD."""
        from domains.solution_pro.solution_living_md import parse_final_solution_md
        md = """# Solution Pro — Final Solution Document

## Key Decisions

1. **Decision One**
   - Rationale: because X
2. **Decision Two**
   - Rationale: because Y

## Implementation Phases

### Phase 1: Foundation
- Duration: Week 1-2

### Phase 2: Core
- Duration: Week 3-4
"""
        result = parse_final_solution_md(md)
        assert len(result.get("implementation_phases", [])) == 2, \
            f"Expected 2 phases, got {len(result.get('implementation_phases', []))}"


class TestRoundTrip:
    def test_minimal_round_trip(self):
        md = render_final_solution_md(MINIMAL_SOLUTION)
        parsed = parse_final_solution_md(md)
        assert parsed["schema_version"] == MINIMAL_SOLUTION["schema_version"]
        assert parsed["metadata"]["session_id"] == "test_001"

    def test_rich_round_trip(self):
        """Rich dict → MD → dict: 核心字段保留率 ≥ 90%"""
        md = render_final_solution_md(RICH_SOLUTION)
        parsed = parse_final_solution_md(md)

        total = 0
        preserved = 0

        # schema_version
        total += 1
        if parsed.get("schema_version") == "3.0.0":
            preserved += 1

        # key_decisions
        total += 1
        if parsed.get("key_decisions") and len(parsed["key_decisions"]) >= 2:
            preserved += 1

        # implementation_phases
        total += 1
        if parsed.get("implementation_phases") and len(parsed["implementation_phases"]) >= 2:
            preserved += 1

        # risk_summary
        total += 1
        if parsed.get("risk_summary") and len(parsed["risk_summary"]) >= 1:
            preserved += 1

        # metadata.session_id
        total += 1
        if parsed.get("metadata", {}).get("session_id") == "test_rich":
            preserved += 1

        rate = preserved / total
        assert rate >= 0.90, f"Round-trip rate {rate:.0%} < 90% ({preserved}/{total})"

    def test_real_data_round_trip(self):
        """用真实 final_solution.json 做 round-trip"""
        real_path = Path(__file__).resolve().parent.parent.parent.parent / "blackboard" / "ai_loop_solution_e591f8b1" / "stages" / "final_solution.json"
        if not real_path.exists():
            pytest.skip(f"Real data not found: {real_path}")

        with open(real_path) as f:
            raw = json.load(f)
        # Handle double-encoded
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw

        md = render_final_solution_md(data)
        passed, errors = validate_final_solution_md(md)
        assert passed, f"Validation failed: {errors}"

        parsed = parse_final_solution_md(md)
        assert parsed.get("schema_version") == data.get("schema_version")
        assert len(parsed.get("key_decisions", [])) >= len(data.get("key_decisions", [])) * 0.8
