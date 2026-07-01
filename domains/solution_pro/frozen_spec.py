"""Deterministic REQ-ID frozen spec generation for Solution Pro."""

from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# =============================================================================
# ⚠️ DEPRECATION NOTICE (V3 AI Native)
# =============================================================================
# frozen_spec.py 已进入废弃路径：
#   Phase 1（当前）: frozen_spec 降级为 REQ-ID 索引生成器
#   Phase 2（下次迭代）: 完全废弃 frozen_spec.py，REQ-ID 索引由 living_spec.py 直接生成
#
# 过渡期规则：
#   - 当 living_spec 参数存在时，优先使用 living_spec.requirement_index
#   - frozen_spec 仅作为 fallback（living_spec 不存在时）
#   - 禁止在 living_spec 模式下读取 frozen_spec 的非索引字段
# =============================================================================

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


def _auto_generate_hints(confirmed: Dict[str, Any]) -> List[str]:
    """V4: 当 solution_pro_hints 为 null 时，从 confirmed 自动推导研究重点提示。"""
    hints = []
    
    # 从 architecture 推导技术焦点
    arch = confirmed.get("architecture", {})
    if isinstance(arch, dict):
        pattern = arch.get("pattern", "")
        if pattern:
            hints.append(f"架构模式: {pattern} — 方案应围绕此模式设计")
        layers = arch.get("layers", [])
        if layers and isinstance(layers, list):
            layer_names = [l.get("name", "") for l in layers if isinstance(l, dict)]
            if layer_names:
                hints.append(f"架构层次: {', '.join(layer_names[:4])} — 方案应覆盖所有层次")
    
    # 从 innovation_mechanisms 推导创新点
    innovations = confirmed.get("innovation_mechanisms", [])
    if innovations and isinstance(innovations, list):
        names = [i.get("name", "") for i in innovations if isinstance(i, dict)]
        if names:
            hints.append(f"创新机制: {', '.join(names[:5])} — 方案应包含这些机制的设计")
    
    # 从 tools 推导工具集成重点
    tools = confirmed.get("tools", {})
    if isinstance(tools, dict):
        tool_names = [k for k in tools.keys() if k not in ("description",)]
        if tool_names:
            hints.append(f"工具集成: {', '.join(tool_names[:5])} — 方案应说明如何集成这些工具")
    
    # 从 core_insight 推导核心设计原则
    insight = confirmed.get("core_insight", "")
    if insight and isinstance(insight, str):
        hints.append(f"核心洞察: {insight}")
    
    return hints


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

    # 兼容 dict 和 list 格式的 constraints
    constraints_raw = confirmed.get("constraints", {})
    if isinstance(constraints_raw, list):
        # list 格式: ["一步到位", "全LLM控制", ...]
        # 转换为: {"items": ["一步到位", "全LLM控制", ...]}
        confirmed_constraints = {"items": constraints_raw} if constraints_raw else {}
    else:
        # dict 格式: {"budget": "...", "timeline": "...", ...}
        confirmed_constraints = constraints_raw if constraints_raw else {}
    
    for key, val in confirmed_constraints.items():
        if not val:
            continue
        if isinstance(val, list):
            for item in val:
                _add_requirement(requirements, "constraint", f"{key}: {item}", "P1", f"living_spec.confirmed.constraints.{key}")
        else:
            _add_requirement(requirements, "constraint", f"{key}: {val}", "P0", f"living_spec.confirmed.constraints.{key}")

    # integration - 兼容 dict 和 list 格式
    integration_raw = confirmed.get("integration", {})
    if isinstance(integration_raw, dict):
        integration = integration_raw
    elif isinstance(integration_raw, list):
        # list 格式: 转换为 {"requirements": [...]}
        integration = {"requirements": integration_raw} if integration_raw else {}
    else:
        integration = {}
    
    for item in integration.get("requirements", []) or []:
        _add_requirement(requirements, "integration", item, "P1", "living_spec.confirmed.integration.requirements")

    # Pain points → 方案要解决的为什么
    for item in confirmed.get("pain_points", []) or []:
        _add_requirement(requirements, "pain_point", item, "P1", "living_spec.confirmed.pain_points")

    # Success metrics → 做对的标准
    for item in confirmed.get("success_metrics", []) or []:
        if isinstance(item, dict):
            metric_name = item.get("metric", "")
            target = item.get("target", "")
            priority = item.get("priority", "P1")
            # V4 fix: 组合 metric + target 作为 description，避免过短
            if metric_name and target:
                desc = f"{metric_name}: {target}"
            elif metric_name:
                desc = metric_name
            else:
                desc = target or str(item)
            measurable = target
        else:
            desc = str(item)
            priority = "P1"
            measurable = ""
        _add_requirement(requirements, "success_metric", desc, priority,
                         "living_spec.confirmed.success_metrics", measurable)

    # Users → 用户画像
    for item in confirmed.get("users", []) or []:
        if isinstance(item, dict):
            role = item.get("role", "")
            description = item.get("description", "")
            key_needs = item.get("key_needs", [])
            # V4 fix: 组合 role + key_needs 作为 description
            if role and key_needs:
                needs_str = "、".join(key_needs[:3]) if isinstance(key_needs, list) else str(key_needs)
                desc = f"{role}（需求: {needs_str}）"
            elif role:
                desc = role
            else:
                desc = description or str(item)
            measurable = f"tech_level={item.get('tech_level', 'unknown')}"
        else:
            desc = str(item)
            measurable = ""
        if desc:
            _add_requirement(requirements, "user", desc, "P1", "living_spec.confirmed.users", measurable)

    # Key scenarios → 核心使用场景
    for item in confirmed.get("key_scenarios", []) or []:
        _add_requirement(requirements, "scenario", item, "P1", "living_spec.confirmed.key_scenarios")

    # Risks and assumptions → 风险和假设
    ra = confirmed.get("risks_and_assumptions", {}) if isinstance(confirmed.get("risks_and_assumptions", {}), dict) else {}
    for item in ra.get("risks", []) or []:
        if isinstance(item, dict):
            desc = item.get("description", "")
            severity = item.get("severity", "")
            likelihood = item.get("likelihood", "")
            # V4 fix: 组合 description + severity/likelihood
            if desc and severity:
                desc = f"[风险-{severity}/{likelihood}] {desc}"
            measurable = f"severity={severity}, likelihood={likelihood}"
        else:
            desc = str(item)
            measurable = ""
        if desc:
            _add_requirement(requirements, "risk", desc, "P1", "living_spec.confirmed.risks_and_assumptions.risks", measurable)
    for item in ra.get("assumptions", []) or []:
        if isinstance(item, dict):
            desc = item.get("description", "")
            measurable = f"id={item.get('id', '')}"
        else:
            desc = str(item)
            measurable = ""
        if desc:
            _add_requirement(requirements, "assumption", desc, "P1", "living_spec.confirmed.risks_and_assumptions.assumptions", measurable)

    # Guardrails → 行为边界（guardrails 是顶层字段，不在 confirmed 下）
    # V4 fix: 支持两种格式：
    #   flat 格式: {always_do: [...], never_do: [...], resolved: [...]}
    #   zone 格式: {zone_0_immutable: {rules: [...]}, zone_1_verified_change: {rules: [...]}, ...}
    guardrails = (living_spec or {}).get("guardrails", {}) if isinstance(living_spec, dict) else {}
    if isinstance(guardrails, dict):
        # flat 格式
        for item in guardrails.get("always_do", []) or []:
            _add_requirement(requirements, "guardrail", item, "P0", "living_spec.guardrails.always_do")
        for item in guardrails.get("never_do", []) or []:
            _add_requirement(requirements, "guardrail_prohibition", item, "P0", "living_spec.guardrails.never_do")
        for item in guardrails.get("resolved", []) or []:
            if isinstance(item, dict):
                question = item.get("question", "")
                answer = item.get("answer", "")
                if question or answer:
                    desc = f"决策: {question} → {answer}".strip()
                    _add_requirement(requirements, "design_decision", desc, "P1", "living_spec.guardrails.resolved")
        
        # zone 格式（V4 新增）
        zone_map = {
            "zone_0_immutable": ("guardrail_prohibition", "P0", "绝对不可修改"),
            "zone_1_verified_change": ("guardrail", "P0", "需验证的变更"),
            "zone_2_free_change": ("guardrail", "P1", "可自由调整"),
        }
        for zone_key, (category, priority, zone_label) in zone_map.items():
            zone = guardrails.get(zone_key, {})
            if isinstance(zone, dict):
                rules = zone.get("rules", [])
                if rules:
                    for rule in rules:
                        desc = f"[{zone_label}] {rule}" if isinstance(rule, str) else str(rule)
                        _add_requirement(requirements, category, desc, priority, f"living_spec.guardrails.{zone_key}")
        
        # operational_boundaries（V4 新增）
        op_bounds = guardrails.get("operational_boundaries", {})
        if isinstance(op_bounds, dict):
            for key, val in op_bounds.items():
                if val is not None:
                    desc = f"[操作边界] {key}: {val}"
                    _add_requirement(requirements, "guardrail", desc, "P1", "living_spec.guardrails.operational_boundaries", f"{key}={val}")

    # Solution Pro hints → Spec Pro 给下游的提示
    hints = (living_spec or {}).get("solution_pro_hints", None) if isinstance(living_spec, dict) else None
    if hints:
        if isinstance(hints, str):
            _add_requirement(requirements, "hint", hints, "P1", "living_spec.solution_pro_hints")
        elif isinstance(hints, dict):
            for key, value in hints.items():
                _add_requirement(requirements, "hint", f"{key}: {value}", "P1", f"living_spec.solution_pro_hints.{key}")
    elif confirmed:
        # V4 fix: 当 solution_pro_hints 为 null 时，从 confirmed 自动推导
        auto_hints = _auto_generate_hints(confirmed)
        for hint_text in auto_hints:
            _add_requirement(requirements, "hint", hint_text, "P1", "auto_generated_from_confirmed")

    # Inferred → AI 推断需求（顶层字段，不在 confirmed 下）
    inferred = (living_spec or {}).get("inferred", []) if isinstance(living_spec, dict) else []
    if isinstance(inferred, list):
        for item in inferred:
            if isinstance(item, dict):
                dimension = item.get("dimension", "")
                content = item.get("content", "")
                confidence = item.get("confidence", 0)
                if content:
                    desc = f"推断[{dimension}]: {content}".strip()
                    priority = "P1" if confidence >= 0.8 else "P2"
                    _add_requirement(requirements, "inferred", desc, priority, "living_spec.inferred")

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

    # ====================================================================
    # V3: 冲突解决策略（P0）
    # ====================================================================
    # 原则：requirement_index 是权威源（结构化、可追溯）
    # narrative 是辅助理解（语义丰富但不可精确追溯）
    # 当两者不一致时，以 requirement_index 为准，但在 metadata 中记录差异
    
    narrative = living_spec.get("narrative", "") if isinstance(living_spec, dict) else ""
    req_index = living_spec.get("requirement_index", []) if isinstance(living_spec, dict) else []
    
    conflicts = []
    if narrative and req_index:
        # 基本一致性检查：narrative 中提到的关键概念是否都在 requirement_index 中有对应
        # 这是轻量级检查，不做完整语义分析
        req_titles = [r.get("title", "") for r in req_index if isinstance(r, dict)]
        # 不做深度语义检查，只记录两者都存在的事实
    
    # V2.0: 透传 guardrails 和 solution_pro_hints
    guardrails_raw = (living_spec or {}).get("guardrails", {}) if isinstance(living_spec, dict) else {}
    solution_pro_hints_raw = (living_spec or {}).get("solution_pro_hints", None) if isinstance(living_spec, dict) else None
    
    # V4 fix: 当 solution_pro_hints 为 null 时，从 confirmed 自动推导
    if not solution_pro_hints_raw and confirmed:
        arch = confirmed.get("architecture", {})
        innovations = confirmed.get("innovation_mechanisms", [])
        tools_conf = confirmed.get("tools", {})
        insight = confirmed.get("core_insight", "")
        
        focus_areas = []
        if isinstance(arch, dict) and arch.get("pattern"):
            focus_areas.append({"area": arch["pattern"], "weight": 0.3, "reason": "核心架构模式"})
        if isinstance(innovations, list):
            for inn in innovations[:3]:
                if isinstance(inn, dict):
                    focus_areas.append({"area": inn.get("name", ""), "weight": 0.2, "reason": inn.get("description", "")[:80]})
        
        solution_pro_hints_raw = {
            "focus_areas": focus_areas,
            "core_insight": insight,
            "tool_integrations": list(tools_conf.keys()) if isinstance(tools_conf, dict) else [],
            "auto_generated": True,
        }

    # 冲突解决策略（P0）
    # requirement_index 是权威源（结构化、可追溯），narrative 是辅助理解
    narrative = living_spec.get("narrative", "") if isinstance(living_spec, dict) else ""
    req_index = living_spec.get("requirement_index", []) if isinstance(living_spec, dict) else []
    conflicts = []
    if narrative and req_index:
        # 轻量级一致性检查：requirement_index 中的 title 是否在 narrative 中有语义对应
        req_titles = [r.get("title", "") for r in req_index if isinstance(r, dict)]
        for title in req_titles[:20]:  # cap to avoid token explosion
            if title and len(title) > 5 and title.lower() not in narrative.lower():
                conflicts.append({"req_title": title, "issue": "not_found_in_narrative"})

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
        "metadata": {
            "conflict_resolution": {
                "authority": "requirement_index",
                "narrative_role": "auxiliary_context",
                "detected_conflicts": conflicts,
            },
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

    # constraints: 从 confirmed.constraints 提取 - 兼容 dict 和 list 格式
    constraints_raw = confirmed.get("constraints", {}) if has_living_spec else {}
    constraints_dict = {}
    if isinstance(constraints_raw, dict):
        # dict 格式: {"budget": "...", "timeline": "...", "tech_stack": [...]}
        budget = constraints_raw.get("budget", "")
        timeline = constraints_raw.get("timeline", "")
        tech_stack = constraints_raw.get("tech_stack", [])
        if budget:
            constraints_dict["budget"] = budget
        if timeline:
            constraints_dict["timeline"] = timeline
        if isinstance(tech_stack, list) and tech_stack:
            constraints_dict["tech_stack"] = tech_stack
    elif isinstance(constraints_raw, list):
        # list 格式: ["一步到位", "全LLM控制", ...]
        # 转换为: {"items": ["一步到位", "全LLM控制", ...]}
        if constraints_raw:
            constraints_dict["items"] = constraints_raw

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


# ============================================================================
# V3: Living Spec 优先 — 新函数
# ============================================================================

def generate_requirement_index(living_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 living_spec 的 narrative + confirmed 中提取 REQ-ID 列表。

    每条包含: id, description (≥50字), priority, source_section

    V3: 这是 frozen_spec 的替代方案 — 保留完整描述，不拆成标题。

    Args:
        living_spec: Living Spec dict（含 narrative 和 confirmed）

    Returns:
        REQ-ID 索引列表
    """
    if not isinstance(living_spec, dict):
        return []

    confirmed = living_spec.get("confirmed", {})
    if not isinstance(confirmed, dict):
        confirmed = {}

    index: List[Dict[str, Any]] = []
    req_counter = 0

    def _add_index_entry(description: str, priority: str, source_section: str) -> None:
        nonlocal req_counter
        text = str(description or "").strip()
        if not text:
            return
        # 确保 description ≥ 50 字（保留完整上下文）
        if len(text) < 50:
            # 补充来源上下文
            text = f"[{source_section}] {text}"
        req_counter += 1
        index.append({
            "id": f"REQ-{req_counter:03d}",
            "description": text,
            "priority": priority or "P1",
            "source_section": source_section,
        })

    # 1. Objective（P0）
    objective = confirmed.get("objective", "")
    if objective:
        _add_index_entry(objective, "P0", "confirmed.objective")

    # 2. Pain points（P1）
    for item in confirmed.get("pain_points", []) or []:
        _add_index_entry(str(item), "P1", "confirmed.pain_points")

    # 3. Key scenarios（P1）
    for item in confirmed.get("key_scenarios", []) or []:
        _add_index_entry(str(item), "P1", "confirmed.key_scenarios")

    # 4. Capabilities（P0/P1）
    capabilities = confirmed.get("capabilities", {})
    if isinstance(capabilities, dict):
        for item in capabilities.get("always_do", []) or []:
            _add_index_entry(str(item), "P0", "confirmed.capabilities.always_do")
        for item in capabilities.get("should_do", []) or []:
            _add_index_entry(str(item), "P1", "confirmed.capabilities.should_do")
        for item in capabilities.get("never_do", []) or []:
            _add_index_entry(str(item), "P0", "confirmed.capabilities.never_do")

    # 5. Quality attributes（P1）
    for qa in confirmed.get("quality_attributes", []) or []:
        if isinstance(qa, dict):
            desc = qa.get("spec") or qa.get("description") or qa.get("category", "")
            priority = qa.get("priority", "P1")
            _add_index_entry(desc, priority, "confirmed.quality_attributes")
        else:
            _add_index_entry(str(qa), "P1", "confirmed.quality_attributes")

    # 6. Success metrics（P1）
    for item in confirmed.get("success_metrics", []) or []:
        if isinstance(item, dict):
            metric = item.get("metric", "")
            target = item.get("target", "")
            desc = f"{metric}: {target}" if metric and target else (metric or target or str(item))
            _add_index_entry(desc, "P1", "confirmed.success_metrics")
        else:
            _add_index_entry(str(item), "P1", "confirmed.success_metrics")

    # 7. Constraints（P0/P1）
    constraints_raw = confirmed.get("constraints", {})
    if isinstance(constraints_raw, dict):
        for key, val in constraints_raw.items():
            if val:
                if isinstance(val, list):
                    for v in val:
                        _add_index_entry(f"{key}: {v}", "P1", f"confirmed.constraints.{key}")
                else:
                    _add_index_entry(f"{key}: {val}", "P0", f"confirmed.constraints.{key}")
    elif isinstance(constraints_raw, list):
        for item in constraints_raw:
            _add_index_entry(str(item), "P1", "confirmed.constraints")

    # 8. Users（P1）
    for item in confirmed.get("users", []) or []:
        if isinstance(item, dict):
            role = item.get("role", "")
            key_needs = item.get("key_needs", [])
            needs_str = "、".join(key_needs[:3]) if isinstance(key_needs, list) else str(key_needs)
            desc = f"{role}（需求: {needs_str}）" if role and key_needs else (role or str(item))
            _add_index_entry(desc, "P1", "confirmed.users")
        else:
            _add_index_entry(str(item), "P1", "confirmed.users")

    # 9. Integration（P1）
    integration_raw = confirmed.get("integration", {})
    if isinstance(integration_raw, dict):
        for item in integration_raw.get("requirements", []) or []:
            _add_index_entry(str(item), "P1", "confirmed.integration.requirements")
    elif isinstance(integration_raw, list):
        for item in integration_raw:
            _add_index_entry(str(item), "P1", "confirmed.integration")

    # 10. Risks and assumptions（P1）
    ra = confirmed.get("risks_and_assumptions", {})
    if isinstance(ra, dict):
        for item in ra.get("risks", []) or []:
            if isinstance(item, dict):
                desc = item.get("description", str(item))
                severity = item.get("severity", "")
                if severity:
                    desc = f"[风险-{severity}] {desc}"
                _add_index_entry(desc, "P1", "confirmed.risks_and_assumptions.risks")
            else:
                _add_index_entry(str(item), "P1", "confirmed.risks_and_assumptions.risks")
        for item in ra.get("assumptions", []) or []:
            if isinstance(item, dict):
                _add_index_entry(item.get("description", str(item)), "P1", "confirmed.risks_and_assumptions.assumptions")
            else:
                _add_index_entry(str(item), "P1", "confirmed.risks_and_assumptions.assumptions")

    # 11. Guardrails（P0）
    guardrails = living_spec.get("guardrails", {})
    if isinstance(guardrails, dict):
        for item in guardrails.get("always_do", []) or []:
            _add_index_entry(str(item), "P0", "guardrails.always_do")
        for item in guardrails.get("never_do", []) or []:
            _add_index_entry(str(item), "P0", "guardrails.never_do")

    # 12. Inferred（P1/P2）
    for item in living_spec.get("inferred", []) or []:
        if isinstance(item, dict):
            dimension = item.get("dimension", "")
            content = item.get("content", "")
            confidence = item.get("confidence", 0)
            if content:
                desc = f"推断[{dimension}]: {content}"
                priority = "P1" if confidence >= 0.8 else "P2"
                _add_index_entry(desc, priority, "inferred")

    # 13. Solution Pro hints（P1）
    hints = living_spec.get("solution_pro_hints")
    if hints:
        if isinstance(hints, dict):
            focus_areas = hints.get("focus_areas", [])
            for area in focus_areas:
                if isinstance(area, dict):
                    _add_index_entry(
                        f"研究重点: {area.get('area', '')} — {area.get('reason', '')}",
                        "P1",
                        "solution_pro_hints.focus_areas"
                    )
                else:
                    _add_index_entry(f"研究重点: {area}", "P1", "solution_pro_hints.focus_areas")

    return index


def format_living_spec_for_prompt(living_spec: Dict[str, Any]) -> str:
    """
    格式化 Living Spec 供 prompt 注入。

    输出结构：
    1. narrative（叙述为主体）
    2. requirement_index 表格（REQ-ID 为附件）

    V3: 这是 frozen_spec 注入方式的替代方案。

    Args:
        living_spec: Living Spec dict

    Returns:
        格式化后的 prompt 字符串
    """
    if not isinstance(living_spec, dict):
        return "(No living spec available)"

    parts = []

    # === Part 1: Narrative（叙述为主体）===
    narrative = living_spec.get("narrative", "")
    if narrative:
        parts.append("## 用户需求叙述\n")
        parts.append(narrative)
        parts.append("")  # blank line

    # === Part 2: Requirement Index（REQ-ID 为附件）===
    requirement_index = living_spec.get("requirement_index", [])
    if requirement_index:
        parts.append("## REQ-ID 追溯索引\n")
        parts.append("| ID | Priority | Description | Source |")
        parts.append("|---|---|---|---|")
        for req in requirement_index:
            req_id = req.get("id", "?")
            priority = req.get("priority", "P1")
            desc = req.get("description", "")
            # 截断过长的 description（prompt 友好）
            if len(desc) > 120:
                desc = desc[:117] + "..."
            source = req.get("source_section", "")
            parts.append(f"| {req_id} | {priority} | {desc} | {source} |")
        parts.append("")

    # === Part 3: Confirmed 摘要（补充上下文）===
    confirmed = living_spec.get("confirmed", {})
    if isinstance(confirmed, dict) and confirmed:
        parts.append("## 已确认信息摘要\n")

        objective = confirmed.get("objective", "")
        if objective:
            parts.append(f"**目标**: {objective}")
            parts.append("")

        pain_points = confirmed.get("pain_points", [])
        if pain_points:
            parts.append("**痛点**:")
            for pp in pain_points[:5]:
                parts.append(f"- {pp}")
            parts.append("")

        key_scenarios = confirmed.get("key_scenarios", [])
        if key_scenarios:
            parts.append("**核心场景**:")
            for s in key_scenarios[:5]:
                parts.append(f"- {s}")
            parts.append("")

        capabilities = confirmed.get("capabilities", {})
        if isinstance(capabilities, dict):
            always_do = capabilities.get("always_do", [])
            never_do = capabilities.get("never_do", [])
            if always_do:
                parts.append(f"**必须做**: {', '.join(always_do[:5])}")
            if never_do:
                parts.append(f"**禁止做**: {', '.join(never_do[:5])}")
            parts.append("")

    if not parts:
        return "(Living spec is empty)"

    return "\n".join(parts)

