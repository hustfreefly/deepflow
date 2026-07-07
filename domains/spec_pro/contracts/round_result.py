"""
RoundResult Pydantic 模型

每轮评分和问题输出。
"""

from typing import Any, Dict, Optional, Union, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    model_config = ConfigDict(populate_by_name=True)

    type: str
    text: str
    dimension: str = ""
    boundary_check: str = "demand"
    priority: str = Field(default="medium", alias="importance", description="问题优先级 high/medium/low")
    reasoning: str = Field(default="", description="为什么问这个问题")
    boundary_reasoning: str = Field(default="", description="需求vs设计边界判定理由")
    id: str = Field(default="", description="问题ID如Q-01-1")
    is_inference_validation: bool = False
    inference_id: Optional[str] = None


class RoundResult(BaseModel):
    """轮次结果"""
    action: Literal["questions", "summary", "proposal", "done", "safety_stop", "error"]
    round: int = 1
    questions: list[Question] = Field(default_factory=list)
    quality: Quality
    inferred_items: list[Union[dict, str]] = Field(default_factory=list)
    summary_text: Optional[str] = None
    proposal_text: Optional[str] = None
    # Fix 2: 补全 6 个缺失字段，使 action="done" 时的 round_result 完整记录产出
    living_spec: Optional[Dict[str, Any]] = Field(default=None, description="最终 Living Spec 快照")
    harness_report: Optional[Dict[str, Any]] = Field(default=None, description="Harness 质量门控报告")
    route_recommendation: Optional[Dict[str, Any]] = Field(default=None, description="路由建议（dict 格式）")
    solution_pro_hints: Optional[Dict[str, Any]] = Field(default=None, description="Solution Pro 上下文提示")
    transition_prompt: Optional[Union[str, dict]] = Field(default=None, description="过渡提示（string 或 dict 格式）")
    handoff_package_path: Optional[str] = Field(default=None, description="Handoff 包文件路径")

    @field_validator('transition_prompt', mode='before')
    @classmethod
    def coerce_transition_prompt(cls, v):
        if v is None:
            return None
        if isinstance(v, dict):
            return v  # 保留 dict 格式
        if isinstance(v, str):
            return v  # 保留 string 格式
        raise ValueError(f"transition_prompt must be str or dict, got {type(v).__name__}: {v}")
