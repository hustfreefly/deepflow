"""VersionCheckResult Pydantic V2 model.

This module defines the output type for VersionValidator.validate().
It is the structured result of a version validation check, containing
the validation status, version information, and optional diagnostic details.

Downstream consumers (fix_engine) use this model to determine whether
a version declaration is valid and, if not, what action to take.

AC-3: Pydantic V2 BaseModel with exactly 5 fields:
    - is_valid: bool
    - declared_version: str
    - detected_version: Optional[str]
    - mismatch_details: Optional[str]
    - suggestion: Optional[str]

AC-4: When constructed with is_valid=True and no detected_version,
    the model serializes correctly with detected_version=None.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class VersionCheckResult(BaseModel):
    """Result of a version validation check.

    This model is the output type for VersionValidator.validate() and must
    be importable by downstream consumers (fix_engine).

    Attributes:
        is_valid: Whether the version declaration passed validation.
            True means the version format is valid and (if directory
            content was checked) consistent.
        declared_version: The version string as declared in the frontmatter.
            Always present regardless of validation outcome.
        detected_version: The version detected from directory content
            (e.g., CHANGELOG entries, version-tagged files). None when
            no version marker was found in the directory.
        mismatch_details: Human-readable description of what went wrong
            when validation fails. Populated for both format errors and
            directory content mismatches. None when is_valid is True
            and no warnings exist.
        suggestion: Suggested fix direction when validation fails.
            For example, "Update declared_version to match directory
            content" or "Fix version format to SemVer". None when no
            suggestion is applicable.

    Example:
        >>> result = VersionCheckResult(
        ...     is_valid=True,
        ...     declared_version="1.0.0",
        ... )
        >>> result.detected_version is None
        True
        >>> result.model_dump()
        {'is_valid': True, 'declared_version': '1.0.0',
         'detected_version': None, 'mismatch_details': None, 'suggestion': None}
    """

    model_config = ConfigDict(frozen=True)

    is_valid: bool = Field(
        description="Whether the version declaration passed validation."
    )
    declared_version: str = Field(
        description="The version string as declared in the frontmatter."
    )
    detected_version: Optional[str] = Field(
        default=None,
        description=(
            "The version detected from directory content. "
            "None when no version marker was found."
        ),
    )
    mismatch_details: Optional[str] = Field(
        default=None,
        description=(
            "Human-readable description of validation failure. "
            "None when is_valid is True and no warnings exist."
        ),
    )
    suggestion: Optional[str] = Field(
        default=None,
        description=(
            "Suggested fix direction when validation fails. "
            "None when no suggestion is applicable."
        ),
    )
