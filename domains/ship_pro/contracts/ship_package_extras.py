"""
Ship Package Extras V3 — Pydantic Contracts
Based on 3 AI Native expert reviews.

New fields for Packager output:
1. api_conventions (LLM + anchoring + override)
2. integration_tests (LLM + component anchoring)
3. error_handling_principles (LLM + project-level)
4. environment (deterministic, 0 LLM)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# 1. API Conventions
# ---------------------------------------------------------------------------

class NamingStyle(str, Enum):
    SNAKE_CASE = "snake_case"
    CAMEL_CASE = "camelCase"
    PASCAL_CASE = "PascalCase"


class ParameterStyle(str, Enum):
    DICT = "dict"
    KWARGS = "kwargs"
    POSITIONAL = "positional"
    DATACLASS = "dataclass"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConventionOverride(BaseModel):
    """Hermes can mark a rule as overridden during execution."""
    rule_index: int = Field(description="Index of the overridden rule")
    reason: str = Field(description="Why this rule doesn't work")
    alternative: str = Field(description="What Hermes used instead")


class ApiExample(BaseModel):
    """Positive/negative example pair."""
    correct: str
    incorrect: str
    explanation: str = ""


class ApiConventions(BaseModel):
    """API naming conventions (LLM-generated with WP anchoring)."""
    naming_style: NamingStyle
    method_prefixes: dict[str, list[str]] = Field(
        description="Map operation type to allowed prefixes",
        default_factory=lambda: {
            "write": ["write_", "set_", "save_"],
            "read": ["read_", "get_", "load_"],
            "validate": ["check_", "validate_", "verify_"],
        },
    )
    parameter_style: ParameterStyle = ParameterStyle.DICT
    rules: list[str] = Field(
        description="5-8 consistency rules, must reference actual WP module names",
        min_length=5,
        max_length=8,
    )
    examples: list[ApiExample] = Field(
        description="3-5 positive/negative example pairs",
        min_length=3,
        max_length=5,
    )
    confidence: Confidence = Confidence.HIGH
    convention_overrides: list[ConventionOverride] = Field(
        default_factory=list,
        description="Filled by Hermes during execution",
    )


# ---------------------------------------------------------------------------
# 2. Integration Tests
# ---------------------------------------------------------------------------

class IntegrationTest(BaseModel):
    """Integration test definition (LLM-generated with component anchoring)."""
    name: str
    description: str
    components: list[str] = Field(
        description="Component IDs, must exist in work_packages",
        min_length=2,
    )
    scenario: str
    expected_result: str = Field(
        description="Must contain quantifiable metrics, no vague language",
    )
    confidence: Confidence = Confidence.HIGH

    @field_validator("expected_result")
    @classmethod
    def no_vague_result(cls, v: str) -> str:
        vague_words = ["正常", "符合预期", "工作良好", "没有问题", "正常启动"]
        for word in vague_words:
            if word in v:
                raise ValueError(
                    f"expected_result contains vague term '{word}'. "
                    f"Use quantifiable metrics instead."
                )
        return v


# ---------------------------------------------------------------------------
# 3. Error Handling Principles
# ---------------------------------------------------------------------------

class ErrorHandlingPrinciples(BaseModel):
    """Project-level error handling principles (LLM-generated)."""
    principles: list[str] = Field(
        description="3-5 project-level principles",
        min_length=3,
        max_length=5,
    )
    exception_categories: list[str] = Field(
        description="Exception categories (count <= WP_count * 0.5)",
    )
    max_retry_limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Global retry limit",
    )
    confidence: Confidence = Confidence.HIGH


# ---------------------------------------------------------------------------
# 4. Environment Spec (Deterministic, 0 LLM)
# ---------------------------------------------------------------------------

class EnvironmentSpec(BaseModel):
    """Environment specification (deterministic generation, no LLM)."""
    python: str = Field(
        default=">=3.10",
        description="Python version constraint",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Third-party dependencies (scanned from imports)",
    )
    test_dependencies: list[str] = Field(
        default_factory=lambda: ["pytest>=7.0"],
    )
    test_runner: str = "pytest"
    test_command: str = "pytest -v"


# ---------------------------------------------------------------------------
# Packager output extension
# ---------------------------------------------------------------------------

class ShipPackageExtras(BaseModel):
    """Extension fields for Packager output."""
    api_conventions: Optional[ApiConventions] = None
    integration_tests: Optional[list[IntegrationTest]] = None
    error_handling_principles: Optional[ErrorHandlingPrinciples] = None
    environment: Optional[EnvironmentSpec] = None


if __name__ == "__main__":
    import json

    # Example
    extras = ShipPackageExtras(
        api_conventions=ApiConventions(
            naming_style=NamingStyle.SNAKE_CASE,
            rules=[
                "所有写入操作以 write_ 开头，接受字典参数",
                "所有读取操作以 read_ 开头，返回完整状态",
                "所有验证操作统一使用 check_ 前缀",
                "队列操作统一使用 put/get",
                "路由操作接受枚举类型而非字符串",
            ],
            examples=[
                ApiExample(
                    correct="blackboard.write_state({'key': 'value'})",
                    incorrect="blackboard.write('key', 'value')",
                    explanation="write_state 接受字典，不拆分为 key/value 参数",
                ),
            ],
        ),
        integration_tests=[
            IntegrationTest(
                name="Task Loop E2E",
                description="End-to-end task loop execution",
                components=["input_gate", "model_router", "dag_decomposer"],
                scenario="Process a request through full pipeline",
                expected_result="Output latency < 5000ms, all stages completed",
            ),
        ],
        error_handling_principles=ErrorHandlingPrinciples(
            principles=[
                "所有外部 API 调用必须有重试机制",
                "错误必须包含上下文信息（模块名、操作名）",
                "关键路径错误必须上抛，不静默吞掉",
            ],
            exception_categories=[
                "ValidationError",
                "ExternalServiceError",
                "CircuitBreakerOpen",
            ],
            max_retry_limit=3,
        ),
        environment=EnvironmentSpec(
            dependencies=["pydantic>=2.0"],
        ),
    )

    print(json.dumps(extras.model_dump(), indent=2, ensure_ascii=False))
