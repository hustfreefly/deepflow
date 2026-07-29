"""
ADR-009 MD Track Extractor
从域输出 MD 中提取 track.json 数据 + 结构验证。

Phase 2a: validate_md_structure() — 纯函数，L1 确定性校验
Phase 2b: extract_track_json() — mistune AST 解析，提取失败 raise ValueError

职责分离：本模块只做提取，不碰文件系统。
Orchestrator 调用 Blackboard API 写入文件。
"""

from __future__ import annotations

import logging
import re
import yaml
from typing import Any

logger = logging.getLogger(__name__)

try:
    import mistune
except ImportError:
    mistune = None  # fallback to regex if mistune unavailable

# ─── Domain Configuration ───────────────────────────────────────────────────

DOMAIN_CONFIG = {
    "spec_pro": {
        "required_sections": [
            "meta_info", "confirmed_reqs", "capability_boundary",
            "constraints", "gate_decisions",
        ],
        "optional_sections": [
            "overview", "inferred", "quality_attrs", "conversation_summary",
            "user_directives", "open_questions", "guardrails",
            "traceability", "solution_pro_hints", "route_recommendation",
            "semantic_anchors",
        ],
        "min_length": 500,
        "req_id_semantics": "functional/quality/constraint requirements",
    },
    "solution_pro": {
        "required_sections": ["meta_info"],
        "optional_sections": ["overview", "solution_structure", "key_decisions", "implementation_phases", "implementation_plan", "requirement_coverage", "quality_impl", "semantic_anchors", "gate_decisions"],
        "section_aliases": {"implementation_plan": ["implementation_phases"], "solution_structure": ["overview", "key_decisions"]},
        "min_length": 300,
        "req_id_semantics": "requirement coverage mapping",
        "summary_sections": {
            "key_decisions": "关键决策表",
            "implementation_phases": "实施阶段表",
            "risks": "风险登记表",
            "requirement_coverage": "需求覆盖章节",
        },
    },
    "ship_pro": {
        "required_sections": ["meta_info", "work_packages", "execution_order"],
        "optional_sections": ["req_traceability"],
        "min_length": 600,
        "req_id_semantics": "WP coverage mapping",
    },
    "deliver_pro": {
        "required_sections": ["meta_info", "deliverables", "execution_guide"],
        "optional_sections": ["acceptance_summary"],
        "min_length": 200,
        "req_id_semantics": "acceptance criteria mapping",
    },
    "research_pro": {
        "required_sections": ["meta_info", "findings", "recommendations"],
        "optional_sections": ["research_questions", "references"],
        "min_length": 300,
        "req_id_semantics": "research question mapping",
    },
}

GATE_VERDICTS = {"PASS", "CONDITIONAL", "FAIL"}

# ─── Phase 2a: Validate ─────────────────────────────────────────────────────

def validate_md_structure(md_content: str, domain: str) -> tuple[bool, str, list[str]]:
    """
    L1: MD 结构校验（纯函数，不碰文件系统）。
    
    Returns:
        (passed, message, warnings)
        - passed: bool — 是否通过校验
        - message: str — 结果说明
        - warnings: list[str] — 非阻断警告
    """
    if domain not in DOMAIN_CONFIG:
        return False, f"未知域: {domain}，合法域: {list(DOMAIN_CONFIG.keys())}", []

    config = DOMAIN_CONFIG[domain]
    warnings: list[str] = []
    errors: list[str] = []

    # 1. YAML frontmatter 检查
    if not md_content.strip().startswith("---"):
        errors.append("缺少 YAML frontmatter（应以 --- 开头）")

    # 2. 必填章节检查（支持别名：如 implementation_plan 可用 implementation_phases 替代）
    section_aliases = config.get("section_aliases", {})
    for section in config["required_sections"]:
        aliases = section_aliases.get(section, [])
        found = f"## {section}" in md_content
        if not found:
            for alias in aliases:
                if f"## {alias}" in md_content:
                    found = True
                    break
        if not found:
            all_names = [section] + aliases
            errors.append(f"缺少必要章节: ## {' 或 '.join(all_names)}")

    # 3. 最小长度检查（按域）
    if len(md_content) < config["min_length"]:
        errors.append(
            f"内容过短（{len(md_content)} < {config['min_length']} 字符，域: {domain}）"
        )

    # 4. 表格检查（warning，非阻断 — 非软件域可能没表格）
    if "|" not in md_content:
        warnings.append("未检测到结构化表格（非软件域可忽略）")

    # 5. Gate 决策表检查（warning）
    if "## Gate 决策" not in md_content and "## Gate Decision" not in md_content and "## gate_decisions" not in md_content:
        warnings.append("缺少 Gate 决策表")

    passed = len(errors) == 0
    message = "校验通过" if passed else f"校验失败（{len(errors)} 个错误）: {'; '.join(errors)}"
    return passed, message, warnings


# ─── Phase 2b: Extract ──────────────────────────────────────────────────────

def _extract_tables_mistune(md_content: str) -> list[dict]:
    """用 mistune 解析 MD，提取所有表格为 list[dict]。"""
    if mistune is None:
        return _extract_tables_regex(md_content)

    md = mistune.create_markdown(renderer=None)
    tokens = md(md_content)

    tables = []
    for token in tokens:
        if token.get("type") == "table":
            header = [cell.get("text", "").strip() for cell in token.get("head", [])]
            rows = []
            for row in token.get("body", []):
                row_data = {}
                for i, cell in enumerate(row):
                    if i < len(header):
                        row_data[header[i]] = cell.get("text", "").strip()
                rows.append(row_data)
            tables.append({"header": header, "rows": rows})
    return tables


def _extract_tables_regex(md_content: str) -> list[dict]:
    """正则 fallback（mistune 不可用时）。"""
    tables = []
    lines = md_content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line and i + 1 < len(lines) and "---" in lines[i + 1]:
            # Found table header
            header = [c.strip() for c in line.split("|") if c.strip()]
            rows = []
            i += 2  # skip separator line
            while i < len(lines) and "|" in lines[i]:
                cells = [c.strip() for c in lines[i].split("|") if c.strip()]
                if len(cells) == len(header):
                    rows.append(dict(zip(header, cells)))
                i += 1
            if header and rows:
                tables.append({"header": header, "rows": rows})
        else:
            i += 1
    return tables


def _extract_frontmatter(md_content: str) -> dict:
    """提取 YAML frontmatter 元数据。"""
    if not md_content.strip().startswith("---"):
        return {}
    parts = md_content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def _extract_gate_verdict(tables: list[dict]) -> dict:
    """从 Gate 决策表提取 L1/L2/L3 verdict。"""
    gate_summary = {}
    for table in tables:
        header = table.get("header", [])
        if "检查层" in header or "Check Layer" in header or "check_layer" in header:
            for row in table["rows"]:
                layer_key = row.get("检查层", row.get("Check Layer", row.get("check_layer", ""))).strip()
                result = row.get("结果", row.get("Result", row.get("result", ""))).strip()
                # Extract verdict (PASS/CONDITIONAL/FAIL)
                for verdict in GATE_VERDICTS:
                    if verdict in result:
                        gate_summary[layer_key] = verdict
                        break
    return gate_summary


def _extract_req_ids(tables: list[dict]) -> list[str]:
    """从 REQ-ID 相关表格提取 REQ-ID 列表。"""
    req_ids = []
    for table in tables:
        header = table.get("header", [])
        # Look for tables containing REQ-ID column
        req_col = None
        for col in header:
            if "REQ" in col.upper() or "REQ-ID" in col.upper():
                req_col = col
                break
        if req_col:
            for row in table["rows"]:
                val = row.get(req_col, "").strip()
                if re.match(r"REQ-\d+", val):
                    req_ids.append(val)
    return list(dict.fromkeys(req_ids))  # deduplicate preserving order


def _compute_anchors(md_content: str) -> dict:
    """计算各章节的行号位置（替代 MD 中的 anchor 注释）。"""
    anchors = {}
    for i, line in enumerate(md_content.split("\n"), 1):
        if line.startswith("## "):
            section_name = line[3:].strip()
            anchors[section_name] = {"line": i, "section": section_name}
    return anchors


# ─── Phase 2c: Semantic & Summary Extraction ───────────────────────────────


def _extract_semantic_anchors(md_content: str) -> list[dict[str, str]]:
    """
    从 ## semantic_anchors 章节提取语义锚点。

    支持两种格式：
    1. 表格格式: | name | category | constraint |
    2. 列表格式: - [category] name: constraint

    Returns:
        [{"name": "...", "category": "...", "constraint": "..."}]
    """
    anchors: list[dict[str, str]] = []

    # Locate the ## semantic_anchors section
    section_text = _extract_section_text(md_content, "semantic_anchors")

    # Try table format first (only if section exists): | name | category | constraint |
    table_rows = _extract_table_rows_from_text(section_text) if section_text else []
    if table_rows and len(table_rows) >= 2:
        header = [h.strip().lower() for h in table_rows[0]]
        name_idx = _find_col(header, ["name"])
        cat_idx = _find_col(header, ["category"])
        con_idx = _find_col(header, ["constraint"])
        if name_idx is not None:
            for row_cells in table_rows[1:]:
                if len(row_cells) > max(name_idx, cat_idx or 0, con_idx or 0):
                    anchors.append({
                        "name": row_cells[name_idx].strip(),
                        "category": row_cells[cat_idx].strip() if cat_idx is not None else "",
                        "constraint": row_cells[con_idx].strip() if con_idx is not None else "",
                    })
        if anchors:
            return anchors

    # Fallback: list format - [category] name: constraint
    # Search in section first, then fall back to full document
    search_text = section_text if section_text else md_content
    for m in re.finditer(r"^\s*-\s+\[([^\]]*)\]\s+([^:]+):\s+(.+)$", search_text, re.MULTILINE):
        anchors.append({
            "category": m.group(1).strip(),
            "name": m.group(2).strip(),
            "constraint": m.group(3).strip(),
        })

    return anchors


def _extract_summary(md_content: str) -> dict[str, int]:
    """
    从 MD 各章节表格行数计算 summary 统计。

    - ## 关键技术决策 / ## key_decisions → key_decisions_count
    - ## 实施阶段 / ## implementation_phases / ## 实施计划 → implementation_phases_count
    - ## 风险评估 / ## risk_summary / ## 风险与应对 → risk_count

    Returns:
        {"key_decisions_count": int, "implementation_phases_count": int, "risk_count": int}
    """
    summary: dict[str, int] = {}

    # key_decisions: Chinese or English section names
    kd_text = _extract_section_text(md_content, "key_decisions", "关键技术决策", "关键决策")
    summary["key_decisions_count"] = _count_data_rows(kd_text) if kd_text else 0

    # implementation_phases
    ip_text = _extract_section_text(md_content, "implementation_phases", "实施阶段", "实施计划")
    summary["implementation_phases_count"] = _count_data_rows(ip_text) if ip_text else 0

    # risk
    risk_text = _extract_section_text(md_content, "risk_summary", "风险评估", "风险与应对", "风险")
    summary["risk_count"] = _count_data_rows(risk_text) if risk_text else 0

    return summary


def _extract_constraint_coverage(md_content: str) -> dict[str, Any]:
    """
    从 ## requirement_coverage / ## 需求覆盖度 章节提取覆盖率。

    支持格式：
    1. 表格含 covered/total 或 覆盖率 行 → 解析数值
    2. 文本中 "X/Y" 模式 → 提取 covered=X, total=Y

    Returns:
        {"covered": int, "total": int, "ratio": float}
    """
    result: dict[str, Any] = {"covered": 0, "total": 0, "ratio": 0.0}

    section_text = _extract_section_text(md_content, "requirement_coverage", "需求覆盖度", "constraint_coverage")
    if not section_text:
        return result

    # Try table rows: look for patterns like "覆盖率 | 100% (8/8)" or "covered | 8"
    table_rows = _extract_table_rows_from_text(section_text)
    for row_cells in table_rows:
        if len(row_cells) >= 2:
            label = row_cells[0].strip().lower()
            value = row_cells[1].strip()
            # Pattern: "100% (8/8)" or "8/10" or just "8"
            frac_m = re.search(r"(\d+)\s*/\s*(\d+)", value)
            if frac_m:
                covered = int(frac_m.group(1))
                total = int(frac_m.group(2))
                if total > 0:
                    result["covered"] = covered
                    result["total"] = total
                    result["ratio"] = round(covered / total, 4)
                    return result
            if "covered" in label or "覆盖" in label:
                num_m = re.search(r"(\d+)", value)
                if num_m:
                    result["covered"] = int(num_m.group(1))
            if "total" in label or "总数" in label:
                num_m = re.search(r"(\d+)", value)
                if num_m:
                    result["total"] = int(num_m.group(1))

    # Fallback 1: search for "covered: X / total: Y" pattern in section text
    if result["covered"] == 0 and result["total"] == 0:
        ct_m = re.search(r"covered[:\s]+(\d+)\s*/?\s*total[:\s]+(\d+)", section_text, re.IGNORECASE)
        if ct_m:
            covered = int(ct_m.group(1))
            total = int(ct_m.group(2))
            if total > 0:
                result["covered"] = covered
                result["total"] = total
                result["ratio"] = round(covered / total, 4)
                return result

    # Fallback 2: search for X/Y pattern in section text
    if result["covered"] == 0 and result["total"] == 0:
        frac_m = re.search(r"(\d+)\s*/\s*(\d+)", section_text)
        if frac_m:
            covered = int(frac_m.group(1))
            total = int(frac_m.group(2))
            if total > 0:
                result["covered"] = covered
                result["total"] = total
                result["ratio"] = round(covered / total, 4)

    # Fallback 3: count covered items from table rows (✓, ✅, yes, 是, covered)
    if result["covered"] == 0 and result["total"] == 0 and table_rows:
        covered_indicators = {"✓", "✅", "yes", "是", "covered", "done", "完成"}
        total_rows = 0
        covered_rows = 0
        for row_cells in table_rows:
            # Skip header row and separator
            if any("---" in c for c in row_cells):
                continue
            if row_cells == table_rows[0]:
                continue  # skip header
            total_rows += 1
            # Check last meaningful cell for coverage indicator
            for cell in reversed(row_cells):
                val = cell.strip().lower()
                if val in covered_indicators:
                    covered_rows += 1
                break
        if total_rows > 0:
            result["total"] = total_rows
            result["covered"] = covered_rows
            result["ratio"] = round(covered_rows / total_rows, 4)

    # Compute ratio if we have both but ratio not set
    if result["total"] > 0 and result["ratio"] == 0.0:
        result["ratio"] = round(result["covered"] / result["total"], 4)

    return result


# ─── Helper functions for section extraction ────────────────────────────────

def _extract_section_text(md_content: str, *section_names: str) -> str:
    """
    Extract text content of a ## section by trying multiple name variants.
    Returns the text between the matched ## header and the next ## header.
    """
    lines = md_content.split("\n")
    for name in section_names:
        start_idx = None
        for i, line in enumerate(lines):
            if line.startswith("## ") and line[3:].strip().lower() == name.lower():
                start_idx = i
                break
            # Also match ### level for sub-sections like ### 关键技术决策（ADR）
            if line.startswith("### ") and name.lower() in line[4:].strip().lower():
                start_idx = i
                break
        if start_idx is not None:
            # Collect lines until next ## or ### of same/higher level
            section_lines = []
            for j in range(start_idx + 1, len(lines)):
                if lines[j].startswith("## "):
                    break
                section_lines.append(lines[j])
            return "\n".join(section_lines)
    return ""


def _extract_table_rows_from_text(text: str) -> list[list[str]]:
    """
    Extract table rows (as list of cell lists) from a text block.
    Returns list of rows, each row is a list of cell strings.
    First row is the header.
    """
    rows: list[list[str]] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line and i + 1 < len(lines) and "---" in lines[i + 1]:
            header = [c.strip() for c in line.split("|") if c.strip()]
            if header:
                rows.append(header)
                i += 2  # skip separator
                while i < len(lines) and "|" in lines[i]:
                    cells = [c.strip() for c in lines[i].split("|") if c.strip()]
                    if cells:
                        rows.append(cells)
                    i += 1
                return rows
        i += 1
    return rows


def _count_data_rows(section_text: str) -> int:
    """
    Count data rows in a section's tables (excluding header and separator lines).
    Handles multiple sub-tables within a section.
    """
    count = 0
    lines = section_text.split("\n")
    in_table = False
    header_seen = False
    for line in lines:
        stripped = line.strip()
        if "|" in stripped and not header_seen:
            # This is a header line
            in_table = True
            header_seen = True
            continue
        if in_table and "---" in stripped and header_seen:
            # Separator line, skip
            continue
        if in_table and header_seen and "|" in stripped:
            count += 1
        elif in_table and "|" not in stripped and stripped:
            # End of table
            header_seen = False
            in_table = False
    return count


def _find_col(header: list[str], candidates: list[str]) -> int | None:
    """Find column index by trying candidate names (case-insensitive)."""
    for i, h in enumerate(header):
        for c in candidates:
            if h.lower() == c.lower():
                return i
    return None


def extract_track_json(md_content: str, domain: str) -> dict[str, Any]:
    """
    从 MD 提取 track.json 数据。
    
    提取失败 → raise ValueError（不静默返回空数据）。
    
    Returns:
        track.json dict，符合 ADR-009 Schema。
    """
    if domain not in DOMAIN_CONFIG:
        raise ValueError(f"未知域: {domain}")

    # 先验证结构
    passed, msg, warnings = validate_md_structure(md_content, domain)
    if not passed:
        raise ValueError(f"MD 结构校验失败: {msg}")

    # 提取 frontmatter
    frontmatter = _extract_frontmatter(md_content)
    if not frontmatter:
        raise ValueError("无法提取 YAML frontmatter")

    # 提取表格数据（放宽：无表格仅 warning，不 raise）
    tables = _extract_tables_mistune(md_content)
    if not tables:
        logger.warning("未找到任何表格，将返回空提取结果（domain=%s）", domain)
        tables = []

    # 提取 REQ-IDs
    req_ids = _extract_req_ids(tables)

    # 提取 Gate verdicts
    gate_summary = _extract_gate_verdict(tables)

    # 计算 anchors（章节位置）
    anchors = _compute_anchors(md_content)

    # Phase 2c: 新增提取
    semantic_anchors = _extract_semantic_anchors(md_content)
    summary = _extract_summary(md_content)
    constraint_coverage = _extract_constraint_coverage(md_content)

    # 构建 track.json (schema 3.1.0)
    track = {
        "schema_version": "3.1.0",
        "domain": domain,
        "source_file": f"{domain}_output.md",
        "frontmatter": {
            "version": frontmatter.get("version", "unknown"),
            "session": frontmatter.get("session", "unknown"),
            "created": frontmatter.get("created", "unknown"),
        },
        "gate_summary": gate_summary,
        "metrics": {
            "req_ids": req_ids,
            "req_count": len(req_ids),
            "section_count": len(anchors),
            "content_length": len(md_content),
        },
        "summary": {
            **summary,
            "constraint_coverage": constraint_coverage,
        },
        "semantic_anchors": semantic_anchors,
        "anchors": anchors,
    }

    # 放宽验证：gate_summary 为空仅 warning（非所有域都有 Gate 表）
    if not gate_summary:
        logger.warning("Gate 决策表提取为空，track.json 可能不完整（domain=%s）", domain)

    # 放宽验证：L3 合并 verdict 不存在仅 warning
    l3_keys = [k for k in gate_summary if "L3" in k or "合并" in k]
    if not l3_keys and gate_summary:
        logger.warning("未找到 L3 合并 verdict，Gate 决策表可能不完整（domain=%s）", domain)

    return track
