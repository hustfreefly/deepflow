#!/usr/bin/env python3
"""
验证脚本: Solution Pro P0/P1 修复闭环验证
契约: Codex 诊断报告修复清单

验证项:
- P0-1: PipelineOrchestrator 等待的文件路径必须匹配 task_builder 要求写入的路径
- P0-2: _is_valid_worker_output 必须识别标准输出格式
- P0-3: EntryHarness 的 session_id 不能分裂
- P1: 文档和代码模式一致
"""

import sys
import os
import json
import re
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
# P0-1: 输出文件名一致性
# ============================================================================
print("\n=== P0-1: 输出文件名一致性 ===")

orch_path = DEEPFLOW_BASE / "core" / "pipeline_orchestrator.py"
with open(orch_path, "r", encoding="utf-8") as f:
    orch_content = f.read()

# 检查是否使用了 resolve_worker_output_path 映射函数
check("PipelineOrchestrator 有 resolve_worker_output_path 映射",
      "resolve_worker_output_path" in orch_content or "WORKER_OUTPUT_PATH_MAP" in orch_content,
      "没有找到输出路径映射函数")

# 检查 _wait_for_worker 是否使用动态路径
wait_func = orch_content.split("def _wait_for_worker")[1].split("def ")[0] if "def _wait_for_worker" in orch_content else ""
check("_wait_for_worker 使用 resolve_worker_output_path",
      "resolve_worker_output_path" in wait_func,
      "_wait_for_worker 没有使用 resolve_worker_output_path")

# 检查 _build_default_task 是否使用正确的路径
default_task = orch_content.split("def _build_default_task")[1].split("def ")[0] if "def _build_default_task" in orch_content else ""
check("_build_default_task 使用 resolve_worker_output_path",
      "resolve_worker_output_path" in default_task,
      "_build_default_task 没有使用 resolve_worker_output_path")

# ============================================================================
# P0-2: 有效输出判断
# ============================================================================
print("\n=== P0-2: 有效输出判断 ===")

is_valid_section = orch_content.split("def _is_valid_worker_output")[1].split("def ")[0] if "def _is_valid_worker_output" in orch_content else ""

check("识别标准格式 status/stage/data",
      '"status"' in is_valid_section and '"stage"' in is_valid_section,
      "没有识别 {status, stage, data} 标准格式")

check("识别 content_keys 中的字段",
      '"analysis"' in is_valid_section or '"key_findings"' in is_valid_section,
      "没有保留原有 content_keys 识别")

# ============================================================================
# P0-3: session_id 一致性
# ============================================================================
print("\n=== P0-3: session_id 一致性 ===")

entry_harness_path = DEEPFLOW_BASE / "core" / "entry_harness.py"
with open(entry_harness_path, "r", encoding="utf-8") as f:
    eh_content = f.read()

# 检查 _generate_execution_plan 是否复用 session_id
gen_plan_section = eh_content.split("def _generate_execution_plan")[1].split("\n    def ")[0] if "def _generate_execution_plan" in eh_content else ""

check("_generate_execution_plan 复用 context['session_id']",
      'context.get("session_id")' in gen_plan_section or "context['session_id']" in gen_plan_section,
      "没有复用已有的 session_id")

check("_generate_execution_plan 设置 orch.session_id 而非重新 init",
      "orch.session_id = session_id" in gen_plan_section,
      "没有手动设置已有的 session_id")

# ============================================================================
# P1: 文档同步
# ============================================================================
print("\n=== P1: 文档同步 ===")

doc_path = DEEPFLOW_BASE / "docs" / "SOLUTION_MODULE_DESIGN.md"
if doc_path.exists():
    with open(doc_path, "r", encoding="utf-8") as f:
        doc_content = f.read()
    has_quick = "quick" in doc_content.lower() and "mode" in doc_content.lower()
    check("文档已移除 quick 模式描述或标注已废弃",
          not has_quick or "deprecated" in doc_content.lower() or "已删除" in doc_content,
          "文档仍然描述 quick 模式但代码已删除")
else:
    print(f"  ⚠️ SKIP: 文档不存在 {doc_path}")

# ============================================================================
# 总结
# ============================================================================
print(f"\n{'='*50}")
print(f"验证结果: {pass_count} passed, {fail_count} failed")
if fail_count > 0:
    print("状态: ❌ 修复未完成")
    sys.exit(1)
else:
    print("状态: ✅ 全部通过")
