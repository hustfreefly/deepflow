"""
Spec Pro → Solution Pro 上下文适配器

将 Spec Pro 输出的 living_spec 转换为 Solution Pro 各 Worker 需要的上下文信息。
职责:
1. 提取并传递 user_directives(用户显式要求)
2. 提取并传递 inferred_pending(待确认推断)
3. 优化 solution_pro_hints 处理(避免展平为字符串)
4. 提供统一的 context building 接口

设计原则:
- 职责分离:frozen_spec.py 负责需求冻结,spec_context.py 负责上下文构建
- 保持结构:不展平复杂字段,保留原始结构供 Worker 使用
- 渐进增强:新增字段向后兼容,不影响现有流程
"""

from typing import Dict, List, Any, Optional


def build_living_spec_context(living_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 living_spec 构建 Solution Pro Worker 需要的上下文信息。

    Args:
        living_spec: Spec Pro 输出的完整 living_spec

    Returns:
        包含以下字段的字典:
        - user_directives: 用户显式要求列表(保持原始结构)
        - inferred_pending: 待确认推断列表
        - solution_pro_hints: 结构化的提示(不展平)
        - guardrails: 行为边界(保持原始结构)
    """
    if not isinstance(living_spec, dict):
        return {}

    context = {}

    # 1. 提取 user_directives(从 confirmed 层)
    confirmed = living_spec.get("confirmed", {})
    if isinstance(confirmed, dict):
        user_directives = confirmed.get("user_directives", [])
        if user_directives:  # 只在非空时添加
            context["user_directives"] = user_directives

    # 2. 提取 inferred_pending(从 inferred 层,只取 pending 状态)
    inferred = living_spec.get("inferred", [])
    if isinstance(inferred, list):
        pending_inferences = [
            inf for inf in inferred
            if isinstance(inf, dict) and inf.get("status") == "pending"
        ]
        if pending_inferences:
            context["inferred_pending"] = pending_inferences

    # 3. 提取 solution_pro_hints(保持原始结构,不展平)
    hints = living_spec.get("solution_pro_hints")
    if hints and isinstance(hints, dict):
        context["solution_pro_hints"] = hints

    # 4. 提取 guardrails(保持原始结构)
    guardrails = living_spec.get("guardrails")
    if guardrails and isinstance(guardrails, dict):
        context["guardrails"] = guardrails

    return context


def format_user_directives_for_prompt(user_directives: List[Dict[str, Any]]) -> str:
    """
    将 user_directives 格式化为 prompt 文本,供 Worker 理解。

    Args:
        user_directives: 用户显式要求列表

    Returns:
        格式化后的文本,可直接插入 prompt
    """
    if not user_directives:
        return ""

    lines = ["## 用户显式要求(User Directives)", ""]
    lines.append("以下是用户在对话中明确提出的要求,必须严格遵守:")
    lines.append("")

    for directive in user_directives:
        if not isinstance(directive, dict):
            continue

        directive_type = directive.get("directive", "unknown")
        content = directive.get("content", "")
        dimension = directive.get("dimension", "general")

        if directive_type == "deliberately_omitted":
            lines.append(f"- **【{dimension} 维度已省略】** {content}")
        elif directive_type == "benchmark_reference":
            lines.append(f"- **【参考基准】** {content}")
        elif directive_type == "design_delegation":
            lines.append(f"- **【设计委托】** {content}")
        elif directive_type == "adaptive_expectation":
            lines.append(f"- **【自适应期望】** {content}")
        elif directive_type == "quality_priority":
            lines.append(f"- **【质量优先级】** {content}")
        else:
            lines.append(f"- **【{directive_type}】** {content}")

    lines.append("")
    return "\n".join(lines)


def format_inferred_pending_for_prompt(inferred_pending: List[Dict[str, Any]]) -> str:
    """
    将 inferred_pending 格式化为 prompt 文本,提醒 Worker 注意待确认推断。

    Args:
        inferred_pending: 待确认推断列表

    Returns:
        格式化后的文本
    """
    if not inferred_pending:
        return ""

    lines = ["## 待确认推断(Pending Inferences)", ""]
    lines.append('以下是 Spec Pro 推断但尚未用户确认的需求，方案中如涉及需标注为「待确认」：')
    lines.append("")

    for inf in inferred_pending:
        if not isinstance(inf, dict):
            continue

        dimension = inf.get("dimension", "general")
        content = inf.get("content", "")
        confidence = inf.get("confidence", 0.0)

        confidence_pct = f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "未知"
        lines.append(f"- **【{dimension}】** {content} (置信度: {confidence_pct})")

    lines.append("")
    return "\n".join(lines)


def format_solution_pro_hints_for_prompt(hints: Dict[str, Any]) -> str:
    """
    将 solution_pro_hints 格式化为 prompt 文本(保持结构,不展平)。

    Args:
        hints: 结构化的提示字典

    Returns:
        格式化后的文本
    """
    if not hints:
        return ""

    lines = ["## Spec Pro 提示(Solution Pro Hints)", ""]

    # focus_areas
    focus_areas = hints.get("focus_areas", [])
    if focus_areas and isinstance(focus_areas, list):
        lines.append("### 重点关注领域")
        for area in focus_areas:
            if isinstance(area, dict):
                area_name = area.get("area", "")
                weight = area.get("weight", 0)
                reason = area.get("reason", "")
                weight_pct = f"{weight:.0%}" if isinstance(weight, (int, float)) else "未知"
                lines.append(f"- **{area_name}** (权重: {weight_pct}): {reason}")
            else:
                lines.append(f"- {area}")
        lines.append("")

    # layer2_hints
    layer2_hints = hints.get("layer2_hints", {})
    if layer2_hints and isinstance(layer2_hints, dict):
        lines.append("### Layer 2 提示")
        for worker_role, hints_list in layer2_hints.items():
            if isinstance(hints_list, list) and hints_list:
                lines.append(f"**{worker_role}**:")
                for hint in hints_list:
                    lines.append(f"  - {hint}")
        lines.append("")

    # anti_patterns
    anti_patterns = hints.get("anti_patterns", [])
    if anti_patterns and isinstance(anti_patterns, list):
        lines.append("### 反模式警告")
        for pattern in anti_patterns:
            lines.append(f"- {pattern}")
        lines.append("")

    return "\n".join(lines)


def build_conversation_digest_for_prompt(digest) -> str:
    """Build a prompt-friendly summary of conversation_digest for downstream workers.
    
    Args:
        digest: conversation_digest dict (or None for V1 compat)
    
    Returns a formatted string with summary + key excerpts.
    """
    if digest is None or not isinstance(digest, dict):
        return ""
    
    excerpts = digest.get("key_excerpts", [])
    summary = digest.get("summary", "")
    
    if not excerpts and not summary:
        return ""
    
    lines = []
    
    # 需求概述 section
    if summary:
        lines.append("## 需求概述")
        lines.append("")
        lines.append(summary)
        lines.append("")
    
    # 用户关键表达 section
    if excerpts:
        lines.append("## 用户关键表达")
        lines.append("")
        for e in excerpts:
            excerpt = e.get("excerpt", "")
            importance = e.get("importance", "")
            dimension = e.get("dimension", "other")
            if importance == "critical":
                lines.append(f'⭐ [{dimension}] **"{excerpt}"** ← 不可妥协')
            else:
                lines.append(f"• [{dimension}] {excerpt}")
        lines.append("")
    
    return "\n".join(lines)


def build_worker_context_section(
    living_spec: Dict[str, Any],
    worker_role: str,
    include_executive_summary: bool = True
) -> str:
    """
    为特定 Worker 构建上下文段落,可直接插入 prompt。

    Args:
        living_spec: 完整的 living_spec
        worker_role: Worker 角色(planner/researcher/reviewer/auditor/fixer/consolidator/summarizer)
        include_executive_summary: 是否包含 executive_summary(默认 True)

    Returns:
        格式化后的上下文文本段落
    """
    context = build_living_spec_context(living_spec)

    sections = []

    # 1. 用户显式要求(所有 Worker 都需要)
    if "user_directives" in context:
        sections.append(format_user_directives_for_prompt(context["user_directives"]))

    # 2. 待确认推断(Planner/Researcher/Consolidator 需要)
    if "inferred_pending" in context and worker_role in ["planner", "researcher", "consolidator"]:
        sections.append(format_inferred_pending_for_prompt(context["inferred_pending"]))

    # 3. Spec Pro 提示(所有 Worker 都需要)
    if "solution_pro_hints" in context:
        sections.append(format_solution_pro_hints_for_prompt(context["solution_pro_hints"]))

    # 4. 研究边界 / guardrails(所有 Worker 都需要)
    guardrails = living_spec.get("guardrails", {})
    if guardrails:
        gr_lines = ["## 研究边界", ""]
        if guardrails.get("always_do"):
            gr_lines.append("### 必须遵守")
            for item in guardrails["always_do"]:
                gr_lines.append(f"- {item}")
            gr_lines.append("")
        if guardrails.get("ask_first"):
            gr_lines.append("### 需要确认")
            for item in guardrails["ask_first"]:
                gr_lines.append(f"- {item}")
            gr_lines.append("")
        if guardrails.get("never_do"):
            gr_lines.append("### 禁止")
            for item in guardrails["never_do"]:
                gr_lines.append(f"- {item}")
            gr_lines.append("")
        sections.append("\n".join(gr_lines))

    # 5. 对话摘要 / conversation_digest(所有 Worker 都需要)
    digest = living_spec.get("conversation_digest", {})
    if digest:
        digest_text = build_conversation_digest_for_prompt(digest)
        if digest_text:
            sections.append(digest_text)

    return "\n".join(sections)
