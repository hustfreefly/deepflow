"""
任务构建器,使用 BlackboardManager API 替代路径拼接

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
Solution Task Builder V2.3 - Harness V2 修复版
===============================================

为 Solution 领域 Workers 构建 Task。
包含 Harness V2 修复:Layer 2 约束注入、格式标准化

禁止:直接调用 openclaw

变更日志:
- V2.3 (2026-05-03): Harness V2 P0/P1 修复
  - P0-1: Layer 2 约束 Prompt 注入
  - P0-2: 文件格式标准化
  - P1-1: 约束数量限制(最多2条)
- V2.2 (2026-05-01): 使用PromptRegistry(Phase 2试点)
- V2.1 (2026-05-01): 使用统一prompt读取函数
- V2.0 (2026-04-27): 初始版本
"""

import core.bootstrap
import os
import json
from typing import Dict, List, Tuple
import logging
logger = logging.getLogger(__name__)


from core.prompt_registry import read_prompt, read_prompt_with_vars
from core.config.path_config import PathConfig
from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY, BlackboardManager
from domains.solution_pro.spec_context import build_worker_context_section

# ============================================================================
# P0-3 契约修复: Layer 2 运行时读取指令模板
# 追加到下游 Worker prompt 尾部,让 Worker 运行时读取 planning.json
# 而非依赖 Orchestrator 预先注入(因为 get_all_tasks 执行时 planning.json 可能尚未生成)
# ============================================================================
LAYER2_READ_INSTRUCTION = """
## Layer 2 场景约束(运行时读取)

在开始你的任务前,你必须先通过 BlackboardManager API 读取 Planner 生成的场景约束:

```python
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager(session_id="{session_id}")
planning_data = bb.read_stage("planning")
```

从 `planning_data` 中提取 `layer2_constraints` 字段(如果存在),
找到 `worker_role="{worker_role}"` 对应的约束列表。

如果 `layer2_constraints` 字段不存在或为 `null`,
则使用以下默认约束:
1. [完整性] 覆盖该任务的关键方面
2. [必要性] 方案贴合实际,无过度设计

在你的输出 JSON 中包含 `layer2_response` 字段来响应这些约束。

⚠️ 绝对禁止自己拼接路径。所有 stage 操作必须通过 BlackboardManager API。
"""

REQ_TRACEABILITY_INSTRUCTION = """
## REQ-ID 需求追踪要求

在开始任务前,通过 BlackboardManager API 读取需求文件:

```python
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager(session_id="{session_id}")
frozen_spec = bb.read_data("frozen_spec.json")
structured_req = bb.read_data("structured_requirements.json")  # 如果存在
```

`frozen_spec.json.executive_summary` 是全局理解的权威来源；prompt 中注入的"全局理解"文本只作为辅助摘要。若两者不一致，以 `frozen_spec.json` 为准，并在输出中说明差异。

⚠️ 绝对禁止自己拼接路径。所有 data 操作必须通过 BlackboardManager API。

你的输出 JSON 顶层必须包含:

```json
{{
  "covered_req_ids": ["REQ-001"],
  "requirement_evidence": [
    {{
      "req_id": "REQ-001",
      "status": "covered|partial|missing",
      "evidence": "说明你在本阶段如何覆盖或未覆盖该需求"
    }}
  ]
}}
```

规则:
- 只允许使用 `frozen_spec.json` 中存在的 REQ-ID。
- `structured_requirements.json` 只能作为覆盖提示,不能新增或覆盖 `frozen_spec.json` 的权威需求。
- 如果某个 P0 需求与你的任务相关但无法覆盖,必须写入 `status="missing"` 并说明原因。
- 不要臆造新的 REQ-ID;需要新增需求时写入建议,但不要改变 frozen spec。
"""

# ============================================================================
# Harness V2 修复:Layer 2 约束注入
# ============================================================================

# P1-1: 默认约束(当 Planner 未生成约束时使用)
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
        "[必要性] 审计标准适中,不过度严格或宽松",
        "[目标一致性] 审计始终围绕原始需求"
    ],
    "fixer": [
        "[必要性] 修复方案贴合实际,不过度设计",
        "[完整性] 修复覆盖所有关键问题"
    ],
    "fixer_expert": [
        "[必要性] 深度修复不引入过度复杂度",
        "[目标一致性] 修复始终服务于原始目标"
    ]
}


def get_default_constraints(worker_role: str) -> List[str]:
    """获取默认 Layer 2 约束(P1-1 修复:Fallback 机制)"""
    return DEFAULT_LAYER2_CONSTRAINTS.get(worker_role, [
        "[完整性] 覆盖该任务的关键方面",
        "[必要性] 方案贴合实际,无过度设计"
    ])


def inject_layer2_constraints(base_prompt: str, worker_role: str,
                              layer2_constraints: Dict[str, List[str]]) -> str:
    """
    将 Layer 2 约束注入 Worker Prompt(P0-1 修复)

    Args:
        base_prompt: 基础 Prompt
        worker_role: Worker 角色(如 reviewer_technical)
        layer2_constraints: Planner 生成的约束字典 {role: [约束列表]}

    Returns:
        注入约束后的完整 Prompt
    """
    # 获取该 Worker 的约束
    constraints = layer2_constraints.get(worker_role, [])

    # P1-1 修复:使用默认约束作为 Fallback
    if not constraints:
        constraints = get_default_constraints(worker_role)

    # P1-1 修复:限制最多 2 条约束
    constraints = constraints[:2]

    # 格式化约束
    constraints_text = "\n".join([f"{i+1}. {c}" for i, c in enumerate(constraints)])

    # 构建注入内容
    injection = f"""
## Layer 2 场景约束(来自 Planner)

你必须遵守以下针对本任务的细化约束:

{constraints_text}

### 约束响应要求
在完成任务后,你必须在输出中包含对这些约束的响应:
```json
{{
  "layer2_response": {{
    "constraints": [
      {{"constraint": "约束内容", "satisfied": true/false, "note": "如何满足或不满足的理由(至少10字)"}}
    ]
  }}
}}
```

**重要**:
- 这些约束是 Planner 基于任务场景为你制定的,必须认真执行
- 如果无法满足某条约束,必须在 note 中说明充分理由
- 敷衍响应(如简单写"已执行")将被视为无效输出
"""

    return base_prompt + "\n\n" + injection


def inject_req_traceability(base_prompt: str, session_id: str) -> str:
    """Append the shared REQ-ID traceability contract to a worker prompt."""
    return base_prompt + "\n\n" + REQ_TRACEABILITY_INSTRUCTION.format(
        session_id=session_id
    )


# ============================================================================
# Harness V2 修复:文件格式标准化(P0-2)
# ============================================================================

# Harness 豁免阶段:这些阶段不需要 4 维 harness_check
# - data_collection: 采集阶段,不做质量评分
# - planning: 规划阶段,有 quality_assessment 但不是标准 4 维 harness
# - summarizer: 总结阶段,不做质量评分
HARNESS_EXEMPT_STAGES = frozenset(["data_collection", "planning", "summarizer"])

# 标准 Stage 输出格式定义
STAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["status", "stage", "covered_req_ids"],
    "properties": {
        "status": {"enum": ["completed", "failed", "skipped"]},
        "stage": {"type": "string"},
        "session_id": {"type": "string"},
        "timestamp": {"type": "string", "format": "date-time"},
        "data": {"type": "object"},
        "covered_req_ids": {"type": "array", "items": {"type": "string"}},
        "harness_check": {
            "type": "object",
            "required": ["completeness", "necessity", "alignment", "global_impact", "overall_score", "decision", "improvements"],
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
                "global_impact": {
                    "type": "object",
                    "required": ["score", "level", "reasoning"],
                    "properties": {
                        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "level": {"enum": ["high", "medium", "low"]},
                        "reasoning": {"type": "string"}
                    }
                },
                "overall_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "decision": {"enum": ["PASS", "PASS_WITH_CONDITIONS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]},
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
    验证 Stage 输出是否符合 Harness V2 标准格式(P0-2 修复)

    Args:
        output: Stage 输出字典
        stage_name: Stage 名称(用于错误信息)

    Returns:
        (是否有效, 错误信息)
    """
    # 检查是否为字典
    if not isinstance(output, dict):
        return False, f"{stage_name} 输出必须是字典"

    # 豁免阶段: 只检查 covered_req_ids(不要求 status/stage/harness_check)
    if stage_name in HARNESS_EXEMPT_STAGES:
        if "covered_req_ids" not in output:
            return False, f"{stage_name} 输出缺少必需字段: covered_req_ids"
    else:
        # 非豁免阶段: 检查完整字段集
        required_fields = ["status", "stage", "covered_req_ids"]
        for field in required_fields:
            if field not in output:
                return False, f"{stage_name} 输出缺少必需字段: {field}"
        # 非豁免阶段必须有 harness_check
        if "harness_check" not in output:
            return False, f"{stage_name} 输出缺少必需字段: harness_check"

        # 检查 harness_check 结构
        hc = output["harness_check"]
        if not isinstance(hc, dict):
            return False, f"{stage_name} harness_check 必须是字典"

        hc_required = ["completeness", "necessity", "alignment", "global_impact", "overall_score", "decision"]
        for field in hc_required:
            if field not in hc:
                return False, f"{stage_name} harness_check 缺少: {field}"

        # 检查 decision 值
        valid_decisions = ["PASS", "PASS_WITH_CONDITIONS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]
        if hc["decision"] not in valid_decisions:
            return False, f"{stage_name} 无效的 decision: {hc['decision']}"

        # 检查分数范围
        for dim in ["completeness", "necessity", "alignment", "global_impact"]:
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

    req_ids = output.get("covered_req_ids")
    if not isinstance(req_ids, list):
        return False, f"{stage_name} covered_req_ids 必须是数组"
    for req_id in req_ids:
        if not isinstance(req_id, str) or not req_id.startswith("REQ-"):
            return False, f"{stage_name} covered_req_ids 包含非法REQ-ID: {req_id}"

    # P0-6 修复: 非豁免阶段必须包含 requirement_evidence(REQ-ID 追踪契约)
    if stage_name not in HARNESS_EXEMPT_STAGES:
        req_evidence = output.get("requirement_evidence")
        if req_evidence is None:
            return False, f"{stage_name} 缺少 requirement_evidence"
        if not isinstance(req_evidence, list):
            return False, f"{stage_name} requirement_evidence 必须是数组"
        for item in req_evidence:
            if not isinstance(item, dict):
                return False, f"{stage_name} requirement_evidence 每项必须是对象"
            if "req_id" not in item or "status" not in item:
                return False, f"{stage_name} requirement_evidence 每项必须包含 req_id 和 status"

    return True, ""


def build_data_collection_task(session_id: str, topic: str, constraints: list, living_spec: dict = None) -> str:
    """构建数据采集 Task(修复 P1-001: 增加种子 URL)

    Args:
        session_id: Session ID
        topic: 任务主题
        constraints: 用户约束列表
        living_spec: Living Spec(Spec Pro 产出,可选)
    """
    constraints_text = "\n".join([f"- {c}" for c in constraints]) if constraints else "- 无"

    # Living Spec 注入:基于 confirmed 生成精准搜索词
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]

        # P4: 注入 executive_summary(Core 组 - pain_point + scenario)
        objective = confirmed.get("objective", topic)
        one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
        pain_points = confirmed.get("pain_points", [])[:3]
        scenarios = confirmed.get("key_scenarios", [])[:3]

        living_spec_context += f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**为什么做(痛点)**:
{chr(10).join([f"- {p}" for p in pain_points]) if pain_points else "- 未指定"}

**关键场景**:
{chr(10).join([f"- {s}" for s in scenarios]) if scenarios else "- 未指定"}

## 你的角色相关需求分组(Data Collection: Core - pain_point + scenario)

**搜索策略**: 基于以上需求生成精准搜索关键词,优先搜索痛点解决方案和核心场景相关的技术方案。
"""

    # Phase 2: 尝试从文件读取prompt(优先),失败则使用硬编码兜底
    try:
        prompt = read_prompt("solution/data_collection")
        # 替换模板变量
        prompt = prompt.replace("{{TOPIC}}", topic)
        prompt = prompt.replace("{{CONSTRAINTS_TEXT}}", constraints_text)
        # DEEPFLOW_BASE from PathConfig base_dir
        prompt = prompt.replace("{{SESSION_ID}}", session_id)
    except FileNotFoundError:
        # 向后兼容:硬编码兜底
        prompt = f"""你是 Solution 数据收集 Agent。

## 任务
收集以下信息,为"{topic}"的解决方案设计提供数据支撑:

## 约束条件
{constraints_text}

## 种子数据源(优先访问)
1. 技术文档: https://developer.aliyun.com/article/  (搜索"高并发架构")
2. 行业报告: https://www.gartner.com/en/newsroom  (搜索"e-commerce")
3. 竞品分析: https://aws.amazon.com/cn/architecture/  (AWS 架构最佳实践)
4. 最佳实践: https://martinfowler.com/articles/  (Martin Fowler 架构文章)

## 执行步骤
1. 使用 web_fetch 访问上述种子 URL 获取最新信息
2. 收集行业报告和案例分析
3. 整理竞品信息
4. 使用 BlackboardManager API 写入结果到 stage "data_collection"

## 输出格式(JSON)
```json
{{
  "tech_docs": [{{"title": "...", "summary": "...", "source": "..."}}],
  "industry_reports": [{{"title": "...", "key_findings": "..."}}],
  "competitor_analysis": [{{"company": "...", "strengths": "...", "weaknesses": "..."}}],
  "risks": [{{"risk": "...", "mitigation": "..."}}]
}}
```

## 输出要求(子Agent直接写入模式)
1. 使用 **write** 工具将结果写入:
   `bb.write_stage("data_collection", {...})`
2. 写入前确保目录存在(必要时创建)
3. 写入格式为JSON,包含以下字段:
   ```json
   {{
     "status": "completed",
     "stage": "data_collection",
     "session_id": "{session_id}",
     "timestamp": "<ISO8601>",
     "data": {{
       "tech_docs": [...],
       "industry_reports": [...],
       "competitor_analysis": [...],
       "risks": [...]
     }},
   }}
   ```
4. 在最终回复中确认:✅ 结果已写入 `bb.write_stage("data_collection", {...})`
"""

    # Append living_spec_context (全局理解) to prompt
    prompt = prompt + "\n" + living_spec_context

    # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "data_collection")
        if spec_ctx:
            prompt += "\n\n" + spec_ctx

    return prompt


def build_planner_task(session_id: str, topic: str, solution_type: str,
                       constraints: list, stakeholders: list,
                       living_spec: dict = None) -> str:
    """构建 Planner Task(Harness V2)

    Args:
        session_id: Session ID
        topic: 任务主题
        solution_type: 方案类型
        constraints: 用户约束列表
        stakeholders: 利益相关者
        living_spec: Living Spec(Spec Pro 产出,可选)
    """
    # 读取基础Prompt并注入Layer 2约束
    base_prompt = read_prompt("solution/planner_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "planner", {})
    constraints_text = ", ".join(constraints) if constraints else "无"
    stakeholders_text = ", ".join(stakeholders) if stakeholders else "无"

    # Living Spec 上下文注入:完整需求摘要
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]

        pain_points = "\n".join([f"- {p}" for p in confirmed.get("pain_points", [])]) or "- 未指定"
        success_metrics = "\n".join([f"- {m.get('metric','')}: {m.get('target','')} (当前: {m.get('current','未知')})" for m in confirmed.get("success_metrics", [])]) or "- 未指定"
        users = "\n".join([f"- {u.get('role','')} ({u.get('count','未知')}人): {u.get('key_needs','')}" for u in confirmed.get("users", [])]) or "- 未指定"
        key_scenarios = "\n".join([f"- {s}" for s in confirmed.get("key_scenarios", [])[:5]]) or "- 未指定"
        always_do = "\n".join([f"- {c}" for c in confirmed.get("capabilities", {}).get("always_do", [])]) or "- 未指定"
        should_do = "\n".join([f"- {c}" for c in confirmed.get("capabilities", {}).get("should_do", [])]) or "- 未指定"
        never_do = "\n".join([f"- {c}" for c in confirmed.get("capabilities", {}).get("never_do", [])]) or "- 未指定"
        qa_text = "\n".join([f"- {q.get('category','')}: {q.get('spec','')} (优先级: {q.get('priority','P1')})" for q in confirmed.get("quality_attributes", [])]) or "- 未指定"
        budget = confirmed.get("constraints", {}).get("budget", "未指定")
        timeline = confirmed.get("constraints", {}).get("timeline", "未指定")
        tech_stack = ", ".join(confirmed.get("constraints", {}).get("tech_stack", [])) or "未指定"
        _raw_systems = confirmed.get("integration", {}).get("existing_systems", [])
        existing_systems = "\n".join([f"- {s.get('name','')}: {s.get('role','')}" if isinstance(s, dict) else f"- {s}" for s in _raw_systems]) or "- 未指定"
        risks = "\n".join([f"- {r}" for r in confirmed.get("risks_and_assumptions", {}).get("risks", [])]) or "- 未指定"
        assumptions = "\n".join([f"- {a}" for a in confirmed.get("risks_and_assumptions", {}).get("assumptions", [])]) or "- 未指定"
        living_spec_context = f"""
## 全局理解(来自 executive_summary)

> **重要**: 以下需求已经过用户确认,是权威来源。你的任务是制定**研究计划**,不是重新收集需求。

### 核心目标
{confirmed.get('objective', '未指定')}

### 关键痛点
{pain_points}

### 成功指标
{success_metrics}

### 用户角色
{users}

### 关键场景
{key_scenarios}

### 能力要求
**必须做 (Always)**:
{always_do}

**应该做 (Should)**:
{should_do}

**禁止做 (Never)**:
{never_do}

### 质量属性
{qa_text}

### 约束条件
- 预算: {budget}
- 时间: {timeline}
- 技术栈: {tech_stack}

### 集成环境
{existing_systems}

### 风险与假设
**风险**: {risks}
**假设**: {assumptions}
"""

    context = f"""
## 项目信息
- 主题: {topic}
- 类型: {solution_type}
- 约束: {constraints_text}
- 干系人: {stakeholders_text}
{living_spec_context}
## 前置输入(必须读取)
1. 数据收集结果:
   `bb.read_stage("data_collection")`

请先读取 `data/collection.json`, 将其中的 `for_planner`、`recommendations_for_planner`、`search_results_summary` 等信息纳入规划。若文件不存在或内容为空, 在 `warnings` 中说明, 但不要假装已经使用。

## 输出要求(子Agent直接写入模式)
1. 使用 **write** 工具将结果写入:
   `bb.write_stage("planning", {...})`
2. 写入前确保目录存在(必要时创建)
3. 写入格式为JSON,包含以下字段:
   ```json
   {{
     "status": "completed",
     "stage": "planning",
     "session_id": "{session_id}",
     "timestamp": "<ISO8601>",
     "data": {{
       "goals": [...],
       "constraints": [...],
       "stakeholders": [...],
       "timeline": {{...}},
       "milestones": [...]
     }},
   }}
   ```
4. 在最终回复中确认:✅ 结果已写入 `bb.write_stage("planning", {...})`
"""
    final_prompt = prompt + "\n" + context

    # S4: 注入 Spec Pro 上下文(user_directives, inferred_pending 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "planner")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


def build_researcher_task(expert: str, session_id: str, topic: str, context: dict,
                         expert_id: str = "expert_1",
                         angle: str = "综合分析",
                         reason: str = "需要深入分析该领域",
                         living_spec: dict = None) -> str:
    """构建 Researcher Task(Stage 4,Harness V2)

    Args:
        expert: 专家名称
        session_id: Session ID
        topic: 研究主题
        context: 上下文字典
        expert_id: 专家标识(用于生成唯一文件名)
        angle: 研究角度(替换 {{ expert.angle }})
        reason: 需要该专家的原因(替换 {{ expert.reason }})
        living_spec: Living Spec(可选)
    """
    # 读取基础Prompt并注入Layer 2约束(使用默认)
    base_prompt = read_prompt("solution/researcher_v2_harness")
    worker_role = f"researcher_{expert_id}"
    prompt = inject_layer2_constraints(base_prompt, worker_role, {})

    # 替换模板占位符(修复 P2-001:替换所有占位符)
    prompt = prompt.replace("{{ expert.angle }}", angle)
    prompt = prompt.replace("{{ expert.reason }}", reason)
    prompt = prompt.replace("{{ topic }}", topic)
    prompt = prompt.replace("{{ constraints }}", json.dumps({}, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{{ expert_id }}", expert_id)
    # BlackboardManager API injected via prompt template
    prompt = prompt.replace("{{ solution_type }}", context.get("type", "architecture"))
    prompt = prompt.replace("{{ mode }}", context.get("mode", "standard"))
    prompt = prompt.replace("{{ stage_name }}", f"research_expert_{expert_id}")

    context_json = json.dumps(context, ensure_ascii=False, indent=2)

    # Living Spec 上下文注入:全局理解 + focus_areas + guardrails
    living_spec_context = ""
    if living_spec:
        # P4: 注入 executive_summary(Core + Functional 组)
        confirmed = living_spec.get("confirmed", {})
        if confirmed:
            objective = confirmed.get("objective", topic)
            one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
            pain_points = confirmed.get("pain_points", [])[:3]
            users = confirmed.get("users", [])[:3]
            always_do = confirmed.get("capabilities", {}).get("always_do", [])[:3]

            living_spec_context += f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**为什么做(痛点)**:
{chr(10).join([f"- {p}" for p in pain_points]) if pain_points else "- 未指定"}

**为谁做(用户)**:
{chr(10).join([f"- {u.get('role','')}: {u.get('key_needs','')}" if isinstance(u, dict) else f"- {u}" for u in users]) if users else "- 未指定"}

**必须做的事(核心功能)**:
{chr(10).join([f"- {c}" for c in always_do]) if always_do else "- 未指定"}

## 你的角色相关需求分组(Research Expert: Core + Functional)

"""
        # 原有 focus_areas + guardrails 注入
        hints = living_spec.get("solution_pro_hints") or {}
        focus_areas = hints.get("focus_areas", [])
        guardrails = living_spec.get("guardrails", {})
        if focus_areas:
            fa_lines = "\n".join([f"- **{fa.get('area','')}** (权重 {fa.get('weight',0):.0%}): {fa.get('reason','')}" for fa in focus_areas])
            living_spec_context += f"\n## 重点关注领域(来自 Spec Pro)\n{fa_lines}\n"
        if guardrails:
            always = "\n".join([f"- {i}" for i in guardrails.get("always_do", [])]) or "- 无"
            never = "\n".join([f"- {i}" for i in guardrails.get("never_do", [])]) or "- 无"
            living_spec_context += f"\n## 研究边界\n**必须研究**:\n{always}\n**禁止涉及**:\n{never}\n"

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
{living_spec_context}
## 输出要求(子Agent直接写入模式)
1. 使用 **write** 工具将结果写入:
   `bb.write_stage(f"research_{expert_id}", {...})`
2. 写入前确保目录存在(必要时创建)
3. 写入格式为JSON,包含以下字段:
   ```json
   {{
     "status": "completed",
     "stage": "research_expert_{expert_id}",
     "session_id": "{session_id}",
     "timestamp": "<ISO8601>",
     "data": {{
       "expert_id": "{expert_id}",
       "angle": "...",
       "findings": {{...}},
       "conclusions": [...]
     }},
   }}
   ```
4. 在最终回复中确认:✅ 结果已写入 `bb.write_stage(f"research_{expert_id}", {...})`
"""
    final_prompt = prompt + "\n" + ctx

    # S4: 注入 Spec Pro 上下文(user_directives, inferred_pending 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "researcher")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


def build_designer_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Designer Task(修复 P1-003: 明确前置输入文件)"""
    prompt = read_prompt("solution/designer")
    context_json = json.dumps(context, ensure_ascii=False, indent=2)

    ctx = f"""
## 设计主题
{topic}

## 上下文
{context_json}

## 前置输入(必须读取)
1. 规划阶段: bb.read_stage("planning")
2. 研究结果:
   - bb.read_stage("research_expert_1")
   - bb.read_stage("research_expert_2")
   - bb.read_stage("research_expert_3")
3. 数据收集: bb.read_stage("data_collection")

## 输出要求(子Agent直接写入模式)
1. 使用 **write** 工具将结果写入:
   `bb.write_stage("design", {...})`
2. 写入前确保目录存在(必要时创建)
3. 写入格式为JSON,包含以下字段:
   ```json
   {{
     "status": "completed",
     "stage": "design",
     "session_id": "{session_id}",
     "timestamp": "<ISO8601>",
     "data": {{
       "architecture": "...",
       "components": [...],
       "interfaces": [...],
       "data_model": {{...}}
     }}
   }}
   ```
4. 在最终回复中确认:✅ 结果已写入 `bb.write_stage("design", {...})`
"""
    return prompt + "\n" + ctx


def build_auditor_task(session_id: str, topic: str, context: dict,
                       living_spec: dict = None) -> str:
    """构建 Auditor Task(Stage 6,Harness V2)

    Args:
        living_spec: Living Spec(Spec Pro 产出,可选)
    """
    # 读取基础Prompt并注入Layer 2约束(使用默认)
    base_prompt = read_prompt("solution/auditor_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "auditor", {})
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    prompt = prompt.replace("{{ TOPIC }}", topic)
    prompt = prompt.replace("{{ SOLUTION_TYPE }}", context.get("type", "architecture"))
    prompt = prompt.replace("{{ CONSTRAINTS }}", json.dumps(context.get("constraints", {}), ensure_ascii=False, indent=2))

    # Living Spec 上下文注入:全局理解
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]
        objective = confirmed.get("objective", "未指定")
        one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
        pain_points = confirmed.get("pain_points", [])[:3]
        users = confirmed.get("users", [])[:3]
        always_do = confirmed.get("capabilities", {}).get("always_do", [])[:3]

        living_spec_context = f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**为什么做(痛点)**:
{chr(10).join([f"- {p}" for p in pain_points]) if pain_points else "- 未指定"}

**为谁做(用户)**:
{chr(10).join([f"- {u.get('role','')}: {u.get('key_needs','')}" if isinstance(u, dict) else f"- {u}" for u in users]) if users else "- 未指定"}

**必须做的事(核心功能)**:
{chr(10).join([f"- {c}" for c in always_do]) if always_do else "- 未指定"}

## 你的角色相关需求分组(Auditor: Boundaries + NonFunctional)

**审计要求**: 检查方案是否违反行为边界,质量属性是否达标。
"""

    ctx = f"""
## 审计主题
{topic}

## 上下文
{context_json}
{living_spec_context}
## 输出要求(子Agent直接写入模式)
1. 使用 **write** 工具将结果写入:
   `bb.write_stage("audit", {...})`
2. 写入前确保目录存在(必要时创建)
3. 写入格式为JSON,包含以下字段:
   ```json
   {{
     "status": "completed",
     "stage": "audit",
     "session_id": "{session_id}",
	     "timestamp": "<ISO8601>",
	     "data": {{
	       "audit_findings": [{{"id": "AUD-001", "severity": "critical|major|minor|info", "level": "P0|P1|P2|INFO", "description": "..."}}],
	       "issues": [{{"id": "AUD-001", "severity": "critical|major|minor|info", "level": "P0|P1|P2|INFO", "description": "..."}}],
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
5. 在最终回复中确认:✅ 结果已写入 `bb.write_stage("audit", {...})`
"""
    final_prompt = prompt + "\n" + ctx

    # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "auditor")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


def build_fixer_task(session_id: str, topic: str, context: dict,
                     living_spec: dict = None) -> str:
    """
    @deprecated - Use build_fixer_task_with_audit() instead.
    This function is kept for backward compatibility but is no longer
    used by the 10-stage pipeline.
    """
    # 读取基础Prompt并注入Layer 2约束(使用默认)
    base_prompt = read_prompt("solution/fixer_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "fixer", {})
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    prompt = prompt.replace("{{ TOPIC }}", topic)
    # AUDIT_PATH replaced with bb.read_stage("audit") guide

    # Living Spec 上下文注入:全局理解
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]
        objective = confirmed.get("objective", "未指定")
        one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
        never_do = confirmed.get("capabilities", {}).get("never_do", [])[:3]

        living_spec_context = f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**禁止做的事(修复边界)**:
{chr(10).join([f"- {c}" for c in never_do]) if never_do else "- 未指定"}

**修复要求**: 修复方案不能违反上述边界约束,修复后仍需满足核心目标。
"""

    ctx = f"""
## 修复主题
{topic}

## 问题清单
{context_json}
{living_spec_context}
## 输出要求(子Agent直接写入模式)
1. 使用 **write** 工具将结果写入:
   `bb.write_stage("fix", {...})`
2. 写入前确保目录存在(必要时创建)
3. 写入格式为JSON,包含以下字段:
   ```json
   {{
     "status": "completed",
     "stage": "fix",
     "session_id": "{session_id}",
     "timestamp": "<ISO8601>",
     "data": {{
       "fixes": [{{"priority": "P0", "issue": "...", "fix": "..."}}],
       "verification_plan": "..."
     }}
   }}
   ```
4. 在最终回复中确认:✅ 结果已写入 `bb.write_stage("fix", {...})`
"""
    final_prompt = prompt + "\n" + ctx

    # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "fixer")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


def build_fixer_task_with_audit(session_id: str, topic: str, audit_path: str, living_spec: dict = None) -> str:
    """构建 Fixer Task,从 audit.json 读取问题清单(P0 Fix + P3-002 fallback)"""
    # Living Spec 上下文注入:全局理解
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]
        objective = confirmed.get("objective", "未指定")
        one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
        never_do = confirmed.get("capabilities", {}).get("never_do", [])[:3]

        living_spec_context = f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**禁止做的事(修复边界)**:
{chr(10).join([f"- {c}" for c in never_do]) if never_do else "- 未指定"}

**修复要求**: 修复方案不能违反上述边界约束,修复后仍需满足核心目标。
"""

    # Phase 2: 尝试从文件读取prompt(优先),失败则使用硬编码兜底
    try:
        prompt = read_prompt("solution/fixer_v2_harness")
        # 替换模板变量
        prompt = prompt.replace("{{TOPIC}}", topic)
        prompt = prompt.replace("{{ TOPIC }}", topic)
        prompt = prompt.replace("{{AUDIT_PATH}}", audit_path)
        prompt = prompt.replace("{{ AUDIT_PATH }}", audit_path)
        # DEEPFLOW_BASE from PathConfig base_dir
        prompt = prompt.replace("{{ DEEPFLOW_BASE }}", str(PathConfig.resolve().base_dir))
        prompt = prompt.replace("{{SESSION_ID}}", session_id)
        prompt = prompt.replace("{{ SESSION_ID }}", session_id)
        final_prompt = prompt + "\n" + living_spec_context
        # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
        if living_spec:
            spec_ctx = build_worker_context_section(living_spec, "fixer")
            if spec_ctx:
                final_prompt += "\n\n" + spec_ctx
        return final_prompt
    except FileNotFoundError as e:
        logger.debug(f"fixer audit: {e}")  # 向后兼容:硬编码兜底

    return f"""你是 Solution 修复 Agent。

## 任务
基于审计报告修复方案中的问题。

## 主题
{topic}

## 审计报告位置
{audit_path}
{living_spec_context}
## 执行步骤
1. 尝试读取审计报告 {audit_path}
2. 如果文件不存在或无法读取:
   - 输出警告:"Audit report not found, using default fixes"
   - 基于常见最佳实践生成通用修复建议
3. 如果读取成功:
   - 提取所有 P0/P1/P2 级别问题
   - 为每个问题制定修复方案
4. 按优先级排序修复项
5. 使用 **write** 工具将修复方案写入:
   `bb.write_stage("fix", {...})`
6. 在最终回复中确认:✅ 修复方案已写入 `bb.write_stage("fix", {...})`

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
  "notes": "备注信息(如使用了默认修复)"
}}
```

## Fallback 机制(P3-002)
- 如果 audit.json 不存在,使用以下默认修复:
  1. 检查设计文档完整性
  2. 验证约束条件是否满足
  3. 确认技术选型合理性
- 在 notes 中标注使用了 fallback 修复
- 每个修复必须有明确的验证方法

## 失败处理
- 如果 write 工具报错,立即报告错误
- 如果文件写入后 read 验证失败,重试最多 3 次
"""


def build_deliver_task(session_id: str, topic: str, context: dict) -> str:
    """构建 Deliver Task(修复 P1-002, P2-003: 使用专门交付模板,与 design 区分)"""
    # Phase 2: 尝试从文件读取prompt(优先),失败则使用硬编码兜底
    try:
        prompt = read_prompt("solution/deliver")
    except FileNotFoundError:
        # 向后兼容:硬编码兜底
        prompt = """# Solution Deliver Agent Prompt
# 角色:交付专家
# 目标:整合所有研究成果,产出最终交付文档

## 角色定义
你是 DeepFlow 解决方案设计系统的交付专家。你的任务是将所有研究成果、架构设计、审计修复整合成一份专业、完整的解决方案交付文档。

## 核心职责
- 整合前期所有阶段输出(planning, research, design, audit, fix)
- 确保文档结构完整、逻辑清晰
- 统一术语和格式
- 生成可直接交付的 Markdown 文档

## 输出标准
### 必须包含的章节
1. 执行摘要(1页以内)
2. 项目背景与目标
3. 需求分析总结
4. 解决方案概述
5. 详细架构设计
6. 技术选型与理由
7. 实施路线图
8. 风险评估与缓解
9. 附录(参考资料、术语表)

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

## 前置输入(必须读取)
1. 设计方案: bb.read_stage("design")
2. 审计报告: bb.read_stage("audit")
3. 修复记录: bb.read_stage("fix")

## 输出要求(子Agent直接写入模式)
1. 使用 **write** 工具将结果写入:
   `bb.write_stage("deliver", {...})`
2. 写入前确保目录存在(必要时创建)
3. 写入格式为JSON,包含以下字段:
   ```json
   {{
     "status": "completed",
     "stage": "deliver",
     "session_id": "{session_id}",
     "timestamp": "<ISO8601>",
     "data": {{
       "executive_summary": "...",
       "solution_overview": "...",
       "technical_spec": "...",
       "implementation_plan": "...",
       "risk_assessment": "..."
     }}
   }}
   ```
4. 在最终回复中确认:✅ 结果已写入 `bb.write_stage("deliver", {...})`
"""
    return prompt + "\n" + ctx


# ============================================================
# Stage 2: Reviewers ×3(并行评审)
# ============================================================

def build_reviewer_task(session_id: str, topic: str, review_type: str,
                        review_focus: str, input_plan: dict,
                        living_spec: dict = None) -> str:
    """构建 Reviewer Task(Stage 3,Harness V2)

    Args:
        session_id: Session ID
        topic: 评审主题
        review_type: 评审类型(technical/business/risk)
        review_focus: 评审焦点描述
        input_plan: Planner生成的执行计划
        living_spec: Living Spec(Spec Pro 产出,可选)
    """
    # 读取基础 Prompt 后注入 Layer 2 约束(使用默认)
    base_prompt = read_prompt("solution/reviewer_v2_harness")
    worker_role = f"reviewer_{review_type}"
    prompt = inject_layer2_constraints(base_prompt, worker_role, {})

    # 替换模板变量
    constraints_text = json.dumps({}, ensure_ascii=False, indent=2)
    prompt = prompt.replace("{{ review_type }}", review_type)
    prompt = prompt.replace("{{ review_focus }}", review_focus)
    prompt = prompt.replace("{{ input_plan }}", json.dumps(input_plan, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{{ constraints }}", constraints_text)
    prompt = prompt.replace("{{ stage_name }}", f"reviewer_{review_type}")

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

    # Living Spec 上下文注入:评审基准
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]

        # P4: 注入 executive_summary(指针 + 上下文)
        objective = confirmed.get("objective", topic)
        one_liner = objective if len(objective) <= 50 else objective[:47] + "..."

        living_spec_context += f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**为什么做(痛点)**:
{chr(10).join([f"- {p}" for p in confirmed.get("pain_points", [])[:3]]) if confirmed.get("pain_points") else "- 未指定"}

**为谁做(用户)**:
{chr(10).join([f"- {u.get('role','')}: {u.get('key_needs','')}" if isinstance(u, dict) else f"- {u}" for u in confirmed.get("users", [])[:3]]) if confirmed.get("users") else "- 未指定"}

**做对的标准(成功指标)**:
{chr(10).join([f"- {m.get('metric','')}: {m.get('target','')}" if isinstance(m, dict) else f"- {m}" for m in confirmed.get("success_metrics", [])[:5]]) if confirmed.get("success_metrics") else "- 未指定"}

"""

        # P4: 按评审类型裁剪分组
        if review_type == "technical":
            living_spec_context += """## 你的角色相关需求分组(Reviewer Technical: Functional + NonFunctional)

"""
        elif review_type == "business":
            living_spec_context += """## 你的角色相关需求分组(Reviewer Business: Core + Context)

"""
        else:  # risk
            living_spec_context += """## 你的角色相关需求分组(Reviewer Risk: Boundaries + Context)

"""

        objective = confirmed.get("objective", "未指定")
        always_do = ", ".join(confirmed.get("capabilities", {}).get("always_do", [])) or "未指定"
        should_do = ", ".join(confirmed.get("capabilities", {}).get("should_do", [])) or "未指定"
        never_do = ", ".join(confirmed.get("capabilities", {}).get("never_do", [])) or "未指定"
        qa_text = "\n".join([f"- {q.get('category','')}: {q.get('spec','')}" for q in confirmed.get("quality_attributes", [])]) or "- 未指定"
        budget = confirmed.get("constraints", {}).get("budget", "未指定")
        timeline = confirmed.get("constraints", {}).get("timeline", "未指定")
        living_spec_context += f"""
## 评审基准(来自 Spec Pro - 用户确认的需求)

你的评审必须基于以下**用户已确认的需求**,而不是自己的假设:

### 核心目标
{objective}

### 能力要求
**必须做**: {always_do}
**应该做**: {should_do}
**禁止做**: {never_do}

### 质量属性
{qa_text}

### 约束条件
- 预算: {budget}
- 时间: {timeline}

**评审要求**: 检查方案是否满足以上用户确认的需求,而不是泛泛评估。
"""

    ctx = f"""
## 评审主题
{topic}

## 输入计划
{input_plan_json}
{living_spec_context}
## Blackboard路径
BlackboardManager(session_id="{session_id}").get_blackboard_path()
"""
    final_prompt = prompt + "\n" + ctx

    # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, f"reviewer_{review_type}")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


# ============================================================
# Stage 2, 5, 9: Harness V2(统一4维质量检查)
# ============================================================

def build_harness_v2_task(session_id: str, topic: str, worker_role: str,
                          layer2_constraints: list = None) -> str:
    """构建 Harness V2 Task(通用Worker自评)

    Args:
        session_id: Session ID
        topic: 任务主题
        worker_role: Worker角色(planner/reviewer/researcher/...)
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
    # _DEEPFLOW_BASE from PathConfig base_dir

    return prompt


def build_harness_final_task(session_id: str, topic: str, living_spec: dict = None) -> str:
    """构建 Harness Final Task(Stage 9,独立门禁)

    Args:
        session_id: Session ID
        topic: 任务主题
        living_spec: Living Spec(Spec Pro 产出,可选)

    职责:
    - 统一4维评分(完整性/必要性/目标一致性/全局影响)
    - 跨阶段一致性检查
    - 生成Summarizer必须响应的意见清单
    """
    from core.prompt_registry import read_prompt

    prompt = read_prompt("solution/harness_v3")
    harness_scoring = read_prompt("solution/harness_scoring")

    # 注入输入文件路径
    # BlackboardManager API injected via prompt template
    prompt = prompt.replace("{topic}", topic)
    prompt = prompt.replace("{session_id}", session_id)

    # P0-4 修复: 补全 harness_v3.md 模板变量替换
    prompt = prompt.replace("{{ stage_number }}", "9")
    prompt = prompt.replace("{{ stage_suffix }}", "_final")
    prompt = prompt.replace("{{ check_type }}", "最终质量检查")
    prompt = prompt.replace("{{ harness_scoring }}", harness_scoring)
    prompt = prompt.replace("{{ final_check_instructions }}", """
## 最终检查特殊要求
- 对比之前各阶段的评分,评估改进效果
- 确认所有 Critical 问题已解决
- 给出最终通过/阻断决策
- 验证 Worker 自检诚实性(如 Worker 自评 green 但实际 red,则标记)""")
    prompt = prompt.replace("{{ input_stage }}", "consolidator")
    prompt = prompt.replace("{{ completeness_items }}", """
1. 容错机制: 是否有故障处理和恢复策略
2. 数据流: 数据流向是否清晰,无断点
3. 测试策略: 是否有单元测试、集成测试、压力测试计划
4. 监控运维: 是否有监控、告警、日志、运维方案
5. 成本估算: 是否有详细的 CAPEX 和 OPEX 估算
6. 文档完整性: 设计文档、API文档、运维文档是否齐全""")
    prompt = prompt.replace("{{ necessity_items }}", """
1. 避免过度设计: 技术选型是否与业务规模匹配
2. 避免过度审计: 审计深度是否与风险等级匹配
3. 贴合实际场景: 是否考虑实际约束(预算、周期、团队)
4. 现实可行: 技术是否可实现,团队是否有能力
5. 约束匹配: 所有 constraints 是否有对应方案""")
    prompt = prompt.replace("{{ alignment_items }}", """
1. 原始目标: 最终方案是否直接服务于用户目标
2. confirmed 需求: 是否覆盖 Spec Pro confirmed 层的关键能力
3. 阶段一致性: 研究、整合、审计、修复结论是否前后一致
4. 决策理由: 关键技术/业务决策是否有清晰依据""")
    prompt = prompt.replace("{{ global_impact_items }}", """
1. 成本影响: 是否说明 CAPEX/OPEX、资源投入和维护成本
2. 风险影响: 是否识别关键技术、业务、合规和交付风险
3. 集成影响: 是否考虑现有系统、数据迁移和接口依赖
4. 运营影响: 是否考虑监控、告警、运维、团队能力和长期演进""")

    # Living Spec 上下文注入:基于 confirmed 评估覆盖度
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]

        # P4: 提取全局理解字段(why/for_whom/success_criteria)
        always_do = "\n".join([f"- {c}" for c in confirmed.get("capabilities", {}).get("always_do", [])]) or "- 无"
        qa_text = "\n".join([f"- {q.get('category','')}: {q.get('spec','')}" for q in confirmed.get("quality_attributes", [])]) or "- 无"
        budget = confirmed.get("constraints", {}).get("budget", "未指定")
        timeline = confirmed.get("constraints", {}).get("timeline", "未指定")
        tech_stack = ", ".join(confirmed.get("constraints", {}).get("tech_stack", [])) or "未指定"

        why = "\n".join([f"- {p}" for p in confirmed.get("pain_points", [])]) or "- 未指定"
        for_whom = "\n".join([f"- {u.get('role','')}: {u.get('key_needs','')}" if isinstance(u, dict) else f"- {u}" for u in confirmed.get("users", [])]) or "- 未指定"
        success_criteria = "\n".join([f"- {m.get('metric','')}: {m.get('target','')}" for m in confirmed.get("success_metrics", [])]) or "- 未指定"

        living_spec_context = f"""
## 需求覆盖度评估基准(来自 Spec Pro)

最终方案必须覆盖以下**用户已确认的需求**:

### 必须覆盖的能力
{always_do}

### 必须满足的质量属性
{qa_text}

### 必须遵守的约束
- 预算: {budget}
- 时间: {timeline}
- 技术栈: {tech_stack}

## 全局理解一致性验证(来自 executive_summary)

最终方案必须回应用户的核心诉求。请验证以下三个维度:

### 1. 方案是否回应了核心痛点?
用户的核心痛点:
{why}

**验证要求**: 方案必须明确说明如何解决这些痛点,而不是泛泛而谈。

### 2. 方案是否满足目标用户需求?
目标用户及其关键需求:
{for_whom}

**验证要求**: 方案必须体现对这些用户需求的理解,并提供针对性解决方案。

### 3. 方案是否达成成功指标?
用户定义的成功指标:
{success_criteria}

**验证要求**: 方案必须说明如何达成这些指标,并提供可衡量的证据。

**评估要求**:
1. 检查最终方案是否覆盖了以上所有需求
2. 对每个未覆盖的需求,标注【缺失:REQ-XXX-原因】
3. 检查全局理解一致性:方案是否真正理解并回应了用户的核心诉求
4. 如果方案只是"正确"但缺乏"灵魂"(没有回应痛点/用户/指标),标注【缺乏全局理解】
5. 需求覆盖度评分 = 已覆盖需求数 / 总需求数

**输出要求**: 在输出 JSON 中新增 `global_understanding_check` 字段:
```json
{{
  "global_understanding_check": {{
    "why_alignment": "aligned|partial|misaligned",
    "for_whom_alignment": "aligned|partial|misaligned",
    "success_criteria_alignment": "aligned|partial|misaligned",
    "evidence": "说明判断依据"
  }}
}}
```
"""

    final_prompt = prompt + living_spec_context

    # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "harness_final")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


# 保留兼容入口:内部也统一走4维 Harness V3
def build_harness_task(session_id: str, topic: str, current_solution: dict,
                       is_final: bool = False) -> str:
    """构建 Harness V3 Task(兼容入口,统一4维评分)

    Args:
        session_id: Session ID
        topic: 检查主题
        current_solution: 当前方案内容
        is_final: 是否为最终检查(Stage 7.5)
    """
    prompt = read_prompt("solution/harness_v3")
    harness_scoring = read_prompt("solution/harness_scoring")

    # 设置阶段相关变量
    if is_final:
        stage_number = "7.5"
        stage_suffix = "_final"
        check_type = "最终质量检查"
        final_instructions = """
## 最终检查特殊要求
- 对比Stage 3.5的评分,评估改进效果
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
2. 数据流: 数据流向是否清晰,有无断点
3. 测试策略: 是否有单元/集成/压力测试计划
4. 监控运维: 是否有监控、告警、日志方案
5. 成本估算: 是否有详细的CAPEX和OPEX估算
6. 文档完整性: 设计/API/运维文档是否齐全"""

    necessity_items = """
1. 避免过度设计: 技术选型是否与业务规模匹配
2. 避免过度审计: 审计深度是否与风险等级匹配
3. 贴合实际场景: 是否考虑实际约束(预算/周期/团队)
4. 现实可行: 技术是否可实现,团队是否有能力
5. 约束匹配: 所有constraints是否都有对应方案"""

    alignment_items = """
1. 原始目标: 方案是否直接服务于用户目标
2. 需求覆盖: 是否覆盖关键能力与质量属性
3. 阶段一致: 各阶段结论是否前后一致
4. 决策依据: 关键决策是否有明确理由"""

    global_impact_items = """
1. 成本影响: 是否说明建设、维护和资源投入
2. 风险影响: 是否识别技术、业务、合规和交付风险
3. 集成影响: 是否考虑现有系统、迁移和接口依赖
4. 运营影响: 是否考虑监控、告警、运维和长期演进"""

    prompt = prompt.replace("{{ harness_scoring }}", harness_scoring)
    prompt = prompt.replace("{{ completeness_items }}", completeness_items)
    prompt = prompt.replace("{{ necessity_items }}", necessity_items)
    prompt = prompt.replace("{{ alignment_items }}", alignment_items)
    prompt = prompt.replace("{{ global_impact_items }}", global_impact_items)
    # BlackboardManager API injected via prompt template
    prompt = prompt.replace("{topic}", topic)
    prompt = prompt.replace("{session_id}", session_id)

    solution_json = json.dumps(current_solution, ensure_ascii=False, indent=2)

    ctx = f"""
## 检查主题
{topic}

## 当前方案
{solution_json}

## Blackboard路径
BlackboardManager(session_id="{session_id}").get_blackboard_path()
"""
    return prompt + "\n" + ctx


# ============================================================
# Stage 5: Consolidator(成果整合)
# ============================================================

def build_consolidator_task(session_id: str, topic: str,
                            research_outputs: list,
                            living_spec: dict = None) -> str:
    """构建 Consolidator Task(Stage 5,Harness V2内嵌检查)

    Args:
        session_id: Session ID
        topic: 整合主题
        research_outputs: 所有Researcher的输出列表
        layer2_constraints: Layer 2场景约束(Orchestrator集成)
        living_spec: Living Spec(Spec Pro 产出,可选)
    """
    # 读取基础Prompt并注入Layer 2约束(使用默认)
    base_prompt = read_prompt("solution/consolidator_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "consolidator", {})

    # 整合策略
    integration_strategy = """
1. 技术选型:基于业务场景和团队能力选择,参考主流方案
2. 成本估算:取各researcher估算的加权平均
3. 时间规划:考虑最悲观的researcher估计
4. 风险整合:合并所有识别的风险,去重"""

    # 序列化研究输出
    outputs_json = json.dumps(research_outputs, ensure_ascii=False, indent=2)

    prompt = prompt.replace("{{ research_outputs }}", outputs_json)
    prompt = prompt.replace("{{ integration_strategy }}", integration_strategy)
    prompt = prompt.replace("{{ topic }}", topic)
    prompt = prompt.replace("{{ quality_requirements }}", "{}")

    # Living Spec 上下文注入:全局理解(全部5个分组)
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]
        objective = confirmed.get("objective", topic)
        one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
        pain_points = confirmed.get("pain_points", [])[:3]
        users = confirmed.get("users", [])[:3]
        success_metrics = confirmed.get("success_metrics", [])[:5]
        always_do = confirmed.get("capabilities", {}).get("always_do", [])[:3]
        never_do = confirmed.get("capabilities", {}).get("never_do", [])[:3]

        living_spec_context = f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**为什么做(痛点)**:
{chr(10).join([f"- {p}" for p in pain_points]) if pain_points else "- 未指定"}

**为谁做(用户)**:
{chr(10).join([f"- {u.get('role','')}: {u.get('key_needs','')}" if isinstance(u, dict) else f"- {u}" for u in users]) if users else "- 未指定"}

**做对的标准(成功指标)**:
{chr(10).join([f"- {m.get('metric','')}: {m.get('target','')}" if isinstance(m, dict) else f"- {m}" for m in success_metrics]) if success_metrics else "- 未指定"}

**必须做的事**:
{chr(10).join([f"- {c}" for c in always_do]) if always_do else "- 未指定"}

**禁止做的事**:
{chr(10).join([f"- {c}" for c in never_do]) if never_do else "- 未指定"}

## 你的角色相关需求分组(Consolidator: 全部 5 个分组)

**整合要求**: 整合方案必须回应全局理解中的痛点和成功指标,不能只是"正确"但缺乏"灵魂"。
"""

    ctx = f"""
## 整合主题
{topic}

## 前置输入(必须读取)
以下是 Stage 4 Researcher 输出文件清单。请逐个读取, 不要只使用内联摘要:
{outputs_json}

读取失败时, 必须在 `data.missing_research_outputs` 中记录缺失路径, 并在 Harness 自评中降低完整性评分。

## Blackboard路径
BlackboardManager(session_id="{session_id}").get_blackboard_path()
{living_spec_context}
"""
    final_prompt = prompt + "\n" + ctx

    # S4: 注入 Spec Pro 上下文(user_directives, inferred_pending 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "consolidator")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


# ============================================================
# Stage 7: Fixer Expert(深度修正)
# ============================================================

def build_fixer_expert_task(session_id: str, topic: str,
                            audit_findings: list, severity: str,
                            living_spec: dict = None) -> str:
    """构建 Fixer Expert Task(Stage 8,Harness V2深度修正)

    Args:
        session_id: Session ID
        topic: 修正主题
        audit_findings: Auditor发现的问题列表
        severity: 严重性级别(critical/major/minor)
        living_spec: Living Spec(Spec Pro 产出,可选)
    """
    # 读取基础Prompt并注入Layer 2约束(使用默认)
    base_prompt = read_prompt("solution/fixer_expert_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "fixer_expert", {})

    # 根据严重性确定修正策略
    if severity == "critical":
        fix_strategy = """
### Critical级别修正策略
1. 必须修正,否则方案不可行
2. 可能需要重新设计核心模块
3. 重新评估项目可行性
4. 更新所有相关文档"""
    elif severity == "major":
        fix_strategy = """
### Major级别修正策略
1. 强烈建议修正,显著影响质量
2. 需要调整设计或策略
3. 评估对成本/时间的影响
4. 确保修正不引入新问题"""
    else:  # minor
        fix_strategy = """
### Minor级别修正策略
1. 可选修正,优化细节
2. 不影响整体可行性
3. 文档描述更清晰
4. 低优先级处理"""

    prompt = prompt.replace("{{ severity }}", severity)
    prompt = prompt.replace("{{ SEVERITY }}", severity)
    prompt = prompt.replace("{{ TOPIC }}", topic)
    prompt = prompt.replace("{{ fix_strategy }}", fix_strategy)

    findings_json = json.dumps(audit_findings, ensure_ascii=False, indent=2)
    prompt = prompt.replace("{{ audit_findings }}", findings_json)
    prompt = prompt.replace("{{ AUDIT_FINDINGS }}", findings_json)

    # Living Spec 上下文注入:全局理解
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]
        objective = confirmed.get("objective", "未指定")
        one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
        never_do = confirmed.get("capabilities", {}).get("never_do", [])[:3]

        living_spec_context = f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**禁止做的事(修复边界)**:
{chr(10).join([f"- {c}" for c in never_do]) if never_do else "- 未指定"}

**修复要求**: 修复方案不能违反上述边界约束,修复后仍需满足核心目标。
"""

    ctx = f"""
## 修正主题
{topic}

## 前置输入(必须读取)
以下是审计与初步修复输入。请优先读取文件内容, 并以其中的 P0/critical 问题作为深度修复对象:
{findings_json}

如果审计文件不存在、没有 P0/critical 问题, 或初步修复已经解决全部关键问题, 必须在输出 `data.summary.overall_assessment` 和 `harness_check.reasoning` 中说明依据。

## Blackboard路径
BlackboardManager(session_id="{session_id}").get_blackboard_path()
{living_spec_context}
"""
    final_prompt = prompt + "\n" + ctx

    # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "fixer_expert")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt


# ============================================================
# Stage 8: Summarizer(最终总结)
# ============================================================

def build_summarizer_task(session_id: str, topic: str,
                          all_outputs: dict,
                          living_spec: dict = None) -> str:
    """构建 Summarizer Task(Stage 10,Harness V2最终总结)

    Args:
        session_id: Session ID
        topic: 总结主题
        all_outputs: 所有stage的输出字典
        living_spec: Living Spec(Spec Pro 产出,可选)
    """
    # 读取基础Prompt并注入Layer 2约束(使用默认)
    base_prompt = read_prompt("solution/summarizer_v2_harness")
    prompt = inject_layer2_constraints(base_prompt, "summarizer", {})

    # 提取关键信息生成summary
    solution_summary = f"""
### 方案概述
本方案针对"{topic}",通过8阶段深度分析与优化,形成了完整的技术与实施规划。

### 核心亮点
- 经过多维度评审和审计,质量达到高标准
- 技术选型与业务需求精准匹配
- 风险控制完善,实施路径清晰
"""

    key_recommendations = [
        "优先实施高价值低风险的模块",
        "建立完善的监控和告警体系",
        "分阶段上线,控制风险暴露",
        "定期进行架构评审和技术债务清理"
    ]

    all_outputs_json = json.dumps(all_outputs, ensure_ascii=False, indent=2)

    prompt = prompt.replace("{{ stage_name }}", "summarizer")
    prompt = prompt.replace("{{ all_outputs }}", all_outputs_json)
    prompt = prompt.replace("{{ solution_summary }}", solution_summary)
    prompt = prompt.replace("{{ key_recommendations }}",
                           "\n".join([f"{i+1}. {r}" for i, r in enumerate(key_recommendations)]))

    # Living Spec 上下文注入:全局理解 + 需求覆盖标注
    living_spec_context = ""
    if living_spec and "confirmed" in living_spec:
        confirmed = living_spec["confirmed"]

        # 全局理解部分(与其他 worker 一致)
        objective = confirmed.get("objective", topic)
        one_liner = objective if len(objective) <= 80 else objective[:77] + "..."

        pain_points = confirmed.get("pain_points", [])
        pain_points_str = "\n".join([f"- {p}" for p in pain_points]) if pain_points else "- 未指定"

        users = confirmed.get("users", [])
        users_str = "\n".join([f"- {u.get('role', '未知')}: {u.get('key_needs', '未知')}" if isinstance(u, dict) else f"- {u}" for u in users]) if users else "- 未指定"

        success_metrics = confirmed.get("success_metrics", [])
        success_metrics_str = "\n".join([f"- {m.get('metric', '未知')}: {m.get('target', '未知')}" if isinstance(m, dict) else f"- {m}" for m in success_metrics]) if success_metrics else "- 未指定"

        constraints = confirmed.get("constraints", {})
        constraints_str = "\n".join([f"- {k}: {v}" for k, v in constraints.items()]) if constraints else "- 未指定"

        # 需求覆盖标注部分
        always_do = "\n".join([f"- {c}" for c in confirmed.get("capabilities", {}).get("always_do", [])]) or "- 无"
        qa_text = "\n".join([f"- {q.get('category','')}: {q.get('spec','')}" for q in confirmed.get("quality_attributes", [])]) or "- 无"
        budget = confirmed.get("constraints", {}).get("budget", "未指定")
        timeline = confirmed.get("constraints", {}).get("timeline", "未指定")

        living_spec_context = f"""
## 全局理解(来自 executive_summary)

**一句话概括**: {one_liner}

**为什么做(痛点)**:
{pain_points_str}

**为谁做(用户)**:
{users_str}

**做对的标准(成功指标)**:
{success_metrics_str}

**关键约束**:
{constraints_str}

## 需求覆盖标注要求(来自 Spec Pro)

在最终报告中,必须显式标注以下**用户确认需求**的覆盖情况:

### 必须覆盖的能力
{always_do}

### 必须满足的质量属性
{qa_text}

### 必须遵守的约束
- 预算: {budget}
- 时间: {timeline}

**标注要求**:
1. 对每个已覆盖的需求,标注【已覆盖:REQ-XXX】
2. 对每个未覆盖的需求,标注【缺失:REQ-XXX-原因】
3. 在报告开头添加"需求覆盖度"章节,列出覆盖率
"""

    ctx = f"""
## 总结主题
{topic}
{living_spec_context}
## Blackboard路径
BlackboardManager(session_id="{session_id}").get_blackboard_path()

## 输出文件要求
1. final_result.json - 结构化最终结果(唯一输出文件,包含 covered_req_ids + 完整方案)
"""
    final_prompt = prompt + "\n" + ctx

    # S4: 注入 Spec Pro 上下文(user_directives, solution_pro_hints 等)
    if living_spec:
        spec_ctx = build_worker_context_section(living_spec, "summarizer")
        if spec_ctx:
            final_prompt += "\n\n" + spec_ctx

    return final_prompt
