"""
Tests for core/md_merge_validator.py

契约笼子: 所有测试必须通过，不允许 skip/xfail。
"""

import pytest
from core.md_merge_validator import (
    MergeValidationResult,
    SectionDiff,
    parse_sections,
    validate_merge,
    detect_missing_content,
    _line_similarity,
    REQUIRED_SECTIONS,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

MINIMAL_MD = """---
domain: spec_pro
version: "1.0"
session: "test_001"
---

# Spec Requirements: Test Project

## meta_info

| field | value |
|-------|-------|
| spec_version | 1.0 |
| domain_type | software |

## confirmed_reqs

### REQ-ID Table

| REQ-ID | dimension | description | priority | status |
|--------|-----------|-------------|----------|--------|
| REQ-001 | functional | Feature A | P0 | confirmed |
| REQ-002 | functional | Feature B | P1 | confirmed |

## capability_boundary

| category | content |
|----------|---------|
| always_do | Support API |
| never_do | Store passwords |

## constraints

| key | value |
|-----|-------|
| language | Python 3.11+ |
| framework | FastAPI |

## gate_decisions

| check_layer | result | reason |
|-------------|--------|--------|
| L1 (Schema) | PASS | Valid structure |
| L3 (merge) | PASS | Complete |
"""

UPDATED_MD_SAME = MINIMAL_MD  # Identical copy

UPDATED_MD_MODIFIED = """---
domain: spec_pro
version: "1.1"
session: "test_001"
---

# Spec Requirements: Test Project

## meta_info

| field | value |
|-------|-------|
| spec_version | 1.1 |
| domain_type | software |
| conversation_rounds | 2 |

## confirmed_reqs

### REQ-ID Table

| REQ-ID | dimension | description | priority | status |
|--------|-----------|-------------|----------|--------|
| REQ-001 | functional | Feature A | P0 | confirmed |
| REQ-002 | functional | Feature B | P1 | confirmed |
| REQ-003 | quality | Performance < 200ms | P0 | confirmed |

### Pain Points
- Slow response times
- Poor documentation

## capability_boundary

| category | content |
|----------|---------|
| always_do | Support API |
| always_do | Log all requests |
| never_do | Store passwords |

## constraints

| key | value |
|-----|-------|
| language | Python 3.11+ |
| framework | FastAPI |
| database | PostgreSQL |

## gate_decisions

| check_layer | result | reason |
|-------------|--------|--------|
| L1 (Schema) | PASS | Valid structure |
| L3 (merge) | PASS | Complete |
"""

UPDATED_MD_MISSING_SECTION = """---
domain: spec_pro
version: "1.0"
session: "test_001"
---

# Spec Requirements: Test Project

## meta_info

| field | value |
|-------|-------|
| spec_version | 1.0 |

## confirmed_reqs

| REQ-ID | description |
|--------|-------------|
| REQ-001 | Feature A |

## capability_boundary

| category | content |
|----------|---------|
| always_do | Support API |

## constraints

| key | value |
|-----|-------|
| language | Python |

"""
# Missing: gate_decisions (required section)


# ─── Test: SectionDiff Contract ──────────────────────────────────────────────

class TestSectionDiffContract:
    def test_valid_statuses(self):
        for status in ("stable", "modified", "missing", "new"):
            d = SectionDiff(section="test", status=status)
            assert d.status == status

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="must be one of"):
            SectionDiff(section="test", status="invalid")

    def test_similarity_range(self):
        SectionDiff(section="t", status="stable", similarity=0.0)
        SectionDiff(section="t", status="stable", similarity=1.0)
        with pytest.raises(ValueError, match="0.0~1.0"):
            SectionDiff(section="t", status="stable", similarity=-0.1)
        with pytest.raises(ValueError, match="0.0~1.0"):
            SectionDiff(section="t", status="stable", similarity=1.1)


# ─── Test: MergeValidationResult Contract ────────────────────────────────────

class TestMergeValidationResultContract:
    def test_valid_result(self):
        r = MergeValidationResult(passed=True, similarity_score=0.95)
        assert r.passed is True
        assert r.similarity_score == 0.95

    def test_similarity_range(self):
        with pytest.raises(ValueError, match="0.0~1.0"):
            MergeValidationResult(passed=True, similarity_score=1.5)

    def test_summary_no_changes(self):
        r = MergeValidationResult(passed=True)
        assert r.summary() == "no changes"

    def test_summary_with_missing(self):
        r = MergeValidationResult(
            passed=False,
            missing_sections=["gate_decisions"],
            semantic_review_needed=True,
        )
        s = r.summary()
        assert "missing 1 sections" in s
        assert "semantic review needed" in s


# ─── Test: parse_sections ────────────────────────────────────────────────────

class TestParseSections:
    def test_minimal_md(self):
        sections = parse_sections(MINIMAL_MD)
        assert "meta_info" in sections
        assert "confirmed_reqs" in sections
        assert "capability_boundary" in sections
        assert "constraints" in sections
        assert "gate_decisions" in sections

    def test_skips_frontmatter(self):
        sections = parse_sections(MINIMAL_MD)
        # Frontmatter should not appear as a section
        assert "---" not in sections
        assert "domain" not in sections

    def test_skips_h1_title(self):
        sections = parse_sections(MINIMAL_MD)
        # H1 title should not create a section
        assert "Spec" not in sections

    def test_non_string_raises(self):
        with pytest.raises(TypeError, match="must be str"):
            parse_sections(123)

    def test_empty_string(self):
        sections = parse_sections("")
        assert sections == {}

    def test_no_sections(self):
        sections = parse_sections("Just some text\nwithout headings")
        assert sections == {}


# ─── Test: _line_similarity ──────────────────────────────────────────────────

class TestLineSimilarity:
    def test_identical(self):
        assert _line_similarity("hello\nworld", "hello\nworld") == 1.0

    def test_completely_different(self):
        assert _line_similarity("hello\nworld", "foo\nbar") == 0.0

    def test_partial_overlap(self):
        sim = _line_similarity("a\nb\nc", "a\nb\nd")
        assert 0.45 <= sim <= 0.55  # Jaccard: {a,b} / {a,b,c,d} = 0.5

    def test_both_empty(self):
        assert _line_similarity("", "") == 1.0

    def test_one_empty(self):
        assert _line_similarity("hello", "") == 0.0
        assert _line_similarity("", "hello") == 0.0


# ─── Test: validate_merge ────────────────────────────────────────────────────

class TestValidateMerge:
    def test_identical_md_passes(self):
        result = validate_merge(MINIMAL_MD, UPDATED_MD_SAME)
        assert result.passed is True
        assert result.similarity_score >= 0.95
        assert result.missing_sections == []
        assert result.semantic_review_needed is False

    def test_modified_md_passes_or_conditional(self):
        """Modified: all required sections present. May trigger semantic review if diff > 20%."""
        result = validate_merge(MINIMAL_MD, UPDATED_MD_MODIFIED)
        # No required sections missing
        assert result.missing_sections == []
        # Some sections were modified (new content added)
        assert len(result.modified_sections) > 0
        # If similarity < 80%, semantic review is needed (this is correct behavior)
        if result.similarity_score < 0.80:
            assert result.semantic_review_needed is True
            # Still acceptable: no required sections missing, just needs LLM review

    def test_missing_required_section_fails(self):
        """Missing gate_decisions (required) → FAIL"""
        result = validate_merge(MINIMAL_MD, UPDATED_MD_MISSING_SECTION)
        assert result.passed is False
        assert "gate_decisions" in result.missing_sections

    def test_new_section_detected(self):
        """Updated MD has new optional section"""
        updated = UPDATED_MD_MODIFIED + "\n## inferred\n\n| hypothesis | confidence |\n|---|---|\n| Test | 0.8 |\n"
        result = validate_merge(MINIMAL_MD, updated)
        assert "inferred" in result.new_sections

    def test_empty_current_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_merge("", MINIMAL_MD)

    def test_empty_updated_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_merge(MINIMAL_MD, "")

    def test_non_string_raises(self):
        with pytest.raises(TypeError):
            validate_merge(123, MINIMAL_MD)

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match="0.0~1.0"):
            validate_merge(MINIMAL_MD, MINIMAL_MD, threshold=2.0)

    def test_custom_threshold(self):
        """Lower threshold → more lenient"""
        result = validate_merge(MINIMAL_MD, UPDATED_MD_MODIFIED, threshold=0.5)
        assert result.semantic_review_needed is False

    def test_high_threshold_triggers_review(self):
        """Very high threshold → semantic review"""
        result = validate_merge(MINIMAL_MD, UPDATED_MD_MODIFIED, threshold=0.99)
        # Modified sections will drop below 0.99
        assert result.semantic_review_needed is True


# ─── Test: detect_missing_content ────────────────────────────────────────────

class TestDetectMissingContent:
    def test_no_missing_when_identical(self):
        missing = detect_missing_content(MINIMAL_MD, MINIMAL_MD)
        assert missing == []

    def test_detects_missing_table_row(self):
        """Updated MD drops REQ-002"""
        updated = MINIMAL_MD.replace(
            "| REQ-002 | functional | Feature B | P1 | confirmed |\n",
            "",
        )
        missing = detect_missing_content(MINIMAL_MD, updated)
        assert any("REQ-002" in m for m in missing)

    def test_detects_missing_section(self):
        missing = detect_missing_content(MINIMAL_MD, UPDATED_MD_MISSING_SECTION)
        assert any("gate_decisions" in m for m in missing)

    def test_no_false_positive_on_expanded_md(self):
        """Updated MD has MORE content → no missing"""
        missing = detect_missing_content(MINIMAL_MD, UPDATED_MD_MODIFIED)
        # Should be empty or very few (new content added, nothing removed)
        # REQ-001 and REQ-002 are still present in updated
        req_missing = [m for m in missing if "REQ-00" in m]
        assert len(req_missing) == 0


# ─── Test: Integration ───────────────────────────────────────────────────────

class TestIntegration:
    def test_full_workflow(self):
        """Simulate: current MD → LLM merge → validate → detect missing"""
        current = MINIMAL_MD
        updated = UPDATED_MD_MODIFIED

        # Step 1: Validate merge
        result = validate_merge(current, updated)
        assert isinstance(result, MergeValidationResult)

        # Step 2: If not passed, detect what's missing
        if not result.passed:
            missing = detect_missing_content(current, updated)
            # Should have specific missing items
            assert isinstance(missing, list)

        # Step 3: Check result has useful info
        assert result.message != ""
        assert result.similarity_score > 0
        assert len(result.details) > 0
