"""
FixContext 契约 — Judge → Generator 的修复上下文

在 V4.0 闭环中，当 Judge 裁定 verdict != "pass" 时，
将 Judge 的输出转换为 FixContext 传递给 Generator 进行定向修复。

V4.0 架构: Generator + Judge 两阶段闭环。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FixInstruction(BaseModel):
    """单条修复指令"""

    risk_id: str
    severity: Literal["critical", "major", "minor"]
    fix_suggestion: str
    affected_stages: list[str]


class FixRoundResult(BaseModel):
    """单轮修复结果"""

    round: int
    fixed_risk_ids: list[str] = Field(default_factory=list)
    new_risk_ids: list[str] = Field(default_factory=list)
    unresolved_risk_ids: list[str] = Field(default_factory=list)


class FixContext(BaseModel):
    """
    传递给 Generator 的修复上下文

    当 Judge 裁定 fail/conditional 时，构造 FixContext 传递给 Generator，
    约束 Generator 在下一轮只修复指定问题，不引入新问题。
    """

    original_verdict: Literal["fail", "conditional"]
    current_round: int = Field(ge=1, le=3)
    max_rounds: int = 3
    instructions: list[FixInstruction] = Field(default_factory=list)
    history: list[FixRoundResult] = Field(default_factory=list)

    # 约束：本轮只修复 instructions 中的问题，不要引入新问题
    focus_areas: list[str] = Field(default_factory=list)
    regression_warnings: list[str] = Field(
        default_factory=list,
        description="上轮修复后回退的问题，本轮必须避免",
    )


__all__ = [
    "FixInstruction",
    "FixRoundResult",
    "FixContext",
]
