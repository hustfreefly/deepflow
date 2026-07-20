"""Tests for Exit Code Decision Logic.

Covers the four exit code scenarios required by AC-2:
    1. All pass → exit code 0
    2. Has warn, no fail → exit code 0
    3. Has fail → exit code 1
    4. Parameter/usage error → exit code 2

Also covers edge cases:
    - Empty report (no skills) → exit code 0
    - Mixed results across multiple skills
    - determine_exit_code_from_skills() alternative interface
    - exit_with_code() calls sys.exit()
    - raise_usage_error() raises SystemExit(2)
"""

import pytest

from src.skill_health.report_model import (
    CheckResult,
    ReportModel,
    ScanMetadata,
    SkillReport,
    Summary,
)
from src.skill_health.exit_code import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    determine_exit_code,
    determine_exit_code_from_skills,
    exit_with_code,
    raise_usage_error,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_check_result(
    checker_name: str = "TestChecker",
    status: str = "pass",
    message: str = "OK",
) -> CheckResult:
    """Create a CheckResult for testing."""
    return CheckResult(
        checker_name=checker_name,
        status=status,
        message=message,
    )


def _make_skill_report(
    skill_name: str = "test-skill",
    check_results: list[CheckResult] | None = None,
) -> SkillReport:
    """Create a SkillReport for testing."""
    if check_results is None:
        check_results = [_make_check_result()]
    return SkillReport(
        skill_name=skill_name,
        skill_path=f"/skills/{skill_name}",
        check_results=check_results,
    )


def _make_report(
    total: int = 1,
    passed: int = 1,
    warned: int = 0,
    failed: int = 0,
    skill_reports: list[SkillReport] | None = None,
) -> ReportModel:
    """Create a ReportModel for testing."""
    if skill_reports is None:
        skill_reports = [_make_skill_report()]
    return ReportModel(
        scan_metadata=ScanMetadata(
            scan_timestamp="2026-07-16T00:00:00Z",
            target_path="/skills",
            skill_count=total,
        ),
        summary=Summary(
            total=total,
            passed=passed,
            warned=warned,
            failed=failed,
        ),
        skill_reports=skill_reports,
    )


# ===========================================================================
# Scenario 1: All pass → exit code 0
# ===========================================================================

class TestAllPass:
    """All checks passed → exit code 0 (success)."""

    def test_single_skill_all_pass(self):
        """Single skill with all checks passing returns exit code 0."""
        report = _make_report(
            total=1, passed=1, warned=0, failed=0,
            skill_reports=[
                _make_skill_report("weather", [
                    _make_check_result("DescChecker", "pass", "Description OK"),
                    _make_check_result("SigCalc", "pass", "Signature computed"),
                ]),
            ],
        )
        assert determine_exit_code(report) == EXIT_SUCCESS
        assert determine_exit_code(report) == 0

    def test_multiple_skills_all_pass(self):
        """Multiple skills all passing returns exit code 0."""
        report = _make_report(
            total=3, passed=3, warned=0, failed=0,
            skill_reports=[
                _make_skill_report("weather", [_make_check_result(status="pass")]),
                _make_skill_report("github", [_make_check_result(status="pass")]),
                _make_skill_report("apple-notes", [_make_check_result(status="pass")]),
            ],
        )
        assert determine_exit_code(report) == 0

    def test_empty_report_all_pass(self):
        """Empty report (no skills) returns exit code 0."""
        report = _make_report(
            total=0, passed=0, warned=0, failed=0,
            skill_reports=[],
        )
        assert determine_exit_code(report) == 0


# ===========================================================================
# Scenario 2: Has warn, no fail → exit code 0
# ===========================================================================

class TestWarnNoFail:
    """Warnings present but no failures → exit code 0 (non-blocking)."""

    def test_single_skill_warn_only(self):
        """Single skill with warnings but no failures returns exit code 0."""
        report = _make_report(
            total=1, passed=0, warned=1, failed=0,
            skill_reports=[
                _make_skill_report("weather", [
                    _make_check_result("DescChecker", "warn", "Description short"),
                    _make_check_result("SigCalc", "pass", "Signature OK"),
                ]),
            ],
        )
        assert determine_exit_code(report) == EXIT_SUCCESS
        assert determine_exit_code(report) == 0

    def test_mixed_pass_and_warn(self):
        """Mix of passing and warning skills returns exit code 0."""
        report = _make_report(
            total=3, passed=2, warned=1, failed=0,
            skill_reports=[
                _make_skill_report("weather", [_make_check_result(status="pass")]),
                _make_skill_report("github", [_make_check_result(status="warn")]),
                _make_skill_report("notes", [_make_check_result(status="pass")]),
            ],
        )
        assert determine_exit_code(report) == 0

    def test_all_warn(self):
        """All skills with warnings (no failures) returns exit code 0."""
        report = _make_report(
            total=2, passed=0, warned=2, failed=0,
            skill_reports=[
                _make_skill_report("a", [_make_check_result(status="warn")]),
                _make_skill_report("b", [_make_check_result(status="warn")]),
            ],
        )
        assert determine_exit_code(report) == 0


# ===========================================================================
# Scenario 3: Has fail → exit code 1
# ===========================================================================

class TestHasFail:
    """At least one failure → exit code 1 (failure)."""

    def test_single_skill_fail(self):
        """Single skill with a failure returns exit code 1."""
        report = _make_report(
            total=1, passed=0, warned=0, failed=1,
            skill_reports=[
                _make_skill_report("weather", [
                    _make_check_result("DescChecker", "fail", "Missing description"),
                ]),
            ],
        )
        assert determine_exit_code(report) == EXIT_FAILURE
        assert determine_exit_code(report) == 1

    def test_mixed_pass_warn_fail(self):
        """Mix of pass, warn, and fail returns exit code 1."""
        report = _make_report(
            total=3, passed=1, warned=1, failed=1,
            skill_reports=[
                _make_skill_report("weather", [_make_check_result(status="pass")]),
                _make_skill_report("github", [_make_check_result(status="warn")]),
                _make_skill_report("broken", [_make_check_result(status="fail")]),
            ],
        )
        assert determine_exit_code(report) == 1

    def test_all_fail(self):
        """All skills failing returns exit code 1."""
        report = _make_report(
            total=2, passed=0, warned=0, failed=2,
            skill_reports=[
                _make_skill_report("a", [_make_check_result(status="fail")]),
                _make_skill_report("b", [_make_check_result(status="fail")]),
            ],
        )
        assert determine_exit_code(report) == 1

    def test_fail_overrides_warn(self):
        """Even with many warnings, a single failure triggers exit code 1."""
        report = _make_report(
            total=5, passed=0, warned=4, failed=1,
            skill_reports=[
                _make_skill_report("w1", [_make_check_result(status="warn")]),
                _make_skill_report("w2", [_make_check_result(status="warn")]),
                _make_skill_report("w3", [_make_check_result(status="warn")]),
                _make_skill_report("w4", [_make_check_result(status="warn")]),
                _make_skill_report("f1", [_make_check_result(status="fail")]),
            ],
        )
        assert determine_exit_code(report) == 1


# ===========================================================================
# Scenario 4: Parameter/usage error → exit code 2
# ===========================================================================

class TestUsageError:
    """Parameter/usage errors → exit code 2."""

    def test_raise_usage_error_exits_with_code_2(self):
        """raise_usage_error() raises SystemExit with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            raise_usage_error("Invalid target path: /nonexistent")
        assert exc_info.value.code == EXIT_USAGE_ERROR
        assert exc_info.value.code == 2

    def test_exit_usage_error_constant(self):
        """EXIT_USAGE_ERROR constant equals 2."""
        assert EXIT_USAGE_ERROR == 2


# ===========================================================================
# Alternative interface: determine_exit_code_from_skills()
# ===========================================================================

class TestDetermineExitCodeFromSkills:
    """Tests for the alternative list[SkillReport] interface."""

    def test_all_pass_returns_0(self):
        """All skills passing returns exit code 0."""
        skills = [
            _make_skill_report("a", [_make_check_result(status="pass")]),
            _make_skill_report("b", [_make_check_result(status="pass")]),
        ]
        assert determine_exit_code_from_skills(skills) == 0

    def test_warn_no_fail_returns_0(self):
        """Warnings without failures returns exit code 0."""
        skills = [
            _make_skill_report("a", [_make_check_result(status="warn")]),
            _make_skill_report("b", [_make_check_result(status="pass")]),
        ]
        assert determine_exit_code_from_skills(skills) == 0

    def test_has_fail_returns_1(self):
        """Any failure returns exit code 1."""
        skills = [
            _make_skill_report("a", [_make_check_result(status="pass")]),
            _make_skill_report("b", [_make_check_result(status="fail")]),
        ]
        assert determine_exit_code_from_skills(skills) == 1

    def test_empty_list_returns_0(self):
        """Empty skill list returns exit code 0."""
        assert determine_exit_code_from_skills([]) == 0

    def test_multiple_checks_per_skill(self):
        """Checks multiple check_results per skill for any failure."""
        skills = [
            _make_skill_report("a", [
                _make_check_result(status="pass"),
                _make_check_result(status="warn"),
                _make_check_result(status="pass"),
            ]),
        ]
        assert determine_exit_code_from_skills(skills) == 0

    def test_fail_in_second_check(self):
        """Failure in any check_result (not just first) triggers exit 1."""
        skills = [
            _make_skill_report("a", [
                _make_check_result(status="pass"),
                _make_check_result(status="fail"),
            ]),
        ]
        assert determine_exit_code_from_skills(skills) == 1


# ===========================================================================
# exit_with_code() integration
# ===========================================================================

class TestExitWithCode:
    """Tests for exit_with_code() convenience function."""

    def test_exit_with_code_success(self):
        """exit_with_code() calls sys.exit(0) when no failures."""
        report = _make_report(total=1, passed=1, warned=0, failed=0)
        with pytest.raises(SystemExit) as exc_info:
            exit_with_code(report)
        assert exc_info.value.code == 0

    def test_exit_with_code_failure(self):
        """exit_with_code() calls sys.exit(1) when failures present."""
        report = _make_report(total=1, passed=0, warned=0, failed=1)
        with pytest.raises(SystemExit) as exc_info:
            exit_with_code(report)
        assert exc_info.value.code == 1

    def test_exit_with_code_warn_success(self):
        """exit_with_code() calls sys.exit(0) when only warnings."""
        report = _make_report(total=1, passed=0, warned=1, failed=0)
        with pytest.raises(SystemExit) as exc_info:
            exit_with_code(report)
        assert exc_info.value.code == 0


# ===========================================================================
# Constants and module-level checks
# ===========================================================================

class TestConstants:
    """Verify exit code constants match expected values."""

    def test_exit_success_is_zero(self):
        assert EXIT_SUCCESS == 0

    def test_exit_failure_is_one(self):
        assert EXIT_FAILURE == 1

    def test_exit_usage_error_is_two(self):
        assert EXIT_USAGE_ERROR == 2

    def test_all_constants_are_distinct(self):
        codes = {EXIT_SUCCESS, EXIT_FAILURE, EXIT_USAGE_ERROR}
        assert len(codes) == 3
