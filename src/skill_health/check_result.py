"""
CheckResult — Pydantic V2 model for description check results.

This model is the return type of DescriptionChecker.check() and enforces
strict validation on all fields. It captures length validation status,
quality scoring, warnings, and human-readable suggestions.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """Result of a description quality and length check.

    Encapsulates the outcome of DescriptionChecker.check(), including
    validity status, character length, quality score, warnings, and
    an optional improvement suggestion.

    Attributes:
        is_valid: Whether the description passes the length check
            (True when 30 ≤ length ≤ 500, False otherwise).
        length: Character count of the input description.
        status: Length classification — 'too_short' (<30 chars),
            'valid' (30-500 chars), or 'too_long' (>500 chars).
        quality_score: Composite quality score in range 0-100.
        warnings: List of non-blocking warnings (e.g. non-ASCII chars).
        suggestion: Optional human-readable improvement advice.
    """

    is_valid: bool = Field(
        ...,
        description="Whether the description passes the length check "
        "(True when 30 ≤ length ≤ 500, False otherwise).",
    )

    length: int = Field(
        ...,
        description="Character count of the input description.",
        ge=0,
    )

    status: Literal["too_short", "valid", "too_long"] = Field(
        ...,
        description="Length classification: 'too_short' (<30 chars), "
        "'valid' (30-500 chars), or 'too_long' (>500 chars).",
    )

    quality_score: int = Field(
        ...,
        description="Composite quality score in range 0-100. "
        "Base 50 + action verb (+20) + target object (+15) "
        "+ ideal length 80-300 (+15).",
        ge=0,
        le=100,
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Non-blocking warnings collected during the check "
        "(e.g. description contains non-ASCII characters).",
    )

    suggestion: Optional[str] = Field(
        default=None,
        description="Human-readable improvement advice. "
        "Populated when the description is too short or too long.",
    )
