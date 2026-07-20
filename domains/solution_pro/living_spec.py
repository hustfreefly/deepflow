"""Living Spec utilities — ADR-009 Phase 3

Functions migrated from frozen_spec.py (deprecated).
frozen_spec.py 已废弃，这些函数是 living_spec 路径的核心工具。
"""

from __future__ import annotations
from typing import Dict, Any, List


def generate_requirement_index(living_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 living_spec 的 narrative + confirmed 中提取 REQ-ID 列表。

    每条包含: id, description (≥50字), priority, source_section

    这是 frozen_spec 的替代方案 — 保留完整描述，不拆成标题。

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
    ⚠️ DEPRECATED (ADR-009 Phase 3) — 下游应直接读 living_spec.md。

    格式化 Living Spec 供 prompt 注入。

    输出结构：
    1. narrative（叙述为主体）
    2. requirement_index 表格（REQ-ID 为附件）

    这是 frozen_spec 注入方式的替代方案。

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