"""
ADR-009 MD Track Extractor
从域输出 MD 中提取 track.json 数据 + 结构验证。

Phase 2a: validate_md_structure() — 纯函数，L1 确定性校验
Phase 2b: extract_track_json() — mistune AST 解析，提取失败 raise ValueError

职责分离：本模块只做提取，不碰文件系统。
Orchestrator 调用 Blackboard API 写入文件。
"""

from __future__ import annotations

import re
import yaml
from typing import Any

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
        "required_sections": ["meta_info", "solution_structure", "requirement_coverage", "implementation_plan"],
        "optional_sections": ["quality_impl"],
        "min_length": 800,
        "req_id_semantics": "requirement coverage mapping",
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

    # 2. 必填章节检查
    for section in config["required_sections"]:
        if f"## {section}" not in md_content:
            errors.append(f"缺少必要章节: ## {section}")

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

    # 提取表格数据
    tables = _extract_tables_mistune(md_content)
    if not tables:
        raise ValueError("未找到任何表格，无法提取结构化数据")

    # 提取 REQ-IDs
    req_ids = _extract_req_ids(tables)

    # 提取 Gate verdicts
    gate_summary = _extract_gate_verdict(tables)

    # 计算 anchors（章节位置）
    anchors = _compute_anchors(md_content)

    # 构建 track.json
    track = {
        "schema_version": "3.0.0",
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
        "anchors": anchors,
    }

    # 验证 track.json 完整性
    if not track["gate_summary"]:
        raise ValueError("Gate 决策表提取为空，track.json 不完整")

    # 验证 L3 合并 verdict 存在
    l3_keys = [k for k in track["gate_summary"] if "L3" in k or "合并" in k]
    if not l3_keys:
        raise ValueError("未找到 L3 合并 verdict，Gate 决策表不完整")

    return track
