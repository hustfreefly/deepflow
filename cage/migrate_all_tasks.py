#!/usr/bin/env python3
"""
批量迁移所有 task 到中心化写入模式
"""

import re

input_file = "/Users/allen/.openclaw/workspace/.deepflow/domains/solution/task_builder.py"
output_file = "/Users/allen/.openclaw/workspace/.deepflow/domains/solution/task_builder.py"

with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 定义迁移模式
migrations = [
    # data_collection
    {
        "old": """## 执行要求（必须遵守）
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`{_DEEPFLOW_BASE}/blackboard/{session_id}/data/research_data.json`
   - 格式：JSON
2. 写入后必须使用 `read` 工具验证文件存在
3. 在最终回复中确认：✅ 文件已成功写入 {_DEEPFLOW_BASE}/blackboard/{session_id}/data/research_data.json

## 失败处理
- 如果 write 工具报错，立即报告错误，不要返回虚假成功
- 如果文件写入后 read 验证失败，重试最多 3 次""",
        "new": """## 输出要求（中心化写入模式）
1. **不要直接写入文件**，将采集结果以 JSON 格式返回
2. 返回格式：
   ```json
   {
     "status": "completed",
     "stage": "data_collection",
     "data": {
       "tech_docs": [...],
       "industry_reports": [...],
       "competitor_analysis": [...],
       "risks": [...]
     }
   }
   ```
3. 确保返回的 JSON 完整且可解析
4. 在最终回复中确认：✅ 数据采集结果已生成"""
    },
    # research
    {
        "old": """## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/research_{expert_id}.json`
   - 格式：JSON
2. 写入后必须使用 `read` 工具验证文件存在
3. 在最终回复中确认：✅ 文件已成功写入 {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/research_{expert_id}.json

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次""",
        "new": """## 输出要求（中心化写入模式）
1. **不要直接写入文件**，将研究结果以 JSON 格式返回
2. 返回格式：
   ```json
   {
     "status": "completed",
     "stage": "research",
     "data": {
       "expert_id": "{expert_id}",
       "angle": "...",
       "findings": {...},
       "conclusions": [...]
     }
   }
   ```
3. 确保返回的 JSON 完整且可解析
4. 在最终回复中确认：✅ 研究结果已生成"""
    },
    # design
    {
        "old": """## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/design.md`
   - 格式：Markdown
2. 写入后必须使用 `read` 工具验证文件存在
3. 在最终回复中确认：✅ 文件已成功写入 {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/design.md

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次""",
        "new": """## 输出要求（中心化写入模式）
1. **不要直接写入文件**，将设计方案以 JSON 格式返回
2. 返回格式：
   ```json
   {
     "status": "completed",
     "stage": "design",
     "data": {
       "architecture": "...",
       "components": [...],
       "interfaces": [...],
       "data_model": {...}
     }
   }
   ```
3. 确保返回的 JSON 完整且可解析
4. 在最终回复中确认：✅ 设计方案已生成"""
    },
    # audit
    {
        "old": """## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/audit.json`
   - 格式：JSON
2. 包含: issues（P0/P1/P2分级）, score（0-100分）, recommendations
3. 检查: 完整性、可行性、一致性、创新性
4. 评分标准:
   - 基础分: 100分
   - 每个 P0 问题: -30分
   - 每个 P1 问题: -15分
   - 每个 P2 问题: -5分
   - 最低分: 0分
5. 写入后必须使用 `read` 工具验证文件存在
6. 在最终回复中确认：✅ 文件已成功写入 {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/audit.json

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次""",
        "new": """## 输出要求（中心化写入模式）
1. **不要直接写入文件**，将审计结果以 JSON 格式返回
2. 返回格式：
   ```json
   {
     "status": "completed",
     "stage": "audit",
     "data": {
       "issues": [{"level": "P0/P1/P2", "description": "..."}],
       "score": 85,
       "recommendations": [...]
     }
   }
   ```
3. 评分标准:
   - 基础分: 100分
   - 每个 P0 问题: -30分
   - 每个 P1 问题: -15分
   - 每个 P2 问题: -5分
   - 最低分: 0分
4. 确保返回的 JSON 完整且可解析
5. 在最终回复中确认：✅ 审计结果已生成"""
    },
    # fix
    {
        "old": """## 输出要求
1. 输出修复方案到 {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/fix.json
2. 包含: fixes（按优先级排序）, verification_plan
3. 确保每个问题都有对应修复""",
        "new": """## 输出要求（中心化写入模式）
1. **不要直接写入文件**，将修复方案以 JSON 格式返回
2. 返回格式：
   ```json
   {
     "status": "completed",
     "stage": "fix",
     "data": {
       "fixes": [{"priority": "P0", "issue": "...", "fix": "..."}],
       "verification_plan": "..."
     }
   }
   ```
3. 确保返回的 JSON 完整且可解析
4. 在最终回复中确认：✅ 修复方案已生成"""
    },
    # deliver
    {
        "old": """## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/deliver.md`
   - 格式：Markdown
2. 包含: executive_summary, solution_overview, technical_spec, implementation_plan, risk_assessment
3. 格式清晰，适合直接交付
4. 整合审计修复结果，标注变更点
5. 写入后必须使用 `read` 工具验证文件存在
6. 在最终回复中确认：✅ 文件已成功写入 {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/deliver.md

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次""",
        "new": """## 输出要求（中心化写入模式）
1. **不要直接写入文件**，将交付文档以 JSON 格式返回
2. 返回格式：
   ```json
   {
     "status": "completed",
     "stage": "deliver",
     "data": {
       "executive_summary": "...",
       "solution_overview": "...",
       "technical_spec": "...",
       "implementation_plan": "...",
       "risk_assessment": "..."
     }
   }
   ```
3. 确保返回的 JSON 完整且可解析
4. 在最终回复中确认：✅ 交付文档已生成"""
    }
]

# 执行迁移
updated_count = 0
for migration in migrations:
    if migration["old"] in content:
        content = content.replace(migration["old"], migration["new"])
        updated_count += 1

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✅ 已迁移 {updated_count} 个 task")
print("迁移的 task：data_collection, research, design, audit, fix, deliver")
