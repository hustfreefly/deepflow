"""Deterministic REQ-ID frozen spec generation for Solution Pro."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# ============================================================================
# V2.0: 二级分组映射（12 category → 5 group）
# ============================================================================

GROUP_MAP = {
    "Core": {
        "description": "核心目标、痛点、场景",
        "categories": ["objective", "pain_point", "scenario"],
    },
    "Functional": {
        "description": "功能需求、集成需求",
        "categories": ["capability", "integration"],
    },
    "NonFunctional": {
        "description": "质量属性、约束条件、成功指标",
        "categories": ["quality_attribute", "constraint", "success_metric"],
    },
    "Boundaries": {
        "description": "禁止项、行为边界",
        "categories": ["prohibition", "guardrail", "guardrail_prohibition"],
    },
    "Context": {
        "description": "用户画像、风险、假设、提示",
        "categories": ["user", "risk", "assumption", "hint"],
    },
}


def _add_requirement(
    requirements: List[Dict[str, Any]],
    category: str,
    description: Any,
    priority: str = "P1",
    source: str = "fallback",
    measurable: str = "",
) -> None:
    text = str(description or "").strip()
    if not text:
        return
    requirements.append({
        "id": f"REQ-{len(requirements) + 1:03d}",
        "category": category,
        "description": text,
        "priority": priority or "P1",
        "source": source,
        "measurable": str(measurable or ""),
    })


def build_frozen_spec(topic: str, constraints: List[str] | None = None,
                      living_spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build a stable requirements contract from confirmed user input."""
    constraints = constraints or []
    confirmed = (living_spec or {}).get("confirmed", {}) if isinstance(living_spec, dict) else {}
    requirements: List[Dict[str, Any]] = []

    _add_requirement(requirements, "objective", confirmed.get("objective") or topic, "P0", "topic")

    capabilities = confirmed.get("capabilities", {}) if isinstance(confirmed.get("capabilities", {}), dict) else {}
    for item in capabilities.get("always_do", []) or []:
        _add_requirement(requirements, "capability", item, "P0", "living_spec.confirmed.capabilities.always_do")
    for item in capabilities.get("should_do", []) or []:
        _add_requirement(requirements, "capability", item, "P1", "living_spec.confirmed.capabilities.should_do")
    for item in capabilities.get("never_do", []) or []:
        _add_requirement(requirements, "prohibition", item, "P0", "living_spec.confirmed.capabilities.never_do")

    for qa in confirmed.get("quality_attributes", []) or []:
        if isinstance(qa, dict):
            desc = qa.get("spec") or qa.get("description") or qa.get("category")
            priority = qa.get("priority", "P1")
            measurable = qa.get("target") or qa.get("metric") or ""
        else:
            desc = qa
            priority = "P1"
            measurable = ""
        _add_requirement(requirements, "quality_attribute", desc, priority, "living_spec.confirmed.quality_attributes", measurable)

    confirmed_constraints = confirmed.get("constraints", {}) if isinstance(confirmed.get("constraints", {}), dict) else {}
    for key in ("budget", "timeline"):
        if confirmed_constraints.get(key):
            _add_requirement(requirements, "constraint", f"{key}: {confirmed_constraints[key]}", "P0", "living_spec.confirmed.constraints")
    for item in confirmed_constraints.get("tech_stack", []) or []:
        _add_requirement(requirements, "constraint", f"tech_stack: {item}", "P1", "living_spec.confirmed.constraints.tech_stack")

    integration = confirmed.get("integration", {}) if isinstance(confirmed.get("integration", {}), dict) else {}
    for item in integration.get("requirements", []) or []:
        _add_requirement(requirements, "integration", item, "P1", "living_spec.confirmed.integration.requirements")

    # Pain points → 方案要解决的为什么
    for item in confirmed.get("pain_points", []) or []:
        _add_requirement(requirements, "pain_point", item, "P1", "living_spec.confirmed.pain_points")

    # Success metrics → 做对的标准
    for item in confirmed.get("success_metrics", []) or []:
        measurable = item.get("target", "") if isinstance(item, dict) else ""
        desc = item.get("metric", "") if isinstance(item, dict) else item
        _add_requirement(requirements, "success_metric", desc, "P1",
                         "living_spec.confirmed.success_metrics", measurable)

    # Users → 用户画像
    for item in confirmed.get("users", []) or []:
        if isinstance(item, dict):
            desc = item.get("role", "") or item.get("description", "")
        else:
            desc = str(item)
        if desc:
            _add_requirement(requirements, "user", desc, "P1", "living_spec.confirmed.users")

    # Key scenarios → 核心使用场景
    for item in confirmed.get("key_scenarios", []) or []:
        _add_requirement(requirements, "scenario", item, "P1", "living_spec.confirmed.key_scenarios")

    # Risks and assumptions → 风险和假设
    ra = confirmed.get("risks_and_assumptions", {}) if isinstance(confirmed.get("risks_and_assumptions", {}), dict) else {}
    for item in ra.get("risks", []) or []:
        desc = item.get("description", "") if isinstance(item, dict) else str(item)
        if desc:
            _add_requirement(requirements, "risk", desc, "P1", "living_spec.confirmed.risks_and_assumptions.risks")
    for item in ra.get("assumptions", []) or []:
        desc = item.get("description", "") if isinstance(item, dict) else str(item)
        if desc:
            _add_requirement(requirements, "assumption", desc, "P1", "living_spec.confirmed.risks_and_assumptions.assumptions")

    # Guardrails → 行为边界（guardrails 是顶层字段，不在 confirmed 下）
    guardrails = (living_spec or {}).get("guardrails", {}) if isinstance(living_spec, dict) else {}
    if isinstance(guardrails, dict):
        for item in guardrails.get("always_do", []) or []:
            _add_requirement(requirements, "guardrail", item, "P0", "living_spec.guardrails.always_do")
        for item in guardrails.get("never_do", []) or []:
            _add_requirement(requirements, "guardrail_prohibition", item, "P0", "living_spec.guardrails.never_do")

    # Solution Pro hints → Spec Pro 给下游的提示
    hints = (living_spec or {}).get("solution_pro_hints", None) if isinstance(living_spec, dict) else None
    if hints:
        if isinstance(hints, str):
            _add_requirement(requirements, "hint", hints, "P1", "living_spec.solution_pro_hints")
        elif isinstance(hints, dict):
            for key, value in hints.items():
                _add_requirement(requirements, "hint", f"{key}: {value}", "P1", f"living_spec.solution_pro_hints.{key}")

    for item in constraints:
        _add_requirement(requirements, "constraint", item, "P1", "input.constraints")

    if not requirements:
        _add_requirement(requirements, "objective", topic, "P0", "topic")

    # ====================================================================
    # V2.0: 合并 LLM 标注（如果存在）
    # ====================================================================
    annotations = confirmed.get("requirement_annotations") if isinstance(confirmed, dict) else None
    if annotations and isinstance(annotations, list):
        requirements = _merge_annotations(requirements, annotations)

    # ====================================================================
    # V2.0: 构建 executive_summary（指针 + 上下文）
    # ====================================================================
    executive_summary = _build_executive_summary(confirmed, requirements, topic, living_spec)

    # V2.0: 构建 requirement_groups（二级分组）
    requirement_groups = _build_requirement_groups(requirements)

    # V2.0: 透传 guardrails 和 solution_pro_hints
    guardrails_raw = (living_spec or {}).get("guardrails", {}) if isinstance(living_spec, dict) else {}
    solution_pro_hints_raw = (living_spec or {}).get("solution_pro_hints", None) if isinstance(living_spec, dict) else None

    return {
        "version": "2.0",
        "generated_at": datetime.now().isoformat(),
        "topic": topic,
        "source": "living_spec.confirmed+topic+constraints",
        "executive_summary": executive_summary,
        "guardrails": guardrails_raw,
        "solution_pro_hints": solution_pro_hints_raw,
        "requirements": requirements,
        "requirement_groups": requirement_groups,
        "coverage_policy": {
            "worker_field": "covered_req_ids",
            "matrix_path": "requirements_traceability_matrix.json",
            "harness_final_must_check_all_p0": True,
        },
    }


# ============================================================================
# V2.0: executive_summary 构建（指针 + 上下文模式）
# ============================================================================

def _build_executive_summary(
    confirmed: Dict[str, Any],
    requirements: List[Dict[str, Any]],
    topic: str,
    living_spec: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    构建 executive_summary（指针 + 上下文模式）。

    - 指针字段：用 REQ-ID 引用（objective_req, key_scenarios_reqs）
    - 上下文字段：从 confirmed 提取补充信息（why, for_whom, success_criteria, constraints）
    - 场景 B：living_spec=None 时生成 minimal 版本
    """
    # 判断是否有 living_spec（场景 A vs 场景 B）
    has_living_spec = isinstance(living_spec, dict) and living_spec.get("confirmed")

    # --- 指针字段 ---
    # objective_req: 指向第一条 objective 类型的 REQ
    objective_req = ""
    for req in requirements:
        if req.get("category") == "objective":
            objective_req = req["id"]
            break

    # key_scenarios_reqs: 指向所有 scenario 类型的 REQ
    key_scenarios_reqs = [
        req["id"] for req in requirements if req.get("category") == "scenario"
    ]

    # --- 上下文字段 ---
    # why: 从 pain_points 提取
    pain_points = confirmed.get("pain_points", []) if has_living_spec else []
    why = list(pain_points[:3]) if isinstance(pain_points, list) else []

    # for_whom: 从 users 提取
    users = confirmed.get("users", []) if has_living_spec else []
    for_whom = []
    if isinstance(users, list):
        for user in users[:3]:
            if isinstance(user, dict):
                role = user.get("role", "")
                description = user.get("description", "")
                if role or description:
                    for_whom.append({"role": role, "description": description})
            elif isinstance(user, str) and user.strip():
                for_whom.append({"role": user, "description": ""})

    # success_criteria: 从 success_metrics 提取
    success_metrics = confirmed.get("success_metrics", []) if has_living_spec else []
    success_criteria = []
    if isinstance(success_metrics, list):
        for metric in success_metrics[:5]:
            if isinstance(metric, dict):
                metric_name = metric.get("metric", "")
                target = metric.get("target", "")
                if metric_name:
                    criteria = f"{metric_name}: {target}" if target else metric_name
                    success_criteria.append(criteria)
            elif isinstance(metric, str) and metric.strip():
                success_criteria.append(metric)

    # constraints: 从 confirmed.constraints 提取
    constraints_raw = confirmed.get("constraints", {}) if has_living_spec else {}
    constraints_dict = {}
    if isinstance(constraints_raw, dict):
        budget = constraints_raw.get("budget", "")
        timeline = constraints_raw.get("timeline", "")
        tech_stack = constraints_raw.get("tech_stack", [])
        if budget:
            constraints_dict["budget"] = budget
        if timeline:
            constraints_dict["timeline"] = timeline
        if isinstance(tech_stack, list) and tech_stack:
            constraints_dict["tech_stack"] = tech_stack

    # one_liner: 从 objective 截取（≤50字）
    objective_text = confirmed.get("objective", "") if has_living_spec else ""
    if not objective_text:
        objective_text = topic
    one_liner = objective_text if len(objective_text) <= 50 else objective_text[:47] + "..."

    # source: 标记来源
    source = "living_spec" if has_living_spec else "auto_generated_from_topic"

    return {
        "one_liner": one_liner,
        "objective_req": objective_req,
        "key_scenarios_reqs": key_scenarios_reqs,
        "why": why,
        "for_whom": for_whom,
        "success_criteria": success_criteria,
        "constraints": constraints_dict,
        "source": source,
    }


# ============================================================================
# V2.0: requirement_groups 构建（二级分组）
# ============================================================================

def _build_requirement_groups(requirements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    基于 REQ 的 category 自动聚合为 5 个高层 group。

    返回格式：
    {
        "Core": {
            "description": "核心目标、痛点、场景",
            "categories": ["objective", "pain_point", "scenario"],
            "req_ids": ["REQ-001", "REQ-010"]
        },
        ...
    }
    """
    groups = {}
    for group_name, group_info in GROUP_MAP.items():
        categories = group_info["categories"]
        req_ids = [
            req["id"] for req in requirements
            if req.get("category") in categories
        ]
        if req_ids:  # 只输出非空的 group
            groups[group_name] = {
                "description": group_info["description"],
                "categories": categories,
                "req_ids": req_ids,
            }
    return groups


# ============================================================================
# V2.0: LLM 标注合并（阶段 2：Spec Pro 标注增强）
# ============================================================================

def _merge_annotations(requirements: List[Dict[str, Any]], 
                      annotations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将 LLM 标注合并到 REQ 列表中（宽松匹配）。

    匹配策略：
    1. 优先精确匹配（description == original_text）
    2. 宽松匹配（original_text in description 或 description in original_text）
    3. 未匹配的 REQ 保持原样，记录日志

    合并内容：
    - context_note: 一句话结构化上下文
    - dependencies: 依赖的 REQ-ID
    - potential_conflicts: 潜在冲突的 REQ-ID

    Args:
        requirements: 脚本生成的 REQ 列表
        annotations: LLM 标注结果列表

    Returns:
        合并后的 REQ 列表（新增 context_note/dependencies/potential_conflicts 字段）
    """
    import logging
    logger = logging.getLogger(__name__)

    merged = []
    matched_count = 0

    for req in requirements:
        req_desc = req.get("description", "")
        matched_ann = None

        # 尝试匹配标注
        for ann in annotations:
            original_text = ann.get("original_text", "")

            # 精确匹配
            if req_desc == original_text:
                matched_ann = ann
                break

            # 宽松匹配（子串包含）
            if original_text in req_desc or req_desc in original_text:
                matched_ann = ann
                break

        if matched_ann:
            # 合并元数据（不替换基础结构）
            req["context_note"] = matched_ann.get("context_note", "")
            req["dependencies"] = matched_ann.get("dependencies", [])
            req["potential_conflicts"] = matched_ann.get("potential_conflicts", [])
            matched_count += 1
            logger.debug(f"REQ {req['id']} matched annotation: {matched_ann['original_text'][:50]}")
        else:
            # 未匹配的 REQ 保持原样，添加空字段
            req["context_note"] = ""
            req["dependencies"] = []
            req["potential_conflicts"] = []
            logger.debug(f"REQ {req['id']} no matching annotation found")

        merged.append(req)

    logger.info(f"Merged {matched_count}/{len(requirements)} REQs with LLM annotations")
    return merged


def write_frozen_spec(base_path: str | Path, topic: str,
                      constraints: List[str] | None = None,
                      living_spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base = Path(base_path)
    spec = build_frozen_spec(topic, constraints, living_spec)
    path = base / "data" / "frozen_spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    return spec

