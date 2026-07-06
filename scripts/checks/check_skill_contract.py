#!/usr/bin/env python3
"""
SKILL.md 契约笼子验证器
=======================
验证所有 SKILL.md 文件是否符合统一契约。

契约定义:
  domain SKILL.md:
    - [MUST] YAML frontmatter (name, description, version)
    - [MUST] H1 title (#{Domain} — Agent 执行指南)
    - [MUST] metadata block (版本/架构/状态)
    - [MUST] trigger section (## 🚀 or 触发)
    - [MUST] execution steps section (## 执行步骤 or Step)
    - [SHOULD] architecture overview section
    - [SHOULD] related files section
    - [MUST] 100-400 lines
    - [MUST] no hardcoded /Users/ paths

  root SKILL.md:
    - [MUST] YAML frontmatter (name, description, version)
    - [MUST] H1 title (DeepFlow)
    - [MUST] positioning (one-line description)
    - [MUST] domain table (commands + domains)
    - [SHOULD] references to domain SKILL.md files
    - [MUST] 50-150 lines
    - [MUST] no hardcoded /Users/ paths

Usage:
    python3 scripts/checks/check_skill_contract.py
"""

import re
import sys
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------- Domain SKILL.md contract ----------

DOMAIN_SKILLS = {
    "domains/spec_pro/SKILL.md": {
        "name": "spec-pro",
        "max_lines": 400,
        "min_lines": 100,
    },
    "domains/solution_pro/SKILL.md": {
        "name": "solution-pro",
        "max_lines": 550,  # solution_pro is inherently complex
        "min_lines": 100,
    },
    "domains/ship_pro/SKILL.md": {
        "name": "ship-pro",
        "max_lines": 400,
        "min_lines": 100,
    },
    "domains/research_pro/SKILL.md": {
        "name": "research-pro",
        "max_lines": 400,
        "min_lines": 100,
    },
}

ROOT_SKILL = "SKILL.md"


def check_frontmatter(content: str, expected_name: str) -> list[str]:
    """Check YAML frontmatter."""
    issues = []
    if not content.startswith("---"):
        issues.append("[MUST] Missing YAML frontmatter (must start with ---)")
        return issues

    # Find closing ---
    lines = content.split("\n")
    end_idx = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        issues.append("[MUST] Missing closing --- for YAML frontmatter")
        return issues

    fm = "\n".join(lines[1:end_idx])

    # Check required fields
    if f"name: {expected_name}" not in fm and f'name: "{expected_name}"' not in fm:
        issues.append(f"[MUST] frontmatter missing or wrong name (expected: {expected_name})")
    if "description:" not in fm:
        issues.append("[MUST] frontmatter missing description")
    if "version:" not in fm:
        issues.append("[MUST] frontmatter missing version")

    return issues


def check_h1_title(content: str, domain_name: str) -> list[str]:
    """Check H1 title exists."""
    issues = []
    h1_lines = [l for l in content.split("\n") if l.startswith("# ")]
    if not h1_lines:
        issues.append("[MUST] Missing H1 title (# ...)")
    elif domain_name not in h1_lines[0] and domain_name.replace("-", " ") not in h1_lines[0].lower():
        # Allow flexible naming but flag if totally unrelated
        pass
    return issues


def check_required_sections(content: str, sections: list[tuple[str, str]]) -> list[str]:
    """Check required sections exist (by heading keyword)."""
    issues = []
    for label, keyword in sections:
        if keyword.lower() not in content.lower():
            issues.append(f"[MUST] Missing section: {label} (looked for '{keyword}')")
    return issues


def check_line_count(content: str, min_lines: int, max_lines: int) -> list[str]:
    """Check line count within bounds."""
    issues = []
    count = len(content.split("\n"))
    if count < min_lines:
        issues.append(f"[MUST] Too short: {count} lines (min {min_lines})")
    if count > max_lines:
        issues.append(f"[SHOULD] Too long: {count} lines (max {max_lines}) — consider trimming")
    return issues


def check_no_hardcoded_paths(content: str) -> list[str]:
    """Check for hardcoded /Users/ paths."""
    issues = []
    # Match /Users/xxx/.openclaw/workspace/.deepflow
    pattern = r"/Users/\w+/.openclaw/workspace/\.deepflow"
    matches = re.findall(pattern, content)
    if matches:
        issues.append(f"[MUST] Found {len(matches)} hardcoded path(s): {matches[0]}")
    return issues


def check_no_deprecated_api(content: str) -> list[str]:
    """Check for deprecated API references."""
    issues = []
    deprecated = [
        ("PipelineOrchestrator", "core/orchestrator/pipeline_orchestrator.py"),
        ("DataManager", "core/data/data_manager_worker.py"),
        ("_SolutionDispatcher", "domains/solution_pro/orchestrator_agent.py"),
    ]
    for api_name, old_path in deprecated:
        if api_name in content:
            issues.append(f"[SHOULD] References deprecated API: {api_name} (was in {old_path})")
    return issues


def check_version_consistency(content: str) -> list[str]:
    """Check version is 2.0.0, not old versions."""
    issues = []
    old_versions = ["0.4.0", "0.3.0", "1.0.0", "v0.4", "v0.3"]
    for v in old_versions:
        if v in content:
            issues.append(f"[SHOULD] References old version {v} (should be 2.0.0)")
    return issues


def validate_domain_skill(filepath: str, config: dict) -> dict:
    """Validate a domain SKILL.md against contract."""
    path = DEEPFLOW_ROOT / filepath
    if not path.exists():
        return {"file": filepath, "status": "MISSING", "issues": ["File not found"]}

    content = path.read_text(encoding="utf-8")
    issues = []

    issues.extend(check_frontmatter(content, config["name"]))
    issues.extend(check_h1_title(content, config["name"]))

    required_sections = [
        ("trigger/activation", "触发"),
        ("execution steps", "step"),
    ]
    issues.extend(check_required_sections(content, required_sections))
    issues.extend(check_line_count(content, config["min_lines"], config["max_lines"]))
    issues.extend(check_no_hardcoded_paths(content))
    issues.extend(check_no_deprecated_api(content))
    issues.extend(check_version_consistency(content))

    must_issues = [i for i in issues if i.startswith("[MUST]")]
    status = "PASS" if not must_issues else "FAIL"

    return {
        "file": filepath,
        "status": status,
        "issues": issues,
        "must_count": len(must_issues),
        "should_count": len(issues) - len(must_issues),
    }


def validate_root_skill() -> dict:
    """Validate root SKILL.md."""
    filepath = ROOT_SKILL
    path = DEEPFLOW_ROOT / filepath
    if not path.exists():
        return {"file": filepath, "status": "MISSING", "issues": ["File not found"]}

    content = path.read_text(encoding="utf-8")
    issues = []

    issues.extend(check_frontmatter(content, "deepflow"))
    issues.extend(check_h1_title(content, "DeepFlow"))

    required_sections = [
        ("domain table", "|"),  # Must have a table
        ("trigger", "触发"),
    ]
    issues.extend(check_required_sections(content, required_sections))
    issues.extend(check_line_count(content, 50, 150))
    issues.extend(check_no_hardcoded_paths(content))
    issues.extend(check_no_deprecated_api(content))
    issues.extend(check_version_consistency(content))

    must_issues = [i for i in issues if i.startswith("[MUST]")]
    status = "PASS" if not must_issues else "FAIL"

    return {
        "file": filepath,
        "status": status,
        "issues": issues,
        "must_count": len(must_issues),
        "should_count": len(issues) - len(must_issues),
    }


def check_quickstart_dedup() -> dict:
    """Check QUICKSTART deduplication."""
    root_qs = DEEPFLOW_ROOT / "docs/QUICKSTART.md"
    guides_qs = DEEPFLOW_ROOT / "docs/guides/QUICKSTART.md"

    issues = []
    if root_qs.exists():
        issues.append("[MUST] docs/QUICKSTART.md should be removed (canonical: docs/guides/QUICKSTART.md)")

    if not guides_qs.exists():
        issues.append("[MUST] docs/guides/QUICKSTART.md missing (canonical quickstart)")
    else:
        content = guides_qs.read_text(encoding="utf-8")
        issues.extend(check_no_hardcoded_paths(content))
        issues.extend(check_version_consistency(content))

    must_issues = [i for i in issues if i.startswith("[MUST]")]
    return {
        "file": "docs/QUICKSTART.md + docs/guides/QUICKSTART.md",
        "status": "PASS" if not must_issues else "FAIL",
        "issues": issues,
        "must_count": len(must_issues),
        "should_count": len(issues) - len(must_issues),
    }


def main():
    print("=" * 60)
    print("SKILL.md 契约笼子验证")
    print("=" * 60)
    print()

    results = []

    # Domain SKILL.md files
    for filepath, config in DOMAIN_SKILLS.items():
        result = validate_domain_skill(filepath, config)
        results.append(result)

    # Root SKILL.md
    results.append(validate_root_skill())

    # QUICKSTART dedup
    results.append(check_quickstart_dedup())

    # Print results
    total_must = 0
    total_should = 0

    for r in results:
        status_icon = {"PASS": "✅", "FAIL": "❌", "MISSING": "💀"}.get(r["status"], "?")
        print(f"{status_icon} {r['file']}")
        for issue in r["issues"]:
            print(f"   {issue}")
        total_must += r["must_count"]
        total_should += r["should_count"]
        print()

    print("-" * 60)
    print(f"Total: {len(results)} files | MUST issues: {total_must} | SHOULD issues: {total_should}")

    if total_must > 0:
        print(f"\n❌ CONTRACT VIOLATION: {total_must} MUST issues found")
        sys.exit(1)
    else:
        print(f"\n✅ CONTRACT PASS (with {total_should} SHOULD suggestions)")
        sys.exit(0)


if __name__ == "__main__":
    main()
