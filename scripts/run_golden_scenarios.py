#!/usr/bin/env python3
"""Validate or execute golden behavior scenarios.

Default is a CI-safe structural check (schema + coverage). Execution reads
recorded JSON results and never calls an LLM from CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.golden.scenarios import (  # noqa: E402
    CONTRACT_PATH,
    EXPECTED_SCENARIO_COUNT,
    evaluate_result,
    load_scenarios,
    validate_coverage,
)


def _print_coverage(data) -> list[str]:
    counts = {}
    for scenario in data.scenarios:
        counts[scenario.domain] = counts.get(scenario.domain, 0) + 1
    summary = ", ".join(
        f"{domain}={counts.get(domain, 0)}" for domain in sorted(counts)
    )
    p0 = sum(1 for scenario in data.scenarios if scenario.severity == "P0")
    print(f"contract: {CONTRACT_PATH}")
    print(f"scenarios: {len(data.scenarios)}/{EXPECTED_SCENARIO_COUNT}")
    print(f"coverage: {summary}")
    print(f"P0: {p0}")
    return validate_coverage(data)


def _execute(data, results_dir: Path, scenario_id: str | None) -> int:
    selected = [s for s in data.scenarios if scenario_id is None or s.id == scenario_id]
    if not selected:
        print(f"unknown scenario: {scenario_id}")
        return 2

    failures: list[str] = []
    for scenario in selected:
        path = results_dir / f"{scenario.id}.json"
        if not path.exists():
            message = f"{scenario.id}: missing result file {path}"
            print(f"[FAIL] {message}")
            failures.append(message)
            continue
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            message = f"{scenario.id}: invalid JSON in {path}: {exc}"
            print(f"[FAIL] {message}")
            failures.append(message)
            continue
        errors = evaluate_result(scenario, result)
        print(f"[{'PASS' if not errors else 'FAIL'}] {scenario.id}")
        for error in errors:
            print(f"  - {error}")
        failures.extend(errors)

    print(f"executed: {len(selected)}; failures: {len(failures)}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate/execute the golden behavior scenario contract."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--validate", action="store_true", help="schema + coverage (default)"
    )
    mode.add_argument("--list", action="store_true", help="list scenarios")
    mode.add_argument(
        "--plan", action="store_true", help="print execution plan as JSON"
    )
    mode.add_argument(
        "--execute", action="store_true", help="evaluate recorded results"
    )
    parser.add_argument(
        "--results-dir", type=Path, help="directory of <scenario-id>.json"
    )
    parser.add_argument("--scenario", help="limit execution to one scenario id")
    args = parser.parse_args(argv)

    data = load_scenarios()

    if args.list:
        for scenario in data.scenarios:
            print(
                f"{scenario.id}\t{scenario.domain}\t{scenario.severity}\t"
                f"{scenario.title}"
            )
        return 0

    if args.plan:
        for scenario in data.scenarios:
            print(
                json.dumps(
                    {
                        "id": scenario.id,
                        "domain": scenario.domain,
                        "runner": scenario.runner,
                        "input": scenario.input,
                        "expect": scenario.expect.model_dump(exclude_none=True),
                        "rubric": scenario.rubric,
                    },
                    ensure_ascii=False,
                )
            )
        return 0

    if args.execute:
        if args.results_dir is None:
            parser.error("--execute requires --results-dir")
        return _execute(data, args.results_dir, args.scenario)

    errors = _print_coverage(data)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        print("RESULT: FAIL")
        return 1

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
