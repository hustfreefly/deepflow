"""
Spec Pro Gate 函数

门控验证:LLM 输出 → Pydantic 验证 → 格式不对就拦截。

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
        - validated_model: 验证通过的 Pydantic 模型,失败时为 None
        - errors: 错误信息列表,成功时为空
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


def gate_living_spec_density(spec: LivingSpec) -> dict:
    """
    契约笼子：Living Spec 需求密度 Gate
    
    泛化性改进：防止稀疏输入导致下游 Solution Pro 被迫"脑补"需求。
    
    检查维度（5 维，4/5 通过即达标）：
    1. requirement_index 非空（至少有 1 条 REQ）       [硬检查]
    2. confirmed.objective 非空（≥10 字）              [硬检查]
    3. confirmed.success_metrics 非空                   [硬检查]
    4. core_summary 或 narrative 非空                   [硬检查]
    5. semantic_anchors 非空                            [软检查，不单独阻断]
    
    通过条件：4 个硬检查全部通过（软检查不影响 passed）。
    
    Returns:
        dict:
            passed: bool — 密度是否达标
            issues: list[str] — 不达标的维度描述
            score: float — 密度得分 (0.0-1.0)
            warnings: list[str] — 非阻断性警告
    """
    issues = []
    warnings = []
    passed_count = 0
    total_hard = 4  # 硬检查数量

    # 1. 需求索引非空 [硬]
    if not spec.requirement_index:
        issues.append("requirement_index 为空 — 至少需要 1 条结构化需求")
    else:
        passed_count += 1

    # 2. 目标非空 [硬]
    if not spec.confirmed.objective or len(spec.confirmed.objective.strip()) < 10:
        issues.append("confirmed.objective 太短或为空 — 需要明确的项目目标（≥10 字）")
    else:
        passed_count += 1

    # 3. 成功指标非空 [硬]
    if not spec.confirmed.success_metrics:
        issues.append("confirmed.success_metrics 为空 — 至少需要 1 条可量化的成功标准")
    else:
        passed_count += 1

    # 4. 叙述内容非空 [硬]
    if not spec.core_summary and not spec.narrative:
        issues.append("core_summary 和 narrative 都为空 — 需要需求叙述内容")
    else:
        passed_count += 1

    # 5. Semantic Anchors 非空 [软检查 — 警告但不阻断]
    if not spec.semantic_anchors:
        warnings.append("semantic_anchors 为空 — 建议添加语义锚点（如平台 API、架构原则）以增强下游信息守恒")
    else:
        passed_count += 1

    # 通过条件：4 个硬检查全部通过
    passed = passed_count >= total_hard
    score = passed_count / 5.0

    return {
        "passed": passed,
        "issues": issues,
        "score": round(score, 2),
        "warnings": warnings,
    }
