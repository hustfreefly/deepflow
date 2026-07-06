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
# 校验函数
# ============================================================================

def validate_against_schema(
    data: Any,
    schema: Dict[str, Any],
    path: str = ""
) -> Tuple[bool, List[str]]:
    """
    校验数据是否符合 Schema
    
    Args:
        data: 待校验的数据
        schema: Schema 定义
        path: 当前路径（用于错误信息）
    
    Returns:
        (is_valid, errors)
        - is_valid: 是否通过校验
        - errors: 错误信息列表（空列表表示无错误）
    
    设计：软校验模式，返回错误但不抛异常
    """
    errors = []
    
    # 类型检查
    expected_type = schema.get("type")
    if expected_type:
        type_map = {
            "str": str,
            "int": int,
            "float": (int, float),  # int 也可以作为 float
            "bool": bool,
            "list": list,
            "dict": dict,
            "any": object  # 任意类型
        }
        
        expected_py_type = type_map.get(expected_type)
        if expected_py_type and not isinstance(data, expected_py_type):
            errors.append(f"{path or 'root'}: 期望类型 {expected_type}，实际 {type(data).__name__}")
            return False, errors  # 类型错误直接返回，不继续检查
    
    # 必填字段检查（仅对 dict 类型）
    if isinstance(data, dict):
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in data:
                errors.append(f"{path}.{field}: 缺少必填字段" if path else f"{field}: 缺少必填字段")
        
        # 递归检查 properties
        properties = schema.get("properties", {})
        for key, value in data.items():
            if key in properties:
                child_path = f"{path}.{key}" if path else key
                child_schema = properties[key]
                child_valid, child_errors = validate_against_schema(value, child_schema, child_path)
                errors.extend(child_errors)
    
    # 枚举检查
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path or 'root'}: 值 '{data}' 不在允许的枚举中 {schema['enum']}")
    
    # 数组项检查
    if isinstance(data, list) and "items" in schema:
        item_schema = schema["items"]
        for i, item in enumerate(data):
            item_path = f"{path}[{i}]"
            item_valid, item_errors = validate_against_schema(item, item_schema, item_path)
            errors.extend(item_errors)
    
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_living_spec(living_spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 Living Spec 是否符合 LIVING_SPEC_SCHEMA"""
    return validate_against_schema(living_spec, LIVING_SPEC_SCHEMA)


def validate_round_result(round_result: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 Round Result 是否符合 ROUND_RESULT_SCHEMA"""
    return validate_against_schema(round_result, ROUND_RESULT_SCHEMA)


def validate_response(response: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 Response 是否符合 RESPONSE_SCHEMA"""
    return validate_against_schema(response, RESPONSE_SCHEMA)


def validate_quality_report(quality_report: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 Quality Report 是否符合 QUALITY_REPORT_SCHEMA"""
    return validate_against_schema(quality_report, QUALITY_REPORT_SCHEMA)


def validate_conversation_log(conversation_log: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 Conversation Log 是否符合 CONVERSATION_LOG_SCHEMA"""
    return validate_against_schema(conversation_log, CONVERSATION_LOG_SCHEMA)


def validate_quality_trajectory(quality_trajectory: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 Quality Trajectory 是否符合 QUALITY_TRAJECTORY_SCHEMA"""
    return validate_against_schema(quality_trajectory, QUALITY_TRAJECTORY_SCHEMA)


# ============================================================================
# 辅助函数：生成 Schema 的 JSON 表示（供 Prompt 使用）
# ============================================================================

def schema_to_json(schema: Dict[str, Any], indent: int = 2) -> str:
    """将 Schema 转换为简洁的 JSON 表示（用于 Prompt 展示）"""
    import json
    
    def simplify(s):
        if not isinstance(s, dict):
            return s
        
        result = {}
        
        # 只保留关键信息
        if "type" in s:
            result["type"] = s["type"]
        if "required" in s:
            result["required"] = s["required"]
        if "enum" in s:
            result["enum"] = s["enum"]
        
        # 递归处理 properties
        if "properties" in s:
            result["properties"] = {
                k: simplify(v) for k, v in s["properties"].items()
            }
        
        # 递归处理 items
        if "items" in s:
            result["items"] = simplify(s["items"])
        
        return result
    
    simplified = simplify(schema)
    return json.dumps(simplified, indent=indent, ensure_ascii=False)


if __name__ == "__main__":
    # 测试：打印所有 Schema 的 JSON 表示
    print("=" * 80)
    print("LIVING_SPEC_SCHEMA")
    print("=" * 80)
    print(schema_to_json(LIVING_SPEC_SCHEMA))
    
    print("\n" + "=" * 80)
    print("ROUND_RESULT_SCHEMA")
    print("=" * 80)
    print(schema_to_json(ROUND_RESULT_SCHEMA))
    
    print("\n" + "=" * 80)
    print("RESPONSE_SCHEMA")
    print("=" * 80)
    print(schema_to_json(RESPONSE_SCHEMA))
    
    print("\n" + "=" * 80)
    print("QUALITY_REPORT_SCHEMA")
    print("=" * 80)
    print(schema_to_json(QUALITY_REPORT_SCHEMA))
