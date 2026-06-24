#!/usr/bin/env python3
"""
DeepFlow Doctor — T5 Prompt Auditor

检测 prompts/SKILL.md 中教了 LLM 使用不支持的参数、方法或模式。

核心思路: LLM 犯错 ≠ LLM 的锅，可能是我们的文档教坏了它。
T5 扫描所有面向 LLM 的指令文档，对照已知约束，发现"教坏"的地方。

用法:
    from prompt_auditor import audit_prompts

    issues = audit_prompts(deepflow_root)
    # → [{"category": "T5", "severity": "red", "file": "...", "line": N, ...}, ...]
"""

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 已知约束规则（可配置，后续可从 config 文件加载）
# ---------------------------------------------------------------------------

UNSUPPORTED_PARAMS = {
    # tool: [不支持的参数列表]
    "sessions_spawn": ["runTimeoutSeconds", "model", "thinking"],
    "sessions_send": ["model", "thinking"],
    "sessions_yield": [],  # no known unsupported params
    "exec": ["host"],  # host is not a valid param
    "message": [],
    "cron": [],
}

# 已知的"禁止模式" — prompt 中不应该出现的指令
FORBIDDEN_PATTERNS = [
    {
        "pattern": r'from\s+openclaw\s+import',
        "description": "教 LLM 在 exec 中 import openclaw 模块（exec 环境无 SDK）",
        "fix": "使用注入的 spawn_fn 或 sessions_spawn 工具",
    },
    {
        "pattern": r'import\s+openclaw',
        "description": "教 LLM 在脚本中 import openclaw（隔离环境不可用）",
        "fix": "通过 Agent 工具调用，不要在代码中 import",
    },
    {
        "pattern": r'openclaw\s+gateway\s+restart',
        "description": "教 LLM 使用 openclaw gateway restart（服务模式会杀死进程）",
        "fix": "使用 launchctl kickstart -k",
    },
]

# 参数使用警告 — 参数存在但有限制
PARAM_WARNINGS = {
    "sessions_spawn": {
        "runTimeoutSeconds": {
            "reason": "OpenClaw 不支持 per-call timeout，需要在 agents.defaults 配置",
            "fix": "删除此参数，在 openclaw.json 的 agents.defaults.subagents.runTimeoutSeconds 配置",
        },
        "model": {
            "reason": "sessions_spawn 不支持 per-call model override",
            "fix": "在 agents 配置中设置模型，或使用 agentId 指定不同 agent",
        },
    },
}


def audit_prompts(deepflow_root: str | Path | None = None) -> list[dict]:
    """
    扫描所有面向 LLM 的指令文档，检测"教坏 LLM"的地方。

    参数:
        deepflow_root: .deepflow 根目录路径

    返回:
        T5 问题列表
    """
    root = Path(deepflow_root) if deepflow_root else Path(__file__).resolve().parent.parent.parent
    
    if not root.exists():
        return []

    issues = []

    # 扫描目标文件
    target_patterns = [
        "domains/**/prompts/*.md",
        "domains/**/prompts_archive/*.md",
        "domains/**/SKILL.md",
        "skills/**/SKILL.md",
        "domains/**/config/*.json",
    ]

    # 排除 archive 目录（历史文档不算）
    all_files = []
    for pattern in target_patterns:
        for f in root.glob(pattern):
            if "archive" in str(f).lower() or "ARCHIVED" in str(f):
                continue
            if f.is_file():
                all_files.append(f)

    for filepath in all_files:
        try:
            content = filepath.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        lines = content.split('\n')
        rel_path = str(filepath.relative_to(root)) if filepath.is_relative_to(root) else str(filepath)

        # 检查 1: 不支持的参数
        issues.extend(_check_unsupported_params(lines, rel_path, content))

        # 检查 2: 禁止模式
        issues.extend(_check_forbidden_patterns(lines, rel_path, content))

        # 检查 3: 参数使用警告
        issues.extend(_check_param_warnings(lines, rel_path, content))

    return issues


def _check_unsupported_params(lines: list[str], rel_path: str, content: str) -> list[dict]:
    """检查文档中使用了不支持的参数。"""
    issues = []

    for tool, params in UNSUPPORTED_PARAMS.items():
        if not params:
            continue
        for param in params:
            for i, line in enumerate(lines, 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('//'):
                    continue
                # Skip lines that say "禁止" or "❌" or "不支持"
                if any(kw in line for kw in ['禁止', '❌', '不支持', '不要', 'don\'t', 'never']):
                    continue

                # Word boundary check: model ≠ model_id/model_tier
                if re.search(r'\b' + re.escape(param) + r'\b', line) and tool in content:
                    issues.append({
                        "category": "T5",
                        "severity": "red",
                        "description": f"文档教 LLM 使用不支持的参数: {tool}({param})",
                        "file": rel_path,
                        "line": i,
                        "evidence": line.strip()[:150],
                        "fix": f"删除 {param}，使用全局配置或替代方案",
                        "wasted_tokens": 2000,
                        "wasted_seconds": 5,
                    })

    return issues


def _check_forbidden_patterns(lines: list[str], rel_path: str, content: str) -> list[dict]:
    """检查禁止模式。"""
    issues = []

    for rule in FORBIDDEN_PATTERNS:
        for i, line in enumerate(lines, 1):
            # Skip comments and "禁止" warnings
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            if any(kw in line for kw in ['禁止', '❌', '不要', 'never', 'don\'t']):
                continue

            if re.search(rule["pattern"], line, re.IGNORECASE):
                issues.append({
                    "category": "T5",
                    "severity": "red",
                    "description": f"文档包含禁止模式: {rule['description']}",
                    "file": rel_path,
                    "line": i,
                    "evidence": line.strip()[:150],
                    "fix": rule["fix"],
                    "wasted_tokens": 3000,
                    "wasted_seconds": 10,
                })

    return issues


def _check_param_warnings(lines: list[str], rel_path: str, content: str) -> list[dict]:
    """检查参数使用警告。"""
    issues = []

    for tool, params in PARAM_WARNINGS.items():
        if tool not in content:
            continue
        for param, info in params.items():
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('//'):
                    continue
                if any(kw in line for kw in ['禁止', '❌', '不支持', '不要', 'never']):
                    continue

                if re.search(r'\b' + re.escape(param) + r'\b', line):
                    issues.append({
                        "category": "T5",
                        "severity": "yellow",
                        "description": f"参数使用警告: {tool}({param}) — {info['reason']}",
                        "file": rel_path,
                        "line": i,
                        "evidence": line.strip()[:150],
                        "fix": info["fix"],
                        "wasted_tokens": 2000,
                        "wasted_seconds": 5,
                    })

    return issues


def audit_bootstrap_coverage(deepflow_root: str | Path | None = None) -> list[dict]:
    """
    检查 Python 文件的 bootstrap 覆盖率。
    如果文件有 `from domains.*` import 但没有 bootstrap，报告为 T5。
    """
    root = Path(deepflow_root) if deepflow_root else Path(__file__).resolve().parent.parent.parent
    issues = []

    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file) or "ARCHIVED" in str(py_file):
            continue
        if "/tests/" in str(py_file):
            continue

        try:
            content = py_file.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        has_domain_import = bool(re.search(r'from\s+domains\.\w+\s+import', content))
        has_bootstrap = ("bootstrap" in content or "_sys.path.insert" in content 
                        or "_p=__import__" in content or "import core.bootstrap" in content)

        if has_domain_import and not has_bootstrap:
            rel_path = str(py_file.relative_to(root)) if py_file.is_relative_to(root) else str(py_file)
            issues.append({
                "category": "T5",
                "severity": "yellow",
                "description": f"Python 文件缺少 bootstrap: {rel_path}",
                "file": rel_path,
                "line": 1,
                "evidence": "有 from domains.* import 但没有 sys.path 引导",
                "fix": "添加 inline bootstrap 或 import core.bootstrap",
                "wasted_tokens": 3500,
                "wasted_seconds": 5,
            })

    return issues
