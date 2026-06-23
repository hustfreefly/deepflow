#!/usr/bin/env python3
"""
DocUpdate 依赖索引构建器

从 CodeGraph SQLite + Python AST 提取符号，
扫描所有 .md 文件中的引用，生成 doc_index.json。

用法:
    python3 scripts/docupdate/build_index.py
"""

import ast
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = DEEPFLOW_ROOT / ".doc_index.json"
EXCLUDE_DIRS = {"ARCHIVED", "docs/archive", "blackboard", "__pycache__", ".git", ".codegraph", "node_modules", "venv", ".deepflow/frontend"}


def _should_exclude(path: Path) -> bool:
    s = str(path)
    return any(d in s for d in EXCLUDE_DIRS)


def _extract_symbols_from_codegraph() -> dict:
    """从 CodeGraph SQLite 提取关键符号。"""
    db_path = DEEPFLOW_ROOT / ".codegraph" / "codegraph.db"
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, kind, file_path
        FROM nodes
        WHERE kind IN ('function', 'class', 'constant', 'method')
          AND language = 'python'
    """)
    symbols = {}
    for name, kind, file_path in cursor.fetchall():
        if not name.startswith("_") or kind == "class":
            symbols[name] = {"file": file_path, "kind": kind}
    conn.close()
    return symbols


def _extract_symbols_from_ast() -> dict:
    """Fallback: Python AST 提取符号。"""
    symbols = {}
    for py_file in DEEPFLOW_ROOT.rglob("*.py"):
        if _should_exclude(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text())
            rel = str(py_file.relative_to(DEEPFLOW_ROOT))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        symbols[node.name] = {"file": rel, "kind": "function"}
                elif isinstance(node, ast.ClassDef):
                    if not node.name.startswith("_"):
                        symbols[node.name] = {"file": rel, "kind": "class"}
        except Exception:
            pass
    return symbols


def _extract_words(text: str) -> set:
    """从文本中提取所有标识符单词（快速）。"""
    return set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{3,}', text))


def _scan_markdown_refs(symbols: dict) -> dict:
    """扫描 .md 文件中的符号引用（优化版：集合交集）。"""
    refs = defaultdict(list)
    sym_names = set(symbols.keys())

    # 按文件分组符号
    file_to_syms = defaultdict(set)
    all_src_files = set()
    for sym, info in symbols.items():
        file_to_syms[info["file"]].add(sym)
        all_src_files.add(info["file"])

    md_count = 0
    for md_file in DEEPFLOW_ROOT.rglob("*.md"):
        if _should_exclude(md_file):
            continue
        md_count += 1
        rel_path = str(md_file.relative_to(DEEPFLOW_ROOT))
        content = md_file.read_text(errors="ignore")

        found = {}  # sym -> (context, confidence)

        # 策略 1: 代码块中提取单词，与符号名做集合交集（高置信度）
        code_blocks = re.findall(r'```(?:\w*)\n(.*?)```', content, re.DOTALL)
        for block in code_blocks:
            words = _extract_words(block)
            hits = words & sym_names
            for sym in hits:
                if sym not in found:
                    found[sym] = ("code_block", "high")

        # 策略 2: 内联代码引用（中置信度）
        inline_matches = re.findall(r'`([^`]+)`', content)
        for ref_text in inline_matches:
            words = _extract_words(ref_text)
            hits = words & sym_names
            for sym in hits:
                if sym not in found:
                    found[sym] = (f"inline: `{ref_text[:40]}`", "medium")

        # 策略 3: 路径引用（高置信度）
        for src_file in all_src_files:
            if src_file in content:
                for sym in file_to_syms[src_file]:
                    if sym not in found:
                        found[sym] = (f"path: {src_file}", "high")

        # 写入 refs
        for sym, (context, confidence) in found.items():
            refs[sym].append({
                "file": rel_path,
                "context": context,
                "confidence": confidence,
            })

    return dict(refs)


def build_index():
    """构建完整索引。"""
    # 优先 CodeGraph，fallback AST
    symbols = _extract_symbols_from_codegraph()
    source = "CodeGraph"
    if not symbols:
        symbols = _extract_symbols_from_ast()
        source = "Python AST (fallback)"

    # 扫描 markdown 引用
    md_refs = _scan_markdown_refs(symbols)

    # 组装
    index = {}
    for sym_name, sym_info in symbols.items():
        index[sym_name] = {
            "defined_in": sym_info["file"],
            "kind": sym_info["kind"],
            "referenced_by_docs": md_refs.get(sym_name, []),
        }

    # 统计
    total_refs = sum(len(v["referenced_by_docs"]) for v in index.values())
    syms_with_refs = sum(1 for v in index.values() if v["referenced_by_docs"])

    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"✅ DocUpdate 索引已构建 (来源: {source})")
    print(f"   符号数: {len(index)}")
    print(f"   有引用的符号: {syms_with_refs}")
    print(f"   总引用数: {total_refs}")
    print(f"   输出: {INDEX_PATH}")
    return index


if __name__ == "__main__":
    build_index()
