#!/usr/bin/env python3
"""
Master Agent V4.0
==================

主Agent（depth-0）执行脚本。

职责：
1. 生成 session_id
2. 创建 Blackboard 目录
3. 调用 Task Builder 生成所有 Worker Tasks
4. 保存 Tasks 到文件
5. 生成 Orchestrator Agent 指南
6. 返回执行摘要（供主Agent使用 sessions_spawn 创建 Orchestrator）

使用方式：
    python3 master_agent.py --code 688981.SH --name 中芯国际 --industry 半导体制造
"""

import sys
import os
import json
import uuid
import argparse
from datetime import datetime

# DeepFlow 基础路径
DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)
sys.path.insert(0, DEEPFLOW_BASE)

from core.task_builder import (
    build_data_manager_task,
    build_planner_task,
    build_researcher_task,
    build_auditor_task,
    build_fixer_task,
    build_summarizer_task,
    build_send_reporter_task
)


def init_session(company_code: str, company_name: str, industry: str) -> str:
    """生成 session_id 并创建目录"""
    code_clean = company_code.replace('.SH', '').replace('.SZ', '')
    session_id = f"{company_name}_{code_clean}_{uuid.uuid4().hex[:8]}"
    
    base_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}"
    os.makedirs(f"{base_path}/data", exist_ok=True)
    os.makedirs(f"{base_path}/stages", exist_ok=True)
    
    print(f"[MasterAgent] Session: {session_id}")
    print(f"[MasterAgent] Blackboard: {base_path}")
    return session_id


def generate_tasks(session_id: str, company_code: str, company_name: str, industry: str) -> dict:
    """生成所有 Worker Tasks"""
    print("[MasterAgent] 生成 Worker Tasks...")
    
    tasks = {
        "data_manager": build_data_manager_task(session_id, company_code, company_name, industry),
        "planner": build_planner_task(session_id, company_code, company_name),
        "researchers": {},
        "auditors": {},
        "fixer": build_fixer_task(session_id, company_code, company_name),
        "summarizer": build_summarizer_task(session_id, company_code, company_name),
        "send_reporter": build_send_reporter_task(session_id, company_code, company_name)
    }
    
    # 生成 6 个 Researcher Tasks
    for angle in ["finance", "tech", "market", "macro_chain", "management", "sentiment"]:
        tasks["researchers"][angle] = build_researcher_task(
            angle, session_id, company_code, company_name, industry
        )
    
    # 生成 3 个 Auditor Tasks
    for auditor_type in ["factual", "upside", "downside"]:
        tasks["auditors"][auditor_type] = build_auditor_task(
            auditor_type, session_id, company_code, company_name
        )
    
    print(f"[MasterAgent] Tasks 生成完成:")
    print(f"  - DataManager: {len(tasks['data_manager'])} 字符")
    print(f"  - Planner: {len(tasks['planner'])} 字符")
    print(f"  - Researchers: {len(tasks['researchers'])} 个")
    print(f"  - Auditors: {len(tasks['auditors'])} 个")
    print(f"  - Fixer: {len(tasks['fixer'])} 字符")
    print(f"  - Summarizer: {len(tasks['summarizer'])} 字符")
    
    return tasks


def save_tasks(tasks: dict, session_id: str) -> str:
    """保存 Tasks 到文件"""
    base_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}"
    tasks_path = f"{base_path}/tasks.json"
    
    with open(tasks_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    print(f"[MasterAgent] Tasks 已保存: {tasks_path}")
    return tasks_path


def save_execution_plan(session_id: str, company_code: str, company_name: str, industry: str, force_rebuild: bool = False) -> str:
    """保存执行计划"""
    plan = {
        "session_id": session_id,
        "company_code": company_code,
        "company_name": company_name,
        "industry": industry,
        "version": "4.0",
        "force_rebuild": force_rebuild,
        "created_at": datetime.now().isoformat(),
        "phases": [
            {"phase": 1, "name": "data_manager", "worker": "data_manager", "timeout": 300},
            {"phase": 2, "name": "planner", "worker": "planner", "timeout": 180},
            {"phase": 3, "name": "researchers", "parallel": True, "workers": ["finance", "tech", "market", "macro_chain", "management", "sentiment"], "timeout": 300},
            {"phase": 4, "name": "auditors", "parallel": True, "workers": ["factual", "upside", "downside"], "timeout": 240},
            {"phase": 5, "name": "fixer", "worker": "fixer", "timeout": 180, "optional": True},
            {"phase": 6, "name": "summarizer", "worker": "summarizer", "timeout": 240},
            {"phase": 7, "name": "send_report", "worker": "send_reporter", "timeout": 60, "description": "发送投资摘要到飞书"}
        ]
    }
    
    base_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}"
    plan_path = f"{base_path}/execution_plan.json"
    
    with open(plan_path, 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    
    print(f"[MasterAgent] 执行计划已保存: {plan_path}")
    return plan_path


def generate_orchestrator_task(session_id: str) -> str:
    """读取 Orchestrator Agent 指南"""
    guide_path = f"{DEEPFLOW_BASE}/orchestrator_agent.py"
    
    with open(guide_path, 'r', encoding='utf-8') as f:
        guide = f.read()
    
    # 替换 session_id 占位符
    guide = guide.replace("{session_id}", session_id)
    
    return guide


def main():
    """主流程"""
    parser = argparse.ArgumentParser(description="Master Agent V4.0")
    parser.add_argument("--code", default="688981.SH", help="股票代码")
    parser.add_argument("--name", default="中芯国际", help="公司名称")
    parser.add_argument("--industry", default="半导体制造", help="行业")
    parser.add_argument("--force-rebuild", action="store_true", help="强制重新分析，不重用历史数据")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Master Agent V4.0 - 初始化管线")
    print(f"目标: {args.name}({args.code})")
    if args.force_rebuild:
        print("⚠️ 强制重建模式：将重新执行所有分析步骤")
    print("=" * 60)
    
    # Step 1: 初始化
    session_id = init_session(args.code, args.name, args.industry)
    
    # Step 2: 生成 Tasks
    tasks = generate_tasks(session_id, args.code, args.name, args.industry)
    
    # Step 3: 保存 Tasks
    tasks_path = save_tasks(tasks, session_id)
    
    # Step 4: 保存执行计划
    plan_path = save_execution_plan(session_id, args.code, args.name, args.industry, args.force_rebuild)
    
    # Step 5: 生成 Orchestrator Task
    orchestrator_task = generate_orchestrator_task(session_id)
    orchestrator_task_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}/orchestrator_task.txt"
    with open(orchestrator_task_path, 'w', encoding='utf-8') as f:
        f.write(orchestrator_task)
    
    # 汇总
    print("\n" + "=" * 60)
    print("初始化完成！")
    print("=" * 60)
    print(f"Session: {session_id}")
    print(f"Tasks: {tasks_path}")
    print(f"Plan: {plan_path}")
    print(f"Orchestrator Task: {orchestrator_task_path}")
    print("\n下一步：使用 sessions_spawn 创建 Orchestrator Agent")
    print(f"Task 内容见: {orchestrator_task_path}")
    
    # 输出 JSON 摘要（供主Agent解析）
    result = {
        "session_id": session_id,
        "company_code": args.code,
        "company_name": args.name,
        "industry": args.industry,
        "force_rebuild": args.force_rebuild,
        "tasks_path": tasks_path,
        "plan_path": plan_path,
        "orchestrator_task_path": orchestrator_task_path,
        "status": "initialized"
    }
    
    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    
    return result


if __name__ == "__main__":
    main()
