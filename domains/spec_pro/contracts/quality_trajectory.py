"""
QualityTrajectory Pydantic 模型

质量轨迹。
"""

from typing import Union
from pydantic import BaseModel, Field


class TrajectoryPoint(BaseModel):
    """轨迹点"""
    round: int
    overall_score: Union[int, float]
    level: str = ""
    dimension_scores: dict = Field(default_factory=dict)
    delta: Union[int, float] = 0
    questions_asked: int = 0
    inferences_validated: int = 0


class QualityTrajectory(BaseModel):
    """质量轨迹"""
    scores: list[Union[int, float]] = Field(default_factory=list)
    trajectory: list[TrajectoryPoint] = Field(default_factory=list)
