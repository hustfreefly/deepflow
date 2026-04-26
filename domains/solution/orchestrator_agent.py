"""
Solution Orchestrator V2.0 - 纯调度实现
=======================================

职责：
1. 生成 session_id
2. 创建 blackboard 目录
3. 生成所有 Worker Tasks
4. （由主Agent）使用 sessions_spawn 创建 Workers

禁止：直接调用 openclaw
"""

import sys
import os
import json
import uuid

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"
sys.path.insert(0, DEEPFLOW_BASE)

from domains.solution.task_builder import (
    build_data_collection_task,
    build_planner_task,
    build_researcher_task,
    build_designer_task,
    build_auditor_task,
    build_fixer_task,
    build_fixer_task_with_audit,
    build_deliver_task
)


class SolutionOrchestratorV2:
    """Solution Orchestrator V2.0 - 纯调度"""
    
    def __init__(self, topic: str, solution_type: str = "architecture",
                 mode: str = "standard", constraints: list = None,
                 stakeholders: list = None):
        self.topic = topic
        self.solution_type = solution_type
        self.mode = mode
        self.constraints = constraints or []
        self.stakeholders = stakeholders or []
        self.session_id = None
        self.base_path = None
    
    def init(self) -> str:
        """初始化 session"""
        import hashlib
        topic_hash = hashlib.md5(self.topic.encode()).hexdigest()[:8]
        self.session_id = f"{self.topic[:20]}_{self.solution_type}_{topic_hash}"
        self.base_path = f"{DEEPFLOW_BASE}/blackboard/{self.session_id}"
        
        os.makedirs(f"{self.base_path}/data", exist_ok=True)
        os.makedirs(f"{self.base_path}/stages", exist_ok=True)
        
        print(f"[SolutionOrchestratorV2] Session: {self.session_id}")
        return self.session_id
    
    def get_all_tasks(self) -> dict:
        """获取所有 Worker Tasks"""
        # 根据 mode 确定 pipeline
        if self.mode == "quick":
            pipeline = ["planning", "design", "deliver"]
        else:
            pipeline = ["data_collection", "planning", "research", "design", 
                       "audit", "fix", "deliver"]
        
        tasks = {}
        
        for stage in pipeline:
            if stage == "data_collection":
                tasks[stage] = build_data_collection_task(
                    self.session_id, self.topic, self.constraints
                )
            elif stage == "planning":
                tasks[stage] = build_planner_task(
                    self.session_id, self.topic, self.solution_type, 
                    self.constraints, self.stakeholders
                )
            elif stage == "research":
                # 动态生成 researcher tasks（修复 P0-001, P0-002）
                experts = [
                    {
                        "id": "expert_1",
                        "name": "技术架构专家",
                        "angle": "高并发系统架构与性能优化",
                        "reason": "日均百万订单需要分析 QPS、延迟、吞吐量，设计缓存、异步、分库分表策略"
                    },
                    {
                        "id": "expert_2",
                        "name": "业务分析专家",
                        "angle": "电商业务流程与领域模型设计",
                        "reason": "订单系统涉及复杂业务规则，需要分析订单生命周期、状态机、业务约束"
                    },
                    {
                        "id": "expert_3",
                        "name": "风险评估专家",
                        "angle": "系统风险识别与容错设计",
                        "reason": "99.99%可用性要求需要识别单点故障、级联故障、数据一致性等风险"
                    }
                ]
                tasks[stage] = {}
                for expert in experts:
                    tasks[stage][expert["id"]] = build_researcher_task(
                        expert["name"], self.session_id, self.topic,
                        {"type": self.solution_type, "constraints": self.constraints},
                        expert_id=expert["id"],
                        angle=expert["angle"],
                        reason=expert["reason"]
                    )
            elif stage == "design":
                tasks[stage] = build_designer_task(
                    self.session_id, self.topic,
                    {"type": self.solution_type, "constraints": self.constraints}
                )
            elif stage == "audit":
                tasks[stage] = build_auditor_task(
                    self.session_id, self.topic,
                    {"type": self.solution_type, "constraints": self.constraints}
                )
            elif stage == "fix":
                # P0 Fix: Fixer 需要读取 audit.json 作为输入
                audit_path = f"{self.base_path}/stages/audit.json"
                tasks[stage] = build_fixer_task_with_audit(
                    self.session_id, self.topic, audit_path
                )
            elif stage == "deliver":
                tasks[stage] = build_deliver_task(
                    self.session_id, self.topic,
                    {"type": self.solution_type}
                )
        
        return tasks
    
    def save_execution_plan(self):
        """保存执行计划"""
        tasks = self.get_all_tasks()
        
        # 构建 phases
        phases = []
        for stage_name, task in tasks.items():
            if isinstance(task, dict):
                # 并行阶段（如 research）
                phases.append({
                    "phase": len(phases) + 1,
                    "stage": stage_name,
                    "workers": list(task.keys()),
                    "parallel": True,
                    "timeout": 300
                })
            else:
                # 串行阶段
                phases.append({
                    "phase": len(phases) + 1,
                    "stage": stage_name,
                    "worker": stage_name,
                    "parallel": False,
                    "timeout": 300
                })
        
        plan = {
            "session_id": self.session_id,
            "topic": self.topic,
            "solution_type": self.solution_type,
            "mode": self.mode,
            "version": "2.0",
            "phases": phases
        }
        
        plan_path = f"{self.base_path}/execution_plan.json"
        with open(plan_path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        
        return plan
    
    def save_tasks(self):
        """保存所有 tasks"""
        tasks = self.get_all_tasks()
        tasks_path = f"{self.base_path}/tasks.json"
        with open(tasks_path, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        return tasks


def main():
    """入口"""
    orch = SolutionOrchestratorV2(
        topic="设计一个支持百万日订单的电商订单系统",
        solution_type="architecture",
        mode="standard",
        constraints=["日均百万订单", "99.99%可用性", "<200ms响应时间"],
        stakeholders=["技术团队", "产品团队", "运维团队"]
    )
    session_id = orch.init()
    tasks = orch.get_all_tasks()
    plan = orch.save_execution_plan()
    orch.save_tasks()
    print(f"\n✅ Solution Orchestrator V2.0 初始化完成")
    print(f"   Session: {session_id}")
    print(f"   Tasks: {len(tasks)} stages")
    return session_id, tasks


if __name__ == "__main__":
    main()
