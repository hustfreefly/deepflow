"""
RecoveryAction / WorkerError — Worker 故障恢复相关数据结构。

AI Native 设计：LLM 端到端诊断，不预定义故障类型（废除 F1-F8）。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RecoveryStrategy(str, Enum):
    """恢复策略枚举（LLM 输出，非查表）。"""

    RETRY = "retry"  # 原样重试
    SWITCH_MODEL = "switch_model"  # 换模型
    SPLIT_WP = "split_wp"  # 拆分任务
    SIMPLIFY = "simplify"  # 简化任务
    ADD_CONTEXT = "add_context"  # 补充上下文
    SKIP = "skip"  # 跳过（标记 FAILED）


class WorkerError(BaseModel):
    """Worker 执行错误。"""

    task_id: str
    error_type: str = Field(
        description="错误类型（LLM 分类，非硬编码）",
    )
    message: str = Field(description="错误信息")
    context: dict = Field(
        default_factory=dict,
        description="错误上下文（model, timeout, attempts 等）",
    )
    recovery_history: list[dict] = Field(
        default_factory=list,
        description="已尝试的恢复策略 [{round, action, result}]",
    )


class RecoveryAction(BaseModel):
    """
    LLM 生成的恢复动作。

    Orchestrator 调用 LLM 诊断 WorkerError，得到 RecoveryAction。
    """

    task_id: str
    diagnosis: str = Field(description="LLM 的诊断结果")
    recovery_action: RecoveryStrategy = Field(
        description="恢复策略",
    )
    specific_changes: str = Field(
        description="具体的修改建议",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="LLM 对恢复方案的信心度",
    )
    suggested_model: Optional[str] = Field(
        default=None,
        description="换模型时的推荐模型",
    )

    @property
    def should_retry(self) -> bool:
        """是否应该重试。"""
        return self.recovery_action != RecoveryStrategy.SKIP
