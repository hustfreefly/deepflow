"""
Spec Pro Requirement Structuring Worker

触发时机：Spec Pro 收尾阶段（用户确认"需求已完整"后）
输入：living_spec.confirmed（已收集的结构化字段）
输出：living_spec.confirmed.requirement_annotations（LLM标注）

设计原则：
- LLM 只做语义标注（JSON + Schema 验证）
- 脚本负责格式化组装（分配REQ-ID、构建frozen_spec）
- 不替换REQ结构，只增强元数据
"""

import json
import jsonschema
from typing import Dict, Any, List, Optional, Callable
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# JSON Schema 定义（LLM 输出格式验证）
# ============================================================================

ANNOTATION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["original_text", "category", "priority"],
        "properties": {
            "original_text": {
                "type": "string",
                "description": "原始需求文本（用于匹配REQ）"
            },
            "category": {
                "enum": [
                    "core_objective", "capability", "prohibition",
                    "quality_attribute", "constraint", "integration",
                    "pain_point", "success_metric", "user", "scenario",
                    "risk", "assumption"
                ],
                "description": "需求分类"
            },
            "priority": {
                "enum": ["P0", "P1", "P2"],
                "description": "优先级（P0=必须, P1=应该, P2=可以）"
            },
            "dependencies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "依赖的REQ-ID列表（可选）"
            },
            "potential_conflicts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "潜在冲突的REQ-ID列表（可选，标记为potential而非confirmed）"
            },
            "context_note": {
                "type": "string",
                "description": "一句话结构化上下文（不是用户原话，信息密度更高）"
            }
        }
    }
}

# ============================================================================
# Prompt 构建
# ============================================================================

def _build_annotation_prompt(confirmed: Dict[str, Any]) -> str:
    """构建 LLM 标注 prompt"""
    
    # 提取所有需求文本
    req_texts = []
    
    # objective
    if confirmed.get("objective"):
        req_texts.append(f"目标: {confirmed['objective']}")
    
    # pain_points
    for p in confirmed.get("pain_points", []):
        req_texts.append(f"痛点: {p}")
    
    # users
    for u in confirmed.get("users", []):
        if isinstance(u, dict):
            req_texts.append(f"用户: {u.get('role', '')} - {u.get('description', '')}")
        else:
            req_texts.append(f"用户: {u}")
    
    # key_scenarios
    for s in confirmed.get("key_scenarios", []):
        req_texts.append(f"场景: {s}")
    
    # success_metrics
    for m in confirmed.get("success_metrics", []):
        if isinstance(m, dict):
            req_texts.append(f"成功指标: {m.get('metric', '')} - {m.get('target', '')}")
        else:
            req_texts.append(f"成功指标: {m}")
    
    # capabilities
    caps = confirmed.get("capabilities", {})
    for cap in caps.get("always_do", []):
        req_texts.append(f"必须做: {cap}")
    for cap in caps.get("should_do", []):
        req_texts.append(f"应该做: {cap}")
    for cap in caps.get("never_do", []):
        req_texts.append(f"禁止做: {cap}")
    
    # quality_attributes
    for qa in confirmed.get("quality_attributes", []):
        if isinstance(qa, dict):
            req_texts.append(f"质量属性: {qa.get('category', '')} - {qa.get('spec', '')}")
        else:
            req_texts.append(f"质量属性: {qa}")
    
    # constraints
    constraints = confirmed.get("constraints", {})
    if isinstance(constraints, dict):
        for k, v in constraints.items():
            req_texts.append(f"约束: {k} - {v}")
    
    # integration
    integration = confirmed.get("integration", {})
    for req in integration.get("requirements", []):
        req_texts.append(f"集成需求: {req}")
    
    # risks
    ra = confirmed.get("risks_and_assumptions", {})
    for r in ra.get("risks", []):
        if isinstance(r, dict):
            req_texts.append(f"风险: {r.get('description', '')}")
        else:
            req_texts.append(f"风险: {r}")
    
    # assumptions
    for a in ra.get("assumptions", []):
        if isinstance(a, dict):
            req_texts.append(f"假设: {a.get('description', '')}")
        else:
            req_texts.append(f"假设: {a}")
    
    # 构建 prompt
    prompt = f"""你是一个需求标注专家。请对以下需求进行语义标注。

## 输入需求列表
{chr(10).join([f"- {text}" for text in req_texts])}

## 输出要求

请返回一个 JSON 数组，每个元素对应一条需求，包含以下字段：

### 必填字段
- `original_text`: 原始需求文本（从上面列表中复制，用于匹配）
- `category`: 需求分类，必须是以下之一：
  - `core_objective`: 核心目标
  - `capability`: 功能需求
  - `prohibition`: 禁止项
  - `quality_attribute`: 质量属性
  - `constraint`: 约束条件
  - `integration`: 集成需求
  - `pain_point`: 痛点
  - `success_metric`: 成功指标
  - `user`: 用户画像
  - `scenario`: 使用场景
  - `risk`: 风险
  - `assumption`: 假设
- `priority`: 优先级，必须是 P0（必须）/ P1（应该）/ P2（可以）

### 可选字段
- `dependencies`: 依赖的REQ-ID列表（例如 ["REQ-001"]），如果该需求依赖其他需求先实现
- `potential_conflicts`: 潜在冲突的REQ-ID列表（例如 ["REQ-002"]），如果该需求与其他需求可能冲突（标记为potential而非confirmed）
- `context_note`: 一句话结构化上下文（不是用户原话，而是提炼后的上下文备注，信息密度更高）

## 输出示例

```json
[
  {{
    "original_text": "目标: 为半导体封装领域求职者提供智能简历定制系统",
    "category": "core_objective",
    "priority": "P0",
    "context_note": "用户核心诉求：快速定制简历应对猎头推送"
  }},
  {{
    "original_text": "必须做: 保持简历真实性",
    "category": "capability",
    "priority": "P0",
    "dependencies": [],
    "potential_conflicts": ["REQ-011"],
    "context_note": "用户强调不希望AI乱写，只能基于真实经历"
  }}
]
```

## 注意事项

1. **original_text 必须从输入列表中精确复制**，不要修改或缩写
2. **category 必须使用上述枚举值**，不要自创分类
3. **priority 判断标准**：
   - P0: 不满足则方案失败（核心目标、必须做的事、禁止做的事）
   - P1: 应该满足，不满足会降低方案质量
   - P2: 可以满足，锦上添花
4. **dependencies 和 potential_conflicts 使用 REQ-ID 格式**（REQ-001, REQ-002...），按输入顺序编号
5. **context_note 要精炼**，一句话概括上下文，信息密度高于用户原话
6. **只输出 JSON 数组**，不要包含其他文字或 markdown 标记

请开始标注："""
    
    return prompt

# ============================================================================
# 标注验证
# ============================================================================

def _validate_annotations(annotations: List[Dict[str, Any]]) -> bool:
    """验证标注是否符合 Schema"""
    try:
        jsonschema.validate(annotations, ANNOTATION_SCHEMA)
        return True
    except jsonschema.ValidationError as e:
        logger.warning(f"LLM annotation validation failed: {e.message}")
        return False

def _check_coverage(confirmed: Dict[str, Any], annotations: List[Dict[str, Any]]) -> float:
    """检查标注覆盖率"""
    # 提取所有需求文本
    req_texts = set()
    
    if confirmed.get("objective"):
        req_texts.add(f"目标: {confirmed['objective']}")
    
    for p in confirmed.get("pain_points", []):
        req_texts.add(f"痛点: {p}")
    
    for u in confirmed.get("users", []):
        if isinstance(u, dict):
            req_texts.add(f"用户: {u.get('role', '')} - {u.get('description', '')}")
        else:
            req_texts.add(f"用户: {u}")
    
    for s in confirmed.get("key_scenarios", []):
        req_texts.add(f"场景: {s}")
    
    for m in confirmed.get("success_metrics", []):
        if isinstance(m, dict):
            req_texts.add(f"成功指标: {m.get('metric', '')} - {m.get('target', '')}")
        else:
            req_texts.add(f"成功指标: {m}")
    
    caps = confirmed.get("capabilities", {})
    for cap in caps.get("always_do", []):
        req_texts.add(f"必须做: {cap}")
    for cap in caps.get("should_do", []):
        req_texts.add(f"应该做: {cap}")
    for cap in caps.get("never_do", []):
        req_texts.add(f"禁止做: {cap}")
    
    for qa in confirmed.get("quality_attributes", []):
        if isinstance(qa, dict):
            req_texts.add(f"质量属性: {qa.get('category', '')} - {qa.get('spec', '')}")
        else:
            req_texts.add(f"质量属性: {qa}")
    
    constraints = confirmed.get("constraints", {})
    if isinstance(constraints, dict):
        for k, v in constraints.items():
            req_texts.add(f"约束: {k} - {v}")
    
    integration = confirmed.get("integration", {})
    for req in integration.get("requirements", []):
        req_texts.add(f"集成需求: {req}")
    
    ra = confirmed.get("risks_and_assumptions", {})
    for r in ra.get("risks", []):
        if isinstance(r, dict):
            req_texts.add(f"风险: {r.get('description', '')}")
        else:
            req_texts.add(f"风险: {r}")
    
    for a in ra.get("assumptions", []):
        if isinstance(a, dict):
            req_texts.add(f"假设: {a.get('description', '')}")
        else:
            req_texts.add(f"假设: {a}")
    
    # 统计已标注的需求
    annotated_texts = {ann.get("original_text", "") for ann in annotations}
    
    # 计算覆盖率
    if not req_texts:
        return 1.0
    
    covered = sum(1 for text in req_texts if text in annotated_texts)
    coverage = covered / len(req_texts)
    
    logger.info(f"Annotation coverage: {coverage:.2%} ({covered}/{len(req_texts)})")
    return coverage

# ============================================================================
# 主函数
# ============================================================================

def annotate_requirements(
    living_spec: Dict[str, Any],
    llm_call_fn: Callable[[str], str]
) -> Optional[List[Dict[str, Any]]]:
    """
    LLM 标注需求
    
    Args:
        living_spec: living_spec.json 内容
        llm_call_fn: LLM 调用函数（输入prompt，返回response文本）
    
    Returns:
        标注列表（符合Schema），失败时返回 None
    """
    confirmed = living_spec.get("confirmed", {})
    if not confirmed:
        logger.info("No confirmed requirements, skipping annotation")
        return None
    
    # 构建 prompt
    prompt = _build_annotation_prompt(confirmed)
    
    try:
        # 调用 LLM
        response = llm_call_fn(prompt)
        
        # 解析 JSON
        annotations = json.loads(response)
        
        # Schema 验证
        if not _validate_annotations(annotations):
            logger.warning("LLM annotation schema validation failed, falling back to script")
            return None
        
        # 覆盖率检查
        coverage = _check_coverage(confirmed, annotations)
        if coverage < 0.8:
            logger.warning(f"LLM annotation coverage too low: {coverage:.2%}, falling back to script")
            return None
        
        logger.info(f"LLM annotation successful: {len(annotations)} annotations, {coverage:.2%} coverage")
        return annotations
    
    except json.JSONDecodeError as e:
        logger.warning(f"LLM annotation JSON parse failed: {e}, falling back to script")
        return None
    except Exception as e:
        logger.warning(f"LLM annotation failed: {e}, falling back to script")
        return None
