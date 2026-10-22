"""Exit Code Decision Logic for Skill Health CLI.

This module implements the exit code determination logic for the skill health
CLI tool. It follows standard Unix/POSIX conventions:
    - Exit code 0: Success (all checks passed or warnings only)
    - Exit code 1: Failure (at least one check failed)
    - Exit code 2: Usage error (invalid arguments or parameters)

The main function `determine_exit_code()` accepts a ReportModel and returns
the appropriate exit code based on the aggregate status of all skills.

Design decisions:
    - Warnings are non-blocking (exit 0) — they inform but don't fail CI/CD
    - Any failure triggers exit 1 — CI/CD pipelines can detect issues
    - Parameter errors use exit 2 — follows argparse convention
    - Empty reports (no skills) return 0 — no issues found

Integration:
    - Call `determine_exit_code(report)` after printing the summary
    - Use `sys.exit(code)` to terminate the process
    - For CLI argument errors, raise SystemExit(2) directly
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .report_model import ReportModel, SkillReport


# ---------------------------------------------------------------------------
# Exit code constants
# ---------------------------------------------------------------------------

EXIT_SUCCESS = 0
"""Exit code for successful execution (all pass or warnings only)."""

EXIT_FAILURE = 1
"""Exit code for general failures (at least one check failed)."""

EXIT_USAGE_ERROR = 2
"""Exit code for command-line usage errors (invalid arguments)."""


# ---------------------------------------------------------------------------
# Core exit code determination
# ---------------------------------------------------------------------------

def determine_exit_code(report: "ReportModel") -> int:
    """Determine the CLI exit code from a completed report.

    This function implements the Exit Code Decision Logic:
        - All checks passed → EXIT_SUCCESS (0)
        - Warnings present but no failures → EXIT_SUCCESS (0)
        - At least one failure → EXIT_FAILURE (1)
        - (Parameter errors handled separately via SystemExit(2))

    Parameters
    ----------
    report : ReportModel
        The completed report containing summary statistics and per-skill
        check results. The function examines `report.summary.failed` to
        determine if any skill has failed checks.

    Returns
    -------
    int
        The exit code to pass to `sys.exit()`:
            - 0 (EXIT_SUCCESS): No failures detected (warnings allowed)
            - 1 (EXIT_FAILURE): At least one skill has failed checks

    Examples
    --------
    >>> from skill_health.report_model import ReportModel, Summary, ScanMetadata
    >>> report = ReportModel(
    ...     scan_metadata=ScanMetadata(
    ...         scan_timestamp="2026-07-16T00:00:00Z",
    ...         target_path="/skills",
    ...         skill_count=3
    ...     ),
    ...     summary=Summary(total=3, passed=2, warned=1, failed=0),
    ...     skill_reports=[]
    ... )
    >>> determine_exit_code(report)
    0

    >>> report.summary.failed = 1
    >>> determine_exit_code(report)
    1

    Notes
    -----
    - Warnings are intentionally non-blocking. This allows CI/CD pipelines
      to continue on warnings while still failing on actual issues.
    - The function does NOT call `sys.exit()` itself. The caller is
      responsible for terminating the process.
    - Empty reports (summary.total == 0) return EXIT_SUCCESS (0).
    """
    # Check if any skill has failed
    if report.summary.failed > 0:
        return EXIT_FAILURE
    
    # Warnings are non-blocking; all-pass and warn-only both return success
    return EXIT_SUCCESS


def determine_exit_code_from_skills(skill_reports: list["SkillReport"]) -> int:
    """Determine exit code from a list of SkillReport objects.

    This is an alternative interface that works directly with skill reports
    instead of a full ReportModel. Useful for testing or when the full
    report is not yet constructed.

    Parameters
    ----------
    skill_reports : list[SkillReport]
        List of per-skill reports, each containing check_results.

    Returns
    -------
    int
        Exit code:
            - 0: No failures (all pass or warnings only)
            - 1: At least one skill has a failed check

    Examples
    --------
    >>> from skill_health.report_model import SkillReport, CheckResult
    >>> skills = [
    ...     SkillReport(
    ...         skill_name="weather",
    ...         skill_path="/skills/weather",
    ...         check_results=[
    ...             CheckResult(checker_name="Desc", status="pass", message="OK")
    ...         ]
    ...     )
    ... ]
    >>> determine_exit_code_from_skills(skills)
    0

    Notes
    -----
    - Iterates through all check_results of all skills to detect any "fail"
    - Empty list returns EXIT_SUCCESS (0)
    """
    for skill_report in skill_reports:
        for check_result in skill_report.check_results:
            if check_result.status == "fail":
                return EXIT_FAILURE
    
    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# CLI integration helpers
# ---------------------------------------------------------------------------

def exit_with_code(report: "ReportModel") -> None:
    """Print summary and exit with the appropriate code.

    This is a convenience function for CLI entry points. It:
        1. Determines the exit code from the report
        2. Calls `sys.exit(code)` to terminate the process

    Parameters
    ----------
    report : ReportModel
        The completed report to evaluate.

    Raises
    ------
    SystemExit
        Always raised with the determined exit code.

    Examples
    --------
    >>> # In a CLI entry point:
    >>> report = run_validation(args.target)
    >>> printer = TerminalSummaryPrinter()
    >>> printer.print(report)
    >>> exit_with_code(report)  # doctest: +SKIP
    """
    code = determine_exit_code(report)
    sys.exit(code)


def raise_usage_error(message: str) -> None:
    """Raise a usage error with exit code 2.

    Use this for CLI argument validation errors (invalid paths, missing
    required arguments, etc.). Follows the argparse convention of using
    exit code 2 for usage errors.

    Parameters
    ----------
    message : str
        Human-readable error message to print to stderr.

    Raises
    ------
    SystemExit
        Always raised with exit code 2.

    Examples
    --------
    >>> if not args.target.exists():
    ...     raise_usage_error(f"Target path does not exist: {args.target}")
    """
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(EXIT_USAGE_ERROR)


# ---------------------------------------------------------------------------
# Module-level exports
# ---------------------------------------------------------------------------

__all__ = [
    "EXIT_SUCCESS",
    "EXIT_FAILURE",
    "EXIT_USAGE_ERROR",
    "determine_exit_code",
    "determine_exit_code_from_skills",
    "exit_with_code",
    "raise_usage_error",
]
