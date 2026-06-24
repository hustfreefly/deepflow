"""
RoundResult Pydantic 模型

每轮评分和问题输出。
"""

from typing import Optional, Union, Literal
from pydantic import BaseModel, Field


class DimensionScores(BaseModel):
    """维度分数（dict 格式：key=维度名, value={score, delta, change}）"""
    objective: Optional[dict] = None
    users: Optional[dict] = None
    capabilities: Optional[dict] = None
    quality_attributes: Optional[dict] = None
    constraints: Optional[dict] = None
    integration: Optional[dict] = None
    risks: Optional[dict] = None


class Quality(BaseModel):
    """质量评估"""
    overall_score: Union[int, float]
    level: str
    dimension_scores: DimensionScores = Field(default_factory=DimensionScores)
    top_improvements: list[Union[dict, str]] = Field(default_factory=list)
    top_missing: list[str] = Field(default_factory=list)


class Question(BaseModel):
    """引导问题"""
    type: str
    text: str
    dimension: str = ""
    boundary_check: str = "demand"
    priority: str = "medium"
    is_inference_validation: bool = False
    inference_id: Optional[str] = None


class RoundResult(BaseModel):
    """轮次结果"""
    action: Literal["questions", "summary", "proposal", "done", "safety_stop"]
    round: int = 1
    questions: list[Question] = Field(default_factory=list)
    quality: Quality
    inferred_items: list[Union[dict, str]] = Field(default_factory=list)
    summary_text: Optional[str] = None
    proposal_text: Optional[str] = None
