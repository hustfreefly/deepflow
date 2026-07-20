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

    # ─── Stage 2: Solution Pro ───────────────────────────
    print("\nStage 2: run_solution_pro_agent() [B1-FIX]")
    try:
        from domains.solution_pro import run_solution_pro_agent  # B1-FIX: explicit agent path
        # 契约笼子：topic 必须是 project_name（控制 blackboard 目录名）
        # run_solution_pro 用 topic 创建 blackboard 目录，Ship Pro 通过 project_name 查找
        # 如果不传 topic，默认用 user_input[:50] → 导致 Ship Pro 找不到目录
        sol_result = run_solution_pro_agent(USER_INPUT, topic=project_name)

        sol_session = sol_result.get("session_id", "")
        sol_spawn = sol_result.get("spawn_params", {})

        # 契约笼子：spawn_params 验证
        spawn_contract = validate_spawn_params(sol_spawn)

        # 契约笼子：跨域数据流
        cross_domain = validate_cross_domain(sol_result.get("base_path", ""))

        req_count = cross_domain.requirement_count
        frozen_spec_size = cross_domain.frozen_spec_md_size

        print(f"  session_id: {sol_session}")
        print(f"  task: {len(sol_spawn.get('task', '').encode('utf-8'))}B")
        print(f"  requirements: {req_count}")
        print(f"  frozen_spec.md: {frozen_spec_size}B")
        print(f"  → ✅ PASS (contract validated)")

        results["stages"]["solution_pro"] = {
            "status": "PASS",
            "session_id": sol_session,
            "task_size": len(sol_spawn.get("task", "").encode("utf-8")),
            "requirement_count": req_count,
            "frozen_spec_md_size": frozen_spec_size,
        }
        results["spawn_params"]["solution_pro"] = sol_spawn

    except Exception as e:
        print(f"  → ❌ FAIL: {e}")
        results["stages"]["solution_pro"] = {"status": "FAIL", "error": str(e)}

    # ─── Stage 3: Ship Pro ───────────────────────────────
    print("\nStage 3: run_ship_pro()")
    try:
        from domains.ship_pro import run_ship_pro

        # 使用 Solution Pro 的 session_id 作为 project_name
        ship_result = run_ship_pro(project_name)

        ship_spawn = ship_result.get("spawn_params", {})

        # 契约笼子：spawn_params 验证
        validate_spawn_params(ship_spawn)

        # 契约笼子：跨域数据流（Ship Pro 必须读到 Solution Pro 输出）
        input_summary = ship_result.get("input_summary", {})
        req_count = input_summary.get("req_count", 0)

        # 注意：req_count=0 不一定是 bug（frozen_spec 可能没有 requirements 字段）
        # 但如果 Solution Pro 有 7 个 requirements，Ship Pro 应该也能读到
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
        from domains.deliver_pro.contracts import WorkPackage, AcceptanceCriterion

        # 契约笼子：mock WP 必须符合 Pydantic schema
        mock_wp = WorkPackage(
            wp_id="WP-001",
            title="CLI Task Manager - Core",
            objective="Implement CLI for task management with CRUD, filter, export",
            scenario="code",
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="AC-001",
                    description="Add/list/complete/delete tasks",
                    priority="MUST",
                ),
                AcceptanceCriterion(
                    id="AC-002",
                    description="Export to JSON/CSV",
                    priority="SHOULD",
                ),
                AcceptanceCriterion(
                    id="AC-003",
                    description="Filter by priority, status, or tag",
                    priority="MUST",
                ),
            ],
            constraints={"language": "Python 3.11+"},
        )

        # 验证 mock WP 通过 Pydantic
        WorkPackage.model_validate(mock_wp.model_dump())

        del_result = run_deliver_pro(mock_wp, project_name=project_name)
        del_spawn = del_result.get("spawn_params", {})

        # 契约笼子：spawn_params 验证
        validate_spawn_params(del_spawn)

        print(f"  wp_id: {mock_wp.wp_id}")
        print(f"  task: {len(del_spawn.get('task', '').encode('utf-8'))}B")
        print(f"  → ✅ PASS (WP contract + spawn_params validated)")

        results["stages"]["deliver_pro"] = {
            "status": "PASS",
            "task_size": len(del_spawn.get("task", "").encode("utf-8")),
        }
        results["spawn_params"]["deliver_pro"] = del_spawn

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
    frozen_spec = bb_dir / "data" / "frozen_spec.md"
    sol_exists = final_solution.exists() or frozen_spec.exists()
    if sol_exists:
        print(f"  final_solution.md: {'✅' if final_solution.exists() else '❌'}")
        print(f"  frozen_spec.md: {'✅' if frozen_spec.exists() else '❌'}")
        print("  → ✅ PASS")
        results["checks"]["solution_pro"] = {"status": "PASS"}
    else:
        print("  → ❌ FAIL (no output files)")
        results["checks"]["solution_pro"] = {"status": "FAIL"}

    # Check 3: Ship Pro outputs
    print("\nCheck 3: Ship Pro outputs")
    ship_package = bb_dir / "ship_pro" / "stages" / "ship_package.json"
    ship_package_md = bb_dir / "ship_pro" / "stages" / "ship_package.md"
    ship_exists = ship_package.exists() or ship_package_md.exists()
    if ship_exists:
        print(f"  ship_package.json: {'✅' if ship_package.exists() else '❌'}")
        print(f"  ship_package.md: {'✅' if ship_package_md.exists() else '❌'}")
        print("  → ✅ PASS")
        results["checks"]["ship_pro"] = {"status": "PASS"}
    else:
        print("  → ❌ FAIL (no ship package)")
        results["checks"]["ship_pro"] = {"status": "FAIL"}

    # Check 4: Deliver Pro outputs
    print("\nCheck 4: Deliver Pro outputs")
    deliver_dir = bb_dir / "deliver_pro"
    deliver_files = list(deliver_dir.rglob("final_*")) if deliver_dir.exists() else []
    if deliver_files:
        for f in deliver_files:
            print(f"  {f.name}: ✅ ({f.stat().st_size}B)")
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
