#!/usr/bin/env python3
"""
Solution Pro 启动脚本

用途：在 exec 工具中安全启动 Solution Pro 管线
位置：.deepflow/scripts/start_solution_pro.py

使用方式：
    cd {deepflow_root} && python3 scripts/start_solution_pro.py \
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
    
    # 契约笼子（2026-07-05）：自动发现 Living Spec（AI Native 数据流桥接）
    # 优先级：1) 显式 --living-spec-path 2) 自动扫描最近的 Spec Pro 输出
    living_spec = None
    living_spec_full_path = None
    
    if args.living_spec_path:
        living_spec_full_path = os.path.join(DEEPFLOW_HOME, args.living_spec_path)
        if not os.path.exists(living_spec_full_path):
            print(f"❌ Living Spec 文件不存在: {living_spec_full_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # 自动发现：扫描 .deepflow/blackboard/ 找最近的 spec_* 目录中的 living_spec.json
        blackboard_dir = os.path.join(DEEPFLOW_HOME, "blackboard")
        if os.path.exists(blackboard_dir):
            spec_dirs = sorted(
                [d for d in os.listdir(blackboard_dir) if d.startswith("spec_")],
                key=lambda d: os.path.getmtime(os.path.join(blackboard_dir, d)),
                reverse=True,
            )
            for spec_dir in spec_dirs[:5]:  # 只检查最近 5 个
                candidate = os.path.join(blackboard_dir, spec_dir, "spec", "living_spec.json")
                completed_marker = os.path.join(blackboard_dir, spec_dir, ".completed")
                if os.path.exists(candidate) and os.path.exists(completed_marker):
                    living_spec_full_path = candidate
                    print(f"✅ 自动发现 Living Spec: {spec_dir}/spec/living_spec.json", file=sys.stderr)
                    break
    
    if living_spec_full_path:
        try:
            with open(living_spec_full_path, 'r', encoding='utf-8') as f:
                living_spec = json.load(f)
        except Exception as e:
            print(f"❌ 读取 Living Spec 失败: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("⚠️ 未找到 Living Spec，将使用 topic 生成最小 frozen_spec", file=sys.stderr)
    
    # 契约笼子（2026-07-05）：调用 三模块架构
    try:
        result = run_solution_pro(
            user_input=args.topic,   # 第一参数是 user_input
            topic=args.topic,        # topic 作为 kwarg 传递
            solution_type=args.solution_type,
            constraints=constraints,
            stakeholders=stakeholders,
            living_spec=living_spec,
        )

        # startup_notification（三模块架构，无需读 execution_plan.json）
        result['startup_notification'] = (
            f"✅ 已启动 DeepFlow Solution Pro 管线\n"
            f"📋 主题: {args.topic}\n"
            f"🏛️ 架构: Planning（三层）→ Research（多专家并行）→ Summary（5+1 Phase 收敛）\n"
            f"⏱️ 预计: 20-40 分钟\n"
            f"💬 期间你可以继续问我其他问题，完成后我会通知你"
        )

        # Watcher 配置（元数据，由主 Agent 创建 cron job）
        from datetime import datetime
        result['run_start_at'] = datetime.now().isoformat()
        result['deepflow_root'] = DEEPFLOW_HOME
        result['watcher_config'] = 'domains/solution_pro/config/watcher_config.json'
        result['watcher_config_abs'] = os.path.join(DEEPFLOW_HOME, 'domains/solution_pro/config/watcher_config.json')

        # 输出结果（JSON 格式）
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"❌ 启动 Solution Pro 失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
