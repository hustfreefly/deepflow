#!/usr/bin/env python3
# ---
# id: ship_pro/e2e_test
# version: "3.0.0"
# component: ship_pro
# updated: "2026-06-19"
# status: active
# ---
"""
Ship Pro V3 — End-to-End Integration Test

Prepares test environments for the 5-Agent pipeline and validates outputs.

Usage:
    python3 e2e_test.py prepare <final_result.json> <output_dir>
        → Prepare environment, generate run_plan.json

    python3 e2e_test.py validate <output_dir>
        → Validate all Agent outputs, generate report

    python3 e2e_test.py prepare-all <cases_dir>
        → Prepare all 3 standard test cases

    python3 e2e_test.py report <output_dir>
        → Print human-readable test report
"""

import sys
from pathlib import Path

from e2e_prepare import prepare, prepare_all_cases
from e2e_validate import validate
from e2e_report import format_report, print_report


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "prepare":
        if len(sys.argv) < 4:
            print("用法: python3 e2e_test.py prepare <final_result.json> <output_dir>")
            sys.exit(1)
        input_path = Path(sys.argv[2])
        output_dir = Path(sys.argv[3])
        prepare(input_path, output_dir)

    elif command == "validate":
        if len(sys.argv) < 3:
            print("用法: python3 e2e_test.py validate <output_dir>")
            sys.exit(1)
        output_dir = Path(sys.argv[2])
        results = validate(output_dir)
        print(format_report(results))

    elif command == "prepare-all":
        base_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("test_runs")
        prepare_all_cases(base_dir)

    elif command == "report":
        if len(sys.argv) < 3:
            print("用法: python3 e2e_test.py report <output_dir>")
            sys.exit(1)
        output_dir = Path(sys.argv[2])
        print_report(output_dir)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
