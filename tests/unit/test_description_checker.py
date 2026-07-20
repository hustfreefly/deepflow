"""
Tests for DescriptionChecker — covers AC-1, AC-2, AC-4.

AC-1: Length validation returns correct status/is_valid for <30, >500, 30-500.
AC-2: Suggestions for too_short and too_long.
AC-4: Quality scoring per dimension (base, action_verb, target_object, ideal_length).
"""

import pytest

from src.skill_health.description_checker import DescriptionChecker


@pytest.fixture
def checker():
    """Default DescriptionChecker instance."""
    return DescriptionChecker()


# ──────────────────────────────────────────────────────────────────
# AC-1: Length validation
# ──────────────────────────────────────────────────────────────────


class TestLengthValidation:
    """AC-1: DescriptionChecker.check() returns correct length/status/is_valid."""

    def test_too_short_below_30(self, checker):
        """Description < 30 chars → status='too_short', is_valid=False."""
        desc = "A short description"  # 19 chars
        result = checker.check(desc)
        assert result.is_valid is False
        assert result.status == "too_short"
        assert result.length == len(desc)

    def test_too_short_boundary_29(self, checker):
        """Exactly 29 chars → still too_short."""
        desc = "a" * 29
        result = checker.check(desc)
        assert result.is_valid is False
        assert result.status == "too_short"
        assert result.length == 29

    def test_valid_boundary_30(self, checker):
        """Exactly 30 chars → valid."""
        desc = "a" * 30
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        assert result.length == 30

    def test_valid_middle_range(self, checker):
        """150 chars → valid."""
        base = "Build and deploy container images to Kubernetes "
        desc = (base + "clusters with automated rollback and health checks. ") * 2
        desc = desc[:150]
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        assert result.length == 150

    def test_valid_boundary_500(self, checker):
        """Exactly 500 chars → valid."""
        desc = "a" * 500
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        assert result.length == 500

    def test_too_long_boundary_501(self, checker):
        """Exactly 501 chars → too_long."""
        desc = "a" * 501
        result = checker.check(desc)
        assert result.is_valid is False
        assert result.status == "too_long"
        assert result.length == 501

    def test_too_long_way_over(self, checker):
        """600 chars → too_long."""
        desc = "x" * 600
        result = checker.check(desc)
        assert result.is_valid is False
        assert result.status == "too_long"
        assert result.length == 600


# ──────────────────────────────────────────────────────────────────
# AC-2: Suggestions
# ──────────────────────────────────────────────────────────────────


class TestSuggestions:
    """AC-2: Correct suggestions for too_short and too_long."""

    def test_too_short_suggestion(self, checker):
        """too_short → '信息不足，建议补充功能说明'."""
        result = checker.check("Short")
        assert result.suggestion == "信息不足，建议补充功能说明"

    def test_too_long_suggestion(self, checker):
        """too_long → '描述过长，建议精简至核心功能'."""
        result = checker.check("x" * 600)
        assert result.suggestion == "描述过长，建议精简至核心功能"

    def test_valid_no_suggestion(self, checker):
        """valid → suggestion is None."""
        desc = "a" * 100
        result = checker.check(desc)
        assert result.suggestion is None


# ──────────────────────────────────────────────────────────────────
# AC-4: Quality scoring
# ──────────────────────────────────────────────────────────────────


class TestQualityScoring:
    """AC-4: Quality scoring algorithm — base 50 + action_verb(+20) + target_object(+15) + ideal_length(+15)."""

    def test_base_score_only(self, checker):
        """No action verb, no target object, outside ideal range → base 50."""
        # 50 chars of neutral text (no verbs, no objects, not in 80-300)
        desc = "xyz " * 12 + "ab"  # 50 chars, no verbs or objects
        result = checker.check(desc)
        assert result.quality_score == 50

    def test_action_verb_bonus(self, checker):
        """Contains action verb → base 50 + 20 = 70 (without other bonuses)."""
        # 50 chars with 'build' but no target object, not in ideal range
        desc = "build " + "x" * 44  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 70

    def test_target_object_bonus(self, checker):
        """Contains target object → base 50 + 15 = 65 (without other bonuses)."""
        desc = "xxxx " + "api " + "x" * 41  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 65

    def test_ideal_length_bonus(self, checker):
        """Length in 80-300 → base 50 + 15 = 65 (without other bonuses)."""
        desc = "xyz " * 25  # 100 chars, no verbs or objects
        result = checker.check(desc)
        assert result.quality_score == 65

    def test_all_bonuses(self, checker):
        """All bonuses → 50 + 20 + 15 + 15 = 100."""
        # Need: action verb + target object + length 80-300
        desc = "Build the application with " + "x" * 73  # 100 chars
        result = checker.check(desc)
        assert result.quality_score == 100

    def test_score_capped_at_100(self, checker):
        """Score cannot exceed 100."""
        desc = "Build the application with " + "x" * 273  # 300 chars
        result = checker.check(desc)
        assert result.quality_score == 100
        assert result.quality_score <= 100

    def test_action_verb_and_target_only(self, checker):
        """Action verb + target object, outside ideal range → 50 + 20 + 15 = 85."""
        desc = "Build the api " + "x" * 36  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 85

    def test_verb_plus_ideal_length(self, checker):
        """Action verb + ideal length, no target object → 50 + 20 + 15 = 85."""
        desc = "build " + "x" * 94  # 100 chars
        result = checker.check(desc)
        assert result.quality_score == 85

    def test_target_plus_ideal_length(self, checker):
        """Target object + ideal length, no action verb → 50 + 15 + 15 = 80."""
        desc = "xxxx " + "api " + "x" * 91  # 100 chars
        result = checker.check(desc)
        assert result.quality_score == 80


# ──────────────────────────────────────────────────────────────────
# Word-boundary regex (no false positives)
# ──────────────────────────────────────────────────────────────────


class TestWordBoundaryRegex:
    """Action verb/target object detection uses word-boundary regex."""

    def test_no_false_positive_create_in_procreate(self, checker):
        """'create' should NOT match inside 'procreate'."""
        desc = "procreate " + "x" * 40  # 50 chars, 'create' is substring
        result = checker.check(desc)
        # Should NOT get action_verb_bonus
        # base 50 + ideal_length (50 not in 80-300) = 50
        assert result.quality_score == 50

    def test_no_false_positive_run_in_prune(self, checker):
        """'run' should NOT match inside 'prune' — wait, 'run' is not in 'prune'.
        Test 'run' not matching 'drunk' or similar."""
        desc = "drunk " + "x" * 44  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 50

    def test_action_verb_matches_standalone(self, checker):
        """'Build' at start of string should match."""
        desc = "Build " + "x" * 44  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 70  # base + action_verb

    def test_action_verb_case_insensitive(self, checker):
        """'BUILD' (uppercase) should match."""
        desc = "BUILD " + "x" * 44  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 70

    def test_action_verb_mixed_case(self, checker):
        """'DePlOy' (mixed case) should match."""
        desc = "DePlOy " + "x" * 43  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 70

    def test_target_object_case_insensitive(self, checker):
        """'API' (uppercase) should match."""
        desc = "xxxx " + "API " + "x" * 41  # 50 chars
        result = checker.check(desc)
        assert result.quality_score == 65


# ──────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Handle empty string, whitespace-only, and non-ASCII gracefully."""

    def test_empty_string(self, checker):
        """Empty string → length=0, status='too_short', is_valid=False, no exception."""
        result = checker.check("")
        assert result.is_valid is False
        assert result.status == "too_short"
        assert result.length == 0
        assert result.quality_score == 50  # base only
        assert result.suggestion == "信息不足，建议补充功能说明"

    def test_whitespace_only(self, checker):
        """Whitespace-only → stripped length=0, status='too_short', is_valid=False."""
        result = checker.check("   \t\n  ")
        assert result.is_valid is False
        assert result.status == "too_short"
        assert result.length == 0

    def test_whitespace_with_content(self, checker):
        """Leading/trailing whitespace is stripped for length calculation."""
        desc = "  " + "a" * 30 + "  "  # stripped length = 30
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        assert result.length == 30

    def test_non_ascii_warning(self, checker):
        """Non-ASCII characters generate a warning."""
        desc = "构建应用并部署到Kubernetes集群中 " + "x" * 60  # 100+ chars with Chinese
        result = checker.check(desc)
        assert len(result.warnings) >= 1
        assert "non-ASCII" in result.warnings[0]

    def test_ascii_no_warning(self, checker):
        """Pure ASCII → no warnings."""
        desc = "Build and deploy the application to production servers with zero downtime"
        result = checker.check(desc)
        assert result.warnings == []

    def test_quality_score_range(self, checker):
        """Quality score is always 0-100."""
        for text in ["", "a" * 30, "a" * 500, "x" * 1000]:
            result = checker.check(text)
            assert 0 <= result.quality_score <= 100


# ──────────────────────────────────────────────────────────────────
# Integration: realistic descriptions
# ──────────────────────────────────────────────────────────────────


class TestRealisticDescriptions:
    """Test with realistic skill descriptions."""

    def test_good_description(self, checker):
        """A well-written description gets high score."""
        desc = (
            "Build and deploy container images to Kubernetes clusters "
            "with automated health checks and rollback support"
        )
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        # Has 'Build', 'deploy' (action verbs) + 'container', 'clusters' (target objects)
        # Length ~120 chars (in ideal range)
        assert result.quality_score == 100
        assert result.warnings == []
        assert result.suggestion is None

    def test_short_vague_description(self, checker):
        """A short vague description gets low score."""
        desc = "A tool for stuff"
        result = checker.check(desc)
        assert result.is_valid is False
        assert result.status == "too_short"
        assert result.quality_score == 50  # base only (no verbs/objects matched, not ideal length)

    def test_chinese_description(self, checker):
        """Chinese description with action verbs and target objects."""
        desc = "构建应用并部署到集群中，支持自动健康检查和回滚功能，确保服务的高可用性和稳定性"
        result = checker.check(desc)
        assert result.is_valid is True
        assert result.status == "valid"
        # Has non-ASCII warning
        assert len(result.warnings) >= 1
        assert "non-ASCII" in result.warnings[0]
