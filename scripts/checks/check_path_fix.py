#!/usr/bin/env python3
"""
路径硬编码检查 — 契约笼子

检测活跃 prompt 和代码文件中是否残留 /Users/xxx 等硬编码路径。
开源项目可移植性的基本保障。

用法:
    python scripts/checks/check_path_fix.py
"""

import re
import sys
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent

# 只检查活跃文件（排除归档、历史、审计）
SCAN_DIRS = [
    DEEPFLOW_ROOT / "domains" / "solution_pro" / "prompts",
    DEEPFLOW_ROOT / "domains" / "spec_pro",
    DEEPFLOW_ROOT / "domains" / "ship_pro",
    DEEPFLOW_ROOT / "domains" / "research_pro",
    DEEPFLOW_ROOT / "domains" / "solution_pro" / "python_preamble.txt",
    DEEPFLOW_ROOT / "domains" / "solution_pro" / "SKILL.md",
]

SKIP_PATTERNS = [
    "_archive",
    "ARCHIVED",
    "proposals",
    "AUDIT",
    "audit_edge_cases",
    "reviews",
    "__pycache__",
]

HARDCODED_PATH_RE = re.compile(
    r"/Users/[a-zA-Z0-9_-]+/\.openclaw/workspace/\.deepflow"
)

ALLOWED_IN = {
    ".pyc",
    ".json",  # blackboard data files
}


def should_skip(path: Path) -> bool:
    path_str = str(path)
    return any(skip in path_str for skip in SKIP_PATTERNS)


def check_file(path: Path) -> list[str]:
    """返回该文件中发现的硬编码路径行号列表"""
    if path.suffix in ALLOWED_IN:
        return []
    violations = []
    try:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HARDCODED_PATH_RE.search(line):
                # 跳过包含 {deepflow_root} 的行（模板变量，不是硬编码）
                if "{deepflow_root}" in line or "{DEEPFLOW_ROOT}" in line:
                    continue
                violations.append(f"  L{line_no}: {line.strip()[:100]}")
    except (UnicodeDecodeError, PermissionError):
        pass
    return violations


def main():
    all_violations = {}

    for scan_target in SCAN_DIRS:
        if scan_target.is_file():
            violations = check_file(scan_target)
            if violations:
                all_violations[str(scan_target.relative_to(DEEPFLOW_ROOT))] = violations
        elif scan_target.is_dir():
            for ext in ("*.md", "*.txt", "*.py"):
                for path in scan_target.rglob(ext):
                    if should_skip(path):
                        continue
                    violations = check_file(path)
                    if violations:
                        all_violations[str(path.relative_to(DEEPFLOW_ROOT))] = violations

    if all_violations:
        print(f"❌ FAIL: {len(all_violations)} 个文件包含硬编码路径")
        for filepath, lines in sorted(all_violations.items()):
            print(f"\n  {filepath}:")
            for line in lines[:3]:  # 最多显示 3 行
                print(line)
            if len(lines) > 3:
                print(f"  ... and {len(lines) - 3} more")
        print(f"\n修复: 将 /Users/xxx/.openclaw/workspace/.deepflow 替换为 {{deepflow_root}}")
        return 1
    else:
        print("✅ PASS: 活跃文件中无硬编码路径")
        return 0


if __name__ == "__main__":
    sys.exit(main())
