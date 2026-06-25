"""
Architect Agent 输出契约 — 唯一真相源

从此模型自动生成:
1. JSON Schema (供 gate_packager 的 check_schema_compliance 使用)
2. Prompt 中的输出格式段落 (architect.md 的 "输出格式" 章节)
3. Gate 字段检查清单 (gate_architect 的字段检查)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .principles import (
    ArchitecturePrinciple,
    PlatformCapability,
    PrincipleCoverage,
    PlatformReuseEntry,
)


class DataSufficiency(BaseModel):
    """数据充分性标记，反映各维度提取情况。"""

    modules: Literal["sufficient", "partial", "insufficient"]
    dependencies: Literal["sufficient", "partial", "insufficient"]
    requirements: Literal["sufficient", "partial", "insufficient"]
    risks: Literal["sufficient", "partial", "insufficient"]


class ArchitectMeta(BaseModel):
    """Architect 输出元数据。"""

    agent: Literal["architect"] = "architect"
    input_format: Literal["A", "B", "C", "D"]
    overall_confidence: Literal["high", "medium", "low"]
    data_sufficiency: DataSufficiency
    prompt_sha: str = ""
    model_id: str = ""
    run_id: str = ""
    round: int = 0
    timestamp: str = ""


class Project(BaseModel):
    """项目基本信息。"""

    name: str
    objective: str
    problem_statement: str


class Module(BaseModel):
    """架构模块。"""

    id: str
    name: str
    summary: str
    responsibilities: list[str] = Field(default_factory=list)
    technology_stack: list[str] = Field(default_factory=list)
    is_infrastructure: bool = False


class Dependency(BaseModel):
    """模块间依赖关系。"""

    from_: str = Field(alias="from")
    to: str
    reason: str = ""

    class Config:
        populate_by_name = True


class Requirement(BaseModel):
    """需求条目。mapped_components 是 Gate Major 必检字段。"""

    req_id: str
    description: str
    priority: Literal["P0", "P1", "P2"]
    coverage: Literal["covered", "partial", "missing"]
    mapped_components: list[str] = Field(
        default_factory=list,
        description="实现该需求的模块 ID 列表。Gate Major 必检字段。",
    )


class SLAConstraint(BaseModel):
    """SLA 约束。"""

    metric: str
    target: str
    scope: str = ""


class Risk(BaseModel):
    """风险条目。"""

    id: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]


class ImplementationHint(BaseModel):
    """实施建议。"""

    phase: str
    description: str
    modules: list[str] = Field(default_factory=list)


class ArchitectOutput(BaseModel):
    """
    Architect Agent 的完整输出契约。

    Gate 检查映射:
    - Critical: modules (non-empty), dependencies (acyclic), requirements (non-empty)
    - Major: project_type (exists), requirements[].mapped_components (all present)
    - Minor: wp_file_mapping (exists), domain_details (non-empty)
    """

    _meta: ArchitectMeta
    project_type: str = Field(
        description="项目类型分类。Gate Major 必检字段。",
        examples=["web_app", "data_pipeline", "multi_agent", "api_service", "mobile_app", "desktop_app", "other"],
    )
    project: Project
    modules: list[Module] = Field(min_length=1, description="架构模块列表，不能为空")
    dependencies: list[Dependency] = Field(default_factory=list)
    domain_details: dict = Field(default_factory=dict, description="专项架构深度信息")
    sla_constraints: list[SLAConstraint] = Field(default_factory=list)
    requirements: list[Requirement] = Field(min_length=1, description="需求列表，不能为空")
    risks: list[Risk] = Field(default_factory=list)
    implementation_hints: list[ImplementationHint] = Field(default_factory=list)
    wp_file_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="需求到文件的映射。Gate Minor 必检字段。",
    )
    # 新增字段（Phase 1: 原则对齐）
    architecture_principles: list[ArchitecturePrinciple] = Field(
        default_factory=list,
        description="架构原则列表（从 Spec Pro final_result 继承）。Gate Major 必检字段。"
    )
    platform_capabilities: list[PlatformCapability] = Field(
        default_factory=list,
        description="平台能力列表（从 Spec Pro final_result 继承）。Gate Major 必检字段。"
    )
    principle_coverage: list[PrincipleCoverage] = Field(
        default_factory=list,
        description="原则-组件映射。Gate Critical 必检字段（如果 architecture_principles 非空）。"
    )
    platform_reuse_map: list[PlatformReuseEntry] = Field(
        default_factory=list,
        description="平台能力-组件映射。Gate Critical 必检字段（如果 platform_capabilities 非空）。"
    )


__all__ = [
    "ArchitectOutput",
    "ArchitectMeta",
    "DataSufficiency",
    "Project",
    "Module",
    "Dependency",
    "Requirement",
    "SLAConstraint",
    "Risk",
    "ImplementationHint",
]
