"""Terminal summary printer for skill health check reports.

Outputs a three-section terminal summary:
  1. Scan summary line — target path, skill count, generation timestamp
  2. Per-skill status lines — ✅/⚠️/❌ + skill name + checker result summary
     (failed skills in red, warning skills in yellow)
  3. Bottom summary line — overall status + exit code hint

Uses the ``rich`` library for coloured output when available.  Falls back
gracefully to raw ANSI escape codes when ``rich`` is not installed, and
automatically disables all escape sequences in non-TTY environments
(pipes, redirects, CI log files).

Exit-code decision logic (CI/CD-friendly):
  - ``determine_exit_code(results)`` — pure function, no side effects
  - ``TerminalSummaryPrinter.print_and_exit(report)`` — print + sys.exit
"""

from __future__ import annotations

import sys
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Lazy import of ReportModel — avoids circular imports at module level.
# The printer accepts any object with the expected attributes (duck typing),
# so the import is only used for type-check annotations.
# ---------------------------------------------------------------------------

try:
    from .report import ReportModel
except ImportError:  # pragma: no cover — package not installed
    ReportModel = Any  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Status → display constants
# ---------------------------------------------------------------------------

_STATUS_ICONS: dict[str, str] = {
    "passed": "✅",
    "warning": "⚠️",
    "failed": "❌",
}

# ANSI SGR codes for foreground colours
_ANSI_RESET = "\033[0m"
_ANSI_BOLD = "\033[1m"
_ANSI_COLORS: dict[str, str] = {
    "passed": "\033[32m",   # green
    "warning": "\033[33m",  # yellow
    "failed": "\033[31m",   # red
}

# Rich style names matching the ANSI palette
_RICH_STYLES: dict[str, str] = {
    "passed": "green",
    "warning": "yellow",
    "failed": "bold red",
}

# ---------------------------------------------------------------------------
# Exit code constants (follow POSIX / argparse conventions)
# ---------------------------------------------------------------------------

EXIT_SUCCESS = 0        # All passed, or warnings only (no failures)
EXIT_FAILURE = 1        # One or more checks failed
EXIT_USAGE_ERROR = 2    # Parameter / input error (invalid data, bad args)


# ---------------------------------------------------------------------------
# Internal adapter — wraps a status string for determine_exit_code()
# ---------------------------------------------------------------------------

class _StatusHolder:
    """Minimal object with a ``status`` attribute, used by ``get_exit_code``
    to bridge between the report model and :func:`determine_exit_code`."""

    __slots__ = ("status",)

    def __init__(self, status: str) -> None:
        self.status = status


# ---------------------------------------------------------------------------
# Exit-code decision logic (pure function — no I/O, no side effects)
# ---------------------------------------------------------------------------

def determine_exit_code(results: list[Any] | None) -> int:
    """Determine the CLI exit code from a list of skill result objects.

    Each element in *results* must expose a ``status`` attribute whose value
    is one of ``"passed"``, ``"warning"``, or ``"failed"`` (case-insensitive
    strings are accepted and normalised internally).

    Exit-code mapping
    -----------------
    ==== ======================================================
    Code Condition
    ==== ======================================================
    0    All checks passed **or** warnings present but no fail
    1    One or more checks have status ``"failed"``
    2    Parameter / input error (see below)
    ==== ======================================================

    Parameter-error conditions (→ exit code 2)
    -------------------------------------------
    * *results* is ``None``
    * *results* is not a list or tuple
    * Any element lacks a ``status`` attribute
    * Any element has an unrecognised status value (not in
      ``{"passed", "warning", "failed", "pass", "warn", "fail"}``)

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> determine_exit_code([SimpleNamespace(status="passed")])
    0
    >>> determine_exit_code([SimpleNamespace(status="warning")])
    0
    >>> determine_exit_code([SimpleNamespace(status="failed")])
    1
    >>> determine_exit_code(None)
    2
    """
    # --- Parameter validation (→ exit code 2) ----------------------------
    if results is None:
        return EXIT_USAGE_ERROR

    if not isinstance(results, (list, tuple)):
        return EXIT_USAGE_ERROR

    # Normalise accepted status values to canonical form
    _STATUS_NORMALISE: dict[str, str] = {
        "passed": "passed",
        "pass": "passed",
        "warning": "warning",
        "warn": "warning",
        "failed": "failed",
        "fail": "failed",
    }

    has_failure = False

    for item in results:
        # Each item must have a .status attribute
        status_raw = getattr(item, "status", None)
        if status_raw is None:
            return EXIT_USAGE_ERROR

        # Normalise to lowercase string for comparison
        if not isinstance(status_raw, str):
            return EXIT_USAGE_ERROR

        normalised = _STATUS_NORMALISE.get(status_raw.lower().strip())
        if normalised is None:
            # Unrecognised status value → parameter error
            return EXIT_USAGE_ERROR

        if normalised == "failed":
            has_failure = True

    # --- Decision logic --------------------------------------------------
    if has_failure:
        return EXIT_FAILURE

    # All passed or warnings only (no failures)
    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill_aggregate_status(checks: list[Any]) -> Literal["passed", "warning", "failed"]:
    """Derive the worst status from a list of check results.

    Priority: failed > warning > passed.  An empty check list counts as passed.
    """
    statuses = {c.status for c in checks}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "passed"


def _checker_summary(checks: list[Any]) -> str:
    """Build a one-line summary of checker results for a skill."""
    if not checks:
        return "all checks passed"
    parts: list[str] = []
    for c in checks:
        parts.append(f"{c.check_id}: {c.message}")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# TerminalSummaryPrinter
# ---------------------------------------------------------------------------

class TerminalSummaryPrinter:
    """Print a three-section coloured terminal summary of a *ReportModel*.

    Parameters
    ----------
    use_colors:
        Enable coloured output.  Even when ``True``, colours are suppressed
        automatically when *stdout* is not a TTY (pipe / redirect / CI).
        Set to ``False`` to force plain-text output unconditionally.
    """

    def __init__(self, use_colors: bool = True) -> None:
        self._use_colors = use_colors

        # Probe for rich availability once at construction time.
        self._has_rich: bool
        try:
            import rich.console  # noqa: F401
            self._has_rich = True
        except ImportError:
            self._has_rich = False

    # -- public API ---------------------------------------------------------

    def print(self, report: ReportModel, file: Any = None) -> None:  # noqa: A003
        """Write the three-section summary to *file* (default ``sys.stdout``).

        Sections
        --------
        1. **Scan summary** — target path, skill count, generation time.
        2. **Per-skill status** — one line per skill with ✅/⚠️/❌ icon,
           skill name, and checker result summary.  Failed skills are
           rendered in red, warnings in yellow (when colours are enabled).
        3. **Bottom summary** — aggregate counts + exit-code hint.
        """
        out = file if file is not None else sys.stdout

        if self._colors_active():
            if self._has_rich:
                self._render_rich(report, out)
            else:
                self._render_ansi(report, out)
        else:
            self._render_plain(report, out)

    def get_exit_code(self, report: ReportModel) -> int:
        """Compute the exit code for *report* without printing or exiting.

        Adapts the report's skill list into simple status objects and
        delegates to :func:`determine_exit_code`.  This is the recommended
        integration point for callers that want to handle the exit code
        themselves (e.g. testing, logging).
        """
        # Adapt each skill report to an object with a .status attribute
        # by computing the aggregate status from its checks.
        adapted = [
            _StatusHolder(_skill_aggregate_status(skill.checks))
            for skill in report.skills
        ]
        return determine_exit_code(adapted)

    def print_and_exit(
        self,
        report: ReportModel,
        file: Any = None,
        *,
        dry_run: bool = False,
    ) -> int:
        """Print the summary and return the appropriate exit code.

        Parameters
        ----------
        report:
            The report model to render.
        file:
            Output stream (default ``sys.stdout``).
        dry_run:
            When ``True``, compute the exit code *without* calling
            ``sys.exit()``.  Useful for testing and programmatic use.
            When ``False`` (default), calls ``sys.exit(code)`` after
            printing.

        Returns
        -------
        int
            The exit code that was (or would be) passed to ``sys.exit()``.
        """
        self.print(report, file=file)
        code = self.get_exit_code(report)

        if dry_run:
            return code

        sys.exit(code)

    # -- colour gating ------------------------------------------------------

    def _colors_active(self) -> bool:
        """Return ``True`` only when the caller wants colours *and* the
        current stdout is an interactive terminal."""
        if not self._use_colors:
            return False
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    # -- rich rendering -----------------------------------------------------

    def _render_rich(self, report: ReportModel, file: Any) -> None:
        """Render via the *rich* library (Console + inline markup)."""
        from rich.console import Console

        console = Console(file=file, force_terminal=True)
        meta = report.metadata
        summary = report.summary

        # Section 1 — scan summary
        console.print(
            f"[bold]Scan:[/bold] {meta.scan_root} | "
            f"{summary.total_skills} skills | "
            f"generated {meta.generated_at}"
        )
        console.print()

        # Section 2 — per-skill status lines
        for skill in report.skills:
            status = _skill_aggregate_status(skill.checks)
            icon = _STATUS_ICONS[status]
            style = _RICH_STYLES[status]
            detail = _checker_summary(skill.checks)
            console.print(f"  {icon} [{style}]{skill.skill_name}[/{style}] {detail}")

        console.print()

        # Section 3 — bottom summary
        overall_icon, overall_style, exit_hint = self._overall_line(summary)
        console.print(
            f"{overall_icon} [{overall_style}]"
            f"{summary.passed} passed, {summary.failed} failed, "
            f"{summary.warnings} warnings[/{overall_style}] "
            f"({exit_hint})"
        )

    # -- ANSI fallback rendering --------------------------------------------

    def _render_ansi(self, report: ReportModel, file: Any) -> None:
        """Render using raw ANSI escape codes (no *rich* dependency)."""
        meta = report.metadata
        summary = report.summary
        w = file.write

        # Section 1 — scan summary
        w(
            f"{_ANSI_BOLD}Scan:{_ANSI_RESET} {meta.scan_root} | "
            f"{summary.total_skills} skills | "
            f"generated {meta.generated_at}\n"
        )
        w("\n")

        # Section 2 — per-skill status lines
        for skill in report.skills:
            status = _skill_aggregate_status(skill.checks)
            icon = _STATUS_ICONS[status]
            color = _ANSI_COLORS[status]
            detail = _checker_summary(skill.checks)
            w(
                f"  {icon} {color}{_ANSI_BOLD}"
                f"{skill.skill_name}{_ANSI_RESET} {detail}\n"
            )

        w("\n")

        # Section 3 — bottom summary
        overall_icon, overall_style, exit_hint = self._overall_line(summary)
        color = _ANSI_COLORS.get(overall_style.replace("bold ", ""), "\033[32m")
        w(
            f"{overall_icon} {color}{_ANSI_BOLD}"
            f"{summary.passed} passed, {summary.failed} failed, "
            f"{summary.warnings} warnings{_ANSI_RESET} "
            f"({exit_hint})\n"
        )

    # -- plain-text rendering (non-TTY / use_colors=False) ------------------

    def _render_plain(self, report: ReportModel, file: Any) -> None:
        """Render without any escape sequences or markup."""
        meta = report.metadata
        summary = report.summary
        w = file.write

        # Section 1 — scan summary
        w(
            f"Scan: {meta.scan_root} | "
            f"{summary.total_skills} skills | "
            f"generated {meta.generated_at}\n"
        )
        w("\n")

        # Section 2 — per-skill status lines
        for skill in report.skills:
            status = _skill_aggregate_status(skill.checks)
            icon = _STATUS_ICONS[status]
            detail = _checker_summary(skill.checks)
            w(f"  {icon} {skill.skill_name} {detail}\n")

        w("\n")

        # Section 3 — bottom summary
        overall_icon, _, exit_hint = self._overall_line(summary)
        w(
            f"{overall_icon} "
            f"{summary.passed} passed, {summary.failed} failed, "
            f"{summary.warnings} warnings "
            f"({exit_hint})\n"
        )

    # -- shared helpers -----------------------------------------------------

    @staticmethod
    def _overall_line(summary: Any) -> tuple[str, str, str]:
        """Return ``(icon, rich_style, exit_hint)`` for the bottom summary."""
        if summary.failed > 0:
            return "❌", "failed", "exit code 1"
        if summary.warnings > 0:
            return "⚠️", "warning", "exit code 0"
        return "✅", "passed", "exit code 0"
