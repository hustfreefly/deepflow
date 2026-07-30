"""
ValidationVerdict — Phase 4 Validate Judge 的判定结果。

对标 Solution Pro 的 AgentResult，但增加了 6 维度评分和修复指令。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScoreDimension(BaseModel):
    """单个评分维度。"""

    score: int = Field(ge=1, le=5, description="评分 1-5")
    max: int = Field(default=5)
    weight: float = Field(ge=0.0, le=1.0, description="权重")
    notes: str = Field(default="", description="评分说明")


class FixDirective(BaseModel):
    """定向修复指令。"""

    target: str = Field(description="目标 task_id")
    issue: str = Field(description="问题描述")
    fix_instruction: str = Field(description="修复指令")
    priority: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="high | medium | low",
    )
    estimated_effort: str = Field(default="", description="预估修复工作量")


# 默认维度权重
DEFAULT_WEIGHTS = {
    "completeness": 0.25,
    "correctness": 0.25,
    "credibility": 0.20,
    "actionability": 0.15,
    "consistency": 0.10,
    "professionalism": 0.05,
}

# 六维质量门要求的完整维度集合
REQUIRED_DIMENSIONS = frozenset(DEFAULT_WEIGHTS.keys())


class ValidationVerdict(BaseModel):
    """
    Validate Judge 的判定结果。

    包含 6 维度评分、门禁判定、修复指令。
    """

    round: int = Field(ge=1, description="当前轮次")
    verdict: Literal["PASS", "CONDITIONAL", "FAIL"] = Field(
        description="PASS | CONDITIONAL | FAIL",
    )
    scores: dict[str, ScoreDimension] = Field(
        description="6 维度评分",
    )
    weighted_score: float = Field(
        ge=0.0,
        le=5.0,
        description="加权平均分",
    )
    fix_directives: list[FixDirective] = Field(
        default_factory=list,
        description="修复指令列表",
    )
    has_fixable: bool = Field(
        default=False,
        description="是否有可修复项",
    )
    should_continue: bool = Field(
        default=True,
        description="是否应继续修复循环",
    )
    should_continue_reason: str = Field(
        default="",
        description="继续/停止的理由",
    )

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        allowed = {"PASS", "CONDITIONAL", "FAIL"}
        if v not in allowed:
            raise ValueError(f"verdict must be one of {allowed}, got '{v}'")
        return v

    @property
    def is_pass(self) -> bool:
        return self.verdict == "PASS"

    @property
    def is_fail(self) -> bool:
        return self.verdict == "FAIL"

    @classmethod
    def compute_verdict(cls, weighted_score: float, scores: dict[str, ScoreDimension]) -> str:
        """根据加权分、维度分和维度完整性计算门禁判定。

        六维质量门要求：scores 必须包含全部 6 个维度
        （completeness, correctness, credibility, actionability,
        consistency, professionalism）。缺失任意维度视为契约违反，
        直接返回 FAIL。
        """
        # 维度完整性检查：缺失任意维度 → FAIL
        present_dims = set(scores.keys())
        missing_dims = REQUIRED_DIMENSIONS - present_dims
        if missing_dims:
            return "FAIL"

        min_score = min(s.score for s in scores.values()) if scores else 0

        if weighted_score >= 3.5 and min_score >= 3:
            return "PASS"
        elif weighted_score >= 3.0 and min_score >= 2:
            return "CONDITIONAL"
        else:
            return "FAIL"

    @classmethod
    def compute_weighted_score(cls, scores: dict[str, ScoreDimension]) -> float:
        """计算加权平均分。"""
        if not scores:
            return 0.0
        total_weight = sum(s.weight for s in scores.values())
        if total_weight == 0:
            return 0.0
        return sum(s.score * s.weight for s in scores.values()) / total_weight

    @classmethod
    def from_json(cls, path: str | Path) -> "ValidationVerdict":
        """从 validation_result.json 构造 ValidationVerdict。

        处理常见格式差异：
        - 缺少 round → 默认 1
        - scores 为非 ScoreDimension 格式 → 自动转换
        - dimensions 代替 scores → 兼容
        """
        data = json.loads(Path(path).read_text())
        dims_raw = data.get("dimensions", data.get("scores", {}))

        # 转换 scores: 支持 {"dim": {"score": 5, ...}} 和 {"dim": 5} 两种格式
        scores = {}
        for dim_name, dim_data in dims_raw.items():
            if isinstance(dim_data, dict):
                weight = dim_data.get("weight", DEFAULT_WEIGHTS.get(dim_name, 0.0))
                scores[dim_name] = ScoreDimension(
                    score=dim_data.get("score", 0),
                    weight=weight,
                    notes=dim_data.get("notes", ""),
                )
            elif isinstance(dim_data, (int, float)):
                scores[dim_name] = ScoreDimension(
                    score=int(dim_data),
                    weight=DEFAULT_WEIGHTS.get(dim_name, 0.0),
                )

        weighted_score = data.get("weighted_score", cls.compute_weighted_score(scores))
        verdict = data.get("verdict", cls.compute_verdict(weighted_score, scores))

        return cls(
            round=data.get("round", 1),
            verdict=verdict,
            scores=scores,
            weighted_score=weighted_score,
            fix_directives=data.get("fix_directives", []),
            has_fixable=data.get("has_fixable", False),
            should_continue=data.get("should_continue", False),
            should_continue_reason=data.get("should_continue_reason", ""),
        )
