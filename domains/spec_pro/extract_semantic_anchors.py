"""
Semantic Anchor 提取工具 — Spec Pro 阶段使用

AI Native 契约笼子：
- LLM 做语义提取（从 narrative 识别不可抽象化的具体引用）
- 代码做格式化（Pydantic 验证 + raise ValueError 无 fallback）
- confidence < 0.7 → 标记 needs_review，不自动注入下游

使用方式：
  from domains.spec_pro.extract_semantic_anchors import extract_semantic_anchors
  anchors = extract_semantic_anchors(narrative_text, llm_call_fn)
"""

from typing import Callable, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# 提取 Prompt（LLM 语义理解）
# ============================================================================

EXTRACTION_PROMPT = """你是一个技术约束提取专家。从以下用户需求叙述中，提取所有**不可抽象化的具体技术引用**。

## 什么是 Semantic Anchor？

Semantic Anchor 是在多阶段管线传递中**不应被泛化/抽象化**的具体技术引用。
例如：
- "sessions_spawn" 不应被泛化为 "子 Agent 生成能力"
- "BlackboardManager" 不应被泛化为 "共享状态管理"
- "全LLM控制" 不应被泛化为 "智能决策"

## 提取维度

根据项目性质选择合适的类别。常见类别包括：
- **platform_api** — 具体的平台 API / 工具名（如 sessions_spawn, BlackboardManager）
- **architecture_principle** — 不可妥协的架构原则（如 全LLM控制, 三层Loop架构）
- **external_system** — 必须集成的外部系统（如 OpenClaw, Hermes, Claude）
- **technical_constraint** — 硬性的技术约束（如 8+小时无人干预, 最大6并发）
- **market_segment** / **patent_portfolio** / **regulatory_framework**（投资域）
- **physical_constraint** / **material_spec**（硬件域）
- **business_rule** / **compliance_requirement**（商业域）

也可根据项目需要自定义类别。

## 判断标准

一个引用是 Semantic Anchor 当且仅当：
- ✅ 如果被泛化/抽象化，会导致下游实施者不知道该用什么具体技术
- ✅ 是该项目的独特约束，不是通用软件工程常识
- ❌ "设计优雅"、"代码质量高" — 这些不是 anchor（太抽象，不可操作）

## 输出格式

输出 JSON 数组：
```json
[
  {
    "name": "sessions_spawn",
    "category": "platform_api",
    "constraint": "子 Agent 生成必须使用 sessions_spawn，不能用其他 spawn 机制",
    "source_quote": "技术基础：OpenClaw现有平台能力（sessions_spawn, BlackboardManager...）",
    "confidence": 0.95,
    "applicable_to": ["all"]
  }
]
```

## 用户需求叙述

{narrative}

请提取所有 Semantic Anchors。如果叙述中没有不可抽象化的具体引用，返回空数组 []。"""


# ============================================================================
# 提取函数（代码格式化 + Pydantic 验证）
# ============================================================================

def extract_semantic_anchors(
    narrative: str,
    llm_call: Callable[[str], str],
    min_confidence: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    从 narrative 中提取 semantic anchors。
    
    Args:
        narrative: 用户需求叙述文本
        llm_call: LLM 调用函数 (prompt: str) -> str (返回 JSON 文本)
        min_confidence: 最低置信度阈值，低于此值标记 needs_review
    
    Returns:
        List[Dict] — 通过 Pydantic 验证的 semantic anchors
    
    Raises:
        ValueError: LLM 返回格式不合法且无法解析
    """
    # Import here to avoid circular dependency
    from domains.spec_pro.contracts.living_spec import SemanticAnchor
    
    if not narrative or len(narrative.strip()) < 20:
        logger.warning("narrative 太短，跳过 semantic anchor 提取")
        return []
    
    # 1. LLM 语义提取
    prompt = EXTRACTION_PROMPT.format(narrative=narrative[:5000])  # 截断防止超长
    raw_output = llm_call(prompt)
    
    # 2. 解析 JSON
    anchors_data = _parse_llm_json(raw_output)
    if anchors_data is None:
        raise ValueError(
            f"契约笼子: LLM 返回的 semantic anchors JSON 无法解析。\n"
            f"原始输出前 500 字: {raw_output[:500]}"
        )
    
    if not isinstance(anchors_data, list):
        raise ValueError(
            f"契约笼子: semantic anchors 必须是 JSON 数组，实际: {type(anchors_data).__name__}"
        )
    
    # 3. Pydantic 验证 + 置信度过滤
    validated_anchors = []
    for i, anchor_dict in enumerate(anchors_data):
        try:
            anchor = SemanticAnchor(**anchor_dict)
            
            # 置信度检查
            if anchor.confidence < min_confidence:
                logger.info(
                    f"Semantic anchor '{anchor.name}' confidence={anchor.confidence} "
                    f"< {min_confidence}，标记 needs_review"
                )
                # 不跳过，但标记
                anchor_dict["needs_review"] = True
            
            anchor_dict["needs_review"] = anchor_dict.get("needs_review", False)
            validated_anchors.append(anchor.model_dump())
            
        except Exception as e:
            logger.warning(
                f"semantic_anchors[{i}] Pydantic 验证失败: {e}\n"
                f"原始数据: {json.dumps(anchor_dict, ensure_ascii=False)[:200]}"
            )
            # 契约笼子：不跳过，raise
            raise ValueError(
                f"契约笼子: semantic_anchors[{i}] 验证失败: {e}\n"
                f"原始数据: {json.dumps(anchor_dict, ensure_ascii=False)[:300]}"
            )
    
    logger.info(f"提取了 {len(validated_anchors)} 个 semantic anchors")
    return validated_anchors


def _parse_llm_json(raw: str) -> Any:
    """从 LLM 输出中提取 JSON（处理 markdown 代码块）"""
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
    
    # 尝试找第一个 [ 和最后一个 ]
    start = raw.find('[')
    end = raw.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    
    return None
