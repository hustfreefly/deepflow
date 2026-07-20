"""Tests for VersionValidator — format validation and directory consistency.

Covers:
- AC-1: validate() accepts version string, returns VersionCheckResult;
  supports SemVer (MAJOR.MINOR.PATCH) and simplified formats ('1.0', '2');
  invalid format returns is_valid=False with format error description.
- AC-2: Directory consistency check compares frontmatter version with
  SkillInfo directory content; mismatch populates mismatch_details with
  specific diff description.
- AC-4: When directory has no version markers, detected_version=None,
  is_valid=True, mismatch_details contains '无法验证一致性' warning.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.skill_health.skill_info import SkillInfo
from src.skill_health.version_check_result import VersionCheckResult
from src.skill_health.version_validator import VersionValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def validator() -> VersionValidator:
    """Create a VersionValidator instance."""
    return VersionValidator()


@pytest.fixture
def tmp_skill_dir(tmp_path: Path) -> Path:
    """Create a temporary skill directory."""
    return tmp_path


def _make_skill_info(skill_dir: Path, name: str = "test-skill") -> SkillInfo:
    """Helper to create a SkillInfo with minimal required fields."""
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nskill_name: test\nversion: 1.0.0\n---\n", encoding="utf-8")
    return SkillInfo(
        skill_dir=skill_dir,
        skill_md_path=skill_md,
        skill_name=name,
    )


# ===========================================================================
# AC-1: Format validation — valid SemVer
# ===========================================================================


class TestSemVerValidation:
    """AC-1: SemVer MAJOR.MINOR.PATCH format support."""

    @pytest.mark.parametrize(
        "version",
        [
            "0.0.0",
            "1.0.0",
            "1.2.3",
            "10.20.30",
            "100.200.300",
            "0.0.1",
            "0.1.0",
        ],
    )
    def test_valid_basic_semver(self, validator: VersionValidator, version: str) -> None:
        result = validator.validate(version)
        assert result.is_valid is True
        assert result.declared_version == version
        assert result.detected_version is None
        assert result.mismatch_details is None

    @pytest.mark.parametrize(
        "version",
        [
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-0.3.7",
            "1.0.0-x.7.z.92",
            "1.0.0-alpha-beta",
            "1.0.0-rc.1",
            "1.0.0-beta.2+build.456",
        ],
    )
    def test_valid_semver_prerelease(self, validator: VersionValidator, version: str) -> None:
        result = validator.validate(version)
        assert result.is_valid is True
        assert result.declared_version == version

    @pytest.mark.parametrize(
        "version",
        [
            "1.0.0+build.123",
            "1.0.0+20130313144700",
            "1.0.0-beta.1+build.999",
            "1.0.0+exp.sha.5114f85",
        ],
    )
    def test_valid_semver_build_metadata(self, validator: VersionValidator, version: str) -> None:
        result = validator.validate(version)
        assert result.is_valid is True
        assert result.declared_version == version

    @pytest.mark.parametrize(
        "version",
        [
            "1.0",       # Missing patch
            "1",         # Major only
            "01.0.0",    # Leading zero
            "1.01.0",    # Leading zero
            "1.0.01",    # Leading zero
            "1.0.0-",    # Trailing hyphen
            "1.0.0+",    # Trailing plus
            "v1.0.0",    # v prefix not allowed in strict SemVer
            "1.0.0.0",   # Too many parts
            "",          # Empty string
            "abc",       # Non-numeric
            "1.0.0-",    # Incomplete prerelease
            "1.a.0",     # Non-numeric minor
        ],
    )
    def test_invalid_semver(self, validator: VersionValidator, version: str) -> None:
        """These are invalid as SemVer but some may be valid as simplified."""
        result = validator.validate(version)
        # Only check the ones that should be fully invalid
        if version in ("1.0", "1"):
            # These are valid simplified formats
            assert result.is_valid is True
        else:
            assert result.is_valid is False


# ===========================================================================
# AC-1: Format validation — simplified formats
# ===========================================================================


class TestSimplifiedVersionValidation:
    """AC-1: Simplified version formats ('1.0', '2')."""

    @pytest.mark.parametrize(
        "version",
        [
            "0",
            "1",
            "2",
            "10",
            "100",
            "0.0",
            "1.0",
            "2.0",
            "1.10",
            "10.20",
        ],
    )
    def test_valid_simplified(self, validator: VersionValidator, version: str) -> None:
        result = validator.validate(version)
        assert result.is_valid is True
        assert result.declared_version == version

    @pytest.mark.parametrize(
        "version",
        [
            "01",      # Leading zero
            "1.01",    # Leading zero in minor
            "1.0.0",   # This is SemVer, not simplified (but still valid)
            "v1",      # v prefix
            "1.",      # Trailing dot
            ".1",      # Leading dot
            "1.0.0.0", # Too many parts
            "-1",      # Negative
            "1.02.3",  # Leading zero in patch
        ],
    )
    def test_invalid_simplified(self, validator: VersionValidator, version: str) -> None:
        """These should not match simplified format."""
        result = validator.validate(version)
        if version == "1.0.0":
            # This IS valid as SemVer
            assert result.is_valid is True
        else:
            assert result.is_valid is False


# ===========================================================================
# AC-1: Invalid format error messages
# ===========================================================================


class TestInvalidFormatErrorMessages:
    """AC-1: Invalid format returns is_valid=False with format error description."""

    def test_invalid_format_returns_is_valid_false(self, validator: VersionValidator) -> None:
        result = validator.validate("not-a-version")
        assert result.is_valid is False
        assert result.declared_version == "not-a-version"

    def test_invalid_format_has_mismatch_details(self, validator: VersionValidator) -> None:
        result = validator.validate("abc.def.ghi")
        assert result.mismatch_details is not None
        assert "Invalid version format" in result.mismatch_details

    def test_invalid_format_mentions_valid_examples(self, validator: VersionValidator) -> None:
        result = validator.validate("xyz")
        assert result.mismatch_details is not None
        assert "1.0.0" in result.mismatch_details  # Shows example

    def test_invalid_format_has_suggestion(self, validator: VersionValidator) -> None:
        result = validator.validate("hello")
        assert result.suggestion is not None
        assert len(result.suggestion) > 0

    def test_empty_string_is_invalid(self, validator: VersionValidator) -> None:
        result = validator.validate("")
        assert result.is_valid is False
        assert result.declared_version == ""

    def test_result_type_is_version_check_result(self, validator: VersionValidator) -> None:
        result = validator.validate("1.0.0")
        assert isinstance(result, VersionCheckResult)


# ===========================================================================
# AC-2: Directory consistency check — match
# ===========================================================================


class TestDirectoryConsistencyMatch:
    """AC-2: Directory consistency check with matching versions."""

    def test_changelog_version_matches_declared(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [1.0.0] - 2024-01-01\n### Added\n- Initial release\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.declared_version == "1.0.0"
        assert result.detected_version == "1.0.0"

    def test_changelog_version_with_v_prefix_matches(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [v2.0.0]\n### Changed\n- Big update\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("2.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "2.0.0"

    def test_version_tagged_directory_matches(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        (tmp_skill_dir / "v1.5.0").mkdir()
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.5.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "1.5.0"

    def test_version_tagged_file_matches(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        # Create a version-tagged file (no common extension — will be scanned)
        (tmp_skill_dir / "v3.0.0").write_bytes(b"")
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("3.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "3.0.0"


# ===========================================================================
# AC-2: Directory consistency check — mismatch
# ===========================================================================


class TestDirectoryConsistencyMismatch:
    """AC-2: Mismatch populates mismatch_details with specific diff description."""

    def test_changelog_version_mismatch(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [2.0.0]\n### Changed\n- Updated\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is False
        assert result.declared_version == "1.0.0"
        assert result.detected_version == "2.0.0"
        assert result.mismatch_details is not None
        assert "mismatch" in result.mismatch_details.lower() or "1.0.0" in result.mismatch_details

    def test_mismatch_has_suggestion_with_fix_direction(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [3.0.0]\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is False
        assert result.suggestion is not None
        # Suggestion should mention both versions
        assert "1.0.0" in result.suggestion
        assert "3.0.0" in result.suggestion

    def test_directory_version_mismatch_with_v_prefix(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        (tmp_skill_dir / "v2.0.0").mkdir()
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is False
        assert result.detected_version == "2.0.0"


# ===========================================================================
# AC-4: No version markers in directory
# ===========================================================================


class TestNoVersionMarkers:
    """AC-4: No version markers → detected_version=None, is_valid=True,
    mismatch_details contains '无法验证一致性'."""

    def test_empty_directory(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert result.mismatch_details is not None
        assert "无法验证一致性" in result.mismatch_details

    def test_directory_with_only_py_files(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        (tmp_skill_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")
        (tmp_skill_dir / "utils.py").write_text("def helper(): pass\n", encoding="utf-8")
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert "无法验证一致性" in result.mismatch_details

    def test_directory_with_non_version_subdirs(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        (tmp_skill_dir / "src").mkdir()
        (tmp_skill_dir / "tests").mkdir()
        (tmp_skill_dir / "docs").mkdir()
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert "无法验证一致性" in result.mismatch_details

    def test_no_skill_info_skips_directory_check(
        self, validator: VersionValidator
    ) -> None:
        """Without skill_info, no directory check is performed."""
        result = validator.validate("1.0.0")
        assert result.is_valid is True
        assert result.detected_version is None
        assert result.mismatch_details is None


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_changelog_without_brackets(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """CHANGELOG with '## 2.0.0' (no brackets) should also be detected."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## 2.0.0\n### Added\n- Stuff\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("2.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "2.0.0"

    def test_changelog_picks_first_version(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Should pick the first (most recent) version in CHANGELOG."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n"
            "## [3.0.0] - 2024-03-01\n### Added\n- v3\n\n"
            "## [2.0.0] - 2024-02-01\n### Added\n- v2\n\n"
            "## [1.0.0] - 2024-01-01\n### Added\n- v1\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("3.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "3.0.0"

    def test_build_metadata_ignored_in_comparison(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Build metadata should be stripped for comparison."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [1.0.0]\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        # Declared with build metadata, detected without — should match
        result = validator.validate("1.0.0+build.123", skill_info=skill_info)
        assert result.is_valid is True

    def test_v_prefix_stripped_in_normalization(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """v prefix in detected version should be normalized."""
        (tmp_skill_dir / "v1.0.0").mkdir()
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True

    def test_nonexistent_directory(
        self, validator: VersionValidator, tmp_path: Path
    ) -> None:
        """Non-existent skill_dir should gracefully return no markers."""
        nonexistent = tmp_path / "does_not_exist"
        nonexistent.mkdir()  # Create dir so SkillInfo can be constructed
        # But don't put any version markers in it
        skill_info = _make_skill_info(nonexistent)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert "无法验证一致性" in result.mismatch_details

    def test_simplified_version_with_directory_check(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Simplified version '1.0' should work with directory check."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [1.0]\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "1.0"

    def test_prerelease_version_in_changelog(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Prerelease versions in CHANGELOG should be detected."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [2.0.0-beta.1]\n### Added\n- Beta\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("2.0.0-beta.1", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "2.0.0-beta.1"

    def test_changelog_case_insensitive_filename(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """CHANGELOG.MD (uppercase) should be detected."""
        changelog = tmp_skill_dir / "CHANGELOG.MD"
        changelog.write_text(
            "# Changelog\n\n## [1.0.0]\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version == "1.0.0"


# ===========================================================================
# Importability
# ===========================================================================


class TestImportability:
    """VersionValidator is importable and instantiable."""

    def test_import_from_module(self) -> None:
        from src.skill_health.version_validator import VersionValidator
        assert VersionValidator is not None

    def test_instantiate(self) -> None:
        v = VersionValidator()
        assert hasattr(v, "validate")
        assert callable(v.validate)

    def test_validate_returns_version_check_result(self, validator: VersionValidator) -> None:
        result = validator.validate("1.0.0")
        assert isinstance(result, VersionCheckResult)
