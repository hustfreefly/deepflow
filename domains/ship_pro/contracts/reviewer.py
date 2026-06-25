"""
Reviewer Agent 输出契约 — 唯一真相源

从此模型自动生成:
1. JSON Schema (schemas/reviewer_output_v3.schema.json)
2. Prompt 中的输出格式段落
3. Gate 字段检查清单 (gate_reviewer)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .principles import PrincipleAuditEntry, PlatformAuditEntry


class Issue(BaseModel):
    """Reviewer 发现的单个问题。"""

    severity: Literal["critical", "high", "medium", "low"]
    target_agent: Literal["architect", "decomposer", "specifier"]
    description: str = Field(min_length=1)
    suggestion: str = ""
    affected_wp: str = ""
    target_field: str = ""


class QualityMetrics(BaseModel):
    """
    Reviewer 评估的质量指标。

    字段名来自 reviewer.md prompt 定义：
    - ac_verifiability_score: AC 可验证性均分 (0-100)
    - coverage_rate: 模块覆盖率 (0.0-1.0)
    - dependency_sanity: 依赖无环检查 ("ok" / "cycle_detected")
    - details: 逐 WP 评分详情 (optional)
    """

    ac_verifiability_score: float = Field(ge=0, le=100)
    coverage_rate: float = Field(ge=0, le=1)
    dependency_sanity: Literal["ok", "cycle_detected"] = "ok"
    details: dict[str, Any] = Field(default_factory=dict)


class ReviewerOutput(BaseModel):
    """
    Reviewer Agent 输出契约。

    Critical 字段: verdict, issues, quality_metrics
    Major 字段: summary, round
    """

    verdict: Literal["PASS", "PASS_WITH_CONDITIONS", "FAIL"]
    issues: list[Issue] = Field(default_factory=list)
    quality_metrics: QualityMetrics
    summary: str = Field(min_length=1)
    round: int = Field(ge=0, default=0)
    # 新增字段（Phase 1: 原则对齐）
    principle_audit: list[PrincipleAuditEntry] = Field(
        default_factory=list,
        description="原则审计结果。Gate Major 必检字段（如果输入包含 architecture_principles）。"
    )
    platform_audit: list[PlatformAuditEntry] = Field(
        default_factory=list,
        description="平台审计结果。Gate Major 必检字段（如果输入包含 platform_capabilities）。"
    )
