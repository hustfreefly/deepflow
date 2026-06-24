"""
QualityReport Pydantic 模型

质量评估报告。
"""

from typing import Union
from pydantic import BaseModel, Field


class Dimension(BaseModel):
    """单维度评分"""
    dimension: str
    score: Union[int, float]
    weight: Union[int, float] = 0.15
    reasoning: str = ""
    missing_items: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    """质量报告"""
    overall_score: Union[int, float]
    level: str
    dimensions: list[Dimension] = Field(default_factory=list)
    top_missing: list[str] = Field(default_factory=list)
    recommendation: str = ""
