#!/usr/bin/env python3
"""Pre-spawn guard (P1 weapon): enforce heterogeneous review and task size.

Contract: cage/active/dev_ops_v1.0.yaml
Does not call sessions_spawn; validates a JSON request only.
"""

import argparse
import json
from pathlib import Path

ALLOWED_AGENTS = {"deepflow", "expert", "redteam", "researcher", "worker"}
MAX_TASK_BYTES = 3072


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a spawn request")
    parser.add_argument("--request", required=True, help="path to request JSON")
    args = parser.parse_args(argv)

    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"ok": False, "violations": [f"invalid request: {exc}"]}))
        return 2

    agent = str(request.get("agent", "")).strip()
    model = str(request.get("model", "")).strip()
    executor = str(request.get("executor_model", "")).strip()
    task = str(request.get("task", ""))

    violations = []
    if agent not in ALLOWED_AGENTS:
        violations.append(f"agent not allowed: {agent!r}")
    if not model:
        violations.append("model is required")
    if agent == "redteam" and model and executor and model == executor:
        violations.append("redteam model must differ from executor_model")
    if len(task.encode("utf-8")) > MAX_TASK_BYTES:
        violations.append(f"task exceeds {MAX_TASK_BYTES} bytes")

    payload = {
        "ok": not violations,
        "agent": agent,
        "model": model,
        "violations": violations,
    }
    print(json.dumps(payload, ensure_ascii=False))

    if not violations:
        return 0
    if any("task exceeds" in item for item in violations):
        return 4
    if any("redteam model" in item for item in violations):
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
