"""Tests for Pulse Scheduling V1（2026-07-24 评审裁决 A1-A8 落地）。

覆盖：
- A1: 原子写 / 单实例文件锁 / stale 锁告警
- A2: task 重试预算（重派 / 终态 MANIFEST）+ WP 终态 + all_resolved
- A3: derive 判 timed_out → 无视 stale dedup 直接重派
- A4: 两阶段 dispatch（orphan 窗口）+ 孤儿目录清扫 + spawn 回滚
- A5: MAX_IN_FLIGHT 并发上限截断
- A7: STALLED 零进展告警 + 冷却
- 契约笼子: PulseReport/PulseAction/SpawnConfirmation Pydantic 验证
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
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


@contextmanager
def _make_orchestrator(mock_blackboard):
    bb_root, project_name = mock_blackboard
    with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
        from domains.deliver_pro.orchestrator import DeliverOrchestrator
        orch = DeliverOrchestrator(project_name)
        yield orch, bb_root, project_name


def _wp_dir(bb_root, project_name, wp_id):
    return bb_root / project_name / "deliver_pro" / wp_id.lower().replace("-", "_")


def _setup_generating_wp(bb_root, project_name, wp_id, task_ids, timeout_task=None):
    """构造 GENERATING 状态的 WP：plan + 可选的超时 task 目录。"""
    stages = _wp_dir(bb_root, project_name, wp_id) / "stages"
    stages.mkdir(parents=True)
    plan = {
        "task_graph": [
            {"task_id": t, "depends_on": []} for t in task_ids
        ]
    }
    (stages / "execution_plan.json").write_text(json.dumps(plan))
    if timeout_task:
        task_dir = stages / "worker_outputs" / timeout_task
        task_dir.mkdir(parents=True)
        old = time.time() - 31 * 60  # 31min 前 → 超时
        os.utime(task_dir, (old, old))
    return stages


def _mock_driver_for_retry(bb_root, project_name, wp_id, task_ids, timed_out=()):
    """构造 GENERATING 分支用的 mock driver。"""
    driver = MagicMock()
    plan = SimpleNamespace(
        task_graph=[SimpleNamespace(task_id=t, depends_on=[]) for t in task_ids]
    )
    driver.orch.load_execution_plan.return_value = plan
    driver.orch._derive_worker_progress.return_value = {
        "completed": set(),
        "failed": set(timed_out),
        "blocked": set(),
        "running": set(),
        "pending": set(task_ids) - set(timed_out),
        "timed_out": set(timed_out),
        "failure_reasons": {},
    }
    driver.orch._prepare_single_worker_spawn.side_effect = lambda task_node, _plan: {
        "task_id": task_node.task_id,
        "label": f"deliver-worker-{task_node.task_id.lower()}",
        "task": f"do {task_node.task_id}",
        "mode": "run",
    }
    driver.worker_outputs_dir = (
        _wp_dir(bb_root, project_name, wp_id) / "stages" / "worker_outputs"
    )
    driver.step2_check_analyze.return_value = (True, {})
    driver.step4_check_workers.return_value = (False, {})
    driver.step3_workers.return_value = []
    return driver


# ---------------------------------------------------------------------------
# A1: 原子写 + 文件锁
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_save_progress_atomic_with_version(self, mock_blackboard):
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            orch.progress["AAA-001"] = {"phase": "PENDING"}
            orch._save_progress()
            data = json.loads((bb_root / project / "batch_progress.json").read_text())
            assert data["_meta"]["version"] == 1
            assert data["AAA-001"]["phase"] == "PENDING"
            # 无残留 .tmp 文件
            assert not list((bb_root / project).glob("*.tmp"))


class TestPulseLock:
    def test_second_pulse_locked(self, mock_blackboard):
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            fh = orch._acquire_pulse_lock()
            try:
                report = orch.pulse()
                assert report["status"] == "locked"
                assert report["actions"] == []
            finally:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()

    def test_stale_lock_alert(self, mock_blackboard):
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            fh = orch._acquire_pulse_lock()
            try:
                lock_path = bb_root / project / "_pulse.lock"
                old = time.time() - 11 * 60  # 11min 前
                os.utime(lock_path, (old, old))
                report = orch.pulse()
                assert report["status"] == "locked"
                assert any(a["code"] == "LOCK_STALE" for a in report["alerts"])
            finally:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()


# ---------------------------------------------------------------------------
# A4: 两阶段 dispatch
# ---------------------------------------------------------------------------

class TestTwoPhaseDispatch:
    def test_orphan_window_unconfirmed(self, mock_blackboard):
        with _make_orchestrator(mock_blackboard) as (orch, _, _p):
            now = time.time()
            # 未确认 + 11min → stale（orphan 窗口 10min）
            entry = {"last_spawned_at": now - 11 * 60, "dispatch_confirmed": False}
            assert orch._is_stale_dispatch(entry, "analyze") is True
            # 未确认 + 5min → 不 stale
            entry = {"last_spawned_at": now - 5 * 60, "dispatch_confirmed": False}
            assert orch._is_stale_dispatch(entry, "analyze") is False
            # 已确认 + 11min → 不 stale（analyze 窗口 30min）
            entry = {"last_spawned_at": now - 11 * 60, "dispatch_confirmed": True}
            assert orch._is_stale_dispatch(entry, "analyze") is False
            # 已确认 + 31min → stale
            entry = {"last_spawned_at": now - 31 * 60, "dispatch_confirmed": True}
            assert orch._is_stale_dispatch(entry, "analyze") is True
            # 已确认 + 31min spawn_workers → 不 stale（窗口 90min）
            entry = {"last_spawned_at": now - 31 * 60, "dispatch_confirmed": True}
            assert orch._is_stale_dispatch(entry, "spawn_workers") is False

    def test_orphan_sweep_drops_empty_dirs(self, mock_blackboard):
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001", "T-002"])
            empty_dir = stages / "worker_outputs" / "T-001"
            empty_dir.mkdir(parents=True)  # 空目录（params 生成时创建，spawn 未发生）
            orch.progress["AAA-001"] = {
                "last_spawned_action": "spawn_workers:T-001",
                "last_spawned_at": time.time() - 11 * 60,
                "dispatch_confirmed": False,
            }
            orch._orphan_sweep()
            assert not empty_dir.exists()  # 空目录已删除
            entry = orch.progress["AAA-001"]
            assert "last_spawned_action" not in entry

    def test_confirm_dispatches_ok_and_rollback(self, mock_blackboard):
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001", "T-002"])
            for t in ("T-001", "T-002"):
                (stages / "worker_outputs" / t).mkdir(parents=True)
            orch.progress["AAA-001"] = {
                "last_spawned_action": "spawn_workers:T-001,T-002",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": False,
            }
            out = orch.confirm_dispatches([
                {"wp_id": "AAA-001", "label": "deliver-worker-t-001", "ok": True, "error": None},
                {"wp_id": "AAA-001", "label": "deliver-worker-t-002", "ok": False, "error": "429"},
            ])
            assert out["confirmed"] == 1
            assert out["rolled_back"] == 1
            entry = orch.progress["AAA-001"]
            # T-002 从 dedup_key 移除，T-001 保留并部分确认
            assert entry["last_spawned_action"] == "spawn_workers:T-001"
            assert entry["dispatch_confirmed"] is True
            assert entry["spawn_failures"] == 1
            # T-002 空目录已删除 → 下次 pulse 可重派
            assert not (stages / "worker_outputs" / "T-002").exists()
            assert (stages / "worker_outputs" / "T-001").exists()


# ---------------------------------------------------------------------------
# A2/A3: 重试预算 + derive 判死直接重派
# ---------------------------------------------------------------------------

class TestRetryBudget:
    def test_timed_out_task_retried_immediately(self, mock_blackboard):
        """derive 判 timed_out → 无视 stale dedup 直接重派 + touch 目录 + attempts 记账。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timeout_task="T-001"
            )
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=("T-001",)
            )
            orch.progress["AAA-001"] = {"task_attempts": {"T-001": 2}}
            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()

            assert report["status"] == "active"
            labels = [a["label"] for a in report["actions"]]
            assert "deliver-worker-t-001" in labels
            # 目录已 touch → mtime 新鲜（derive 视为 running，防重复重派）
            mtime = (stages / "worker_outputs" / "T-001").stat().st_mtime
            assert time.time() - mtime < 60
            # attempts 记账：2 → 3
            assert orch.progress["AAA-001"]["task_attempts"]["T-001"] == 3
            assert any(a["code"] == "TASK_RETRY" for a in report["alerts"])

    def test_retry_budget_exceeded_terminal_manifest(self, mock_blackboard):
        """attempts >= RETRY_BUDGET → 合成 MANIFEST FAILED（终态），不再重派。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timeout_task="T-001"
            )
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=("T-001",)
            )
            orch.progress["AAA-001"] = {"task_attempts": {"T-001": 3}}
            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()

            # 合成 MANIFEST 已写入
            manifest = json.loads(
                (stages / "worker_outputs" / "T-001" / "MANIFEST.json").read_text()
            )
            assert manifest["status"] == "FAILED"
            assert "retry_budget_exceeded" in manifest["failure_reason"]
            # 不再重派
            assert all(a["label"] != "deliver-worker-t-001" for a in report["actions"])
            assert any(a["code"] == "TASK_RETRY_EXHAUSTED" for a in report["alerts"])


# ---------------------------------------------------------------------------
# A5: MAX_IN_FLIGHT
# ---------------------------------------------------------------------------

class TestInFlightCap:
    def test_budget_truncation(self, mock_blackboard):
        """in_flight=7 → 预算 1 → 2 个候选只派 1 个 + truncated + 告警。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            driver = MagicMock()
            driver.step1_analyze.side_effect = lambda: {
                "task": "analyze", "label": f"analyze-{id(driver)}", "mode": "run",
            }
            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=7):
                report = orch.pulse()

            assert len(report["actions"]) == 1
            assert report["summary"]["truncated"] is True
            assert report["summary"]["in_flight"] == 7
            assert any(a["code"] == "IN_FLIGHT_CAP" for a in report["alerts"])


# ---------------------------------------------------------------------------
# A2/P1-4: 终态 all_resolved
# ---------------------------------------------------------------------------

class TestAllResolved:
    def test_completed_marker_written(self, mock_blackboard):
        """1 DONE + 1 terminal_failed → all_resolved → .deliver_completed.json。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            # AAA-001 → DONE（Pulse V1.1 K3: 交付物必须 ≥50B）
            stages = _wp_dir(bb_root, project, "AAA-001") / "stages"
            (stages / "final_deliverable").mkdir(parents=True)
            (stages / "final_deliverable" / "out.md").write_text("x" * 60)
            (stages / "delivery_manifest.json").write_text("{}")
            # BBB-001 → terminal_failed
            orch.progress["BBB-001"] = {"terminal_failed": True}
            with patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()

            assert report["status"] == "completed"
            completed = json.loads(
                (bb_root / project / ".deliver_completed.json").read_text()
            )
            assert completed["completed"] == 1
            assert completed["terminal_failed"] == 1
            assert completed["terminal_failed_wps"] == ["BBB-001"]

    def test_completed_fast_path(self, mock_blackboard):
        """完成标记存在 → 快速通道，零扫描。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            (bb_root / project / ".deliver_completed.json").write_text(json.dumps({
                "total_wps": 2, "completed": 2, "terminal_failed": 0,
            }))
            report = orch.pulse()
            assert report["status"] == "completed"
            assert report["actions"] == []


# ---------------------------------------------------------------------------
# A7: STALLED 告警 + 冷却
# ---------------------------------------------------------------------------

class TestStalledAlert:
    def test_stalled_after_threshold_with_cooldown(self, mock_blackboard):
        """连续 3 次零进展 → STALLED；冷却期内不再报。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            # GENERATING 且全部 running（无超时、无 ready）→ 每次 pulse 零动作
            _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            running_dir = _wp_dir(bb_root, project, "AAA-001") / "stages" / "worker_outputs" / "T-001"
            running_dir.mkdir(parents=True)  # 新鲜 mtime → running

            driver = MagicMock()
            plan = SimpleNamespace(task_graph=[SimpleNamespace(task_id="T-001", depends_on=[])])
            driver.orch.load_execution_plan.return_value = plan
            driver.orch._derive_worker_progress.return_value = {
                "completed": set(), "failed": set(), "blocked": set(),
                "running": {"T-001"}, "pending": set(), "timed_out": set(),
                "failure_reasons": {},
            }
            driver.worker_outputs_dir = running_dir.parent
            driver.step2_check_analyze.return_value = (True, {})
            driver.step4_check_workers.return_value = (False, {})
            driver.step3_workers.return_value = []

            alerts_seen = []
            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0):
                for _ in range(4):
                    report = orch.pulse()
                    alerts_seen.append(
                        any(a["code"] == "STALLED" for a in report["alerts"])
                    )

            assert alerts_seen == [False, False, True, False]  # 第 3 次告警，第 4 次冷却


# ---------------------------------------------------------------------------
# 契约笼子
# ---------------------------------------------------------------------------

class TestContractCage:
    def test_pulse_report_rejects_unknown_field(self):
        from domains.deliver_pro.contracts.pulse_report import PulseReport

        with pytest.raises(Exception):
            PulseReport(
                pulse_id="p1", project_name="x", generated_at=time.time(),
                status="active", actions=[], alerts=[],
                summary={
                    "total_wps": 1, "completed": 0, "terminal_failed": 0,
                    "in_progress": 1, "in_flight": 0, "zero_progress_count": 0,
                },
                unknown_field="boom",
            )

    def test_pulse_action_rejects_empty_label(self):
        from domains.deliver_pro.contracts.pulse_report import PulseAction

        with pytest.raises(Exception):
            PulseAction(wp_id="A", action="analyze", task="t", label="")

    def test_pulse_action_rejects_bad_action_enum(self):
        from domains.deliver_pro.contracts.pulse_report import PulseAction

        with pytest.raises(Exception):
            PulseAction(wp_id="A", action="explode", task="t", label="l")

    def test_spawn_confirmation_requires_label(self):
        from domains.deliver_pro.contracts.pulse_report import SpawnConfirmation

        with pytest.raises(Exception):
            SpawnConfirmation(wp_id="A", ok=True)

    def test_report_file_passes_validation(self, mock_blackboard):
        """pulse() 产出的 _pulse_actions.json 必须能通过 PulseReport 验证（契约笼子闭环）。"""
        from domains.deliver_pro.contracts.pulse_report import PulseReport

        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            with patch.object(orch, "_count_in_flight", return_value=0):
                orch.pulse()
            data = json.loads((bb_root / project / "_pulse_actions.json").read_text())
            validated = PulseReport.model_validate(data)
            assert validated.project_name == project


# ---------------------------------------------------------------------------
# K3（Pulse V1.1）: DONE 契约要求实质交付物
# ---------------------------------------------------------------------------

class TestSubstantialFileContract:
    """空交付物 / worker_outputs 灌入 不得判 DONE（2026-07-24 STORE-003 / SDK-001 实证）。"""

    def test_done_requires_substantial_file(self, tmp_path):
        from domains.deliver_pro.phase_deriver import derive_phase, PHASE_DONE

        stages = tmp_path / "stages"
        (stages / "final_deliverable").mkdir(parents=True)
        (stages / "delivery_manifest.json").write_text("{}")
        (stages / "validation_result.json").write_text("{}")
        (stages / "final_deliverable" / "DELIVERABLE.md").write_text("")  # 0B
        assert derive_phase(tmp_path) == "PACKAGING"  # 空交付物 → 不是 DONE
        (stages / "final_deliverable" / "DELIVERABLE.md").write_text("x" * 60)
        assert derive_phase(tmp_path) == PHASE_DONE

    def test_done_excludes_worker_outputs_dump(self, tmp_path):
        """final_deliverable 内嵌套的 worker_outputs/ 是中间产物，不计入交付物。"""
        from domains.deliver_pro.phase_deriver import derive_phase, PHASE_DONE

        stages = tmp_path / "stages"
        dump = stages / "final_deliverable" / "worker_outputs" / "T-001"
        dump.mkdir(parents=True)
        (stages / "delivery_manifest.json").write_text("{}")
        (stages / "validation_result.json").write_text("{}")
        (dump / "big.bin").write_text("x" * 5000)  # 灌入的大文件不算交付物
        (stages / "final_deliverable" / "DELIVERABLE.md").write_text("")
        assert derive_phase(tmp_path) == "PACKAGING"
        (stages / "final_deliverable" / "DELIVERABLE.md").write_text("x" * 60)
        assert derive_phase(tmp_path) == PHASE_DONE


# ---------------------------------------------------------------------------
# K5-B（Pulse V1.1）: 零产出 assembly → terminal_failed
# ---------------------------------------------------------------------------

class TestAssemblyEmptyGuard:
    """plan 非空但 workers_integrated=0 → 不烧 validate/package 两轮 LLM，直接 terminal。"""

    def test_step5_zero_integrated_assembly_empty(self):
        from domains.deliver_pro.driver import DeliverRunner

        driver = object.__new__(DeliverRunner)
        driver.wp_id = "TEST-001"
        plan = SimpleNamespace(task_graph=[SimpleNamespace(task_id="T-001", depends_on=[])])
        driver.orch = MagicMock()
        driver.orch.load_execution_plan.return_value = plan
        driver.orch.run_integrate.return_value = SimpleNamespace(
            workers_integrated=0, workers_failed=1, retention_ratio=0.0, status="OK"
        )
        info = driver.step5_integrate()
        assert info["status"] == "ASSEMBLY_EMPTY"
        assert "zero workers" in info["error"]

    def test_step5_zero_worker_plan_passes_through(self):
        """真 zero-worker WP（plan.task_graph 为空）→ 守卫不触发（设计内行为）。"""
        from domains.deliver_pro.driver import DeliverRunner

        driver = object.__new__(DeliverRunner)
        driver.wp_id = "TEST-001"
        plan = SimpleNamespace(task_graph=[])
        driver.orch = MagicMock()
        driver.orch.load_execution_plan.return_value = plan
        driver.orch.run_integrate.return_value = SimpleNamespace(
            workers_integrated=0, workers_failed=0, retention_ratio=1.0, status="OK"
        )
        driver.orch.verify_integrate_output.return_value = (True, "ok")
        info = driver.step5_integrate()
        assert info["status"] == "OK"

    def test_assembly_empty_maps_terminal_failed(self, mock_blackboard):
        """tick assemble 分支：ASSEMBLY_EMPTY → terminal_failed + CRITICAL 告警。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            driver = MagicMock()
            driver.step5_integrate.return_value = {
                "status": "ASSEMBLY_EMPTY", "workers_integrated": 0,
                "error": "zero workers integrated",
            }
            with patch.object(orch, "_get_wp_next_action", return_value={
                "wp_id": "AAA-001", "action": "assemble", "spawn_params": None, "error": None,
            }), patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()
            assert orch.progress["AAA-001"]["terminal_failed"] is True
            assert any(a["code"] == "TERMINAL_FAILED" for a in report["alerts"])
