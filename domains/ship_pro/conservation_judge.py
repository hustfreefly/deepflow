"""
Conservation Judge — 信息守恒裁判（Layer 3 事后审计）

AI Native 契约笼子：
- LLM 做语义判断（不靠字符串匹配，靠理解）
- 代码做格式化（Pydantic 输出 schema + raise ValueError）
- alignment_rate < 0.8 → 触发告警（代码判断，确定性）

使用方式：
  from domains.ship_pro.conservation_judge import run_conservation_judge
  result = run_conservation_judge(semantic_anchors, ship_package, llm_call)
  if result["verdict"] == "FAIL":
      # 处理信息丢失
"""

from typing import Callable, Dict, Any, List
import json
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Judge Prompt（LLM 语义判断）
# ============================================================================

JUDGE_PROMPT = """你是信息守恒裁判（Conservation Judge）。

## 任务

检查以下语义锚点是否在最终产物中被保留。

"保留"的定义：
- 不要求 ID 精确匹配（anchor.name 不需要原样出现在产物中）
- 但必须有**语义等价**表述
- 例如：anchor "sessions_spawn" → 产物中提到 "sub-agents 生成" = 语义等价 ✅
- 例如：anchor "sessions_spawn" → 产物中完全没提及任何相关概念 = ❌ 信息丢失

## 语义锚点（来自上游，不可变）

{anchors_json}

## 最终产物

{output_json}

## 输出格式

输出 JSON：
```json
{{
  "preserved": [
    {{"name": "sessions_spawn", "evidence": "WP CORE-007 描述中提到 Agent Task Dispatcher 使用 sub-agents"}}
  ],
  "lost": [
    {{"name": "BlackboardManager", "severity": "high", "reason": "没有任何 WP 提到共享状态管理的具体机制"}}
  ],
  "alignment_rate": 0.85,
  "verdict": "PASS"
}}
```

verdict 规则：
- alignment_rate >= 0.8 → "PASS"
- alignment_rate >= 0.6 → "CONDITIONAL"
- alignment_rate < 0.6 → "FAIL"

severity 规则：
- "high" — 核心平台能力/架构原则丢失
- "medium" — 外部系统集成丢失
- "low" — 次要技术约束丢失

请逐个检查每个 anchor，输出完整的判断结果。"""


# ============================================================================
# Judge 执行函数
# ============================================================================

def run_conservation_judge(
    semantic_anchors: List[Dict[str, Any]],
    stage_output: Dict[str, Any],
    llm_call: Callable[[str], str],
    min_alignment: float = 0.8,
) -> Dict[str, Any]:
    """
    运行 Conservation Judge 检查信息守恒。
    
    Args:
        semantic_anchors: 上游传递的语义锚点列表
        stage_output: 当前阶段的最终产物（如 ship_package.json 的内容）
        llm_call: LLM 调用函数 (prompt: str) -> str
        min_alignment: 最低对齐率阈值
    
    Returns:
        {
            "preserved": [...],
            "lost": [...],
            "alignment_rate": float,
            "verdict": "PASS" | "CONDITIONAL" | "FAIL",
            "below_threshold": bool  # alignment_rate < min_alignment
        }
    """
    if not semantic_anchors:
        # 契约笼子：空输入 = FAIL，不静默 PASS
        logger.error(
            "契约笼子: semantic_anchors 为空，信息守恒验证 FAIL。\n"
            "  根因: 上游 extract_semantic_anchors() 未被调用，或透传链路断裂。\n"
            "  检查: Spec Pro coordinator.py 是否调用了 extract_semantic_anchors()。"
        )
        return {
            "preserved": [],
            "lost": [],
            "alignment_rate": 0.0,
            "verdict": "FAIL",
            "below_threshold": True,
            "error": "semantic_anchors 为空 — 信息守恒管线断路",
        }
    
    # 1. 构建 Judge prompt
    anchors_json = json.dumps(semantic_anchors, ensure_ascii=False, indent=2)
    # 产物截断防止超长（保留 WPs + statistics）
    output_summary = {
        "work_packages": stage_output.get("work_packages", [])[:10],  # 前 10 个 WP
        "statistics": stage_output.get("statistics", {}),
        "issues": stage_output.get("issues", []),
    }
    output_json = json.dumps(output_summary, ensure_ascii=False, indent=2)
    
    prompt = JUDGE_PROMPT.format(
        anchors_json=anchors_json,
        output_json=output_json[:8000],  # 截断
    )
    
    # 2. LLM 判断
    raw_output = llm_call(prompt)
    
    # 3. 解析结果
    result = _parse_judge_output(raw_output)
    
    # 4. 契约笼子：验证输出格式
    required_keys = {"preserved", "lost", "alignment_rate", "verdict"}
    missing = required_keys - set(result.keys())
    if missing:
        raise ValueError(
            f"契约笼子: Conservation Judge 输出缺少字段: {missing}\n"
            f"原始输出前 500 字: {raw_output[:500]}"
        )
    
    # 5. 阈值检查
    result["below_threshold"] = result["alignment_rate"] < min_alignment
    
    if result["below_threshold"]:
        lost_names = [item.get("name", "?") for item in result["lost"]]
        logger.warning(
            f"信息守恒告警: alignment_rate={result['alignment_rate']:.2f} < {min_alignment}\n"
            f"丢失的 anchors: {lost_names}"
        )
    
    return result


def _parse_judge_output(raw: str) -> Dict[str, Any]:
    """从 LLM 输出中解析 Judge 结果"""
    import re
    
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    
    # 尝试提取 ```json ... ``` 块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 尝试找第一个 { 和最后一个 }
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    
    return {"preserved": [], "lost": [], "alignment_rate": 0.0, "verdict": "FAIL"}

