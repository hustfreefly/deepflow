"""
DeepFlow V4.0 Orchestrator Agent Guide

Identity:
You are the DeepFlow V4.0 Orchestrator Agent (depth-1).
Your role is the **dispatch center**: read Tasks files, spawn Workers in order, and manage the pipeline.

Session ID Retrieval:
1. From Tasks filename (recommended):
   import glob, os
   tasks_files = glob.glob('/Users/allen/.openclaw/workspace/.deepflow/blackboard/*/tasks.json')
   if tasks_files:
       latest = max(tasks_files, key=os.path.getmtime)
       session_id = os.path.basename(os.path.dirname(latest))
2. From environment variable:
   session_id = os.environ.get('DEEPFLOW_SESSION_ID')
3. From execution plan:
   plan_files = glob.glob('/Users/allen/.openclaw/workspace/.deepflow/blackboard/*/execution_plan.json')
   if plan_files:
       latest = max(plan_files, key=lambda x: os.path.getmtime(x))
       with open(latest) as f:
           plan = json.load(f)
       session_id = plan['session_id']

Core Principles:
1. Dispatch only, no analysis - You do not execute data analysis, only manage Workers.
2. File-driven - All Tasks are read from files, not relying on memory state.
3. Tool invocation - Use `sessions_spawn` to create Workers, use `sessions_yield` to wait.
4. Fault tolerance - Worker failures do not block the pipeline.

Input Files:
Read these files before executing tasks:
- tasks.json: Contains all worker tasks.
- execution_plan.json: Contains the execution plan.

Execution Steps:
Phase 0: Confirm initialization.
Phase 1: DataManager Worker (spawn + yield).
Phase 2: Planner Worker (spawn + yield).
Phase 3: Researchers x6 (parallel spawn + yield).
Phase 4: Auditors x3 (parallel spawn + yield).
Phase 5: Fixer Worker (optional, spawn + yield).
Phase 6: Summarizer Worker (spawn + yield).
Phase 7: SendReport Worker (spawn + yield) - 发送投资摘要到飞书。

Convergence Check:
Check for final_report.md after completion.

Error Handling:
- Worker timeout: Log and continue.
- Worker failure: Log and continue.
- DataManager failure: Try fallback or continue with limited data.

Output:
Update execution_plan.json status to "completed".

Key Reminders:
1. Do not execute Python code to spawn Workers - use `sessions_spawn` tool.
2. Do not poll status - use `sessions_yield` to wait for push events.
3. Worker failures do not block - log errors and continue.
4. Final report is the key output - check for `final_report.md`.

## Force Rebuild 规则（重要）

执行前必须读取 execution_plan.json，检查 `force_rebuild` 字段：

- **如果 force_rebuild: true**（强制重建）：
  - ⚠️ **禁止使用任何历史 session 的数据**
  - ⚠️ **每个 Phase 必须重新 spawn Workers 执行**
  - ⚠️ **即使检测到旧的 final_report.md，也必须重新生成**
  - 所有输出写入当前 session 的 blackboard 目录

- **如果 force_rebuild: false 或未设置**（默认）：
  - 可以检查历史 session 是否有可用数据
  - 如果历史数据完整且有效，可以复用以节省资源
  - 但必须验证数据的新鲜度

## 执行检查清单

每个 Phase 执行前：
- [ ] 检查 execution_plan.json 中的 `force_rebuild` 字段
- [ ] 如果 force_rebuild=true，确认当前是全新执行
- [ ] 如果 force_rebuild=false，检查是否有历史数据可用
- [ ] 记录决策原因到 execution_plan.json 的 `notes` 字段
"""

import sys
import os
import json
import uuid
import time

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"
sys.path.insert(0, DEEPFLOW_BASE)

from core.task_builder import (
    build_data_manager_task, build_planner_task,
    build_researcher_task, build_auditor_task,
    build_fixer_task, build_summarizer_task,
    build_send_reporter_task
)


def run_initialization(company_code: str, company_name: str, industry: str = "半导体设备", force_rebuild: bool = False) -> dict:
    """Initialize session and generate tasks."""
    code_clean = company_code.replace('.SH', '').replace('.SZ', '')
    session_id = f"{company_name}_{code_clean}_{uuid.uuid4().hex[:8]}"
    
    base_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}"
    os.makedirs(f"{base_path}/data", exist_ok=True)
    os.makedirs(f"{base_path}/stages", exist_ok=True)
    
    tasks = {
        "data_manager": build_data_manager_task(session_id, company_code, company_name, industry),
        "planner": build_planner_task(session_id, company_code, company_name),
        "researchers": {a: build_researcher_task(a, session_id, company_code, company_name) 
                      for a in ["finance", "tech", "market", "macro_chain", "management", "sentiment"]},
        "auditors": {t: build_auditor_task(t, session_id, company_code, company_name) 
                    for t in ["factual", "upside", "downside"]},
        "fixer": build_fixer_task(session_id, company_code, company_name),
        "summarizer": build_summarizer_task(session_id, company_code, company_name),
        "send_reporter": build_send_reporter_task(session_id, company_code, company_name)
    }
    
    tasks_path = f"{base_path}/tasks.json"
    with open(tasks_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
        
    plan = {
        "session_id": session_id,
        "company_code": company_code,
        "company_name": company_name,
        "version": "4.0",
        "force_rebuild": force_rebuild,
        "phases": [
            {"phase": 1, "worker": "data_manager", "timeout": 300},
            {"phase": 2, "worker": "planner", "timeout": 180},
            {"phase": 3, "workers": list(tasks["researchers"].keys()), "parallel": True, "timeout": 300},
            {"phase": 4, "workers": list(tasks["auditors"].keys()), "parallel": True, "timeout": 240},
            {"phase": 5, "worker": "fixer", "timeout": 180, "optional": True},
            {"phase": 6, "worker": "summarizer", "timeout": 240},
            {"phase": 7, "worker": "send_reporter", "timeout": 60, "optional": True}
        ]
    }
    plan_path = f"{base_path}/execution_plan.json"
    with open(plan_path, 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        
    return {
        "session_id": session_id,
        "tasks_path": tasks_path,
        "plan_path": plan_path
    }


def generate_all_tasks(session_id: str, company_code: str, company_name: str, industry: str = "半导体设备") -> dict:
    """Generate all worker tasks for a given session."""
    return {
        "data_manager": build_data_manager_task(session_id, company_code, company_name, industry),
        "planner": build_planner_task(session_id, company_code, company_name),
        "researchers": {a: build_researcher_task(a, session_id, company_code, company_name) 
                      for a in ["finance", "tech", "market", "macro_chain", "management", "sentiment"]},
        "auditors": {t: build_auditor_task(t, session_id, company_code, company_name) 
                    for t in ["factual", "upside", "downside"]},
        "fixer": build_fixer_task(session_id, company_code, company_name),
        "summarizer": build_summarizer_task(session_id, company_code, company_name),
        "send_reporter": build_send_reporter_task(session_id, company_code, company_name)
    }


if __name__ == "__main__":
    result = run_initialization("688652.SH", "京仪装备", force_rebuild=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
