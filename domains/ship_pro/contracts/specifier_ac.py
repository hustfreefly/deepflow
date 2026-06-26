"""
Ship Pro V4.1 — Structured Acceptance Criteria Pydantic Contract

Replaces string ACs with structured JSON that downstream agents can consume directly.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class ACLevel(str, Enum):
    """AC 分级 — 可执行性从高到低"""
    L4 = "L4"  # 可直接执行的测试命令（pytest, curl, etc.）
    L3 = "L3"  # 可验证但有前置依赖（需先部署/配置）
    L2 = "L2"  # 需要人工判断（review, inspect）
    L1 = "L1"  # 模糊/空泛（"系统正常工作"）


class AcceptanceCriterion(BaseModel):
    """Structured AC — 源头结构化，不让下游猜"""
    id: str = Field(description="AC 唯一标识，如 AC-001-1")
    level: ACLevel = Field(description="可执行性分级")
    description: str = Field(description="AC 描述")
    test_command: Optional[str] = Field(
        default=None,
        description="可执行的测试命令（L4 必填，L3 选填）",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="前置依赖（其他 AC 或环境条件）",
    )
    expected_result: Optional[str] = Field(
        default=None,
        description="预期结果描述",
    )

    def to_prompt_string(self) -> str:
        """Generate human-readable string for Worker prompt."""
        parts = [f"{self.id} [{self.level.value}]: {self.description}"]
        if self.test_command:
            parts.append(f"  test: `{self.test_command}`")
        if self.expected_result:
            parts.append(f"  expected: {self.expected_result}")
        if self.dependencies:
            parts.append(f"  deps: {', '.join(self.dependencies)}")
        return "\n".join(parts)


class WorkPackageSpec(BaseModel):
    """Specifier output for a single work package (with structured ACs)."""
    id: str
    title: str
    objective: str
    budget: Optional[dict] = None
    complexity: str = "medium"
    model_tier: str = "standard"
    dependencies: list[str] = Field(default_factory=list)
    priority: str = "medium"
    related_modules: list[str] = Field(default_factory=list)
    context_files: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    acceptance_tests: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    retry_policy: Optional[dict] = None
    tags: list[str] = Field(default_factory=list)


class SpecifierOutput(BaseModel):
    """Top-level Specifier output contract."""
    meta: dict = Field(default_factory=dict, alias="_meta")
    work_packages: list[WorkPackageSpec] = Field(default_factory=list)
    self_check: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


if __name__ == "__main__":
    import json
    # Example AC
    ac = AcceptanceCriterion(
        id="AC-001-1",
        level=ACLevel.L4,
        description="原子写入在 100 次连续写入中无数据损坏",
        test_command="pytest tests/test_blackboard_checkpoint.py::test_atomic_write -v",
        expected_result="All 100 writes succeed without corruption",
    )
    print(json.dumps(ac.model_dump(), indent=2, ensure_ascii=False))
    print("---")
    print(ac.to_prompt_string())
