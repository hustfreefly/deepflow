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
    """构建数据采集 Task（修复 P1-001: 增加种子 URL）"""
    constraints_text = "\n".join([f"- {c}" for c in constraints]) if constraints else "- 无"
    return f"""你是 Solution 数据收集 Agent。

## 任务
收集以下信息，为"{topic}"的解决方案设计提供数据支撑：

## 约束条件
{constraints_text}

## 种子数据源（优先访问）
1. 技术文档: https://developer.aliyun.com/article/  (搜索"高并发架构")
2. 行业报告: https://www.gartner.com/en/newsroom  (搜索"e-commerce")
3. 竞品分析: https://aws.amazon.com/cn/architecture/  (AWS 架构最佳实践)
4. 最佳实践: https://martinfowler.com/articles/  (Martin Fowler 架构文章)

## 执行步骤
1. 使用 web_fetch 访问上述种子 URL 获取最新信息
2. 收集行业报告和案例分析
3. 整理竞品信息
4. 将结果写入 blackboard/{session_id}/data/

## 输出格式（JSON）
```json
{{
  "tech_docs": [{{"title": "...", "summary": "...", "source": "..."}}],
  "industry_reports": [{{"title": "...", "key_findings": "..."}}],
  "competitor_analysis": [{{"company": "...", "strengths": "...", "weaknesses": "..."}}],
  "risks": [{{"risk": "...", "mitigation": "..."}}]
}}
```

## 执行要求（必须遵守）
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`blackboard/{session_id}/data/research_data.json`
   - 格式：JSON
2. 写入后必须使用 `read` 工具验证文件存在
3. 在最终回复中确认：✅ 文件已成功写入 blackboard/{session_id}/data/research_data.json

## 失败处理
- 如果 write 工具报错，立即报告错误，不要返回虚假成功
- 如果文件写入后 read 验证失败，重试最多 3 次
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
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`blackboard/{session_id}/stages/planning.json`
   - 格式：JSON
2. 写入后必须使用 `read` 工具验证文件存在
3. 在最终回复中确认：✅ 文件已成功写入 blackboard/{session_id}/stages/planning.json

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次
"""
    return prompt + "\n" + context


def build_researcher_task(expert: str, session_id: str, topic: str, context: dict,
                         expert_id: str = "expert_1", 
                         angle: str = "综合分析",
                         reason: str = "需要深入分析该领域") -> str:
    """构建 Researcher Task（修复 P0-001, P0-002, P2-001）
    
    Args:
        expert: 专家名称
        session_id: Session ID
        topic: 研究主题
        context: 上下文字典
        expert_id: 专家标识（用于生成唯一文件名）
        angle: 研究角度（替换 {{ expert.angle }}）
        reason: 需要该专家的原因（替换 {{ expert.reason }}）
    """
    prompt = read_original_prompt("researcher_template.md")
    
    # 替换模板占位符（修复 P2-001：替换所有占位符）
    prompt = prompt.replace("{{ expert.angle }}", angle)
    prompt = prompt.replace("{{ expert.reason }}", reason)
    prompt = prompt.replace("{{ topic }}", topic)
    prompt = prompt.replace("{{ solution_type }}", context.get("type", "architecture"))
    prompt = prompt.replace("{{ mode }}", context.get("mode", "standard"))
    
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 专家角色
{expert}

## 研究角度
{angle}

## 需要原因
{reason}

## 研究主题
{topic}

## 上下文
{context_json}

## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`blackboard/{session_id}/stages/research_{expert_id}.json`
   - 格式：JSON
2. 写入后必须使用 `read` 工具验证文件存在
3. 在最终回复中确认：✅ 文件已成功写入 blackboard/{session_id}/stages/research_{expert_id}.json

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次
"""
    return prompt + "\n" + ctx


def build_designer_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Designer Task（修复 P1-003: 明确前置输入文件）"""
    prompt = read_original_prompt("designer.md")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 设计主题
{topic}

## 上下文
{context_json}

## 前置输入（必须读取）
1. 规划阶段: blackboard/{session_id}/stages/planning.json
2. 研究结果: 
   - blackboard/{session_id}/stages/research_expert_1.json
   - blackboard/{session_id}/stages/research_expert_2.json
   - blackboard/{session_id}/stages/research_expert_3.json
3. 数据收集: blackboard/{session_id}/data/

## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`blackboard/{session_id}/stages/design.md`
   - 格式：Markdown
2. 写入后必须使用 `read` 工具验证文件存在
3. 在最终回复中确认：✅ 文件已成功写入 blackboard/{session_id}/stages/design.md

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次
"""
    return prompt + "\n" + ctx


def build_auditor_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Auditor Task（修复 P2-002: 统一使用 0-100 分制）"""
    prompt = read_original_prompt("auditor.md")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 审计主题
{topic}

## 上下文
{context_json}

## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`blackboard/{session_id}/stages/audit.json`
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
6. 在最终回复中确认：✅ 文件已成功写入 blackboard/{session_id}/stages/audit.json

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次
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
    """构建 Fixer Task，从 audit.json 读取问题清单（P0 Fix + P3-002 fallback）"""
    return f"""你是 Solution 修复 Agent。

## 任务
基于审计报告修复方案中的问题。

## 主题
{topic}

## 审计报告位置
{audit_path}

## 执行步骤
1. 尝试读取审计报告 {audit_path}
2. 如果文件不存在或无法读取：
   - 输出警告："Audit report not found, using default fixes"
   - 基于常见最佳实践生成通用修复建议
3. 如果读取成功：
   - 提取所有 P0/P1/P2 级别问题
   - 为每个问题制定修复方案
4. 按优先级排序修复项
5. **必须使用 `write` 工具** 将修复方案写入以下路径：
   - 文件路径：`blackboard/{session_id}/stages/fix.json`
   - 格式：JSON
6. 写入后必须使用 `read` 工具验证文件存在
7. 在最终回复中确认：✅ 文件已成功写入 blackboard/{session_id}/stages/fix.json

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
  "verification_plan": "验证计划",
  "notes": "备注信息（如使用了默认修复）"
}}
```

## Fallback 机制（P3-002）
- 如果 audit.json 不存在，使用以下默认修复：
  1. 检查设计文档完整性
  2. 验证约束条件是否满足
  3. 确认技术选型合理性
- 在 notes 中标注使用了 fallback 修复
- 每个修复必须有明确的验证方法

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次
"""


def build_deliver_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Deliver Task（修复 P1-002, P2-003: 使用专门交付模板，与 design 区分）"""
    # 使用专门的交付提示，而非 designer.md
    prompt = """# Solution Deliver Agent Prompt
# 角色：交付专家
# 目标：整合所有研究成果，产出最终交付文档

## 角色定义
你是 DeepFlow 解决方案设计系统的交付专家。你的任务是将所有研究成果、架构设计、审计修复整合成一份专业、完整的解决方案交付文档。

## 核心职责
- 整合前期所有阶段输出（planning, research, design, audit, fix）
- 确保文档结构完整、逻辑清晰
- 统一术语和格式
- 生成可直接交付的 Markdown 文档

## 输出标准
### 必须包含的章节
1. 执行摘要（1页以内）
2. 项目背景与目标
3. 需求分析总结
4. 解决方案概述
5. 详细架构设计
6. 技术选型与理由
7. 实施路线图
8. 风险评估与缓解
9. 附录（参考资料、术语表）

### 格式要求
- 使用 Markdown 格式
- 包含目录导航
- 关键决策标注理由
- 图表使用 Mermaid 语法
"""
    
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 交付主题
{topic}

## 上下文
{context_json}

## 前置输入（必须读取）
1. 设计方案: blackboard/{session_id}/stages/design.md
2. 审计报告: blackboard/{session_id}/stages/audit.json
3. 修复记录: blackboard/{session_id}/stages/fix.json

## 输出要求
1. **必须使用 `write` 工具** 将结果写入以下路径：
   - 文件路径：`blackboard/{session_id}/stages/deliver.md`
   - 格式：Markdown
2. 包含: executive_summary, solution_overview, technical_spec, implementation_plan, risk_assessment
3. 格式清晰，适合直接交付
4. 整合审计修复结果，标注变更点
5. 写入后必须使用 `read` 工具验证文件存在
6. 在最终回复中确认：✅ 文件已成功写入 blackboard/{session_id}/stages/deliver.md

## 失败处理
- 如果 write 工具报错，立即报告错误
- 如果文件写入后 read 验证失败，重试最多 3 次
"""
    return prompt + "\n" + ctx
