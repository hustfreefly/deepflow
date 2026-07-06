"""
Spec Pro Schema 契约层
=====================

定义所有核心数据结构的 Schema，供 Prompt 和 Code 共同遵守。

设计原则：
1. 使用 Python dict 定义（不引入新依赖）
2. 提供 validate_against_schema() 函数进行软校验
3. Schema 作为 Single Source of Truth，Prompt 和 Code 都从此对齐

Schema 结构说明：
- required: 必填字段列表
- properties: 字段定义（类型 + 描述）
- 类型标记: 'str', 'int', 'float', 'bool', 'list', 'dict', 'any'
"""

from typing import Any, Dict, List, Tuple


# ============================================================================
# 常量 — 跨模块共享的确定性配置（禁止在其他地方硬编码）
# ============================================================================

INFERENCE_AUDIT_THRESHOLD = 5  # pending 推断超过此数 → WARN
QUALITY_DIMENSIONS = [
    "objective", "users", "capabilities", "quality_attributes",
    "constraints", "integration", "risks",
]
QUALITY_DIMENSION_WEIGHTS = {
    "objective": 0.20,
    "users": 0.15,
    "capabilities": 0.15,
    "quality_attributes": 0.15,
    "constraints": 0.15,
    "integration": 0.10,
    "risks": 0.10,
}


# ============================================================================
# 1. LIVING_SPEC_SCHEMA — Living Spec 完整结构
# ============================================================================

LIVING_SPEC_SCHEMA = {
    "required": ["meta", "confirmed"],
    "properties": {
        "meta": {
            "type": "dict",
            "required": ["version", "created_at", "updated_at"],
            "properties": {
                "version": {"type": "str"},
                "created_at": {"type": "str"},
                "updated_at": {"type": "str"},
                "rounds": {"type": "int"},
                "conversation_rounds": {"type": "int"},
                "quality_score": {"type": "any"},  # int or float
                "quality_level": {"type": "str"},
                "scenario": {"type": "str"},
                "mode": {"type": "str"}
            }
        },
        "confirmed": {
            "type": "dict",
            "required": [
                "objective", "success_metrics", "pain_points", "users",
                "key_scenarios", "capabilities", "quality_attributes",
                "constraints", "risks_and_assumptions", "integration",
            ],
            "properties": {
                "objective": {"type": "str"},
                "success_metrics": {"type": "list"},
                "pain_points": {"type": "list"},
                "users": {"type": "list"},
                "key_scenarios": {"type": "list"},
                "capabilities": {
                    "type": "dict",
                    "properties": {
                        "always_do": {"type": "list"},
                        "should_do": {"type": "list"},
                        "never_do": {"type": "list"}
                    }
                },
                "quality_attributes": {"type": "list"},
                "constraints": {"type": "dict"},
                "risks_and_assumptions": {
                    "type": "dict",
                    "properties": {
                        "risks": {"type": "list"},
                        "assumptions": {"type": "list"}
                    }
                },
                "integration": {"type": "dict"},
                "terms": {"type": "list"},
                "user_directives": {"type": "list"}
            }
        },
        "inferred": {"type": "list"},
        "solution_pro_hints": {"type": "any"},  # None until StructureWorker fills it
        "route_recommendation": {"type": "any"},  # None until StructureWorker fills it
        "guardrails": {
            "type": "dict",
            "properties": {
                "always_do": {"type": "list"},
                "never_do": {"type": "list"}
            }
        }
    }
}


# ============================================================================
# 2. ROUND_RESULT_SCHEMA — 统一 quality 对象结构（所有 action 模式）
# ============================================================================

ROUND_RESULT_SCHEMA = {
    "required": ["action", "quality"],
    "properties": {
        "action": {
            "type": "str",
            "enum": ["questions", "summary", "proposal", "done", "safety_stop"]
        },
        "questions": {"type": "list"},
        "proposal_text": {"type": "str"},
        "summary_text": {"type": "str"},
        "quality": {
            "type": "dict",
            "required": ["overall_score", "level", "dimension_scores"],
            "properties": {
                "overall_score": {"type": "any"},  # int or float
                "level": {"type": "str"},
                "dimension_scores": {
                    "type": "dict",  # key=维度名, value={score, delta, change}
                    "description": "每个维度的分数和变化，key 为维度名",
                    "properties": {
                        "objective": {"type": "dict"},
                        "users": {"type": "dict"},
                        "capabilities": {"type": "dict"},
                        "quality_attributes": {"type": "dict"},
                        "constraints": {"type": "dict"},
                        "integration": {"type": "dict"},
                        "risks": {"type": "dict"}
                    }
                },
                "top_missing": {"type": "list"}
            }
        },
        "conversation_log": {"type": "list"}
    }
}


# ============================================================================
# 3. RESPONSE_SCHEMA — ParseResponseWorker 输出格式
# ============================================================================

RESPONSE_SCHEMA = {
    "required": ["parsed_updates"],
    "properties": {
        "parsed_updates": {
            "type": "dict",
            "properties": {
                "objective": {"type": "str"},
                "success_metrics": {"type": "list"},
                "pain_points": {"type": "list"},
                "users": {"type": "list"},
                "key_scenarios": {"type": "list"},
                "capabilities": {"type": "dict"},
                "quality_attributes": {"type": "list"},
                "constraints": {"type": "dict"},
                "risks_and_assumptions": {"type": "dict"},
                "integration": {"type": "dict"},
                "user_directives": {
                    "type": "list",
                    "items": {
                        "type": "dict",
                        "required": ["directive"],
                        "properties": {
                            "directive": {
                                "type": "str",
                                "enum": [
                                    "deliberately_omitted",
                                    "benchmark_reference",
                                    "design_delegation",
                                    "adaptive_expectation",
                                    "quality_priority",
                                    "industry_reference"
                                ]
                            },
                            "dimension": {"type": "str"},
                            "content": {"type": "str"},
                            "reason": {"type": "str"},
                            "status": {"type": "str"}
                        }
                    }
                }
            }
        },
        "meta_signals": {
            "type": "dict",
            "properties": {
                "user_said_enough": {"type": "bool"},
                "user_wants_pivot": {"type": "bool"},
                "directive_stop_asking": {"type": "bool"},
                "stop_asking_dimensions": {"type": "list"}
            }
        },
        "inference_responses": {"type": "list"},
        "new_inferences": {"type": "list"}
    }
}


# ============================================================================
# 4. QUALITY_REPORT_SCHEMA — AssessWorker 输出格式
# ============================================================================

QUALITY_REPORT_SCHEMA = {
    "required": ["overall_score", "level", "dimensions"],
    "properties": {
        "overall_score": {"type": "int"},
        "level": {"type": "str"},
        "dimensions": {
            "type": "list",  # 注意：数组格式，非字典
            "items": {
                "type": "dict",
                "required": ["dimension", "score", "weight"],
                "properties": {
                    "dimension": {"type": "str"},
                    "score": {"type": "int"},
                    "weight": {"type": "any"},  # int or float
                    "reasoning": {"type": "str"},
                    "missing_items": {"type": "list"}
                }
            }
        },
        "top_missing": {"type": "list"},
        "recommendation": {"type": "str"}
    }
}


# ============================================================================
# 5. CONVERSATION_LOG_SCHEMA — 对话日志格式
# ============================================================================

CONVERSATION_LOG_SCHEMA = {
    "type": "dict",
    "required": ["rounds"],
    "properties": {
        "rounds": {
            "type": "list",
            "items": {
                "type": "dict",
                "required": ["round", "phase", "user_response"],
                "properties": {
                    "round": {"type": "int"},
                    "timestamp": {"type": "str"},
                    "phase": {"type": "str"},
                    "questions": {"type": "list"},
                    "user_response": {"type": "str"},
                    "parsed_updates_summary": {"type": "str"},
                    "quality_before": {"type": "any"},
                    "quality_after": {"type": "any"},
                    "quality_delta": {"type": "any"},
                    "inferences_created": {"type": "int"},
                    "inferences_confirmed": {"type": "int"},
                    "inferences_rejected": {"type": "int"},
                }
            }
        }
    }
}

# 空对话日志初始值（coordinator 初始化时使用）
EMPTY_CONVERSATION_LOG = {"rounds": []}


# ============================================================================
# 6. QUALITY_TRAJECTORY_SCHEMA — 质量轨迹格式
# ============================================================================

QUALITY_TRAJECTORY_SCHEMA = {
    "type": "dict",
    "required": ["scores"],
    "properties": {
        "scores": {
            "type": "list",
            "description": "每轮的 overall_score 列表（快速索引用）",
            "items": {"type": "any"}  # int or float
        },
        "trajectory": {
            "type": "list",
            "description": "每轮详细轨迹点",
            "items": {
                "type": "dict",
                "required": ["round", "overall_score"],
                "properties": {
                    "round": {"type": "int"},
                    "overall_score": {"type": "any"},
                    "level": {"type": "str"},
                    "dimension_scores": {"type": "dict"},
                    "delta": {"type": "any"},
                    "questions_asked": {"type": "int"},
                    "inferences_validated": {"type": "int"},
                }
            }
        }
    }
}

# 空质量轨迹初始值（coordinator 初始化时使用）
EMPTY_QUALITY_TRAJECTORY = {"scores": [], "trajectory": []}


# ============================================================================
# 验证说明
# ============================================================================

# 注意：Schema 验证由 Pydantic 契约笼子（contracts/ 目录）负责，
# schemas.py 仅保留 Schema 定义作为 Single Source of Truth，
# 不再提供 validate_* 函数（已被 gate_* 函数取代）。

