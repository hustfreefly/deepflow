"""
ExecutionPlan — Phase 1 Analyze Agent 的输出。

定义任务图（DAG）、并发计划、质量门禁。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TaskNode(BaseModel):
    """任务图中的单个节点。"""

    task_id: str = Field(description="Task ID, e.g. 'T-001'")
    title: str = Field(description="任务标题")
    description: str = Field(default="", description="任务详细描述")
    scenario_type: Literal["code", "report"] = Field(
        default="code",
        description="场景类型: code | report",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="依赖的 task_id 列表",
    )
    estimated_complexity: str = Field(
        default="medium",
        description="预估复杂度: low | medium | high",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="该任务的验收标准",
    )
    expected_outputs: list[dict] = Field(
        default_factory=list,
        description="预期产出 [{path, type}]",
    )
    forced_actions: list[str] = Field(
        default_factory=list,
        description="必须执行的动作列表",
    )
    suggested_model: Optional[str] = Field(
        default=None,
        description="推荐模型（如 qwen3.7-plus）",
    )
    timeout_seconds: int = Field(
        default=300,
        description="Worker 超时秒数（默认 300s = 5min）",
    )


class Wave(BaseModel):
    """并发执行的一波任务。"""

    wave: int = Field(description="波次编号，从 1 开始")
    task_ids: list[str] = Field(description="该波次的 task_id 列表")


class ConcurrencyPlan(BaseModel):
    """并发执行计划。"""

    suggested_parallelism: int = Field(
        default=3,
        description="建议并发数",
        ge=1,
        le=10,
    )
    safety_cap: int = Field(
        default=8,
        description="安全上限（最大并发数）",
        ge=1,
        le=20,
    )
    waves: list[Wave] = Field(
        default_factory=list,
        description="分波次执行计划",
    )


class ExecutionPlan(BaseModel):
    """
    Phase 1 Analyze Agent 的输出。

    包含任务图（DAG）、并发计划、质量门禁。
    """

    schema_version: str = Field(default="1.0.0")
    wp_id: str = Field(description="对应的 WP ID")
    scenario: Literal["code", "report", "mixed"] = Field(
        description="场景类型: code | report | mixed",
    )
    task_graph: list[TaskNode] = Field(
        description="任务图（必须是无环 DAG）",
    )
    concurrency_plan: ConcurrencyPlan = Field(
        default_factory=ConcurrencyPlan,
        description="并发执行计划",
    )
    glossary: dict = Field(
        default_factory=dict,
        description="共享术语表（报告场景）",
    )
    quality_gates: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "code": ["lint_pass", "test_pass"],
            "report": ["data_verified", "source_cited"],
        },
        description="质量门禁规则",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="风险标记",
    )

    @field_validator("task_graph")
    @classmethod
    def validate_dag(cls, tasks: list[TaskNode]) -> list[TaskNode]:
        """验证任务图是无环 DAG。"""
        task_ids = {t.task_id for t in tasks}
        for task in tasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    raise ValueError(
                        f"Task {task.task_id} depends on unknown task {dep}"
                    )

        # 检测环
        visited = set()
        in_stack = set()

        def has_cycle(tid: str) -> bool:
            if tid in in_stack:
                return True
            if tid in visited:
                return False
            visited.add(tid)
            in_stack.add(tid)
            task = next(t for t in tasks if t.task_id == tid)
            for dep in task.depends_on:
                if has_cycle(dep):
                    return True
            in_stack.remove(tid)
            return False

        for task in tasks:
            if has_cycle(task.task_id):
                raise ValueError("Task graph contains a cycle (not a DAG)")

        return tasks

    @property
    def root_tasks(self) -> list[TaskNode]:
        """获取无依赖的根任务。"""
        return [t for t in self.task_graph if not t.depends_on]

    @property
    def task_count(self) -> int:
        """任务总数。"""
        return len(self.task_graph)

    def get_task(self, task_id: str) -> TaskNode | None:
        """按 ID 获取任务。"""
        return next((t for t in self.task_graph if t.task_id == task_id), None)

    def get_ready_tasks(self, completed: set[str]) -> list[TaskNode]:
        """获取依赖已满足、可以执行的任务。"""
        return [
            t
            for t in self.task_graph
            if t.task_id not in completed
            and all(dep in completed for dep in t.depends_on)
        ]
