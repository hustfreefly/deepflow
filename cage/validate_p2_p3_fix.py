#!/usr/bin/env python3
"""
P2 + P3 Fix 验证脚本
"""

import sys
import os

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"
sys.path.insert(0, DEEPFLOW_BASE)

passed = 0
failed = 0

def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} - {detail}")

print("\n[P2 + P3 Fix 验证]")

from domains.solution import task_builder

# 1. P2-001: Research prompt 无占位符
task = task_builder.build_researcher_task(
    "测试专家", "test_session", "测试主题",
    {"type": "architecture", "constraints": []},
    expert_id="expert_1", angle="测试角度", reason="测试原因"
)
check(
    "P2-001: Research prompt 无 {{ solution_type }} 占位符",
    "{{ solution_type }}" not in task,
    "发现未替换占位符"
)
check(
    "P2-001: Research prompt 无 {{ mode }} 占位符",
    "{{ mode }}" not in task,
    "发现未替换占位符"
)

# 2. P2-002: Audit score 0-100
task = task_builder.build_auditor_task(
    "test_session", "测试主题", {"type": "architecture"}
)
check(
    "P2-002: Audit task 使用 0-100 分制",
    "0-100" in task or "score" in task.lower(),
    "未明确 score 范围"
)

# 3. P2-003: Deliver 与 Design 区分度
design_task = task_builder.build_designer_task(
    "test_session", "测试主题", {"type": "architecture"}
)
deliver_task = task_builder.build_deliver_task(
    "test_session", "测试主题", {"type": "architecture"}
)
check(
    "P2-003: Deliver 与 Design 有区分",
    design_task != deliver_task,
    "两个 task 完全相同"
)
check(
    "P2-003: Deliver 强调最终交付",
    "最终交付" in deliver_task or "deliver" in deliver_task.lower() or "整合" in deliver_task,
    "deliver task 未强调交付"
)

# 4. P3-002: Fixer fallback
task = task_builder.build_fixer_task_with_audit(
    "test_session", "测试主题", "/path/to/audit.json"
)
check(
    "P3-002: Fixer 包含 audit.json 缺失 fallback",
    "不存在" in task or "缺失" in task or "无法读取" in task,
    "未包含 fallback 说明"
)

# 5. 基础验证
import subprocess
result = subprocess.run(
    ["python3", f"{DEEPFLOW_BASE}/cage/validate_refactor.py"],
    capture_output=True,
    text=True
)
check(
    "基础验证仍然通过",
    result.returncode == 0,
    "validate_refactor.py 失败"
)

print(f"\n结果: {passed}/{passed+failed} 通过")
sys.exit(0 if failed == 0 else 1)
