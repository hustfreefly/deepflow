"""
Generator Agent 输出契约 V4.1 — 唯一真相源

合并 Architect + Decomposer + Specifier + Packager 的全部输出字段，
由 Generator 一次性生成完整的架构蓝图 + WP 规格 + 打包信息。

V4.1 改进: Pydantic 模型宽容化，接受 LLM 常用输出变体。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, BeforeValidator, Field
from typing_extensions import Annotated

from .principles import (
    ArchitecturePrinciple,
    PlatformCapability,
    PrincipleCoverage,
    PlatformReuseEntry,
)
from .architect import (
    ArchitectMeta,
    Project,
    Module,
    Dependency,
    Requirement,
    SLAConstraint,
    Risk,
    ImplementationHint,
)


# ---------------------------------------------------------------------------
# BeforeValidator 工厂：LLM 输出宽容化
# ---------------------------------------------------------------------------

def _flatten_to_str_list(v: Any) -> list[str]:
    """将 list[str] 或 list[dict] 展平为 list[str]。"""
    if isinstance(v, list):
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # 提取最可能的文本字段
                for key in ("text", "description", "criteria", "ac_id", "name", "value"):
                    if key in item and isinstance(item[key], str):
                        result.append(item[key])
                        break
                else:
                    result.append(str(item))
            else:
                result.append(str(item))
        return result
    return v


def _list_to_dict(v: Any) -> dict:
    """将 list 转为 dict（如果 LLM 输出了 list 而非 dict）。"""
    if isinstance(v, list):
        return {f"item_{i}": item if isinstance(item, str) else str(item) for i, item in enumerate(v)}
    return v


def _dict_or_list_to_list(v: Any) -> list:
    """将 dict 转为 list（如果 LLM 输出了 dict 而非 list）。"""
    if isinstance(v, dict):
        return [{"category": k, "description": val if isinstance(val, str) else str(val)} for k, val in v.items()]
    return v


# 类型别名：带 BeforeValidator 的宽容类型
FlexibleStrList = Annotated[list[str], BeforeValidator(_flatten_to_str_list)]
FlexibleDict = Annotated[dict, BeforeValidator(_list_to_dict)]
FlexibleListFromDict = Annotated[list, BeforeValidator(_dict_or_list_to_list)]


# ---------------------------------------------------------------------------
# WorkPackageSpec
# ---------------------------------------------------------------------------

class WorkPackageSpec(BaseModel):
    """单个 WP 的完整规格（合并 decomposer + specifier 信息）"""

    id: str
    title: str = Field(alias="name")  # 接受 LLM 常用的 "name" 字段名
    objective: str = Field(default="")  # 可选，LLM 可能不输出
    source_modules: list[str] = Field(default_factory=list)
    dependencies: FlexibleStrList = Field(default_factory=list)  # 接受 str[] 或 dict[]
    priority: str = Field(default="medium", description="high/medium/low")
    complexity: str = ""
    budget: dict = Field(default_factory=dict)
    model_tier: str = ""
    outputs: list = Field(default_factory=list)
    acceptance_criteria: FlexibleStrList = Field(default_factory=list)  # 接受 str[] 或 dict[]
    acceptance_tests: FlexibleStrList = Field(default_factory=list)
    constraints: FlexibleDict = Field(default_factory=dict)  # 接受 dict 或 list
    requirements: FlexibleStrList = Field(default_factory=list)
    serving_principles: list[dict] = Field(default_factory=list)
    context_files: list[str] = Field(default_factory=list)
    retry_policy: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True  # 允许同时使用 alias 和字段名

    def model_post_init(self, __context: Any) -> None:
        # objective 回填：如果为空，从 description/summary/rationale 提取
        if not self.objective:
            for attr in ("description", "summary", "rationale"):
                val = getattr(self, attr, None) or self.__pydantic_extra__.get(attr, "") if self.__pydantic_extra__ else ""
                if val and isinstance(val, str):
                    self.objective = val
                    break
            if not self.objective:
                self.objective = self.title

        # acceptance_tests 回填：如果为空，复制 AC
        if not self.acceptance_tests and self.acceptance_criteria:
            self.acceptance_tests = self.acceptance_criteria[:3]

        # priority 归一化
        _pri_map = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low", "CRITICAL": "high"}
        self.priority = _pri_map.get(self.priority.upper() if isinstance(self.priority, str) else "", self.priority)


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------

class DependencyEdge(BaseModel):
    """依赖图的边"""

    from_: str = Field(alias="from")
    to: str
    reason: str = ""

    class Config:
        populate_by_name = True


class DependencyGraph(BaseModel):
    """依赖图"""

    edges: list[DependencyEdge] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)
    parallel_groups: list[list[str]] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# GeneratorOutput
# ---------------------------------------------------------------------------

class GeneratorOutput(BaseModel):
    """
    Generator Agent 完整输出（合并 architect+decomposer+specifier+packager）

    V4.1: Pydantic 宽容化，接受 LLM 常用输出变体。
    """

    # 元数据
    _meta: ArchitectMeta

    # 项目信息
    project_type: str = ""
    project: Project

    # 架构蓝图（from Architect）
    modules: list[Module] = Field(min_length=1)
    dependencies: list[Dependency] = Field(default_factory=list)
    architecture_principles: list[ArchitecturePrinciple] = Field(default_factory=list)
    platform_capabilities: list[PlatformCapability] = Field(default_factory=list)
    principle_coverage: list[PrincipleCoverage] = Field(default_factory=list)
    platform_reuse_map: list[PlatformReuseEntry] = Field(default_factory=list)
    domain_details: dict = Field(default_factory=dict)
    sla_constraints: list[SLAConstraint] = Field(default_factory=list)
    requirements: list[Requirement] = Field(min_length=1)
    risks: list[Risk] = Field(default_factory=list)
    implementation_hints: list[ImplementationHint] = Field(default_factory=list)

    # WP 包（from Decomposer + Specifier）
    work_packages: list[WorkPackageSpec] = Field(min_length=1)

    # 依赖图（from Decomposer）
    dependency_graph: DependencyGraph = Field(default_factory=DependencyGraph)

    # 打包信息（from Packager）
    api_conventions: dict = Field(default_factory=dict)
    integration_tests: list[dict] = Field(default_factory=list)
    error_handling_principles: FlexibleListFromDict = Field(default_factory=list)  # 接受 list 或 dict

    # 自检结果
    self_check: dict = Field(default_factory=dict)


__all__ = [
    "WorkPackageSpec",
    "DependencyEdge",
    "DependencyGraph",
    "GeneratorOutput",
]
