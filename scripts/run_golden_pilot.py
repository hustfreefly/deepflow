#!/usr/bin/env python3
"""Evaluate recorded golden pilot samples (manual/nightly entry point).

This script never calls an LLM. Sample collection is explicit; it enforces a
minimum pass count across recorded <scenario>.json / <scenario>.sampleN.json
files. Scenarios without any recorded samples are reported as NO_SAMPLES and
do not fail the run (e.g. platform-level routing checks).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.golden.scenarios import evaluate_result, load_scenarios  # noqa: E402


def sample_files(results_dir: Path, scenario_id: str) -> list[Path]:
    """Return the exact result plus numbered samples, without duplicates."""
    files: list[Path] = []
    exact = results_dir / f"{scenario_id}.json"
    if exact.exists():
        files.append(exact)
    files.extend(sorted(results_dir.glob(f"{scenario_id}.sample*.json")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate recorded golden behavior samples."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=ROOT / "artifacts" / "golden_results",
        help="directory containing <scenario-id>.json samples",
    )
    parser.add_argument(
        "--samples", type=int, default=3, help="expected samples per scenario"
    )
    parser.add_argument(
        "--min-pass", type=int, default=2, help="minimum passing samples"
    )
    parser.add_argument("--scenario", help="limit to one scenario id")
    args = parser.parse_args(argv)

    data = load_scenarios()
    selected = [
        scenario
        for scenario in data.scenarios
        if args.scenario is None or scenario.id == args.scenario
    ]
    if not selected:
        print(f"unknown scenario: {args.scenario}")
        return 2

    rows: list[tuple[str, int, int, str]] = []
    hard_failures: list[str] = []
    for scenario in selected:
        files = sample_files(args.results_dir, scenario.id)
        if not files:
            rows.append((scenario.id, 0, 0, "NO_SAMPLES"))
            continue

        passed = 0
        details: list[str] = []
        for path in files:
            try:
                result = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                details.append(f"{path.name}: invalid JSON ({exc})")
                continue
            errors = evaluate_result(scenario, result)
            if errors:
                details.append(f"{path.name}: " + "; ".join(errors))
            else:
                passed += 1

        status = "PASS" if passed >= args.min_pass else "FAIL"
        rows.append((scenario.id, len(files), passed, status))
        if status == "FAIL":
            hard_failures.append(scenario.id)
            for detail in details:
                print(f"  - {detail}")

    print(f"{'scenario':28} {'samples':>8} {'pass':>5}  status")
    for scenario_id, count, passed, status in rows:
        print(f"{scenario_id:28} {count:>8} {passed:>5}  {status}")

    sampled = [row for row in rows if row[1] > 0]
    print(f"sampled scenarios: {len(sampled)}; failures: {len(hard_failures)}")
    if hard_failures:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
