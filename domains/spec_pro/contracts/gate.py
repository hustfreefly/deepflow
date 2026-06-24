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
