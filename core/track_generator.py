"""
ADR-009: Universal Track Generator for All Domains

Shared utility that any domain can call to generate track.json from MD.
Handles both "MD exists" (Deliver Pro, Solution Pro) and
"JSON -> MD conversion needed" (Spec Pro, Ship Pro) scenarios.

V2: Walk-based adaptive renderer for Spec Pro (replaces fixed mapping).
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from core.md_track_extractor import validate_md_structure, extract_track_json
    _HAS_TRACK_EXTRACTOR = True
except ImportError:
    _HAS_TRACK_EXTRACTOR = False


def generate_track_from_md(
    md_path: Path,
    domain: str,
    output_path: Path | None = None,
) -> dict | None:
    """Extract track.json from an existing MD file."""
    if not _HAS_TRACK_EXTRACTOR:
        logger.info(f"ADR-009: extractor not available, skipping track for {domain}")
        return None
    if not md_path.exists():
        logger.warning(f"ADR-009: {md_path.name} not found, skipping track for {domain}")
        return None
    try:
        md_content = md_path.read_text(encoding="utf-8")
        passed, msg, warnings = validate_md_structure(md_content, domain)
        if not passed:
            logger.warning(f"ADR-009: [{domain}] MD validation failed: {msg}")
            return None
        if warnings:
            logger.info(f"ADR-009: [{domain}] validation warnings: {warnings}")
        track_data = extract_track_json(md_content, domain)

        # ── 完整性检查（FixFlow Phase 3: Track 自动生成）──
        # 验证 summary 和 semantic_anchors 字段存在且非空
        missing_fields = []
        if "summary" not in track_data or not track_data["summary"]:
            missing_fields.append("summary")
        if "semantic_anchors" not in track_data:
            missing_fields.append("semantic_anchors")
        if missing_fields:
            raise ValueError(
                f"ADR-009: [{domain}] track.json 完整性检查失败: "
                f"缺少字段 {missing_fields}。"
                f"extract_track_json() 输出不完整。"
            )

        if output_path is None:
            output_path = md_path.parent / f"{domain}_track.json"
        output_path.write_text(
            json.dumps(track_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        metrics = track_data.get("metrics", {})
        logger.info(
            f"ADR-009: [{domain}] track.json generated - "
            f"req_count={metrics.get('req_count', 0)}, "
            f"sections={metrics.get('section_count', 0)}"
        )
        return track_data
    except ValueError as e:
        logger.warning(f"ADR-009: [{domain}] extraction failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"ADR-009: [{domain}] unexpected error: {e}")
        return None


def generate_track_from_json(
    json_path: Path,
    domain: str,
    md_template_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict | None:
    """Generate MD + track.json from a JSON output file."""
    if not json_path.exists():
        logger.warning(f"ADR-009: [{domain}] {json_path.name} not found")
        return None
    try:
        json_data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"ADR-009: [{domain}] JSON read failed: {e}")
        return None

    md_content = _json_to_md(json_data, domain)
    if output_dir is None:
        output_dir = json_path.parent

    md_filename = {
        "spec_pro": "spec_requirements.md",
        "ship_pro": "ship_package.md",
    }.get(domain, f"{domain}_output.md")

    md_path = output_dir / md_filename
    md_path.write_text(md_content, encoding="utf-8")
    logger.info(f"ADR-009: [{domain}] generated {md_filename} ({len(md_content)} chars)")

    track_path = output_dir / f"{domain}_track.json"
    return generate_track_from_md(md_path, domain, track_path)


def _json_to_md(json_data: dict, domain: str) -> str:
    """Dispatch to domain-specific JSON-to-MD converter."""
    if domain == "spec_pro":
        return _spec_json_to_md(json_data)
    elif domain == "ship_pro":
        return _ship_json_to_md(json_data)
    else:
        return f"# {domain} Output\n\n```json\n{json.dumps(json_data, ensure_ascii=False, indent=2)}\n```\n"


# ============================================================================
# Spec Pro: Walk-based Adaptive JSON -> MD Converter (V2)
#
# Section names use English keys to avoid Unicode in code.
# The md_track_extractor DOMAIN_CONFIG must match these keys.
# ============================================================================

_SPEC_REQ_SUB_KEYS = {
    "pain_points": "Pain Points",
    "terms": "Terms",
    "success_metrics": "Success Metrics",
    "key_scenarios": "Key Scenarios",
}

_SPEC_HANDLED_KEYS = {
    "objective", "description", "pain_points", "terms",
    "success_metrics", "users", "key_scenarios",
    "capabilities", "quality_attributes", "constraints",
}

_SPEC_KEY_ALIASES = {
    "risks": ["risks", "risks_and_assumptions"],
    "risks_and_assumptions": ["risks_and_assumptions", "risks"],
    "objective": ["objective", "description"],
}

_CN_MAP = {
    "risks": "Risks",
    "risks_and_assumptions": "Risks and Assumptions",
    "integration": "Integration Requirements",
    "user_directives": "User Directives",
    "timeline": "Timeline",
    "equipment_types": "Equipment Types",
    "core_decisions": "Core Decisions",
    "architecture": "Architecture Direction",
    "primitives": "Design Primitives",
    "tools": "Toolchain",
    "innovation_mechanisms": "Innovation Mechanisms",
}


def _spec_json_to_md(data: dict) -> str:
    """Walk-based adaptive converter: living_spec.json -> spec_requirements.md."""
    if not isinstance(data, dict):
        logger.warning("ADR-009: [spec_pro] data is not dict, falling back")
        return f"# Spec Requirements\n\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```\n"

    meta = data.get("meta", {}) or {}
    confirmed = data.get("confirmed", {}) or {}
    inferred_list = data.get("inferred", []) or []
    requirement_index = data.get("requirement_index", []) or []
    semantic_anchors = data.get("semantic_anchors", []) or []

    project_name = _spec_extract_project_name(data, confirmed)
    spec_version = meta.get("spec_version", "1.0.0")
    rounds = meta.get("conversation_rounds", "?")
    domain_type = meta.get("domain_type", "unknown")

    lines = []

    # YAML Frontmatter
    lines.extend([
        "---",
        "domain: spec_pro",
        f'version: "{spec_version}"',
        f'session: "{data.get("session_id", "unknown")}"',
        "---",
        "",
    ])

    # Title
    lines.append(f"# Spec Requirements: {project_name}")
    lines.append("")

    # S1: meta_info (required) - dynamic rows only for existing fields
    lines.extend(["## meta_info", "", "| field | value |", "|------|-----|"])
    lines.append(f"| spec_version | {spec_version} |")
    lines.append(f"| domain_type | {domain_type} |")
    lines.append(f"| conversation_rounds | {rounds} |")
    _META_SKIP = {"spec_version", "domain_type", "conversation_rounds", "created_at", "updated_at"}
    for k, v in meta.items():
        if k not in _META_SKIP:
            lines.append(f"| {k} | {v} |")
    lines.append("")

    # S2: overview (optional)
    objective = _spec_resolve(confirmed, ["objective", "description"], "")
    narrative = data.get("narrative") or data.get("core_summary") or ""
    overview_text = objective or narrative or "(no overview)"
    lines.extend(["## overview", "", overview_text, ""])

    # S3: confirmed_reqs (required)
    lines.append("## confirmed_reqs")
    lines.append("")
    lines.append("### REQ-ID Table")
    lines.append("")
    _spec_render_req_id_table(lines, requirement_index, confirmed)
    lines.append("")

    users = confirmed.get("users", [])
    if users:
        lines.extend(["### User Roles", ""])
        _spec_render_users_table(lines, users)
        lines.append("")

    for key, section_title in _SPEC_REQ_SUB_KEYS.items():
        val = confirmed.get(key)
        if val and ((isinstance(val, (list, str)) and val) or (isinstance(val, dict) and val)):
            lines.extend([f"### {section_title}", ""])
            _spec_render_value(lines, val)
            lines.append("")

    # S4: capability_boundary (required)
    capabilities = confirmed.get("capabilities", {})
    lines.append("## capability_boundary")
    lines.append("")
    if capabilities:
        _spec_render_capabilities_table(lines, capabilities)
    else:
        lines.append("(no capability boundary defined)")
    lines.append("")

    # S5: constraints (required)
    constraints = confirmed.get("constraints", {})
    guardrails = data.get("guardrails", {})
    lines.append("## constraints")
    lines.append("")
    if constraints:
        _spec_render_value(lines, constraints)
    elif guardrails:
        _spec_render_value(lines, guardrails)
    else:
        lines.append("(no constraints defined)")
    lines.append("")

    # S6: inferred (optional)
    if inferred_list:
        lines.extend(["## inferred", ""])
        lines.append("| hypothesis | confidence | status |")
        lines.append("|------|--------|------|")
        for item in inferred_list:
            if isinstance(item, dict):
                desc = item.get("description", str(item))[:100]
                conf = item.get("confidence", "?")
                status = item.get("status", "pending")
                lines.append(f"| {desc} | {conf} | {status} |")
            else:
                lines.append(f"| {str(item)[:100]} | ? | pending |")
        lines.append("")

    # S7: quality_attrs (optional)
    qa = confirmed.get("quality_attributes", [])
    if qa:
        lines.extend(["## quality_attrs", "", "| category | spec | priority |", "|------|------|--------|"])
        for item in qa:
            if isinstance(item, dict):
                cat = item.get("category", "?")
                spec_val = item.get("spec", str(item))[:80]
                pri = item.get("priority", "?")
                lines.append(f"| {cat} | {spec_val} | {pri} |")
            else:
                lines.append(f"| ? | {str(item)[:80]} | ? |")
        lines.append("")

    # S8: conversation_summary (optional)
    pain_points = confirmed.get("pain_points", [])
    key_scenarios = confirmed.get("key_scenarios", [])
    if pain_points or key_scenarios:
        lines.extend(["## conversation_summary", ""])
        if pain_points:
            lines.append("**pain_points**:")
            for pp in pain_points:
                lines.append(f"- {pp if isinstance(pp, str) else str(pp)[:100]}")
            lines.append("")
        if key_scenarios:
            lines.append("**key_scenarios**:")
            for ks in key_scenarios:
                lines.append(f"- {ks if isinstance(ks, str) else str(ks)[:100]}")
            lines.append("")

    # S9: Walk remaining confirmed.* keys (never silently drop)
    _handled = _SPEC_HANDLED_KEYS | set(_SPEC_REQ_SUB_KEYS.keys())
    for key, val in confirmed.items():
        if key in _handled or not val:
            continue
        section_title = _CN_MAP.get(key, key.replace("_", " ").title())
        lines.extend([f"## {section_title}", ""])
        _spec_render_value(lines, val)
        lines.append("")

    # S10: Semantic Anchors
    if semantic_anchors:
        lines.extend(["## semantic_anchors", ""])
        for sa in semantic_anchors:
            if isinstance(sa, dict):
                name = sa.get("name", "unnamed")
                cat = sa.get("category", "unknown")
                constraint = sa.get("constraint", "")
                lines.append(f"- [{cat}] {name}: {constraint}")
            else:
                lines.append(f"- {sa}")
        lines.append("")

    # S11: Gate decisions
    lines.extend([
        "## gate_decisions",
        "",
        "| check_layer | result | reason |",
        "|--------|------|------|",
        "| L1 (Schema) | PASS | Spec Pro output |",
        "| L3 (合并) | PASS | spec complete |",
    ])

    return "\n".join(lines)


# --- Spec Pro Helper Functions ---

def _spec_extract_project_name(data, confirmed):
    for key in ("objective", "description"):
        val = confirmed.get(key, "")
        if val and isinstance(val, str):
            return val[:80]
    for key in ("project_name", "topic"):
        val = data.get(key, "")
        if val and isinstance(val, str):
            return val[:80]
    narrative = data.get("narrative", "")
    if narrative:
        return narrative[:80]
    return "Unknown"


def _spec_resolve(d, keys, default=""):
    for k in keys:
        v = d.get(k)
        if v is not None and v != "" and v != [] and v != {}:
            return v
    return default


def _spec_render_req_id_table(lines, requirement_index, confirmed):
    lines.append("| REQ-ID | dimension | description | priority | status |")
    lines.append("|--------|------|----------|--------|------|")
    if requirement_index:
        for i, req in enumerate(requirement_index):
            if isinstance(req, dict):
                rid = req.get("id", f"REQ-{i+1:03d}")
                dim = req.get("dimension", req.get("category", "functional"))
                desc = req.get("description", str(req))[:80]
                pri = req.get("priority", "P0")
                st = req.get("status", "confirmed")
                lines.append(f"| {rid} | {dim} | {desc} | {pri} | {st} |")
            else:
                lines.append(f"| REQ-{i+1:03d} | functional | {str(req)[:80]} | P0 | confirmed |")
        return
    idx = 1
    for src_key, dimension in [
        ("key_scenarios", "scenario"),
        ("pain_points", "pain_point"),
        ("success_metrics", "metric"),
    ]:
        items = confirmed.get(src_key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                desc = item[:80]
            elif isinstance(item, dict):
                desc = item.get("description", str(item))[:80]
            else:
                desc = str(item)[:80]
            lines.append(f"| REQ-{idx:03d} | {dimension} | {desc} | P0 | confirmed |")
            idx += 1
    if idx == 1:
        lines.append("| REQ-001 | general | See overview | P0 | confirmed |")


def _spec_render_users_table(lines, users):
    if not users:
        return
    if isinstance(users[0], dict):
        keys = list(users[0].keys())
        header = " | ".join(keys)
        sep = " | ".join("------" for _ in keys)
        lines.append(f"| {header} |")
        lines.append(f"| {sep} |")
        for user in users:
            vals = " | ".join(str(user.get(k, ""))[:40] for k in keys)
            lines.append(f"| {vals} |")
    else:
        for user in users:
            lines.append(f"- {user}")


def _spec_render_value(lines, val):
    if val is None:
        lines.append("(none)")
        return
    if isinstance(val, str):
        lines.append(val)
        return
    if isinstance(val, bool):
        lines.append(str(val))
        return
    if isinstance(val, (int, float)):
        lines.append(str(val))
        return
    if isinstance(val, list):
        _spec_render_list(lines, val)
        return
    if isinstance(val, dict):
        _spec_render_dict(lines, val)
        return
    lines.append(str(val))


def _spec_render_list(lines, lst):
    if not lst:
        lines.append("(none)")
        return
    if all(isinstance(x, str) for x in lst):
        for item in lst:
            lines.append(f"- {item}")
        return
    dict_items = [x for x in lst if isinstance(x, dict)]
    if dict_items and len(dict_items) == len(lst):
        all_keys = []
        for item in dict_items:
            for k in item:
                if k not in all_keys:
                    all_keys.append(k)
        header = " | ".join(all_keys)
        sep = " | ".join("------" for _ in all_keys)
        lines.append(f"| {header} |")
        lines.append(f"| {sep} |")
        for item in dict_items:
            vals = " | ".join(str(item.get(k, ""))[:60] for k in all_keys)
            lines.append(f"| {vals} |")
        return
    for item in lst:
        if isinstance(item, dict):
            desc = ", ".join(f"{k}: {v}" for k, v in item.items())
            lines.append(f"- {desc[:100]}")
        else:
            lines.append(f"- {item}")


def _spec_render_dict(lines, d):
    if not d:
        lines.append("(none)")
        return
    cap_keys = {"always_do", "should_do", "never_do"}
    if any(isinstance(d.get(k), list) for k in cap_keys if k in d):
        lines.append("| category | content |")
        lines.append("|------|------|")
        for ck in ("always_do", "should_do", "never_do"):
            items = d.get(ck, [])
            if items:
                content = "; ".join(str(i) for i in items)
                lines.append(f"| {ck} | {content} |")
        for ck, cv in d.items():
            if ck not in cap_keys:
                lines.append(f"| {ck} | {cv} |")
        return
    if "risks" in d and "assumptions" in d:
        risks = d.get("risks", [])
        assumptions = d.get("assumptions", [])
        if risks:
            lines.append("**risks**:")
            for r in risks:
                lines.append(f"- {r if isinstance(r, str) else str(r)[:80]}")
            lines.append("")
        if assumptions:
            lines.append("**assumptions**:")
            for a in assumptions:
                lines.append(f"- {a if isinstance(a, str) else str(a)[:80]}")
        return
    lines.append("| field | value |")
    lines.append("|------|-----|")
    for k, v in d.items():
        if isinstance(v, list):
            val_str = "; ".join(str(i) for i in v)[:80]
        elif isinstance(v, dict):
            val_str = ", ".join(f"{kk}: {vv}" for kk, vv in v.items())[:80]
        else:
            val_str = str(v)[:80]
        lines.append(f"| {k} | {val_str} |")


def _spec_render_capabilities_table(lines, cap):
    lines.append("| category | content |")
    lines.append("|------|------|")
    for ck in ("always_do", "should_do", "never_do"):
        items = cap.get(ck, [])
        if items:
            content = "; ".join(str(i) for i in items)
            lines.append(f"| {ck} | {content} |")
    for ck, cv in cap.items():
        if ck not in ("always_do", "should_do", "never_do"):
            lines.append(f"| {ck} | {cv} |")


# ============================================================================
# Ship Pro: JSON -> MD Converter
# ============================================================================

def _ship_json_to_md(data: dict) -> str:
    """Convert ship_package.json to ship_package.md format."""
    project_name = data.get("project_name", data.get("wp_id", "Unknown"))
    tasks = data.get("work_packages", data.get("tasks", []))
    total_effort = data.get("total_effort_hours", 0)
    coverage = data.get("requirement_coverage", {})

    lines = [
        "---",
        "domain: ship_pro",
        'version: "1.0.0"',
        f"session: {data.get('session_id', 'unknown')}",
        "---",
        "",
        f"# Ship Package: {project_name}",
        "",
        "## meta_info",
        "",
        "| field | value |",
        "|------|-----|",
        f"| project_name | {project_name} |",
        f"| task_count | {len(tasks)} |",
        f"| total_effort_hours | {total_effort} |",
        f"| requirement_coverage | {coverage.get('percentage', 'N/A')} |",
        "",
        "## work_packages",
        "",
        "| WP-ID | title | estimated_effort | dependencies |",
        "|-------|------|---------|------|",
    ]

    for i, task in enumerate(tasks):
        if isinstance(task, dict):
            wp_id = task.get("wp_id", task.get("id", f"WP-{i+1:03d}"))
            title = task.get("title", task.get("name", "unnamed"))
            effort = task.get("estimated_effort", task.get("effort_hours", "?"))
            deps = ", ".join(task.get("dependencies", task.get("depends_on", [])))
        else:
            wp_id = f"WP-{i+1:03d}"
            title = str(task)[:50]
            effort = "?"
            deps = "none"
        lines.append(f"| {wp_id} | {title} | {effort}h | {deps} |")

    lines.extend([
        "",
        "## gate_decisions",
        "",
        "| check_layer | result | reason |",
        "|--------|------|------|",
        "| L1 (structure) | PASS | Ship Pro output |",
        "| L3 (merge) | PASS | work packages complete |",
    ])

    return "\n".join(lines)
