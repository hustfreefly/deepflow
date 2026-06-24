#!/usr/bin/env python3
"""
Ship Pro 启动脚本

用途：在 exec 工具中安全启动 Ship Pro 管线
位置：.deepflow/scripts/start_ship_pro.py

使用方式：
    cd /Users/allen/.openclaw/workspace/.deepflow && python3 scripts/start_ship_pro.py \
      --input "blackboard/<session>/stages/final_result.json" \
      --output "blackboard/<session>/ship_output"

参数说明：
    --input: Solution Pro 的 final_result.json 路径（必填，相对于 .deepflow）
    --output: Ship Pro 输出目录（必填，相对于 .deepflow）
    --print-watcher-prompt: 打印 watcher wrapper prompt
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# 动态获取 DeepFlow 根目录
DEEPFLOW_HOME = os.path.expanduser('~/.openclaw/workspace/.deepflow')

if not os.path.exists(DEEPFLOW_HOME):
    print(f"❌ DeepFlow 目录不存在: {DEEPFLOW_HOME}", file=sys.stderr)
    sys.exit(1)

os.chdir(DEEPFLOW_HOME)
if DEEPFLOW_HOME not in sys.path:
    sys.path.insert(0, DEEPFLOW_HOME)

import core.bootstrap


def main():
    parser = argparse.ArgumentParser(description='Ship Pro 启动脚本')
    parser.add_argument('--input', required=True, help='final_result.json 路径（相对于 .deepflow）')
    parser.add_argument('--output', required=True, help='Ship Pro 输出目录（相对于 .deepflow）')
    parser.add_argument('--print-watcher-prompt', action='store_true',
                        help='打印 watcher wrapper prompt（供主 Agent 创建 cron 使用）')
    args = parser.parse_args()

    input_path = os.path.join(DEEPFLOW_HOME, args.input)
    output_path = os.path.join(DEEPFLOW_HOME, args.output)

    # 验证输入文件
    if not os.path.exists(input_path):
        print(f"❌ 输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    # 创建输出目录
    os.makedirs(output_path, exist_ok=True)

    # 记录运行启动时间
    run_start_at = datetime.now(timezone.utc).isoformat()

    # Watcher 配置
    watcher_config_rel = "domains/ship_pro/config/watcher_config.json"
    watcher_config_abs = os.path.join(DEEPFLOW_HOME, watcher_config_rel)

    # 构建 Ship Pro orchestrator task
    task = f"""你是 Ship Pro 管线编排器。

## 你的任务
运行完整的 Ship Pro 5 阶段管线。

## 输入
- Solution Pro 输出: `{input_path}`
- Ship Pro 输出目录: `{output_path}`

## 执行步骤

### 1. 准备阶段
```bash
cd {DEEPFLOW_HOME}
PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py prepare \\
  {args.input} {args.output}
```

### 2. 依次运行 5 个 Agent
按顺序: architect → decomposer → specifier → reviewer → packager

对每个 agent:
```bash
cd {DEEPFLOW_HOME}
PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py run-agent <agent_name> {args.output}
PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py run-gate <agent_name> {args.output}
```

### 3. 最终验证
```bash
cd {DEEPFLOW_HOME}
PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py validate {args.output}
```

## 约束
- 必须完整运行所有 5 个阶段
- 每个 gate 必须 PASS 才能继续下一阶段
- 如果某个 gate FAIL，记录失败原因并停止

## 输出
完成后读取并报告:
1. `{output_path}/summary.md` 内容
2. `{output_path}/ship_package.json` 摘要
3. 每个 gate 结果（PASS/FAIL）
"""

    # 构建 spawn_params
    spawn_params = {
        "runtime": "subagent",
        "mode": "run",
        "label": "ship-pro-pipeline",
        "task": task,
        "runTimeoutSeconds": 1800
    }

    result = {
        "input_path": input_path,
        "output_path": output_path,
        "run_start_at": run_start_at,
        "spawn_params": spawn_params,
        "watcher_config": watcher_config_rel,
        "watcher_config_abs": watcher_config_abs,
        "deepflow_root": DEEPFLOW_HOME,
        "startup_notification": f"✅ 已启动 DeepFlow Ship Pro 管线\n📦 输入: {args.input}\n📊 共 5 个阶段（Architect → Decomposer → Specifier → Reviewer → Packager）\n💬 期间你可以继续问我其他问题，完成后我会通知你"
    }

    # Watcher wrapper prompt
    if args.print_watcher_prompt:
        from scripts.pipeline_watcher import render_wrapper_prompt, WRAPPER_PROMPT_TEMPLATE
        result['watcher_wrapper_prompt_template'] = WRAPPER_PROMPT_TEMPLATE
        result['watcher_wrapper_prompt_prefilled'] = render_wrapper_prompt(
            deepflow_root=DEEPFLOW_HOME,
            config_path=watcher_config_abs,
            base_path=output_path,
            run_start_at=run_start_at,
            cron_job_id="",  # empty = auto-discover (solves chicken-and-egg)
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
