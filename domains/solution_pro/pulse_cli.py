"""Solution Pulse CLI — Solution Pro 脉冲调度的 exec 入口（2026-07-25）。

用法:
    python3 -m domains.solution_pro.pulse_cli pulse --session-id "X"
        运行一次脉冲扫描，动作落盘 _solution_pulse_actions.json 并打印到 stdout。
        exit code: 0=active/idle, 2=locked, 3=completed, 4=failed

    python3 -m domains.solution_pro.pulse_cli confirm --session-id "X" --results '<json>'
        spawn 回执（两阶段 dispatch / 失败回滚）。
        --results: JSON 数组字符串 '[{"module":"planning","label":"...","ok":true,"error":null}]'
        或用 --results-file <path> 从文件读取。

    python3 -m domains.solution_pro.pulse_cli check --session-id "X"
        轻量检查（cron 点火前 / 人工检查用）：还有活 → exit 0；已终态 → exit 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_pulse(session_id: str):
    from domains.solution_pro.pulse import SolutionPulse

    return SolutionPulse(session_id)


def cmd_pulse(args) -> int:
    sp = _load_pulse(args.session_id)
    report = sp.pulse()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    status = report.get("status")
    if status == "locked":
        return 2
    if status == "completed":
        return 3
    if status == "failed":
        return 4
    return 0


def cmd_confirm(args) -> int:
    if args.results_file:
        results = json.loads(Path(args.results_file).read_text())
    elif args.results:
        results = json.loads(args.results)
    else:
        print("ERROR: --results or --results-file required", file=sys.stderr)
        return 1
    if not isinstance(results, list):
        print("ERROR: results must be a JSON array", file=sys.stderr)
        return 1

    # 契约笼子：回执必须通过 SpawnConfirmation 验证（逐条验证，
    # 单条格式错误不拖垮整批 — all-or-nothing 会让全部 spawn 变孤儿）
    from domains.solution_pro.contracts.pulse_report import SpawnConfirmation

    validated = []
    validation_errors = []
    for i, r in enumerate(results):
        try:
            validated.append(SpawnConfirmation(**r).model_dump(mode="json"))
        except Exception as e:
            validation_errors.append({"index": i, "item": r, "error": str(e)})

    sp = _load_pulse(args.session_id)
    out = sp.confirm_dispatches(validated)
    if validation_errors:
        out["validation_errors"] = validation_errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args) -> int:
    from domains.solution_pro.pulse import (
        PULSE_COMPLETED_FILENAME,
        PULSE_FAILED_FILENAME,
        SolutionPulse,
    )

    sp = SolutionPulse(args.session_id)
    if (sp.session_dir / PULSE_COMPLETED_FILENAME).exists():
        print(f"completed: {args.session_id} pipeline 已终态（.completed 存在）")
        return 1
    if (sp.session_dir / PULSE_FAILED_FILENAME).exists():
        print(f"failed: {args.session_id} pipeline 已终败（.failed 存在）")
        return 1
    if not sp.session_dir.exists():
        print(f"no_session: {args.session_id} 无 blackboard 目录")
        return 1
    print(f"work_remains: {args.session_id} 有待调度工作")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="solution_pulse_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("pulse", "confirm", "check"):
        p = sub.add_parser(name)
        p.add_argument("--session-id", required=True)
        if name == "confirm":
            p.add_argument("--results", default=None)
            p.add_argument("--results-file", default=None)

    args = parser.parse_args()
    if args.command == "pulse":
        return cmd_pulse(args)
    if args.command == "confirm":
        return cmd_confirm(args)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
