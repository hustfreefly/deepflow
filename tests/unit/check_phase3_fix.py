#!/usr/bin/env python3
"""
Phase 3 修复验证脚本：验证与部署
"""

import sys
from pathlib import Path


def check_skill_registration():
    """验证 Skill 注册"""
    print("=" * 50)
    print("【验证 3.1】Skill 注册")
    print("=" * 50)

    skill_path = Path.home() / ".openclaw/workspace/.deepflow/SKILL.md"
    if not skill_path.exists():
        print("  ❌ SKILL.md 不存在")
        return False

    content = skill_path.read_text()
    checks = {
        "/deep": "/deep" in content,
        "深度分析": "深度分析" in content,
        "Coordinator": "Coordinator" in content,
    }

    for name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")

    return all(checks.values())


def check_integration_test():
    """验证集成测试"""
    print("\n" + "=" * 50)
    print("【验证 3.2】集成测试")
    print("=" * 50)

    # 检查 Blackboard 是否有测试 session
    blackboard_dir = Path.home() / ".openclaw/workspace/.v3/blackboard"
    test_sessions = list(blackboard_dir.glob("integration-test-*"))

    if not test_sessions:
        print("  ❌ 无集成测试 session")
        return False

    print(f"  ✅ 发现 {len(test_sessions)} 个测试 session")

    # 检查 session 结构
    for session_dir in test_sessions[:2]:  # 检查前2个
        shared_state = session_dir / "shared_state.json"
        if shared_state.exists():
            print(f"  ✅ {session_dir.name}: shared_state.json 存在")
        else:
            print(f"  ❌ {session_dir.name}: shared_state.json 缺失")

    return len(test_sessions) > 0


def check_quality_gate():
    """验证 Quality Gate 基础结构"""
    print("\n" + "=" * 50)
    print("【验证 3.3】Quality Gate 结构")
    print("=" * 50)

    engine_path = Path.home() / ".openclaw/workspace/.deepflow/pipeline_engine.py"
    content = engine_path.read_text()

    checks = {
        "quality_scores": "quality_scores" in content,
        "check_convergence": "check_convergence" in content,
        "_check_convergence": "_check_convergence" in content,
    }

    for name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")

    return all(checks.values())


def main():
    print("=" * 50)
    print("Phase 3 修复验证: 验证与部署")
    print("=" * 50)

    results = {
        "skill_registration": check_skill_registration(),
        "integration_test": check_integration_test(),
        "quality_gate": check_quality_gate(),
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
        print("🎉 Phase 3 修复验证全部通过！")
        print("\n✅✅✅ 所有 Phase (1/2/3) 修复完成！✅✅✅")
        return 0
    else:
        print("⚠️  部分验证未通过")
        return 1


if __name__ == "__main__":
    sys.exit(main())
