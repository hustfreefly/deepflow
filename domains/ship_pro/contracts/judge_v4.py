"""
Judge Agent V4.0 输出契约 — 唯一真相源

替代 V3.1 的 Reviewer，增强:
- AC 质量维度检查
- 回归检测（第 2+ 轮检查上轮修复是否回退）
- fixable 标记（Fixer 能否修复）
- 可消费性评分

V4.0 架构: Generator + Judge 两阶段闭环。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JudgeRisk(BaseModel):
    """单个风险条目"""

    id: str
    severity: Literal["critical", "major", "minor"]
    description: str
    affected_stages: list[str] = Field(default_factory=list)
    fix_suggestion: str = ""
    fixable: bool = True  # 新增：Fixer 能否修复


class JudgeMeta(BaseModel):
    """Judge 输出元数据"""

    agent: Literal["judge"] = "judge"
    round: int = 1
    stance: str = ""
    model_id: str = ""
    timestamp: str = ""


class JudgeOutput(BaseModel):
    """
    Judge V4.0 输出（增强：AC质量 + 回归检查 + fixable 标记 + 量化评分）

    Judge 替代 V3.1 的 Reviewer，在原有评审基础上增加:
    - overall_score: 量化总分（0-100），用于 verdict 决策
    - ac_quality: AC 质量维度评分
    - regressions: 回归检测（第 2+ 轮）
    - consumability_score: 可消费性评分
    - risks[].fixable: Fixer 能否修复的标记
    """

    _meta: JudgeMeta
    verdict: Literal["pass", "fail", "conditional"]
    overall_score: int = Field(
        ge=0, le=100,
        description="量化总分（0-100），计算公式见 Judge prompt。用于 verdict 决策：>=85 pass, 70-84 conditional, <50 fail"
    )
    risks: list[JudgeRisk] = Field(default_factory=list)

    # 新增：AC 质量维度
    ac_quality: dict = Field(
        default_factory=dict,
        description="""
    {
        "total_acs": int,
        "executable_count": int,     // 有具体命令的 AC
        "verifiable_count": int,     // 有明确通过标准的 AC
        "specific_count": int,       // 避免模糊描述的 AC
        "complete_coverage": bool,   // 是否覆盖所有功能点
        "details": [{"wp_id": str, "issues": [str]}]
    }
    """,
    )

    # 新增：回归检查（第 2+ 轮时检查上轮修复是否回退）
    regressions: list[dict] = Field(
        default_factory=list,
        description="""
    [{"risk_id": str, "description": str, "was_fixed_in_round": int, "regressed_in_round": int}]
    """,
    )

    # 新增：可消费性评分
    consumability_score: float = Field(ge=0.0, le=1.0, default=0.0)
    consumability_details: list[dict] = Field(default_factory=list)

    # 汇总
    summary: str = ""


__all__ = [
    "JudgeRisk",
    "JudgeMeta",
    "JudgeOutput",
]
