"""VersionValidator — format validation and directory consistency check.

This module validates version strings declared in skill frontmatter against
two supported formats (SemVer 2.0.0 and simplified version numbers), and
optionally checks consistency between the declared version and version
markers found in the skill directory.

Supported version formats:
1. SemVer MAJOR.MINOR.PATCH (official SemVer 2.0.0 regex)
   Reference: https://semver.org/
2. Simplified: '1.0' or '2' (major-only or major.minor)

Directory version markers detected:
- CHANGELOG entries: '## [2.0.0]', '## [1.0.0]'
- Version-tagged files: 'v2.0.0', 'v1.0.0'
- Directory names containing version identifiers

Integration with FMV-001:
    The caller extracts frontmatter_data.version (from FrontmatterData)
    and passes it as version_str to validate(). This component does NOT
    execute repairs — it only outputs VersionCheckResult for fix_engine
    downstream consumption.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from .skill_info import SkillInfo
from .version_check_result import VersionCheckResult


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Official SemVer 2.0.0 regex from https://semver.org/
# Handles MAJOR.MINOR.PATCH with optional prerelease and build metadata.
_SEMVER_REGEX: re.Pattern[str] = re.compile(
    r"^(0|[1-9]\d*)"
    r"\.(0|[1-9]\d*)"
    r"\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# Simplified version: major-only ('2') or major.minor ('1.0')
_SIMPLIFIED_REGEX: re.Pattern[str] = re.compile(
    r"^(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))?$"
)

# ---------------------------------------------------------------------------
# Directory scanning patterns
# ---------------------------------------------------------------------------

# CHANGELOG heading: ## [2.0.0] or ## [v2.0.0] or ## 2.0.0 or ## [1.0]
# Supports both full SemVer (MAJOR.MINOR.PATCH) and simplified (MAJOR.MINOR)
_CHANGELOG_VERSION_RE: re.Pattern[str] = re.compile(
    r"^##\s+\[?v?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:\.(?:0|[1-9]\d*)"
    r"(?:-[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?)?)\]?",
    re.MULTILINE,
)

# Version-tagged file or directory name: v2.0.0, 2.0.0, v1.0, 1.0, etc.
_VERSION_TAG_RE: re.Pattern[str] = re.compile(
    r"^v?((?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))?"
    r"(?:\.(?:0|[1-9]\d*)"
    r"(?:-[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?))$"
)

# Names that are likely CHANGELOG files (case-insensitive)
_CHANGELOG_NAMES: frozenset[str] = frozenset(
    {"changelog", "changelog.md", "changelog.txt", "changes", "changes.md",
     "history", "history.md", "release_notes", "release_notes.md"}
)


class VersionValidator:
    """Validates version strings and checks directory content consistency.

    This validator performs two levels of checking:

    1. **Format validation** (always): Checks whether the version string
       matches one of the two supported formats (SemVer or simplified).

    2. **Directory consistency check** (optional): When a SkillInfo is
       provided, scans the skill directory for version markers and compares
       them against the declared version.

    This component does NOT execute repairs — it only outputs
    VersionCheckResult for fix_engine downstream consumption.

    Example:
        >>> validator = VersionValidator()
        >>> result = validator.validate("1.0.0")
        >>> result.is_valid
        True
        >>> result = validator.validate("not-a-version")
        >>> result.is_valid
        False
    """

    def validate(
        self,
        version_str: str,
        skill_info: SkillInfo | None = None,
    ) -> VersionCheckResult:
        """Validate a version string and optionally check directory consistency.

        Args:
            version_str: The version string as declared in frontmatter.
            skill_info: Optional SkillInfo for directory consistency check.
                When provided, the validator scans skill_info.skill_dir for
                version markers and compares them with version_str.

        Returns:
            VersionCheckResult with validation outcome. Always populated
            with is_valid and declared_version. When directory check is
            performed, also populated with detected_version and
            mismatch_details on mismatch.
        """
        # --- Step 1: Format validation ---
        format_result = self._validate_format(version_str)
        if format_result is not None:
            # Format is invalid — return immediately
            return format_result

        # --- Step 2: Directory consistency check (optional) ---
        if skill_info is not None:
            return self._check_directory_consistency(version_str, skill_info)

        # Format is valid, no directory check requested
        return VersionCheckResult(
            is_valid=True,
            declared_version=version_str,
        )

    def _validate_format(self, version_str: str) -> Optional[VersionCheckResult]:
        """Check if version_str matches SemVer or simplified format.

        Returns:
            None if format is valid (caller continues to next step).
            VersionCheckResult(is_valid=False, ...) if format is invalid.
        """
        # Try SemVer first (strictest)
        if _SEMVER_REGEX.match(version_str):
            return None  # Valid SemVer

        # Try simplified format
        if _SIMPLIFIED_REGEX.match(version_str):
            return None  # Valid simplified version

        # Invalid format — build a descriptive error
        return VersionCheckResult(
            is_valid=False,
            declared_version=version_str,
            mismatch_details=(
                f"Invalid version format: '{version_str}' does not match "
                f"SemVer (MAJOR.MINOR.PATCH) or simplified (MAJOR or "
                f"MAJOR.MINOR) format. "
                f"Examples of valid formats: '1.0.0', '2.1.0-beta.1', "
                f"'1.0', '2'."
            ),
            suggestion=(
                "Use SemVer format (MAJOR.MINOR.PATCH) for full version "
                "declaration, or simplified format (MAJOR or MAJOR.MINOR) "
                "for less specific versioning."
            ),
        )

    def _check_directory_consistency(
        self,
        version_str: str,
        skill_info: SkillInfo,
    ) -> VersionCheckResult:
        """Scan skill directory for version markers and compare with declared.

        Scans for:
        - CHANGELOG files with version headings (e.g. '## [2.0.0]')
        - Version-tagged files or directories (e.g. 'v2.0.0')

        Returns:
            VersionCheckResult with directory consistency outcome.
        """
        skill_dir = skill_info.skill_dir
        detected_version = self._scan_for_version_markers(skill_dir)

        if detected_version is None:
            # No version markers found in directory
            return VersionCheckResult(
                is_valid=True,
                declared_version=version_str,
                detected_version=None,
                mismatch_details="无法验证一致性：目录中未发现版本标记",
            )

        # Normalize both versions for comparison
        normalized_declared = self._normalize_version(version_str)
        normalized_detected = self._normalize_version(detected_version)

        if normalized_declared == normalized_detected:
            # Versions match
            return VersionCheckResult(
                is_valid=True,
                declared_version=version_str,
                detected_version=detected_version,
            )

        # Mismatch detected
        return VersionCheckResult(
            is_valid=False,
            declared_version=version_str,
            detected_version=detected_version,
            mismatch_details=(
                f"Version mismatch: frontmatter declares '{version_str}' "
                f"but directory content shows '{detected_version}'. "
                f"The declared version does not match the version found "
                f"in the skill directory."
            ),
            suggestion=(
                f"Update declared_version from '{version_str}' to "
                f"'{detected_version}' to match directory content, "
                f"or update directory content to match the declared version."
            ),
        )

    def _scan_for_version_markers(self, skill_dir: os.PathLike[str]) -> Optional[str]:
        """Scan a directory for version markers.

        Checks:
        1. CHANGELOG-like files for version headings
        2. Subdirectory names matching version patterns
        3. File names matching version patterns (excluding .py, .pyc, etc.)

        Returns:
            The first detected version string, or None if no markers found.
            Prefers CHANGELOG entries (most authoritative), then directory
            names, then file names.
        """
        skill_path = os.fspath(skill_dir)

        try:
            entries = os.listdir(skill_path)
        except (OSError, PermissionError):
            return None

        # --- Priority 1: CHANGELOG files ---
        for entry_name in sorted(entries):
            if entry_name.lower() in _CHANGELOG_NAMES:
                file_path = os.path.join(skill_path, entry_name)
                if os.path.isfile(file_path):
                    version = self._scan_changelog_file(file_path)
                    if version is not None:
                        return version

        # --- Priority 2: Subdirectory names ---
        for entry_name in sorted(entries):
            entry_path = os.path.join(skill_path, entry_name)
            if os.path.isdir(entry_path):
                match = _VERSION_TAG_RE.match(entry_name)
                if match:
                    return match.group(1)

        # --- Priority 3: File names (non-CHANGELOG) ---
        # Skip common non-version files
        _SKIP_EXTENSIONS = frozenset({
            ".py", ".pyc", ".pyo", ".md", ".txt", ".json", ".yaml", ".yml",
            ".toml", ".cfg", ".ini", ".sh", ".bash", ".env", ".git",
        })
        for entry_name in sorted(entries):
            entry_path = os.path.join(skill_path, entry_name)
            if not os.path.isfile(entry_path):
                continue
            # Skip files with common code/config extensions
            _, ext = os.path.splitext(entry_name)
            if ext.lower() in _SKIP_EXTENSIONS:
                continue
            if entry_name.lower() in _CHANGELOG_NAMES:
                continue
            match = _VERSION_TAG_RE.match(entry_name)
            if match:
                return match.group(1)

        return None

    def _scan_changelog_file(self, file_path: str) -> Optional[str]:
        """Extract the first (most recent) version from a CHANGELOG file.

        Looks for patterns like:
        - ## [2.0.0]
        - ## [v1.0.0]
        - ## 2.0.0
        - ## 1.0.0-beta.1

        Returns:
            The first version string found, or None.
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(8192)  # Read first 8KB — enough for changelogs
        except (OSError, PermissionError):
            return None

        match = _CHANGELOG_VERSION_RE.search(content)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def _normalize_version(version: str) -> str:
        """Normalize a version string for comparison.

        Strips leading 'v', removes build metadata (after '+'),
        and ensures consistent format.

        Examples:
            'v1.0.0' -> '1.0.0'
            '1.0.0+build.123' -> '1.0.0'
            '1.0' -> '1.0'
            '2' -> '2'
        """
        normalized = version.strip()
        # Strip leading 'v' or 'V'
        if normalized.startswith(("v", "V")):
            normalized = normalized[1:]
        # Remove build metadata (everything after '+')
        plus_idx = normalized.find("+")
        if plus_idx != -1:
            normalized = normalized[:plus_idx]
        return normalized
