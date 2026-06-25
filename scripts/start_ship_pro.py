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

    # 生成 run_id
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Watcher 配置
    watcher_config_rel = "domains/ship_pro/config/watcher_config.json"
    watcher_config_abs = os.path.join(DEEPFLOW_HOME, watcher_config_rel)

    # ── 构建 Orchestrator task prompt ──
    task = f"""你是 Ship Pro 管线编排器。

## 你的任务
运行完整的 Ship Pro 5 阶段管线，使用 run_pipeline.py CLI 驱动。

## 运行信息
- DeepFlow 根目录: `{DEEPFLOW_HOME}`
- 输入文件: `{input_path}`
- 输出目录: `{output_path}`
- Run ID: `{run_id}`

## 执行步骤

### Phase -1: 原则提取（AI Native）

读取输入文件 `{input_path}` 中的 `constraints` 字段。

用你的 LLM 能力，从 constraints 中提取：
1. `architecture_principles`: 架构原则列表（每条包含 id, name, type, description, severity）
2. `platform_capabilities`: 平台能力列表（每条包含 platform, capability, api, must_use, replaces）

判断标准（用你的理解判断，不是硬编码规则）：
- 如果 constraint 描述的是"必须怎么做"或"禁止怎么做" → architecture_principle
- 如果 constraint 描述的是"基于什么平台"或"用什么工具" → platform_capabilities
- 其他 → 忽略

severity 判断：
- 如果违反会导致系统无法运行或严重偏离设计意图 → BLOCKER
- 如果违反会影响质量但不阻塞 → WARNING

把提取结果写入输入文件（读取原文件，增加这两个字段，写回）。

如果输入文件没有 `constraints` 字段，跳过此阶段。

### Phase 0: 准备管线
```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py prepare {args.input} {args.output}
```

### Phase 1-5: 依次运行 5 个 Agent

对每个 agent（按顺序: architect, decomposer, specifier, reviewer, packager），执行以下循环：

#### 1. 获取 Worker Task Prompt
```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py task <agent_name> {args.output}
```
输出 JSON 包含 `task` 字段（完整的 worker prompt）。

#### 2. Spawn Worker
```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="ship-<agent_name>",
    task=<从 Step 1 输出的 task 字段>
)
sessions_yield()
```

#### 3. 验证 Gate
```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py gate <agent_name> {args.output}
```
输出 JSON 包含 `decision` 字段（PASS/CONDITIONAL/FAIL）。

#### 3.5 语义检查（AI Native，必须执行 architect/decomposer/specifier 三个阶段）

如果 gate 输出包含 `"needs_semantic_check": true`，你必须执行语义检查。

重要：语义检查必须覆盖 architect、decomposer、specifier 三个阶段，不能只跑 architect 就停止。

```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py semantic-task <agent_name> {args.output}
```

这会输出一个语义评估任务（`task` 字段）。你需要：
1. 读取 `task` 字段中的评估 prompt
2. 用你自己的 LLM 能力评估 Worker 输出是否符合架构原则
3. 输出 JSON 结果（decision + issues + reasoning）
4. 将结果写入 `semantic_<agent_name>.json` 文件
5. 运行合并：

```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py merge-semantic <agent_name> {args.output} <semantic_result_json_or_path>
```

合并后的结果作为最终 gate 决策。

语义检查的判断标准：
- 用你的理解判断，不是硬编码规则
- 如果问题严重（如原则被违反），输出 FAIL
- 如果问题中等（如措辞歧义），输出 PASS_WITH_WARNING
- 如果没有问题，输出 PASS

#### 4. 如果 Gate FAIL，重试
```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py feedback <agent_name> {args.output}
```
将 feedback 注入到新的 task prompt 中，重新 spawn worker。
最多重试 2 次（reviewer 最多 5 次）。

#### 5. 更新状态
```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py update-status {args.output} <agent_name> <PASS|CONDITIONAL|FAIL>
```

### Phase 6: 最终验证
```bash
cd {DEEPFLOW_HOME} && PYTHONPATH={DEEPFLOW_HOME} python3 domains/ship_pro/scripts/run_pipeline.py validate {args.output}
```

### Phase 7: 写入完成标记
用 write 工具写入 `{output_path}/.completed`：
```json
{{
  "status": "completed",
  "session_id": "{run_id}",
  "completed_at": "<ISO时间>",
  "stages_completed": 5,
  "failed_stages": []
}}
```

## 约束
- 必须完整运行所有 5 个阶段
- 每个 gate 必须 PASS 或 CONDITIONAL 才能继续下一阶段
- 如果某个 gate 重试耗尽仍 FAIL，记录失败原因并继续（非 abort 级错误）
- 每个阶段完成后必须 update-status
- 禁止跳过验证

## 输出
完成后输出最终状态摘要。
"""

    # 构建 spawn_params
    spawn_params = {
        "runtime": "subagent",
        "mode": "run",
        "label": "ship-pro-orchestrator",
        "task": task,
        "runTimeoutSeconds": 1800
    }

    result = {
        "input_path": input_path,
        "output_path": output_path,
        "run_id": run_id,
        "run_start_at": run_start_at,
        "spawn_params": spawn_params,
        "watcher_config": watcher_config_rel,
        "watcher_config_abs": watcher_config_abs,
        "deepflow_root": DEEPFLOW_HOME,
        "startup_notification": (
            f"✅ 已启动 DeepFlow Ship Pro 管线\n"
            f"📦 输入: {args.input}\n"
            f"📊 共 5 个阶段（Architect → Decomposer → Specifier → Reviewer → Packager）\n"
            f"💬 期间你可以继续问我其他问题，完成后我会通知你"
        )
    }

    # ── Watcher V3 AI Native（铁律固化 2026-06-25）──
    # 主 Agent 创建 cron 时，必须使用 watcher_cron_payload。
    # 禁止主 Agent 手写 watcher prompt。
    try:
        from contracts.shared.watcher_config import build_v3_cron_payload
        result['watcher_cron_payload'] = build_v3_cron_payload(
            config_path=watcher_config_abs,
            base_path=output_path,
            run_start_at=run_start_at,
            cron_job_id="",  # empty = auto-discover (solves chicken-and-egg)
            deepflow_root=DEEPFLOW_HOME,
            display_name="Ship Pro",
            max_runs=15,
            pipeline_id="ship_pro",
        )
    except ImportError:
        result['watcher_cron_payload'] = None

    # 清理旧的 watcher 状态文件（防止残留干扰）
    import shutil
    for f in [".watcher_seen.json", ".watcher_run_count", ".watcher_no_output_count",
              ".watcher_should_remove", ".pipeline_watcher.lock"]:
        p = os.path.join(output_path, f)
        if os.path.exists(p):
            os.remove(p)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
