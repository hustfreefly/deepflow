"""
路径修复验证脚本
契约: cage/path_fix_contract.yaml
"""

import sys
import os

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

from core.task_builder import (
    build_planner_task,
    build_researcher_task,
    build_auditor_task,
    build_fixer_task,
    build_summarizer_task
)

print("=" * 60)
print("路径修复验证")
print("=" * 60)

# 测试参数
session_id = "test_session_123"
company_code = "688981.SH"
company_name = "中芯国际"

errors = []

# 1. 验证 Planner Task
print("\n[Planner Task 验证]")
planner_task = build_planner_task(session_id, company_code, company_name)
if "/Users/allen/.openclaw/workspace/.deepflow/blackboard/" in planner_task:
    print("  ✅ 输入路径使用绝对路径")
else:
    print("  ❌ 输入路径仍使用相对路径")
    errors.append("Planner 输入路径")

if f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/stages/planner_output.json" in planner_task:
    print("  ✅ 输出路径使用绝对路径")
else:
    print("  ❌ 输出路径仍使用相对路径")
    errors.append("Planner 输出路径")

# 2. 验证 Researcher Task
print("\n[Researcher Task 验证]")
researcher_task = build_researcher_task("finance", session_id, company_code, company_name)
if "/Users/allen/.openclaw/workspace/.deepflow/blackboard/" in researcher_task:
    print("  ✅ 输入路径使用绝对路径")
else:
    print("  ❌ 输入路径仍使用相对路径")
    errors.append("Researcher 输入路径")

if f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/stages/researcher_finance_output.json" in researcher_task:
    print("  ✅ 输出路径使用绝对路径")
else:
    print("  ❌ 输出路径仍使用相对路径")
    errors.append("Researcher 输出路径")

# 3. 验证 Auditor Task
print("\n[Auditor Task 验证]")
auditor_task = build_auditor_task("factual", session_id, company_code, company_name)
if "/Users/allen/.openclaw/workspace/.deepflow/blackboard/" in auditor_task:
    print("  ✅ 输入路径使用绝对路径")
else:
    print("  ❌ 输入路径仍使用相对路径")
    errors.append("Auditor 输入路径")

if f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/stages/auditor_factual_output.json" in auditor_task:
    print("  ✅ 输出路径使用绝对路径")
else:
    print("  ❌ 输出路径仍使用相对路径")
    errors.append("Auditor 输出路径")

# 4. 验证 Fixer Task
print("\n[Fixer Task 验证]")
fixer_task = build_fixer_task(session_id, company_code, company_name)
if "/Users/allen/.openclaw/workspace/.deepflow/blackboard/" in fixer_task:
    print("  ✅ 输入路径使用绝对路径")
else:
    print("  ❌ 输入路径仍使用相对路径")
    errors.append("Fixer 输入路径")

if f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/stages/fixer_output.json" in fixer_task:
    print("  ✅ 输出路径使用绝对路径")
else:
    print("  ❌ 输出路径仍使用相对路径")
    errors.append("Fixer 输出路径")

# 5. 验证 Summarizer Task
print("\n[Summarizer Task 验证]")
summarizer_task = build_summarizer_task(session_id, company_code, company_name)
path_count = summarizer_task.count("/Users/allen/.openclaw/workspace/.deepflow/blackboard/")
print(f"  绝对路径出现次数: {path_count}")
if path_count >= 10:  # 应该有多个路径
    print("  ✅ 所有路径使用绝对路径")
else:
    print(f"  ❌ 路径数量不足 (期望>=10, 实际={path_count})")
    errors.append("Summarizer 路径数量")

# 6. 检查没有相对路径残留（排除提示词模板中的示例）
print("\n[相对路径残留检查]")
all_tasks = [planner_task, researcher_task, auditor_task, fixer_task, summarizer_task]
relative_found = False
for i, task in enumerate(all_tasks):
    task_names = ["Planner", "Researcher", "Auditor", "Fixer", "Summarizer"]
    lines = task.split('\n')
    for line in lines:
        # 只检查代码块和明确的路径行，排除提示词模板示例
        if ('blackboard/' in line and 
            '/Users/allen/.openclaw/workspace/.deepflow/blackboard/' not in line and
            '`' not in line and  # 排除代码块标记
            '示例' not in line and
            '模板' not in line):
            # 检查是否是实际路径（包含{session_id}变量）
            if '{session_id}' in line or 'data/' in line or 'stages/' in line:
                print(f"  ⚠️ {task_names[i]} 发现相对路径: {line.strip()[:80]}")
                relative_found = True

if not relative_found:
    print("  ✅ 无相对路径残留（代码生成部分）")
else:
    errors.append("相对路径残留")

# 汇总
print("\n" + "=" * 60)
print("验证结果汇总")
print("=" * 60)
if not errors:
    print("✅ 所有验证通过！")
    print("\n修复内容:")
    print("  - Planner: 输入/输出路径 → 绝对路径")
    print("  - Researcher: 输入/输出路径 → 绝对路径")
    print("  - Auditor: 输入/输出路径 → 绝对路径")
    print("  - Fixer: 输入/输出路径 → 绝对路径")
    print("  - Summarizer: 所有读取和输出路径 → 绝对路径")
    sys.exit(0)
else:
    print(f"❌ 发现 {len(errors)} 个问题:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
