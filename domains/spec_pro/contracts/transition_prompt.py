"""
过渡引导词 Pydantic 模型

用于 Spec Pro → Solution Pro、Solution Pro → Ship Pro、Ship Pro 完成三个过渡点的引导词数据验证。

设计原则：
1. 数据生成 vs 展示渲染分离
2. 使用 quality.level（S/A/B/C）而非硬编码阈值
3. 所有字段可选（Optional），适应不同过渡点的数据需求
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class TransitionPromptVariables(BaseModel):
    """过渡引导词变量
    
    不同过渡点使用不同的变量子集：
    - spec_to_solution: quality_score, quality_level, num_users, num_capabilities, num_constraints
    - solution_to_ship: harness_score, num_reqs, num_modules
    - ship_completed: harness_score
    """
    # Spec Pro → Solution Pro 变量
    quality_score: Optional[int] = Field(None, description="Spec Pro 质量评分（0-100）")
    quality_level: Optional[Literal["S", "A", "B", "C"]] = Field(None, description="Spec Pro 质量等级")
    num_users: Optional[int] = Field(None, description="用户角色数量", ge=0)
    num_capabilities: Optional[int] = Field(None, description="核心能力数量", ge=0)
    num_constraints: Optional[int] = Field(None, description="约束条件数量", ge=0)
    
    # Solution Pro → Ship Pro 变量
    harness_score: Optional[int] = Field(None, description="Harness 质量评分（0-100）")
    num_reqs: Optional[int] = Field(None, description="需求项数量", ge=0)
    num_modules: Optional[int] = Field(None, description="模块数量", ge=0)
    
    class Config:
        extra = "allow"  # 允许额外字段，保持向后兼容


class TransitionPrompt(BaseModel):
    """过渡引导词数据
    
    数据生成层（worker/watcher）生成此结构，
    展示渲染层（主 Agent）读取后渲染为用户可见的引导词。
    """
    template: Literal["spec_to_solution", "solution_to_ship", "ship_completed"] = Field(
        ..., description="引导词模板标识"
    )
    variables: TransitionPromptVariables = Field(
        ..., description="模板变量"
    )
    
    class Config:
        extra = "allow"  # 允许额外字段，保持向后兼容


def validate_transition_prompt(data: dict) -> TransitionPrompt:
    """验证过渡引导词数据
    
    Args:
        data: 过渡引导词数据字典
        
    Returns:
        验证通过的 TransitionPrompt 模型
        
    Raises:
        ValidationError: 数据不符合 schema
    """
    return TransitionPrompt(**data)
