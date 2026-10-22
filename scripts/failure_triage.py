#!/usr/bin/env python3
"""Classify failing tests by re-running each one in isolation (repair Phase 0).

Contract: cage/active/repair_program_v1.0.yaml
Never modifies tests. Output: isolation-pass / isolation-fail / error.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAIL_RE = re.compile(r"^FAILED\s+(\S+::\S+?)(?:\s+-.*)?$")


def extract(log: Path) -> list[str]:
    seen = set()
    for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = FAIL_RE.match(line.strip())
        if match:
            seen.add(match.group(1))
    return sorted(seen)


def run_one(test_id: str, timeout: int) -> tuple[str, str]:
    command = [sys.executable, "-m", "pytest", test_id, "-q", "--tb=no",
               "-p", "no:cacheprovider"]
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "error", f"timeout>{timeout}s"
    if proc.returncode == 0:
        return "pass", ""
    if proc.returncode == 1:
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        return "fail", tail[-200:]
    return "error", f"exit={proc.returncode} " + proc.stderr.strip()[-200:]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify failing tests")
    parser.add_argument("--log", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args(argv)

    ids = extract(Path(args.log))
    if args.limit:
        ids = ids[: args.limit]

    results = []
    counts = {"isolation-pass": 0, "isolation-fail": 0, "error": 0}
    for index, test_id in enumerate(ids, 1):
        status, detail = run_one(test_id, args.timeout)
        bucket = {"pass": "isolation-pass", "fail": "isolation-fail"}.get(status, "error")
        counts[bucket] += 1
        results.append({"test": test_id, "bucket": bucket, "detail": detail})
        if not args.as_json:
            print(f"[{index}/{len(ids)}] {bucket:15s} {test_id}", file=sys.stderr)

    payload = {"total": len(ids), "counts": counts, "results": results}
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())