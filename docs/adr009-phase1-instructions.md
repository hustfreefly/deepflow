# ADR-009 Phase 1: 契约层修复 — Worker 指令

## 任务概述

修复 frozen_living_md.py 和 solution_living_md.py 的 round-trip 信息丢失问题，补充测试，跑通 pytest。

---

## 1. frozen_living_md.py 修复

文件路径: `.deepflow/domains/solution_pro/frozen_living_md.py`

### 1.1 新增 helper 函数

在文件末尾（_extract_table_rows 之后）新增：

```python
def _parse_table_to_dicts(text: str) -> list[dict]:
    """Parse markdown table to list of dicts."""
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
                d[h] = row[i].replace("\\|", "|")  # unescape pipes
            if d:
                pass
        if d:
            result.append(d)
    return result


def _escape_pipe(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return str(text).replace("|", "\\|")
```

### 1.2 render 修改

**key_decisions（F2）**: 从 bullet list 改为表格

当前代码（约 line 100-110）:
```python
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
```

替换为:
```python
    key_decisions = data.get("key_decisions", [])
    if key_decisions:
        lines.append("## key_decisions")
        lines.append("")
        lines.append("| # | decision | rationale | alternatives |")
        lines.append("|---|----------|-----------|--------------|")
        for i, d in enumerate(key_decisions, 1):
            if isinstance(d, dict):
                dec = _escape_pipe(d.get("decision", d.get("description", str(d))))
                rat = _escape_pipe(d.get("rationale", ""))
                alt = _escape_pipe(d.get("alternatives", ""))
                lines.append(f"| {i} | {dec} | {rat} | {alt} |")
            else:
                lines.append(f"| {i} | {_escape_pipe(str(d))} | | |")
        lines.append("")
```

**risk_summary（F3）**: 从 bullet list 改为表格

当前代码（约 line 130-145）:
```python
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
```

替换为:
```python
    risk_summary = data.get("risk_summary", data.get("risk_mitigations"))
    if risk_summary:
        lines.append("## risk_summary")
        lines.append("")
        if isinstance(risk_summary, list):
            lines.append("| # | risk | severity | probability | mitigation |")
            lines.append("|---|------|----------|-------------|------------|")
            for i, r in enumerate(risk_summary, 1):
                if isinstance(r, dict):
                    risk = _escape_pipe(r.get("risk", r.get("description", str(r))))
                    sev = _escape_pipe(r.get("severity", ""))
                    prob = _escape_pipe(r.get("probability", ""))
                    mit = _escape_pipe(r.get("mitigation", ""))
                    lines.append(f"| {i} | {risk} | {sev} | {prob} | {mit} |")
                else:
                    lines.append(f"| {i} | {_escape_pipe(str(r))} | | | |")
        else:
            lines.append(str(risk_summary))
        lines.append("")
```

**implementation_phases（F4）**: 从 bullet list 改为表格

当前代码（约 line 147-157）:
```python
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
```

替换为:
```python
    impl_phases = data.get("implementation_phases", [])
    if impl_phases:
        lines.append("## implementation_phases")
        lines.append("")
        lines.append("| phase | title | timeline | effort |")
        lines.append("|-------|-------|----------|--------|")
        for phase in impl_phases:
            if isinstance(phase, dict):
                p = _escape_pipe(phase.get("phase", ""))
                title = _escape_pipe(phase.get("title", phase.get("name", "")))
                timeline = _escape_pipe(phase.get("timeline", phase.get("duration", "")))
                effort = _escape_pipe(phase.get("estimated_effort", phase.get("effort", "")))
                lines.append(f"| {p} | {title} | {timeline} | {effort} |")
            else:
                lines.append(f"| | {_escape_pipe(str(phase))} | | |")
        lines.append("")
```

**去除截断（constraints）**: 

当前（约 line 70）:
```python
                desc = str(c.get("description", c.get("text", "")))[:100]
```
替换为:
```python
                desc = _escape_pipe(str(c.get("description", c.get("text", ""))))
```

同样在 requirements section（约 line 85）:
```python
                    desc = str(r.get("description", r.get("text", "")))[:100]
```
替换为:
```python
                    desc = _escape_pipe(str(r.get("description", r.get("text", ""))))
```

**去除截断（semantic_anchors）**:

当前（约 line 163）:
```python
                lines.append(f"| {a.get('name', '?')} | {a.get('category', '?')} | {str(a.get('constraint', ''))[:60]} |")
```
替换为:
```python
                lines.append(f"| {a.get('name', '?')} | {a.get('category', '?')} | {_escape_pipe(str(a.get('constraint', '')))} |")
```

### 1.3 parse 修改

**frontmatter 解析（F1 + F5）**:

当前（约 line 185-190）:
```python
    # Parse YAML Frontmatter
    body = md
    if md.startswith("---"):
        end = md.find("---", 3)
        if end != -1:
            body = md[end + 3:]
```

替换为:
```python
    # Parse YAML Frontmatter (F1+F5: extract schema_version + session_id)
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
                        result["session_id"] = val
```

**key_decisions 解析（F2）**: 表格优先，bullet list fallback

当前（约 line 220-230）:
```python
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
```

替换为:
```python
    # key_decisions (F2: table → list[dict], bullet list fallback → list[str])
    kd_text = sections.get("key_decisions", "")
    if kd_text:
        table_decisions = _parse_table_to_dicts(kd_text)
        if table_decisions:
            result["key_decisions"] = [
                {
                    "decision": d.get("decision", ""),
                    "rationale": d.get("rationale", ""),
                    "alternatives": d.get("alternatives", ""),
                }
                for d in table_decisions
            ]
        else:
            # Fallback: bullet list (backward compat)
            decisions = []
            for line in kd_text.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    decisions.append(line[2:].strip())
            if decisions:
                result["key_decisions"] = decisions
```

**risk_summary 解析（F3）**: 表格优先，bullet list fallback

当前（约 line 245-255）:
```python
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
```

替换为:
```python
    # risk_summary (F3: table → list[dict], bullet list fallback → list[str])
    rs_text = sections.get("risk_summary", "")
    if rs_text:
        table_risks = _parse_table_to_dicts(rs_text)
        if table_risks:
            risks = [
                {
                    "risk": r.get("risk", ""),
                    "severity": r.get("severity", ""),
                    "probability": r.get("probability", ""),
                    "mitigation": r.get("mitigation", ""),
                }
                for r in table_risks
            ]
            result["risk_summary"] = risks
            result["risk_mitigations"] = risks
        else:
            # Fallback: bullet list (backward compat)
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
```

**implementation_phases 解析（F4）**: 表格优先，bullet list fallback

当前（约 line 257-267）:
```python
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
```

替换为:
```python
    # implementation_phases (F4: table → list[dict], bullet list fallback → list[str])
    ip_text = sections.get("implementation_phases", "")
    if ip_text:
        table_phases = _parse_table_to_dicts(ip_text)
        if table_phases:
            phases = [
                {
                    "phase": p.get("phase", ""),
                    "title": p.get("title", ""),
                    "timeline": p.get("timeline", ""),
                    "estimated_effort": p.get("effort", ""),
                }
                for p in table_phases
            ]
            result["implementation_phases"] = phases
        else:
            # Fallback: bullet list (backward compat)
            phases = []
            for line in ip_text.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    phases.append(line[2:].strip())
            if phases:
                result["implementation_phases"] = phases
```

---

## 2. solution_living_md.py 修复

文件路径: `.deepflow/domains/solution_pro/solution_living_md.py`

### 2.1 full_solution 结构化解析（S1）

当前 parse 中（约 line 350）:
```python
    # S12: full_solution
    fs_text = sections.get("full_solution", "")
    if fs_text:
        result["full_solution"] = fs_text.strip()
```

替换为:
```python
    # S12: full_solution (S1: structured parse — detect **Title**: / **Summary**: pattern)
    fs_text = sections.get("full_solution", "")
    if fs_text:
        # Try structured parse: **Title**: xxx / **Summary**: xxx
        title_m = re.search(r"\*\*Title\*\*:\s*(.+)", fs_text)
        summary_m = re.search(r"\*\*Summary\*\*:\s*(.+)", fs_text)
        if title_m or summary_m:
            fs_dict: dict[str, Any] = {}
            if title_m:
                fs_dict["title"] = title_m.group(1).strip()
            if summary_m:
                fs_dict["summary"] = summary_m.group(1).strip()
            # Key sections
            ks_items = re.findall(r"^- (.+)$", fs_text, re.MULTILINE)
            if ks_items:
                fs_dict["key_sections"] = ks_items
            result["full_solution"] = fs_dict
        else:
            result["full_solution"] = fs_text.strip()
```

### 2.2 gate_decisions 解析（S2）

在 parse 函数中，在 `# S9: covered_req_ids` 之前，新增:
```python
    # S8: gate_decisions (S2: parse gate decisions table)
    gd_text = sections.get("gate_decisions", "")
    if gd_text:
        result["gate_decisions"] = _parse_table_to_dicts(gd_text)
```

注意: solution_living_md.py 已有 `_parse_table_to_dicts` 函数，可以直接使用。

### 2.3 去除硬截断

在 render 函数中:

1. risk_summary 表格（约 line 200）:
```python
                lines.append(f"| {i} | {r.get('risk', '')[:40]} | {r.get('severity', '')} | {r.get('probability', '')} | {r.get('mitigation', '')[:60]} |")
```
替换为:
```python
                lines.append(f"| {i} | {r.get('risk', '')} | {r.get('severity', '')} | {r.get('probability', '')} | {r.get('mitigation', '')} |")
```

2. metadata dict values（约 line 65）:
```python
                v_str = json.dumps(v, ensure_ascii=False)[:80]
```
替换为:
```python
                v_str = json.dumps(v, ensure_ascii=False)
```

---

## 3. 新增 test_frozen_living_md.py

文件路径: `.deepflow/domains/solution_pro/tests/test_frozen_living_md.py`

测试用例:
1. `test_render_basic` — 基础渲染，检查 required sections 存在
2. `test_parse_frontmatter` — 验证 schema_version + session_id 解析
3. `test_parse_key_decisions_table` — 表格格式解析为 list[dict]
4. `test_parse_risk_summary_table` — 表格格式解析为 list[dict]
5. `test_parse_implementation_phases_table` — 表格格式解析为 list[dict]
6. `test_round_trip_minimal` — 最小 dict round-trip
7. `test_round_trip_rich` — 丰富 dict round-trip，保留率 ≥ 95%
8. `test_round_trip_backward_compat` — 旧 bullet list 格式仍可解析
9. `test_validate` — 校验函数
10. `test_empty_fields` — 空 semantic_anchors、空 constraints

Fixture:
```python
RICH_FROZEN_SPEC = {
    "schema_version": "2.0.0",
    "session_id": "test_frozen_001",
    "topic": "Test Architecture",
    "solution_type": "architecture",
    "domain": "test",
    "mode": "full",
    "constraints": [
        {"req_id": "REQ-001", "description": "Must support high availability", "priority": "MUST"},
        {"req_id": "REQ-002", "description": "Must complete within 30 days", "priority": "SHOULD"},
    ],
    "key_decisions": [
        {"decision": "Use microservices", "rationale": "Scalability", "alternatives": "Monolith (rejected)"},
        {"decision": "Use PostgreSQL", "rationale": "ACID compliance", "alternatives": "MongoDB"},
    ],
    "risk_summary": [
        {"risk": "Context degradation", "severity": "高", "probability": "Medium", "mitigation": "Periodic restart"},
    ],
    "implementation_phases": [
        {"phase": "1", "title": "Foundation", "timeline": "Week 1-2", "estimated_effort": "2 weeks"},
        {"phase": "2", "title": "Core", "timeline": "Week 3-4", "estimated_effort": "2 weeks"},
    ],
    "semantic_anchors": [
        {"name": "HA Pattern", "category": "architecture", "constraint": "REQ-001"},
    ],
    "covered_req_ids": ["REQ-001", "REQ-002"],
}
```

---

## 4. 验证

```bash
cd /Users/allen/.openclaw/workspace/.deepflow
python -m pytest domains/solution_pro/tests/test_frozen_living_md.py -v
python -m pytest domains/solution_pro/tests/test_solution_living_md.py -v
python -m pytest domains/solution_pro/tests/ -v
```

全部通过 = Phase 1 完成。
