#!/usr/bin/env python3
"""
Phase 2 修复验证脚本：架构补齐
验证项：
1. 并行执行框架实现
2. Audit 管线实现
3. Architecture 域补齐
"""

import sys
from pathlib import Path


def check_parallel_framework():
    """验证并行执行框架"""
    print("=" * 50)
    print("【验证 2.1】并行执行框架")
    print("=" * 50)

    engine_path = Path.home() / ".openclaw/workspace/.deepflow/pipeline_engine.py"
    content = engine_path.read_text()

    checks = {
        "_execute_parallel_agents": "_execute_parallel_agents" in content,
        "asyncio.gather": "asyncio.gather" in content,
        "artifacts/": "artifacts/" in content,
        "_aggregate": "_aggregate" in content or "aggregate" in content,
    }

    for name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")

    return all(checks.values())


def check_audit_pipeline():
    """验证 Audit 管线"""
    print("\n" + "=" * 50)
    print("【验证 2.2】Audit 管线实现")
    print("=" * 50)

    engine_path = Path.home() / ".openclaw/workspace/.deepflow/pipeline_engine.py"
    content = engine_path.read_text()

    checks = {
        "_execute_audit_stage": "_execute_audit_stage" in content,
        "_run_single_audit": "_run_single_audit" in content,
        "correctness/security/performance": "correctness" in content and "security" in content,
        "audit_summary.md": "audit_summary.md" in content,
    }

    for name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")

    return all(checks.values())


def check_architecture_domain():
    """验证 Architecture 域补齐"""
    print("\n" + "=" * 50)
    print("【验证 2.3】Architecture 域 Prompt")
    print("=" * 50)

    prompts_dir = Path.home() / ".openclaw/workspace/.deepflow/prompts"

    required = [
        "architecture_researcher.md",
        "architecture_auditor.md",
        "architecture_fixer.md",
    ]

    all_passed = True
    for name in required:
        path = prompts_dir / name
        exists = path.exists()
        has_blackboard = False
        if exists:
            content = path.read_text()
            has_blackboard = "Blackboard" in content or "blackboard" in content

        status = "✅" if exists and has_blackboard else "❌"
        print(f"  {status} {name}")
        if exists and not has_blackboard:
            print(f"      ⚠️  缺少 Blackboard 指令")
        all_passed = all_passed and exists and has_blackboard

    return all_passed


def main():
    print("=" * 50)
    print("Phase 2 修复验证: 架构补齐")
    print("=" * 50)

    results = {
        "parallel_framework": check_parallel_framework(),
        "audit_pipeline": check_audit_pipeline(),
        "architecture_domain": check_architecture_domain(),
    }

    print("\n" + "=" * 50)
    print("验证结果汇总")
    print("=" * 50)

    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(results.values())
    print()
    if all_passed:
        print("🎉 Phase 2 修复验证全部通过！")
        return 0
    else:
        print("⚠️  部分验证未通过，需要继续修复")
        return 1


if __name__ == "__main__":
    sys.exit(main())
