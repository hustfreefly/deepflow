#!/usr/bin/env python3
"""Golden dry-run for Solution Pro fixed 10-stage contract."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domains.solution.orchestrator_agent import _SolutionDispatcher
from domains.solution.control_contract import rewrite_after_planning
from domains.solution.completion_handler import _check_expected_outputs, _expected_outputs_from_plan
from domains.solution.frozen_spec import write_frozen_spec


class FakeBlackboard:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def get_stage_path(self, stage: str) -> Path:
        mapping = {
            "audit": "stages/audit.json",
            "fix": "stages/fix.json",
            "harness_final": "stages/harness_final.json",
        }
        return self.base_path / mapping.get(stage, f"stages/{stage}.json")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def stage_output(stage: str) -> dict:
    output = {
        "status": "completed",
        "stage": stage,
        "session_id": "golden_session",
        "timestamp": datetime.now().isoformat(),
        "data": {"summary": f"mock {stage}"},
        "covered_req_ids": ["REQ-001"],
        "harness_check": {
            "completeness": {"score": 0.9, "level": "high", "reasoning": "mock"},
            "necessity": {"score": 0.9, "level": "high", "reasoning": "mock"},
            "alignment": {"score": 0.9, "level": "high", "reasoning": "mock"},
            "global_impact": {"score": 0.9, "level": "high", "reasoning": "mock"},
            "overall_score": 0.9,
            "decision": "PASS",
            "improvements": [],
        },
    }
    if stage not in {"data_collection", "planning", "summarizer"}:
        output["requirement_evidence"] = [
            {"req_id": "REQ-001", "status": "covered", "evidence": f"mock {stage}"}
        ]
    return output


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="solution_golden_"))
    dispatcher = _SolutionDispatcher(
        topic="设计一个固定十阶段验证系统",
        solution_type="architecture",
        mode="standard",
        constraints=["固定10阶段", "统一4维评分"],
        stakeholders=["架构师"],
    )
    dispatcher.session_id = "golden_session"
    dispatcher.base_path = str(temp_root)
    dispatcher.blackboard = FakeBlackboard(temp_root)
    (temp_root / "stages").mkdir(parents=True, exist_ok=True)
    (temp_root / "data").mkdir(parents=True, exist_ok=True)
    write_frozen_spec(temp_root, dispatcher.topic, dispatcher.constraints, dispatcher.living_spec)

    dispatcher.save_tasks()
    dispatcher.save_execution_plan()

    planning = {
        "required_experts": [
            {"name": "security_expert", "angle": "安全架构", "reason": "验证 expert_1 槽位映射"},
            {"name": "cost_expert", "angle": "成本优化", "reason": "验证 expert_2 槽位映射"},
            {"name": "ops_expert", "angle": "运维可靠性", "reason": "验证 expert_3 槽位映射"},
        ],
        "layer2_constraints": {
            "auditor": ["必须检查固定10阶段输出完整性"],
            "fixer": ["修复必须保持4维评分一致"],
        },
        "audit_strategy": "strict",
    }
    write_json(temp_root / "stages" / "planning.json", planning)
    rewrite_after_planning(str(temp_root))

    plan = json.loads((temp_root / "execution_plan.json").read_text(encoding="utf-8"))
    expected = _expected_outputs_from_plan(plan)

    for stage, paths in expected.items():
        for rel_path in paths:
            path = temp_root / rel_path
            if rel_path.endswith(".md"):
                path.write_text("# Mock final solution\n", encoding="utf-8")
            else:
                write_json(path, stage_output(stage))
    (temp_root / "final_solution.md").write_text("# Mock final solution\n", encoding="utf-8")
    write_json(temp_root / "final_result.json", {
        "status": "completed",
        "summary": "Mock final result",
        "covered_req_ids": ["REQ-001"],
    })
    write_json(temp_root / "requirements_traceability_matrix.json", {
        "version": "1.0",
        "requirements": {
            "REQ-001": {
                "status": "covered",
                "evidence": [
                    {"stage": "planning", "path": "stages/planning.json"},
                    {"stage": "summarizer", "path": "stages/summarizer.json"},
                ],
            }
        },
    })

    result = _check_expected_outputs(
        temp_root,
        expected,
        required_artifacts=[
            "requirements_traceability_matrix.json",
            "final_result.json",
            "final_solution.md",
        ],
    )
    contract = json.loads((temp_root / "control_contract.json").read_text(encoding="utf-8"))
    tasks = json.loads((temp_root / "tasks.json").read_text(encoding="utf-8"))

    output = {
        "status": "ok" if result["status"] == "completed" else "failed",
        "base_path": str(temp_root),
        "completion": result,
        "phase_count": len(plan.get("phases", [])),
        "research_task_keys": list(tasks.get("research", {}).keys()),
        "contract_worker_ids": [w["id"] for w in contract.get("research_workers", [])],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
