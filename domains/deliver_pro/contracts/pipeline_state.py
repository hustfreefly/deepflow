"""
PipelineState — Deliver Pro 流水线状态。

对标 Solution Pro 的 SolutionProPipelineState。
单一真相源：delivery_state.json。
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class PipelinePhase(str, Enum):
    """流水线阶段枚举。"""

    INIT = "INIT"
    ANALYZING = "ANALYZING"
    GENERATING = "GENERATING"
    WORKER_RETRY = "WORKER_RETRY"
    INTEGRATING = "INTEGRATING"
    VALIDATING = "VALIDATING"
    FIX_LOOP = "FIX_LOOP"
    PACKAGING = "PACKAGING"
    COMPLETED = "COMPLETED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


# 合法的状态转换
VALID_TRANSITIONS: dict[PipelinePhase, list[PipelinePhase]] = {
    PipelinePhase.INIT: [PipelinePhase.ANALYZING, PipelinePhase.FAILED],
    PipelinePhase.ANALYZING: [PipelinePhase.GENERATING, PipelinePhase.FAILED],
    PipelinePhase.GENERATING: [
        PipelinePhase.WORKER_RETRY,
        PipelinePhase.INTEGRATING,
        PipelinePhase.FAILED,
    ],
    PipelinePhase.WORKER_RETRY: [
        PipelinePhase.GENERATING,
        PipelinePhase.INTEGRATING,
        PipelinePhase.FAILED,
    ],
    PipelinePhase.INTEGRATING: [PipelinePhase.VALIDATING, PipelinePhase.FAILED],
    PipelinePhase.VALIDATING: [
        PipelinePhase.FIX_LOOP,
        PipelinePhase.PACKAGING,
        PipelinePhase.FAILED,
    ],
    PipelinePhase.FIX_LOOP: [PipelinePhase.VALIDATING, PipelinePhase.FAILED],
    PipelinePhase.PACKAGING: [PipelinePhase.COMPLETED, PipelinePhase.DELIVERED, PipelinePhase.FAILED],
    PipelinePhase.COMPLETED: [],  # terminal
    PipelinePhase.DELIVERED: [],  # terminal (successful delivery)
    PipelinePhase.FAILED: [PipelinePhase.INIT],  # can retry from start
}


class PipelineState(BaseModel):
    """
    Deliver Pro 流水线状态。

    持久化为 delivery_state.json，是流水线的单一真相源。
    """

    wp_id: str = Field(description="WP ID")
    phase: PipelinePhase = Field(default=PipelinePhase.INIT)
    completed_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    pending_tasks: list[str] = Field(default_factory=list)
    running_tasks: list[str] = Field(default_factory=list)
    round_count: int = Field(default=0, description="Validate Loop 当前轮次")
    max_rounds: int = Field(default=5, description="Validate Loop 最大轮次")
    validation_score: Optional[float] = None
    last_verdict: Optional[str] = None
    error: Optional[str] = None
    started_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )
    completed_at: Optional[str] = None

    def transition_to(self, new_phase: PipelinePhase, *, force: bool = False) -> None:
        """
        状态记录（V3: 降级为 append-only 日志语义，不再作为决策门禁）。

        V3 变更：不再对"非法转换"raise ValueError。
        phase 决策一律通过 phase_deriver 从文件系统推导；
        本方法仅维护 progress log 中的 phase 字段（可观测性用途）。

        Args:
            new_phase: 目标阶段
            force: 保留参数，兼容旧调用（已无实际作用）
        """
        if new_phase == self.phase:
            return
        allowed = VALID_TRANSITIONS.get(self.phase, [])
        if new_phase not in allowed:
            # V3: 不 raise，仅记录。文件系统才是真相。
            logger.warning(
                f"Non-standard transition (log only): "
                f"{self.phase.value} → {new_phase.value}"
            )
        self.phase = new_phase
        self.updated_at = datetime.now().isoformat()
        if new_phase in (PipelinePhase.COMPLETED, PipelinePhase.DELIVERED):
            self.completed_at = datetime.now().isoformat()

    @property
    def is_terminal(self) -> bool:
        """是否处于终态。"""
        return self.phase in (PipelinePhase.COMPLETED, PipelinePhase.DELIVERED, PipelinePhase.FAILED)

    @property
    def can_continue_validate(self) -> bool:
        """是否可以继续 Validate Loop。"""
        return (
            self.phase == PipelinePhase.VALIDATING
            and self.round_count < self.max_rounds
        )

    def mark_task_completed(self, task_id: str) -> None:
        """标记任务完成。"""
        if task_id in self.pending_tasks:
            self.pending_tasks.remove(task_id)
        if task_id in self.running_tasks:
            self.running_tasks.remove(task_id)
        if task_id not in self.completed_tasks:
            self.completed_tasks.append(task_id)
        self.updated_at = datetime.now().isoformat()

    def mark_task_failed(self, task_id: str) -> None:
        """标记任务失败。"""
        if task_id in self.pending_tasks:
            self.pending_tasks.remove(task_id)
        if task_id in self.running_tasks:
            self.running_tasks.remove(task_id)
        if task_id not in self.failed_tasks:
            self.failed_tasks.append(task_id)
        self.updated_at = datetime.now().isoformat()
