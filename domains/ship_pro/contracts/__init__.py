"""
Ship Pro 契约层 (Contract Layer)

Pydantic 模型作为唯一真相源 (Single Source of Truth)。

从此处自动生成:
1. JSON Schema → schemas/ 目录
2. Prompt 中的输出格式段落 → .md 文件
3. Gate 字段检查清单 → gates.py 引用

用法:
    from domains.ship_pro.contracts import ArchitectOutput, ShipPackage

    # 验证数据
    validated = ArchitectOutput(**data)

    # 生成 Schema
    schema = ShipPackage.model_json_schema()

    # 检查一致性
    from domains.ship_pro.contracts.generator import check_schema_consistency
    issues = check_schema_consistency(ShipPackage, "schemas/ship_package_v3.schema.json")
"""

from domains.ship_pro.contracts.architect import (
    ArchitectOutput,
    ArchitectMeta,
    DataSufficiency,
    Project,
    Module,
    Dependency,
    Requirement,
    SLAConstraint,
    Risk,
    ImplementationHint,
)

from domains.ship_pro.contracts.reviewer import (
    ReviewerOutput,
    Issue,
    QualityMetrics,
)

from domains.ship_pro.contracts.packager import (
    ShipPackage,
    PackageMeta,
    Generator,
    ProjectContext,
    Architecture,
    ArchitectureComponent,
    RequirementsCoverage,
    RequirementCoverageItem,
    WorkPackage,
    Budget,
    OutputArtifact,
    AcceptanceTest,
    RetryPolicy,
    DependencyGraph,
    DependencyEdge,
    RiskRegisterItem,
    PackageSummary,
    ComplexityDistribution,
    QualityReport,
    Layer1Structural,
    Layer2Semantic,
    Layer3Actionable,
    QualityIssue,
)

__all__ = [
    # Architect
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
    # Reviewer
    "ReviewerOutput",
    "Issue",
    "QualityMetrics",
    # Packager
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
