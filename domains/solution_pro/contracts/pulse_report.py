"""Solution Pulse Report — Solution Pro 脉冲调度 IPC 契约（契约笼子）。

参照 Deliver Pro Pulse V1（contracts/pulse_report.py），适配 Solution Pro
3 模块顺序流水线（planning → research → summary → validate → review → finalize）。

设计原则：
- extra="forbid"：未知字段直接 ValidationError，不静默吞掉
- min_length/gt/ge 约束：空字符串、负数值 = 契约违反
- pulse() 写入 _solution_pulse_actions.json 前必须通过 model_validate
- confirm CLI 逐条验证（单条格式错误不拖垮整批）

数据流：
    SolutionPulse.pulse() → SolutionPulseReport → _solution_pulse_actions.json
    → pulse Agent (LLM) 读取 → sessions_spawn → confirm CLI 回执
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 流水线相位（严格顺序）
PHASES = ("planning", "research", "summary", "validate", "review", "finalize")

# 模块完成判定所需的输出 stage（全部存在才算完成）
MODULE_REQUIRED_STAGES: dict[str, tuple[str, ...]] = {
    "planning": ("planning_convergence",),
    "research": ("research_digest",),
    "summary": ("solution_document", "final_solution"),
}

# review 相位的两个并行审查 Agent（非门控，失败不阻断）
REVIEW_AGENTS = ("adversarial_reviewer", "consistency_checker")


class SolutionPulseAction(BaseModel):
    """一条待 spawn 动作（pulse agent 逐条执行）。"""

    model_config = ConfigDict(extra="forbid")

    module: str = Field(min_length=1, description="目标相位/模块名")
    action: Literal["spawn_module", "spawn_reviewer"]
    task: str = Field(min_length=1, description="sessions_spawn 的 task 内容")
    label: str = Field(min_length=1, description="sessions_spawn 的 label")
    mode: str = "run"


class SolutionPulseAlert(BaseModel):
    """告警（pulse agent 据此发飞书消息）。"""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["INFO", "WARN", "CRITICAL"]
    code: str = Field(
        min_length=1,
        description="MODULE_STALLED | MODULE_RETRY | TERMINAL_FAILED | LOCK_STALE | "
        "POST_VALIDATION_FAILED | REVIEW_TIMEOUT | ZERO_PROGRESS | SPAWN_ROLLBACK",
    )
    message: str = Field(min_length=1)


class SolutionPulseSummary(BaseModel):
    """脉冲摘要（一行汇报的数据源）。"""

    model_config = ConfigDict(extra="forbid")

    current_phase: str = Field(min_length=1)
    completed_modules: list[str] = Field(default_factory=list)
    in_flight: int = Field(ge=0, description="当前在途 module/reviewer agent 数")
    retry_counts: dict[str, int] = Field(default_factory=dict)
    zero_progress_count: int = Field(ge=0)


class SolutionPulseReport(BaseModel):
    """_solution_pulse_actions.json 的顶层契约。"""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    pulse_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    generated_at: float = Field(gt=0)
    status: Literal["active", "idle", "locked", "completed", "failed"]
    actions: list[SolutionPulseAction] = Field(default_factory=list)
    alerts: list[SolutionPulseAlert] = Field(default_factory=list)
    summary: SolutionPulseSummary


class SpawnConfirmation(BaseModel):
    """confirm CLI 的单条回执（两阶段 dispatch / 失败回滚）。"""

    model_config = ConfigDict(extra="forbid")

    module: str = Field(min_length=1)
    label: str = Field(min_length=1, description="spawn 时使用的 label")
    ok: bool
    error: str | None = None


class ModuleDispatch(BaseModel):
    """单个模块/审查员的 dispatch 状态（写入 _solution_pulse_state.json）。"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "dispatched", "completed", "terminal_failed"] = "pending"
    retry_count: int = Field(default=0, ge=0)
    label: str | None = None
    last_spawned_at: float | None = None
    dispatch_confirmed: bool = False
    completed_at: float | None = None


class SolutionPulseState(BaseModel):
    """_solution_pulse_state.json 的顶层契约（pulse 的唯一可变状态）。"""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    session_id: str = Field(min_length=1)
    phase: Literal[
        "planning", "research", "summary", "validate", "review", "finalize",
        "completed", "failed",
    ] = "planning"
    modules: dict[str, ModuleDispatch] = Field(default_factory=dict)
    review: dict[str, ModuleDispatch] = Field(default_factory=dict)
    zero_progress_count: int = Field(default=0, ge=0)
    last_progress_at: float | None = None
    fail_reason: str | None = None
    created_at: float = Field(gt=0)
    updated_at: float = Field(gt=0)
