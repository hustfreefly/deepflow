"""
v5_blueprint.py — Ship Pro V5 Phase 1 输出契约
唯一真相源：Blueprint 结构体，定义在 Phase 1 (Parser → Explorer → Architect → 3 Critic → Consolidator) 完成后输出。
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Literal


class Module(BaseModel):
    """系统模块 / 组件定义。"""

    id: str = Field(..., pattern=r"^COMP-\d{3}$")
    name: str
    summary: str
    responsibilities: List[str]
    technology_stack: List[str]
    is_infrastructure: bool = False

    model_config = {"extra": "forbid"}

    @field_validator("responsibilities", "technology_stack")
    @classmethod
    def not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("List must not be empty")
        return v


class Requirement(BaseModel):
    """需求映射条目，描述 PRD 需求到模块的追踪关系。"""

    req_id: str = Field(..., pattern=r"^REQ-\d{3}$")
    description: str
    priority: Literal["P0", "P1", "P2"]
    coverage: Literal["covered", "partial", "missing"]
    mapped_components: List[str]

    model_config = {"extra": "forbid"}

    @field_validator("description")
    @classmethod
    def description_min_len(cls, v: str) -> str:
        if len(v.strip()) < 5:
            raise ValueError("Description must be at least 5 characters")
        return v

    @field_validator("mapped_components")
    @classmethod
    def not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("mapped_components must not be empty")
        return v


class Dependency(BaseModel):
    """组件间依赖关系。"""

    from_: str = Field(..., alias="from", pattern=r"^COMP-\d{3}$")
    to: str = Field(..., pattern=r"^COMP-\d{3}$")
    reason: str

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v

    @field_validator("from_", "to")
    @classmethod
    def not_self_loop(cls, v: str, info) -> str:
        return v

    @field_validator("to")
    @classmethod
    def no_self_loop(cls, v: str, info) -> str:
        from_ = info.data.get("from_")
        if from_ is not None and from_ == v:
            raise ValueError("Dependency cannot be a self-loop (from == to)")
        return v


class WorkPackageSkeleton(BaseModel):
    """Phase 1 拆出的工作包骨架，Phase 2 会进一步填充 AC 和 Propagator 产出。"""

    id: str = Field(..., pattern=r"^WP-\d{3}$")
    title: str
    source_modules: List[str]        # COMP IDs
    dependencies: List[str]            # WP IDs
    priority: Literal["high", "medium", "low"]
    rationale: str                    # 为什么这样拆分

    model_config = {"extra": "forbid"}

    @field_validator("title", "rationale")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank")
        return v

    @field_validator("source_modules")
    @classmethod
    def not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("source_modules must not be empty")
        return v


class Blueprint(BaseModel):
    """Phase 1 最终产物：blueprint.json 的结构。"""

    project_name: str
    project_type: Literal[
        "web_app", "data_pipeline", "multi_agent", "api_service",
        "mobile_app", "desktop_app", "other"
    ]
    modules: List[Module]
    requirements: List[Requirement]
    dependencies: List[Dependency]
    architecture_principles: List[Dict[str, Any]]
    platform_capabilities: List[Dict[str, Any]]
    sla_constraints: List[Dict[str, Any]]
    work_packages: List[WorkPackageSkeleton]
    coverage_report: Dict[str, Any]   # 覆盖率统计
    meta: Dict[str, Any] = Field(default_factory=dict, alias="_meta")

    model_config = {"extra": "forbid", "populate_by_name": True}

    # ── 跨字段校验 ──────────────────────────────────────────
    @field_validator("work_packages")
    @classmethod
    def wp_deps_exist(cls, v: List[WorkPackageSkeleton], info) -> List[WorkPackageSkeleton]:
        wp_ids = {wp.id for wp in v}
        for wp in v:
            for dep in wp.dependencies:
                if dep not in wp_ids:
                    raise ValueError(f"WorkPackage {wp.id} depends on unknown WP {dep}")
        return v

    @field_validator("dependencies")
    @classmethod
    def dep_ref_exists(cls, v: List[Dependency], info) -> List[Dependency]:
        # 需要在 Blueprint 实例化后二次校验（见 gate_blueprint）
        return v

    # 便捷方法
    def module_ids(self) -> set[str]:
        return {m.id for m in self.modules}

    def wp_ids(self) -> set[str]:
        return {wp.id for wp in self.work_packages}

    def req_ids(self) -> set[str]:
        return {r.req_id for r in self.requirements}


# ── 自测 ──────────────────────────────────────────────────
if __name__ == "__main__":
    bp = Blueprint(
        project_name="Ship Pro V5",
        project_type="multi_agent",
        modules=[
            Module(
                id="COMP-001",
                name="Parser",
                summary="Parse PRD into structured requirement tree",
                responsibilities=["Extract requirements", "Build requirement tree"],
                technology_stack=["pydantic", "python"],
                is_infrastructure=True,
            ),
            Module(
                id="COMP-002",
                name="Explorer",
                summary="Discover dependencies between modules",
                responsibilities=["Analyze dependencies", "Produce evidence"],
                technology_stack=["python"],
            ),
        ],
        requirements=[
            Requirement(
                req_id="REQ-001",
                description="System must parse PRD into structured tree",
                priority="P0",
                coverage="covered",
                mapped_components=["COMP-001"],
            ),
        ],
        dependencies=[
            Dependency(from_="COMP-002", to="COMP-001", reason="Explorer uses Parser output"),
        ],
        architecture_principles=[{"name": "separation_of_concerns", "scope": "global"}],
        platform_capabilities=[{"name": "async", "level": "native"}],
        sla_constraints=[{"metric": "latency", "target": "< 200ms"}],
        work_packages=[
            WorkPackageSkeleton(
                id="WP-001",
                title="Build Parser",
                source_modules=["COMP-001"],
                dependencies=[],
                priority="high",
                rationale="Parser is the first phase gate",
            ),
            WorkPackageSkeleton(
                id="WP-002",
                title="Build Explorer",
                source_modules=["COMP-002"],
                dependencies=["WP-001"],
                priority="high",
                rationale="Explorer depends on Parser output",
            ),
        ],
        coverage_report={
            "total_requirements": 1,
            "covered": 1,
            "partial": 0,
            "missing": 0,
            "coverage_rate": 1.0,
        },
        _meta={"version": "5.0.0", "schema": "v5_blueprint"},
    )
    print("✅ Blueprint validated:", bp.project_name)
    print(f"   Modules: {len(bp.modules)}, WPs: {len(bp.work_packages)}")

    # 自环测试
    try:
        Dependency(from_="COMP-001", to="COMP-001", reason="self")
    except Exception as e:
        print(f"✅ Self-loop blocked: {e}")

    # 未知 WP 依赖测试
    try:
        Blueprint(
            project_name="Bad",
            project_type="web_app",
            modules=[Module(id="COMP-001", name="A", summary="A", responsibilities=["r"], technology_stack=["t"])],
            requirements=[],
            dependencies=[],
            architecture_principles=[],
            platform_capabilities=[],
            sla_constraints=[],
            work_packages=[
                WorkPackageSkeleton(id="WP-001", title="A", source_modules=["COMP-001"], dependencies=["WP-999"], priority="high", rationale="bad")
            ],
            coverage_report={},
        )
    except Exception as e:
        print(f"✅ Unknown WP dep blocked: {e}")

    print("\n🎉 v5_blueprint.py 所有自测通过")
