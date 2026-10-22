#!/usr/bin/env python3
"""Task metrics ledger (P0-4).

Contract: cage/active/dev_toolchain_v1.0.yaml
One JSON object per line. Invalid input must not create or modify the file.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("task", "model", "duration", "passed", "failed", "commit")


def _positive_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise ValueError("duration must be >= 0")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise ValueError("count must be >= 0")
    return number


def record(args) -> int:
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task": str(args.task).strip(),
            "model": str(args.model).strip(),
            "duration_s": _positive_float(args.duration),
            "passed": _non_negative_int(args.passed),
            "failed": _non_negative_int(args.failed),
            "commit": str(args.commit).strip(),
            "note": (args.note or "").strip(),
        }
    except (TypeError, ValueError) as exc:
        print(f"invalid metrics entry: {exc}", file=sys.stderr)
        return 2
    if not entry["task"] or not entry["model"] or not entry["commit"]:
        print(
            "invalid metrics entry: task/model/commit must be non-empty",
            file=sys.stderr,
        )
        return 2

    path = Path(args.file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0


def summary(args) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"metrics file not found: {path}", file=sys.stderr)
        return 1
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    payload = {
        "count": len(entries),
        "passed": sum(int(e.get("passed", 0)) for e in entries),
        "failed": sum(int(e.get("failed", 0)) for e in entries),
        "duration_total": round(sum(float(e.get("duration_s", 0)) for e in entries), 3),
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"tasks={payload['count']} passed={payload['passed']} "
            f"failed={payload['failed']} duration={payload['duration_total']}s"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeepFlow task metrics")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--file", required=True)
    for name in REQUIRED:
        rec.add_argument(f"--{name}", required=True)
    rec.add_argument("--note", default="")
    rec.set_defaults(func=record)

    summ = sub.add_parser("summary")
    summ.add_argument("--file", required=True)
    summ.add_argument("--json", action="store_true", dest="as_json")
    summ.set_defaults(func=summary)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
