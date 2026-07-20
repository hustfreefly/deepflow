#!/usr/bin/env python3
"""E2E Pipeline Stage Validator — 契约笼子 CLI

用法:
    # 验证当前阶段是否完成，获取下一阶段动作
    python3 scripts/e2e_pipeline_check.py --project "项目名" --completed solution_pro

    # 检查完整管线状态
    python3 scripts/e2e_pipeline_check.py --project "项目名" --status

    # 验证下一阶段的前置条件
    python3 scripts/e2e_pipeline_check.py --project "项目名" --prerequisites ship_pro

输出 JSON:
    {"ok": true, "action": "continue", "next_stage": "ship_pro", "entry": "run_ship_pro()", ...}
    {"ok": true, "action": "done", "message": "Pipeline complete"}
    {"ok": false, "error": "Stage incomplete", "missing": [...]}

契约铁律:
    - 阶段产出不完整 → raise ValueError (不静默跳过)
    - 后续阶段存在 → 必须续行 (不允许终止)
    - 管线完成 → 报告成功
"""

import sys
import json
import argparse
from pathlib import Path

# 自动发现 .deepflow 根目录
_script_path = Path(__file__).resolve()
_deepflow_root = next((d for d in _script_path.parents if (d / 'core' / 'blackboard').is_dir()), None)
if _deepflow_root and str(_deepflow_root) not in sys.path:
    sys.path.insert(0, str(_deepflow_root))

from contracts.shared.e2e_contract import E2EValidator, STANDARD_PIPELINE


def main():
    parser = argparse.ArgumentParser(description="E2E Pipeline Stage Validator (契约笼子)")
    parser.add_argument("--project", required=True, help="Project name (blackboard directory name)")
    parser.add_argument("--completed", help="Stage name that just completed (e.g., solution_pro)")
    parser.add_argument("--status", action="store_true", help="Check full pipeline status")
    parser.add_argument("--prerequisites", help="Check prerequisites for a stage")
    args = parser.parse_args()

    # Resolve project blackboard
    bb_root = _deepflow_root / "blackboard"
    project_bb = bb_root / args.project

    if not project_bb.exists():
        print(json.dumps({
            "ok": False,
            "error": f"Project blackboard not found: {project_bb}",
            "hint": "Run Spec Pro or Solution Pro first",
        }))
        sys.exit(1)

    validator = E2EValidator(project_bb)

    if args.status:
        # Full pipeline status
        is_complete, details = validator.check_pipeline_complete()
        output = {
            "ok": True,
            "action": "status",
            "pipeline_complete": is_complete,
            "stages": {},
        }
        for stage_name, validation in details.items():
            output["stages"][stage_name] = {
                "complete": validation["ok"],
                "produced": validation["produced"],
                "missing": validation["missing"],
            }
        print(json.dumps(output, indent=2, ensure_ascii=False))

    elif args.completed:
        # Check if completed stage's output is valid, get next action
        try:
            next_action = validator.get_next_action(args.completed)
            if next_action is None:
                print(json.dumps({
                    "ok": True,
                    "action": "done",
                    "message": f"Pipeline complete after {args.completed}",
                    "completed_stage": args.completed,
                }))
            else:
                print(json.dumps({
                    "ok": True,
                    "action": "continue",
                    "completed_stage": args.completed,
                    "next_stage": next_action["stage"],
                    "domain": next_action["domain"],
                    "entry_function": next_action["entry_function"],
                    "prerequisites_ok": next_action["prerequisites_ok"],
                    "prerequisites_missing": next_action["prerequisites_missing"],
                    "instruction": f"Must run {next_action['entry_function']} next. Do NOT terminate.",
                }, indent=2, ensure_ascii=False))
        except ValueError as e:
            print(json.dumps({
                "ok": False,
                "action": "blocked",
                "error": str(e),
                "instruction": "Fix the missing outputs before continuing.",
            }))
            sys.exit(1)

    elif args.prerequisites:
        # Check prerequisites for a stage
        result = validator.validate_prerequisites(args.prerequisites)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
