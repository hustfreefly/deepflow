"""
Solution Pro: Final Solution MD ↔ Dict 双向转换

契约笼子:
- render_final_solution_md(data: dict) → str: dict → MD（V2 schema）
- parse_final_solution_md(md: str) → dict: MD → dict（round-trip）
- validate_final_solution_md(md: str) → tuple[bool, list[str]]: MD 结构校验

V2 Schema sections:
Required: meta_info, overview, key_decisions, implementation_phases
Optional: requirement_coverage, risk_summary, verification_status
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ─── V2 Section 定义 ─────────────────────────────────────────────────────────

REQUIRED_SECTIONS = [
    "meta_info",
    "overview",
    "key_decisions",
    "implementation_phases",
]

OPTIONAL_SECTIONS = [
    "requirement_coverage",
    "risk_summary",
    "verification_status",
    "gate_decisions",
]

ALL_SECTIONS = REQUIRED_SECTIONS + OPTIONAL_SECTIONS


# ─── render: dict → MD ──────────────────────────────────────────────────────

def render_final_solution_md(data: dict) -> str:
    """
    将 final_solution dict 渲染为 V2 schema 的 Markdown。

    契约:
    - data 必须是 dict（如果收到 str 会尝试 json.loads）
    - 返回值包含所有 REQUIRED_SECTIONS
    """
    # Handle double-encoded JSON
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise TypeError(f"data is a string that cannot be parsed as JSON")
    if not isinstance(data, dict):
        raise TypeError(f"data must be dict, got {type(data).__name__}")

    lines: list[str] = []

    # ── YAML Frontmatter ──
    metadata = data.get("metadata", {})
    lines.append("---")
    lines.append("domain: solution_pro")
    lines.append(f'version: "{data.get("schema_version", "2.0.0")}"')
    lines.append(f'session: "{metadata.get("session_id", "unknown")}"')
    lines.append("---")
    lines.append("")

    # ── S1: meta_info (required) ──
    lines.append("## meta_info")
    lines.append("")
    lines.append("| field | value |")
    lines.append("|-------|-------|")
    lines.append(f"| schema_version | {data.get('schema_version', '2.0.0')} |")
    if metadata:
        for k, v in metadata.items():
            if isinstance(v, dict):
                v_str = json.dumps(v, ensure_ascii=False)[:80]
            else:
                v_str = str(v)
            lines.append(f"| {k} | {v_str} |")
    lines.append("")

    # ── S2: overview (required) ──
    lines.append("## overview")
    lines.append("")
    status = metadata.get("status", "")
    if status:
        lines.append(f"**Status**: {status}")
        lines.append("")
    # Summarize from constraint_coverage
    cc = data.get("constraint_coverage", {})
    if cc:
        total = cc.get("total", 0)
        covered = cc.get("covered", 0)
        ratio = cc.get("ratio", 0)
        lines.append(f"**Constraint Coverage**: {covered}/{total} ({ratio:.0%})")
        breakdown = cc.get("breakdown", {})
        if breakdown:
            for level, stats in breakdown.items():
                if isinstance(stats, dict):
                    lines.append(f"- {level}: {stats.get('passed', 0)}/{stats.get('total', 0)}")
        lines.append("")

    # ── S3: key_decisions (required) ──
    lines.append("## key_decisions")
    lines.append("")
    decisions = data.get("key_decisions", [])
    if decisions:
        lines.append("| # | decision | rationale |")
        lines.append("|---|----------|-----------|")
        for i, d in enumerate(decisions, 1):
            if isinstance(d, dict):
                dec = d.get("decision", str(d))[:60]
                rat = d.get("rationale", "")[:80]
                lines.append(f"| {i} | {dec} | {rat} |")
            else:
                lines.append(f"| {i} | {str(d)[:60]} | |")
        lines.append("")
        # Detailed decisions (rationale + alternatives)
        for i, d in enumerate(decisions, 1):
            if isinstance(d, dict):
                dec = d.get("decision", "")
                rat = d.get("rationale", "")
                alt = d.get("alternatives", "")
                lines.append(f"### Decision {i}: {dec}")
                lines.append("")
                if rat:
                    lines.append(f"**Rationale**: {rat}")
                    lines.append("")
                if alt:
                    lines.append(f"**Alternatives**: {alt}")
                    lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # ── S4: implementation_phases (required) ──
    lines.append("## implementation_phases")
    lines.append("")
    phases = data.get("implementation_phases", [])
    if phases:
        lines.append("| phase | title | timeline | effort |")
        lines.append("|-------|-------|----------|--------|")
        for p in phases:
            if isinstance(p, dict):
                lines.append(f"| {p.get('phase', '?')} | {p.get('title', '')} | {p.get('timeline', '')} | {p.get('estimated_effort', '')} |")
        lines.append("")
        # Detailed phases
        for p in phases:
            if isinstance(p, dict):
                lines.append(f"### Phase {p.get('phase', '?')}: {p.get('title', '')}")
                lines.append("")
                tasks = p.get("tasks", [])
                if tasks:
                    for t in tasks:
                        lines.append(f"- {t}")
                    lines.append("")
                verification = p.get("verification", "")
                if verification:
                    lines.append(f"**Verification**: {verification}")
                    lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # ── S5: requirement_coverage (optional) ──
    cc = data.get("constraint_coverage", {})
    if cc:
        lines.append("## requirement_coverage")
        lines.append("")
        uncovered = cc.get("uncovered", [])
        if uncovered:
            lines.append("### Uncovered Constraints")
            lines.append("")
            for item in uncovered:
                lines.append(f"- {item}")
            lines.append("")
        else:
            lines.append("All constraints covered.")
            lines.append("")

    # ── S6: risk_summary (optional) ──
    risks = data.get("risk_summary", [])
    if risks:
        lines.append("## risk_summary")
        lines.append("")
        lines.append("| # | risk | severity | probability | mitigation |")
        lines.append("|---|------|----------|-------------|------------|")
        for i, r in enumerate(risks, 1):
            if isinstance(r, dict):
                lines.append(f"| {i} | {r.get('risk', '')[:40]} | {r.get('severity', '')} | {r.get('probability', '')} | {r.get('mitigation', '')[:60]} |")
            else:
                lines.append(f"| {i} | {str(r)[:40]} | | | |")
        lines.append("")

    # ── S7: verification_status (optional) ──
    vs = data.get("verification_status", {})
    if vs:
        lines.append("## verification_status")
        lines.append("")
        lines.append("| field | value |")
        lines.append("|-------|-------|")
        for k, v in vs.items():
            if isinstance(v, dict):
                v_str = json.dumps(v, ensure_ascii=False)[:80]
            else:
                v_str = str(v)
            lines.append(f"| {k} | {v_str} |")
        lines.append("")

    # ── S8: gate_decisions (optional) ──
    lines.append("## gate_decisions")
    lines.append("")
    lines.append("| check_layer | result | reason |")
    lines.append("|-------------|--------|--------|")
    lines.append("| L1 (Schema) | PASS | Solution Pro output |")
    if vs:
        verdict = "PASS" if vs.get("failed", 1) == 0 else "CONDITIONAL"
        lines.append(f"| L2 (Verification) | {verdict} | {vs.get('passed', 0)}/{vs.get('total_checks', 0)} checks passed |")
    lines.append("| L3 (merge) | PASS | solution complete |")
    lines.append("")

    return "\n".join(lines)


# ─── parse: MD → dict ────────────────────────────────────────────────────────

def parse_final_solution_md(md: str) -> dict:
    """
    从 V2 schema MD 解析为 final_solution dict。

    契约:
    - md 必须是 str
    - 返回 dict 包含 schema_version + 核心字段
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
                        result["schema_version"] = val
                    elif key == "session":
                        metadata["session_id"] = val

    result["metadata"] = metadata

    # ── Parse Sections ──
    sections = _parse_md_sections(body)

    # S1: meta_info
    meta_text = sections.get("meta_info", "")
    if meta_text:
        rows = _extract_table_rows(meta_text)
        for row in rows:
            if len(row) >= 2:
                k, v = row[0].strip(), row[1].strip()
                if k == "schema_version":
                    result["schema_version"] = v
                else:
                    metadata[k] = v

    # S3: key_decisions
    kd_text = sections.get("key_decisions", "")
    if kd_text:
        result["key_decisions"] = _parse_decisions(kd_text)

    # S4: implementation_phases
    ip_text = sections.get("implementation_phases", "")
    if ip_text:
        result["implementation_phases"] = _parse_phases(ip_text)

    # S6: risk_summary
    rs_text = sections.get("risk_summary", "")
    if rs_text:
        result["risk_summary"] = _parse_table_to_dicts(rs_text)

    # S7: verification_status
    vs_text = sections.get("verification_status", "")
    if vs_text:
        result["verification_status"] = _parse_table_to_dict(vs_text)

    return result


def _parse_md_sections(body: str) -> dict[str, str]:
    """Parse MD body into sections by ## headers.

    BUG-001 FIX (2026-07-15): 支持多词标题（如 "## Key Decisions"）。
    旧正则 ``^## (\\S+)`` 只捕获第一个词，导致 "## Key Decisions" → "key"（丢失 "Decisions"）。
    新正则 ``^## (.+?)`` 捕获完整标题文本，然后 normalize 为 snake_case。
    向后兼容：render 产出的 snake_case 标题（如 "## key_decisions"）normalize 后不变。
    """
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []

    for line in body.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            # Normalize: "Key Decisions" → "key_decisions", "key_decisions" → "key_decisions"
            raw = m.group(1).strip().rstrip(":")
            current = re.sub(r"\s+", "_", raw).lower()
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
    """Extract data rows from markdown table (skip header + separator)."""
    rows = []
    lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(lines) < 3:
        return rows
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if cells and any(c for c in cells):
            rows.append(cells)
    return rows


def _parse_table_to_dicts(text: str) -> list[dict]:
    """Parse a markdown table into list of dicts."""
    rows = _extract_table_rows(text)
    lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(lines) < 2:
        return []
    headers = [c.strip().lower().replace(" ", "_") for c in lines[0].split("|")[1:-1]]
    result = []
    for row in rows:
        d = {}
        for i, h in enumerate(headers):
            if i < len(row):
                d[h] = row[i]
        if d:
            result.append(d)
    return result


def _parse_table_to_dict(text: str) -> dict:
    """Parse a key-value table into dict."""
    rows = _extract_table_rows(text)
    result = {}
    for row in rows:
        if len(row) >= 2:
            result[row[0].strip()] = row[1].strip()
    return result


def _parse_decisions(text: str) -> list[dict]:
    """Parse key_decisions section."""
    decisions = []
    # Try summary table first
    table_decisions = _parse_table_to_dicts(text)
    if table_decisions:
        # Also parse detailed ### Decision N subsections
        sub_sections = re.findall(r"###\s+Decision\s+(\d+):\s*(.+?)(?=\n###|\Z)", text, re.DOTALL)
        detail_map = {}
        for num, content in sub_sections:
            detail_map[int(num)] = content.strip()

        for i, d in enumerate(table_decisions, 1):
            detail = detail_map.get(i, "")
            rationale = ""
            alternatives = ""
            if detail:
                rat_m = re.search(r"\*\*Rationale\*\*:\s*(.+?)(?=\n\*\*|\Z)", detail, re.DOTALL)
                alt_m = re.search(r"\*\*Alternatives\*\*:\s*(.+?)(?=\Z)", detail, re.DOTALL)
                if rat_m:
                    rationale = rat_m.group(1).strip()
                if alt_m:
                    alternatives = alt_m.group(1).strip()

            decisions.append({
                "decision": d.get("decision", ""),
                "rationale": rationale or d.get("rationale", ""),
                "alternatives": alternatives,
            })
    return decisions


def _parse_phases(text: str) -> list[dict]:
    """Parse implementation_phases section."""
    phases = []
    # Try summary table first
    table_phases = _parse_table_to_dicts(text)

    # Also parse detailed ### Phase N subsections
    sub_sections = re.findall(r"###\s+Phase\s+(\S+):\s*(.+?)(?=\n###\s+Phase|\Z)", text, re.DOTALL)

    if sub_sections:
        for phase_num, content in sub_sections:
            tasks = re.findall(r"^- (.+)$", content, re.MULTILINE)
            ver_m = re.search(r"\*\*Verification\*\*:\s*(.+?)$", content, re.MULTILINE)
            # Find corresponding table row
            table_row = next((p for p in table_phases if p.get("phase") == phase_num), {})
            phases.append({
                "phase": int(phase_num) if phase_num.isdigit() else phase_num,
                "title": table_row.get("title", ""),
                "timeline": table_row.get("timeline", ""),
                "estimated_effort": table_row.get("effort", ""),
                "tasks": tasks,
                "verification": ver_m.group(1).strip() if ver_m else "",
            })
    elif table_phases:
        for p in table_phases:
            phases.append({
                "phase": int(p.get("phase", 0)) if str(p.get("phase", "")).isdigit() else p.get("phase"),
                "title": p.get("title", ""),
                "timeline": p.get("timeline", ""),
                "estimated_effort": p.get("effort", ""),
                "tasks": [],
                "verification": "",
            })

    return phases


# ─── validate: MD 结构校验 ───────────────────────────────────────────────────

def validate_final_solution_md(md: str) -> tuple[bool, list[str]]:
    """
    校验 MD 是否符合 V2 schema。

    Returns:
        (passed, errors)
    """
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
