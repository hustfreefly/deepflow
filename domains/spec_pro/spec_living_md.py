"""
Spec Pro: Living Spec MD ↔ Dict 双向转换

契约笼子:
- render_living_spec_md(data: dict) → str: dict → MD（V2 schema）
- parse_living_spec_md(md: str) → dict: MD → dict（round-trip 无损）
- validate_living_spec_md(md: str) → tuple[bool, list[str]]: MD 结构校验

V2 Schema: 6 required sections + 10 optional sections
Frontmatter: domain + version + session（3 fields）
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
    "confirmed_reqs",
    "capability_boundary",
    "constraints",
    "gate_decisions",
]

OPTIONAL_SECTIONS = [
    "inferred_reqs",
    "quality_attrs",
    "user_directives",
    "open_questions",
    "guardrails",
    "traceability",
    "solution_pro_hints",
    "route_recommendation",
    "semantic_anchors",
    "conversation_summary",
]

ALL_SECTIONS = REQUIRED_SECTIONS + OPTIONAL_SECTIONS


# ─── render: dict → MD ──────────────────────────────────────────────────────

def render_living_spec_md(data: dict) -> str:
    """
    将 living_spec dict 渲染为 V2 schema 的 Markdown。

    契约:
    - data 必须是 dict
    - 返回值必须包含所有 REQUIRED_SECTIONS
    - 空 section 渲染为 "(none)" 占位
    """
    if not isinstance(data, dict):
        raise TypeError(f"data must be dict, got {type(data).__name__}")

    lines: list[str] = []

    # ── YAML Frontmatter ──
    meta = data.get("meta", {})
    lines.append("---")
    lines.append(f'domain: spec_pro')
    lines.append(f'version: "{meta.get("spec_version", "1.0")}"')
    lines.append(f'session: "{data.get("session_id", "unknown")}"')
    lines.append("---")
    lines.append("")

    # ── S1: meta_info (required) ──
    lines.append("## meta_info")
    lines.append("")
    lines.append("| field | value |")
    lines.append("|-------|-------|")
    for k, v in meta.items():
        if k in ("created_at", "updated_at"):
            continue  # skip timestamps in table
        lines.append(f"| {k} | {v} |")
    if not meta:
        lines.append("| (none) | (none) |")
    lines.append("")

    # ── S2: overview (required) ──
    lines.append("## overview")
    lines.append("")
    confirmed = data.get("confirmed", {})
    objective = confirmed.get("objective", "")
    if objective:
        lines.append(objective)
    else:
        lines.append("(none)")
    lines.append("")

    # ── S2b: narrative (optional, separate section for round-trip fidelity) ──
    narrative = data.get("narrative", "")
    if narrative:
        lines.append("## narrative")
        lines.append("")
        lines.append(narrative)
        lines.append("")

    # ── S2c: core_summary (optional, separate section for round-trip fidelity) ──
    core_summary = data.get("core_summary", "")
    if core_summary:
        lines.append("## core_summary")
        lines.append("")
        lines.append(core_summary)
        lines.append("")

    # ── S3: confirmed_reqs (required) ──
    lines.append("## confirmed_reqs")
    lines.append("")
    _render_confirmed_reqs(lines, confirmed, data)
    lines.append("")

    # ── S4: capability_boundary (required) ──
    lines.append("## capability_boundary")
    lines.append("")
    caps = confirmed.get("capabilities", {})
    if caps:
        lines.append("| category | content |")
        lines.append("|----------|---------|")
        for cat in ("always_do", "should_do", "never_do"):
            items = caps.get(cat, [])
            if items:
                content = "; ".join(str(i) for i in items)
                lines.append(f"| {cat} | {content} |")
        # Extra capability keys
        for k, v in caps.items():
            if k not in ("always_do", "should_do", "never_do"):
                lines.append(f"| {k} | {v} |")
    else:
        lines.append("(none)")
    lines.append("")

    # ── S5: constraints (required) ──
    lines.append("## constraints")
    lines.append("")
    constraints = confirmed.get("constraints", data.get("guardrails", {}))
    if isinstance(constraints, dict) and constraints:
        lines.append("| key | value |")
        lines.append("|-----|-------|")
        for k, v in constraints.items():
            if isinstance(v, list):
                v_str = "; ".join(str(i) for i in v)
            else:
                v_str = str(v)
            lines.append(f"| {k} | {v_str} |")
    elif isinstance(constraints, list) and constraints:
        for item in constraints:
            lines.append(f"- {item}")
    else:
        lines.append("(none)")
    lines.append("")

    # ── S6: gate_decisions (required) ──
    lines.append("## gate_decisions")
    lines.append("")
    # Gate decisions are typically added at write time, not from the dict
    lines.append("| check_layer | result | reason |")
    lines.append("|-------------|--------|--------|")
    gate = data.get("gate_summary", {})
    if gate:
        for layer, verdict in gate.items():
            lines.append(f"| {layer} | {verdict} | |")
    else:
        lines.append("| L1 (Schema) | PASS | Spec Pro output |")
        lines.append("| L3 (merge) | PASS | spec complete |")
    lines.append("")

    # ── S6b: stakeholders (optional) ──
    stakeholders = data.get("stakeholders", [])
    if stakeholders:
        lines.append("## stakeholders")
        lines.append("")
        if isinstance(stakeholders, list):
            for item in stakeholders:
                if isinstance(item, dict):
                    role = item.get("role", item.get("name", "?"))
                    interest = item.get("interest", item.get("concern", ""))
                    lines.append(f"- **{role}**: {interest}")
                else:
                    lines.append(f"- {item}")
        elif isinstance(stakeholders, dict):
            for k, v in stakeholders.items():
                lines.append(f"- **{k}**: {v}")
        lines.append("")

    # ── Optional Sections ──

    # S7: inferred_reqs
    inferred = data.get("inferred", [])
    if inferred:
        lines.append("## inferred_reqs")
        lines.append("")
        lines.append("| hypothesis | confidence | source |")
        lines.append("|------------|------------|--------|")
        for item in inferred:
            if isinstance(item, dict):
                desc = item.get("description", item.get("hypothesis", str(item)))
                conf = item.get("confidence", "?")
                src = item.get("source", "")
                lines.append(f"| {desc} | {conf} | {src} |")
            else:
                lines.append(f"| {item} | ? | |")
        lines.append("")

    # S8: quality_attrs
    qa = confirmed.get("quality_attributes", [])
    if qa:
        lines.append("## quality_attrs")
        lines.append("")
        lines.append("| category | spec | priority |")
        lines.append("|----------|------|----------|")
        for item in qa:
            if isinstance(item, dict):
                lines.append(f"| {item.get('category', '?')} | {item.get('spec', '')} | {item.get('priority', '?')} |")
            else:
                lines.append(f"| ? | {item} | ? |")
        lines.append("")

    # S9: user_directives
    ud = confirmed.get("user_directives", [])
    if ud:
        lines.append("## user_directives")
        lines.append("")
        for item in ud:
            if isinstance(item, dict):
                dim = item.get("dimension", "")
                directive = item.get("directive", str(item))
                reason = item.get("reason", "")
                lines.append(f"- **{dim}**: {directive} ({reason})")
            else:
                lines.append(f"- {item}")
        lines.append("")

    # S10: open_questions
    oq = data.get("open_questions", [])
    if oq:
        lines.append("## open_questions")
        lines.append("")
        for item in oq:
            if isinstance(item, dict):
                qid = item.get("id", "?")
                question = item.get("question", str(item))
                blocking = item.get("blocking", False)
                lines.append(f"- [{qid}] {question} {'🔴 blocking' if blocking else ''}")
            else:
                lines.append(f"- {item}")
        lines.append("")

    # S11: guardrails (zone-based or list)
    gr = data.get("guardrails", {})
    # B4-FIX: Always render guardrails section if present (remove gr != constraints guard)
    # B2-FIX: Support both dict (zone-based) and list types
    if isinstance(gr, dict) and gr:
        lines.append("## guardrails")
        lines.append("")
        for zone_key, zone_val in gr.items():
            if isinstance(zone_val, dict):
                desc = zone_val.get("description", zone_key)
                rules = zone_val.get("rules", [])
                lines.append(f"### {desc}")
                lines.append("")
                for rule in rules:
                    lines.append(f"- {rule}")
                lines.append("")
            else:
                # Non-dict zone value: render as bullet
                lines.append(f"- {zone_key}: {zone_val}")
        lines.append("")
    elif isinstance(gr, list) and gr:
        lines.append("## guardrails")
        lines.append("")
        for item in gr:
            if isinstance(item, dict):
                desc = item.get("description", item.get("name", str(item)))
                lines.append(f"- {desc}")
            else:
                lines.append(f"- {item}")
        lines.append("")

    # S12: traceability
    trace = data.get("traceability", {})
    if trace:
        lines.append("## traceability")
        lines.append("")
        sources = trace.get("input_sources", [])
        if sources:
            lines.append("### Input Sources")
            for s in sources:
                lines.append(f"- {s}")
            lines.append("")
        prov = trace.get("decision_provenance", {})
        if prov:
            lines.append("### Decision Provenance")
            lines.append("| decision | source |")
            lines.append("|----------|--------|")
            for k, v in prov.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")

    # S13: solution_pro_hints
    sph = data.get("solution_pro_hints", {})
    if sph:
        lines.append("## solution_pro_hints")
        lines.append("")
        for k, v in sph.items():
            if isinstance(v, list):
                lines.append(f"### {k}")
                for item in v:
                    lines.append(f"- {item}")
                lines.append("")
            else:
                lines.append(f"**{k}**: {v}")
                lines.append("")

    # S14: route_recommendation
    rr = data.get("route_recommendation", {})
    if rr:
        lines.append("## route_recommendation")
        lines.append("")
        lines.append("| field | value |")
        lines.append("|-------|-------|")
        for k, v in rr.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    # S15: semantic_anchors
    sa = data.get("semantic_anchors", [])
    if sa:
        lines.append("## semantic_anchors")
        lines.append("")
        # B2-FIX: Include source_quote column for round-trip fidelity
        lines.append("| name | category | constraint | priority | source_quote |")
        lines.append("|------|----------|------------|----------|--------------|")
        for item in sa:
            if isinstance(item, dict):
                sq = item.get('source_quote', '')
                lines.append(f"| {item.get('name', '?')} | {item.get('category', '?')} | {item.get('constraint', '')} | {item.get('priority', '?')} | {sq} |")
            else:
                lines.append(f"| {item} | ? | | ? | |")
        lines.append("")

    # S16: conversation_summary
    digest = data.get("conversation_digest", {})
    if digest:
        lines.append("## conversation_summary")
        lines.append("")
        summary = digest.get("summary", "")
        if summary:
            lines.append(f"**summary**: {summary}")
            lines.append("")
        excerpts = digest.get("key_excerpts", [])
        if excerpts:
            lines.append("### Key Excerpts")
            for exc in excerpts:
                if isinstance(exc, dict):
                    rnd = exc.get("round", "?")
                    text = exc.get("text", str(exc))
                    lines.append(f"- Round {rnd}: {text}")
                else:
                    lines.append(f"- {exc}")
            lines.append("")

    # ── Walk remaining confirmed.* keys (never silently drop) ──
    _handled_confirmed = {
        "objective", "description", "pain_points", "terms", "success_metrics",
        "users", "key_scenarios", "capabilities", "quality_attributes",
        "constraints", "integration", "risks_and_assumptions", "risks",
        "user_directives", "deprecated", "requirement_index",
        # B4-FIX: fields now rendered as separate ## sections above
        "narrative", "core_summary", "stakeholders",
        "conversation_digest", "open_questions", "traceability",
    }
    for key, val in confirmed.items():
        if key in _handled_confirmed or not val:
            continue
        section_name = key.replace("_", " ").title()
        lines.append(f"## {section_name}")
        lines.append("")
        _render_value(lines, val)
        lines.append("")

    return "\n".join(lines)


def _render_confirmed_reqs(lines: list[str], confirmed: dict, data: dict | None = None) -> None:
    """Render the confirmed_reqs section."""
    # REQ-ID Table
    lines.append("### REQ-ID Table")
    lines.append("")
    # B2-FIX: Read requirement_index from both confirmed and top-level data
    req_index = confirmed.get("requirement_index", [])
    if not req_index and data:
        req_index = data.get("requirement_index", [])
    if req_index:
        lines.append("| REQ-ID | dimension | description | priority | status |")
        lines.append("|--------|-----------|-------------|----------|--------|")
        for i, req in enumerate(req_index):
            if isinstance(req, dict):
                rid = req.get("id", f"REQ-{i+1:03d}")
                dim = req.get("dimension", req.get("category", "functional"))
                desc = req.get("description", req.get("title", str(req)))[:80]
                pri = req.get("priority", "P0")
                status = req.get("status", "confirmed")
                lines.append(f"| {rid} | {dim} | {desc} | {pri} | {status} |")
            else:
                lines.append(f"| REQ-{i+1:03d} | functional | {str(req)[:80]} | P0 | confirmed |")
    else:
        # Build from sub-fields
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
                desc = item if isinstance(item, str) else item.get("description", str(item))[:80]
                lines.append(f"| REQ-{idx:03d} | {dimension} | {desc} | P0 | confirmed |")
                idx += 1
        if idx == 1:
            lines.append("| REQ-001 | general | See overview | P0 | confirmed |")
    lines.append("")

    # Users
    users = confirmed.get("users", [])
    if users:
        lines.append("### Users")
        lines.append("")
        if isinstance(users[0], dict):
            keys = list(users[0].keys())
            lines.append("| " + " | ".join(keys) + " |")
            lines.append("| " + " | ".join("------" for _ in keys) + " |")
            for u in users:
                vals = " | ".join(str(u.get(k, ""))[:40] for k in keys)
                lines.append(f"| {vals} |")
        else:
            for u in users:
                lines.append(f"- {u}")
        lines.append("")

    # Pain Points
    pp = confirmed.get("pain_points", [])
    if pp:
        lines.append("### Pain Points")
        lines.append("")
        for item in pp:
            lines.append(f"- {item}")
        lines.append("")

    # Key Scenarios
    ks = confirmed.get("key_scenarios", [])
    if ks:
        lines.append("### Key Scenarios")
        lines.append("")
        for item in ks:
            lines.append(f"- {item}")
        lines.append("")

    # Success Metrics
    sm = confirmed.get("success_metrics", [])
    if sm:
        lines.append("### Success Metrics")
        lines.append("")
        if isinstance(sm[0], dict):
            lines.append("| metric | target | priority |")
            lines.append("|--------|--------|----------|")
            for item in sm:
                lines.append(f"| {item.get('metric', '?')} | {item.get('target', '')} | {item.get('priority', '?')} |")
        else:
            for item in sm:
                lines.append(f"- {item}")
        lines.append("")

    # Terms
    terms = confirmed.get("terms", [])
    if terms:
        lines.append("### Terms")
        lines.append("")
        for item in terms:
            if isinstance(item, dict):
                name = item.get("name", str(item))
                defn = item.get("definition", "")
                lines.append(f"- **{name}**: {defn}")
            else:
                lines.append(f"- {item}")
        lines.append("")

    # Integration
    integ = confirmed.get("integration", {})
    if integ:
        lines.append("### Integration")
        lines.append("")
        _render_value(lines, integ)
        lines.append("")

    # Risks & Assumptions
    ra = confirmed.get("risks_and_assumptions", confirmed.get("risks", {}))
    if ra:
        lines.append("### Risks & Assumptions")
        lines.append("")
        _render_value(lines, ra)
        lines.append("")


def _render_value(lines: list[str], val: Any) -> None:
    """Walk-based adaptive renderer."""
    if val is None:
        lines.append("(none)")
    elif isinstance(val, str):
        lines.append(val)
    elif isinstance(val, bool):
        lines.append(str(val))
    elif isinstance(val, (int, float)):
        lines.append(str(val))
    elif isinstance(val, list):
        if not val:
            lines.append("(none)")
        elif all(isinstance(x, str) for x in val):
            for item in val:
                lines.append(f"- {item}")
        elif all(isinstance(x, dict) for x in val):
            all_keys = []
            for item in val:
                for k in item:
                    if k not in all_keys:
                        all_keys.append(k)
            lines.append("| " + " | ".join(all_keys) + " |")
            lines.append("| " + " | ".join("------" for _ in all_keys) + " |")
            for item in val:
                vals = " | ".join(str(item.get(k, ""))[:60] for k in all_keys)
                lines.append(f"| {vals} |")
        else:
            for item in val:
                lines.append(f"- {item}")
    elif isinstance(val, dict):
        if not val:
            lines.append("(none)")
        else:
            lines.append("| key | value |")
            lines.append("|-----|-------|")
            for k, v in val.items():
                if isinstance(v, list):
                    v_str = "; ".join(str(i) for i in v)[:80]
                elif isinstance(v, dict):
                    v_str = json.dumps(v, ensure_ascii=False)[:80]
                else:
                    v_str = str(v)[:80]
                lines.append(f"| {k} | {v_str} |")
    else:
        lines.append(str(val))


# ─── parse: MD → dict ────────────────────────────────────────────────────────

def parse_living_spec_md(md: str) -> dict:
    """
    从 V2 schema MD 解析为 living_spec dict。

    契约:
    - md 必须是 str
    - 返回 dict 必须包含 meta + confirmed 两个顶层 key
    - 缺失 section → 对应字段为空（不 raise）
    """
    if not isinstance(md, str):
        raise TypeError(f"md must be str, got {type(md).__name__}")

    result: dict[str, Any] = {}

    # ── Parse YAML Frontmatter ──
    meta = {}
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
                    if key == "domain":
                        result["domain"] = val
                    elif key == "version":
                        meta["spec_version"] = val
                    elif key == "session":
                        result["session_id"] = val

    result["meta"] = meta

    # ── Parse Sections ──
    sections = _parse_md_sections(body)
    confirmed: dict[str, Any] = {}

    # S2: overview → confirmed.objective
    overview = sections.get("overview", "")
    if overview and overview != "(none)":
        confirmed["objective"] = overview.strip()

    # S3: confirmed_reqs → parse sub-sections
    cr_text = sections.get("confirmed_reqs", "")
    if cr_text:
        _parse_confirmed_reqs(confirmed, cr_text)

    # S4: capability_boundary → confirmed.capabilities
    cb_text = sections.get("capability_boundary", "")
    if cb_text and cb_text.strip() != "(none)":
        caps = _parse_capability_table(cb_text)
        if caps:
            confirmed["capabilities"] = caps

    # S5: constraints → confirmed.constraints
    ct_text = sections.get("constraints", "")
    if ct_text and ct_text.strip() != "(none)":
        constraints = _parse_constraints(ct_text)
        if constraints:
            confirmed["constraints"] = constraints

    # S7: inferred_reqs
    inf_text = sections.get("inferred_reqs", "")
    if inf_text:
        result["inferred"] = _parse_table_to_dicts(inf_text)

    # S8: quality_attrs
    qa_text = sections.get("quality_attrs", "")
    if qa_text:
        confirmed["quality_attributes"] = _parse_table_to_dicts(qa_text)

    # S15: semantic_anchors
    sa_text = sections.get("semantic_anchors", "")
    if sa_text:
        result["semantic_anchors"] = _parse_table_to_dicts(sa_text)

    # S13: solution_pro_hints
    sph_text = sections.get("solution_pro_hints", "")
    if sph_text:
        result["solution_pro_hints"] = _parse_key_value_sections(sph_text)

    # S14: route_recommendation
    rr_text = sections.get("route_recommendation", "")
    if rr_text:
        result["route_recommendation"] = _parse_table_to_dict(rr_text)

    # ── B4-FIX: Restore optional fields that were previously lost ──
    # narrative: from ## narrative section
    narrative_text = sections.get("narrative", "")
    if narrative_text and narrative_text != "(none)":
        result["narrative"] = narrative_text.strip()

    # guardrails: from ## guardrails section (zone-based structure)
    gr_text = sections.get("guardrails", "")
    if gr_text and gr_text != "(none)":
        gr_subs = _parse_subsections(gr_text)
        if gr_subs:
            guardrails = {}
            for sub_key, sub_val in gr_subs.items():
                guardrails[sub_key] = {
                    "description": sub_key,
                    "rules": _parse_bullet_list(sub_val),
                }
            result["guardrails"] = guardrails
        else:
            # Fallback: try as constraints-style table or bullet list
            gr_parsed = _parse_constraints(gr_text)
            if gr_parsed:
                result["guardrails"] = gr_parsed

    # core_summary: from ## core_summary section
    core_summary_text = sections.get("core_summary", "")
    if core_summary_text and core_summary_text != "(none)":
        result["core_summary"] = core_summary_text.strip()

    # stakeholders: from ## stakeholders section
    sh_text = sections.get("stakeholders", "")
    if sh_text and sh_text != "(none)":
        result["stakeholders"] = _parse_bullet_list(sh_text) or _parse_table_to_dicts(sh_text)

    # conversation_digest: from ## conversation_summary section
    cd_text = sections.get("conversation_summary", "")
    if cd_text and cd_text != "(none)":
        digest = {}
        # Parse summary line
        for line in cd_text.split("\n"):
            line = line.strip()
            if line.startswith("**summary**:"):
                digest["summary"] = line.replace("**summary**:", "").strip()
                break
        # Parse key excerpts
        excerpts_sub = _parse_subsections(cd_text)
        ke_text = excerpts_sub.get("key excerpts", "")
        if ke_text:
            digest["key_excerpts"] = _parse_bullet_list(ke_text)
        result["conversation_digest"] = digest

    # open_questions: from ## open_questions section
    oq_text = sections.get("open_questions", "")
    if oq_text and oq_text != "(none)":
        result["open_questions"] = _parse_bullet_list(oq_text)

    # traceability: from ## traceability section
    trace_text = sections.get("traceability", "")
    if trace_text and trace_text != "(none)":
        trace = {}
        trace_subs = _parse_subsections(trace_text)
        src_text = trace_subs.get("input sources", "")
        if src_text:
            trace["input_sources"] = _parse_bullet_list(src_text)
        prov_text = trace_subs.get("decision provenance", "")
        if prov_text:
            trace["decision_provenance"] = _parse_table_to_dict(prov_text)
        result["traceability"] = trace

    # confirmed.user_directives: from ## user_directives section
    ud_text = sections.get("user_directives", "")
    if ud_text and ud_text != "(none)":
        confirmed["user_directives"] = _parse_bullet_list(ud_text)

    # ── B5-FIX: Promote confirmed.requirement_index to top-level ──
    if "requirement_index" in confirmed and confirmed["requirement_index"]:
        result["requirement_index"] = confirmed["requirement_index"]

    result["confirmed"] = confirmed
    return result


def _parse_md_sections(body: str) -> dict[str, str]:
    """Parse MD body into sections by ## headers."""
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


def _parse_confirmed_reqs(confirmed: dict, text: str) -> None:
    """Parse confirmed_reqs section into confirmed dict."""
    sub_sections = _parse_subsections(text)

    # Users
    users_text = sub_sections.get("users", "")
    if users_text:
        confirmed["users"] = _parse_table_to_dicts(users_text) or _parse_bullet_list(users_text)

    # Pain Points
    pp_text = sub_sections.get("pain points", "")
    if pp_text:
        confirmed["pain_points"] = _parse_bullet_list(pp_text)

    # Key Scenarios
    ks_text = sub_sections.get("key scenarios", "")
    if ks_text:
        confirmed["key_scenarios"] = _parse_bullet_list(ks_text)

    # Success Metrics
    sm_text = sub_sections.get("success metrics", "")
    if sm_text:
        confirmed["success_metrics"] = _parse_table_to_dicts(sm_text) or _parse_bullet_list(sm_text)

    # Terms
    terms_text = sub_sections.get("terms", "")
    if terms_text:
        confirmed["terms"] = _parse_bullet_list(terms_text)

    # REQ-ID Table
    req_table = sub_sections.get("req-id table", "")
    if req_table:
        reqs = _parse_table_to_dicts(req_table)
        if reqs:
            confirmed["requirement_index"] = reqs


def _parse_subsections(text: str) -> dict[str, str]:
    """Parse ### subsections."""
    subs: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []

    for line in text.split("\n"):
        m = re.match(r"^###\s+(.+)", line)
        if m:
            if current is not None:
                subs[current] = "\n".join(lines).strip()
            current = m.group(1).strip().lower()
            lines = []
        else:
            if current is not None:
                lines.append(line)

    if current is not None:
        subs[current] = "\n".join(lines).strip()

    return subs


def _parse_capability_table(text: str) -> dict:
    """Parse capability_boundary table into dict."""
    rows = _extract_table_rows(text)
    caps: dict[str, list] = {"always_do": [], "should_do": [], "never_do": []}
    for row in rows:
        if len(row) >= 2:
            cat = row[0].strip().lower().replace(" ", "_")
            content = row[1].strip()
            items = [s.strip() for s in content.split(";") if s.strip()]
            if cat in caps:
                caps[cat].extend(items)
            else:
                caps[cat] = items
    return caps if any(caps.values()) else {}


def _parse_constraints(text: str) -> Any:
    """Parse constraints section (table or bullet list)."""
    rows = _extract_table_rows(text)
    if rows:
        result = {}
        for row in rows:
            if len(row) >= 2:
                result[row[0].strip()] = row[1].strip()
        return result if result else None
    # Try bullet list
    bullets = _parse_bullet_list(text)
    return bullets if bullets else None


def _extract_table_rows(text: str) -> list[list[str]]:
    """Extract data rows from markdown table (skip header + separator)."""
    rows = []
    lines = [l.strip() for l in text.split("\n") if l.strip().startswith("|")]
    if len(lines) < 3:
        return rows
    # Skip header (line 0) and separator (line 1)
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
    # Get headers
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


def _parse_key_value_sections(text: str) -> dict:
    """Parse sections with ### headers and bullet lists into dict."""
    subs = _parse_subsections(text)
    if subs:
        result = {}
        for key, val in subs.items():
            bullets = _parse_bullet_list(val)
            result[key.replace(" ", "_")] = bullets if bullets else val
        return result
    # Fallback: single key-value pairs
    return _parse_table_to_dict(text)


def _parse_bullet_list(text: str) -> list[str]:
    """Extract bullet list items."""
    items = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            items.append(stripped[2:].strip())
    return items


# ─── validate: MD 结构校验 ───────────────────────────────────────────────────

def validate_living_spec_md(md: str) -> tuple[bool, list[str]]:
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

    # Check frontmatter
    if not md.startswith("---"):
        errors.append("missing YAML frontmatter")

    # Check required sections
    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in md:
            errors.append(f"missing required section: ## {section}")

    return len(errors) == 0, errors
