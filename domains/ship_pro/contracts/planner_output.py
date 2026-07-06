"""
Ship Pro - Planner Output Schema (DEPRECATED → re-export)

DEPRECATED: Use domains.ship_pro.pipeline_designer.WorkerSpec and PipelinePlan instead.
This module is kept for backward compatibility only.
The unified schema in pipeline_designer.py includes all fields from this module
(must_constraints, wp_id_prefix, needs_web_search, web_search_scope, solution_pro_refs)
plus additional operational fields (execution_order, module_purpose, interface_provides/requires).

遵循 AI Native 原则：
- 不硬编码枚举（让 LLM 自由分类）
- 不限制角色名称（让 LLM 自由命名）
- 只约束必要字段（让 LLM 有充分空间）
"""
from typing import Any, Dict

# Re-export unified schema from pipeline_designer
from ..pipeline_designer import PipelinePlan, WorkerSpec

# DEPRECATED aliases — old code importing from here still works
PlannerOutput = PipelinePlan


def get_planner_output_schema() -> Dict[str, Any]:
    """获取 PlannerOutput (→ PipelinePlan) 的 JSON Schema（用于 LLM 输出约束）"""
    return PipelinePlan.model_json_schema()


__all__ = [
    "WorkerSpec",
    "PipelinePlan",
    "PlannerOutput",  # DEPRECATED alias
    "get_planner_output_schema",
]
