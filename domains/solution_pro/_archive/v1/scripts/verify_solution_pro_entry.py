#!/usr/bin/env python3
"""
验证 Solution Pro 唯一入口重构 (V3.3)

验证点:
1. run_solution_pro 函数可导入
2. 函数签名包含 topic，不包含 spawn_fn
3. 不传 topic 时抛出 ValueError
4. 旧类名 SolutionOrchestratorV21 不再暴露
5. 内部类 _SolutionDispatcher 存在（下划线前缀）
6. Dispatcher 只实例化一次
7. 无 EntryHarness 嵌套
8. 无 openclaw import
"""

import os
import ast

DEEPFLOW_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

print("=" * 60)
print("Solution Pro 唯一入口验证 (V3.3)")
print("=" * 60)

# ========== 测试 1: 导入验证 ==========
print("\n[测试 1] 导入验证")
try:
    from domains.solution_pro import run_solution_pro
    print("✅ run_solution_pro 可导入")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

# ========== 测试 2: 函数签名 ==========
print("\n[测试 2] 函数签名（topic 必填，spawn_fn 不存在）")
import inspect
sig = inspect.signature(run_solution_pro)
params = list(sig.parameters.keys())
if "topic" in params and "spawn_fn" not in params:
    print(f"✅ 签名正确: {params}")
else:
    print(f"❌ 签名错误: {params}")
    sys.exit(1)

# ========== 测试 3: topic 必填 ==========
print("\n[测试 3] topic 必填")
try:
    run_solution_pro(topic="")
    print("❌ 应该抛出 ValueError")
    sys.exit(1)
except ValueError as e:
    if "topic" in str(e).lower():
        print(f"✅ 正确抛出: {e}")
    else:
        print(f"❌ 错误消息不对: {e}")
        sys.exit(1)
except Exception as e:
    print(f"❌ 异常类型错误: {type(e).__name__}: {e}")
    sys.exit(1)

# ========== 测试 4: 旧类名不再暴露 ==========
print("\n[测试 4] 旧类名不再暴露")
try:
    from domains.solution_pro import SolutionOrchestratorV21
    print("❌ SolutionOrchestratorV21 仍然暴露")
    sys.exit(1)
except ImportError:
    print("✅ SolutionOrchestratorV21 已移除")

try:
    from domains.solution_pro import SolutionDispatcher
    print("❌ SolutionDispatcher 仍然暴露")
    sys.exit(1)
except ImportError:
    print("✅ SolutionDispatcher 已移除")

# ========== 测试 5: 内部类命名约定 ==========
print("\n[测试 5] 内部类命名约定")
try:
    from domains.solution_pro.orchestrator_agent import _SolutionDispatcher
import core.bootstrap
    print(f"✅ _SolutionDispatcher 存在（内部类）")
except ImportError as e:
    print(f"❌ 内部类导入失败: {e}")
    sys.exit(1)

# ========== 测试 6: Dispatcher 单次实例化 ==========
print("\n[测试 6] Dispatcher 单次实例化")

with open(os.path.join(DEEPFLOW_BASE, "domains/solution_pro/__init__.py"), "r") as f:
    source = f.read()

tree = ast.parse(source)

func_def = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "run_solution_pro":
        func_def = node
        break

if func_def is None:
    print("❌ run_solution_pro 函数未找到")
    sys.exit(1)

dispatcher_calls = 0
for node in ast.walk(func_def):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "_SolutionDispatcher":
            dispatcher_calls += 1

if dispatcher_calls == 1:
    print(f"✅ Dispatcher 只实例化 1 次")
else:
    print(f"❌ Dispatcher 实例化 {dispatcher_calls} 次（应该只有 1 次）")
    sys.exit(1)

# ========== 测试 7: 无 EntryHarness 嵌套 ==========
print("\n[测试 7] 无 EntryHarness 嵌套")
has_entry_harness = "entry_harness" in source
if not has_entry_harness:
    print("✅ __init__.py 不引用 EntryHarness")
else:
    print("❌ __init__.py 仍引用 EntryHarness")
    sys.exit(1)

# ========== 测试 8: 无 openclaw import ==========
print("\n[测试 8] 无 openclaw import")
# 只检测真正的 import 语句，排除字符串和注释
has_openclaw_import = False
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            if 'openclaw' in alias.name:
                has_openclaw_import = True
                break
    elif isinstance(node, ast.ImportFrom):
        if node.module and 'openclaw' in node.module:
            has_openclaw_import = True
            break

if not has_openclaw_import:
    print("✅ __init__.py 不 import openclaw")
else:
    print("❌ __init__.py 仍 import openclaw（exec 里会报错）")
    sys.exit(1)

# ========== 测试 9: 返回值结构 ==========
print("\n[测试 9] 返回值结构（检查代码逻辑）")
# 检查 return 语句包含 session_id, base_path, plan_path
return_keys = []
for node in ast.walk(func_def):
    if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
        for key in node.value.keys:
            if isinstance(key, ast.Constant):
                return_keys.append(key.value)

expected_keys = {"session_id", "base_path", "plan_path"}
if expected_keys.issubset(set(return_keys)):
    print(f"✅ 返回值包含: {return_keys}")
else:
    print(f"❌ 返回值缺少: {expected_keys - set(return_keys)}")
    sys.exit(1)

# ========== 汇总 ==========
print("\n" + "=" * 60)
print("✅ 全部 9 项验证通过")
print("=" * 60)
print("\n重构成果 (V3.3):")
print("  • 唯一入口: run_solution_pro(topic, **kwargs)")
print("  • 不接收 spawn_fn（那是 LLM 工具，不是 Python 函数）")
print("  • 只生成计划，主 Agent 用 sessions_spawn 工具启动 dispatcher")
print("  • Dispatcher 只实例化 1 次")
print("  • 无 EntryHarness 嵌套")
print("  • 无 openclaw import")
print("  • 旧类名已移除")
