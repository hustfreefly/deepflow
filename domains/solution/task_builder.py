"""
Solution Task Builder V2.3 - Harness V2 修复版
===============================================

为 Solution 领域 Workers 构建 Task。
包含 Harness V2 修复：Layer 2 约束注入、格式标准化

禁止：直接调用 openclaw

变更日志:
- V2.3 (2026-05-03): Harness V2 P0/P1 修复
  - P0-1: Layer 2 约束 Prompt 注入
  - P0-2: 文件格式标准化
  - P1-1: 约束数量限制（最多2条）
- V2.2 (2026-05-01): 使用PromptRegistry（Phase 2试点）
- V2.1 (2026-05-01): 使用统一prompt读取函数
- V2.0 (2026-04-27): 初始版本
"""

import os
import json
from typing import Dict, List, Tuple

from core.prompt_registry import read_prompt, read_prompt_with_vars
from core.config.path_config import PathConfig

# 保持向后兼容的常量（部分函数可能依赖）
_DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)

# ============================================================================
# Harness V2 修复：Layer 2 约束注入
# ============================================================================

# P1-1: 默认约束（当 Planner 未生成约束时使用）
DEFAULT_LAYER2_CONSTRAINTS = {
    "reviewer_technical": [
        "[必要性] 检查技术选型是否贴合实际资源约束",
        "[完整性] 验证关键架构设计点是否充分"
    ],
    "reviewer_business": [
        "[目标一致性] 评估方案是否直接服务于业务目标",
        "[必要性] 检查 ROI 评估是否合理"
    ],
    "reviewer_risk": [
        "[完整性] 识别所有关键风险点",
        "[必要性] 评估风险缓解措施是否适度"
    ],
    "researcher_expert_1": [
        "[目标一致性] 研究成果必须直接服务于原始目标",
        "[完整性] 覆盖该研究角度的关键方面"
    ],
    "researcher_expert_2": [
        "[目标一致性] 案例研究必须与目标场景相关",
        "[必要性] 避免过度深入无关细节"
    ],
    "researcher_expert_3": [
        "[完整性] 全面识别潜在风险",
        "[必要性] 风险缓解方案贴合实际"
    ],
    "auditor": [
        "[必要性] 审计标准适中，不过度严格或宽松",
        "[目标一致性] 审计始终围绕原始需求"
    ],
    "fixer": [
        "[必要性] 修复方案贴合实际，不过度设计",
        "[完整性] 修复覆盖所有关键问题"
    ],
    "fixer_expert": [
        "[必要性] 深度修复不引入过度复杂度",
        "[目标一致性] 修复始终服务于原始目标"
    ]
}


def get_default_constraints(worker_role: str) -> List[str]:
    """获取默认 Layer 2 约束（P1-1 修复：Fallback 机制）"""
    return DEFAULT_LAYER2_CONSTRAINTS.get(worker_role, [
        "[完整性] 覆盖该任务的关键方面",
        "[必要性] 方案贴合实际，无过度设计"
    ])


def inject_layer2_constraints(base_prompt: str, worker_role: str,
                              layer2_constraints: Dict[str, List[str]]) -> str:
    """
    将 Layer 2 约束注入 Worker Prompt（P0-1 修复）
    
    Args:
        base_prompt: 基础 Prompt
        worker_role: Worker 角色（如 reviewer_technical）
        layer2_constraints: Planner 生成的约束字典 {role: [约束列表]}
        
    Returns:
        注入约束后的完整 Prompt
    """
    # 获取该 Worker 的约束
    constraints = layer2_constraints.get(worker_role, [])
    
    # P1-1 修复：使用默认约束作为 Fallback
    if not constraints:
        constraints = get_default_constraints(worker_role)
    
    # P1-1 修复：限制最多 2 条约束
    constraints = constraints[:2]
    
    # 格式化约束
    constraints_text = "\n".join([f"{i+1}. {c}" for i, c in enumerate(constraints)])
    
    # 构建注入内容
    injection = f"""
## Layer 2 场景约束（来自 Planner）

你必须遵守以下针对本任务的细化约束：

{constraints_text}

### 约束响应要求
在完成任务后，你必须在输出中包含对这些约束的响应：
```json
{{
  "layer2_response": {{
    "constraints": [
      {{"constraint": "约束内容", "satisfied": true/false, "note": "如何满足或不满足的理由（至少10字）"}}
    ]
  }}
}}
```

**重要**: 
- 这些约束是 Planner 基于任务场景为你制定的，必须认真执行
- 如果无法满足某条约束，必须在 note 中说明充分理由
- 敷衍响应（如简单写"已执行"）将被视为无效输出
"""
    
    return base_prompt + "\n\n" + injection


# ============================================================================
# Harness V2 修复：文件格式标准化（P0-2）
# ============================================================================

# 标准 Stage 输出格式定义
STAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["status", "stage", "session_id", "timestamp", "data", "harness_check"],
    "properties": {
        "status": {"enum": ["completed", "failed", "skipped"]},
        "stage": {"type": "string"},
        "session_id": {"type": "string"},
        "timestamp": {"type": "string", "format": "date-time"},
        "data": {"type": "object"},
        "harness_check": {
            "type": "object",
            "required": ["completeness", "necessity", "alignment", "overall_score", "decision", "improvements"],
            "properties": {
                "completeness": {
                    "type": "object",
                    "required": ["score", "level", "reasoning"],
                    "properties": {
                        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "level": {"enum": ["high", "medium", "low"]},
                        "reasoning": {"type": "string"}
                    }
                },
                "necessity": {
                    "type": "object",
                    "required": ["score", "level", "reasoning"],
                    "properties": {
                        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "level": {"enum": ["high", "medium", "low"]},
                        "reasoning": {"type": "string"}
                    }
                },
                "alignment": {
                    "type": "object",
                    "required": ["score", "level", "reasoning"],
                    "properties": {
                        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "level": {"enum": ["high", "medium", "low"]},
                        "reasoning": {"type": "string"}
                    }
                },
                "overall_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "decision": {"enum": ["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]},
                "improvements": {"type": "array", "items": {"type": "string"}}
            }
        },
        "layer2_response": {
            "type": "object",
            "properties": {
                "constraints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["constraint", "satisfied", "note"],
                        "properties": {
                            "constraint": {"type": "string"},
                            "satisfied": {"type": "boolean"},
                            "note": {"type": "string"}
                        }
                    }
                }
            }
        },
        "metadata": {
            "type": "object",
            "properties": {
                "worker_role": {"type": "string"},
                "execution_time_ms": {"type": "integer"},
                "tokens_used": {"type": "integer"}
            }
        }
    }
}


def validate_stage_output(output: dict, stage_name: str) -> Tuple[bool, str]:
    """
    验证 Stage 输出是否符合 Harness V2 标准格式（P0-2 修复）
    
    Args:
        output: Stage 输出字典
        stage_name: Stage 名称（用于错误信息）
        
    Returns:
        (是否有效, 错误信息)
    """
    # 检查是否为字典
    if not isinstance(output, dict):
        return False, f"{stage_name} 输出必须是字典"
    
    # 检查必需字段
    required_fields = ["status", "stage", "data", "harness_check"]
    for field in required_fields:
        if field not in output:
            return False, f"{stage_name} 输出缺少必需字段: {field}"
    
    # 检查 harness_check 结构
    hc = output["harness_check"]
    if not isinstance(hc, dict):
        return False, f"{stage_name} harness_check 必须是字典"
    
    hc_required = ["completeness", "necessity", "alignment", "overall_score", "decision"]
    for field in hc_required:
        if field not in hc:
            return False, f"{stage_name} harness_check 缺少: {field}"
    
    # 检查 decision 值
    valid_decisions = ["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]
    if hc["decision"] not in valid_decisions:
        return False, f"{stage_name} 无效的 decision: {hc['decision']}"
    
    # 检查分数范围
    for dim in ["completeness", "necessity", "alignment"]:
        if dim not in hc:
            return False, f"{stage_name} harness_check 缺少维度: {dim}"
        dim_data = hc[dim]
        if isinstance(dim_data, dict):
            score = dim_data.get("score")
        else:
            score = dim_data
        if score is None:
            return False, f"{stage_name} {dim} 缺少 score"
        if not (0.0 <= score <= 1.0):
            return False, f"{stage_name} {dim} 分数超出范围: {score}"
    
    return True, ""


def build_data_collection_task(session_id: str, topic: str, constraints: list) -> str:
    """构建数据采集 Task（修复 P1-001: 增加种子 URL）"""
    constraints_text = "\n".join([f"- {c}" for c in constraints]) if constraints else "- 无"
    
    # Phase 2: 尝试从文件读取prompt（优先），失败则使用硬编码兜底
    try:
        prompt = read_prompt("solution/data_collection")
        # 替换模板变量
        prompt = prompt.replace("{{TOPIC}}", topic)
        prompt = prompt.replace("{{CONSTRAINTS_TEXT}}", constraints_text)
        prompt = prompt.replace("{{DEEPFLOW_BASE}}", _DEEPFLOW_BASE)
        prompt = prompt.replace("{{SESSION_ID}}", session_id)
    except FileNotFoundError:
        # 向后兼容：硬编码兜底
        prompt = f"""你是 Solution 数据收集 Agent。

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
4. 将结果写入 {_DEEPFLOW_BASE}/blackboard/{session_id}/data/

## 输出格式（JSON）
```json
{{
  "tech_docs": [{{"title": "...", "summary": "...", "source": "..."}}],
  "industry_reports": [{{"title": "...", "key_findings": "..."}}],
  "competitor_analysis": [{{"company": "...", "strengths": "...", "weaknesses": "..."}}],
  "risks": [{{"risk": "...", "mitigation": "..."}}]
}}
```

## 输出要求（子Agent直接写入模式）
1. 使用 **write** 工具将结果写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/data/collection.json`
2. 写入前确保目录存在（必要时创建）
3. 写入格式为JSON，包含以下字段：
   ```json
   {{
     "status": "completed",
     "stage": "data_collection",
     "data": {{
       "tech_docs": [...],
       "industry_reports": [...],
       "competitor_analysis": [...],
       "risks": [...]
     }}
   }}
   ```
4. 在最终回复中确认：✅ 结果已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/data/collection.json`
"""
    
    return prompt


def build_planner_task(session_id: str, topic: str, solution_type: str,
                       constraints: list, stakeholders: list,
                       layer2_constraints: dict = None) -> str:
    """构建 Planner Task（Harness V2）
    
    Args:
        session_id: Session ID
        topic: 任务主题
        solution_type: 方案类型
        constraints: 用户约束列表
        stakeholders: 利益相关者
        layer2_constraints: Layer 2场景约束（Orchestrator集成）
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/planner_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "planner", layer2_constraints or {})
    constraints_text = ", ".join(constraints) if constraints else "无"
    stakeholders_text = ", ".join(stakeholders) if stakeholders else "无"
    
    context = f"""
## 项目信息
- 主题: {topic}
- 类型: {solution_type}
- 约束: {constraints_text}
- 干系人: {stakeholders_text}

## 输出要求（子Agent直接写入模式）
1. 使用 **write** 工具将结果写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/planning.json`
2. 写入前确保目录存在（必要时创建）
3. 写入格式为JSON，包含以下字段：
   ```json
   {{
     "status": "completed",
     "stage": "planning",
     "data": {{
       "goals": [...],
       "constraints": [...],
       "stakeholders": [...],
       "timeline": {{...}},
       "milestones": [...]
     }}
   }}
   ```
4. 在最终回复中确认：✅ 结果已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/planning.json`
"""
    return prompt + "\n" + context


def build_researcher_task(expert: str, session_id: str, topic: str, context: dict,
                         expert_id: str = "expert_1", 
                         angle: str = "综合分析",
                         reason: str = "需要深入分析该领域",
                         layer2_constraints: dict = None) -> str:
    """构建 Researcher Task（Stage 4，Harness V2）
    
    Args:
        expert: 专家名称
        session_id: Session ID
        topic: 研究主题
        context: 上下文字典
        expert_id: 专家标识（用于生成唯一文件名）
        angle: 研究角度（替换 {{ expert.angle }}）
        reason: 需要该专家的原因（替换 {{ expert.reason }}）
        layer2_constraints: Layer 2场景约束（Orchestrator集成）
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/researcher_v2_harness")
    worker_role = f"researcher_{expert_id}"
    prompt = inject_layer2_constraints(base_prompt, worker_role, layer2_constraints or {})
    
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

## 输出要求（子Agent直接写入模式）
1. 使用 **write** 工具将结果写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/research_{expert_id}.json`
2. 写入前确保目录存在（必要时创建）
3. 写入格式为JSON，包含以下字段：
   ```json
   {{
     "status": "completed",
     "stage": "research",
     "data": {{
       "expert_id": "{expert_id}",
       "angle": "...",
       "findings": {{...}},
       "conclusions": [...]
     }}
   }}
   ```
4. 在最终回复中确认：✅ 结果已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/research_{expert_id}.json`
"""
    return prompt + "\n" + ctx


def build_designer_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Designer Task（修复 P1-003: 明确前置输入文件）"""
    prompt = read_prompt("solution/designer")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 设计主题
{topic}

## 上下文
{context_json}

## 前置输入（必须读取）
1. 规划阶段: {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/planning.json
2. 研究结果: 
   - {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/research_expert_1.json
   - {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/research_expert_2.json
   - {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/research_expert_3.json
3. 数据收集: {_DEEPFLOW_BASE}/blackboard/{session_id}/data/

## 输出要求（子Agent直接写入模式）
1. 使用 **write** 工具将结果写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/design.json`
2. 写入前确保目录存在（必要时创建）
3. 写入格式为JSON，包含以下字段：
   ```json
   {{
     "status": "completed",
     "stage": "design",
     "data": {{
       "architecture": "...",
       "components": [...],
       "interfaces": [...],
       "data_model": {{...}}
     }}
   }}
   ```
4. 在最终回复中确认：✅ 结果已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/design.json`
"""
    return prompt + "\n" + ctx


def build_auditor_task(session_id: str, topic: str, context: dict,
                       layer2_constraints: dict = None) -> str:
    """构建 Auditor Task（Stage 6，Harness V2）
    
    Args:
        layer2_constraints: Layer 2场景约束（Orchestrator集成）
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/auditor_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "auditor", layer2_constraints or {})
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 审计主题
{topic}

## 上下文
{context_json}

## 输出要求（子Agent直接写入模式）
1. 使用 **write** 工具将结果写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/audit.json`
2. 写入前确保目录存在（必要时创建）
3. 写入格式为JSON，包含以下字段：
   ```json
   {{
     "status": "completed",
     "stage": "audit",
     "data": {{
       "issues": [{{"level": "P0/P1/P2", "description": "..."}}],
       "score": 85,
       "recommendations": [...]
     }}
   }}
   ```
4. 评分标准:
   - 基础分: 100分
   - 每个 P0 问题: -30分
   - 每个 P1 问题: -15分
   - 每个 P2 问题: -5分
   - 最低分: 0分
5. 在最终回复中确认：✅ 结果已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/audit.json`
"""
    return prompt + "\n" + ctx


def build_fixer_task(session_id: str, topic: str, context: dict,
                     layer2_constraints: dict = None) -> str:
    """构建 Fixer Task（Stage 7，Harness V2）
    
    Args:
        layer2_constraints: Layer 2场景约束（Orchestrator集成）
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/fixer_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "fixer", layer2_constraints or {})
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 修复主题
{topic}

## 问题清单
{context_json}

## 输出要求（子Agent直接写入模式）
1. 使用 **write** 工具将结果写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/fix.json`
2. 写入前确保目录存在（必要时创建）
3. 写入格式为JSON，包含以下字段：
   ```json
   {{
     "status": "completed",
     "stage": "fix",
     "data": {{
       "fixes": [{{"priority": "P0", "issue": "...", "fix": "..."}}],
       "verification_plan": "..."
     }}
   }}
   ```
4. 在最终回复中确认：✅ 结果已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/fix.json`
"""
    return prompt + "\n" + ctx


def build_fixer_task_with_audit(session_id: str, topic: str, audit_path: str) -> str:
    """构建 Fixer Task，从 audit.json 读取问题清单（P0 Fix + P3-002 fallback）"""
    # Phase 2: 尝试从文件读取prompt（优先），失败则使用硬编码兜底
    try:
        prompt = read_prompt("solution/fixer_with_audit")
        # 替换模板变量
        prompt = prompt.replace("{{TOPIC}}", topic)
        prompt = prompt.replace("{{AUDIT_PATH}}", audit_path)
        prompt = prompt.replace("{{DEEPFLOW_BASE}}", _DEEPFLOW_BASE)
        prompt = prompt.replace("{{SESSION_ID}}", session_id)
        return prompt
    except FileNotFoundError:
        # 向后兼容：硬编码兜底
        pass
    
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
5. 使用 **write** 工具将修复方案写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/fix.json`
6. 在最终回复中确认：✅ 修复方案已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/fix.json`

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
    # Phase 2: 尝试从文件读取prompt（优先），失败则使用硬编码兜底
    try:
        prompt = read_prompt("solution/deliver")
    except FileNotFoundError:
        # 向后兼容：硬编码兜底
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
1. 设计方案: {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/design.md
2. 审计报告: {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/audit.json
3. 修复记录: {_DEEPFLOW_BASE}/blackboard/{session_id}/stages/fix.json

## 输出要求（子Agent直接写入模式）
1. 使用 **write** 工具将结果写入：
   `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/deliver.json`
2. 写入前确保目录存在（必要时创建）
3. 写入格式为JSON，包含以下字段：
   ```json
   {{
     "status": "completed",
     "stage": "deliver",
     "data": {{
       "executive_summary": "...",
       "solution_overview": "...",
       "technical_spec": "...",
       "implementation_plan": "...",
       "risk_assessment": "..."
     }}
   }}
   ```
4. 在最终回复中确认：✅ 结果已写入 `{_DEEPFLOW_BASE}/blackboard/{session_id}/stages/deliver.json`
"""
    return prompt + "\n" + ctx


# ============================================================
# Stage 2: Reviewers ×3（并行评审）
# ============================================================

def build_reviewer_task(session_id: str, topic: str, review_type: str,
                        review_focus: str, input_plan: dict,
                        layer2_constraints: dict = None) -> str:
    """构建 Reviewer Task（Stage 3，Harness V2）
    
    Args:
        session_id: Session ID
        topic: 评审主题
        review_type: 评审类型（technical/business/risk）
        review_focus: 评审焦点描述
        input_plan: Planner生成的执行计划
        layer2_constraints: Layer 2场景约束（P0-1修复）
    """
    # P0-1 修复：读取基础 Prompt 后注入 Layer 2 约束
    base_prompt = read_prompt("solution/reviewer_v2_harness")
    worker_role = f"reviewer_{review_type}"
    prompt = inject_layer2_constraints(base_prompt, worker_role, layer2_constraints or {})
    
    # 替换模板变量
    prompt = prompt.replace("{{ review_type }}", review_type)
    prompt = prompt.replace("{{ review_focus }}", review_focus)
    
    # 根据评审类型确定具体检查项
    if review_type == "technical":
        specific_checks = """
### 技术评审检查项
- 架构设计是否合理
- 技术选型是否匹配业务规模
- 性能指标是否可达成
- 扩展性是否满足未来3年增长
- 技术债务风险"""
    elif review_type == "business":
        specific_checks = """
### 商业评审检查项
- ROI估算是否合理
- 市场竞争力分析
- 商业模式可行性
- 成本效益比
- 投资回报周期"""
    else:  # risk
        specific_checks = """
### 风险评审检查项
- 技术风险识别
- 业务连续性风险
- 合规风险
- 供应商锁定风险
- 人员技能风险"""
    
    prompt = prompt.replace("{{ review_type_specific_checks }}", specific_checks)
    
    input_plan_json = json.dumps(input_plan, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 评审主题
{topic}

## 输入计划
{input_plan_json}

## Blackboard路径
{_DEEPFLOW_BASE}/blackboard/{session_id}
"""
    return prompt + "\n" + ctx


# ============================================================
# Stage 2, 5, 9: Harness V2（3维度质量检查）
# ============================================================

def build_harness_v2_task(session_id: str, topic: str, worker_role: str,
                          layer2_constraints: list = None) -> str:
    """构建 Harness V2 Task（通用Worker自评）
    
    Args:
        session_id: Session ID
        topic: 任务主题
        worker_role: Worker角色（planner/reviewer/researcher/...）
        layer2_constraints: Layer 2场景约束列表
    """
    from core.prompt_registry import read_prompt
    
    # 根据角色选择Prompt
    prompt_map = {
        "planner": "solution/planner_v2_harness",
        "reviewer": "solution/reviewer_v2_harness",
        "researcher": "solution/researcher_v2_harness",
        "consolidator": "solution/consolidator_v2_harness",
        "auditor": "solution/auditor_v2_harness",
        "fixer": "solution/fixer_v2_harness",
        "fixer_expert": "solution/fixer_expert_v2_harness",
        "summarizer": "solution/summarizer_v2_harness"
    }
    
    prompt_key = prompt_map.get(worker_role, "solution/harness_v2")
    prompt = read_prompt(prompt_key)
    
    # 注入Layer 2约束
    if layer2_constraints:
        constraints_text = "\n".join([f"- {c}" for c in layer2_constraints])
        prompt = prompt.replace("{layer2_constraints}", constraints_text)
    else:
        prompt = prompt.replace("{layer2_constraints}", "无")
    
    # 注入通用上下文
    prompt = prompt.replace("{topic}", topic)
    prompt = prompt.replace("{session_id}", session_id)
    prompt = prompt.replace("{_DEEPFLOW_BASE}", _DEEPFLOW_BASE)
    
    return prompt


def build_harness_final_task(session_id: str, topic: str) -> str:
    """构建 Harness Final Task（Stage 9，独立门禁）
    
    职责：
    - 3维度评分（权重35/25/40）
    - 跨阶段一致性检查
    - 生成Summarizer必须响应的意见清单
    """
    from core.prompt_registry import read_prompt
    
    prompt = read_prompt("solution/harness_v3")
    
    # 注入输入文件路径
    prompt = prompt.replace("{blackboard_path}", f"{_DEEPFLOW_BASE}/blackboard/{session_id}")
    prompt = prompt.replace("{topic}", topic)
    prompt = prompt.replace("{session_id}", session_id)
    
    return prompt


# 保留旧版Harness Task（向后兼容）
def build_harness_task(session_id: str, topic: str, current_solution: dict,
                       is_final: bool = False) -> str:
    """构建 Harness V3 Task（双维度质量检查）
    
    Args:
        session_id: Session ID
        topic: 检查主题
        current_solution: 当前方案内容
        is_final: 是否为最终检查（Stage 7.5）
    """
    prompt = read_prompt("solution/harness_v3")
    
    # 设置阶段相关变量
    if is_final:
        stage_number = "7.5"
        stage_suffix = "_final"
        check_type = "最终质量检查"
        final_instructions = """
## 最终检查特殊要求
- 对比Stage 3.5的评分，评估改进效果
- 确认所有Critical问题已解决
- 给出最终通过/阻断决策"""
    else:
        stage_number = "3.5"
        stage_suffix = ""
        check_type = "中期质量检查"
        final_instructions = ""
    
    prompt = prompt.replace("{{ stage_number }}", stage_number)
    prompt = prompt.replace("{{ stage_suffix }}", stage_suffix)
    prompt = prompt.replace("{{ check_type }}", check_type)
    prompt = prompt.replace("{{ final_check_instructions }}", final_instructions)
    
    # 准备检查清单
    completeness_items = """
1. 容错机制: 是否有故障处理和恢复策略
2. 数据流: 数据流向是否清晰，有无断点
3. 测试策略: 是否有单元/集成/压力测试计划
4. 监控运维: 是否有监控、告警、日志方案
5. 成本估算: 是否有详细的CAPEX和OPEX估算
6. 文档完整性: 设计/API/运维文档是否齐全"""
    
    appropriateness_items = """
1. 避免过度设计: 技术选型是否与业务规模匹配
2. 避免过度审计: 审计深度是否与风险等级匹配
3. 贴合实际场景: 是否考虑实际约束（预算/周期/团队）
4. 现实可行: 技术是否可实现，团队是否有能力
5. 约束匹配: 所有constraints是否都有对应方案"""
    
    prompt = prompt.replace("{{ completeness_items }}", completeness_items)
    prompt = prompt.replace("{{ appropriateness_items }}", appropriateness_items)
    
    solution_json = json.dumps(current_solution, ensure_ascii=False, indent=2)
    
    ctx = f"""
## 检查主题
{topic}

## 当前方案
{solution_json}

## Blackboard路径
{_DEEPFLOW_BASE}/blackboard/{session_id}
"""
    return prompt + "\n" + ctx


# ============================================================
# Stage 5: Consolidator（成果整合）
# ============================================================

def build_consolidator_task(session_id: str, topic: str,
                            research_outputs: list,
                            layer2_constraints: dict = None) -> str:
    """构建 Consolidator Task（Stage 5，Harness V2内嵌检查）
    
    Args:
        session_id: Session ID
        topic: 整合主题
        research_outputs: 所有Researcher的输出列表
        layer2_constraints: Layer 2场景约束（Orchestrator集成）
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/consolidator_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "consolidator", layer2_constraints or {})
    
    # 分析冲突
    conflicts = []
    # 简单的冲突检测：如果有多个researcher对同一技术给出不同建议
    tech_suggestions = {}
    for output in research_outputs:
        if 'tech_stack' in output:
            for tech, choice in output['tech_stack'].items():
                if tech not in tech_suggestions:
                    tech_suggestions[tech] = []
                tech_suggestions[tech].append(choice)
    
    for tech, choices in tech_suggestions.items():
        if len(set(choices)) > 1:
            conflicts.append({
                "area": f"技术选型: {tech}",
                "different_opinions": choices
            })
    
    conflicts_json = json.dumps(conflicts, ensure_ascii=False, indent=2)
    outputs_json = json.dumps(research_outputs, ensure_ascii=False, indent=2)
    
    # 整合策略
    integration_strategy = """
1. 技术选型：基于业务场景和团队能力选择
2. 成本估算：取各researcher估算的加权平均
3. 时间规划：考虑最悲观的researcher估计
4. 风险整合：合并所有识别的风险，去重"""
    
    prompt = prompt.replace("{{ research_outputs }}", outputs_json)
    prompt = prompt.replace("{{ conflicts }}", conflicts_json)
    prompt = prompt.replace("{{ integration_strategy }}", integration_strategy)
    
    ctx = f"""
## 整合主题
{topic}

## Blackboard路径
{_DEEPFLOW_BASE}/blackboard/{session_id}
"""
    return prompt + "\n" + ctx


# ============================================================
# Stage 7: Fixer Expert（深度修正）
# ============================================================

def build_fixer_expert_task(session_id: str, topic: str,
                            audit_findings: list, severity: str,
                            layer2_constraints: dict = None) -> str:
    """构建 Fixer Expert Task（Stage 8，Harness V2深度修正）
    
    Args:
        session_id: Session ID
        topic: 修正主题
        audit_findings: Auditor发现的问题列表
        severity: 严重性级别（critical/major/minor）
        layer2_constraints: Layer 2场景约束（Orchestrator集成）
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/fixer_expert_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "fixer_expert", layer2_constraints or {})
    
    # 根据严重性确定修正策略
    if severity == "critical":
        fix_strategy = """
### Critical级别修正策略
1. 必须修正，否则方案不可行
2. 可能需要重新设计核心模块
3. 重新评估项目可行性
4. 更新所有相关文档"""
    elif severity == "major":
        fix_strategy = """
### Major级别修正策略
1. 强烈建议修正，显著影响质量
2. 需要调整设计或策略
3. 评估对成本/时间的影响
4. 确保修正不引入新问题"""
    else:  # minor
        fix_strategy = """
### Minor级别修正策略
1. 可选修正，优化细节
2. 不影响整体可行性
3. 文档描述更清晰
4. 低优先级处理"""
    
    prompt = prompt.replace("{{ severity }}", severity)
    prompt = prompt.replace("{{ fix_strategy }}", fix_strategy)
    
    findings_json = json.dumps(audit_findings, ensure_ascii=False, indent=2)
    prompt = prompt.replace("{{ audit_findings }}", findings_json)
    
    ctx = f"""
## 修正主题
{topic}

## Blackboard路径
{_DEEPFLOW_BASE}/blackboard/{session_id}
"""
    return prompt + "\n" + ctx


# ============================================================
# Stage 8: Summarizer（最终总结）
# ============================================================

def build_summarizer_task(session_id: str, topic: str,
                          all_outputs: dict,
                          layer2_constraints: dict = None) -> str:
    """构建 Summarizer Task（Stage 10，Harness V2最终总结）
    
    Args:
        session_id: Session ID
        topic: 总结主题
        all_outputs: 所有stage的输出字典
        layer2_constraints: Layer 2场景约束（Orchestrator集成）
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/summarizer_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "summarizer", layer2_constraints or {})
    
    # 提取关键信息生成summary
    solution_summary = f"""
### 方案概述
本方案针对"{topic}"，通过8阶段深度分析与优化，形成了完整的技术与实施规划。

### 核心亮点
- 经过多维度评审和审计，质量达到高标准
- 技术选型与业务需求精准匹配
- 风险控制完善，实施路径清晰
"""
    
    key_recommendations = [
        "优先实施高价值低风险的模块",
        "建立完善的监控和告警体系",
        "分阶段上线，控制风险暴露",
        "定期进行架构评审和技术债务清理"
    ]
    
    all_outputs_json = json.dumps(all_outputs, ensure_ascii=False, indent=2)
    
    prompt = prompt.replace("{{ all_outputs }}", all_outputs_json)
    prompt = prompt.replace("{{ solution_summary }}", solution_summary)
    prompt = prompt.replace("{{ key_recommendations }}", 
                           "\n".join([f"{i+1}. {r}" for i, r in enumerate(key_recommendations)]))
    
    ctx = f"""
## 总结主题
{topic}

## Blackboard路径
{_DEEPFLOW_BASE}/blackboard/{session_id}

## 输出文件要求
1. final_result.json - 结构化最终结果
2. stages/final_solution.md - Markdown汇报文档
"""
    return prompt + "\n" + ctx
