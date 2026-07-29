"""
WorkPackage — 来自 Ship Pro 的工作包定义。

Deliver Pro 的输入：消费 Ship Pro 产出的 WP，生成最终交付物。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    """单条验收标准。"""

    id: str = Field(description="AC ID, e.g. 'AC-001'")
    description: str = Field(description="验收标准描述")
    priority: str = Field(default="must", description="must | should | could")


class WorkPackage(BaseModel):
    """
    Work Package — Deliver Pro 的唯一输入。

    来源：Ship Pro 的 WorkPackage 产出。
    约束：不可修改（只读）。
    """

    # FixFlow P2-1: min_length=1 — 空 wp_id 会导致路径拼接错误，fail-fast 拒绝
    wp_id: str = Field(min_length=1, description="WP ID, e.g. 'WP-001'")
    title: str = Field(description="WP 标题")
    objective: str = Field(description="WP 目标描述")
    scenario: Literal["code", "report", "mixed"] = Field(
        default="code",
        description="场景类型: code | report | mixed",
    )
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        default_factory=list,
        description="验收标准列表",
    )
    constraints: dict[str, str] = Field(
        default_factory=dict,
        description="技术约束（如 tech_stack, database 等）",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="依赖的其他 WP ID",
    )
    interface_contract: Optional[str] = Field(
        default=None,
        description="接口契约（编程场景：函数签名/API 路径等）",
    )
    context: dict = Field(
        default_factory=dict,
        description="额外上下文（来自 Solution Pro 的方案摘要等）",
    )
    semantic_anchors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="语义锚点列表（含 constraint），从 Ship Pro 透传",
    )
    serving_principles: list[dict[str, Any]] = Field(
        default_factory=list,
        description="服务原则列表（含 obligation + anti_patterns），从 Ship Pro 透传",
    )

    @property
    def must_criteria(self) -> list[AcceptanceCriterion]:
        """获取 must 级别的验收标准。"""
        return [ac for ac in self.acceptance_criteria if ac.priority == "must"]

    @property
    def total_ac_count(self) -> int:
        """验收标准总数。"""
        return len(self.acceptance_criteria)
