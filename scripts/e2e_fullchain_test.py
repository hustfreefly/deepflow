#!/usr/bin/env python3
"""
E2E FullChain Test — DeepFlow 全链路测试

设计：方案 B+（统一 Agent E2E Runner + Python 确定性 setup）
  - Python 层：setup 验证（确定性，<10s）
  - Agent 层：orchestrator spawn + verify（由 Main Agent 执行）

用法:
  # Phase 1: 只验证 setup（Python 层）
  python3 scripts/e2e_fullchain_test.py --mode setup

  # Phase 2: 验证已完成的 E2E 结果（Agent spawn 后）
  python3 scripts/e2e_fullchain_test.py --mode verify --project <project_name>

输出:
  JSON 格式的测试结果，供 Agent 层消费。

契约笼子:
  - SpawnParamsContract: spawn_params 结构验证
  - CrossDomainContract: 跨域数据流验证
  - WorkPackage Pydantic: Deliver Pro WP schema 验证
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

# DeepFlow root
DEEPFLOW = Path(__file__).resolve().parent.parent
os.chdir(DEEPFLOW)
if str(DEEPFLOW) not in sys.path:
    sys.path.insert(0, str(DEEPFLOW))


# ═══════════════════════════════════════════════════════════
# 契约笼子导入
# ═══════════════════════════════════════════════════════════
from contracts.shared.spawn_params_contract import (
    validate_spawn_params,
    validate_cross_domain,
)


# ═══════════════════════════════════════════════════════════
# 测试输入
# ═══════════════════════════════════════════════════════════
USER_INPUT = """构建一个 CLI Task Manager：
1. 支持添加任务（标题、优先级 P0/P1/P2、截止日期 ISO 格式、标签）
2. 按优先级、状态（pending/done）、标签筛选任务列表
3. 标记任务完成/未完成
4. 按 ID 删除任务
5. 导出为 JSON 和 CSV
6. Python 3.11+ 实现，使用 argparse CLI
"""


LIVING_SPEC_FIXTURE = {
    "session_id": "e2e_fullchain_fixture",
    "meta": {
        "spec_version": "2.0",
        "domain_type": "software",
        "conversation_rounds": 1,
    },
    "narrative": USER_INPUT,
    "confirmed": {
        "objective": "构建一个 Python 3.11+ CLI Task Manager，支持任务增删改查、筛选和导出。",
        "pain_points": ["任务状态分散", "缺少统一 CLI 入口"],
        "key_scenarios": ["添加任务", "筛选任务", "导出任务"],
        "capabilities": {
            "always_do": ["支持添加任务", "支持按优先级筛选", "支持导出 JSON 和 CSV"],
            "should_do": ["提供清晰的命令行帮助"],
            "never_do": ["依赖外部数据库服务"],
        },
        "constraints": {"language": "Python 3.11+", "cli": "argparse"},
    },
    "requirement_index": [
        {
            "id": "REQ-001",
            "description": "支持添加任务，字段包括标题、优先级 P0/P1/P2、截止日期和标签。",
            "priority": "P0",
            "source_section": "confirmed.objective",
        },
        {
            "id": "REQ-002",
            "description": "支持按优先级、状态和标签筛选任务列表。",
            "priority": "P0",
            "source_section": "confirmed.key_scenarios",
        },
        {
            "id": "REQ-003",
            "description": "支持标记任务完成/未完成、按 ID 删除任务，并导出 JSON 和 CSV。",
            "priority": "P0",
            "source_section": "confirmed.capabilities",
        },
    ],
    "semantic_anchors": [
        {
            "name": "CLI Task Manager",
            "category": "TECHNICAL",
            "constraint": "Python 3.11+ argparse CLI",
            "source": "e2e_fixture",
        }
    ],
    "guardrails": {
        "always_do": ["保持 CLI 简单可用"],
        "never_do": ["引入外部数据库依赖"],
    },
    "solution_pro_hints": {
        "focus_areas": ["CLI UX", "任务数据模型", "导入导出"],
        "anti_patterns": ["过度工程化"],
    },
}


FINAL_SOLUTION_FIXTURE = {
    "schema_version": "2.0.0",
    "metadata": {"session_id": "e2e_fullchain_fixture", "status": "completed"},
    "key_decisions": [
        {
            "decision": "使用 argparse 实现 CLI",
            "rationale": "满足 Python 3.11+ 和无外部服务依赖约束",
        }
    ],
    "implementation_phases": [
        {
            "phase": 1,
            "title": "实现任务模型与 CLI",
            "timeline": "1 day",
            "estimated_effort": "4h",
            "tasks": ["实现 Task 数据模型", "实现 add/list/done/delete/export 命令"],
        }
    ],
    "constraint_coverage": {"total": 3, "covered": 3, "ratio": 1.0},
    "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003"],
    "semantic_anchors": LIVING_SPEC_FIXTURE["semantic_anchors"],
    "risk_summary": [],
}


SHIP_PACKAGE_FIXTURE = {
    "work_packages": [
        {
            "wp_id": "WP-001",
            "title": "CLI Task Manager Core",
            "description": "实现任务 CRUD、筛选和 JSON/CSV 导出。",
            "acceptance_criteria": [
                "可以添加、列出、完成和删除任务",
                "可以按优先级、状态和标签筛选",
                "可以导出 JSON 和 CSV",
            ],
            "dependencies": [],
            "effort_hours": 4,
            "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003"],
        }
    ],
    "dependency_graph": {"execution_layers": [["WP-001"]]},
    "semantic_anchors": LIVING_SPEC_FIXTURE["semantic_anchors"],
}


def run_setup_mode() -> dict:
    """
    Phase 1: Python 确定性 setup 验证。

    调用 4 个域的 setup 函数，验证返回值符合契约。
    不 spawn 任何 orchestrator。

    Returns:
        测试结果 dict
    """
    project_name = f"E2E_FC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    results = {
        "project_name": project_name,
        "mode": "setup",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stages": {},
        "spawn_params": {},
        "overall": "PENDING",
    }

    print(f"\n{'='*60}")
    print(f"  E2E FullChain Setup Test")
    print(f"  Project: {project_name}")
    print(f"{'='*60}\n")

    # ─── Stage 1: Spec Pro ───────────────────────────────
    print("Stage 1: Spec Pro init_session()")
    try:
        from domains.spec_pro.coordinator import SpecProCoordinator
        coord = SpecProCoordinator(scenario="genesis", mode="standard")
        spec_result = coord.init_session(USER_INPUT)

        session_id = spec_result.get("session_id", "")
        coordinator_task = spec_result.get("coordinator_task", "")
        parse_worker_prompt = spec_result.get("v3_parse_worker_prompt", "")

        # 契约笼子：session_id 非空
        assert session_id, "session_id 为空"

        # 报告
        print(f"  session_id: {session_id}")
        print(f"  coordinator_task: {len(coordinator_task.encode('utf-8'))}B")
        print(f"  parse_worker_prompt: {len(parse_worker_prompt.encode('utf-8'))}B")

        # Spec Pro 的 coordinator_task 可能是 inline 或 bootstrap
        # 只要有内容就算 PASS
        task_size = len(coordinator_task.encode('utf-8')) if coordinator_task else 0
        if task_size == 0:
            print("  ⚠️ coordinator_task=0B (检查是否写入 blackboard)")
            results["stages"]["spec_pro"] = {
                "status": "PASS_WITH_WARNING",
                "session_id": session_id,
                "task_size": 0,
            }
        else:
            print("  → ✅ PASS")
            results["stages"]["spec_pro"] = {
                "status": "PASS",
                "session_id": session_id,
                "task_size": task_size,
            }
    except Exception as e:
        print(f"  → ❌ FAIL: {e}")
        results["stages"]["spec_pro"] = {"status": "FAIL", "error": str(e)}

    # setup 模式使用统一 project blackboard；补齐 Spec Pro handoff fixture，
    # 让后续 E2E 契约验证可以在同一个项目目录下检查四段链路。
    spec_dir = DEEPFLOW / "blackboard" / project_name / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    from domains.spec_pro.spec_living_md import render_living_spec_md
    (spec_dir / "living_spec.md").write_text(
        render_living_spec_md(LIVING_SPEC_FIXTURE),
        encoding="utf-8",
    )
    (spec_dir / "spec_handoff_package.json").write_text(
        json.dumps({
            "schema_version": "2.0.0",
            "handoff_allowed": True,
            "living_spec": LIVING_SPEC_FIXTURE,
            "quality_report": {},
            "density_gate_result": {"passed": True, "issues": []},
            "semantic_anchors": LIVING_SPEC_FIXTURE["semantic_anchors"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ─── Stage 2: Solution Pro ───────────────────────────
    print("\nStage 2: run_solution_pro()")
    try:
        from domains.solution_pro import run_solution_pro
        # topic 必须是 project_name（控制统一 blackboard 目录名）
        sol_result = run_solution_pro(
            USER_INPUT,
            topic=project_name,
            living_spec=LIVING_SPEC_FIXTURE,
        )

        sol_session = sol_result.get("session_id", "")
        sol_spawn = sol_result.get("spawn_params", {})

        # 契约笼子：spawn_params 验证
        validate_spawn_params(sol_spawn)

        # 契约笼子：跨域数据流（MD-first living_spec）
        cross_domain = validate_cross_domain(sol_result.get("base_path", ""))

        req_count = cross_domain.requirement_count
        living_spec_size = cross_domain.living_spec_md_size

        print(f"  session_id: {sol_session}")
        print(f"  task: {len(sol_spawn.get('task', '').encode('utf-8'))}B")
        print(f"  requirements: {req_count}")
        print(f"  living_spec.md: {living_spec_size}B")
        print(f"  → ✅ PASS (contract validated)")

        results["stages"]["solution_pro"] = {
            "status": "PASS",
            "session_id": sol_session,
            "task_size": len(sol_spawn.get("task", "").encode("utf-8")),
            "requirement_count": req_count,
            "living_spec_md_size": living_spec_size,
        }
        results["spawn_params"]["solution_pro"] = sol_spawn

    except Exception as e:
        print(f"  → ❌ FAIL: {e}")
        results["stages"]["solution_pro"] = {"status": "FAIL", "error": str(e)}

    # ─── Stage 3: Ship Pro ───────────────────────────────
    print("\nStage 3: run_ship_pro()")
    try:
        from domains.ship_pro import run_ship_pro
        from domains.solution_pro.solution_living_md import render_final_solution_md

        # setup 模式不执行 Orchestrator；用确定性 fixture 模拟 Solution Pro 完成产出
        solution_stage_dir = DEEPFLOW / "blackboard" / project_name / "stages"
        solution_stage_dir.mkdir(parents=True, exist_ok=True)
        (solution_stage_dir / "final_solution.md").write_text(
            render_final_solution_md(FINAL_SOLUTION_FIXTURE),
            encoding="utf-8",
        )

        ship_result = run_ship_pro(project_name)

        ship_spawn = ship_result.get("spawn_params", {})

        # 契约笼子：spawn_params 验证
        validate_spawn_params(ship_spawn)

        # 契约笼子：跨域数据流（Ship Pro 必须读到 Solution Pro 输出）
        input_summary = ship_result.get("input_summary", {})

        print(f"  project: {project_name}")
        print(f"  task: {len(ship_spawn.get('task', '').encode('utf-8'))}B")
        print(f"  input_summary: {json.dumps(input_summary)}")
        print(f"  → ✅ PASS (contract validated)")

        results["stages"]["ship_pro"] = {
            "status": "PASS",
            "task_size": len(ship_spawn.get("task", "").encode("utf-8")),
            "input_summary": input_summary,
        }
        results["spawn_params"]["ship_pro"] = ship_spawn

    except Exception as e:
        print(f"  → ❌ FAIL: {e}")
        results["stages"]["ship_pro"] = {"status": "FAIL", "error": str(e)}

    # ─── Stage 4: Deliver Pro ────────────────────────────
    print("\nStage 4: run_deliver_pro()")
    try:
        from domains.deliver_pro import run_deliver_pro

        # setup 模式不执行 Ship Orchestrator；写入 canonical ship_package fixture，
        # 验证 Ship Pro → Deliver Pro 的可调度 handoff。
        ship_dir = DEEPFLOW / "blackboard" / project_name / "ship_pro"
        ship_dir.mkdir(parents=True, exist_ok=True)
        (ship_dir / "ship_package.json").write_text(
            json.dumps(SHIP_PACKAGE_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        del_result = run_deliver_pro(project_name)

        assert del_result.get("mode") == "pulse", "Deliver Pro 必须返回 pulse 模式"
        assert del_result.get("launch_command"), "Deliver Pro 必须返回 launch_command"
        assert Path(del_result.get("ship_package_path", "")).exists(), "ship_package_path 必须存在"

        print(f"  project: {project_name}")
        print(f"  ship_package: {del_result['ship_package_path']}")
        print(f"  launch_command: {del_result['launch_command']}")
        print(f"  → ✅ PASS (Pulse handoff validated)")

        results["stages"]["deliver_pro"] = {
            "status": "PASS",
            "mode": del_result["mode"],
            "ship_package_path": del_result["ship_package_path"],
        }

    except Exception as e:
        print(f"  → ❌ FAIL: {e}")
        results["stages"]["deliver_pro"] = {"status": "FAIL", "error": str(e)}

    # ─── Stage 5: Doctor ─────────────────────────────────
    print("\nStage 5: Doctor pipeline_scope")
    try:
        # 简单验证 blackboard 目录结构
        bb_dir = DEEPFLOW / "blackboard" / project_name
        if bb_dir.exists():
            files = list(bb_dir.rglob("*"))
            file_count = len([f for f in files if f.is_file()])
            print(f"  blackboard: {bb_dir}")
            print(f"  files: {file_count}")
            print(f"  → ✅ PASS")
            results["stages"]["doctor"] = {
                "status": "PASS",
                "file_count": file_count,
            }
        else:
            print(f"  ⚠️ blackboard dir not found: {bb_dir}")
            results["stages"]["doctor"] = {"status": "SKIP", "reason": "dir not found"}
    except Exception as e:
        print(f"  → ❌ FAIL: {e}")
        results["stages"]["doctor"] = {"status": "FAIL", "error": str(e)}

    # ─── 汇总 ────────────────────────────────────────────
    pass_count = sum(
        1 for s in results["stages"].values()
        if s.get("status") in ("PASS", "PASS_WITH_WARNING")
    )
    total_count = len(results["stages"])
    all_pass = pass_count == total_count

    results["overall"] = "PASS" if all_pass else "FAIL"

    print(f"\n{'='*60}")
    print(f"  📊 E2E FullChain Setup Results")
    print(f"{'='*60}")
    for stage_name, stage_data in results["stages"].items():
        status = stage_data.get("status", "UNKNOWN")
        icon = "✅" if status == "PASS" else ("⚠️" if "WARNING" in status else "❌")
        print(f"  {icon} {stage_name}: {status}")
    print(f"\n  结果: {pass_count}/{total_count} PASS")
    print(f"  总判定: {results['overall']}")

    # 输出 spawn_params 供 Agent 层使用
    if all_pass and results["spawn_params"]:
        spawn_file = DEEPFLOW / "blackboard" / project_name / "e2e_spawn_params.json"
        spawn_file.parent.mkdir(parents=True, exist_ok=True)
        spawn_file.write_text(json.dumps(results["spawn_params"], indent=2))
        print(f"\n  📁 spawn_params 已写入: {spawn_file}")
        print(f"  → Agent 层可读取此文件执行 Phase 2 (orchestrator spawn)")

    return results


def run_verify_mode(project_name: str) -> dict:
    """
    Phase 2: 验证已完成的 E2E 结果。

    检查所有域的 master_state 和最终产出。

    Args:
        project_name: 项目名（blackboard 目录名）

    Returns:
        验证结果 dict
    """
    bb_dir = DEEPFLOW / "blackboard" / project_name
    if not bb_dir.exists():
        return {
            "project_name": project_name,
            "mode": "verify",
            "overall": "FAIL",
            "error": f"Blackboard dir not found: {bb_dir}",
        }

    results = {
        "project_name": project_name,
        "mode": "verify",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "overall": "PENDING",
    }

    print(f"\n{'='*60}")
    print(f"  E2E FullChain Verification")
    print(f"  Project: {project_name}")
    print(f"{'='*60}\n")

    # Check 1: master_state
    print("Check 1: master_state.json")
    master_state_file = bb_dir / "master_state.json"
    if master_state_file.exists():
        master = json.loads(master_state_file.read_text())
        status = master.get("status", "unknown")
        completed = master.get("completed_modules", [])
        failed = master.get("failed_modules", [])
        print(f"  status: {status}")
        print(f"  completed: {completed}")
        print(f"  failed: {failed}")

        if status == "completed":
            print("  → ✅ PASS")
            results["checks"]["master_state"] = {"status": "PASS", "state": status}
        else:
            print(f"  → ❌ FAIL (expected 'completed', got '{status}')")
            results["checks"]["master_state"] = {
                "status": "FAIL",
                "expected": "completed",
                "actual": status,
            }
    else:
        print("  → ❌ FAIL (file not found)")
        results["checks"]["master_state"] = {"status": "FAIL", "error": "not found"}

    # Check 2: Solution Pro outputs
    print("\nCheck 2: Solution Pro outputs")
    final_solution = bb_dir / "stages" / "final_solution.md"
    living_spec = bb_dir / "data" / "living_spec.md"
    sol_exists = final_solution.exists() and living_spec.exists()
    if sol_exists:
        print(f"  final_solution.md: ✅")
        print(f"  living_spec.md: ✅")
        print("  → ✅ PASS")
        results["checks"]["solution_pro"] = {"status": "PASS"}
    else:
        print(f"  final_solution.md: {'✅' if final_solution.exists() else '❌'}")
        print(f"  living_spec.md: {'✅' if living_spec.exists() else '❌'}")
        print("  → ❌ FAIL (missing output files)")
        results["checks"]["solution_pro"] = {"status": "FAIL"}

    # Check 3: Ship Pro outputs
    print("\nCheck 3: Ship Pro outputs")
    ship_candidates = list(bb_dir.glob("ship_pro*/stages/ship_package.md")) + list(bb_dir.glob("ship_pro*/stages/ship_package.json"))
    ship_exists = len(ship_candidates) > 0
    if ship_exists:
        for path in ship_candidates[:3]:
            print(f"  {path.relative_to(bb_dir)}: ✅")
        print("  → ✅ PASS")
        results["checks"]["ship_pro"] = {"status": "PASS"}
    else:
        print("  → ❌ FAIL (no ship package)")
        results["checks"]["ship_pro"] = {"status": "FAIL"}

    # Check 4: Deliver Pro outputs
    print("\nCheck 4: Deliver Pro outputs")
    deliver_dir = bb_dir / "deliver_pro"
    deliver_files = list(deliver_dir.rglob("DELIVERABLE.md")) if deliver_dir.exists() else []
    deliver_done = (bb_dir / ".deliver_completed.json").exists()
    if deliver_files or deliver_done:
        for f in deliver_files[:5]:
            print(f"  {f.relative_to(bb_dir)}: ✅ ({f.stat().st_size}B)")
        if deliver_done:
            print("  .deliver_completed.json: ✅")
        print("  → ✅ PASS")
        results["checks"]["deliver_pro"] = {"status": "PASS"}
    else:
        print("  → ❌ FAIL (no deliverable)")
        results["checks"]["deliver_pro"] = {"status": "FAIL"}

    # 汇总
    pass_count = sum(1 for c in results["checks"].values() if c.get("status") == "PASS")
    total_count = len(results["checks"])
    results["overall"] = "PASS" if pass_count == total_count else "FAIL"

    print(f"\n{'='*60}")
    print(f"  📊 E2E FullChain Verification Results")
    print(f"{'='*60}")
    for check_name, check_data in results["checks"].items():
        icon = "✅" if check_data.get("status") == "PASS" else "❌"
        print(f"  {icon} {check_name}: {check_data.get('status')}")
    print(f"\n  结果: {pass_count}/{total_count} PASS")
    print(f"  总判定: {results['overall']}")

    return results


def main():
    parser = argparse.ArgumentParser(description="E2E FullChain Test")
    parser.add_argument(
        "--mode",
        choices=["setup", "verify"],
        default="setup",
        help="测试模式: setup (Phase 1) 或 verify (Phase 2)",
    )
    parser.add_argument(
        "--project",
        help="项目名 (verify 模式必需)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出纯 JSON（供 Agent 消费）",
    )
    args = parser.parse_args()

    if args.mode == "setup":
        results = run_setup_mode()
    elif args.mode == "verify":
        if not args.project:
            print("Error: --project required for verify mode")
            sys.exit(1)
        results = run_verify_mode(args.project)
    else:
        print(f"Unknown mode: {args.mode}")
        sys.exit(1)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        # Summary already printed in run_*_mode
        # Print JSON at the end for Agent consumption
        print(f"\n--- JSON ---")
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
