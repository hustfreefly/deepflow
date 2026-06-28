#!/usr/bin/env python3
"""
Ship Pro V5.0 启动脚本

用途：在 exec 工具中安全启动 Ship Pro V5.0 管线
位置：.deepflow/scripts/start_ship_pro_v5.py

使用方式：
    cd /Users/allen/.openclaw/workspace/.deepflow && python3 scripts/start_ship_pro_v5.py \
      --input "blackboard/<session>/stages/final_result.json" \
      --output "blackboard/<session>/ship_v5_output"
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

DEEPFLOW_HOME = os.path.expanduser('~/.openclaw/workspace/.deepflow')

if not os.path.exists(DEEPFLOW_HOME):
    print(f"❌ DeepFlow 目录不存在: {DEEPFLOW_HOME}", file=sys.stderr)
    sys.exit(1)

os.chdir(DEEPFLOW_HOME)
if DEEPFLOW_HOME not in sys.path:
    sys.path.insert(0, DEEPFLOW_HOME)


def _build_v5_orchestrator_prompt(input_path: str, output_dir: str, deepflow_root: str, run_id: str) -> str:
    """Build V5.0 orchestrator prompt from template."""
    prompt_path = Path(deepflow_root) / "domains/ship_pro/v5/prompts/v5_orchestrator.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"V5 orchestrator prompt not found: {prompt_path}")

    template = prompt_path.read_text()

    # 替换变量
    prompt = template.replace("{deepflow_root}", deepflow_root)
    prompt = prompt.replace("{input_path}", input_path)
    prompt = prompt.replace("{output_dir}", output_dir)
    prompt = prompt.replace("{run_id}", run_id)

    return prompt


def main():
    parser = argparse.ArgumentParser(description='Ship Pro V5.0 启动脚本')
    parser.add_argument('--input', required=True, help='final_result.json 路径（相对于 .deepflow）')
    parser.add_argument('--output', required=True, help='Ship Pro V5 输出目录（相对于 .deepflow）')
    args = parser.parse_args()

    input_path = os.path.join(DEEPFLOW_HOME, args.input)
    output_path = os.path.join(DEEPFLOW_HOME, args.output)

    if not os.path.exists(input_path):
        print(f"❌ 输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_path, exist_ok=True)

    run_start_at = datetime.now(timezone.utc).isoformat()
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_v5"

    # Build orchestrator prompt
    task = _build_v5_orchestrator_prompt(
        input_path=input_path,
        output_dir=output_path,
        deepflow_root=DEEPFLOW_HOME,
        run_id=run_id,
    )

    # 构建 spawn_params
    spawn_params = {
        "runtime": "subagent",
        "mode": "run",
        "label": "ship-pro-v5-orchestrator",
        "task": task,
        "cwd": DEEPFLOW_HOME,
    }

    # Watcher config
    watcher_config_rel = "domains/ship_pro/config/watcher_config.json"
    watcher_config_abs = os.path.join(DEEPFLOW_HOME, watcher_config_rel)

    result = {
        "version": "5.0.0",
        "input_path": input_path,
        "output_path": output_path,
        "run_id": run_id,
        "run_start_at": run_start_at,
        "spawn_params": spawn_params,
        "watcher_config": watcher_config_rel,
        "watcher_config_abs": watcher_config_abs,
        "deepflow_root": DEEPFLOW_HOME,
        "startup_notification": (
            f"✅ 已启动 Ship Pro V5.0 管线\n"
            f"📦 输入: {args.input}\n"
            f"🔄 Phase 1 (Blueprint) + Phase 2 (Delivery)\n"
            f"🤖 13 个 LLM Agent + 3 个确定性代码模块\n"
            f"💬 完成后我会通知你"
        ),
    }

    # Watcher V3 契约化
    try:
        from contracts.shared.watcher_config import build_v3_cron_payload
        result['watcher_cron_payload'] = build_v3_cron_payload(
            config_path=watcher_config_abs,
            base_path=output_path,
            run_start_at=run_start_at,
            cron_job_id="",
            deepflow_root=DEEPFLOW_HOME,
            display_name="Ship Pro V5",
            max_runs=25,  # V5 更长：Phase1(8 agents) + Phase2(7 agents + 3 code) + fix cycles
            pipeline_id="ship_pro_v5",
        )
    except ImportError:
        result['watcher_cron_payload'] = None

    # 清理旧状态
    for f in [".watcher_seen.json", ".watcher_run_count", ".watcher_no_output_count",
              ".watcher_should_remove", ".pipeline_watcher.lock", ".completed"]:
        p = os.path.join(output_path, f)
        if os.path.exists(p):
            os.remove(p)

    bb_dir = os.path.join(output_path, "blackboard")
    if os.path.isdir(bb_dir):
        for f in [".completed", "pipeline_status.json", "fix_context_p1.json",
                   "fix_context_p2.json"]:
            p = os.path.join(bb_dir, f)
            if os.path.exists(p):
                os.remove(p)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
