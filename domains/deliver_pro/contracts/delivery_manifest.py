"""
DeliveryManifest — Phase 5 Package Agent 的最终交付清单。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeliveryStatus(str, Enum):
    """交付状态。"""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ComponentStatus(BaseModel):
    """单个组件的交付状态。"""

    task_id: str
    title: str
    status: str = Field(description="PASS | FAILED")
    artifacts: list[str] = Field(
        default_factory=list,
        description="产出文件路径列表",
    )
    failure_reason: Optional[str] = None
    user_actions: list[str] = Field(
        default_factory=list,
        description="用户可以采取的行动（失败时）",
    )


class DeliveryManifest(BaseModel):
    """
    最终交付清单。

    Phase 5 Package Agent 的产出。
    记录每个组件的状态、失败原因、用户行动选项。
    """

    wp_id: str
    delivery_status: DeliveryStatus = Field(
        default=DeliveryStatus.COMPLETE,
    )
    components: list[ComponentStatus] = Field(default_factory=list)
    validation_summary: dict = Field(
        default_factory=lambda: {
            "rounds_run": 0,
            "final_score": 0.0,
            "verdict": "N/A",
        },
    )
    # N6: Information conservation fields
    semantic_anchors: list[str] = Field(
        default_factory=list,
        description="语义锚点列表（来自 Ship Pro ship_package 透传，必须在最终交付物中被引用）",
    )
    requirement_traceability: dict = Field(
        default_factory=lambda: {
            "covered_req_ids": [],
            "total_req_ids": [],
            "coverage_ratio": 0.0,
        },
        description="需求追溯链 {covered_req_ids, total_req_ids, coverage_ratio}",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.components if c.status == "PASS")

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.components if c.status == "FAILED")

    @property
    def total_count(self) -> int:
        return len(self.components)
