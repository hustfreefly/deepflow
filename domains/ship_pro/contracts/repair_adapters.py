"""
Ship Pro - Repair Adapters (兼容性转换层)

将旧版输出格式转换为新版 Schema，避免 Gate 验证 crash。
所有 adapter 均为纯函数，无副作用。
"""
from typing import Any, Dict, List


def legacy_array_to_worker_deliverable(worker_spec: dict, raw_array: list) -> dict:
    """将旧版 JSON 数组输出转换为 WorkerDeliverable object。
    
    Worker prompt 可能输出 JSON 数组（旧格式），但 WorkerGate 期望
    WorkerDeliverable object（含 worker_role, wp_id_prefix, work_packages）。
    
    Args:
        worker_spec: Worker 规格（含 role, wp_id_prefix 等）
        raw_array: 旧版 JSON 数组输出
    
    Returns:
        WorkerDeliverable-compatible dict
    """
    return {
        "worker_role": worker_spec.get("role", "unknown"),
        "wp_id_prefix": worker_spec.get("wp_id_prefix", "wp"),
        "work_packages": raw_array,
        "metadata": {"converted_from_legacy": True},
    }


def legacy_planner_output_to_pipeline_plan(old_data: dict) -> dict:
    """将旧版 PlannerOutput 格式转换为 PipelinePlan。
    
    字段映射：
    - task_description → module_purpose
    - expected_output_stage → 保留（PipelinePlan 无此字段，放入 metadata）
    - must_constraints → must_constraints（同名）
    
    Args:
        old_data: 旧版 PlannerOutput dict
    
    Returns:
        PipelinePlan-compatible dict（部分字段）
    """
    field_map = {
        "task_description": "module_purpose",
        "expected_output_stage": "expected_output_stage",
        "must_constraints": "must_constraints",
    }
    result = {}
    for old_key, new_key in field_map.items():
        if old_key in old_data:
            result[new_key] = old_data[old_key]
    # 直接传递同名字段
    for key in ("role", "covered_req_ids", "depends_on", "wp_id_prefix",
                "needs_web_search", "web_search_scope", "solution_pro_refs",
                "interface_provides", "interface_requires", "relevant_decisions",
                "relevant_risks", "estimated_wps", "estimated_effort_hours"):
        if key in old_data:
            result[key] = old_data[key]
    return result
