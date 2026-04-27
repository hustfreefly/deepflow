"""
Orchestrator V4.0 - 纯调度实现
=================================

职责：
1. 生成 session_id
2. 创建 blackboard 目录  
3. 生成所有 Worker Tasks
4. （由主Agent）使用 sessions_spawn 创建 Workers

契约: cage/orchestrator_contract.yaml
"""

import sys
import os
import json
import uuid
import time

DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)
sys.path.insert(0, DEEPFLOW_BASE)

from core.task_builder import (
    build_data_manager_task, build_planner_task,
    build_researcher_task, build_auditor_task,
    build_fixer_task, build_summarizer_task
)


class OrchestratorV4:
    """Orchestrator V4.0"""
    
    def __init__(self, code: str, name: str, industry: str = "半导体设备"):
        self.company_code = code
        self.company_name = name
        self.industry = industry
        self.session_id = None
        self.base_path = None
    
    def init(self) -> str:
        """初始化 session"""
        code_clean = self.company_code.replace('.SH', '').replace('.SZ', '')
        self.session_id = f"{self.company_name}_{code_clean}_{uuid.uuid4().hex[:8]}"
        self.base_path = f"{DEEPFLOW_BASE}/blackboard/{self.session_id}"
        
        os.makedirs(f"{self.base_path}/data", exist_ok=True)
        os.makedirs(f"{self.base_path}/stages", exist_ok=True)
        
        print(f"[Orchestrator] Session: {self.session_id}")
        return self.session_id
    
    def get_all_tasks(self) -> dict:
        """获取所有 Worker Tasks"""
        return {
            "data_manager": build_data_manager_task(self.session_id, self.company_code, self.company_name, self.industry),
            "planner": build_planner_task(self.session_id, self.company_code, self.company_name),
            "researchers": {a: build_researcher_task(a, self.session_id, self.company_code, self.company_name) 
                          for a in ["finance", "tech", "market", "macro_chain", "management", "sentiment"]},
            "auditors": {t: build_auditor_task(t, self.session_id, self.company_code, self.company_name) 
                        for t in ["factual", "upside", "downside"]},
            "fixer": build_fixer_task(self.session_id, self.company_code, self.company_name),
            "summarizer": build_summarizer_task(self.session_id, self.company_code, self.company_name)
        }
    
    def save_execution_plan(self):
        """保存执行计划"""
        tasks = self.get_all_tasks()
        plan = {
            "session_id": self.session_id,
            "company_code": self.company_code,
            "company_name": self.company_name,
            "version": "4.0",
            "phases": [
                {"phase": 1, "worker": "data_manager", "timeout": 300},
                {"phase": 2, "worker": "planner", "timeout": 180},
                {"phase": 3, "workers": list(tasks["researchers"].keys()), "parallel": True, "timeout": 300},
                {"phase": 4, "workers": list(tasks["auditors"].keys()), "parallel": True, "timeout": 240},
                {"phase": 5, "worker": "fixer", "timeout": 180, "optional": True},
                {"phase": 6, "worker": "summarizer", "timeout": 240}
            ]
        }
        with open(f"{self.base_path}/execution_plan.json", 'w') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        return plan


def main():
    """入口"""
    orch = OrchestratorV4("688652.SH", "京仪装备")
    session_id = orch.init()
    tasks = orch.get_all_tasks()
    plan = orch.save_execution_plan()
    print(f"\n✅ Orchestrator 初始化完成")
    print(f"   Session: {session_id}")
    print(f"   Tasks prepared: {len(tasks)}")
    return session_id, tasks


if __name__ == "__main__":
    main()
