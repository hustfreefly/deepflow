"""Pydantic V2 sub-models for the Skill Health Report system.

Defines the foundational data types used by ReportModel (T-002+):
    - CheckResult: single check outcome from a checker
    - SkillInfo: pipeline input — Skill metadata with check results
    - ScanMetadata: scan context (timestamp, target, count)
    - Summary: aggregate pass/warn/fail statistics
    - SkillReport: per-Skill report entry in the final output
    - ReportModel: top-level report with build() classmethod (T-002)
    - Serialization: to_dict(), to_json(), to_markdown() (T-003)

Status values: pass / warn / fail (not passed/failed/warning).
All fields carry Field(description=..., examples=...) for self-documenting
JSON Schema output via model_json_schema().
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# CheckResult — single check outcome
# ---------------------------------------------------------------------------

class CheckResult(BaseModel):
    """Result of a single checker against a Skill.

    Each checker (e.g. DescriptionChecker, SignatureCalculator) produces one
    CheckResult indicating whether the Skill passed, triggered a warning,
    or failed the check.
    """

    checker_name: str = Field(
        description="Identifier of the checker that produced this result, e.g. 'DescriptionChecker', 'SignatureCalculator'.",
        examples=["DescriptionChecker", "SignatureCalculator", "FrontmatterParser"],
    )
    status: Literal["pass", "warn", "fail"] = Field(
        description="Outcome of the check. 'pass' = check succeeded, 'warn' = non-blocking issue, 'fail' = blocking issue.",
        examples=["pass", "warn", "fail"],
    )
    message: str = Field(
        description="Human-readable summary of the check outcome.",
        examples=["Description length 120 chars (OK)", "Missing SKILL.md version field"],
    )
    details: Optional[dict] = Field(
        default=None,
        description="Optional structured data with checker-specific details (e.g. measured length, threshold).",
        examples=[{"length": 120, "min_length": 30, "max_length": 500}, None],
    )


# ---------------------------------------------------------------------------
# SkillInfo — pipeline input metadata
# ---------------------------------------------------------------------------

class SkillInfo(BaseModel):
    """Skill metadata as consumed by the validation pipeline.

    Represents one Skill discovered during scanning, carrying its check
    results from the validation pipeline output.
    """

    skill_name: str = Field(
        description="Name of the Skill (typically the directory name or SKILL.md title).",
        examples=["weather", "github", "apple-notes"],
    )
    skill_path: str = Field(
        description="Filesystem path to the Skill directory (absolute or relative to scan root).",
        examples=["/Users/allen/.openclaw/workspace/skills/weather", "skills/github"],
    )
    check_results: list[CheckResult] = Field(
        description="List of check results produced by validating this Skill.",
        examples=[
            [
                CheckResult(
                    checker_name="DescriptionChecker",
                    status="pass",
                    message="Description length OK",
                ),
            ]
        ],
    )


# ---------------------------------------------------------------------------
# ScanMetadata — scan context
# ---------------------------------------------------------------------------

class ScanMetadata(BaseModel):
    """Contextual information about the scan that produced the report."""

    scan_timestamp: str = Field(
        description="UTC timestamp of the scan in ISO 8601 format (e.g. '2026-07-16T02:00:00Z').",
        examples=["2026-07-16T02:00:00Z", "2026-01-01T00:00:00Z"],
    )
    target_path: str = Field(
        description="Root directory path that was scanned for Skills.",
        examples=["/Users/allen/.openclaw/workspace/skills", "/opt/homebrew/lib/node_modules/openclaw/skills"],
    )
    skill_count: int = Field(
        description="Total number of Skills discovered during the scan.",
        ge=0,
        examples=[10, 0, 42],
    )


# ---------------------------------------------------------------------------
# Summary — aggregate statistics
# ---------------------------------------------------------------------------

class Summary(BaseModel):
    """Aggregate pass/warn/fail counts across all scanned Skills.

    Each Skill is counted once in exactly one category based on its worst
    check result: any 'fail' → failed; any 'warn' (no fail) → warned;
    all 'pass' → passed.  total = passed + warned + failed.
    """

    total: int = Field(
        description="Total number of Skills scanned.",
        ge=0,
        examples=[10, 0, 42],
    )
    passed: int = Field(
        description="Number of Skills where all checks passed.",
        ge=0,
        examples=[7, 0, 30],
    )
    warned: int = Field(
        description="Number of Skills with warnings but no failures.",
        ge=0,
        examples=[2, 0, 5],
    )
    failed: int = Field(
        description="Number of Skills with at least one failed check.",
        ge=0,
        examples=[1, 0, 7],
    )


# ---------------------------------------------------------------------------
# SkillReport — per-Skill report entry
# ---------------------------------------------------------------------------

class SkillReport(BaseModel):
    """Per-Skill report entry in the final ReportModel output.

    Structurally similar to SkillInfo but represents the output-side view
    of a Skill's validation results.
    """

    skill_name: str = Field(
        description="Name of the Skill.",
        examples=["weather", "github", "apple-notes"],
    )
    skill_path: str = Field(
        description="Filesystem path to the Skill directory.",
        examples=["/Users/allen/.openclaw/workspace/skills/weather", "skills/github"],
    )
    check_results: list[CheckResult] = Field(
        description="All check results for this Skill.",
        examples=[
            [
                CheckResult(
                    checker_name="DescriptionChecker",
                    status="pass",
                    message="Description length OK",
                    details={"length": 120},
                ),
                CheckResult(
                    checker_name="SignatureCalculator",
                    status="pass",
                    message="Signature computed",
                    details={"signature_method": "sha256"},
                ),
            ]
        ],
    )


# ---------------------------------------------------------------------------
# ReportModel — top-level report with build() classmethod (T-002)
# + Serialization methods (T-003)
# ---------------------------------------------------------------------------

def _common_prefix(paths: list[str]) -> str:
    """Compute the longest common directory prefix of a list of paths.

    Uses os.path.commonpath for correctness. Returns empty string if
    the list is empty (caller should handle this case).
    """
    if not paths:
        return ""
    if len(paths) == 1:
        # For a single path, return its directory (the parent)
        return os.path.dirname(paths[0]) if not paths[0].endswith(os.sep) else paths[0]
    try:
        return os.path.commonpath(paths)
    except ValueError:
        # Mixed absolute/relative paths — fall back to empty string
        return ""


def _skill_status(check_results: list[CheckResult]) -> Literal["passed", "warned", "failed"]:
    """Determine the aggregate status of a single Skill from its check results.

    Rules (per WP specification):
        - Any 'fail' → 'failed'
        - Any 'warn' (no fail) → 'warned'
        - All 'pass' (or empty) → 'passed'
    """
    statuses = {cr.status for cr in check_results}
    if "fail" in statuses:
        return "failed"
    if "warn" in statuses:
        return "warned"
    return "passed"


# JSON Schema Draft 2020-12 meta-schema URI (standard identifier)
_JSON_SCHEMA_DRAFT_2020_12_URI = "https://json-schema.org/draft/2020-12/schema"


class ReportModel(BaseModel):
    """Top-level Skill Health Report.

    Aggregates scan metadata, summary statistics, and per-Skill reports
    into a single self-documenting JSON-Schema-ready model.

    Use the ``build()`` classmethod to construct from pipeline outputs
    (CheckResult list + SkillInfo list). Direct construction is also
    supported for testing and deserialization.

    Serialization methods (T-003):
        - ``to_dict()``: full dictionary representation via model_dump()
        - ``to_json()``: JSON string with ``$schema`` field injected
        - ``to_markdown()``: human-readable Markdown report
    """

    scan_metadata: ScanMetadata = Field(
        description="Contextual information about the scan (timestamp, target path, skill count).",
        examples=[
            ScanMetadata(
                scan_timestamp="2026-07-16T02:00:00Z",
                target_path="/Users/allen/.openclaw/workspace/skills",
                skill_count=10,
            )
        ],
    )
    summary: Summary = Field(
        description="Aggregate pass/warn/fail statistics across all Skills.",
        examples=[
            Summary(total=10, passed=7, warned=2, failed=1)
        ],
    )
    skill_reports: list[SkillReport] = Field(
        description="Detailed report for each scanned Skill.",
        default_factory=list,
        examples=[
            [
                SkillReport(
                    skill_name="weather",
                    skill_path="/skills/weather",
                    check_results=[
                        CheckResult(
                            checker_name="DescriptionChecker",
                            status="pass",
                            message="OK",
                        ),
                    ],
                ),
            ]
        ],
    )
    json_schema_version: str = Field(
        default="2020-12",
        description="JSON Schema specification version used for self-documentation output.",
        examples=["2020-12"],
    )

    @classmethod
    def build(
        cls,
        check_results: list[CheckResult],
        skill_infos: list[SkillInfo],
    ) -> "ReportModel":
        """Construct a ReportModel from pipeline outputs.

        Parameters
        ----------
        check_results:
            Flat list of all CheckResult objects across all Skills.
            (Currently unused for aggregation — per-Skill results are
            taken from each SkillInfo.check_results — but accepted for
            interface completeness and future extensions.)
        skill_infos:
            List of SkillInfo objects, each carrying its own check_results.

        Returns
        -------
        ReportModel
            Fully populated report with scan_metadata, summary, and
            skill_reports derived from the inputs.

        Notes
        -----
        - Empty inputs (skill_infos=[]) produce a valid report with
          summary all-zero and empty skill_reports. No exception raised.
        - scan_metadata.target_path is the common directory prefix of
          all skill_paths. Falls back to empty string if no common
          prefix exists or if skill_infos is empty.
        - scan_metadata.scan_timestamp is UTC now in ISO 8601 format.
        """
        # --- scan_metadata ---
        skill_paths = [si.skill_path for si in skill_infos]
        target_path = _common_prefix(skill_paths) if skill_paths else ""
        scan_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        scan_metadata = ScanMetadata(
            scan_timestamp=scan_timestamp,
            target_path=target_path,
            skill_count=len(skill_infos),
        )

        # --- skill_reports + summary ---
        skill_reports: list[SkillReport] = []
        passed_count = 0
        warned_count = 0
        failed_count = 0

        for si in skill_infos:
            # Map SkillInfo → SkillReport (same structure, output-side view)
            skill_report = SkillReport(
                skill_name=si.skill_name,
                skill_path=si.skill_path,
                check_results=list(si.check_results),
            )
            skill_reports.append(skill_report)

            # Classify this Skill's aggregate status
            status = _skill_status(si.check_results)
            if status == "failed":
                failed_count += 1
            elif status == "warned":
                warned_count += 1
            else:
                passed_count += 1

        total = passed_count + warned_count + failed_count
        summary = Summary(
            total=total,
            passed=passed_count,
            warned=warned_count,
            failed=failed_count,
        )

        return cls(
            scan_metadata=scan_metadata,
            summary=summary,
            skill_reports=skill_reports,
        )

    # -------------------------------------------------------------------
    # T-003: Serialization methods
    # -------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return the full dictionary representation of the report.

        Delegates to Pydantic's ``model_dump()`` to preserve all nested
        structures (ScanMetadata, Summary, SkillReport, CheckResult).

        Returns
        -------
        dict
            A JSON-serializable dictionary containing all report fields.
            Nested models are recursively converted to dicts.
        """
        return self.model_dump()

    def to_json(self) -> str:
        """Return a JSON string with an injected ``$schema`` field.

        The output conforms to JSON Schema Draft 2020-12 conventions by
        including a top-level ``"$schema"`` key whose value is the
        standard Draft 2020-12 meta-schema URI.

        Implementation:
            1. ``model_dump()`` to get the base dictionary
            2. Inject ``"$schema"`` key with the Draft 2020-12 URI
            3. ``json.dumps(indent=2)`` for pretty-printed output

        Returns
        -------
        str
            A JSON string (indent=2) containing all report data plus
            the ``$schema`` field at the root level.
        """
        data = self.model_dump()
        data["$schema"] = _JSON_SCHEMA_DRAFT_2020_12_URI
        return json.dumps(data, indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Generate a human-readable Markdown report.

        The output contains:
            a) A **Scan Summary** section with metadata and aggregate
               statistics in table format.
            b) A **Skill Details** section with per-Skill results,
               including each check_result's checker name, status,
               and message.

        Returns
        -------
        str
            A complete Markdown document string.
        """
        lines: list[str] = []

        # --- Title ---
        lines.append("# Skill Health Report")
        lines.append("")

        # --- Scan Summary ---
        lines.append("## Scan Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(
            f"| Scan Time | {self.scan_metadata.scan_timestamp} |"
        )
        lines.append(
            f"| Target | {self.scan_metadata.target_path} |"
        )
        lines.append(
            f"| Total Skills | {self.summary.total} |"
        )
        lines.append(
            f"| Passed | {self.summary.passed} |"
        )
        lines.append(
            f"| Warnings | {self.summary.warned} |"
        )
        lines.append(
            f"| Failed | {self.summary.failed} |"
        )
        lines.append("")

        # --- Skill Details ---
        lines.append("## Skill Details")
        lines.append("")

        if not self.skill_reports:
            lines.append("_No skills scanned._")
            lines.append("")
        else:
            for i, sr in enumerate(self.skill_reports, start=1):
                # Determine aggregate status for this skill
                agg_status = _skill_status(sr.check_results)
                # Status emoji for quick visual scanning
                status_icon = {
                    "passed": "✅",
                    "warned": "⚠️",
                    "failed": "❌",
                }.get(agg_status, "❓")

                lines.append(f"### {i}. {sr.skill_name} {status_icon}")
                lines.append("")
                lines.append(f"**Path**: `{sr.skill_path}`")
                lines.append("")

                if sr.check_results:
                    lines.append("| Checker | Status | Message |")
                    lines.append("|---------|--------|---------|")
                    for cr in sr.check_results:
                        # Status icon for individual check
                        check_icon = {
                            "pass": "✅",
                            "warn": "⚠️",
                            "fail": "❌",
                        }.get(cr.status, "❓")
                        lines.append(
                            f"| {cr.checker_name} | {check_icon} {cr.status} | {cr.message} |"
                        )
                    lines.append("")
                else:
                    lines.append("_No check results available._")
                    lines.append("")

        return "\n".join(lines)
