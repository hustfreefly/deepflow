#!/usr/bin/env python3
"""
Ship Pro V4.0 启动脚本

用途：在 exec 工具中安全启动 Ship Pro V4.0 管线
位置：.deepflow/scripts/start_ship_pro.py

使用方式：
    cd /Users/allen/.openclaw/workspace/.deepflow && python3 scripts/start_ship_pro.py \
      --input "blackboard/<session>/stages/final_result.json" \
      --output "blackboard/<session>/ship_output"

参数说明：
    --input: Solution Pro 的 final_result.json 路径（必填，相对于 .deepflow）
    --output: Ship Pro 输出目录（必填，相对于 .deepflow）
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


def _build_v4_orchestrator_prompt(input_path: str, output_dir: str, deepflow_root: str, run_id: str) -> str:
    """Build V4.0 orchestrator prompt for Generator + Judge loop."""
    return f"""# Ship Pro V4.0 Orchestrator

你是 Ship Pro V4.0 的管线编排器。你的任务是执行 Generator → Judge 两阶段闭环。

## 运行信息

- DeepFlow 根目录: `{deepflow_root}`
- 输入文件: `{input_path}`
- 输出目录: `{output_dir}`
- Run ID: `{run_id}`
- CLI: `python3 {deepflow_root}/domains/ship_pro/scripts/run_pipeline.py`
- Worker model: strong (Qwen 3.7 Max 或同等)
- Generator timeout: 600s | Judge timeout: 300s

## 执行算法

### Phase 0: 初始化

```bash
cd {deepflow_root} && PYTHONPATH=. python3 domains/ship_pro/scripts/run_pipeline.py prepare {input_path} {output_dir}
```

### Phase 1: Generator → Judge 闭环（最多 3 轮）

```
while True:
    # ── Generator 阶段 ──
    1. exec: python3 run_pipeline.py task generator <output_dir>
       → 获取 task prompt（Round 2+ 自动包含 FixContext）
    2. sessions_spawn(worker, task=prompt, runTimeoutSeconds=600)
       → label: "ship-pro-generator-r{{round}}"
    3. sessions_yield()
       → 等待 Generator 完成
    4. exec: python3 run_pipeline.py gate generator <output_dir>
       → Pydantic 门控（GeneratorOutput 验证）
    
    如果 gate FAIL:
        exec: python3 run_pipeline.py increment-retry <output_dir> generator
        如果 allowed=true → 回到步骤 1 重试
        如果 allowed=false → exec: run_pipeline.py finalize <output_dir> fail → 写 .completed → 结束
    
    # ── Judge 阶段 ──
    5. exec: python3 run_pipeline.py task judge <output_dir>
       → 获取 task prompt（包含 Generator 输出引用）
    6. sessions_spawn(worker, task=prompt, runTimeoutSeconds=300)
       → label: "ship-pro-judge-r{{round}}"
    7. sessions_yield()
       → 等待 Judge 完成
    8. exec: python3 run_pipeline.py gate judge <output_dir>
       → Pydantic 门控（JudgeOutput 验证）
    
    如果 gate FAIL:
        exec: python3 run_pipeline.py increment-retry <output_dir> judge
        如果 allowed=true → 回到步骤 5 重试
        如果 allowed=false → exec: run_pipeline.py finalize <output_dir> fail → 写 .completed → 结束
    
    # ── 状态机决策 ──
    9. exec: python3 run_pipeline.py next <output_dir>
       → 解析 action 字段:
       
       - "validate" → 执行 validate + finalize pass → 写 .completed → 完成 ✅
       - "fix_and_rerun" → 执行 fix-context → 继续循环（下一轮 Generator 会收到修复指令）
       - "fail" → 执行 finalize fail → 写 .completed → 失败退出 ❌
       - "spawn" → gate 重试中，继续循环
```

### Phase 2: 完成

```bash
exec: python3 run_pipeline.py validate <output_dir>
exec: python3 run_pipeline.py finalize <output_dir> pass
```

写 `.completed` 文件到 `<output_dir>/blackboard/.completed`:
```json
{{"completed_at": "<ISO timestamp>", "status": "passed"}}
```

## ⛔ 约束

1. **不要跳过 gate** — 每个 Worker 完成后必须 gate 验证
2. **不要忽略 FixContext** — Round 2+ 的 Generator 需要 FixContext 进行定向修复
3. **不要修改 prompt** — task 命令输出的 prompt 直接使用
4. **不要并发** — Generator 和 Judge 必须串行执行
5. **每步 exec 后检查 JSON** — CLI 输出都是 JSON，解析 action/decision 字段做决策
6. **🔴 label 必须带 round 号** — 每轮 spawn 必须用不同的 label（如 `ship-pro-generator-r1`、`ship-pro-judge-r2`），否则完成事件会认错人
7. **🔴 禁止手动改文件** — gate FAIL 时必须 spawn 新 worker 重试，禁止自己用 exec 修改 JSON 输出文件
8. **🔴 不要设置 runTimeoutSeconds** — sessions_spawn 不支持该参数，传了会报错

## spawn Worker 模板

```python
# ⚠️ label 必须包含 round 号，如 r1, r2, r3，绝不能复用
# ⚠️ 必须传 model="bailian2/qwen3.7-max"，否则 worker 会继承 orchestrator 的弱模型
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="ship-pro-generator-r{{round}}",  # round 从 1 开始递增
    task=task_prompt,  # 从 run_pipeline.py task 获取
    model="bailian2/qwen3.7-max",  # Generator/Judge 必须用强模型
    cwd="{deepflow_root}",
)
sessions_yield()
```

记住：你是编排器，不是执行器。所有实际工作通过 spawn worker 完成。
"""


def main():
    parser = argparse.ArgumentParser(description='Ship Pro V4.0 启动脚本')
    parser.add_argument('--input', required=True, help='final_result.json 路径（相对于 .deepflow）')
    parser.add_argument('--output', required=True, help='Ship Pro 输出目录（相对于 .deepflow）')
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
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_v4"

    # Watcher 配置
    watcher_config_rel = "domains/ship_pro/config/watcher_config.json"
    watcher_config_abs = os.path.join(DEEPFLOW_HOME, watcher_config_rel)

    # ── V4.0: Build orchestrator prompt ──
    task = _build_v4_orchestrator_prompt(
        input_path=input_path,
        output_dir=output_path,
        deepflow_root=DEEPFLOW_HOME,
        run_id=run_id,
    )

    # 构建 spawn_params
    spawn_params = {
        "runtime": "subagent",
        "mode": "run",
        "label": "ship-pro-v4-orchestrator",
        "task": task,
        "runTimeoutSeconds": 1800,
        "cwd": DEEPFLOW_HOME,
    }

    result = {
        "version": "4.0.0",
        "input_path": input_path,
        "output_path": output_path,
        "run_id": run_id,
        "run_start_at": run_start_at,
        "spawn_params": spawn_params,
        "watcher_config": watcher_config_rel,
        "watcher_config_abs": watcher_config_abs,
        "deepflow_root": DEEPFLOW_HOME,
        "startup_notification": (
            f"✅ 已启动 Ship Pro V4.0 管线\n"
            f"📦 输入: {args.input}\n"
            f"🔄 2 阶段闭环: Generator ←→ Judge (最多 3 轮)\n"
            f"💬 完成后我会通知你"
        )
    }

    # ── Watcher V3 契约化 ──
    try:
        from contracts.shared.watcher_config import build_v3_cron_payload
        result['watcher_cron_payload'] = build_v3_cron_payload(
            config_path=watcher_config_abs,
            base_path=output_path,
            run_start_at=run_start_at,
            cron_job_id="",
            deepflow_root=DEEPFLOW_HOME,
            display_name="Ship Pro V4",
            max_runs=15,
            pipeline_id="ship_pro",
        )
    except ImportError:
        result['watcher_cron_payload'] = None

    # 清理旧状态文件
    for f in [".watcher_seen.json", ".watcher_run_count", ".watcher_no_output_count",
              ".watcher_should_remove", ".pipeline_watcher.lock", ".completed"]:
        p = os.path.join(output_path, f)
        if os.path.exists(p):
            os.remove(p)
    # 清理 blackboard 子目录
    bb_dir = os.path.join(output_path, "blackboard")
    if os.path.isdir(bb_dir):
        for f in [".completed", "pipeline_status.json", "fix_context.json",
                  "generator_output.json", "judge_output.json"]:
            p = os.path.join(bb_dir, f)
            if os.path.exists(p):
                os.remove(p)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
