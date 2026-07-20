"""
Comprehensive unit tests for DescriptionChecker.

Covers AC-1, AC-4, AC-5, AC-6 with ≥25 test cases across 8 categories:
  1. Length boundary tests at 7 points (0, 29, 30, 250, 500, 501, 1000)
  2. Quality scoring dimension tests (base, action_verb, target_object, ideal_length, combos)
  3. Empty string and whitespace-only input
  4. Suggestion content tests (too_short, too_long, valid→None)
  5. Non-ASCII warning test
  6. Integration with CheckResult model (all 6 fields)
  7. Edge cases (exactly 30, exactly 500, only verbs, only objects)
  8. Word-boundary false positive test ('procreate' ≠ 'create')
"""

import pytest

from src.skill_health.check_result import CheckResult
from src.skill_health.description_checker import DescriptionChecker


# ────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────


@pytest.fixture
def checker():
    """Default DescriptionChecker with min=30, max=500, ideal=80-300."""
    return DescriptionChecker()


@pytest.fixture
def custom_checker():
    """DescriptionChecker with non-default thresholds for parametric tests."""
    return DescriptionChecker(
        min_length=10,
        max_length=200,
        ideal_low=50,
        ideal_high=150,
        base_score=40,
        action_verb_bonus=25,
        target_object_bonus=10,
        ideal_length_bonus=20,
    )


# ────────────────────────────────────────────────────────────────────
# Category 1: Length boundary tests at 7 points — AC-5
# ────────────────────────────────────────────────────────────────────


class TestLengthBoundary7Points:
    """AC-5: Boundary value tests at 0, 29, 30, 250, 500, 501, 1000 characters."""

    def test_0_chars_empty(self, checker):
        """0 chars → too_short, is_valid=False."""
        result = checker.check("")
        assert result.length == 0
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_29_chars_too_short(self, checker):
        """29 chars → too_short, is_valid=False."""
        desc = "a" * 29
        result = checker.check(desc)
        assert result.length == 29
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_30_chars_valid_lower_boundary(self, checker):
        """30 chars → valid, is_valid=True (lower boundary)."""
        desc = "a" * 30
        result = checker.check(desc)
        assert result.length == 30
        assert result.status == "valid"
        assert result.is_valid is True

    def test_250_chars_valid_middle(self, checker):
        """250 chars → valid, is_valid=True (middle of range)."""
        desc = "b" * 250
        result = checker.check(desc)
        assert result.length == 250
        assert result.status == "valid"
        assert result.is_valid is True

    def test_500_chars_valid_upper_boundary(self, checker):
        """500 chars → valid, is_valid=True (upper boundary)."""
        desc = "c" * 500
        result = checker.check(desc)
        assert result.length == 500
        assert result.status == "valid"
        assert result.is_valid is True

    def test_501_chars_too_long(self, checker):
        """501 chars → too_long, is_valid=False."""
        desc = "d" * 501
        result = checker.check(desc)
        assert result.length == 501
        assert result.status == "too_long"
        assert result.is_valid is False

    def test_1000_chars_too_long(self, checker):
        """1000 chars → too_long, is_valid=False."""
        desc = "e" * 1000
        result = checker.check(desc)
        assert result.length == 1000
        assert result.status == "too_long"
        assert result.is_valid is False


# ────────────────────────────────────────────────────────────────────
# Category 2: Quality scoring dimension tests — AC-4
# ────────────────────────────────────────────────────────────────────


class TestQualityScoringDimensions:
    """AC-4: Each scoring component verified independently and in combination.

    Scoring formula: base(50) + action_verb(20) + target_object(15) + ideal_length(15), capped at 100.
    """

    def test_base_score_only(self, checker):
        """No bonuses → score = 50 (base)."""
        # 50 chars of neutral text: no verbs, no objects, not in 80-300
        desc = "xyz " * 12 + "ab"  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 50

    def test_action_verb_bonus_alone(self, checker):
        """Action verb present, no target object, not ideal length → 50 + 20 = 70."""
        desc = "build " + "q" * 44  # 50 chars, 'build' is action verb
        result = checker.check(desc)
        assert result.quality_score == 70

    def test_target_object_bonus_alone(self, checker):
        """Target object present, no action verb, not ideal length → 50 + 15 = 65."""
        desc = "qqqq " + "api " + "q" * 41  # 50 chars, 'api' is target object
        result = checker.check(desc)
        assert result.quality_score == 65

    def test_ideal_length_bonus_alone(self, checker):
        """Length in 80-300, no verbs, no objects → 50 + 15 = 65."""
        desc = "qqq " * 25  # 100 chars, no verbs or objects
        result = checker.check(desc)
        assert result.quality_score == 65

    def test_action_verb_plus_target_object(self, checker):
        """Action verb + target object, not ideal length → 50 + 20 + 15 = 85."""
        desc = "build the api " + "q" * 36  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 85

    def test_action_verb_plus_ideal_length(self, checker):
        """Action verb + ideal length, no target object → 50 + 20 + 15 = 85."""
        desc = "build " + "q" * 94  # 100 chars
        result = checker.check(desc)
        assert result.quality_score == 85

    def test_target_object_plus_ideal_length(self, checker):
        """Target object + ideal length, no action verb → 50 + 15 + 15 = 80."""
        desc = "qqqq " + "api " + "q" * 91  # 100 chars
        result = checker.check(desc)
        assert result.quality_score == 80

    def test_all_bonuses_combined(self, checker):
        """All bonuses → 50 + 20 + 15 + 15 = 100."""
        desc = "build the api " + "q" * 86  # 100 chars
        result = checker.check(desc)
        assert result.quality_score == 100

    def test_score_capped_at_100(self, checker):
        """Score never exceeds 100 even with all bonuses."""
        # 200 chars with verb + object + ideal length
        desc = "build the application " + "q" * 178  # 200 chars
        result = checker.check(desc)
        assert result.quality_score == 100
        assert result.quality_score <= 100

    def test_custom_checker_base_score(self, custom_checker):
        """Custom checker with base_score=40, no bonuses → 40."""
        desc = "qqq " * 5  # 20 chars, not in ideal range 50-150
        result = custom_checker.check(desc)
        assert result.quality_score == 40

    def test_custom_checker_all_bonuses(self, custom_checker):
        """Custom checker: 40 + 25 + 10 + 20 = 95."""
        # Need: verb + object + length in 50-150
        desc = "build the api " + "q" * 56  # 70 chars
        result = custom_checker.check(desc)
        assert result.quality_score == 95


# ────────────────────────────────────────────────────────────────────
# Category 3: Empty string and whitespace-only input — AC-6
# ────────────────────────────────────────────────────────────────────


class TestEmptyAndWhitespace:
    """AC-6: Empty string and whitespace-only produce length=0, status='too_short',
    is_valid=False without exceptions."""

    def test_empty_string(self, checker):
        """Empty string → length=0, too_short, is_valid=False."""
        result = checker.check("")
        assert result.length == 0
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_whitespace_only_spaces(self, checker):
        """Spaces only → stripped length=0, too_short, is_valid=False."""
        result = checker.check("     ")
        assert result.length == 0
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_whitespace_only_tabs(self, checker):
        """Tabs only → stripped length=0, too_short, is_valid=False."""
        result = checker.check("\t\t\t")
        assert result.length == 0
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_whitespace_only_newlines(self, checker):
        """Newlines only → stripped length=0, too_short, is_valid=False."""
        result = checker.check("\n\n\n")
        assert result.length == 0
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_mixed_whitespace(self, checker):
        """Mixed whitespace (spaces, tabs, newlines) → length=0, too_short."""
        result = checker.check("  \t\n  \r\n  ")
        assert result.length == 0
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_empty_string_no_exception(self, checker):
        """Empty string does not raise any exception."""
        # Should not raise
        result = checker.check("")
        assert isinstance(result, CheckResult)

    def test_whitespace_only_no_exception(self, checker):
        """Whitespace-only does not raise any exception."""
        result = checker.check("   \t\n  ")
        assert isinstance(result, CheckResult)


# ────────────────────────────────────────────────────────────────────
# Category 4: Suggestion content tests
# ────────────────────────────────────────────────────────────────────


class TestSuggestionContent:
    """Suggestion strings are correct for each status."""

    def test_too_short_suggestion_content(self, checker):
        """too_short → '信息不足，建议补充功能说明'."""
        result = checker.check("Short")
        assert result.suggestion == "信息不足，建议补充功能说明"

    def test_too_long_suggestion_content(self, checker):
        """too_long → '描述过长，建议精简至核心功能'."""
        result = checker.check("x" * 600)
        assert result.suggestion == "描述过长，建议精简至核心功能"

    def test_valid_suggestion_is_none(self, checker):
        """valid → suggestion is None."""
        desc = "a" * 100
        result = checker.check(desc)
        assert result.suggestion is None

    def test_boundary_30_suggestion_is_none(self, checker):
        """Exactly 30 chars (valid) → suggestion is None."""
        result = checker.check("a" * 30)
        assert result.suggestion is None

    def test_boundary_500_suggestion_is_none(self, checker):
        """Exactly 500 chars (valid) → suggestion is None."""
        result = checker.check("a" * 500)
        assert result.suggestion is None


# ────────────────────────────────────────────────────────────────────
# Category 5: Non-ASCII warning test
# ────────────────────────────────────────────────────────────────────


class TestNonASCIIWarning:
    """Non-ASCII characters generate warning but don't fail."""

    def test_chinese_characters_generate_warning(self, checker):
        """Chinese characters → warning about non-ASCII."""
        desc = "构建应用并部署到Kubernetes集群中，支持自动健康检查和回滚功能确保服务高可用"
        result = checker.check(desc)
        assert len(result.warnings) >= 1
        assert "non-ASCII" in result.warnings[0]

    def test_emoji_generates_warning(self, checker):
        """Emoji characters → warning about non-ASCII."""
        desc = "Build 🚀 and deploy 🔧 the application " + "x" * 60  # 100+ chars
        result = checker.check(desc)
        assert len(result.warnings) >= 1
        assert "non-ASCII" in result.warnings[0]

    def test_pure_ascii_no_warning(self, checker):
        """Pure ASCII → no warnings."""
        desc = "Build and deploy the application to production servers with zero downtime"
        result = checker.check(desc)
        assert result.warnings == []

    def test_non_ascii_does_not_affect_validity(self, checker):
        """Non-ASCII warning is non-blocking; valid length still passes."""
        desc = "构建应用并部署到集群中支持自动健康检查和回滚功能确保服务的高可用性和稳定性"
        result = checker.check(desc)
        # Length is valid (30-500), so is_valid should be True despite warning
        assert result.is_valid is True
        assert result.status == "valid"

    def test_non_ascii_with_too_short_still_invalid(self, checker):
        """Non-ASCII + too short → still invalid."""
        desc = "构建应用"  # 4 chars, too short
        result = checker.check(desc)
        assert result.is_valid is False
        assert result.status == "too_short"
        assert len(result.warnings) >= 1


# ────────────────────────────────────────────────────────────────────
# Category 6: Integration with CheckResult model — all 6 fields
# ────────────────────────────────────────────────────────────────────


class TestCheckResultIntegration:
    """Verify all 6 fields of CheckResult are populated correctly."""

    def test_all_6_fields_populated_too_short(self, checker):
        """Too short result: all 6 CheckResult fields correct."""
        result = checker.check("Hi")
        # 1. is_valid
        assert result.is_valid is False
        # 2. length
        assert result.length == 2
        # 3. status
        assert result.status == "too_short"
        # 4. quality_score
        assert result.quality_score == 50  # base only
        # 5. warnings
        assert result.warnings == []
        # 6. suggestion
        assert result.suggestion == "信息不足，建议补充功能说明"

    def test_all_6_fields_populated_valid(self, checker):
        """Valid result: all 6 CheckResult fields correct."""
        desc = "Build the application with advanced features and robust error handling plus monitoring"
        result = checker.check(desc)
        # 1. is_valid
        assert result.is_valid is True
        # 2. length
        assert result.length == len(desc)
        # 3. status
        assert result.status == "valid"
        # 4. quality_score: has 'Build' verb + 'application' object + ideal length (80-300)
        # base 50 + action_verb 20 + target_object 15 + ideal_length 15 = 100
        assert result.quality_score == 100
        # 5. warnings
        assert result.warnings == []
        # 6. suggestion
        assert result.suggestion is None

    def test_all_6_fields_populated_too_long(self, checker):
        """Too long result: all 6 CheckResult fields correct."""
        desc = "x" * 600
        result = checker.check(desc)
        # 1. is_valid
        assert result.is_valid is False
        # 2. length
        assert result.length == 600
        # 3. status
        assert result.status == "too_long"
        # 4. quality_score
        assert isinstance(result.quality_score, int)
        assert 0 <= result.quality_score <= 100
        # 5. warnings
        assert isinstance(result.warnings, list)
        # 6. suggestion
        assert result.suggestion == "描述过长，建议精简至核心功能"

    def test_checkresult_is_pydantic_model(self, checker):
        """Result is a CheckResult (Pydantic V2 model) instance."""
        result = checker.check("test description that is long enough for validation")
        assert isinstance(result, CheckResult)

    def test_checkresult_field_types(self, checker):
        """Verify field types match CheckResult schema."""
        result = checker.check("Build the api " + "q" * 86)
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.length, int)
        assert isinstance(result.status, str)
        assert isinstance(result.quality_score, int)
        assert isinstance(result.warnings, list)
        assert result.suggestion is None or isinstance(result.suggestion, str)


# ────────────────────────────────────────────────────────────────────
# Category 7: Edge cases
# ────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: exactly 30, exactly 500, only verbs, only objects."""

    def test_exactly_30_chars(self, checker):
        """Exactly 30 chars → valid (lower boundary inclusive)."""
        desc = "a" * 30
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        assert result.length == 30

    def test_exactly_500_chars(self, checker):
        """Exactly 500 chars → valid (upper boundary inclusive)."""
        desc = "a" * 500
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        assert result.length == 500

    def test_string_with_only_action_verbs(self, checker):
        """String containing only action verbs (no target objects)."""
        # 'build create deploy analyze' = 27 chars
        desc = "build create deploy analyze"
        result = checker.check(desc)
        assert result.length == 27
        # Should get action_verb bonus but not target_object bonus
        # Length 27 → too_short
        assert result.status == "too_short"
        assert result.quality_score == 70  # base 50 + action_verb 20

    def test_string_with_only_action_verbs_valid_length(self, checker):
        """String with action verbs padded to valid length."""
        desc = "build create deploy analyze " + "q" * 74  # 102 chars
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.quality_score == 85  # base 50 + verb 20 + ideal 15

    def test_string_with_only_target_objects(self, checker):
        """String containing only target objects (no action verbs)."""
        desc = "api application browser cache cluster"
        result = checker.check(desc)
        assert result.length == 37
        # Should get target_object bonus but not action_verb bonus
        assert result.quality_score == 65  # base 50 + target 15

    def test_string_with_only_target_objects_ideal_length(self, checker):
        """String with target objects padded to ideal length."""
        desc = "api application browser " + "q" * 78  # 102 chars
        result = checker.check(desc)
        assert result.quality_score == 80  # base 50 + target 15 + ideal 15

    def test_leading_trailing_whitespace_stripped(self, checker):
        """Leading/trailing whitespace is stripped for length calculation."""
        desc = "  " + "a" * 30 + "  "  # stripped = 30
        result = checker.check(desc)
        assert result.length == 30
        assert result.is_valid is True

    def test_none_input_treated_as_empty(self, checker):
        """None input is treated as empty string (no exception)."""
        result = checker.check(None)
        assert result.length == 0
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_single_character(self, checker):
        """Single character → too_short."""
        result = checker.check("a")
        assert result.length == 1
        assert result.status == "too_short"
        assert result.is_valid is False


# ────────────────────────────────────────────────────────────────────
# Category 8: Word-boundary false positive test
# ────────────────────────────────────────────────────────────────────


class TestWordBoundaryFalsePositive:
    """'procreate' does NOT match 'create' as action verb."""

    def test_procreate_no_false_positive(self, checker):
        """'procreate' should NOT trigger action_verb bonus for 'create'."""
        # 'procreate' contains 'create' as substring but not as whole word
        desc = "procreate " + "q" * 40  # 50 chars
        result = checker.check(desc)
        # Should NOT get action_verb_bonus
        assert result.quality_score == 50  # base only

    def test_create_standalone_matches(self, checker):
        """'create' as standalone word DOES match."""
        desc = "create " + "q" * 43  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 70  # base + action_verb

    def test_recreate_no_false_positive(self, checker):
        """'recreate' should NOT match 'create' as whole word."""
        desc = "recreate " + "q" * 41  # 50 chars
        result = checker.check(desc)
        # 'recreate' — \bcreate\b won't match because 're' precedes 'create' without boundary
        assert result.quality_score == 50

    def test_downloader_no_false_positive_for_download(self, checker):
        """'downloader' should NOT match 'download' — wait, \\bdownload\\b
        would match 'download' in 'downloader' only if there's a boundary.
        Actually 'downloader' = 'download' + 'er', no boundary between → no match."""
        desc = "downloader " + "q" * 39  # 50 chars
        result = checker.check(desc)
        # \bdownload\b won't match inside 'downloader' (no word boundary after 'download')
        assert result.quality_score == 50

    def test_case_insensitive_match(self, checker):
        """'BUILD' (uppercase) should still match as action verb."""
        desc = "BUILD " + "q" * 44  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 70  # base + action_verb

    def test_action_verb_at_end_of_string(self, checker):
        """Action verb at end of string matches."""
        desc = "qqqq " * 8 + "build"  # 45 chars
        result = checker.check(desc)
        assert result.quality_score == 70  # base + action_verb


# ────────────────────────────────────────────────────────────────────
# Parametric / additional coverage
# ────────────────────────────────────────────────────────────────────


class TestParametricBoundaries:
    """Parametric tests with custom checker to verify configurability."""

    def test_custom_min_length_boundary(self, custom_checker):
        """Custom min_length=10: 9 chars → too_short."""
        desc = "a" * 9
        result = custom_checker.check(desc)
        assert result.status == "too_short"
        assert result.is_valid is False

    def test_custom_min_length_valid(self, custom_checker):
        """Custom min_length=10: 10 chars → valid."""
        desc = "a" * 10
        result = custom_checker.check(desc)
        assert result.status == "valid"
        assert result.is_valid is True

    def test_custom_max_length_boundary(self, custom_checker):
        """Custom max_length=200: 201 chars → too_long."""
        desc = "a" * 201
        result = custom_checker.check(desc)
        assert result.status == "too_long"
        assert result.is_valid is False

    def test_quality_score_never_negative(self, checker):
        """Quality score is never negative."""
        result = checker.check("")
        assert result.quality_score >= 0

    def test_quality_score_never_exceeds_100(self, checker):
        """Quality score never exceeds 100 across various inputs."""
        test_cases = [
            "a" * 30,
            "a" * 100,
            "a" * 500,
            "build the api " + "q" * 286,  # 300 chars, all bonuses
            "x" * 1000,
        ]
        for text in test_cases:
            result = checker.check(text)
            assert result.quality_score <= 100, f"Score {result.quality_score} > 100 for len={len(text)}"
