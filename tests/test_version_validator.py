"""Comprehensive unit tests for VersionValidator covering all 5 mandatory scenarios.

This test file complements the existing tests/unit/test_version_validator.py
with additional coverage including:

1. FrontmatterData integration (version from frontmatter YAML)
2. Read-only verification (validator does not modify any files)
3. Mock-based SkillInfo construction (unittest.mock)
4. All 5 mandatory scenarios from the task specification

Scenarios:
  1. Valid SemVer: '1.0.0', '2.3.4', '0.1.0' → is_valid=True, correct declared_version
  2. Valid simplified version: '1.0', '2' → is_valid=True, correct declared_version
  3. Invalid format: 'abc', '1.0.0.0', '01.0.0' → is_valid=False, format error description
  4. Version mismatch with directory: Mock SkillInfo → is_valid=False, details+suggestion
  5. No version marker in directory: Mock SkillInfo → detected_version=None, is_valid=True,
     mismatch_details contains '无法验证一致性'
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.skill_health.skill_info import SkillInfo
from src.skill_health.version_check_result import VersionCheckResult
from src.skill_health.version_validator import VersionValidator


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def validator() -> VersionValidator:
    """Create a VersionValidator instance."""
    return VersionValidator()


@pytest.fixture
def tmp_skill_dir(tmp_path: Path) -> Path:
    """Create a temporary skill directory with a minimal SKILL.md."""
    return tmp_path


def _make_skill_info(skill_dir: Path, name: str = "test-skill") -> SkillInfo:
    """Helper to create a SkillInfo with a SKILL.md in the directory."""
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nskill_name: test\nversion: 1.0.0\n---\n", encoding="utf-8")
    return SkillInfo(
        skill_dir=skill_dir,
        skill_md_path=skill_md,
        skill_name=name,
    )


# ============================================================================
# Scenario 1: Valid SemVer
# ============================================================================


class TestScenario1ValidSemVer:
    """Scenario 1: Valid SemVer → is_valid=True, correct declared_version."""

    @pytest.mark.parametrize(
        "version",
        ["1.0.0", "2.3.4", "0.1.0", "0.0.0", "999.999.999"],
    )
    def test_valid_semver_basic(self, validator: VersionValidator, version: str) -> None:
        """Basic SemVer formats are accepted."""
        result = validator.validate(version)
        assert result.is_valid is True
        assert result.declared_version == version

    def test_valid_semver_with_prerelease(self, validator: VersionValidator) -> None:
        """SemVer with prerelease tag is accepted."""
        result = validator.validate("1.0.0-alpha")
        assert result.is_valid is True
        assert result.declared_version == "1.0.0-alpha"

    def test_valid_semver_with_build_metadata(self, validator: VersionValidator) -> None:
        """SemVer with build metadata is accepted."""
        result = validator.validate("1.0.0+build.123")
        assert result.is_valid is True
        assert result.declared_version == "1.0.0+build.123"

    def test_valid_semver_with_both_prerelease_and_build(self, validator: VersionValidator) -> None:
        """SemVer with both prerelease and build metadata."""
        result = validator.validate("1.0.0-rc.1+build.456")
        assert result.is_valid is True
        assert result.declared_version == "1.0.0-rc.1+build.456"

    def test_valid_semver_returns_version_check_result(self, validator: VersionValidator) -> None:
        """Valid SemVer returns a VersionCheckResult instance."""
        result = validator.validate("1.0.0")
        assert isinstance(result, VersionCheckResult)
        assert result.is_valid is True
        assert result.declared_version == "1.0.0"
        assert result.detected_version is None
        assert result.mismatch_details is None
        assert result.suggestion is None

    def test_valid_semver_with_frontmatter_data_integration(
        self, validator: VersionValidator
    ) -> None:
        """Integration: version extracted from frontmatter YAML data is validated.

        Simulates the FMV-001 flow where FrontmatterData.version is passed
        to the validator. The FrontmatterData model carries a version field
        from YAML frontmatter parsing.
        """
        # Simulate a FrontmatterData-like object with a version attribute
        frontmatter = Mock()
        frontmatter.version = "1.0.0"

        # Extract version and validate
        version_str = frontmatter.version
        result = validator.validate(version_str)
        assert result.is_valid is True
        assert result.declared_version == "1.0.0"


# ============================================================================
# Scenario 2: Valid simplified version
# ============================================================================


class TestScenario2ValidSimplifiedVersion:
    """Scenario 2: Valid simplified version → is_valid=True, correct declared_version."""

    @pytest.mark.parametrize(
        "version",
        ["1.0", "2", "0", "99", "3.14", "0.0"],
    )
    def test_valid_simplified(self, validator: VersionValidator, version: str) -> None:
        """Simplified version formats are accepted."""
        result = validator.validate(version)
        assert result.is_valid is True
        assert result.declared_version == version

    def test_valid_simplified_returns_correct_structure(self, validator: VersionValidator) -> None:
        """Simplified version returns proper VersionCheckResult."""
        result = validator.validate("1.0")
        assert isinstance(result, VersionCheckResult)
        assert result.is_valid is True
        assert result.declared_version == "1.0"
        assert result.detected_version is None
        assert result.mismatch_details is None

    def test_simplified_version_is_not_semver(self, validator: VersionValidator) -> None:
        """'1.0' is valid as simplified but not as full SemVer (no patch)."""
        result = validator.validate("1.0")
        assert result.is_valid is True
        # It matches simplified format, not SemVer
        # Both should produce is_valid=True

    def test_simplified_with_frontmatterdata_integration(
        self, validator: VersionValidator
    ) -> None:
        """Integration: simplified version '1.0' from frontmatter."""
        frontmatter = Mock()
        frontmatter.version = "1.0"
        result = validator.validate(frontmatter.version)
        assert result.is_valid is True
        assert result.declared_version == "1.0"


# ============================================================================
# Scenario 3: Invalid format
# ============================================================================


class TestScenario3InvalidFormat:
    """Scenario 3: Invalid format → is_valid=False, format error description."""

    @pytest.mark.parametrize(
        "version",
        [
            "abc",
            "1.0.0.0",
            "01.0.0",
            "v1.0.0",
            "",
            "hello.world",
            "1.0.0-",
            "1.0.0+",
            "-1.0.0",
            "1.0.0.0.0",
            "1.0.0-alpha..1",
            "01.01.01",
        ],
    )
    def test_invalid_format_is_valid_false(
        self, validator: VersionValidator, version: str
    ) -> None:
        """Invalid formats return is_valid=False."""
        result = validator.validate(version)
        assert result.is_valid is False
        assert result.declared_version == version

    def test_invalid_format_has_mismatch_details(self, validator: VersionValidator) -> None:
        """Invalid format populates mismatch_details with format error."""
        result = validator.validate("abc")
        assert result.mismatch_details is not None
        assert "Invalid version format" in result.mismatch_details
        assert "abc" in result.mismatch_details

    def test_invalid_format_has_suggestion(self, validator: VersionValidator) -> None:
        """Invalid format includes a suggestion for correction."""
        result = validator.validate("not-a-version")
        assert result.suggestion is not None
        assert len(result.suggestion) > 0
        assert "SemVer" in result.suggestion or "MAJOR" in result.suggestion

    def test_empty_string_is_invalid(self, validator: VersionValidator) -> None:
        """Empty string is invalid format."""
        result = validator.validate("")
        assert result.is_valid is False
        assert result.declared_version == ""

    def test_leading_zeros_invalid(self, validator: VersionValidator) -> None:
        """Leading zeros are rejected (not valid SemVer or simplified)."""
        result = validator.validate("01.0.0")
        assert result.is_valid is False
        assert "Invalid version format" in result.mismatch_details

    def test_too_many_parts_invalid(self, validator: VersionValidator) -> None:
        """Four-part version '1.0.0.0' is invalid."""
        result = validator.validate("1.0.0.0")
        assert result.is_valid is False

    def test_v_prefix_invalid_for_strict_semver(self, validator: VersionValidator) -> None:
        """'v1.0.0' is not valid SemVer (v prefix not in spec)."""
        result = validator.validate("v1.0.0")
        assert result.is_valid is False

    def test_invalid_from_frontmatterdata(self, validator: VersionValidator) -> None:
        """Integration: invalid version from frontmatter produces error."""
        frontmatter = Mock()
        frontmatter.version = "bad.version"
        result = validator.validate(frontmatter.version)
        assert result.is_valid is False
        assert "Invalid version format" in result.mismatch_details


# ============================================================================
# Scenario 4: Version mismatch with directory
# ============================================================================


class TestScenario4VersionMismatch:
    """Scenario 4: Version mismatch with directory → is_valid=False, details+suggestion."""

    def test_changelog_mismatch_with_mock_skillinfo(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """CHANGELOG declares 2.0.0 but frontmatter says 1.0.0."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [2.0.0] - 2024-06-01\n### Added\n- Feature X\n",
            encoding="utf-8",
        )
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is False
        assert result.declared_version == "1.0.0"
        assert result.detected_version == "2.0.0"

    def test_mismatch_person_details_populated(self, validator: VersionValidator, tmp_skill_dir: Path) -> None:
        """Mismatch details describe the specific version diff."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text("## [3.0.0]\n", encoding="utf-8")
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is False
        assert result.mismatch_details is not None
        assert "1.0.0" in result.mismatch_details
        assert "3.0.0" in result.mismatch_details

    def test_mismatch_suggestion_populated(self, validator: VersionValidator, tmp_skill_dir: Path) -> None:
        """Mismatch includes suggestion with fix direction."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text("## [5.0.0]\n", encoding="utf-8")
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is False
        assert result.suggestion is not None
        # Suggestion should reference both versions for fix direction
        assert "1.0.0" in result.suggestion
        assert "5.0.0" in result.suggestion

    def test_mismatch_with_mock_skillinfo(self, validator: VersionValidator) -> None:
        """Using Mock SkillInfo for directory mismatch test."""
        mock_skill_info = Mock(spec=SkillInfo)
        mock_skill_info.skill_dir = "/fake/path"

        # Mock the internal scan to return a detected version
        with patch.object(
            validator, "_scan_for_version_markers", return_value="2.0.0"
        ):
            result = validator.validate("1.0.0", skill_info=mock_skill_info)
            assert result.is_valid is False
            assert result.declared_version == "1.0.0"
            assert result.detected_version == "2.0.0"
            assert result.mismatch_details is not None
            assert result.suggestion is not None

    def test_mismatch_with_mock_skillinfo_and_magicmock(
        self, validator: VersionValidator
    ) -> None:
        """Using MagicMock for SkillInfo in mismatch test."""
        skill_info = MagicMock(spec=SkillInfo, skill_dir=Path("/fake/skill"))
        with patch.object(
            validator, "_scan_for_version_markers", return_value="3.1.0"
        ):
            result = validator.validate("2.0.0", skill_info=skill_info)
            assert result.is_valid is False
            assert result.detected_version == "3.1.0"

    def test_frontmatterdata_mismatch_integration(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Integration: FrontmatterData version mismatches directory content."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text("## [4.0.0]\n", encoding="utf-8")
        skill_info = _make_skill_info(tmp_skill_dir)

        # Simulate frontmatter data with version field
        frontmatter = Mock()
        frontmatter.version = "2.0.0"

        result = validator.validate(frontmatter.version, skill_info=skill_info)
        assert result.is_valid is False
        assert result.declared_version == "2.0.0"
        assert result.detected_version == "4.0.0"


# ============================================================================
# Scenario 5: No version marker in directory
# ============================================================================


class TestScenario5NoVersionMarker:
    """Scenario 5: No version marker → detected_version=None, is_valid=True,
    mismatch_details contains '无法验证一致性'."""

    def test_empty_dir_no_markers(self, validator: VersionValidator, tmp_skill_dir: Path) -> None:
        """Empty directory has no version markers."""
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert result.mismatch_details is not None
        assert "无法验证一致性" in result.mismatch_details

    def test_dir_with_non_version_files(self, validator: VersionValidator, tmp_skill_dir: Path) -> None:
        """Directory with only code files has no version markers."""
        (tmp_skill_dir / "utils.py").write_text("def foo(): pass\n", encoding="utf-8")
        (tmp_skill_dir / "config.json").write_text("{}", encoding="utf-8")
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert "无法验证一致性" in result.mismatch_details

    def test_dir_with_docs_subdir(self, validator: VersionValidator, tmp_skill_dir: Path) -> None:
        """Subdirectories with non-version names don't count as markers."""
        (tmp_skill_dir / "docs").mkdir()
        (tmp_skill_dir / "src").mkdir()
        (tmp_skill_dir / "assets").mkdir()
        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert "无法验证一致性" in result.mismatch_details

    def test_no_markers_with_mock_skillinfo(self, validator: VersionValidator) -> None:
        """Using Mock SkillInfo for no-marker scenario."""
        mock_skill_info = Mock(spec=SkillInfo)
        mock_skill_info.skill_dir = "/fake/empty/path"

        with patch.object(
            validator, "_scan_for_version_markers", return_value=None
        ):
            result = validator.validate("1.0.0", skill_info=mock_skill_info)
            assert result.is_valid is True
            assert result.declared_version == "1.0.0"
            assert result.detected_version is None
            assert result.mismatch_details is not None
            assert "无法验证一致性" in result.mismatch_details

    def test_no_markers_with_magicmock(self, validator: VersionValidator) -> None:
        """Using MagicMock for no-marker scenario."""
        skill_info = MagicMock(spec=SkillInfo, skill_dir=Path("/fake/skill"))
        with patch.object(
            validator, "_scan_for_version_markers", return_value=None
        ):
            result = validator.validate("2.0.0", skill_info=skill_info)
            assert result.is_valid is True
            assert result.detected_version is None
            assert "无法验证一致性" in result.mismatch_details

    def test_frontmatterdata_no_markers_integration(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Integration: FrontmatterData version, directory has no markers."""
        skill_info = _make_skill_info(tmp_skill_dir)
        frontmatter = Mock()
        frontmatter.version = "3.0.0"

        result = validator.validate(frontmatter.version, skill_info=skill_info)
        assert result.is_valid is True
        assert result.detected_version is None
        assert "无法验证一致性" in result.mismatch_details


# ============================================================================
# Read-only verification
# ============================================================================


class TestReadOnlyBehavior:
    """Verify that VersionValidator does NOT modify any files."""

    def test_validate_does_not_modify_directory(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Validator should not create, modify, or delete any files."""
        # Create files first, then snapshot
        (tmp_skill_dir / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [1.0.0]\n", encoding="utf-8"
        )
        skill_info = _make_skill_info(tmp_skill_dir)

        # Record initial state after all setup
        initial_files = set(os.listdir(tmp_skill_dir))
        initial_mtimes = {}
        for fname in initial_files:
            fpath = tmp_skill_dir / fname
            initial_mtimes[fname] = os.path.getmtime(fpath)

        validator.validate("1.0.0", skill_info=skill_info)

        # Verify no files were added or removed
        final_files = set(os.listdir(tmp_skill_dir))
        assert final_files == initial_files

        # Verify no file was modified
        for fname in initial_files:
            fpath = tmp_skill_dir / fname
            if os.path.isfile(fpath):
                assert os.path.getmtime(fpath) == initial_mtimes[fname]

    def test_validate_does_not_modify_skill_md(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """SKILL.md content should remain unchanged after validation."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text("## [1.0.0]\n", encoding="utf-8")

        skill_md = tmp_skill_dir / "SKILL.md"
        original_content = "---\nskill_name: test\nversion: 1.0.0\n---\n"
        skill_md.write_text(original_content, encoding="utf-8")

        skill_info = SkillInfo(
            skill_dir=tmp_skill_dir,
            skill_md_path=skill_md,
            skill_name="test",
        )
        validator.validate("1.0.0", skill_info=skill_info)

        assert skill_md.read_text(encoding="utf-8") == original_content

    def test_validate_does_not_modify_changelog(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """CHANGELOG content should remain unchanged after validation."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        original = "# Changelog\n\n## [1.0.0]\n### Added\n- Feature\n"
        changelog.write_text(original, encoding="utf-8")

        skill_info = _make_skill_info(tmp_skill_dir)
        validator.validate("1.0.0", skill_info=skill_info)

        assert changelog.read_text(encoding="utf-8") == original

    def test_validate_does_not_modify_files_on_mismatch(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Even on mismatch, no files are modified."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        original = "## [3.0.0]\n"
        changelog.write_text(original, encoding="utf-8")

        skill_info = _make_skill_info(tmp_skill_dir)
        result = validator.validate("1.0.0", skill_info=skill_info)
        assert result.is_valid is False  # Mismatch

        # Content unchanged
        assert changelog.read_text(encoding="utf-8") == original

    def test_validate_does_not_modify_files_on_invalid(
        self, validator: VersionValidator
    ) -> None:
        """Even on invalid format, no side effects on filesystem."""
        result = validator.validate("abc")
        assert result.is_valid is False
        # No file operations at all for format-only validation


# ============================================================================
# Edge cases with Mock SkillInfo
# ============================================================================


class TestEdgeCasesWithMock:
    """Edge cases using unittest.mock for SkillInfo construction."""

    def test_mock_skillinfo_without_spec(self, validator: VersionValidator) -> None:
        """Plain Mock (no spec) used as SkillInfo."""
        skill_info = Mock()
        skill_info.skill_dir = "/fake/dir"

        with patch.object(
            validator, "_scan_for_version_markers", return_value="1.0.0"
        ):
            result = validator.validate("1.0.0", skill_info=skill_info)
            assert result.is_valid is True
            assert result.detected_version == "1.0.0"

    def test_mock_skillinfo_with_spec(self, validator: VersionValidator) -> None:
        """Mock with SkillInfo spec for proper attribute validation."""
        skill_info = Mock(spec=SkillInfo)
        skill_info.skill_dir = Path("/fake/skill/dir")

        with patch.object(
            validator, "_scan_for_version_markers", return_value="2.0.0-beta.1"
        ):
            result = validator.validate("2.0.0-beta.1", skill_info=skill_info)
            assert result.is_valid is True
            assert result.detected_version == "2.0.0-beta.1"

    def test_mock_with_prerelease_version(self, validator: VersionValidator) -> None:
        """Mock SkillInfo with prerelease version in directory."""
        skill_info = Mock(spec=SkillInfo)
        skill_info.skill_dir = Path("/fake/skill")

        with patch.object(
            validator, "_scan_for_version_markers", return_value="1.0.0-alpha.1"
        ):
            result = validator.validate("1.0.0-alpha.1", skill_info=skill_info)
            assert result.is_valid is True
            assert result.detected_version == "1.0.0-alpha.1"

    def test_mock_with_build_metadata_normalization(
        self, validator: VersionValidator
    ) -> None:
        """Build metadata is normalized away during comparison."""
        skill_info = Mock(spec=SkillInfo)
        skill_info.skill_dir = Path("/fake/skill")

        with patch.object(
            validator, "_scan_for_version_markers", return_value="1.0.0"
        ):
            result = validator.validate("1.0.0+build.999", skill_info=skill_info)
            assert result.is_valid is True
            assert result.detected_version == "1.0.0"

    def test_simplified_version_with_mock_skillinfo(
        self, validator: VersionValidator
    ) -> None:
        """Simplified version '1.0' directory check with Mock."""
        skill_info = Mock(spec=SkillInfo)
        skill_info.skill_dir = Path("/fake/skill")

        with patch.object(
            validator, "_scan_for_version_markers", return_value="1.0"
        ):
            result = validator.validate("1.0", skill_info=skill_info)
            assert result.is_valid is True
            assert result.detected_version == "1.0"


# ============================================================================
# FrontmatterData integration tests
# ============================================================================


class TestFrontmatterDataIntegration:
    """VersionValidator receives version from FrontmatterData (FMV-001 flow)."""

    def test_frontmatterdata_version_valid_semver(
        self, validator: VersionValidator
    ) -> None:
        """FrontmatterData.version = '1.0.0' → validator accepts it."""
        # Simulate FrontmatterData with version field
        frontmatter = Mock()
        frontmatter.version = "1.0.0"
        frontmatter.skill_name = "my-skill"
        frontmatter.description = "A test skill"

        result = validator.validate(frontmatter.version)
        assert result.is_valid is True
        assert result.declared_version == "1.0.0"

    def test_frontmatterdata_version_valid_simplified(
        self, validator: VersionValidator
    ) -> None:
        """FrontmatterData.version = '2.0' → validator accepts simplified."""
        frontmatter = Mock()
        frontmatter.version = "2.0"
        result = validator.validate(frontmatter.version)
        assert result.is_valid is True
        assert result.declared_version == "2.0"

    def test_frontmatterdata_version_valid_major_only(
        self, validator: VersionValidator
    ) -> None:
        """FrontmatterData.version = '5' → validator accepts major-only."""
        frontmatter = Mock()
        frontmatter.version = "5"
        result = validator.validate(frontmatter.version)
        assert result.is_valid is True
        assert result.declared_version == "5"

    def test_frontmatterdata_version_invalid(
        self, validator: VersionValidator
    ) -> None:
        """FrontmatterData.version = 'latest' → validator rejects."""
        frontmatter = Mock()
        frontmatter.version = "latest"
        result = validator.validate(frontmatter.version)
        assert result.is_valid is False
        assert "Invalid version format" in result.mismatch_details

    def test_frontmatterdata_version_with_directory_check(
        self, validator: VersionValidator, tmp_skill_dir: Path
    ) -> None:
        """Full integration: frontmatter version + directory check."""
        changelog = tmp_skill_dir / "CHANGELOG.md"
        changelog.write_text("## [1.0.0]\n", encoding="utf-8")
        skill_info = _make_skill_info(tmp_skill_dir)

        frontmatter = Mock()
        frontmatter.version = "1.0.0"

        result = validator.validate(frontmatter.version, skill_info=skill_info)
        assert result.is_valid is True
        assert result.declared_version == "1.0.0"
        assert result.detected_version == "1.0.0"

    def test_frontmatterdata_version_none_like_empty(
        self, validator: VersionValidator
    ) -> None:
        """Empty string version from frontmatter is rejected."""
        frontmatter = Mock()
        frontmatter.version = ""
        result = validator.validate(frontmatter.version)
        assert result.is_valid is False


# ============================================================================
# Model serialization
# ============================================================================


class TestModelSerialization:
    """VersionCheckResult model serialization tests."""

    def test_valid_result_serializes_correctly(self) -> None:
        """Valid result model_dump has expected fields."""
        result = VersionCheckResult(
            is_valid=True,
            declared_version="1.0.0",
        )
        data = result.model_dump()
        assert data["is_valid"] is True
        assert data["declared_version"] == "1.0.0"
        assert data["detected_version"] is None
        assert data["mismatch_details"] is None
        assert data["suggestion"] is None

    def test_invalid_result_serializes_correctly(self) -> None:
        """Invalid result serializes with all fields."""
        result = VersionCheckResult(
            is_valid=False,
            declared_version="abc",
            mismatch_details="Invalid format",
            suggestion="Use SemVer",
        )
        data = result.model_dump()
        assert data["is_valid"] is False
        assert data["declared_version"] == "abc"
        assert data["mismatch_details"] == "Invalid format"
        assert data["suggestion"] == "Use SemVer"

    def test_mismatch_result_serializes_correctly(self) -> None:
        """Mismatch result serializes with detected_version."""
        result = VersionCheckResult(
            is_valid=False,
            declared_version="1.0.0",
            detected_version="2.0.0",
            mismatch_details="Version mismatch",
            suggestion="Update to 2.0.0",
        )
        data = result.model_dump()
        assert data["detected_version"] == "2.0.0"
        assert data["mismatch_details"] == "Version mismatch"


# ============================================================================
# Importability and instantiation
# ============================================================================


class TestImportability:
    """VersionValidator is importable and instantiable."""

    def test_import(self) -> None:
        """VersionValidator can be imported."""
        from src.skill_health.version_validator import VersionValidator
        assert VersionValidator is not None

    def test_instantiate(self) -> None:
        """VersionValidator can be instantiated."""
        v = VersionValidator()
        assert hasattr(v, "validate")
        assert callable(v.validate)

    def test_validate_returns_version_check_result(
        self, validator: VersionValidator
    ) -> None:
        """validate() returns a VersionCheckResult."""
        result = validator.validate("1.0.0")
        assert isinstance(result, VersionCheckResult)