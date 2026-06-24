"""Loop Engine Contracts — Pydantic 契约笼子

所有 Loop Engine 的核心数据结构都通过 Pydantic 模型定义。
LLM 输出必须过这些模型验证，格式不对就报错。
"""

from .goal import Goal, GoalConstraint, GoalEvidence, GoalStatus, GoalEvolution
from .task_dag import Task, TaskDAG, TaskStatus, TaskDependency
from .loop_state import LoopState, LoopConfig, LoopPhase, LoopIteration
from .worker import WorkerAllocation, WorkerResult, WorkerType
from .error import ErrorReport, RecoveryAction, RecoveryStrategy
from .heartbeat import HeartbeatConfig, HeartbeatPulse, PulseLevel
from .dream import DreamResult, PatternExtraction, SkillProposal
from .meta import MetaAnalysis, LoopMetrics, ParameterAdjustment

__all__ = [
    # Goal
    "Goal", "GoalConstraint", "GoalEvidence", "GoalStatus", "GoalEvolution",
    # Task DAG
    "Task", "TaskDAG", "TaskStatus", "TaskDependency",
    # Loop State
    "LoopState", "LoopConfig", "LoopPhase", "LoopIteration",
    # Worker
    "WorkerAllocation", "WorkerResult", "WorkerType",
    # Error
    "ErrorReport", "RecoveryAction", "RecoveryStrategy",
    # Heartbeat
    "HeartbeatConfig", "HeartbeatPulse", "PulseLevel",
    # Dream
    "DreamResult", "PatternExtraction", "SkillProposal",
    # Meta
    "MetaAnalysis", "LoopMetrics", "ParameterAdjustment",
]
