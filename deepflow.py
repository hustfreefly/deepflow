#!/usr/bin/env python3
"""
DeepFlow 统一入口脚本
===================

一键初始化分析任务并生成 Orchestrator 调用指令。

用法:
    python3 deepflow.py --code 688981.SH --name 中芯国际
    python3 deepflow.py --code 688981.SH --name 中芯国际 --force-rebuild

输出:
    JSON 格式的执行摘要，包含 session_id 和调用指令
"""

import sys
import os
import json
import argparse

# DeepFlow 基础路径
DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"
sys.path.insert(0, DEEPFLOW_BASE)

# 复用 master_agent 的函数
from core.master_agent import (
    init_session,
    generate_tasks,
    save_tasks,
    save_execution_plan,
    generate_orchestrator_task
)


def run_analysis(code: str, name: str, industry: str = "半导体制造", force_rebuild: bool = False) -> dict:
    """
    一键执行完整分析初始化
    
    Returns:
        执行摘要，包含 session_id 和下一步调用指令
    """
    print("=" * 60)
    print("DeepFlow 0.1.0 - 投资分析管线")
    print(f"目标: {name}({code})")
    if force_rebuild:
        print("⚠️ 强制重建模式")
    print("=" * 60)
    
    # Step 1: 初始化（复用 master_agent.py）
    print("\n[1/3] 初始化 Session...")
    session_id = init_session(code, name, industry)
    
    # Step 2: 生成 Tasks（复用 master_agent.py）
    print("[2/3] 生成 Worker Tasks...")
    tasks = generate_tasks(session_id, code, name, industry)
    tasks_path = save_tasks(tasks, session_id)
    
    # Step 3: 保存执行计划（复用 master_agent.py）
    print("[3/3] 生成执行计划...")
    plan_path = save_execution_plan(session_id, code, name, industry, force_rebuild)
    
    # Step 4: 生成 Orchestrator Task（复用 master_agent.py）
    orchestrator_task = generate_orchestrator_task(session_id)
    orchestrator_task_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}/orchestrator_task.txt"
    with open(orchestrator_task_path, 'w', encoding='utf-8') as f:
        f.write(orchestrator_task)
    
    print("\n✅ 初始化完成！")
    print(f"   Session: {session_id}")
    print(f"   Tasks: {tasks_path}")
    print(f"   Plan: {plan_path}")
    
    # 构建调用指令
    result = {
        "session_id": session_id,
        "company_code": code,
        "company_name": name,
        "industry": industry,
        "force_rebuild": force_rebuild,
        "status": "initialized",
        "next_step": "spawn_orchestrator",
        "call_instruction": {
            "tool": "sessions_spawn",
            "params": {
                "runtime": "subagent",
                "mode": "run",
                "label": f"orchestrator_{session_id}",
                "task": f"""你是 DeepFlow V4.0 Orchestrator Agent。

请执行以下步骤完成投资分析管线：

1. 读取执行计划: {plan_path}
2. 读取 Tasks 文件: {tasks_path}
3. 按顺序 spawn Workers（DataManager → Planner → Researchers ×6 → Auditors ×3 → Fixer → Summarizer → SendReporter）
4. 所有 sessions_spawn 必须设置 label 参数
5. 使用 sessions_yield 等待每个阶段完成
6. 最终报告应写入: {DEEPFLOW_BASE}/blackboard/{session_id}/final_report.md

关键规则:
- execution_plan 中 force_rebuild={force_rebuild}，{'禁止复用历史数据' if force_rebuild else '可以检查历史数据'}
- Worker 失败不阻断，记录错误继续
- 检查 final_report.md 是否存在作为完成标志
""",
                "timeout_seconds": 1800
            }
        },
        "paths": {
            "tasks": tasks_path,
            "plan": plan_path,
            "orchestrator_task": orchestrator_task_path,
            "blackboard": f"{DEEPFLOW_BASE}/blackboard/{session_id}"
        }
    }
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="DeepFlow 0.1.0 - 投资分析统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python3 deepflow.py --code 688981.SH --name 中芯国际
    python3 deepflow.py --code 688981.SH --name 中芯国际 --force-rebuild
    python3 deepflow.py --code 300604.SZ --name 长川科技 --industry 半导体设备
        """
    )
    parser.add_argument("--code", required=True, help="股票代码（如 688981.SH）")
    parser.add_argument("--name", required=True, help="公司名称（如 中芯国际）")
    parser.add_argument("--industry", default="半导体制造", help="行业（默认: 半导体制造）")
    parser.add_argument("--force-rebuild", action="store_true", help="强制重新分析，不重用历史数据")
    
    args = parser.parse_args()
    
    # 执行分析
    result = run_analysis(args.code, args.name, args.industry, args.force_rebuild)
    
    # 输出 JSON（供主 Agent 解析）
    print("\n" + "=" * 60)
    print("执行摘要（JSON）")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
