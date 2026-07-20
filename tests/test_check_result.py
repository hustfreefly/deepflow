"""
Unit tests for CheckResult Pydantic V2 model.

Covers:
- Field validation (all 6 fields correct types)
- Literal status strict mode (rejects invalid values)
- quality_score bounds (ge=0, le=100)
- length non-negative constraint
- Default values (warnings=[], suggestion=None)
- Model serialization and deserialization
- Type coercion rejection
"""

import pytest
from pydantic import ValidationError

from src.skill_health.check_result import CheckResult


# ---------------------------------------------------------------------------
# Construction & field defaults
# ---------------------------------------------------------------------------

class TestCheckResultConstruction:
    """Test that CheckResult can be constructed with valid data."""

    def test_full_construction_all_fields(self):
        """All 6 fields populated correctly."""
        result = CheckResult(
            is_valid=True,
            length=150,
            status="valid",
            quality_score=85,
            warnings=["contains non-ASCII characters"],
            suggestion="Looks good",
        )
        assert result.is_valid is True
        assert result.length == 150
        assert result.status == "valid"
        assert result.quality_score == 85
        assert result.warnings == ["contains non-ASCII characters"]
        assert result.suggestion == "Looks good"

    def test_optional_fields_default(self):
        """warnings defaults to empty list, suggestion defaults to None."""
        result = CheckResult(
            is_valid=False,
            length=10,
            status="too_short",
            quality_score=50,
        )
        assert result.warnings == []
        assert result.suggestion is None

    def test_suggestion_none_allowed(self):
        """suggestion=None is valid."""
        result = CheckResult(
            is_valid=True,
            length=100,
            status="valid",
            quality_score=70,
            warnings=[],
            suggestion=None,
        )
        assert result.suggestion is None


# ---------------------------------------------------------------------------
# status Literal validation
# ---------------------------------------------------------------------------

class TestStatusLiteral:
    """Test that status field enforces Literal with strict mode."""

    @pytest.mark.parametrize(
        "status_value",
        ["too_short", "valid", "too_long"],
    )
    def test_valid_status_values(self, status_value):
        """All three Literal values are accepted."""
        result = CheckResult(
            is_valid=(status_value == "valid"),
            length=100,
            status=status_value,
            quality_score=50,
        )
        assert result.status == status_value

    def test_invalid_status_rejected(self):
        """Invalid status value raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=True,
                length=100,
                status="invalid_status",
                quality_score=50,
            )

    def test_none_status_rejected(self):
        """None is not a valid Literal status."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=True,
                length=100,
                status=None,
                quality_score=50,
            )

    def test_empty_string_status_rejected(self):
        """Empty string is not a valid Literal status."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=True,
                length=100,
                status="",
                quality_score=50,
            )


# ---------------------------------------------------------------------------
# quality_score bounds
# ---------------------------------------------------------------------------

class TestQualityScoreBounds:
    """Test quality_score ge=0, le=100 constraints."""

    @pytest.mark.parametrize("score", [0, 1, 50, 99, 100])
    def test_valid_scores(self, score):
        """Scores in range 0-100 are accepted."""
        result = CheckResult(
            is_valid=True,
            length=100,
            status="valid",
            quality_score=score,
        )
        assert result.quality_score == score

    @pytest.mark.parametrize("score", [-1, -100])
    def test_score_below_zero_rejected(self, score):
        """Score below 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=True,
                length=100,
                status="valid",
                quality_score=score,
            )

    @pytest.mark.parametrize("score", [101, 200])
    def test_score_above_100_rejected(self, score):
        """Score above 100 raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=True,
                length=100,
                status="valid",
                quality_score=score,
            )


# ---------------------------------------------------------------------------
# length validation
# ---------------------------------------------------------------------------

class TestLengthField:
    """Test length field ge=0 constraint."""

    def test_length_zero_allowed(self):
        """length=0 is valid (empty string input)."""
        result = CheckResult(
            is_valid=False,
            length=0,
            status="too_short",
            quality_score=0,
        )
        assert result.length == 0

    def test_length_negative_rejected(self):
        """Negative length raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=False,
                length=-1,
                status="too_short",
                quality_score=0,
            )

    def test_length_large_accepted(self):
        """Large length values are accepted."""
        result = CheckResult(
            is_valid=False,
            length=10000,
            status="too_long",
            quality_score=0,
        )
        assert result.length == 10000


# ---------------------------------------------------------------------------
# is_valid field
# ---------------------------------------------------------------------------

class TestIsValidField:
    """Test is_valid bool field."""

    def test_is_valid_true(self):
        result = CheckResult(
            is_valid=True,
            length=100,
            status="valid",
            quality_score=50,
        )
        assert result.is_valid is True

    def test_is_valid_false(self):
        result = CheckResult(
            is_valid=False,
            length=10,
            status="too_short",
            quality_score=50,
        )
        assert result.is_valid is False

    def test_is_valid_non_bool_rejected(self):
        """Truly non-coercible values for is_valid are rejected."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=[1, 2, 3],  # list cannot be coerced to bool
                length=100,
                status="valid",
                quality_score=50,
            )


# ---------------------------------------------------------------------------
# warnings field
# ---------------------------------------------------------------------------

class TestWarningsField:
    """Test warnings List[str] field."""

    def test_warnings_list_of_strings(self):
        result = CheckResult(
            is_valid=True,
            length=100,
            status="valid",
            quality_score=50,
            warnings=["warning 1", "warning 2"],
        )
        assert result.warnings == ["warning 1", "warning 2"]

    def test_warnings_non_string_rejected(self):
        """List items must be strings."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=True,
                length=100,
                status="valid",
                quality_score=50,
                warnings=[1, 2, 3],
            )

    def test_warnings_not_list_rejected(self):
        """warnings must be a list."""
        with pytest.raises(ValidationError):
            CheckResult(
                is_valid=True,
                length=100,
                status="valid",
                quality_score=50,
                warnings="not_a_list",
            )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    """Test model_dump and model_dump_json."""

    def test_model_dump_includes_all_fields(self):
        result = CheckResult(
            is_valid=True,
            length=250,
            status="valid",
            quality_score=100,
            warnings=["non-ASCII"],
            suggestion="Perfect",
        )
        dumped = result.model_dump()
        assert dumped == {
            "is_valid": True,
            "length": 250,
            "status": "valid",
            "quality_score": 100,
            "warnings": ["non-ASCII"],
            "suggestion": "Perfect",
        }

    def test_model_dump_json_roundtrip(self):
        """model_dump_json can be parsed back."""
        result = CheckResult(
            is_valid=False,
            length=10,
            status="too_short",
            quality_score=50,
        )
        json_str = result.model_dump_json()
        parsed = CheckResult.model_validate_json(json_str)
        assert parsed == result

    def test_model_dump_suggestion_none(self):
        """suggestion=None serializes as null."""
        result = CheckResult(
            is_valid=True,
            length=100,
            status="valid",
            quality_score=50,
        )
        dumped = result.model_dump()
        assert dumped["suggestion"] is None