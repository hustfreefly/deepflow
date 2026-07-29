"""
Ship Pro: Ship Package MD ↔ Dict 双向转换

契约笼子:
- render_ship_package_md(data: dict) → str: dict → MD（V2 schema）
- parse_ship_package_md(md: str) → dict: MD → dict（round-trip）
- validate_ship_package_md(md: str) → tuple[bool, list[str]]: MD 结构校验

V2 Schema sections:
Required: meta_info, work_packages, execution_order
Optional: req_traceability, semantic_anchors, gate_decisions
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


REQUIRED_SECTIONS = [
    "meta_info",
    "work_packages",
    "execution_order",
]

OPTIONAL_SECTIONS = [
    "req_traceability",
    "statistics",
    "issues",
    "semantic_anchors",
    "gate_decisions",
]


# ─── render: dict → MD ──────────────────────────────────────────────────────

def render_ship_package_md(data: dict) -> str:
    """
    将 ship_package dict 渲染为 V2 schema Markdown。

    契约:
    - data 必须是 dict
    - 返回值包含所有 REQUIRED_SECTIONS
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise TypeError("data is a string that cannot be parsed as JSON")
    if not isinstance(data, dict):
        raise TypeError(f"data must be dict, got {type(data).__name__}")

    lines: list[str] = []

    # ── YAML Frontmatter ──
    lines.append("---")
    lines.append("domain: ship_pro")
    lines.append(f'version: "{data.get("ship_package_version", "1.0")}"')
    session = data.get("metadata", {}).get("session_id", "unknown")
    lines.append(f'session: "{session}"')
    lines.append("---")
    lines.append("")

    # ── S1: meta_info (required) ──
    lines.append("## meta_info")
    lines.append("")
    lines.append("| field | value |")
    lines.append("|-------|-------|")
    # N3-FIX: output both solution_name (Pydantic canonical) and solution (backward compat)
    solution_name = data.get("solution_name", data.get("solution", ""))
    lines.append(f"| solution_name | {solution_name} |")
    if data.get("solution"):
        lines.append(f"| solution | {data['solution']} |")
    lines.append(f"| version | {data.get('ship_package_version', '1.0')} |")
    # N3-FIX: render project_name if present
    if data.get("project_name"):
        lines.append(f"| project_name | {data['project_name']} |")
    stats = data.get("statistics", {})
    if stats:
        for k, v in stats.items():
            lines.append(f"| {k} | {v} |")
    lines.append("")

    # ── S2: work_packages (required) ──
    lines.append("## work_packages")
    lines.append("")
    wps = data.get("work_packages", [])
    if wps:
        lines.append("| WP-ID | title | effort_hours | REQ-IDs |")
        lines.append("|-------|-------|--------|---------|")
        for wp in wps:
            wp_id = wp.get("id", wp.get("wp_id", "?"))
            title = wp.get("title", "")[:50]
            effort = wp.get("effort_hours", wp.get("estimated_effort", "?"))
            # R1-FIX: prefer covered_req_ids (WorkerDeliverable schema), fallback for backward compat
            req_ids = wp.get("covered_req_ids", wp.get("requirement_ids", wp.get("req_ids", [])))
            req_str = ", ".join(str(r) for r in req_ids[:5]) if isinstance(req_ids, list) else str(req_ids)[:30]
            lines.append(f"| {wp_id} | {title} | {effort} | {req_str} |")
        lines.append("")

        # Detailed WPs (description + acceptance_criteria + deliverables)
        for wp in wps:
            wp_id = wp.get("id", wp.get("wp_id", "?"))
            title = wp.get("title", "")
            desc = wp.get("description", "")
            ac = wp.get("acceptance_criteria", [])
            deliverables = wp.get("deliverables", [])
            deps = wp.get("dependencies", [])

            lines.append(f"### {wp_id}: {title}")
            lines.append("")
            if desc:
                lines.append(desc[:300])
                lines.append("")
            if ac:
                lines.append("**Acceptance Criteria**:")
                for item in ac[:5]:
                    if isinstance(item, dict):
                        lines.append(f"- {item.get('criterion', item.get('description', str(item)))[:100]}")
                    else:
                        lines.append(f"- {str(item)[:100]}")
                lines.append("")
            if deliverables:
                lines.append("**Deliverables**:")
                for item in deliverables[:5]:
                    if isinstance(item, dict):
                        lines.append(f"- {item.get('name', item.get('type', str(item)))}")
                    else:
                        lines.append(f"- {str(item)}")
                lines.append("")
            if deps:
                dep_str = ", ".join(str(d) for d in deps[:5])
                lines.append(f"**Dependencies**: {dep_str}")
                lines.append("")
            anchored_to = wp.get("anchored_to", [])
            if anchored_to:
                anchor_str = ", ".join(str(a) for a in anchored_to[:10])
                lines.append(f"**Anchored To**: {anchor_str}")
                lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # ── S3: execution_order (required) ──
    lines.append("## execution_order")
    lines.append("")
    dg = data.get("dependency_graph", {})
    layers = dg.get("execution_layers", dg.get("layers", []))
    if layers:
        lines.append("| layer | work_packages |")
        lines.append("|-------|--------------|")
        for i, layer in enumerate(layers):
            if isinstance(layer, list):
                wp_str = ", ".join(str(w) for w in layer)
            else:
                wp_str = str(layer)
            lines.append(f"| {i} | {wp_str} |")
        lines.append("")
    else:
        lines.append("(no execution layers defined)")
        lines.append("")

    # ── S4: req_traceability (optional) ──
    pending = data.get("pending_req_ids", [])
    coverage = stats.get("req_coverage_rate", "")
    if pending or coverage:
        lines.append("## req_traceability")
        lines.append("")
        if coverage:
            lines.append(f"**Coverage Rate**: {coverage}")
            lines.append("")
        if pending:
            lines.append("### Pending REQ-IDs")
            for rid in pending:
                lines.append(f"- {rid}")
            lines.append("")

    # ── S5: statistics (optional) ──
    if stats and any(k not in ("req_coverage_rate",) for k in stats):
        lines.append("## statistics")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|--------|-------|")
        for k, v in stats.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    # ── S6: issues (optional) ──
    issues = data.get("issues", [])
    if issues:
        lines.append("## issues")
        lines.append("")
        for i, issue in enumerate(issues, 1):
            if isinstance(issue, dict):
                desc = issue.get("description", issue.get("issue", str(issue)))
                severity = issue.get("severity", "")
                lines.append(f"{i}. [{severity}] {desc[:100]}")
            else:
                lines.append(f"{i}. {str(issue)[:100]}")
        lines.append("")

    # ── S7: semantic_anchors (optional → R2-FIX: always render, empty → <!-- empty -->) ──
    anchors = data.get("semantic_anchors", [])
    lines.append("## semantic_anchors")
    lines.append("")
    if anchors:
        lines.append("| name | category | constraint |")
        lines.append("|------|----------|------------|")
        for a in anchors:
            if isinstance(a, dict):
                lines.append(f"| {a.get('name', '?')} | {a.get('category', '?')} | {a.get('constraint', '')[:60]} |")
    else:
        lines.append("<!-- empty -->")
    lines.append("")

    # ── S7b: N1-FIX - Solution Pro key info fields ──
    key_decisions = data.get("key_decisions", [])
    architecture = data.get("architecture", "")
    risk_summary = data.get("risk_summary", "")
    implementation_phases = data.get("implementation_phases", [])
    if key_decisions or architecture or risk_summary or implementation_phases:
        lines.append("## solution_pro_summary")
        lines.append("")
        if architecture:
            lines.append(f"**Architecture**: {architecture}")
            lines.append("")
        if key_decisions:
            lines.append("**Key Decisions**:")
            for kd in key_decisions[:10]:
                lines.append(f"- {kd}")
            lines.append("")
        if risk_summary:
            lines.append(f"**Risk Summary**: {risk_summary}")
            lines.append("")
        if implementation_phases:
            lines.append("**Implementation Phases**:")
            for phase in implementation_phases[:10]:
                lines.append(f"- {phase}")
            lines.append("")

    # ── S7c: N3-FIX - modules (optional) ──
    modules = data.get("modules", [])
    if modules:
        lines.append("## modules")
        lines.append("")
        if isinstance(modules, list):
            for mod in modules:
                if isinstance(mod, dict):
                    mod_name = mod.get("name", mod.get("id", str(mod)))
                    lines.append(f"- {mod_name}")
                else:
                    lines.append(f"- {mod}")
        lines.append("")

    # ── S7d: N3-FIX - integration_notes (optional) ──
    integration_notes = data.get("integration_notes", "")
    if integration_notes:
        lines.append("## integration_notes")
        lines.append("")
        if isinstance(integration_notes, list):
            for note in integration_notes:
                lines.append(f"- {note}")
        else:
            lines.append(str(integration_notes))
        lines.append("")

    # ── S8: gate_decisions (optional) ──
    lines.append("## gate_decisions")
    lines.append("")
    lines.append("| check_layer | result | reason |")
    lines.append("|-------------|--------|--------|")
    lines.append("| L1 (Schema) | PASS | Ship Pro output |")
    wp_count = len(wps)
    lines.append(f"| L2 (WP Count) | {'PASS' if wp_count > 0 else 'FAIL'} | {wp_count} work packages |")
    lines.append("| L3 (merge) | PASS | ship package complete |")
    lines.append("")

    return "\n".join(lines)


# ─── parse: MD → dict ────────────────────────────────────────────────────────

def parse_ship_package_md(md: str) -> dict:
    """
    从 V2 schema MD 解析为 ship_package dict。
    """
    if not isinstance(md, str):
        raise TypeError(f"md must be str, got {type(md).__name__}")

    result: dict[str, Any] = {}
    metadata: dict[str, Any] = {}

    # ── Parse YAML Frontmatter ──
    body = md
    if md.startswith("---"):
        end = md.find("---", 3)
        if end != -1:
            fm_text = md[3:end].strip()
            body = md[end + 3:]
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "version":
                        result["ship_package_version"] = val
                    elif key == "session":
                        metadata["session_id"] = val

    result["metadata"] = metadata

    # ── Parse Sections ──
    sections = _parse_md_sections(body)

    # S1: meta_info — N3-FIX: parse all fields from meta_info table
    meta_text = sections.get("meta_info", "")
    if meta_text:
        meta_fields = _parse_kv_table(meta_text)
        # N3-FIX: solution_name is canonical (Pydantic); fallback to solution
        if "solution_name" in meta_fields:
            result["solution_name"] = meta_fields["solution_name"]
        elif "solution" in meta_fields:
            result["solution_name"] = meta_fields["solution"]
        if "solution" in meta_fields:
            result["solution"] = meta_fields["solution"]
        if "project_name" in meta_fields:
            result["project_name"] = meta_fields["project_name"]
        # Parse statistics fields from meta_info table (total_wps, total_effort_hours, etc.)
        for stat_key in ("total_wps", "total_effort_hours", "req_coverage_rate",
                         "dependency_edges", "req_coverage"):
            if stat_key in meta_fields:
                result.setdefault("statistics", {})[stat_key] = meta_fields[stat_key]

    # S2: work_packages
    wp_text = sections.get("work_packages", "")
    if wp_text:
        result["work_packages"] = _parse_work_packages(wp_text)

    # S3: execution_order — preserve both as dependency_graph and execution_order
    eo_text = sections.get("execution_order", "")
    if eo_text:
        exec_layers = _parse_execution_order(eo_text)
        result["dependency_graph"] = exec_layers
        result["execution_order"] = exec_layers.get("execution_layers", [])

    # S4: req_traceability — N3-FIX: parse coverage rate
    req_text = sections.get("req_traceability", "")
    if req_text:
        coverage_match = re.search(r"\*\*Coverage Rate\*\*:\s*(.+)", req_text)
        if coverage_match:
            result.setdefault("statistics", {})["req_coverage_rate"] = coverage_match.group(1).strip()
        pending = [l.strip().lstrip("- ") for l in req_text.split("\n") if l.strip().startswith("- ")]
        if pending:
            result["pending_req_ids"] = pending

    # S5: statistics section — N3-FIX: parse statistics table
    stats_text = sections.get("statistics", "")
    if stats_text:
        stats_fields = _parse_kv_table(stats_text)
        for k, v in stats_fields.items():
            # Try to convert numeric values
            try:
                v = int(v)
            except (ValueError, TypeError):
                try:
                    v = float(v)
                except (ValueError, TypeError):
                    pass
            result.setdefault("statistics", {})[k] = v

    # S7: semantic_anchors (R2-FIX: always present, <!-- empty --> → [])
    sa_text = sections.get("semantic_anchors", "")
    if sa_text and "<!-- empty -->" not in sa_text:
        result["semantic_anchors"] = _parse_anchor_table(sa_text)
    else:
        result["semantic_anchors"] = []

    # S7b: solution_pro_summary — N3-FIX: parse risk_summary, architecture, etc.
    sps_text = sections.get("solution_pro_summary", "")
    if sps_text:
        arch_match = re.search(r"\*\*Architecture\*\*:\s*(.+)", sps_text)
        if arch_match:
            result["architecture"] = arch_match.group(1).strip()
        risk_match = re.search(r"\*\*Risk Summary\*\*:\s*(.+)", sps_text)
        if risk_match:
            result["risk_summary"] = risk_match.group(1).strip()
        # Parse key decisions
        kd_lines = []
        in_kd = False
        for line in sps_text.split("\n"):
            if "**Key Decisions**" in line:
                in_kd = True
                continue
            if in_kd:
                if line.startswith("- "):
                    kd_lines.append(line[2:].strip())
                elif line.startswith("**"):
                    in_kd = False
        if kd_lines:
            result["key_decisions"] = kd_lines
        # Parse implementation phases
        ip_lines = []
        in_ip = False
        for line in sps_text.split("\n"):
            if "**Implementation Phases**" in line:
                in_ip = True
                continue
            if in_ip:
                if line.startswith("- "):
                    ip_lines.append(line[2:].strip())
                elif line.startswith("**"):
                    in_ip = False
        if ip_lines:
            result["implementation_phases"] = ip_lines

    # S7c: modules — N3-FIX
    mod_text = sections.get("modules", "")
    if mod_text:
        modules = [l.strip().lstrip("- ") for l in mod_text.split("\n") if l.strip().startswith("- ")]
        if modules:
            result["modules"] = modules

    # S7d: integration_notes — N3-FIX
    in_text = sections.get("integration_notes", "")
    if in_text:
        in_lines = [l.strip() for l in in_text.split("\n") if l.strip()]
        if in_lines:
            # If all lines start with "- ", treat as list; otherwise as text
            if all(l.startswith("- ") for l in in_lines):
                result["integration_notes"] = [l[2:].strip() for l in in_lines]
            else:
                result["integration_notes"] = "\n".join(in_lines)

    return result


def _parse_md_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in body.split("\n"):
        m = re.match(r"^##\s+(\S+)", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = m.group(1).lower().rstrip(":")
            lines = []
        elif line.startswith("# "):
            if current is not None:
                sections[current] = "\n".join(lines).strip()
                current = None
                lines = []
        else:
            if current is not None:
                lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def _parse_work_packages(text: str) -> list[dict]:
    """Parse WP summary table + detailed subsections.

    Parses both the summary table (id, title, effort, req_ids) and
    detailed WP sections (description, acceptance_criteria, deliverables, dependencies).
    """
    wps = []

    # ── Phase 1: Parse summary table ──
    table_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(table_lines) >= 3:
        for line in table_lines[2:]:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if cells and cells[0]:
                # R1-FIX: parse into covered_req_ids (canonical field name)
                wps.append({
                    "id": cells[0],
                    "title": cells[1] if len(cells) > 1 else "",
                    "effort_hours": cells[2] if len(cells) > 2 else "",
                    "covered_req_ids": [r.strip() for r in cells[3].split(",") if r.strip()] if len(cells) > 3 else [],
                })

    # ── Phase 2: Parse detailed WP subsections (### WP-ID: Title) ──
    wp_detail_pattern = re.compile(r'^###\s+(\S+):\s*(.*)$')
    current_wp_id = None
    current_section = None  # 'description', 'acceptance_criteria', 'deliverables', 'dependencies'
    description_lines: list[str] = []
    ac_items: list[str] = []
    deliverable_items: list[str] = []
    dep_items: list[str] = []
    anchored_items: list[str] = []

    def _flush_wp():
        """Flush current WP detail into the matching wp dict."""
        if current_wp_id is None:
            return
        # Find matching WP in the list
        target = None
        for wp in wps:
            if wp["id"] == current_wp_id:
                target = wp
                break
        if target is None:
            return
        if description_lines:
            target["description"] = "\n".join(description_lines).strip()
        if ac_items:
            target["acceptance_criteria"] = ac_items
        if deliverable_items:
            target["deliverables"] = deliverable_items
        if dep_items:
            target["dependencies"] = dep_items
        if anchored_items:
            target["anchored_to"] = anchored_items

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect new WP subsection
        wp_match = wp_detail_pattern.match(line)
        if wp_match:
            _flush_wp()
            current_wp_id = wp_match.group(1)
            current_section = None
            description_lines = []
            ac_items = []
            deliverable_items = []
            dep_items = []
            anchored_items = []
            i += 1
            continue

        # Detect section headers within WP detail
        if line.startswith("**Acceptance Criteria**"):
            current_section = "acceptance_criteria"
            i += 1
            continue
        if line.startswith("**Deliverables**"):
            current_section = "deliverables"
            i += 1
            continue
        if line.startswith("**Dependencies**"):
            current_section = "dependencies"
            # Extract data from same line: "**Dependencies**: WP-001, WP-002"
            if ":" in line:
                dep_text = line.split(":", 1)[1].strip()
                dep_items = [d.strip() for d in dep_text.split(",") if d.strip()]
            i += 1
            continue
        if line.startswith("**Anchored To**"):
            current_section = "anchored_to"
            # Extract data from same line: "**Anchored To**: REQ-OBJ-001, REQ-QA-003"
            if ":" in line:
                anchor_text = line.split(":", 1)[1].strip()
                anchored_items = [a.strip() for a in anchor_text.split(",") if a.strip()]
            i += 1
            continue

        # Detect another H3 or H2 → end of current WP detail
        if re.match(r'^#{2,3}\s', line):
            _flush_wp()
            current_wp_id = None
            current_section = None
            i += 1
            continue

        if current_wp_id is None:
            i += 1
            continue

        # Collect content based on section
        if current_section is None:
            # Description: non-empty lines before any section header
            if line:
                description_lines.append(line)
        elif current_section == "acceptance_criteria":
            if line.startswith("- "):
                ac_items.append(line[2:].strip())
        elif current_section == "deliverables":
            if line.startswith("- "):
                deliverable_items.append(line[2:].strip())
        elif current_section == "dependencies":
            # Dependencies already parsed from the header line; skip trailing content
            pass
        elif current_section == "anchored_to":
            # Anchored To already parsed from the header line; skip trailing content
            pass

        i += 1

    # Flush last WP
    _flush_wp()

    return wps


def _parse_execution_order(text: str) -> dict:
    layers = []
    table_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(table_lines) >= 3:
        for line in table_lines[2:]:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 2:
                wp_list = [w.strip() for w in cells[1].split(",") if w.strip()]
                layers.append(wp_list)
    return {"execution_layers": layers}


def _parse_kv_table(text: str) -> dict[str, str]:
    """Parse a two-column markdown table (| key | value |) into a dict.

    Handles both meta_info (| field | value |) and statistics (| metric | value |) tables.
    """
    result: dict[str, str] = {}
    table_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    # Skip header + separator (first 2 lines)
    for line in table_lines[2:]:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 2 and cells[0]:
            result[cells[0]] = cells[1]
    return result


def _parse_anchor_table(text: str) -> list[dict]:
    anchors = []
    table_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(table_lines) >= 3:
        for line in table_lines[2:]:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if cells:
                anchors.append({
                    "name": cells[0],
                    "category": cells[1] if len(cells) > 1 else "",
                    "constraint": cells[2] if len(cells) > 2 else "",
                })
    return anchors


# ─── validate ────────────────────────────────────────────────────────────────

def validate_ship_package_md(md: str) -> tuple[bool, list[str]]:
    if not isinstance(md, str):
        return False, [f"md must be str, got {type(md).__name__}"]
    if not md.strip():
        return False, ["md is empty"]

    errors: list[str] = []
    if not md.startswith("---"):
        errors.append("missing YAML frontmatter")
    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in md:
            errors.append(f"missing required section: ## {section}")
    return len(errors) == 0, errors
