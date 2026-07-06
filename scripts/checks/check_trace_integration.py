#!/usr/bin/env python3
"""
检查全链路追踪（trace_id）集成状态

验证：
1. core/trace.py 存在且包含必要的函数
2. 三个域（Spec/Solution/Ship Pro）入口文件有 trace 引用
3. trace_id 在 handoff package 中传递

契约笼子检查脚本 — 确保统一 trace_id 接入不被破坏。
"""
import sys
import re
from pathlib import Path

# 自动发现 .deepflow 根目录
DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent
ERRORS = []
PASSES = []


def check(condition: bool, msg: str):
    """记录检查结果"""
    if condition:
        PASSES.append(f"  ✅ {msg}")
    else:
        ERRORS.append(f"  ❌ {msg}")


def check_core_trace_module():
    """检查 core/trace.py 存在且包含必要函数"""
    print("\n[1/4] core/trace.py 模块检查")
    trace_file = DEEPFLOW_ROOT / "core" / "trace.py"
    check(trace_file.exists(), "core/trace.py 文件存在")

    if not trace_file.exists():
        return

    content = trace_file.read_text(encoding="utf-8")

    # 检查必要的函数定义
    required_functions = ["start_trace", "get_trace_id", "span", "end_trace", "save_to_blackboard"]
    for func in required_functions:
        check(
            f"def {func}(" in content,
            f"core/trace.py 包含 def {func}()"
        )

    # 检查 TraceContext 类
    check("class TraceContext" in content, "core/trace.py 包含 TraceContext 类")

    # 检查线程安全（threading.Lock）
    check("threading.Lock" in content, "core/trace.py 使用 threading.Lock（线程安全）")

    # 检查零外部依赖（只用 stdlib）
    imports = re.findall(r'^import\s+(\w+)|^from\s+(\w+)', content, re.MULTILINE)
    stdlib_modules = {"uuid", "time", "json", "threading", "pathlib", "typing"}
    external_imports = set()
    for match in imports:
        mod = match[0] or match[1]
        if mod and mod not in stdlib_modules and mod != "core":
            external_imports.add(mod)
    check(
        len(external_imports) == 0,
        f"core/trace.py 零外部依赖（发现: {external_imports or '无'}）"
    )


def check_spec_pro_integration():
    """检查 Spec Pro 集成"""
    print("\n[2/4] Spec Pro 集成检查")
    coordinator = DEEPFLOW_ROOT / "domains" / "spec_pro" / "coordinator.py"
    check(coordinator.exists(), "domains/spec_pro/coordinator.py 存在")

    if not coordinator.exists():
        return

    content = coordinator.read_text(encoding="utf-8")
    check(
        "from core.trace import" in content,
        "coordinator.py 有 from core.trace import 引用"
    )
    check(
        "start_trace" in content,
        "coordinator.py 调用 start_trace()"
    )
    check(
        'domain="spec_pro"' in content or "domain='spec_pro'" in content,
        "coordinator.py 记录 spec_pro domain span"
    )
    check(
        "trace_id" in content,
        "coordinator.py 包含 trace_id（传递给 handoff package）"
    )


def check_ship_pro_integration():
    """检查 Ship Pro 集成"""
    print("\n[3/4] Ship Pro 集成检查")
    ship_init = DEEPFLOW_ROOT / "domains" / "ship_pro" / "__init__.py"
    check(ship_init.exists(), "domains/ship_pro/__init__.py 存在")

    if not ship_init.exists():
        return

    content = ship_init.read_text(encoding="utf-8")
    check(
        "from core.trace import" in content,
        "__init__.py 有 from core.trace import 引用"
    )
    check(
        "start_trace" in content,
        "__init__.py 调用 start_trace()"
    )
    check(
        'domain="ship_pro"' in content or "domain='ship_pro'" in content,
        "__init__.py 记录 ship_pro domain span"
    )
    check(
        "trace_id" in content,
        "__init__.py 包含 trace_id（接受或传递）"
    )


def check_solution_pro_integration():
    """检查 Solution Pro 集成"""
    print("\n[4/4] Solution Pro 集成检查")
    master = DEEPFLOW_ROOT / "domains" / "solution_pro" / "master_orchestrator.py"
    check(master.exists(), "domains/solution_pro/master_orchestrator.py 存在")

    if not master.exists():
        return

    content = master.read_text(encoding="utf-8")
    check(
        "from core.trace import" in content,
        "master_orchestrator.py 有 from core.trace import 引用"
    )
    check(
        'domain="solution_pro"' in content or "domain='solution_pro'" in content,
        "master_orchestrator.py 记录 solution_pro domain span"
    )
    # 检查三个模块都有 span 记录
    for module in ["planning", "research", "summary"]:
        check(
            f'module="{module}"' in content or f"module='{module}'" in content,
            f"master_orchestrator.py 记录 {module} 模块 span"
        )


def main():
    print("=" * 60)
    print("DeepFlow 全链路追踪（trace_id）集成检查")
    print("=" * 60)
    print(f"DeepFlow Root: {DEEPFLOW_ROOT}")

    check_core_trace_module()
    check_spec_pro_integration()
    check_ship_pro_integration()
    check_solution_pro_integration()

    # 汇总
    print("\n" + "=" * 60)
    print(f"结果: {len(PASSES)} 通过, {len(ERRORS)} 失败")
    print("=" * 60)

    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(e)

    if ERRORS:
        print(f"\n❌ 检查失败: {len(ERRORS)} 项需要修复")
        return 1
    else:
        print("\n✅ 全链路追踪集成检查全部通过！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
