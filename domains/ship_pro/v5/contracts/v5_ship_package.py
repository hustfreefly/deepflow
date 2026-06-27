"""
v5_ship_package.py — Ship Pro V5 Phase 2 输出契约
唯一真相源：ShipPackage 结构体，定义在 Phase 2 (AC Writer → Propagator → DepGraph → 3 Judge → Consolidator) 完成后输出。
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Literal


class Module(BaseModel):
    """复用 Phase 1 的模块定义，但 Phase 2 中可能额外附加 propagate 产物。"""

    id: str = Field(..., pattern=r"^COMP-\d{3}$")
    name: str
    summary: str
    responsibilities: List[str]
    technology_stack: List[str]
    is_infrastructure: bool = False
    propagated_files: List[str] = Field(default_factory=list)  # Phase 2 新增

    model_config = {"extra": "forbid"}


class Requirement(BaseModel):
    """复用 Phase 1 的需求定义。"""

    req_id: str = Field(..., pattern=r"^REQ-\d{3}$")
    description: str
    priority: Literal["P0", "P1", "P2"]
    coverage: Literal["covered", "partial", "missing"]
    mapped_components: List[str]
    ac_ids: List[str] = Field(default_factory=list)  # Phase 2 关联的 AC

    model_config = {"extra": "forbid"}


class AcceptanceCriterion(BaseModel):
    """可验收标准，由 AC Writer 生成。"""

    text: str
    level: Literal["L1", "L2", "L3", "L4"]
    has_numeric: bool
    has_verification_method: bool
    command_template: Optional[str] = None

    model_config = {"extra": "forbid"}

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("AC text must not be blank")
        return v

    @field_validator("level")
    @classmethod
    def level_with_numeric(cls, v: Literal["L1", "L2", "L3", "L4"], info) -> str:
        has_numeric = info.data.get("has_numeric")
        if v in ("L1", "L2") and has_numeric is False:
            raise ValueError(f"Level {v} requires has_numeric=True")
        return v


class WorkPackage(BaseModel):
    """Phase 2 完整工作包，包含 AC、约束、上下文文件和输出产物。"""

    id: str
    title: str
    objective: str
    source_modules: List[str]       # COMP IDs
    dependencies: List[str]           # WP IDs
    priority: Literal["high", "medium", "low"]
    acceptance_criteria: List[AcceptanceCriterion]
    constraints: Dict[str, Any]
    serving_principles: List[Dict[str, Any]]
    context_files: List[str]        # 相对路径或 URL
    outputs: List[Dict[str, Any]]   # 产物清单

    model_config = {"extra": "forbid"}

    @field_validator("title", "objective")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank")
        return v

    @field_validator("acceptance_criteria")
    @classmethod
    def ac_not_empty(cls, v: List[AcceptanceCriterion]) -> List[AcceptanceCriterion]:
        if not v:
            raise ValueError("acceptance_criteria must contain at least one item")
        return v

    @field_validator("source_modules")
    @classmethod
    def not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("source_modules must not be empty")
        return v


class DependencyGraph(BaseModel):
    """由 DepGraph Agent 生成的执行图。"""

    execution_order: List[str]          # WP IDs 拓扑排序
    parallel_groups: List[List[str]]    # 可并行执行的 WP 组
    critical_path: List[str]            # 关键路径 WP IDs
    edges: List[Dict[str, str]]         # 边列表，每项含 from/to
    has_cycle: bool

    model_config = {"extra": "forbid"}

    @field_validator("execution_order")
    @classmethod
    def order_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("execution_order must not be empty")
        return v

    @field_validator("has_cycle")
    @classmethod
    def no_cycles(cls, v: bool) -> bool:
        if v:
            raise ValueError("Dependency graph must not contain cycles")
        return v


class ShipPackage(BaseModel):
    """Phase 2 最终产物：ship_package.json 的结构。"""

    project: Dict[str, str]                     # 至少含 name, version
    modules: List[Module]
    requirements: List[Requirement]
    work_packages: List[WorkPackage]
    dependency_graph: DependencyGraph
    api_conventions: Dict[str, Any]
    integration_tests: List[Dict[str, Any]]
    error_handling_principles: List[Dict[str, Any]]
    numeric_conflicts: List[Dict[str, Any]]     # 数值冲突报告
    summary: Dict[str, Any]                     # 总览统计
    meta: Dict[str, Any] = Field(default_factory=dict, alias="_meta")

    model_config = {"extra": "forbid", "populate_by_name": True}

    # 便捷方法
    def wp_ids(self) -> set[str]:
        return {wp.id for wp in self.work_packages}

    def module_ids(self) -> set[str]:
        return {m.id for m in self.modules}

    def req_ids(self) -> set[str]:
        return {r.req_id for r in self.requirements}


# ── 自测 ──────────────────────────────────────────────────
if __name__ == "__main__":
    ship = ShipPackage(
        project={"name": "Ship Pro V5", "version": "5.0.0"},
        modules=[
            Module(
                id="COMP-001",
                name="Parser",
                summary="Parse PRD into structured tree",
                responsibilities=["Extract requirements"],
                technology_stack=["pydantic"],
                propagated_files=["src/parser.py"],
            ),
        ],
        requirements=[
            Requirement(
                req_id="REQ-001",
                description="Parse PRD into structured tree",
                priority="P0",
                coverage="covered",
                mapped_components=["COMP-001"],
                ac_ids=["AC-001"],
            ),
        ],
        work_packages=[
            WorkPackage(
                id="WP-001",
                title="Build Parser",
                objective="Deliver a working PRD parser",
                source_modules=["COMP-001"],
                dependencies=[],
                priority="high",
                acceptance_criteria=[
                    AcceptanceCriterion(
                        text="Parser processes 1000-line PRD in < 500ms",
                        level="L1",
                        has_numeric=True,
                        has_verification_method=True,
                        command_template="pytest tests/test_parser.py --benchmark",
                    ),
                ],
                constraints={"max_latency_ms": 500},
                serving_principles=[{"name": "single_responsibility"}],
                context_files=["docs/prd.md"],
                outputs=[{"type": "code", "path": "src/parser.py"}],
            ),
        ],
        dependency_graph=DependencyGraph(
            execution_order=["WP-001"],
            parallel_groups=[["WP-001"]],
            critical_path=["WP-001"],
            edges=[],
            has_cycle=False,
        ),
        api_conventions={"naming": "snake_case"},
        integration_tests=[{"name": "e2e_parser", "path": "tests/e2e/"}],
        error_handling_principles=[{"strategy": "fail_fast"}],
        numeric_conflicts=[],
        summary={
            "total_wps": 1,
            "total_ac": 1,
            "coverage_rate": 1.0,
            "has_numeric_conflicts": False,
        },
        _meta={"version": "5.0.0", "schema": "v5_ship_package"},
    )
    print("✅ ShipPackage validated:", ship.project["name"])
    print(f"   WPs: {len(ship.work_packages)}, ACs: {sum(len(wp.acceptance_criteria) for wp in ship.work_packages)}")

    # L1 AC without numeric test
    try:
        AcceptanceCriterion(text="Do something", level="L1", has_numeric=False, has_verification_method=True)
    except Exception as e:
        print(f"✅ L1 without numeric blocked: {e}")

    # Cycle detection test
    try:
        DependencyGraph(
            execution_order=["WP-001"],
            parallel_groups=[],
            critical_path=[],
            edges=[],
            has_cycle=True,
        )
    except Exception as e:
        print(f"✅ Cycle detection enforced: {e}")

    print("\n🎉 v5_ship_package.py 所有自测通过")
