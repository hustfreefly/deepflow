"""Pulse Report — 脉冲调度 IPC 契约（契约笼子）。

设计原则（2026-07-24 评审裁决）：
- extra="forbid"：未知字段直接 ValidationError，不静默吞掉
- min_length/gt/ge 约束：空字符串、负数值 = 契约违反
- pulse() 写入 _pulse_actions.json 前必须通过 model_validate
- pulse_cli 读取时同样验证（防御文件损坏/手工篡改）

数据流：
    DeliverOrchestrator.pulse() → PulseReport → _pulse_actions.json
    → pulse Agent (LLM) 读取 → sessions_spawn → confirm CLI 回执
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PulseAction(BaseModel):
    """一条待 spawn 动作（pulse agent 逐条执行）。"""

    model_config = ConfigDict(extra="forbid")

    wp_id: str = Field(min_length=1)
    action: Literal[
        "analyze", "spawn_workers", "validate", "package", "package_failed",
        "infer_deliverable_contract", "final_synthesis", "run_final_gate",
    ]
    task: str = Field(min_length=1, description="sessions_spawn 的 task 内容")
    label: str = Field(min_length=1, description="sessions_spawn 的 label")
    model: str | None = None
    mode: str = "run"
    thinking: str = "medium"


class PulseAlert(BaseModel):
    """告警（pulse agent 据此发飞书消息）。"""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["INFO", "WARN", "CRITICAL"]
    code: str = Field(
        min_length=1,
        description="STALLED | TERMINAL_FAILED | LOCK_STALE | TASK_RETRY_EXHAUSTED | "
        "TASK_RETRY | IN_FLIGHT_CAP | SPAWN_ROLLBACK | PACKAGING_STUCK",
    )
    message: str = Field(min_length=1)


class PulseSummary(BaseModel):
    """脉冲摘要（一行汇报的数据源）。"""

    model_config = ConfigDict(extra="forbid")

    total_wps: int = Field(ge=0)
    completed: int = Field(ge=0)
    terminal_failed: int = Field(ge=0)
    in_progress: int = Field(ge=0)
    in_flight: int = Field(ge=0, description="当前在途 agent 数（A5）")
    zero_progress_count: int = Field(ge=0, description="连续零进展 pulse 数（A7）")
    truncated: bool = Field(default=False, description="本次是否因并发上限截断（A5）")


class PulseReport(BaseModel):
    """_pulse_actions.json 的顶层契约。"""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    pulse_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    generated_at: float = Field(gt=0)
    status: Literal["active", "idle", "locked", "completed"]
    actions: list[PulseAction] = Field(default_factory=list)
    alerts: list[PulseAlert] = Field(default_factory=list)
    summary: PulseSummary


class SpawnConfirmation(BaseModel):
    """confirm CLI 的单条回执（A4 两阶段 dispatch / P1-1 回滚）。"""

    model_config = ConfigDict(extra="forbid")

    wp_id: str = Field(min_length=1)
    label: str = Field(min_length=1, description="spawn 时使用的 label")
    ok: bool
    error: str | None = None
