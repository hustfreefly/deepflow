"""
Ship Pro V4.1 — Capability Registry Pydantic Contract

Replaces hardcoded AGENT_ORDER + GATE_CONFIG with declarative JSON config.
Generated schema drives both runtime validation and prompt injection.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class InputSchema(BaseModel):
    """Declares what upstream outputs a capability requires."""
    required: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)


class OutputSchema(BaseModel):
    """Declares the file and fields a capability produces."""
    file: str
    fields: list[str] = Field(default_factory=list)


class Capability(BaseModel):
    """A single registered capability (agent stage)."""
    id: str
    category: str
    description: str
    input_schema: InputSchema
    output_schema: OutputSchema
    max_retries: int = 2
    timeout_minutes: int = 10
    quality_dimensions: list[str] = Field(default_factory=list)
    gate_fn: Optional[str] = None
    worker_prompt: Optional[str] = None


class Constraints(BaseModel):
    """Global pipeline constraints."""
    required_coverage: list[str] = Field(default_factory=list)
    budget_minutes: int = 30
    max_total_retries: int = 15
    max_parallel_workers: int = 3


class ParallelHint(BaseModel):
    """Suggestion for parallel execution (LLM may deviate)."""
    group: list[str]
    note: str = ""


class SkipConditions(BaseModel):
    """Conditions under which a stage may be skipped."""
    # Keys are stage IDs, values are skip reason strings
    pass

    class Config:
        extra = "allow"


class ReferencePlan(BaseModel):
    """A reference execution plan (LLM may choose or deviate)."""
    description: str
    steps: list[str]
    parallel_hints: list[ParallelHint] = Field(default_factory=list)
    skip_conditions: dict[str, str] = Field(default_factory=dict)


class CapabilityRegistry(BaseModel):
    """Top-level capability registry (replaces stage-dependencies.json)."""
    schema_version: str = "capability-registry-v4.1"
    capabilities: dict[str, Capability]
    constraints: Constraints = Field(default_factory=Constraints)
    reference_plans: dict[str, ReferencePlan] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Default registry for Ship Pro (5-stage pipeline)
# ---------------------------------------------------------------------------

def build_default_registry() -> CapabilityRegistry:
    """Build the default Ship Pro capability registry."""
    return CapabilityRegistry(
        capabilities={
            "architect": Capability(
                id="architect",
                category="architecture",
                description="从 Solution Pro 输出中提取统一架构描述，生成 blueprint.json",
                input_schema=InputSchema(required=["input"], optional=[]),
                output_schema=OutputSchema(
                    file="architect",
                    fields=["_meta", "project_type", "project", "modules", "dependencies",
                            "architecture_principles", "platform_capabilities",
                            "principle_coverage", "platform_reuse_map",
                            "domain_details", "sla_constraints", "requirements",
                            "risks", "implementation_hints", "wp_file_mapping"],
                ),
                max_retries=2,
                timeout_minutes=10,
                quality_dimensions=["completeness", "consistency", "feasibility"],
                gate_fn="gate_architect",
                worker_prompt="prompts/architect.md",
            ),
            "decomposer": Capability(
                id="decomposer",
                category="decomposition",
                description="将架构蓝图分解为可执行工作包（DAG 结构）",
                input_schema=InputSchema(
                    required=["architect"],
                    optional=["input"],
                ),
                output_schema=OutputSchema(
                    file="decomposer",
                    fields=["_meta", "work_packages", "dependency_edges",
                            "integration_checkpoints", "self_check",
                            "module_coverage_verification"],
                ),
                max_retries=2,
                timeout_minutes=10,
                quality_dimensions=["granularity", "dependency_clarity", "completeness"],
                gate_fn="gate_decomposer",
                worker_prompt="prompts/decomposer.md",
            ),
            "specifier": Capability(
                id="specifier",
                category="specification",
                description="为工作包生成详细技术规格（含结构化 AC）",
                input_schema=InputSchema(
                    required=["architect", "decomposer"],
                    optional=["input"],
                ),
                output_schema=OutputSchema(
                    file="specifier",
                    fields=["_meta", "work_packages", "self_check"],
                ),
                max_retries=2,
                timeout_minutes=10,
                quality_dimensions=["precision", "testability", "completeness"],
                gate_fn="gate_specifier",
                worker_prompt="prompts/specifier.md",
            ),
            "reviewer": Capability(
                id="reviewer",
                category="review",
                description="独立评审所有产出物的质量（含原则审计 + 平台审计）",
                input_schema=InputSchema(
                    required=["architect", "decomposer", "specifier"],
                    optional=["input"],
                ),
                output_schema=OutputSchema(
                    file="reviewer",
                    fields=["_meta", "verdict", "round", "issues",
                            "quality_metrics", "principle_audit",
                            "platform_audit", "summary"],
                ),
                max_retries=5,
                timeout_minutes=10,
                quality_dimensions=["thoroughness", "actionability"],
                gate_fn="gate_reviewer",
                worker_prompt="prompts/reviewer.md",
            ),
            "packager": Capability(
                id="packager",
                category="package",
                description="打包最终 Ship Package（三层质量报告）",
                input_schema=InputSchema(
                    required=["architect", "specifier", "reviewer"],
                    optional=["decomposer"],
                ),
                output_schema=OutputSchema(
                    file="packager",
                    fields=["schema_version", "meta", "project_context",
                            "work_packages", "dependency_graph",
                            "risk_register", "summary", "quality_report"],
                ),
                max_retries=2,
                timeout_minutes=5,
                quality_dimensions=["completeness", "consistency", "schema_compliance"],
                gate_fn="gate_packager",
                worker_prompt="prompts/packager.md",
            ),
            "judge": Capability(
                id="judge",
                category="judge",
                description="独立 Judge Worker — 对抗性评审，找出 Top-3 风险",
                input_schema=InputSchema(
                    required=["architect", "decomposer", "specifier",
                              "reviewer", "packager"],
                    optional=["input"],
                ),
                output_schema=OutputSchema(
                    file="judge",
                    fields=["_meta", "verdict", "risks", "cross_validation",
                            "downstream_consumability"],
                ),
                max_retries=1,
                timeout_minutes=10,
                quality_dimensions=["risk_detection", "cross_validation"],
                gate_fn="gate_judge",
                worker_prompt="prompts/ship_judge.md",
            ),
            "fixer": Capability(
                id="fixer",
                category="fixer",
                description="架构矛盾修复专家 — 分析 Judge 发现的 critical 矛盾并提出修复方案",
                input_schema=InputSchema(
                    required=["judge", "packager"],
                    optional=["architect", "decomposer", "specifier", "reviewer"],
                ),
                output_schema=OutputSchema(
                    file="fixer",
                    fields=["_meta", "fixes", "updated_package",
                            "remaining_issues"],
                ),
                max_retries=2,
                timeout_minutes=10,
                quality_dimensions=["fix_completeness", "minimal_impact",
                                    "traceability"],
                gate_fn="gate_fixer",
                worker_prompt="prompts/fixer.md",
            ),
        },
        constraints=Constraints(
            required_coverage=["architecture", "review", "package", "judge"],
            budget_minutes=30,
            max_total_retries=15,
            max_parallel_workers=3,
        ),
        reference_plans={
            "standard": ReferencePlan(
                description="标准管线（推荐路径，可偏离）",
                steps=["architect", "decomposer", "specifier", "reviewer",
                       "packager", "judge", "fixer"],
                parallel_hints=[
                    ParallelHint(
                        group=["decomposer", "reviewer"],
                        note="两者输入不冲突，可并行",
                    ),
                ],
                skip_conditions={
                    "specifier": "当 Living Spec 已包含详细规格时可跳过",
                    "decomposer": "当任务足够简单、无需分解时可跳过",
                },
            ),
            "quick_review": ReferencePlan(
                description="快速评审（仅适用于小改动）",
                steps=["reviewer", "packager", "judge"],
                parallel_hints=[],
                skip_conditions={},
            ),
        },
    )


if __name__ == "__main__":
    import json
    registry = build_default_registry()
    print(json.dumps(registry.model_dump(), indent=2, ensure_ascii=False))
