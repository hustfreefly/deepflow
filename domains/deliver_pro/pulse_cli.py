"""Deliver Pro Pulse CLI — 脉冲调度的 exec 入口（Pulse V1, 2026-07-24）。

用法:
    python3 -m domains.deliver_pro.pulse_cli pulse --project "X"
        运行一次脉冲扫描，动作落盘 _pulse_actions.json 并打印到 stdout。
        exit code: 0=active/idle, 2=locked, 3=completed

    python3 -m domains.deliver_pro.pulse_cli confirm --project "X" --results '<json>'
        spawn 回执（A4 两阶段 dispatch / P1-1 回滚）。
        --results: JSON 数组字符串 '[{"wp_id":"...","label":"...","ok":true,"error":null}]'
        或用 --results-file <path> 从文件读取。

    python3 -m domains.deliver_pro.pulse_cli check --project "X"
        轻量检查（cron 点火前 / 人工检查用）：还有活 → exit 0；已完成或无 ship package → exit 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_orchestrator(project: str):
    from domains.deliver_pro.orchestrator import DeliverOrchestrator

    return DeliverOrchestrator(project)


def cmd_pulse(args) -> int:
    orch = _load_orchestrator(args.project)
    report = orch.pulse()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    status = report.get("status")
    if status == "locked":
        return 2
    if status == "completed":
        return 3
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

    # 契约笼子：回执必须通过 SpawnConfirmation 验证（A#2/DryRun R1: 逐条验证，
    # 单条格式错误不拖垮整批 — all-or-nothing 会让全部 spawn 变孤儿）
    from domains.deliver_pro.contracts.pulse_report import SpawnConfirmation

    validated = []
    validation_errors = []
    for i, r in enumerate(results):
        try:
            validated.append(SpawnConfirmation(**r).model_dump(mode="json"))
        except Exception as e:
            validation_errors.append({"index": i, "item": r, "error": str(e)})

    orch = _load_orchestrator(args.project)
    out = orch.confirm_dispatches(validated)
    if validation_errors:
        out["validation_errors"] = validation_errors
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args) -> int:
    from domains.deliver_pro import BLACKBOARD_ROOT
    from domains.deliver_pro.orchestrator import PULSE_COMPLETED_FILENAME

    project_dir = BLACKBOARD_ROOT / args.project
    if (project_dir / PULSE_COMPLETED_FILENAME).exists():
        print(f"completed: {args.project} pipeline 已终态（.deliver_completed.json 存在）")
        return 1
    ship_candidates = [
        project_dir / "ship_pro" / "ship_track.json",
        project_dir / "ship_pro" / "ship_package.json",
        project_dir / "ship_pro" / "stages" / "ship_package.json",
    ]
    if not any(p.exists() for p in ship_candidates):
        print(f"no_ship_package: {args.project} 无 ship package，无法调度")
        return 1
    print(f"work_remains: {args.project} 有待调度工作")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="deliver_pulse_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("pulse", "confirm", "check"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
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
