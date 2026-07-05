"""
Spec Pro Gate 函数

门控验证：LLM 输出 → Pydantic 验证 → 格式不对就拦截。

用法:
    from domains.spec_pro.contracts.gate import gate_living_spec, gate_round_result

    # 门控 LivingSpec
    validated, errors = gate_living_spec(data)
    if errors:
        raise ValueError(f"LivingSpec 格式错误: {errors}")
"""

from typing import Any, Tuple
from pydantic import ValidationError

from domains.spec_pro.contracts import (
    LivingSpec,
    RoundResult,
    QualityReport,
    ConversationLog,
    QualityTrajectory,
)


def gate_living_spec(data: dict) -> Tuple[LivingSpec | None, list[str]]:
    """
    门控 LivingSpec

    Returns:
        (validated_model, errors)
        - validated_model: 验证通过的 Pydantic 模型，失败时为 None
        - errors: 错误信息列表，成功时为空
    """
    try:
        validated = LivingSpec(**data)
        return validated, []
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return None, errors


def gate_round_result(data: dict) -> Tuple[RoundResult | None, list[str]]:
    """
    门控 RoundResult

    Returns:
        (validated_model, errors)
    """
    try:
        validated = RoundResult(**data)
        return validated, []
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return None, errors


def gate_quality_report(data: dict) -> Tuple[QualityReport | None, list[str]]:
    """
    门控 QualityReport

    Returns:
        (validated_model, errors)
    """
    try:
        validated = QualityReport(**data)
        return validated, []
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return None, errors


def gate_conversation_log(data: dict) -> Tuple[ConversationLog | None, list[str]]:
    """
    门控 ConversationLog

    Returns:
        (validated_model, errors)
    """
    try:
        validated = ConversationLog(**data)
        return validated, []
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return None, errors


def gate_quality_trajectory(data: dict) -> Tuple[QualityTrajectory | None, list[str]]:
    """
    门控 QualityTrajectory

    Returns:
        (validated_model, errors)
    """
    try:
        validated = QualityTrajectory(**data)
        return validated, []
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        return None, errors


def gate_living_spec_density(spec: LivingSpec) -> Tuple[bool, list[str]]:
    """
    契约笼子：Living Spec 需求密度 Gate
    
    泛化性改进：防止稀疏输入导致下游 Solution Pro 被迫“脑补”需求。
    
    检查维度：
    1. requirement_index 非空（至少有 1 条 REQ）
    2. confirmed.objective 非空
    3. confirmed.success_metrics 非空（至少有可量化的成功标准）
    4. semantic_anchors 非空（至少有 1 个锚点）
    5. core_summary 或 narrative 非空
    
    Returns:
        (passed, issues)
        - passed: True = 密度达标，False = 需要追问用户
        - issues: 不达标的维度列表
    """
    issues = []
    
    # 1. 需求索引非空
    if not spec.requirement_index:
        issues.append("requirement_index 为空 — 至少需要 1 条结构化需求")
    
    # 2. 目标非空
    if not spec.confirmed.objective or len(spec.confirmed.objective.strip()) < 10:
        issues.append("confirmed.objective 太短或为空 — 需要明确的项目目标（≥10 字）")
    
    # 3. 成功指标非空
    if not spec.confirmed.success_metrics:
        issues.append("confirmed.success_metrics 为空 — 至少需要 1 条可量化的成功标准")
    
    # 4. Semantic Anchors 非空
    if not spec.semantic_anchors:
        issues.append("semantic_anchors 为空 — 至少需要 1 个语义锚点（如平台 API、架构原则）")
    
    # 5. 叙述内容非空
    if not spec.core_summary and not spec.narrative:
        issues.append("core_summary 和 narrative 都为空 — 需要需求叙述内容")
    
    passed = len(issues) == 0
    return passed, issues
