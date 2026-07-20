"""Planner control contract normalization for Solution Pro.

This module is intentionally deterministic. The product runtime is the LLM
orchestrator, but planner output should be normalized by code before it changes
the fixed 10-stage worker prompts.

This file is part of pipeline (10-stage architecture).
V3.1 纯 Agent Orchestrator 架构（Python orchestrator 已删除）.
Do not import this file for new workflows.
"""

from __future__ import annotations

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# [2026-07-13] Removed unused task_builder imports (rewrite_after_planning deprecated):
#   build_researcher_task, build_auditor_task, build_fixer_task_with_audit,
#   build_fixer_expert_task, inject_req_traceability, LAYER2_READ_INSTRUCTION
from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY, BlackboardManager


# ── helpers ──

def _get_bm(base_path: str) -> BlackboardManager:
    """从 base_path（session 目录）创建 BlackboardManager"""
    base = Path(base_path)
    return BlackboardManager(base.name, base_dir=base.parent)


# ── default experts (use registry for expected_output_path) ──

DEFAULT_RESEARCH_EXPERTS = [
    {
        "id": "expert_1",
        "name": "技术架构专家",
        "angle": "高并发系统架构与性能优化",
        "reason": "分析技术架构、性能、吞吐量和稳定性要求",
        "expected_output_path": STAGE_PATH_REGISTRY["research_expert_1"],
        "worker_role": "researcher_expert_1",
    },
    {
        "id": "expert_2",
        "name": "最佳实践专家",
        "angle": "行业最佳实践与标杆案例分析",
        "reason": "参考成熟方案，避免重复造轮子",
        "expected_output_path": STAGE_PATH_REGISTRY["research_expert_2"],
        "worker_role": "researcher_expert_2",
    },
    {
        "id": "expert_3",
        "name": "风险评估专家",
        "angle": "系统风险识别与容错设计",
        "reason": "识别关键风险、单点故障和缓解方案",
        "expected_output_path": STAGE_PATH_REGISTRY["research_expert_3"],
        "worker_role": "researcher_expert_3",
    },
]


def _registry_path(stage_name: str, fallback: str) -> str:
    return STAGE_PATH_REGISTRY.get(stage_name, fallback)


def _slug(value: str, fallback: str) -> str:
    raw = value or fallback
    slug = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", raw).strip("_")
    return (slug or fallback)[:48]


def _normalize_experts(planning: Dict[str, Any], mode: str) -> List[Dict[str, str]]:
    raw_experts = planning.get("required_experts") or []
    if not isinstance(raw_experts, list):
        raw_experts = []

    # B plan keeps the 10-stage pipeline fixed. Research still has three fixed
    # worker slots; Planner controls the assignment inside those slots.
    max_count = 3
    normalized = []
    for index, item in enumerate(raw_experts[:max_count], 1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or f"expert_{index}")
        expert_id = _slug(name, f"expert_{index}")
        fixed_id = f"expert_{index}"
        stage_name = f"research_{fixed_id}"
        normalized.append({
            "id": fixed_id,
            "planner_expert_id": expert_id,
            "name": name,
            "angle": str(item.get("angle") or "综合分析"),
            "reason": str(item.get("reason") or "Planner 认为该角度需要深入研究"),
            "expected_output_path": _registry_path(stage_name, stage_name),
            "worker_role": f"researcher_{fixed_id}",
        })

    if not normalized:
        return DEFAULT_RESEARCH_EXPERTS

    while len(normalized) < 3:
        fallback = DEFAULT_RESEARCH_EXPERTS[len(normalized)]
        normalized.append(dict(fallback))
    return normalized


def _normalize_layer2(planning: Dict[str, Any]) -> Dict[str, List[str]]:
    raw = planning.get("layer2_constraints") or {}
    if not isinstance(raw, dict):
        return {}

    normalized: Dict[str, List[str]] = {}
    for role, constraints in raw.items():
        if isinstance(constraints, str):
            constraints = [constraints]
        if not isinstance(constraints, list):
            continue
        values = [str(item).strip() for item in constraints if str(item).strip()]
        if values:
            normalized[str(role)] = values[:3]
    return normalized


def _normalize_acceptance_criteria(planning: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = planning.get("acceptance_criteria") or planning.get("requirements") or []
    criteria = []
    if isinstance(raw, list):
        for index, item in enumerate(raw, 1):
            if isinstance(item, dict):
                text = item.get("text") or item.get("description") or item.get("measurable")
                priority = item.get("priority", "P1")
                req_id = item.get("id", f"REQ-{index:03d}")
            else:
                text = str(item)
                priority = "P1"
                req_id = f"REQ-{index:03d}"
            if text:
                criteria.append({"id": str(req_id), "text": str(text), "priority": str(priority)})
    return criteria


def _acceptance_from_frozen_spec(bm: BlackboardManager) -> List[Dict[str, str]]:
    """
    从 living_spec 或 frozen_spec 生成 acceptance_criteria。

    ADR-009 Phase 3: 优先读 living_spec（requirement_index），
    fallback 到 frozen_spec.json（旧路径兼容）。
    """
    # ADR-009 Phase 3: 优先从 living_spec 读取 requirement_index
    # P1-6 FIX: 同时检查 spec/ 和 data/ 路径（data/ 是 __init__.py 写入路径）
    living_spec = bm.read_json("spec/living_spec.json") or {}
    if not living_spec:
        living_spec = bm.read_json("data/living_spec.json") or {}
    if not living_spec:
        # 尝试 MD 格式
        md_content = bm.read("spec/living_spec.md")
        if md_content:
            try:
                from domains.spec_pro.spec_living_md import parse_living_spec_md
                living_spec = parse_living_spec_md(md_content) or {}
            except Exception:
                living_spec = {}

    if isinstance(living_spec, dict) and living_spec.get("requirement_index"):
        req_index = living_spec["requirement_index"]
        if isinstance(req_index, list) and req_index:
            criteria = []
            for item in req_index:
                if isinstance(item, dict) and item.get("id") and item.get("description"):
                    criteria.append({
                        "id": str(item["id"]),
                        "text": str(item["description"]),
                        "priority": str(item.get("priority", "P1")),
                        "category": str(item.get("category", "requirement")),
                    })
            if criteria:
                return criteria

    # Fallback: frozen_spec.json（旧路径兼容）
    frozen = bm.read_json("frozen_spec.json", subdir="data") or {}
    if not isinstance(frozen, dict):
        return []

    # 尝试按 requirement_groups 组织
    groups = frozen.get("requirement_groups", {})
    if groups and isinstance(groups, dict):
        criteria = []
        for group_name, group_data in groups.items():
            if not isinstance(group_data, dict):
                continue
            req_ids = group_data.get("req_ids", [])
            group_description = group_data.get("description", "")

            # 为每个 REQ-ID 找到对应的 requirement
            for req_id in req_ids:
                req = _find_requirement_by_id(frozen.get("requirements", []), req_id)
                if req and isinstance(req, dict):
                    criteria.append({
                        "id": str(req.get("id", req_id)),
                        "text": str(req.get("description", "")),
                        "priority": str(req.get("priority", "P1")),
                        "category": str(req.get("category", "requirement")),
                        "group": group_name,
                        "group_description": group_description,
                    })

        if criteria:
            return criteria

    # Fallback: 扁平列表
    criteria = []
    for item in frozen.get("requirements", []) or []:
        if not isinstance(item, dict):
            continue
        req_id = item.get("id")
        text = item.get("description")
        if req_id and text:
            criteria.append({
                "id": str(req_id),
                "text": str(text),
                "priority": str(item.get("priority", "P1")),
                "category": str(item.get("category", "requirement")),
            })
    return criteria


def _find_requirement_by_id(requirements: List[Dict], req_id: str) -> Dict | None:
    """根据 ID 查找 requirement"""
    for req in requirements:
        if isinstance(req, dict) and req.get("id") == req_id:
            return req
    return None


def build_control_contract(base_path: str) -> Dict[str, Any]:
    """构建 control contract（使用 BlackboardManager API）"""
    bm = _get_bm(base_path)

    plan = bm.read_json("execution_plan.json") or {}
    planning = bm.read_stage("planning") or {}

    mode = str(plan.get("mode") or "standard")
    research_workers = _normalize_experts(planning, mode)
    layer2_constraints = _normalize_layer2(planning)
    audit_strategy = str(planning.get("audit_strategy") or "standard")

    return {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "source": {
            "planner_output_path": STAGE_PATH_REGISTRY.get("planning", "planning"),
            "execution_plan_path": "execution_plan.json",
        },
        "research_workers": research_workers,
        "layer2_constraints": layer2_constraints,
        "audit_strategy": audit_strategy,
        "frozen_spec_path": "data/frozen_spec.json",
        "traceability_matrix_path": "requirements_traceability_matrix.json",
        "acceptance_criteria": _acceptance_from_frozen_spec(bm) or _normalize_acceptance_criteria(planning),
        "warnings": [] if planning else ["planning.json missing or invalid; using fallback control contract"],
    }


def rewrite_after_planning(base_path: str, domain_profile=None) -> Dict[str, Any]:
    """[DEPRECATED] V1 10-stage pipeline post-planning rewrite.

    .. deprecated:: 2026-07-13
        V2 uses PlanningOrchestrator with Meta-Planner dynamic expert
        configuration. This function is retained only for V1 archived
        scripts (e.g. _archive/v1/scripts/golden_solution_pro_dry_run.py).
        V2 code should NOT call this function.

    Returns:
        A stub response indicating the function is deprecated.
    """
    import warnings
    warnings.warn(
        "rewrite_after_planning() is deprecated since 2026-07-13. "
        "V2 uses PlanningOrchestrator with Meta-Planner dynamic expert "
        "configuration. Use PlanningOrchestrator.run() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return {
        "status": "deprecated",
        "message": "V1 10-stage pipeline no longer active. Use PlanningOrchestrator.run() for V2.",
        "plan_shape": "deprecated_v1",
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python3 domains/solution_pro/control_contract.py <base_path>")
        raise SystemExit(2)
    print(json.dumps(rewrite_after_planning(sys.argv[1]), ensure_ascii=False, indent=2))