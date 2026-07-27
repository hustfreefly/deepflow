"""
Solution Pro Post-Validator (V3 单一路径架构)

Agent 完成后的 Python 后置验证层。
检查项：Schema、需求覆盖率、信息守恒。

调用方式：
    from domains.solution_pro.post_validator import validate_solution_output
    result = validate_solution_output(bb)

V4 重构：调用 core.quality_utils 通用函数，减少重复逻辑。
"""

from typing import Dict, List, Any, Optional
import logging

# V4: 导入通用函数
from core.quality_utils import (
    check_schema as _quality_check_schema,
    check_coverage as _quality_check_coverage,
    check_anchors as _quality_check_anchors,
)

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
    """验证 final_solution 的结构和必要字段（V4: 调用 quality_utils + Pydantic Cage 验证）"""
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

    # V4: 调用通用函数
    required_fields = ["key_decisions", "implementation_phases"]
    field_types = {"key_decisions": list, "implementation_phases": list}
    result = _quality_check_schema(final_solution, required_fields, field_types)

    if not result.passed:
        # 转换 severity: ERROR → critical
        severity = "critical" if result.severity == "ERROR" else "warning"
        failures.append({
            "severity": severity,
            "check": "schema",
            "message": result.message,
        })

    # 额外检查：空列表警告（保留原有逻辑）
    if "key_decisions" in final_solution:
        kd = final_solution["key_decisions"]
        if isinstance(kd, list) and len(kd) == 0:
            failures.append({
                "severity": "warning",
                "check": "schema",
                "message": "key_decisions 为空列表",
            })

    if "implementation_phases" in final_solution:
        ip = final_solution["implementation_phases"]
        if isinstance(ip, list) and len(ip) == 0:
            failures.append({
                "severity": "critical",
                "check": "schema",
                "message": "implementation_phases 为空列表，必须包含至少 1 个阶段",
            })
    else:
        failures.append({
            "severity": "critical",
            "check": "schema",
            "message": "implementation_phases 字段缺失，必须包含至少 1 个阶段",
        })

    # P1-FIX: Pydantic 完整验证 — 触发 Cage 验证器 (FS1/FS2/FS3)
    # 基础字段检查无法捕获语义级错误（如覆盖率不一致、提取失败未标注等）
    try:
        from domains.solution_pro.schemas.schemas import FinalSolutionSchema
        FinalSolutionSchema(**final_solution)
    except Exception as e:
        failures.append({
            "severity": "critical",
            "check": "pydantic_validation",
            "message": f"FinalSolutionSchema 验证失败: {e}",
        })

    return failures


def _validate_requirement_coverage(bb) -> List[Dict[str, str]]:
    """验证 requirement_index 中的需求是否在输出中被覆盖（V4: 调用 quality_utils）"""
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

    # 提取需求 ID 列表
    req_ids = []
    for req in requirement_index:
        req_id = req.get("id", "") if isinstance(req, dict) else str(req)
        if req_id:
            req_ids.append(req_id)

    # 读取 final_solution 的内容（用于检查覆盖）
    final_solution = bb.read_stage("final_solution") or {}

    # V4: 调用通用函数（双层阈值：0.5 critical, 0.8 warning）
    result = _quality_check_coverage(req_ids, final_solution, critical_threshold=0.5, warning_threshold=0.8)

    if result.severity == "CRITICAL":
        failures.append({
            "severity": "critical",
            "check": "requirement_coverage",
            "message": (
                f"需求覆盖率 {result.coverage_rate:.0%}（{result.covered_reqs}/{result.total_reqs}），"
                f"低于 50% 阈值。未覆盖: {result.uncovered[:5]}..."
            ),
        })
    elif result.severity == "WARNING":
        failures.append({
            "severity": "warning",
            "check": "requirement_coverage",
            "message": (
                f"需求覆盖率 {result.coverage_rate:.0%}（{result.covered_reqs}/{result.total_reqs}），"
                f"低于 80% 目标。未覆盖: {result.uncovered[:5]}..."
            ),
        })

    return failures


def _validate_information_conservation(bb) -> List[Dict[str, str]]:
    """验证 semantic_anchors 是否保留在输出中（V4: 调用 quality_utils）"""
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

    # 提取锚点名称列表（处理 dict 和 str 两种格式）
    anchor_names = []
    for anchor in semantic_anchors:
        if isinstance(anchor, dict):
            anchor_name = anchor.get("name", "") or anchor.get("text", "")
        else:
            anchor_name = str(anchor)
        if anchor_name:
            anchor_names.append(anchor_name)

    if not anchor_names:
        return failures

    # 读取 final_solution 内容
    final_solution = bb.read_stage("final_solution") or {}

    # V4: 调用通用函数（双层阈值：0.5 critical, 0.8 warning）
    result = _quality_check_anchors(anchor_names, final_solution, critical_threshold=0.5, warning_threshold=0.8)

    if result.severity == "CRITICAL":
        # 提取丢失的锚点名称
        missing_names = [a[:50] for a in anchor_names if a.lower() not in str(final_solution).lower()][:5]
        failures.append({
            "severity": "critical",
            "check": "information_conservation",
            "message": (
                f"信息守恒率低于 50% 阈值。丢失: {missing_names}..."
            ),
        })
    elif result.severity == "WARNING":
        missing_names = [a[:50] for a in anchor_names if a.lower() not in str(final_solution).lower()][:5]
        failures.append({
            "severity": "warning",
            "check": "information_conservation",
            "message": (
                f"信息守恒率低于 80% 目标。丢失: {missing_names}..."
            ),
        })

    return failures
