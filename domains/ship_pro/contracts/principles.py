"""
架构原则与平台约束契约 — 唯一真相源

新增模型:
- ArchitecturePrinciple: 架构原则（风格约束）
- PlatformCapability: 平台能力（复用约束）
- PrincipleCoverage: 原则-组件映射
- PlatformReuseEntry: 平台能力-组件映射
- PrincipleAuditEntry: 原则审计结果
- PlatformAuditEntry: 平台审计结果
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ArchitecturePrinciple(BaseModel):
    """
    架构原则（风格约束）。
    
    例: "全LLM控制，Python不做控制流"
    """
    
    id: str = Field(description="原则ID，如 PRINCIPLE-001")
    name: str = Field(min_length=1, description="原则名称")
    type: Literal["must_do", "must_not_do", "must_have", "invariant"]
    description: str = Field(min_length=1)
    anti_patterns: list[str] = Field(
        default_factory=list,
        description="具体的反面模式描述，帮助 LLM 理解什么不该做"
    )
    verification_method: str = Field(
        default="",
        description="如何验证此原则被遵守"
    )
    severity: Literal["BLOCKER", "WARNING"] = "BLOCKER"


class PlatformCapability(BaseModel):
    """
    平台能力（复用约束）。
    
    例: "OpenClaw sessions_spawn 用于子Agent调度，禁止自建 Worker Pool"
    """
    
    platform: str = Field(description="平台名称，如 OpenClaw")
    capability: str = Field(min_length=1, description="能力名称")
    api: str = Field(description="API 调用方式")
    replaces: list[str] = Field(
        default_factory=list,
        description="该能力替代的自建组件列表"
    )
    must_use: bool = Field(
        default=True,
        description="是否必须使用（true=禁止重建）"
    )
    rationale: str = Field(
        default="",
        description="为什么必须用平台能力而非自建"
    )


class PrincipleCoverage(BaseModel):
    """
    原则-组件映射（Architect 输出）。
    
    说明哪些组件负责实现/遵守某条原则。
    """
    
    principle_id: str
    covered_by_modules: list[str] = Field(
        description="负责实现此原则的模块ID列表"
    )
    coverage_method: str = Field(
        description="如何覆盖此原则（例: COMP-001 通过 LLM API 调用实现路由决策）"
    )
    gap_analysis: str = Field(
        default="",
        description="覆盖缺口分析（如果为空表示完全覆盖）"
    )


class PlatformReuseEntry(BaseModel):
    """
    平台能力-组件映射（Architect 输出）。
    
    说明哪些组件复用了哪些平台能力。
    """
    
    platform_capability: str
    reused_by_modules: list[str] = Field(
        description="复用此平台能力的模块ID列表"
    )
    not_reused_rationale: str = Field(
        default="",
        description="如果未复用，说明原因（仅当 must_use=false 时填写）"
    )


class PrincipleAuditEntry(BaseModel):
    """
    原则审计结果（Reviewer 输出）。
    
    检查每条原则是否在 WP 中有可验证的对应。
    """
    
    principle_id: str
    principle_name: str
    wp_coverage: dict[str, str] = Field(
        description="WP覆盖情况，key=WP ID, value=覆盖状态描述"
    )
    overall_status: Literal["PASS", "FAIL", "PARTIAL"]
    action_required: str = Field(
        default="",
        description="需要采取的行动（如果 overall_status != PASS）"
    )


class PlatformAuditEntry(BaseModel):
    """
    平台审计结果（Reviewer 输出）。
    
    检查每个必须复用的平台能力是否在 WP 中被使用。
    """
    
    platform_capability: str
    api: str
    wp_status: dict[str, str] = Field(
        description="WP使用状态，key=WP ID, value=使用状态描述"
    )
    overall_status: Literal["PASS", "FAIL", "PARTIAL"]
    violation_description: str = Field(
        default="",
        description="违反描述（如果 overall_status = FAIL）"
    )


__all__ = [
    "ArchitecturePrinciple",
    "PlatformCapability",
    "PrincipleCoverage",
    "PlatformReuseEntry",
    "PrincipleAuditEntry",
    "PlatformAuditEntry",
]
