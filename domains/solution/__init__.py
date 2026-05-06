"""
Solution Pro - 纯Prompt驱动的11阶段方案设计管线

使用方式（主Agent执行）:
    from domains.solution import SolutionOrchestratorV2
    
    # 方式1: 使用静态异步方法（推荐）
    result = await SolutionOrchestratorV2.run(
        topic="设计一个支持百万日订单的电商订单系统",
        solution_type="architecture",
        mode="standard",
        constraints=["日均百万订单", "99.99%可用性"],
        stakeholders=["技术团队", "产品团队", "运维团队"]
    )
    
    # 方式2: 手动初始化（主Agent直接spawn Workers执行11阶段管线）
    orch = SolutionOrchestratorV2(
        topic="...",
        solution_type="architecture",
        constraints=[...],
        stakeholders=[...]
    )
    session_id = orch.init()
    tasks = orch.get_all_tasks()
    
    # 然后主Agent使用 sessions_spawn 触发11阶段管线
    sessions_spawn(
        runtime="subagent",
        mode="run",
        task=f"执行Solution Pro 11阶段管线，Session: {session_id}",
        timeout_seconds=3600
    )
"""

from .config import SolutionConfig
from .blackboard import BlackboardManager
from .orchestrator_agent import SolutionOrchestratorV21

# 向后兼容：V2指向V21
SolutionOrchestratorV2 = SolutionOrchestratorV21

__all__ = ['SolutionConfig', 'BlackboardManager', 'SolutionOrchestratorV21', 'SolutionOrchestratorV2']
