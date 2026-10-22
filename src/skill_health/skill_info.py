"""
SkillInfo — Pydantic V2 model for skill directory structure representation.

This model encapsulates the directory context that VersionValidator uses
to scan for version markers. It captures the skill's root directory,
the path to SKILL.md, the skill name, and any warnings collected during
directory scanning.

Design note: SkillInfo was originally assumed to come from FMV-001's
scanner_engine, but FMV-001 only delivers FrontmatterData, FrontmatterParser,
and exceptions. FMV-002 defines this minimal SkillInfo containing only
the fields FMV-002 actually needs.
"""

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    """Directory structure information for a skill package.

    Provides the spatial context needed by VersionValidator to perform
    directory content consistency checks. Contains paths to the skill's
    root directory and SKILL.md file, plus the skill's display name.

    Attributes:
        skill_dir: Root directory of the skill package.
            Used by VersionValidator to scan for version markers
            (CHANGELOG entries, version-tagged files, etc.).
        skill_md_path: Absolute path to the SKILL.md file.
            This is the file whose frontmatter version field is
            being validated.
        skill_name: Human-readable name of the skill.
            Used for logging and error messages.
        warnings: Non-blocking warnings collected during directory
            scanning (e.g. missing expected files, permission issues).
            Defaults to an empty list.
    """

    skill_dir: Path = Field(
        ...,
        description="Root directory of the skill package. "
        "Used to scan for version markers.",
    )

    skill_md_path: Path = Field(
        ...,
        description="Absolute path to the SKILL.md file.",
    )

    skill_name: str = Field(
        ...,
        description="Human-readable name of the skill.",
        min_length=1,
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Non-blocking warnings collected during directory scanning.",
    )
