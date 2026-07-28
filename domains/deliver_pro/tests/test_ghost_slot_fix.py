"""Ghost-Slot Fix V2.0 测试（2026-07-29）

覆盖 F1/F2/F3/F5 修复：
- F1a: budget=0 分支清理孤儿目录
- F1b: 无记录孤儿空目录 sweep
- F2: 非 worker dispatch 证据化计数
- F3a/b/c: blocked 级联三道守卫
- F5: worker label WP 前缀 + confirm 解析
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domains.deliver_pro.orchestrator import (
    DeliverOrchestrator,
    MAX_SPAWN_PER_PULSE,
    RECORDLESS_ORPHAN_GRACE_SECONDS,
    RETRY_BUDGET,
)
from domains.deliver_pro.tests.test_pulse import (  # noqa: F401  (复用 helpers)
    _make_orchestrator,
    _setup_generating_wp,
    _mock_driver_for_retry,
    _wp_dir,
)


# ---------------------------------------------------------------------------
# Fixtures（test_pulse.py 的 fixture 不跨模块可见，此处复制定义）
# ---------------------------------------------------------------------------

@pytest.fixture
def ship_package_data():
    return {
        "work_packages": [
            {"wp_id": "AAA-001", "dependencies": [], "title": "Alpha"},
            {"wp_id": "BBB-001", "dependencies": [], "title": "Beta"},
        ],
        "dependency_graph": {
            "execution_layers": [["AAA-001", "BBB-001"]],
        },
    }


@pytest.fixture
def mock_blackboard(tmp_path, ship_package_data):
    project_name = "test-pulse"
    bb_root = tmp_path / "blackboard"
    ship_dir = bb_root / project_name / "ship_pro" / "stages"
    ship_dir.mkdir(parents=True)
    (ship_dir / "ship_package.json").write_text(json.dumps(ship_package_data))
    return bb_root, project_name


# ---------------------------------------------------------------------------
# F1a: budget=0 分支清理孤儿目录
# ---------------------------------------------------------------------------

class TestBudgetZeroNoOrphans:
    def test_budget_zero_leaves_no_orphan_dirs(self, mock_blackboard):
        """budget=0 时 params 已构建（mkdir 副作用）→ 必须清理空目录。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"]
            )
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=()
            )
            # step3_workers 返回 2 个 ready task 的 params（模拟 params 构建 + mkdir）
            wo = stages / "worker_outputs"

            def _build_with_side_effect(task_node, _plan):
                (wo / task_node.task_id).mkdir(parents=True, exist_ok=True)
                return {
                    "task_id": task_node.task_id,
                    "label": f"deliver-worker-aaa-001-{task_node.task_id.lower()}",
                    "task": f"do {task_node.task_id}",
                    "mode": "run",
                }

            driver.orch._prepare_single_worker_spawn.side_effect = _build_with_side_effect
            driver.step3_workers.return_value = [
                {"task_id": "T-001", "label": "deliver-worker-aaa-001-t-001", "task": "x", "mode": "run"},
                {"task_id": "T-002", "label": "deliver-worker-aaa-001-t-002", "task": "x", "mode": "run"},
            ]
            # 手工造出 params 构建时的副作用目录（模拟真实 driver 行为）
            (wo / "T-001").mkdir(parents=True, exist_ok=True)
            (wo / "T-002").mkdir(parents=True, exist_ok=True)

            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=99):  # budget=0
                report = orch.pulse()

            assert report["summary"]["in_flight"] == 99
            # F1a：budget=0 清理后不应留下空目录
            assert not (wo / "T-001").exists(), "budget=0 应清理 T-001 空目录"
            assert not (wo / "T-002").exists(), "budget=0 应清理 T-002 空目录"


# ---------------------------------------------------------------------------
# F1b: 无记录孤儿空目录 sweep
# ---------------------------------------------------------------------------

class TestRecordlessOrphanSweep:
    def test_recordless_empty_dir_swept_after_grace(self, mock_blackboard):
        """空目录 + 无 task_spawned_at + 年龄>5min → 被清扫。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"]
            )
            wo = stages / "worker_outputs"
            orphan = wo / "T-009"
            orphan.mkdir(parents=True)
            # 把 mtime 调到 10 分钟前（超过 5min 宽限）
            old = time.time() - 600
            import os
            os.utime(orphan, (old, old))

            orch._orphan_sweep()
            assert not orphan.exists(), "无记录空孤儿目录应被 F1b 清扫"

    def test_recorded_dir_exempt(self, mock_blackboard):
        """有 task_spawned_at 记录的空目录 → 豁免（真 worker 可能慢启动）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"]
            )
            wo = stages / "worker_outputs"
            legit = wo / "T-001"
            legit.mkdir(parents=True)
            orch.progress["AAA-001"] = {
                "task_spawned_at": {"T-001": time.time() - 3600}  # 即使有记录很久也豁免
            }

            orch._orphan_sweep()
            assert legit.exists(), "有 spawn 记录的目录不应被 F1b 清扫"

    def test_nonempty_dir_exempt(self, mock_blackboard):
        """非空目录（worker 已写产出）→ 豁免。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"]
            )
            wo = stages / "worker_outputs"
            productive = wo / "T-008"
            productive.mkdir(parents=True)
            (productive / "output.md").write_text("real output")
            import os
            old = time.time() - 600
            os.utime(productive, (old, old))

            orch._orphan_sweep()
            assert productive.exists(), "非空目录不应被 F1b 清扫"


# ---------------------------------------------------------------------------
# F2: 非 worker dispatch 证据化计数
# ---------------------------------------------------------------------------

class TestEvidenceBasedInFlight:
    def test_analyze_evidence_releases_slot(self, mock_blackboard):
        """analyze confirmed + execution_plan.json 存在 → 不计 in_flight。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001"]
            )
            # plan 已存在（_setup_generating_wp 已写）= analyze 完成证据
            orch.progress["AAA-001"] = {
                "last_spawned_action": "analyze",
                "last_spawned_at": time.time(),  # 新鲜（30min 内）
                "dispatch_confirmed": True,
            }
            n = orch._count_in_flight()
            assert n == 0, f"plan 存在时 analyze dispatch 不应计数，got {n}"

    def test_validate_evidence_releases_slot(self, mock_blackboard):
        """validate confirmed + validation_result.json 存在 → 不计。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001"]
            )
            (stages / "validation_result.json").write_text(json.dumps({"verdict": "PASS"}))
            orch.progress["AAA-001"] = {
                "last_spawned_action": "validate",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": True,
            }
            n = orch._count_in_flight()
            assert n == 0, f"validation_result 存在时 validate dispatch 不应计数，got {n}"

    def test_no_evidence_still_counts(self, mock_blackboard):
        """无证据文件 + 未超时 → 仍计数（agent 可能还在跑）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            orch.progress["AAA-001"] = {
                "last_spawned_action": "validate",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": True,
            }
            n = orch._count_in_flight()
            assert n == 1, f"无证据时 validate dispatch 应计数，got {n}"

    def test_package_evidence_releases_slot(self, mock_blackboard):
        """package confirmed + delivery_manifest.json 存在 → 不计。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001"]
            )
            (stages / "delivery_manifest.json").write_text(json.dumps({"status": "DONE"}))
            orch.progress["AAA-001"] = {
                "last_spawned_action": "package",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": True,
            }
            n = orch._count_in_flight()
            assert n == 0, f"delivery_manifest 存在时 package dispatch 不应计数，got {n}"


# ---------------------------------------------------------------------------
# F3a: GENERATING 分支级联守卫
# ---------------------------------------------------------------------------

class TestCascadeGuardGenerating:
    def test_all_done_blocked_by_retriable_timed_out(self, mock_blackboard):
        """all_done=True 但存在 timed_out(attempts<budget) → 不进 assemble，走重试。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timeout_task="T-002"
            )
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=("T-002",)
            )
            driver.step4_check_workers.return_value = (True, {})  # all_done=True！
            orch.progress["AAA-001"] = {"task_attempts": {"T-002": 1}}
            with patch.object(orch, "_get_driver", return_value=driver):
                action = orch._get_wp_next_action("AAA-001")
            # F3a：应被拦截，走 spawn_workers（重试）而非 assemble
            assert action["action"] == "spawn_workers", \
                f"F3a 应拦截 assemble，got {action['action']}"

    def test_all_done_passes_when_no_retriable(self, mock_blackboard):
        """all_done=True 且无 retriable timed_out → 正常 assemble。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_generating_wp(bb_root, project, "AAA-001", ["T-001", "T-002"])
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=()
            )
            driver.step4_check_workers.return_value = (True, {})
            orch.progress["AAA-001"] = {}
            with patch.object(orch, "_get_driver", return_value=driver):
                action = orch._get_wp_next_action("AAA-001")
            assert action["action"] == "assemble", \
                f"无 retriable 时应正常 assemble，got {action['action']}"

    def test_manifest_failed_no_deadlock(self, mock_blackboard):
        """MANIFEST-FAILED 任务不触发守卫（防死锁回归）——只查 timed_out 子集。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"]
            )
            # T-002 写 MANIFEST FAILED（真跑过但失败）——不是 timed_out
            t2 = stages / "worker_outputs" / "T-002"
            t2.mkdir(parents=True, exist_ok=True)
            (t2 / "MANIFEST.json").write_text(json.dumps({
                "task_id": "T-002", "status": "FAILED",
                "failure_reason": "real worker failure",
                "completed_at": time.time(),
            }))
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=()
            )
            driver.step4_check_workers.return_value = (True, {})
            orch.progress["AAA-001"] = {"task_attempts": {"T-002": 1}}
            with patch.object(orch, "_get_driver", return_value=driver):
                action = orch._get_wp_next_action("AAA-001")
            # MANIFEST-FAILED 不归 retry 管 → 守卫不触发 → 正常 assemble（不死锁）
            assert action["action"] == "assemble", \
                f"MANIFEST-FAILED 不应触发守卫（死锁），got {action['action']}"


# ---------------------------------------------------------------------------
# F3c: 终态写入前守卫（PACKAGING 分支）
# ---------------------------------------------------------------------------

class TestTerminalWriteGuard:
    def test_packaging_blocked_by_unexecuted_tasks(self, mock_blackboard):
        """PACKAGING 阶段存在从未执行的任务 → 拒绝 package，回退重跑。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            _setup_generating_wp(bb_root, project, "AAA-001", ["T-001", "T-002"])
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=()
            )
            # T-002: ready（无依赖或依赖已 complete）+ attempts=0 + 无 MANIFEST
            driver.orch._derive_worker_progress.return_value = {
                "completed": {"T-001"},
                "running": set(),
                "failed": set(),
                "blocked": set(),
                "timed_out": set(),
                "pending": {"T-002"},
                "failure_reasons": {},
            }
            orch.progress["AAA-001"] = {"phase": "PACKAGING"}
            with patch.object(orch, "_check_wp_phase", return_value="PACKAGING"), \
                 patch.object(orch, "_get_driver", return_value=driver):
                action = orch._get_wp_next_action("AAA-001")
            assert action["action"] == "spawn_workers", \
                f"F3c 应拦截 package 回退重跑，got {action['action']}"

    def test_packaging_passes_when_all_executed(self, mock_blackboard):
        """所有任务都有执行证据 → 正常 package。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001"], timed_out=()
            )
            driver.orch._derive_worker_progress.return_value = {
                "completed": {"T-001"},
                "running": set(),
                "failed": set(),
                "blocked": set(),
                "timed_out": set(),
                "pending": set(),
                "failure_reasons": {},
            }
            driver.step7_package.return_value = {"task": "package it", "mode": "run"}
            orch.progress["AAA-001"] = {"phase": "PACKAGING"}
            with patch.object(orch, "_check_wp_phase", return_value="PACKAGING"), \
                 patch.object(orch, "_get_driver", return_value=driver):
                action = orch._get_wp_next_action("AAA-001")
            assert action["action"] == "package", \
                f"全部执行完应正常 package，got {action['action']}"


# ---------------------------------------------------------------------------
# F5: label WP 前缀 + confirm 解析
# ---------------------------------------------------------------------------

class TestLabelWpPrefix:
    def test_confirm_rollback_with_wp_prefixed_label(self, mock_blackboard):
        """新格式 label（deliver-worker-{wp}-{task}）confirm 回滚解析正确。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            orch.progress["AAA-001"] = {
                "last_spawned_action": "spawn_workers:T-001,T-002",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": False,
                "task_attempts": {"T-001": 1, "T-002": 1},
                "task_spawned_at": {"T-001": time.time(), "T-002": time.time()},
            }
            out = orch.confirm_dispatches([
                {"wp_id": "AAA-001", "label": "deliver-worker-aaa-001-t-001", "ok": True, "error": None},
                {"wp_id": "AAA-001", "label": "deliver-worker-aaa-001-t-002", "ok": False, "error": "429"},
            ])
            assert out["confirmed"] == 1
            assert out["rolled_back"] == 1
            entry = orch.progress["AAA-001"]
            # T-002 被移除，T-001 保留
            assert "T-002" not in entry.get("last_spawned_action", "")
            assert "T-001" in entry.get("last_spawned_action", "")

    def test_confirm_rollback_legacy_label_compatible(self, mock_blackboard):
        """旧格式 label（deliver-worker-{task}）向后兼容。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            orch.progress["AAA-001"] = {
                "last_spawned_action": "spawn_workers:T-001,T-002",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": False,
            }
            out = orch.confirm_dispatches([
                {"wp_id": "AAA-001", "label": "deliver-worker-t-002", "ok": False, "error": "429"},
            ])
            assert out["rolled_back"] == 1
            entry = orch.progress["AAA-001"]
            assert "T-002" not in entry.get("last_spawned_action", "")
