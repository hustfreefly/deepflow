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


def compute_complexity_score(living_spec: dict) -> dict:
    """
    确定性计算 LivingSpec 的复杂度分数。
    从 LLM 移至代码，因为这是纯计数+加分操作。
    """
    confirmed = (living_spec or {}).get("confirmed", {})
    score = 0
    factors: list[str] = []

    # users 角色数
    users = confirmed.get("users", [])
    if len(users) >= 3:
        score += 15
        factors.append(f"{len(users)} 个用户角色 (+15)")

    # capabilities 总数
    caps = confirmed.get("capabilities", {})
    total_caps = (
        len(caps.get("always_do", []))
        + len(caps.get("should_do", []))
        + len(caps.get("never_do", []))
    )
    if total_caps >= 5:
        score += 15
        factors.append(f"{total_caps} 项能力要求 (+15)")

    # quality_attributes 数量
    qa = confirmed.get("quality_attributes", [])
    if len(qa) >= 3:
        score += 10
        factors.append(f"{len(qa)} 项质量属性 (+10)")

    # constraints 数量
    constraints = confirmed.get("constraints", {})
    total_constraints = sum(
        len(v) if isinstance(v, list) else 1 for v in constraints.values()
    )
    if total_constraints >= 3:
        score += 10
        factors.append(f"{total_constraints} 项约束 (+10)")

    # inferred 数量
    inferred = (living_spec or {}).get("inferred", [])
    if len(inferred) >= 5:
        score += 10
        factors.append(f"{len(inferred)} 项推断需求 (+10)")

    # semantic_anchors 数量
    anchors = (living_spec or {}).get("semantic_anchors", [])
    if len(anchors) >= 3:
        score += 10
        factors.append(f"{len(anchors)} 个语义锚点 (+10)")

    # 路由建议
    final_score = min(score, 100)
    if final_score >= 60:
        engine = "solution_pro"
        mode = "full"
    elif final_score >= 30:
        engine = "solution_pro"
        mode = "standard"
    else:
        engine = "direct"
        mode = "simple"

    return {
        "complexity_score": final_score,
        "complexity_factors": factors,
        "suggested_engine": engine,
        "suggested_mode": mode,
    }


def gate_harness_decision(layer1_result: dict, layer2_scores: dict) -> dict:
    """
    Layer 3: 合并 Layer 1（代码结构检查）和 Layer 2（LLM 语义判断）的结果。

    Args:
        layer1_result: gate_living_spec_density() 的输出
        layer2_scores: LLM 输出的评分，优先从 meta_quality 读取，fallback 到 dimension_scores

    Returns:
        最终决策：PASS / WARN / SOFT_BLOCK / HARD_BLOCK
    """
    l1_passed = layer1_result.get("passed", False)

    # 兼容 dimensions 数组格式（来自 assess.md 输出）
    if 'dimensions' in layer2_scores and isinstance(layer2_scores['dimensions'], list):
        l2_scores = {
            d.get('dimension', d.get('name', '')): d.get('score', 50)
            for d in layer2_scores['dimensions']
            if isinstance(d, dict)
        }
        meta_source = "dimensions_array"
    # 优先从 meta_quality 读取（assess.md 新输出），fallback 到 dimension_scores
    elif layer2_scores.get("meta_quality"):
        meta = layer2_scores["meta_quality"]
        l2_scores = {dim: meta[dim].get("score", 50) for dim in meta}
        meta_source = "meta_quality"
    else:
        l2_scores = layer2_scores.get("dimension_scores", {})
        meta_source = "dimension_scores"

    # Layer 2 加权平均
    weights = {
        "clarity": 0.25,
        "completeness": 0.25,
        "executability": 0.20,
        "consistency": 0.15,
        "downstream_fitness": 0.15,
    }

    weighted_sum = sum(
        l2_scores.get(dim, 50) * weight
        for dim, weight in weights.items()
    )

    # Layer 1 不通过 → 至少 WARN
    if not l1_passed:
        decision = "WARN" if weighted_sum >= 60 else "SOFT_BLOCK"
    elif weighted_sum >= 75:
        decision = "PASS"
    elif weighted_sum >= 60:
        decision = "WARN"
    elif weighted_sum >= 45:
        decision = "SOFT_BLOCK"
    else:
        decision = "HARD_BLOCK"

    return {
        "decision": decision,
        "layer1_passed": l1_passed,
        "layer2_weighted_score": round(weighted_sum, 1),
        "layer2_scores": l2_scores,
        "meta_quality_source": meta_source,
    }
