"""Planner control contract normalization for Solution Pro.

This module is intentionally deterministic. The product runtime is the LLM
orchestrator, but planner output should be normalized by code before it changes
the fixed 10-stage worker prompts.
"""

from __future__ import annotations

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from domains.solution_pro.task_builder import (
    build_researcher_task,
    build_auditor_task,
    build_fixer_task_with_audit,
    build_fixer_expert_task,
    inject_req_traceability,
    LAYER2_READ_INSTRUCTION,
)
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
    从 frozen_spec.json 生成 acceptance_criteria（V2.0 增强）。

    优先使用 requirement_groups 组织输出，如果没有则回退到扁平列表。
    """
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

    # Fallback: 扁平列表（向后兼容 V1.0）
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
    """构建 control contract（使用 V6 BlackboardManager API）"""
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


def rewrite_after_planning(base_path: str) -> Dict[str, Any]:
    """Refresh fixed post-planning tasks from Planner output.

    Historical name kept for compatibility. This does not rewrite the 10-stage
    plan shape; it only refreshes tasks and annotates the plan.
    """
    bm = _get_bm(base_path)
    base = Path(base_path)

    plan = bm.read_json("execution_plan.json") or {}
    tasks = bm.read_json("tasks.json") or {}
    contract = build_control_contract(base_path)

    session_id = plan.get("session_id") or base.name
    topic = plan.get("topic") or ""
    solution_type = plan.get("solution_type") or "architecture"
    mode = plan.get("mode") or "standard"
    constraints = plan.get("constraints") or []

    planning_path = str(bm.session_dir / STAGE_PATH_REGISTRY.get("planning", "planning"))
    research_tasks = {}
    for worker in contract["research_workers"]:
        task = build_researcher_task(
            worker["name"],
            session_id,
            topic,
            {"type": solution_type, "mode": mode, "constraints": constraints},
            expert_id=worker["id"],
            angle=worker["angle"],
            reason=worker["reason"],
        )
        research_tasks[worker["id"]] = inject_req_traceability(
            task + "\n" + LAYER2_READ_INSTRUCTION.format(
                session_id=session_id,
                planning_path=planning_path,
                worker_role=worker.get("worker_role") or f"researcher_{worker['id']}",
            ),
            session_id,
        )
    tasks["research"] = research_tasks

    for stage, builder, role in [
        ("audit", build_auditor_task, "auditor"),
    ]:
        base_task = builder(session_id, topic, {"type": solution_type, "mode": mode, "constraints": constraints})
        tasks[stage] = inject_req_traceability(
            base_task + "\n" + LAYER2_READ_INSTRUCTION.format(session_id=session_id, planning_path=planning_path, worker_role=role),
            session_id,
        )

    audit_path = str(bm.session_dir / STAGE_PATH_REGISTRY.get("audit", "audit"))
    tasks["fix"] = inject_req_traceability(
        build_fixer_task_with_audit(session_id, topic, audit_path) + "\n" + LAYER2_READ_INSTRUCTION.format(session_id=session_id, planning_path=planning_path, worker_role="fixer"),
        session_id,
    )
    tasks["fixer_expert"] = inject_req_traceability(
        build_fixer_expert_task(session_id, topic, [], severity="critical") + "\n" + LAYER2_READ_INSTRUCTION.format(session_id=session_id, planning_path=planning_path, worker_role="fixer_expert"),
        session_id,
    )

    # B plan keeps execution_plan fixed. We only annotate the plan with the
    # control contract path; phases/workers remain the original 10-stage shape.
    plan["version"] = "2.1"
    plan["control_contract_path"] = "control_contract.json"

    bm.write("control_contract.json", contract)
    bm.write("tasks.json", tasks)
    bm.write("execution_plan.json", plan)

    return {
        "status": "refreshed",
        "control_contract_path": str(bm.session_dir / "control_contract.json"),
        "execution_plan_path": str(bm.session_dir / "execution_plan.json"),
        "research_workers": [w["id"] for w in contract["research_workers"]],
        "phases": len(plan.get("phases", [])),
        "plan_shape": "fixed_10_stage",
        "warnings": contract.get("warnings", []),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python3 domains/solution_pro/control_contract.py <base_path>")
        raise SystemExit(2)
    print(json.dumps(rewrite_after_planning(sys.argv[1]), ensure_ascii=False, indent=2))