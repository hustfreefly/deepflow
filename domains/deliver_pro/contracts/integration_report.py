"""IntegrationReport — Phase 3 Integrate Agent 的组装报告."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntegrationReport(BaseModel):
    """Integrate Agent 的组装报告.

    记录组装前检查结果、一致性验证、AC 覆盖率。
    """

    workers_integrated: int = Field(description="成功组装的 Worker 数量")
    workers_failed: int = Field(default=0, description="失败的 Worker 数量")
    consistency_checks_passed: bool = Field(default=True)
    conflicts_found: list[str] = Field(default_factory=list)
    coverage: dict = Field(
        default_factory=lambda: {
            "acceptance_criteria_total": 0,
            "covered": 0,
            "gaps": [],
        },
        description="AC 覆盖率",
    )
    integration_test_result: str = Field(
        default="",
        description="集成测试结果（编程场景）",
    )
    status: Literal["READY_FOR_VALIDATE", "ASSEMBLY_FAILED"] = Field(
        default="READY_FOR_VALIDATE",
        description="READY_FOR_VALIDATE | ASSEMBLY_FAILED",
    )

    @property
    def coverage_ratio(self) -> float:
        total = self.coverage.get("acceptance_criteria_total", 0)
        covered = self.coverage.get("covered", 0)
        return covered / total if total > 0 else 0.0
