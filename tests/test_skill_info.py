"""
Unit tests for SkillInfo Pydantic V2 model.

Covers:
- Field validation (all 4 fields correct types)
- Path coercion from strings
- skill_name min_length constraint
- Default values (warnings=[])
- Model serialization and deserialization roundtrip
- Immutability of default list (no shared state between instances)
"""

import pytest
from pathlib import Path
from pydantic import ValidationError

from src.skill_health.skill_info import SkillInfo


# ---------------------------------------------------------------------------
# Construction & field defaults
# ---------------------------------------------------------------------------

class TestSkillInfoConstruction:
    """Test that SkillInfo can be constructed with valid data."""

    def test_full_construction_all_fields(self):
        """All 4 fields populated correctly."""
        info = SkillInfo(
            skill_dir="/home/user/skills/my-skill",
            skill_md_path="/home/user/skills/my-skill/SKILL.md",
            skill_name="my-skill",
            warnings=["SKILL.md missing version field"],
        )
        assert info.skill_dir == Path("/home/user/skills/my-skill")
        assert info.skill_md_path == Path("/home/user/skills/my-skill/SKILL.md")
        assert info.skill_name == "my-skill"
        assert info.warnings == ["SKILL.md missing version field"]

    def test_warnings_defaults_to_empty_list(self):
        """warnings defaults to [] when not provided."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
        )
        assert info.warnings == []

    def test_path_objects_accepted(self):
        """Path objects are accepted directly."""
        skill_dir = Path("/tmp/skill")
        skill_md = Path("/tmp/skill/SKILL.md")
        info = SkillInfo(
            skill_dir=skill_dir,
            skill_md_path=skill_md,
            skill_name="test-skill",
        )
        assert info.skill_dir == skill_dir
        assert info.skill_md_path == skill_md

    def test_empty_warnings_explicit(self):
        """Explicitly passing warnings=[] works."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
            warnings=[],
        )
        assert info.warnings == []

    def test_multiple_warnings(self):
        """Multiple warning strings are preserved in order."""
        warnings = [
            "SKILL.md missing version field",
            "CHANGELOG.md not found",
            "No version markers detected",
        ]
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
            warnings=warnings,
        )
        assert info.warnings == warnings
        assert len(info.warnings) == 3


# ---------------------------------------------------------------------------
# Path coercion
# ---------------------------------------------------------------------------

class TestPathCoercion:
    """Test that string paths are coerced to Path objects."""

    def test_string_to_path_coercion(self):
        """String paths are automatically converted to Path."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
        )
        assert isinstance(info.skill_dir, Path)
        assert isinstance(info.skill_md_path, Path)

    def test_relative_path_accepted(self):
        """Relative paths are accepted."""
        info = SkillInfo(
            skill_dir="skills/my-skill",
            skill_md_path="skills/my-skill/SKILL.md",
            skill_name="my-skill",
        )
        assert info.skill_dir == Path("skills/my-skill")
        assert info.skill_md_path == Path("skills/my-skill/SKILL.md")


# ---------------------------------------------------------------------------
# skill_name validation
# ---------------------------------------------------------------------------

class TestSkillNameValidation:
    """Test skill_name min_length=1 constraint."""

    def test_single_char_name(self):
        """Single character name is valid."""
        info = SkillInfo(
            skill_dir="/tmp/s",
            skill_md_path="/tmp/s/SKILL.md",
            skill_name="s",
        )
        assert info.skill_name == "s"

    def test_empty_name_rejected(self):
        """Empty string skill_name raises ValidationError."""
        with pytest.raises(ValidationError):
            SkillInfo(
                skill_dir="/tmp/skill",
                skill_md_path="/tmp/skill/SKILL.md",
                skill_name="",
            )

    def test_name_with_spaces(self):
        """Name with spaces is accepted (no strip constraint)."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="my cool skill",
        )
        assert info.skill_name == "my cool skill"

    def test_name_with_unicode(self):
        """Unicode characters in name are accepted."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="技能测试",
        )
        assert info.skill_name == "技能测试"


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    """Test that missing required fields raise ValidationError."""

    def test_missing_skill_dir(self):
        """Missing skill_dir raises ValidationError."""
        with pytest.raises(ValidationError):
            SkillInfo(
                skill_md_path="/tmp/skill/SKILL.md",
                skill_name="test-skill",
            )

    def test_missing_skill_md_path(self):
        """Missing skill_md_path raises ValidationError."""
        with pytest.raises(ValidationError):
            SkillInfo(
                skill_dir="/tmp/skill",
                skill_name="test-skill",
            )

    def test_missing_skill_name(self):
        """Missing skill_name raises ValidationError."""
        with pytest.raises(ValidationError):
            SkillInfo(
                skill_dir="/tmp/skill",
                skill_md_path="/tmp/skill/SKILL.md",
            )


# ---------------------------------------------------------------------------
# warnings field type validation
# ---------------------------------------------------------------------------

class TestWarningsField:
    """Test warnings List[str] field type constraints."""

    def test_warnings_non_string_rejected(self):
        """List items must be strings."""
        with pytest.raises(ValidationError):
            SkillInfo(
                skill_dir="/tmp/skill",
                skill_md_path="/tmp/skill/SKILL.md",
                skill_name="test-skill",
                warnings=[1, 2, 3],
            )

    def test_warnings_not_list_rejected(self):
        """warnings must be a list, not a string."""
        with pytest.raises(ValidationError):
            SkillInfo(
                skill_dir="/tmp/skill",
                skill_md_path="/tmp/skill/SKILL.md",
                skill_name="test-skill",
                warnings="not_a_list",
            )

    def test_warnings_mixed_types_rejected(self):
        """Mixed types in warnings list are rejected."""
        with pytest.raises(ValidationError):
            SkillInfo(
                skill_dir="/tmp/skill",
                skill_md_path="/tmp/skill/SKILL.md",
                skill_name="test-skill",
                warnings=["valid", 42, None],
            )


# ---------------------------------------------------------------------------
# Default list isolation (no shared mutable state)
# ---------------------------------------------------------------------------

class TestDefaultListIsolation:
    """Test that default warnings list is not shared between instances."""

    def test_separate_instances_have_independent_warnings(self):
        """Mutating one instance's warnings does not affect another."""
        info1 = SkillInfo(
            skill_dir="/tmp/skill1",
            skill_md_path="/tmp/skill1/SKILL.md",
            skill_name="skill-1",
        )
        info2 = SkillInfo(
            skill_dir="/tmp/skill2",
            skill_md_path="/tmp/skill2/SKILL.md",
            skill_name="skill-2",
        )
        info1.warnings.append("warning for skill-1")
        assert info2.warnings == []

    def test_default_is_empty_not_none(self):
        """Default warnings is an empty list, not None."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
        )
        assert info.warnings is not None
        assert isinstance(info.warnings, list)
        assert len(info.warnings) == 0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    """Test model_dump and model_dump_json."""

    def test_model_dump_includes_all_fields(self):
        """model_dump includes all 4 fields with correct types."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
            warnings=["warning 1"],
        )
        dumped = info.model_dump()
        assert dumped == {
            "skill_dir": Path("/tmp/skill"),
            "skill_md_path": Path("/tmp/skill/SKILL.md"),
            "skill_name": "test-skill",
            "warnings": ["warning 1"],
        }

    def test_model_dump_json_roundtrip(self):
        """model_dump_json can be parsed back to equivalent model."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
            warnings=["w1", "w2"],
        )
        json_str = info.model_dump_json()
        parsed = SkillInfo.model_validate_json(json_str)
        assert parsed == info

    def test_model_dump_default_warnings(self):
        """Default warnings=[] serializes correctly."""
        info = SkillInfo(
            skill_dir="/tmp/skill",
            skill_md_path="/tmp/skill/SKILL.md",
            skill_name="test-skill",
        )
        dumped = info.model_dump()
        assert dumped["warnings"] == []

    def test_model_validate_from_dict(self):
        """model_validate constructs from a plain dict."""
        data = {
            "skill_dir": "/tmp/skill",
            "skill_md_path": "/tmp/skill/SKILL.md",
            "skill_name": "test-skill",
            "warnings": [],
        }
        info = SkillInfo.model_validate(data)
        assert info.skill_dir == Path("/tmp/skill")
        assert info.skill_name == "test-skill"
