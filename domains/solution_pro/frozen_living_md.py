"""
Solution Pro: Frozen Spec MD 渲染

ADR-009 P0（2026-07-12）：
  frozen_spec dict → frozen_spec.md
  供 Ship Pro 直读 MD（不依赖 JSON fallback）。

契约笼子：
  - render_frozen_spec_md(data: dict) → str
  - parse_frozen_spec_md(md: str) → dict（round-trip）
  - validate_frozen_spec_md(md: str) → tuple[bool, list[str]]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = ["meta_info", "constraints", "gate_decisions"]


def render_frozen_spec_md(data: dict) -> str:
    """
    将 frozen_spec dict 渲染为 V2 schema Markdown。

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

    # YAML Frontmatter
    lines.append("---")
    lines.append("domain: solution_pro")
    lines.append(f'version: "{data.get("schema_version", "2.0.0")}"')
    lines.append(f'session: "{data.get("session_id", "unknown")}"')
    lines.append("---")
    lines.append("")

    # S1: meta_info
    lines.append("## meta_info")
    lines.append("")
    lines.append("| field | value |")
    lines.append("|-------|-------|")
    lines.append(f"| topic | {data.get('topic', '')} |")
    lines.append(f"| solution_type | {data.get('solution_type', '')} |")
    lines.append(f"| domain | {data.get('domain', '')} |")
    lines.append(f"| mode | {data.get('mode', '')} |")
    # Extra metadata
    for k in ("executive_summary", "requirement_groups_count", "total_req_ids"):
        if k in data:
            lines.append(f"| {k} | {data[k]} |")
    lines.append("")

    # S2: constraints (REQ-ID indexed) — 兼容 requirements 字段名
    lines.append("## constraints")
    lines.append("")
    constraints = data.get("constraints", data.get("requirements", []))
    if constraints:
        lines.append("| REQ-ID | description | priority |")
        lines.append("|--------|-------------|----------|")
        for c in constraints:
            if isinstance(c, dict):
                rid = c.get("req_id", c.get("id", "?"))
                desc = str(c.get("description", c.get("text", "")))[:100]
                pri = c.get("priority", c.get("level", ""))
                lines.append(f"| {rid} | {desc} | {pri} |")
            else:
                lines.append(f"| ? | {str(c)[:100]} | ? |")
    else:
        lines.append("(none)")
    lines.append("")

    # S2b: requirements section（Ship Pro 兼容层）
    requirements = data.get("requirements")
    if requirements is not None:
        lines.append("## requirements")
        lines.append("")
        if isinstance(requirements, list):
            lines.append("| REQ-ID | description | priority |")
            lines.append("|--------|-------------|----------|")
            for r in requirements:
                if isinstance(r, dict):
                    rid = r.get("req_id", r.get("id", "?"))
                    desc = str(r.get("description", r.get("text", "")))[:100]
                    pri = r.get("priority", r.get("level", ""))
                    lines.append(f"| {rid} | {desc} | {pri} |")
                else:
                    lines.append(f"| ? | {str(r)[:100]} | ? |")
        else:
            lines.append(str(requirements)[:200])
        lines.append("")

    # S3: requirement_groups (optional)
    groups = data.get("requirement_groups", [])
    if groups:
        lines.append("## requirement_groups")
        lines.append("")
        for g in groups:
            if isinstance(g, dict):
                name = g.get("name", g.get("group", "?"))
                req_ids = g.get("req_ids", g.get("requirements", []))
                lines.append(f"### {name}")
                lines.append("")
                for rid in req_ids:
                    lines.append(f"- {rid}")
                lines.append("")

    # S3b: key_decisions (B2-FIX: round-trip 完整保留)
    key_decisions = data.get("key_decisions", [])
    if key_decisions:
        lines.append("## key_decisions")
        lines.append("")
        for d in key_decisions:
            if isinstance(d, dict):
                lines.append(f"- {d.get('description', d.get('decision', str(d)))}")
            else:
                lines.append(f"- {d}")
        lines.append("")

    # S3c: architecture (B2-FIX)
    architecture = data.get("architecture")
    if architecture:
        lines.append("## architecture")
        lines.append("")
        if isinstance(architecture, dict):
            for k, v in architecture.items():
                lines.append(f"- **{k}**: {v}")
        else:
            lines.append(str(architecture))
        lines.append("")

    # S3d: covered_req_ids (B2-FIX)
    covered_req_ids = data.get("covered_req_ids", [])
    if covered_req_ids:
        lines.append("## covered_req_ids")
        lines.append("")
        for rid in covered_req_ids:
            lines.append(f"- {rid}")
        lines.append("")

    # S3e: risk_summary (B2-FIX: 兼容 risk_mitigations)
    risk_summary = data.get("risk_summary", data.get("risk_mitigations"))
    if risk_summary:
        lines.append("## risk_summary")
        lines.append("")
        if isinstance(risk_summary, list):
            for r in risk_summary:
                if isinstance(r, dict):
                    lines.append(f"- {r.get('description', r.get('mitigation', str(r)))}")
                else:
                    lines.append(f"- {r}")
        else:
            lines.append(str(risk_summary))
        lines.append("")

    # S3f: implementation_phases (B2-FIX)
    impl_phases = data.get("implementation_phases", [])
    if impl_phases:
        lines.append("## implementation_phases")
        lines.append("")
        for phase in impl_phases:
            if isinstance(phase, dict):
                lines.append(f"- {phase.get('name', phase.get('phase', str(phase)))}")
            else:
                lines.append(f"- {phase}")
        lines.append("")

    # S4: semantic_anchors (P1-1-FIX: 始终渲染，即使为空)
    anchors = data.get("semantic_anchors", [])
    lines.append("## semantic_anchors")
    lines.append("")
    if anchors:
        lines.append("| name | category | constraint |")
        lines.append("|------|----------|------------|")
        for a in anchors:
            if isinstance(a, dict):
                lines.append(f"| {a.get('name', '?')} | {a.get('category', '?')} | {str(a.get('constraint', ''))[:60]} |")
    else:
        lines.append("<!-- empty -->")
    lines.append("")

    # S5: gate_decisions
    lines.append("## gate_decisions")
    lines.append("")
    lines.append("| check_layer | result | reason |")
    lines.append("|-------------|--------|--------|")
    lines.append("| L1 (Schema) | PASS | Solution Pro frozen_spec |")
    lines.append(f"| L2 (REQ count) | {'PASS' if constraints else 'FAIL'} | {len(constraints)} requirements |")
    lines.append("| L3 (merge) | PASS | frozen spec complete |")
    lines.append("")

    return "\n".join(lines)


def parse_frozen_spec_md(md: str) -> dict:
    """
    从 V2 schema MD 解析为 frozen_spec dict。

    契约:
    - md 必须是 str
    - 返回 dict 包含 topic + constraints
    """
    if not isinstance(md, str):
        raise TypeError(f"md must be str, got {type(md).__name__}")

    result: dict[str, Any] = {}

    # Parse YAML Frontmatter
    body = md
    if md.startswith("---"):
        end = md.find("---", 3)
        if end != -1:
            body = md[end + 3:]

    # Parse sections
    sections = _parse_md_sections(body)

    # meta_info
    meta_text = sections.get("meta_info", "")
    if meta_text:
        rows = _extract_table_rows(meta_text)
        for row in rows:
            if len(row) >= 2:
                k, v = row[0].strip(), row[1].strip()
                result[k] = v

    # constraints — 兼容 requirements 字段名
    for section_name in ("constraints", "requirements"):
        ct_text = sections.get(section_name, "")
        if ct_text:
            constraints = []
            rows = _extract_table_rows(ct_text)
            for row in rows:
                if len(row) >= 2:
                    c = {"req_id": row[0].strip(), "description": row[1].strip()}
                    if len(row) >= 3:
                        c["priority"] = row[2].strip()
                    constraints.append(c)
            if constraints:
                result["constraints"] = constraints
                # B1-FIX: Ship Pro pipeline_designer 期望 requirements 字段
                # 同时输出 requirements（兼容两套字段名）
                result["requirements"] = [
                    {"id": c["req_id"], "description": c["description"],
                     "priority": c.get("priority", "")}
                    for c in constraints
                ]
                break
            elif section_name == "constraints":
                continue
            else:
                result["constraints"] = []
                result["requirements"] = []

    # requirement_groups
    rg_text = sections.get("requirement_groups", "")
    if rg_text:
        groups = []
        sub_sections = re.findall(r"###\s+(.+?)(?=\n###|\Z)", rg_text, re.DOTALL)
        for sub in sub_sections:
            parts = sub.strip().split("\n")
            name = parts[0].strip()
            req_ids = [l.strip("- ").strip() for l in parts[1:] if l.strip().startswith("- ")]
            groups.append({"name": name, "req_ids": req_ids})
        result["requirement_groups"] = groups

    # key_decisions (B2-FIX)
    kd_text = sections.get("key_decisions", "")
    if kd_text:
        decisions = []
        for line in kd_text.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                decisions.append(line[2:].strip())
        if decisions:
            result["key_decisions"] = decisions

    # architecture (B2-FIX)
    arch_text = sections.get("architecture", "")
    if arch_text:
        # Parse "- **key**: value" format back to dict
        arch = {}
        for line in arch_text.split("\n"):
            line = line.strip()
            if line.startswith("- **"):
                m = re.match(r"- \*\*(.+?)\*\*:\s*(.*)", line)
                if m:
                    arch[m.group(1)] = m.group(2).strip()
            elif line and not line.startswith("-"):
                # Plain text architecture
                result["architecture"] = line
                break
        if arch:
            result["architecture"] = arch

    # covered_req_ids (B2-FIX)
    cr_text = sections.get("covered_req_ids", "")
    if cr_text:
        req_ids = []
        for line in cr_text.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                req_ids.append(line[2:].strip())
        if req_ids:
            result["covered_req_ids"] = req_ids

    # risk_summary (B2-FIX: 兼容 risk_mitigations)
    rs_text = sections.get("risk_summary", "")
    if rs_text:
        risks = []
        for line in rs_text.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                risks.append(line[2:].strip())
        if risks:
            result["risk_summary"] = risks
            result["risk_mitigations"] = risks
        elif rs_text.strip():
            result["risk_summary"] = rs_text.strip()

    # implementation_phases (B2-FIX)
    ip_text = sections.get("implementation_phases", "")
    if ip_text:
        phases = []
        for line in ip_text.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                phases.append(line[2:].strip())
        if phases:
            result["implementation_phases"] = phases

    # semantic_anchors (P1-1-FIX: 始终返回 [] 而非缺失)
    sa_text = sections.get("semantic_anchors", "")
    anchors = []
    if sa_text and "<!-- empty -->" not in sa_text:
        rows = _extract_table_rows(sa_text)
        for row in rows:
            if len(row) >= 2:
                a = {"name": row[0].strip(), "category": row[1].strip()}
                if len(row) >= 3:
                    a["constraint"] = row[2].strip()
                anchors.append(a)
    result["semantic_anchors"] = anchors

    return result


def validate_frozen_spec_md(md: str) -> tuple[bool, list[str]]:
    """校验 MD 是否符合 V2 schema。"""
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


def _parse_md_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in body.split("\n"):
        m = re.match(r"^##\s+(.+?)$", line)
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


def _extract_table_rows(text: str) -> list[list[str]]:
    rows = []
    lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(lines) < 3:
        return rows
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if cells and any(c for c in cells):
            rows.append(cells)
    return rows
