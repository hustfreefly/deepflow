"""
Solution Task Builder V2.0
==========================

为 Solution 领域 Workers 构建 Task。

禁止：直接调用 openclaw
"""

import os
import json

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"


def read_original_prompt(prompt_file: str) -> str:
    """读取原始提示词文件"""
    prompt_path = os.path.join(DEEPFLOW_BASE, "prompts", "solution", prompt_file)
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"# {prompt_file}\n\n执行分析任务。"


def build_data_collection_task(session_id: str, topic: str, constraints: list) -> str:
    """构建数据采集 Task"""
    constraints_text = "\n".join([f"- {c}" for c in constraints]) if constraints else "- 无"
    return f"""你是 Solution 数据收集 Agent。

## 任务
收集以下信息，为"{topic}"的解决方案设计提供数据支撑：

## 约束条件
{constraints_text}

## 执行步骤
1. 搜索相关技术文档和最佳实践
2. 收集行业报告和案例分析
3. 整理竞品信息
4. 将结果写入 blackboard/{session_id}/data/

## 输出要求
- 技术文档摘要
- 行业趋势数据
- 竞品分析对比
- 风险因素清单
"""


def build_planner_task(session_id: str, topic: str, solution_type: str,
                       constraints: list, stakeholders: list) -> str:
    """构建 Planner Task"""
    prompt = read_original_prompt("planner.md")
    constraints_text = ", ".join(constraints) if constraints else "无"
    stakeholders_text = ", ".join(stakeholders) if stakeholders else "无"
    
    context = f"""
## 项目信息
- 主题: {topic}
- 类型: {solution_type}
- 约束: {constraints_text}
- 干系人: {stakeholders_text}

## 输出要求
1. 输出研究计划到 blackboard/{session_id}/stages/planning.json
2. 包含: objectives, scope, methodology, deliverables
3. 明确 required_experts（需要哪些专家）
4. 明确 audit_strategy（审计重点）
"""
    return prompt + "\n" + context


def build_researcher_task(expert: str, session_id: str, topic: str, context: dict) -> str:
    """构建 Researcher Task"""
    prompt = read_original_prompt("researcher_template.md")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 专家角色
{expert}

## 研究主题
{topic}

## 上下文
{context_json}

## 输出要求
1. 输出研究结果到 blackboard/{session_id}/stages/research_{{expert}}.json
2. 包含: findings, analysis, recommendations
3. 引用具体数据来源
"""
    return prompt + "\n" + ctx


def build_designer_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Designer Task"""
    prompt = read_original_prompt("designer.md")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 设计主题
{topic}

## 上下文
{context_json}

## 输出要求
1. 输出设计方案到 blackboard/{session_id}/stages/design.md
2. 包含: architecture, components, data_flow, scalability_plan
3. 考虑约束条件和风险评估
"""
    return prompt + "\n" + ctx


def build_auditor_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Auditor Task"""
    prompt = read_original_prompt("auditor.md")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 审计主题
{topic}

## 上下文
{context_json}

## 输出要求
1. 输出审计报告到 blackboard/{session_id}/stages/audit.json
2. 包含: issues（P0/P1/P2分级）, score（0-100）, recommendations
3. 检查: 完整性、可行性、一致性、创新性
"""
    return prompt + "\n" + ctx


def build_fixer_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Fixer Task（向后兼容）"""
    prompt = read_original_prompt("fixer.md")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 修复主题
{topic}

## 问题清单
{context_json}

## 输出要求
1. 输出修复方案到 blackboard/{session_id}/stages/fix.json
2. 包含: fixes（按优先级排序）, verification_plan
3. 确保每个问题都有对应修复
"""
    return prompt + "\n" + ctx


def build_fixer_task_with_audit(session_id: str, topic: str, audit_path: str) -> str:
    """构建 Fixer Task，从 audit.json 读取问题清单（P0 Fix）"""
    return f"""你是 Solution 修复 Agent。

## 任务
基于审计报告修复方案中的问题。

## 主题
{topic}

## 审计报告位置
{audit_path}

## 执行步骤
1. 读取审计报告 {audit_path}
2. 提取所有 P0/P1/P2 级别问题
3. 为每个问题制定修复方案
4. 按优先级排序修复项
5. 输出修复方案到 blackboard/{session_id}/stages/fix.json

## 输出格式
```json
{{
  "fixes": [
    {{
      "issue_id": "P0-1",
      "description": "问题描述",
      "fix": "修复方案",
      "priority": "P0"
    }}
  ],
  "verification_plan": "验证计划"
}}
```

## 注意
- 如果审计报告不存在，输出错误信息
- 每个修复必须有明确的验证方法
"""


def build_deliver_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Deliver Task"""
    prompt = read_original_prompt("architect.md")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 交付主题
{topic}

## 上下文
{context_json}

## 输出要求
1. 输出最终方案到 blackboard/{session_id}/stages/deliver.md
2. 包含: executive_summary, solution_overview, technical_spec, implementation_plan, risk_assessment
3. 格式清晰，适合直接交付
"""
    return prompt + "\n" + ctx
