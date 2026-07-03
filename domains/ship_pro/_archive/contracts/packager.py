"""
Packager Agent 输出契约 (ShipPackage) — 唯一真相源

从此模型自动生成:
1. JSON Schema → schemas/ship_package_v3.schema.json
2. Prompt 中的输出格式段落 → packager.md
3. Gate 字段检查清单 → gate_packager

设计原则: Pydantic 模型是唯一真相源，JSON Schema 由 model_json_schema() 生成。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Meta
# ============================================================================


class Generator(BaseModel):
    agent: Literal["ship-pro"] = "ship-pro"
    model: str
    version: str


class PackageMeta(BaseModel):
    package_id: str = Field(description="Unique package identifier (e.g. SP-001)", pattern=r"^SP-[0-9]+$")
    project_name: str = ""
    generated_at: str = Field(description="ISO 8601 generation timestamp")
    generator: Generator
    source_session_id: str
    input_format: Literal["A_final_solution", "B_flat_domain", "C_pipeline_summary", "D_minimal"] = (
        "A_final_solution"
    )
    tags: list[str] = Field(default_factory=list)


# ============================================================================
# Project Context
# ============================================================================


class ArchitectureComponent(BaseModel):
    name: str
    type: str = ""
    technology: str = ""
    description: str = ""


class Architecture(BaseModel):
    style: str = ""
    components: list[ArchitectureComponent] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)


class RequirementCoverageItem(BaseModel):
    id: str
    title: str = ""
    status: Literal["covered", "partial", "gap"] = "covered"


class RequirementsCoverage(BaseModel):
    total: int = 0
    covered: int = 0
    coverage_rate: float = Field(default=0.0, ge=0, le=1)
    items: list[RequirementCoverageItem] = Field(default_factory=list)


class ProjectContext(BaseModel):
    problem_statement: str
    solution_overview: str
    core_value: str = ""
    architecture: Architecture = Field(default_factory=Architecture)
    requirements_coverage: RequirementsCoverage = Field(default_factory=RequirementsCoverage)
    constraints: list[str] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)


# ============================================================================
# Work Packages
# ============================================================================


class Budget(BaseModel):
    tokens: int = Field(ge=1000)
    time_minutes: int = Field(ge=1)
    max_retries: int = Field(default=3, ge=0, le=10)


class OutputArtifact(BaseModel):
    type: Literal["file", "directory", "api_endpoint", "database_migration", "config", "test", "documentation"]
    path: str
    description: str = ""


class AcceptanceTest(BaseModel):
    command: str
    expected_exit_code: int = 0
    expected_output_contains: str = ""
    description: str = ""


class RetryPolicy(BaseModel):
    on_failure: Literal["abort", "retry", "skip", "fallback"] = "abort"
    fallback_wp: str = ""


class WorkPackage(BaseModel):
    id: str = Field(pattern=r"^WP-[0-9]+$")
    title: str = Field(max_length=120)
    objective: str
    budget: Budget
    complexity: Literal["trivial", "low", "medium", "high", "critical"]
    model_tier: Literal[
        "claude-opus",
        "claude-sonnet",
        "claude-haiku",
        "gpt-4o",
        "gpt-4o-mini",
        "qwen-max",
        "qwen-plus",
        "auto",
    ] = "auto"
    dependencies: list[str] = Field(default_factory=list)
    priority: Literal["critical", "high", "medium", "low"]
    context_files: list[str] = Field(default_factory=list)
    outputs: list[OutputArtifact] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    acceptance_tests: list[AcceptanceTest] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    requires_human_approval: bool = False
    tags: list[str] = Field(default_factory=list)


# ============================================================================
# Dependency Graph
# ============================================================================


class DependencyEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    type: Literal["hard", "soft"] = "hard"

    class Config:
        populate_by_name = True


class DependencyGraph(BaseModel):
    execution_order: list[str]
    parallel_groups: list[list[str]]
    critical_path: list[str] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)


# ============================================================================
# Risk Register
# ============================================================================


class RiskRegisterItem(BaseModel):
    id: str = Field(pattern=r"^RISK-[0-9]+$")
    title: str
    description: str = ""
    severity: Literal["critical", "high", "medium", "low"]
    likelihood: Literal["certain", "likely", "possible", "unlikely", "rare"]
    mitigation: str = ""
    affected_wps: list[str] = Field(default_factory=list)


# ============================================================================
# Summary
# ============================================================================


class ComplexityDistribution(BaseModel):
    trivial: int = 0
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class PackageSummary(BaseModel):
    total_wps: int
    estimated_effort: str
    total_token_budget: int = 0
    total_time_minutes: int = 0
    parallel_time_minutes: int = 0
    complexity_distribution: ComplexityDistribution = Field(default_factory=ComplexityDistribution)
    narrative: str = ""
    immediate_next_steps: list[str] = Field(default_factory=list)


# ============================================================================
# Quality Report
# ============================================================================


class QualityIssue(BaseModel):
    check: str = ""
    status: Literal["pass", "warn", "fail"] = "pass"
    message: str = ""


class Layer1Structural(BaseModel):
    score: float = Field(default=0.0, ge=0, le=1)
    checks_passed: int = 0
    checks_total: int = 0
    issues: list[QualityIssue] = Field(default_factory=list)


class Layer2Semantic(BaseModel):
    score: float = Field(default=0.0, ge=0, le=1)
    coverage_assessment: str = ""
    coherence_assessment: str = ""
    feasibility_assessment: str = ""


class Layer3Actionable(BaseModel):
    score: float = Field(default=0.0, ge=0, le=1)
    clarity_score: float = Field(default=0.0, ge=0, le=1)
    testability_score: float = Field(default=0.0, ge=0, le=1)
    dependency_completeness: float = Field(default=0.0, ge=0, le=1)
    blockers: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    layer1_structural: Layer1Structural = Field(default_factory=Layer1Structural)
    layer2_semantic: Layer2Semantic = Field(default_factory=Layer2Semantic)
    layer3_actionable: Layer3Actionable = Field(default_factory=Layer3Actionable)
    overall_score: float = Field(default=0.0, ge=0, le=1)
    recommendations: list[str] = Field(default_factory=list)


# ============================================================================
# Top-Level ShipPackage
# ============================================================================


class ShipPackage(BaseModel):
    """
    Ship Pro V3 最终交付物契约。

    Pydantic 模型是唯一真相源。JSON Schema 由 ShipPackage.model_json_schema() 生成。
    所有 Prompt 中的输出格式和 Gate 中的字段检查都应从此模型派生。
    """

    schema_version: Literal["3.0.0", "3.1.0"]
    meta: PackageMeta
    project_context: ProjectContext
    work_packages: list[WorkPackage] = Field(min_length=1)
    dependency_graph: DependencyGraph
    risk_register: list[RiskRegisterItem] = Field(default_factory=list)
    summary: PackageSummary
    quality_report: QualityReport = Field(default_factory=QualityReport)

    # V3 Extras (AI Native, from 3-expert review 2026-06-26)
    api_conventions: Optional[dict[str, Any]] = None
    integration_tests: Optional[list[dict[str, Any]]] = None
    error_handling_principles: Optional[dict[str, Any]] = None
    environment: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


__all__ = [
    "ShipPackage",
    "PackageMeta",
    "Generator",
    "ProjectContext",
    "Architecture",
    "ArchitectureComponent",
    "RequirementsCoverage",
    "RequirementCoverageItem",
    "WorkPackage",
    "Budget",
    "OutputArtifact",
    "AcceptanceTest",
    "RetryPolicy",
    "DependencyGraph",
    "DependencyEdge",
    "RiskRegisterItem",
    "PackageSummary",
    "ComplexityDistribution",
    "QualityReport",
    "Layer1Structural",
    "Layer2Semantic",
    "Layer3Actionable",
    "QualityIssue",
]
