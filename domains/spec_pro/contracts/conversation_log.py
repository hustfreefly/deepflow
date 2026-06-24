"""
ConversationLog Pydantic 模型

对话日志。
"""

from typing import Optional, Union
from pydantic import BaseModel, Field


class ConversationRound(BaseModel):
    """单轮对话"""
    round: int
    timestamp: str = ""
    phase: str = "collecting"
    questions: list[dict] = Field(default_factory=list)
    user_response: str = ""
    parsed_updates_summary: str = ""
    quality_before: Union[int, float] = 0
    quality_after: Union[int, float] = 0
    quality_delta: Union[int, float] = 0
    inferences_created: int = 0
    inferences_confirmed: int = 0
    inferences_rejected: int = 0
    meta_directives: list[str] = Field(default_factory=list)
    stop_asking_dimensions: list[str] = Field(default_factory=list)


class ConversationLog(BaseModel):
    """对话日志"""
    rounds: list[ConversationRound] = Field(default_factory=list)
