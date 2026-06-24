#!/usr/bin/env python3
"""
Solution Pro 启动脚本

用途：在 exec 工具中安全启动 Solution Pro 管线
位置：.deepflow/scripts/start_solution_pro.py

使用方式：
    cd /Users/allen/.openclaw/workspace/.deepflow && python3 scripts/start_solution_pro.py \
      --topic "跨境AI算力中转站平台" \
      --solution-type "architecture" \
      --constraints '["预算: 3000刀", "时间: 15天"]' \
      --living-spec-path "blackboard/spec_xxx/spec/living_spec.json"

为什么需要这个脚本：
    1. exec 工具中多行 python3 -c "..." 会遇到引号转义问题
    2. exec 工具中 ~ 可能不会自动展开为 home 目录
    3. 通过命令行参数传递数据，避免在命令中嵌入复杂 JSON

参数说明：
    --topic: 项目主题（必填）
    --solution-type: 方案类型，默认 "architecture"
    --constraints: 约束条件，JSON 数组格式，如 '["预算: 3000刀"]'
    --living-spec-path: Living Spec 文件路径（相对于 .deepflow 目录）
    --stakeholders: 利益相关者，JSON 数组格式（可选）
"""

import argparse
import json
import os
import sys

# 动态获取 DeepFlow 根目录（跨平台兼容）
# 使用 os.path.expanduser('~') 动态获取 home 目录，避免硬编码 /Users/allen
DEEPFLOW_HOME = os.path.expanduser('~/.openclaw/workspace/.deepflow')

# 验证路径存在
if not os.path.exists(DEEPFLOW_HOME):
    print(f"❌ DeepFlow 目录不存在: {DEEPFLOW_HOME}", file=sys.stderr)
    print(f"💡 请确认 OpenClaw 工作空间已正确初始化", file=sys.stderr)
    sys.exit(1)

# 确保在正确的工作目录
os.chdir(DEEPFLOW_HOME)
if DEEPFLOW_HOME not in sys.path:
    sys.path.insert(0, DEEPFLOW_HOME)

import core.bootstrap
from domains.solution_pro import run_solution_pro

def main():
    parser = argparse.ArgumentParser(description='启动 Solution Pro 管线')
    parser.add_argument('--topic', required=True, help='项目主题')
    parser.add_argument('--solution-type', default='architecture', help='方案类型')
    parser.add_argument('--constraints', default='[]', help='约束条件（JSON 数组）')
    parser.add_argument('--living-spec-path', help='Living Spec 文件路径（相对于 .deepflow）')
    parser.add_argument('--stakeholders', default='[]', help='利益相关者（JSON 数组）')
    parser.add_argument('--print-watcher-prompt', action='store_true',
                        help='打印 watcher wrapper prompt（供主 Agent 创建 cron 使用）')
    
    args = parser.parse_args()
    
    # 解析 JSON 参数
    try:
        constraints = json.loads(args.constraints)
        stakeholders = json.loads(args.stakeholders)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 读取 Living Spec（如果提供）
    living_spec = None
    if args.living_spec_path:
        living_spec_full_path = os.path.join(DEEPFLOW_HOME, args.living_spec_path)
        if not os.path.exists(living_spec_full_path):
            print(f"❌ Living Spec 文件不存在: {living_spec_full_path}", file=sys.stderr)
            sys.exit(1)
        
        try:
            with open(living_spec_full_path, 'r', encoding='utf-8') as f:
                living_spec = json.load(f)
        except Exception as e:
            print(f"❌ 读取 Living Spec 失败: {e}", file=sys.stderr)
            sys.exit(1)
    
    # 调用 run_solution_pro
    try:
        result = run_solution_pro(
            topic=args.topic,
            solution_type=args.solution_type,
            constraints=constraints,
            stakeholders=stakeholders,
            living_spec=living_spec
        )
        
        # 生成 startup_notification（从 execution_plan.json 动态读取阶段列表）
        # 目的：消除主 Agent 编造阶段名的空间
        plan_path = result.get('plan_path', '')
        startup_notification = None
        if plan_path and os.path.exists(plan_path):
            try:
                with open(plan_path, 'r', encoding='utf-8') as f:
                    plan = json.load(f)
                phases = plan.get('phases', [])
                phase_count = len(phases)
                parallel_count = sum(1 for p in phases if p.get('parallel'))
                stage_lines = []
                for p in phases:
                    phase_num = p.get('phase', '?')
                    stage_name = p.get('stage', 'unknown')
                    if p.get('parallel'):
                        workers = p.get('workers', [])
                        worker_count = len(workers)
                        stage_lines.append(f"  {phase_num}. {stage_name} (×{worker_count} 并行)")
                    else:
                        stage_lines.append(f"  {phase_num}. {stage_name}")
                stage_list = '\n'.join(stage_lines)
                startup_notification = (
                    f"✅ 已启动 DeepFlow Solution Pro 管线\n"
                    f"📋 主题: {args.topic}\n"
                    f"📊 共 {phase_count} 个阶段（{parallel_count} 个并行阶段），预计 30-60 分钟\n\n"
                    f"阶段列表：\n{stage_list}\n\n"
                    f"💬 期间你可以继续问我其他问题，完成后我会通知你"
                )
            except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
                print(f"⚠️ 读取执行计划失败，跳过 startup_notification: {e}", file=sys.stderr)
        result['startup_notification'] = startup_notification

        # Watcher wrapper prompt (for main Agent to create cron)
        if args.print_watcher_prompt:
            from contracts.shared.watcher_config import render_wrapper_prompt, WRAPPER_PROMPT_TEMPLATE as WRAPPER_PROMPT_TEMPLATE
            result['watcher_wrapper_prompt_template'] = WRAPPER_PROMPT_TEMPLATE
            # Render with all values; cron_job_id="" enables auto-discover mode
            result['watcher_wrapper_prompt_prefilled'] = render_wrapper_prompt(
                deepflow_root=result.get('deepflow_root', DEEPFLOW_HOME),
                config_path=result.get('watcher_config_abs', ''),
                base_path=result.get('base_path', ''),
                run_start_at=result.get('run_start_at', ''),
                cron_job_id="",  # empty = auto-discover (solves chicken-and-egg)
            )

        # 输出结果（JSON 格式）
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"❌ 启动 Solution Pro 失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
