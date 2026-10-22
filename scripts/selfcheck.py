#!/usr/bin/env python3
"""One-command environment self-check (P1 weapon).

Contract: cage/active/dev_ops_v1.0.yaml
Read-only. PASS/WARN exit 0, FAIL exit 1.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_HOME = Path(
    os.environ.get(
        "DEEPFLOW_AGENT_HOME",
        "/Users/allen/.openclaw/workspace/agent-workspaces/deepflow-dev",
    )
)


def check(name, fn):
    try:
        status, detail = fn()
    except Exception as exc:
        status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
    return {"name": name, "status": status, "detail": str(detail)}


def python_check():
    version = sys.version_info
    return (
        "PASS" if version >= (3, 11) else "FAIL",
        f"{version.major}.{version.minor}.{version.micro}",
    )


def pytest_check():
    import pytest

    return "PASS", pytest.__version__


def contract_check():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/contracts",
            "-q",
            "--ignore=tests/contracts/test_dev_ops.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    line = (
        result.stdout.strip().splitlines()[-1]
        if result.stdout.strip()
        else result.stderr[-200:]
    )
    return ("PASS" if result.returncode == 0 else "FAIL", line)


def git_check():
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    dirty = bool(result.stdout.strip())
    return ("WARN" if dirty else "PASS", "dirty" if dirty else "clean")


def skills_check():
    skills = AGENT_HOME / "skills"
    if not skills.exists():
        return "WARN", f"missing {skills}"
    entries = list(skills.iterdir())
    broken = [p.name for p in entries if not p.exists() or not os.access(p, os.R_OK)]
    return ("FAIL" if broken else "PASS", f"{len(entries)} links, broken={broken}")


def scripts_check():
    required = [
        "impact.py",
        "metrics.py",
        "worktree.sh",
        "spawn_guard.py",
        "selfcheck.py",
        "validate.py",
    ]
    missing = [name for name in required if not (ROOT / "scripts" / name).exists()]
    return ("FAIL" if missing else "PASS", f"missing={missing}")


def metrics_check():
    path = AGENT_HOME / "projects" / "_metrics.jsonl"
    return ("PASS" if path.exists() else "WARN", str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description="DeepFlow self-check")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    checks = [
        check("python", python_check),
        check("pytest", pytest_check),
        check("contract_gate", contract_check),
        check("git", git_check),
        check("skills", skills_check),
        check("scripts", scripts_check),
        check("metrics", metrics_check),
    ]
    failed = any(c["status"] == "FAIL" for c in checks)
    warned = any(c["status"] == "WARN" for c in checks)
    status = "FAIL" if failed else ("WARN" if warned else "PASS")
    payload = {"status": status, "checks": checks}

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            print(f"[{item['status']}] {item['name']}: {item['detail']}")
        print(f"RESULT: {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
