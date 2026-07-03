#!/usr/bin/env python3
# ---
# id: ship_pro/e2e_report
# version: "3.0.0"
# component: ship_pro
# updated: "2026-06-19"
# status: active
# ---
"""
Ship Pro V3 — E2E Test Report Command

Prints human-readable test reports.

Usage:
    python3 e2e_report.py <output_dir>
"""

import json
import sys
from pathlib import Path
from typing import Any

from e2e_common import AGENTS


# ---------------------------------------------------------------------------
# Report Command
# ---------------------------------------------------------------------------

def format_report(results: dict) -> str:
    """Format validation results into human-readable report."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("  Ship Pro V3 — E2E Integration Test Report")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Run ID: {results.get('run_id', 'N/A')}")
    lines.append(f"  Input Format: {results.get('input_format', 'N/A')}")
    lines.append(f"  Output Dir: {results.get('output_dir', 'N/A')}")
    lines.append("")

    summary = results.get("summary", {})
    status_icon = "✅" if summary.get("all_passed") else "❌"
    lines.append(f"  Overall: {status_icon} {summary.get('passed_agents', 0)}/{summary.get('total_agents', 0)} agents passed")
    lines.append("")
    lines.append("-" * 70)

    agent_results = results.get("agent_results", {})
    for agent in AGENTS:
        ar = agent_results.get(agent, {})
        passed = ar.get("passed", False)
        icon = "✅" if passed else "❌"
        lines.append(f"  {icon} {agent.upper()}")

        for check in ar.get("checks", []):
            check_icon = "✅" if check.get("passed") else "❌"
            lines.append(f"     {check_icon} {check['name']}: {check['detail']}")

        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def print_report(output_dir: Path) -> None:
    """Print validation report for a test case."""
    report_path = output_dir / "validation_report.json"
    if not report_path.exists():
        print(f"❌ Report not found: {report_path}")
        print("   Run 'validate' first to generate the report.")
        return

    with open(report_path) as f:
        results = json.load(f)

    print(format_report(results))


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    print_report(output_dir)


if __name__ == "__main__":
    main()
