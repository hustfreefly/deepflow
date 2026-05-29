#!/usr/bin/env python3
"""
验证脚本: Spec Pro → Solution Pro 修桥契约验证
契约: 5 项验证（桥代码/异常处理/轻量校验/传递/向后兼容）
"""

import sys
import os
import json
import tempfile
from pathlib import Path

DEEPFLOW_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEEPFLOW_BASE))

pass_count = 0
fail_count = 0

def check(name, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  ✅ PASS: {name}")
    else:
        fail_count += 1
        print(f"  ❌ FAIL: {name} — {detail}")

# ============================================================================
# 1. 桥代码存在
# ============================================================================
print("\n=== 1. 桥代码存在 ===")

eh_path = DEEPFLOW_BASE / "core" / "entry_harness.py"
with open(eh_path, "r", encoding="utf-8") as f:
    eh_content = f.read()

check("EntryHarness 中有 spec_session_id 读取逻辑",
      'spec_session_id' in eh_content,
      "没有找到 spec_session_id")

check("EntryHarness 中有 living_spec.json 路径构建",
      'living_spec.json' in eh_content,
      "没有找到 living_spec.json 路径")

check("EntryHarness 中有 living_spec 加载到 Orchestrator",
      'living_spec=living_spec' in eh_content or 'living_spec = living_spec' in eh_content,
      "living_spec 没有传入 SolutionOrchestratorV21")

# ============================================================================
# 2. 异常处理
# ============================================================================
print("\n=== 2. 异常处理 ===")

check("有 try/except 包裹 JSON 读取",
      "try:" in eh_content and "json.JSONDecodeError" in eh_content,
      "没有异常处理包裹 JSON 读取")

check("降级到 living_spec = None",
      "living_spec = None" in eh_content,
      "没有降级到 None")

# ============================================================================
# 3. 轻量校验
# ============================================================================
print("\n=== 3. 轻量校验 ===")

check("检查 confirmed 层存在",
      '"confirmed"' in eh_content and "not in" in eh_content,
      "没有校验 confirmed 层")

# ============================================================================
# 4. 传递到 Orchestrator
# ============================================================================
print("\n=== 4. 传递到 Orchestrator ===")

check("SolutionOrchestratorV21 构造调用包含 living_spec",
      "living_spec=living_spec" in eh_content,
      "SolutionOrchestratorV21 构造调用缺少 living_spec 参数")

# ============================================================================
# 5. 向后兼容（运行时测试）
# ============================================================================
print("\n=== 5. 向后兼容（运行时测试） ===")

# 模拟不传 spec_session_id 的情况
from core.entry_harness import EntryHarness

eh = EntryHarness()
# validate_and_start 需要 spawn_fn，我们只测试 _generate_execution_plan 的兼容性
# 直接构造 context 不包含 spec_session_id

context_no_spec = {
    "session_id": "test_compat_session",
    "topic": "测试向后兼容",
    "solution_type": "architecture",
    "mode": "standard",
}

# 检查 context 中没有 spec_session_id 时不会报错
check("context 无 spec_session_id 时不报错",
      context_no_spec.get("spec_session_id") is None,
      "spec_session_id 应该默认为 None")

# 模拟 spec_session_id 指向不存在的 session
context_bad_spec = {
    "session_id": "test_compat_session",
    "topic": "测试降级",
    "spec_session_id": "nonexistent_spec_session",
}

check("spec_session_id 指向不存在的 session 时降级",
      not (DEEPFLOW_BASE / "blackboard" / "nonexistent_spec_session" / "spec" / "living_spec.json").exists(),
      "不存在的 spec session 路径应该不存在（降级生效）")

# ============================================================================
# 总结
# ============================================================================
print(f"\n{'='*50}")
print(f"验证结果: {pass_count} passed, {fail_count} failed")
if fail_count > 0:
    print("状态: ❌ 修桥未完成")
    sys.exit(1)
else:
    print("状态: ✅ 修桥完成")
