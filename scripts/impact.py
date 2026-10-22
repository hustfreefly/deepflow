#!/usr/bin/env python3
"""Map changed files to the smallest sufficient test set (P0-1).

Contract: cage/active/dev_toolchain_v1.0.yaml
Unknown paths deliberately fall back to the full suite: never return an empty set.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git_changed(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"git diff failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def select(paths: list[str]) -> tuple[list[str], bool]:
    targets: set[str] = set()
    unknown = False
    for raw in paths:
        parts = Path(raw).parts
        if not parts:
            unknown = True
            continue
        head = parts[0]
        if head == "domains" and len(parts) >= 2:
            targets.add(f"domains/{parts[1]}/tests")
        elif head == "tests":
            targets.add("tests")
        elif head == "core":
            targets.add("tests/contracts")
            targets.add("tests")
        elif head in {"cage", "contracts", "scripts", "prompts"}:
            targets.add("tests/contracts")
            targets.add("tests")
        else:
            unknown = True
    if unknown or not targets:
        return ["."], True
    return sorted(targets), False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map changed files to tests")
    parser.add_argument("--changed", nargs="+", help="changed file paths")
    parser.add_argument("--base", help="derive changed files from git diff BASE")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if not args.changed and not args.base:
        parser.error("one of --changed or --base is required")

    changed = list(args.changed or [])
    if args.base:
        changed.extend(git_changed(args.base))
    changed = sorted(set(changed))
    targets, fallback = select(changed)

    payload = {
        "changed": changed,
        "targets": targets,
        "fallback_full_suite": fallback,
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n".join(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
