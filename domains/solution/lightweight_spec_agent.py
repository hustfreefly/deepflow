"""
Lightweight Spec Agent (场景B优化)

触发时机：Solution Pro 启动时，如果 living_spec=None，自动调用
输入：topic + constraints
输出：minimal living_spec（包含 objective/pain_points/users/scenarios/success_metrics 等）

设计原则：
- 一次 LLM 调用推断 living_spec
- JSON Schema 验证输出格式
- 失败时 fallback 到 minimal living_spec（只有 objective）
- 不依赖 Spec Pro 完整流程
"""

import json
import jsonschema
from typing import Dict, Any, List, Optional, Callable
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# JSON Schema 定义（LLM 输出格式验证）
# ============================================================================

LIGHTWEIGHT_SPEC_SCHEMA = {
    "type": "object",
    "required": ["confirmed"],
    "properties": {
        "confirmed": {
            "type": "object",
            "required": ["objective"],
            "properties": {
                "objective": {"type": "string"},
                "pain_points": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "users": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string"},
                            "description": {"type": "string"},
                            "key_needs": {"type": "string"}
                        }
                    }
                },
                "key_scenarios": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "success_metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metric": {"type": "string"},
                            "target": {"type": "string"}
                        }
                    }
                },
                "capabilities": {
                    "type": "object",
                    "properties": {
                        "always_do": {"type": "array", "items": {"type": "string"}},
                        "should_do": {"type": "array", "items": {"type": "string"}},
                        "never_do": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "quality_attributes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "spec": {"type": "string"},
                            "priority": {"type": "string"}
                        }
                    }
                },
                "constraints": {
                    "type": "object",
                    "properties": {
                        "budget": {"type": "string"},
                        "timeline": {"type": "string"},
                        "tech_stack": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "integration": {
                    "type": "object",
                    "properties": {
                        "requirements": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "risks_and_assumptions": {
                    "type": "object",
                    "properties": {
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "assumptions": {"type": "array", "items": {"type": "string"}}
                    }
                }
            }
        }
    }
}

# ============================================================================
# Prompt 构建
# ============================================================================

def _build_inference_prompt(topic: str, constraints: List[str]) -> str:
    """构建 LLM 推断 prompt"""
    
    constraints_text = "\n".join([f"- {c}" for c in constraints]) if constraints else "无特殊约束"
    
    prompt = f"""你是一个需求分析专家。请基于以下主题和约束，推断出完整的 living_spec.confirmed 结构。

## 输入
- **主题**: {topic}
- **约束条件**:
{constraints_text}

## 输出要求

请返回一个 JSON 对象，包含以下字段：

### 必填字段
- `objective`: 核心目标（一句话概括）

### 可选字段（基于常识推断，不要编造不合理的细节）
- `pain_points`: 痛点列表（2-3个，描述用户当前面临的问题）
- `users`: 用户画像列表（1-2个，每个包含 role/description/key_needs）
- `key_scenarios`: 关键场景列表（2-3个，描述典型使用场景）
- `success_metrics`: 成功指标列表（2-3个，每个包含 metric/target）
- `capabilities`: 能力要求
  - `always_do`: 必须做的事（2-3个）
  - `should_do`: 应该做的事（1-2个）
  - `never_do`: 禁止做的事（1-2个）
- `quality_attributes`: 质量属性列表（1-2个，每个包含 category/spec/priority）
- `constraints`: 约束条件（budget/timeline/tech_stack）
- `integration`: 集成需求（requirements 列表）
- `risks_and_assumptions`: 风险与假设
  - `risks`: 风险列表（1-2个）
  - `assumptions`: 假设列表（1-2个）

## 输出示例

```json
{{
  "confirmed": {{
    "objective": "为半导体封装领域求职者提供智能简历定制系统",
    "pain_points": [
      "HR每天收到10+猎头职位，手动改简历效率低",
      "现有简历无法匹配不同JD的要求"
    ],
    "users": [
      {{
        "role": "HR经理",
        "description": "半导体封装领域的HR",
        "key_needs": "快速响应猎头需求"
      }}
    ],
    "key_scenarios": [
      "收到猎头推送新职位后快速定制简历",
      "批量投递多个岗位"
    ],
    "success_metrics": [
      {{"metric": "简历生成时间", "target": "<60秒"}},
      {{"metric": "JD匹配度", "target": ">85%"}}
    ],
    "capabilities": {{
      "always_do": ["PDF+DOCX双格式输出", "保持简历真实性"],
      "should_do": ["ATS兼容"],
      "never_do": ["编造虚假经历"]
    }},
    "quality_attributes": [
      {{"category": "性能", "spec": "响应<60s", "priority": "P0"}}
    ],
    "constraints": {{
      "budget": "无预算限制",
      "timeline": "尽快上线"
    }},
    "integration": {{
      "requirements": ["作为OpenClaw Skill构建"]
    }},
    "risks_and_assumptions": {{
      "risks": ["LLM幻觉风险"],
      "assumptions": ["用户有基础简历"]
    }}
  }}
}}
```

## 注意事项

1. **基于常识推断**，不要编造过于具体或不合理的细节
2. **objective 必须简洁**（≤50字）
3. **pain_points 要真实**（描述用户当前面临的实际问题）
4. **users 要具体**（包含 role 和 key_needs）
5. **success_metrics 要可衡量**（包含具体 target）
6. **capabilities 要清晰**（always_do/should_do/never_do 界限分明）
7. **只输出 JSON**，不要包含其他文字或 markdown 标记

请开始推断："""
    
    return prompt

# ============================================================================
# 验证与 Fallback
# ============================================================================

def _validate_inferred_spec(spec: Dict[str, Any]) -> bool:
    """验证推断的 living_spec 是否符合 Schema"""
    try:
        jsonschema.validate(spec, LIGHTWEIGHT_SPEC_SCHEMA)
        return True
    except jsonschema.ValidationError as e:
        logger.warning(f"Lightweight spec validation failed: {e.message}")
        return False

def _build_minimal_living_spec(topic: str) -> Dict[str, Any]:
    """构建 minimal living_spec（fallback）"""
    return {
        "confirmed": {
            "objective": topic,
            "pain_points": [],
            "users": [],
            "key_scenarios": [],
            "success_metrics": [],
            "capabilities": {
                "always_do": [],
                "should_do": [],
                "never_do": []
            },
            "quality_attributes": [],
            "constraints": {},
            "integration": {"requirements": []},
            "risks_and_assumptions": {
                "risks": [],
                "assumptions": []
            }
        }
    }

# ============================================================================
# 主函数
# ============================================================================

def infer_living_spec(
    topic: str,
    constraints: List[str],
    llm_call_fn: Callable[[str], str]
) -> Dict[str, Any]:
    """
    轻量 Spec Agent：从 topic + constraints 推断 living_spec
    
    Args:
        topic: 任务主题
        constraints: 约束条件列表
        llm_call_fn: LLM 调用函数（输入prompt，返回response文本）
    
    Returns:
        living_spec 字典（符合 Schema），失败时返回 minimal living_spec
    """
    # 构建 prompt
    prompt = _build_inference_prompt(topic, constraints)
    
    try:
        # 调用 LLM
        response = llm_call_fn(prompt)
        
        # 解析 JSON
        inferred_spec = json.loads(response)
        
        # Schema 验证
        if not _validate_inferred_spec(inferred_spec):
            logger.warning("Lightweight spec schema validation failed, falling back to minimal spec")
            return _build_minimal_living_spec(topic)
        
        logger.info(f"Lightweight spec inference successful: {inferred_spec['confirmed']['objective'][:50]}")
        return inferred_spec
    
    except json.JSONDecodeError as e:
        logger.warning(f"Lightweight spec JSON parse failed: {e}, falling back to minimal spec")
        return _build_minimal_living_spec(topic)
    except Exception as e:
        logger.warning(f"Lightweight spec inference failed: {e}, falling back to minimal spec")
        return _build_minimal_living_spec(topic)
