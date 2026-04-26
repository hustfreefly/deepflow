#!/usr/bin/env python3
"""
IO Write Fix 验证脚本（方案A）
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

print("\n[IO Write Fix 验证 - 方案A]")

from domains.solution import task_builder

# 1. Data Collection
task = task_builder.build_data_collection_task("test_session", "测试主题", ["约束1"])
check("Data Collection: 包含 write 工具要求", "write" in task.lower() or "写入" in task, "未要求 write")

# 2. Planner
task = task_builder.build_planner_task("test_session", "测试主题", "architecture", ["约束1"], ["干系人1"])
check("Planner: 包含 write 工具要求", "write" in task.lower() or "写入" in task, "未要求 write")

# 3. Researcher
task = task_builder.build_researcher_task(
    "测试专家", "test_session", "测试主题",
    {"type": "architecture"},
    expert_id="expert_1", angle="测试角度", reason="测试原因"
)
check("Researcher: 包含 write 工具要求", "write" in task.lower(), "未要求 write")

# 4. Designer
task = task_builder.build_designer_task("test_session", "测试主题", {"type": "architecture"})
check("Designer: 包含 write 工具要求", "write" in task.lower(), "未要求 write")

# 5. Auditor
task = task_builder.build_auditor_task("test_session", "测试主题", {"type": "architecture"})
check("Auditor: 包含 write 工具要求", "write" in task.lower(), "未要求 write")

# 6. Fixer
task = task_builder.build_fixer_task_with_audit("test_session", "测试主题", "/path/to/audit.json")
check("Fixer: 包含 write 工具要求", "write" in task.lower(), "未要求 write")

# 7. Deliver
task = task_builder.build_deliver_task("test_session", "测试主题", {"type": "architecture"})
check("Deliver: 包含 write 工具要求", "write" in task.lower(), "未要求 write")

print(f"\n结果: {passed}/{passed+failed} 通过")
sys.exit(0 if failed == 0 else 1)
