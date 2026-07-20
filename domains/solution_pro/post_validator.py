"""
Solution Pro Post-Validator (V3 单一路径架构)

Agent 完成后的 Python 后置验证层。
检查项：Schema、需求覆盖率、信息守恒。

调用方式：
    from domains.solution_pro.post_validator import validate_solution_output
    result = validate_solution_output(bb)
"""

from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


def validate_solution_output(bb) -> Dict[str, Any]:
    """
    验证 Solution Pro Agent Orchestrator 的输出质量。

    检查项（按严重度排序）：
    1. Schema 验证 — final_solution 结构和必要字段
    2. 需求覆盖率 — requirement_index 中的需求是否在输出中被覆盖
    3. 信息守恒 — semantic_anchors 是否保留

    Args:
        bb: BlackboardManager 实例

    Returns:
        {
            "passed": bool,
            "failures": [{"severity": str, "check": str, "message": str}],
            "summary": {"total_checks": int, "passed": int, "failed": int}
        }
    """
    failures: List[Dict[str, str]] = []
    total_checks = 0
    passed_checks = 0

    # ── 1. Schema 验证 ──────────────────────────────────────────────
    total_checks += 1
    schema_failures = _validate_schema(bb)
    if schema_failures:
        failures.extend(schema_failures)
    else:
        passed_checks += 1

    # ── 2. 需求覆盖率 ───────────────────────────────────────────────
    total_checks += 1
    coverage_failures = _validate_requirement_coverage(bb)
    if coverage_failures:
        failures.extend(coverage_failures)
    else:
        passed_checks += 1

    # ── 3. 信息守恒 ─────────────────────────────────────────────────
    total_checks += 1
    conservation_failures = _validate_information_conservation(bb)
    if conservation_failures:
        failures.extend(conservation_failures)
    else:
        passed_checks += 1

    passed = len(failures) == 0

    result = {
        "passed": passed,
        "failures": failures,
        "summary": {
            "total_checks": total_checks,
            "passed": passed_checks,
            "failed": total_checks - passed_checks,
        },
    }

    # P1-FIX: 持久化 L0 验证结果到 blackboard stage，支持审计
    try:
        bb.write_stage('l0_validation_result', result)
    except Exception as e:
        logger.warning(f"Failed to write L0 validation result to stage: {e}")

    return result


def _validate_schema(bb) -> List[Dict[str, str]]:
    """验证 final_solution 的结构和必要字段"""
    failures = []

    # 读取 final_solution（可能是 JSON dict 或不存在）
    final_solution = bb.read_stage("final_solution")

    if final_solution is None:
        failures.append({
            "severity": "critical",
            "check": "schema",
            "message": "final_solution 不存在（Agent 未完成或输出丢失）",
        })
        return failures

    if not isinstance(final_solution, dict):
        failures.append({
            "severity": "critical",
            "check": "schema",
            "message": f"final_solution 类型错误: {type(final_solution).__name__}（应为 dict）",
        })
        return failures

    # 检查必要字段
    required_fields = ["key_decisions", "implementation_phases"]
    for field in required_fields:
        if field not in final_solution:
            failures.append({
                "severity": "critical",
                "check": "schema",
                "message": f"final_solution 缺少必要字段: {field}",
            })

    # 检查字段类型
    if "key_decisions" in final_solution:
        kd = final_solution["key_decisions"]
        if not isinstance(kd, list):
            failures.append({
                "severity": "critical",
                "check": "schema",
                "message": f"key_decisions 类型错误: {type(kd).__name__}（应为 list）",
            })
        elif len(kd) == 0:
            failures.append({
                "severity": "warning",
                "check": "schema",
                "message": "key_decisions 为空列表",
            })

    if "implementation_phases" in final_solution:
        ip = final_solution["implementation_phases"]
        if not isinstance(ip, list):
            failures.append({
                "severity": "critical",
                "check": "schema",
                "message": f"implementation_phases 类型错误: {type(ip).__name__}（应为 list）",
            })
        elif len(ip) == 0:
            failures.append({
                "severity": "warning",
                "check": "schema",
                "message": "implementation_phases 为空列表",
            })

    return failures


def _validate_requirement_coverage(bb) -> List[Dict[str, str]]:
    """验证 requirement_index 中的需求是否在输出中被覆盖"""
    failures = []

    # 从 living_spec 或 frozen_spec 读取 requirement_index
    living_spec = bb.read_json("data/living_spec.json") or {}
    requirement_index = living_spec.get("requirement_index", [])

    if not requirement_index:
        frozen_spec = bb.read_json("data/frozen_spec.json") or {}
        requirement_index = frozen_spec.get("requirement_index", [])

    if not requirement_index:
        failures.append({
            "severity": "warning",
            "check": "requirement_coverage",
            "message": "requirement_index 为空（无法验证覆盖率）",
        })
        return failures

    # 读取 final_solution 的内容（用于检查覆盖）
    final_solution = bb.read_stage("final_solution") or {}

    # 将 final_solution 转为字符串用于文本匹配
    solution_text = str(final_solution)

    # 检查每个 requirement 是否被提及
    total_reqs = len(requirement_index)
    covered = 0
    uncovered_ids = []

    for req in requirement_index:
        req_id = req.get("id", "") if isinstance(req, dict) else str(req)
        # 检查 req_id 是否出现在 solution_text 中
        if req_id and req_id in solution_text:
            covered += 1
        else:
            uncovered_ids.append(req_id)

    coverage_rate = covered / total_reqs if total_reqs > 0 else 1.0

    if coverage_rate < 0.5:
        failures.append({
            "severity": "critical",
            "check": "requirement_coverage",
            "message": (
                f"需求覆盖率 {coverage_rate:.0%}（{covered}/{total_reqs}），"
                f"低于 50% 阈值。未覆盖: {uncovered_ids[:5]}..."
            ),
        })
    elif coverage_rate < 0.8:
        failures.append({
            "severity": "warning",
            "check": "requirement_coverage",
            "message": (
                f"需求覆盖率 {coverage_rate:.0%}（{covered}/{total_reqs}），"
                f"低于 80% 目标。未覆盖: {uncovered_ids[:5]}..."
            ),
        })

    return failures


def _validate_information_conservation(bb) -> List[Dict[str, str]]:
    """验证 semantic_anchors 是否保留在输出中"""
    failures = []

    # 从 living_spec 读取 semantic_anchors
    living_spec = bb.read_json("data/living_spec.json") or {}
    semantic_anchors = living_spec.get("semantic_anchors", [])

    if not semantic_anchors:
        frozen_spec = bb.read_json("data/frozen_spec.json") or {}
        semantic_anchors = frozen_spec.get("semantic_anchors", [])

    if not semantic_anchors:
        # 没有 semantic_anchors 需要检查，跳过
        return failures

    # 读取 final_solution 内容
    final_solution = bb.read_stage("final_solution") or {}
    solution_text = str(final_solution)

    # 检查每个 anchor 是否被保留
    total_anchors = len(semantic_anchors)
    preserved = 0
    missing_names = []

    for anchor in semantic_anchors:
        # anchor 可能是 dict（{name, category, ...}）或 str
        if isinstance(anchor, dict):
            anchor_name = anchor.get("name", "") or anchor.get("text", "")
        else:
            anchor_name = str(anchor)

        if anchor_name and anchor_name in solution_text:
            preserved += 1
        else:
            missing_names.append(anchor_name[:50])

    conservation_rate = preserved / total_anchors if total_anchors > 0 else 1.0

    if conservation_rate < 0.5:
        failures.append({
            "severity": "critical",
            "check": "information_conservation",
            "message": (
                f"信息守恒率 {conservation_rate:.0%}（{preserved}/{total_anchors}），"
                f"低于 50% 阈值。丢失: {missing_names[:5]}..."
            ),
        })
    elif conservation_rate < 0.8:
        failures.append({
            "severity": "warning",
            "check": "information_conservation",
            "message": (
                f"信息守恒率 {conservation_rate:.0%}（{preserved}/{total_anchors}），"
                f"低于 80% 目标。丢失: {missing_names[:5]}..."
            ),
        })

    return failures
