#!/usr/bin/env python3
"""Validate Solution Pro fixed-pipeline contracts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


FIXED_STAGES = [
    "data_collection",
    "planning",
    "reviewers",
    "research",
    "consolidator",
    "audit",
    "fix",
    "fixer_expert",
    "harness_final",
    "summarizer",
]

FIXED_RESEARCH_WORKERS = ["expert_1", "expert_2", "expert_3"]


class Validation:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_json(path: Path, validation: Validation) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            validation.error(f"{path} must contain a JSON object")
            return {}
        return data
    except FileNotFoundError:
        validation.error(f"Missing file: {path}")
    except json.JSONDecodeError as exc:
        validation.error(f"Invalid JSON in {path}: {exc}")
    return {}


def get_task(tasks: Dict[str, Any], task_key: str) -> Any:
    node: Any = tasks
    for part in task_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def validate_execution_plan(base: Path, validation: Validation) -> None:
    plan = load_json(base / "execution_plan.json", validation)
    tasks = load_json(base / "tasks.json", validation)
    if not plan or not tasks:
        return

    phases = plan.get("phases", [])
    if len(phases) != 10:
        validation.error(f"execution_plan must have fixed 10 phases, got {len(phases)}")
        return

    stages = [phase.get("stage") for phase in phases]
    if stages != FIXED_STAGES:
        validation.error(f"execution_plan stages mismatch: {stages}")

    for phase in phases:
        stage = phase.get("stage", "<unknown>")
        if phase.get("parallel"):
            workers = phase.get("workers")
            if not isinstance(workers, list) or not workers:
                validation.error(f"{stage}: parallel phase requires non-empty workers list")
                continue
            for worker in workers:
                if not isinstance(worker, dict):
                    validation.error(f"{stage}: worker entries must be objects")
                    continue
                for field in ("id", "task_key", "expected_output_path"):
                    if not worker.get(field):
                        validation.error(f"{stage}.{worker.get('id', '?')}: missing {field}")
                task_key = worker.get("task_key", "")
                if get_task(tasks, task_key) is None:
                    validation.error(f"{stage}.{worker.get('id', '?')}: missing task_key {task_key}")
        else:
            for field in ("worker", "task_key", "expected_output_path"):
                if not phase.get(field):
                    validation.error(f"{stage}: missing {field}")
            task_key = phase.get("task_key", "")
            if get_task(tasks, task_key) is None:
                validation.error(f"{stage}: missing task_key {task_key}")

    research_phase = next((p for p in phases if p.get("stage") == "research"), {})
    research_workers = [w.get("id") for w in research_phase.get("workers", []) if isinstance(w, dict)]
    if research_workers != FIXED_RESEARCH_WORKERS:
        validation.error(f"research workers must be fixed {FIXED_RESEARCH_WORKERS}, got {research_workers}")


def validate_control_contract(base: Path, validation: Validation) -> None:
    path = base / "control_contract.json"
    if not path.exists():
        validation.warning("control_contract.json is not present yet")
        return
    contract = load_json(path, validation)
    if contract.get("frozen_spec_path") != "data/frozen_spec.json":
        validation.error("control_contract must reference frozen_spec_path=data/frozen_spec.json")
    if contract.get("traceability_matrix_path") != "requirements_traceability_matrix.json":
        validation.error("control_contract must reference traceability_matrix_path=requirements_traceability_matrix.json")
    criteria = contract.get("acceptance_criteria", [])
    if not isinstance(criteria, list) or not criteria:
        validation.error("control_contract acceptance_criteria must be a non-empty list")
    workers = contract.get("research_workers", [])
    ids = [w.get("id") for w in workers if isinstance(w, dict)]
    if ids != FIXED_RESEARCH_WORKERS:
        validation.error(f"control_contract research_workers must map to fixed slots {FIXED_RESEARCH_WORKERS}, got {ids}")
    for worker in workers:
        if not isinstance(worker, dict):
            validation.error("control_contract research_workers entries must be objects")
            continue
        if not worker.get("angle") or not worker.get("reason"):
            validation.error(f"control_contract {worker.get('id', '?')}: missing angle/reason")


def validate_frozen_spec(base: Path, validation: Validation) -> None:
    path = base / "data" / "frozen_spec.json"
    frozen = load_json(path, validation)
    if not frozen:
        return
    requirements = frozen.get("requirements", [])
    if not isinstance(requirements, list) or not requirements:
        validation.error("frozen_spec requirements must be a non-empty list")
        return
    seen = set()
    has_p0 = False
    for item in requirements:
        if not isinstance(item, dict):
            validation.error("frozen_spec requirements entries must be objects")
            continue
        req_id = item.get("id")
        if not req_id:
            validation.error("frozen_spec requirement missing id")
            continue
        if req_id in seen:
            validation.error(f"Duplicate REQ-ID in frozen_spec: {req_id}")
        seen.add(req_id)
        if not re.match(r"^REQ-\d{3}$", str(req_id)):
            validation.error(f"Invalid REQ-ID format: {req_id}")
        if not item.get("description"):
            validation.error(f"{req_id}: missing description")
        if item.get("priority") == "P0":
            has_p0 = True
    if not has_p0:
        validation.error("frozen_spec must contain at least one P0 requirement")


def validate_traceability_matrix(base: Path, validation: Validation) -> None:
    matrix_path = base / "requirements_traceability_matrix.json"
    if not matrix_path.exists():
        validation.warning("requirements_traceability_matrix.json is not present yet")
        return
    frozen = load_json(base / "data" / "frozen_spec.json", validation)
    matrix = load_json(matrix_path, validation)
    reqs = {
        item.get("id"): item
        for item in frozen.get("requirements", [])
        if isinstance(item, dict) and item.get("id")
    }
    entries = matrix.get("requirements", {})
    if not isinstance(entries, dict):
        validation.error("requirements_traceability_matrix requirements must be an object")
        return
    for req_id in entries:
        if req_id not in reqs:
            validation.error(f"traceability matrix references unknown REQ-ID: {req_id}")
    for req_id, item in reqs.items():
        if item.get("priority") == "P0":
            status = entries.get(req_id, {}).get("status") if isinstance(entries.get(req_id), dict) else None
            if status not in ("covered", "partial"):
                validation.error(f"P0 requirement is not covered in traceability matrix: {req_id}")


def validate_prompt_vars(base: Path, validation: Validation) -> None:
    tasks = load_json(base / "tasks.json", validation)
    if not tasks:
        return

    unresolved = []

    def walk(value: Any, key: str) -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                walk(child_value, f"{key}.{child_key}" if key else child_key)
        elif isinstance(value, str):
            matches = re.findall(r"\{\{\s*[^}]+\s*\}\}", value)
            if matches:
                unresolved.append((key, matches[:5]))

    walk(tasks, "")
    for key, matches in unresolved:
        validation.error(f"Unresolved template vars in tasks.{key}: {matches}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/validate_solution_pro_contract.py <blackboard_session_path>")
        return 2

    base = Path(sys.argv[1]).resolve()
    validation = Validation()
    validate_execution_plan(base, validation)
    validate_frozen_spec(base, validation)
    validate_control_contract(base, validation)
    validate_traceability_matrix(base, validation)
    validate_prompt_vars(base, validation)

    result = {
        "status": "ok" if validation.ok else "failed",
        "errors": validation.errors,
        "warnings": validation.warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if validation.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
