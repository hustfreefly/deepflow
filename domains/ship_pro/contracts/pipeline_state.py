"""
管线状态契约 — 单一状态文件 (pipeline_state.json)

所有状态变更必须通过 run_pipeline.py update-status CLI，禁止直接写文件。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """单个 Agent 的执行状态。"""

    state: Literal[
        "pending",
        "running",
        "gate_pass",
        "gate_conditional",
        "gate_fail",
        "skipped",
        "done",
    ] = "pending"
    retry_count: int = 0
    max_retries: int = 2
    gate_decision: Optional[str] = None
    last_gate_feedback: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class PipelineState(BaseModel):
    """
    管线统一状态。

    这是唯一的状态文件 (pipeline_state.json)。
    所有更新必须通过 `run_pipeline.py update-status` CLI。
    """

    run_id: str
    session_id: str = ""
    status: Literal["preparing", "running", "completed", "failed"] = "preparing"
    current_agent: Optional[str] = None
    agents: dict[str, AgentState] = Field(default_factory=dict)
    started_at: str = ""
    completed_at: Optional[str] = None
    skipped_agents: list[str] = Field(default_factory=list)


__all__ = ["PipelineState", "AgentState"]
