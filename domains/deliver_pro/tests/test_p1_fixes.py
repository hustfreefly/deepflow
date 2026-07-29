"""Tests for P1 修复：F1 (phase 滞留) + F2 (label 冲突) + F3 (僵尸 running_tasks).

覆盖：
- F1: pulse 后 batch_progress phase 与 derive_phase 一致
- F2: label 冲突 fallback spawn 带后缀 + confirm_dispatches 正确 strip
  - 含 F-B contract 重试 label 场景
- F3: 僵尸 running_tasks 条目被清、正常条目保留
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
# Fixtures (复用 test_pulse.py 模式)
# ---------------------------------------------------------------------------

@pytest.fixture
def ship_package_data():
    return {
        "work_packages": [
            {"wp_id": "AAA-001", "dependencies": [], "title": "Alpha"},
        ],
        "dependency_graph": {
            "execution_layers": [["AAA-001"]],
        },
    }


@pytest.fixture
def mock_blackboard(tmp_path, ship_package_data):
    project_name = "test-p1-fixes"
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
        "label": f"deliver-worker-{wp_id.lower()}-{task_node.task_id.lower()}",
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
# F1: pulse 后 batch_progress phase 与 derive_phase 一致
# ---------------------------------------------------------------------------

class TestF1PhaseRefresh:
    def test_pulse_refreshes_phase_in_batch_progress(self, mock_blackboard):
        """pulse 结束后 batch_progress 中的 phase 应与 derive_phase 一致。

        场景：WP 实际已到 DONE（所有 task 有 MANIFEST），但 progress 中 phase 停在 PACKAGING。
        pulse 后应刷新为 DONE。
        """
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            # 写入 MANIFEST → derive_phase 会判 DONE
            task_dir = stages / "worker_outputs" / "T-001"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "MANIFEST.json").write_text(json.dumps({
                "task_id": "T-001", "status": "COMPLETE", "completed_at": time.time(),
            }))
            # 模拟旧 phase 滞留在 PACKAGING
            orch.progress["AAA-001"] = {"phase": "PACKAGING"}

            with patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()

            # batch_progress 中的 phase 应已刷新
            entry = orch.progress.get("AAA-001", {})
            # derive_phase 应该判为 DONE（有 MANIFEST）或至少不是 PACKAGING
            assert entry.get("phase") != "PACKAGING", \
                f"phase should have been refreshed, got {entry.get('phase')}"

    def test_pulse_phase_refresh_no_false_regression(self, mock_blackboard):
        """pulse 不应把正确的 phase 改错。

        场景：WP 实际在 GENERATING（有 task 目录含非 MANIFEST 文件，未超时），
        progress 中 phase 也是 GENERATING。pulse 后应保持一致。
        """
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            # 创建非空 task 目录（有文件但无 MANIFEST）→ derive 判 running → GENERATING
            task_dir = stages / "worker_outputs" / "T-001"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "DELIVERABLE.md").write_text("work in progress")
            # 记录 spawn 时间（防孤儿清扫）
            orch.progress["AAA-001"] = {
                "phase": "GENERATING",
                "task_spawned_at": {"T-001": time.time()},
            }

            # Mock driver 以支持 GENERATING 路径
            driver = MagicMock()
            driver.step2_check_analyze.return_value = (True, {})
            driver.step4_check_workers.return_value = (False, {"completed": 0, "total": 1, "failed": 0, "running": ["T-001"]})
            driver.orch.load_execution_plan.return_value = SimpleNamespace(
                task_graph=[SimpleNamespace(task_id="T-001", depends_on=[])]
            )
            driver.orch._derive_worker_progress.return_value = {
                "completed": set(), "failed": set(), "blocked": set(),
                "running": {"T-001"}, "pending": set(), "timed_out": set(),
            }
            driver.orch._save_state = MagicMock()
            driver.worker_outputs_dir = stages / "worker_outputs"

            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0), \
                 patch.object(orch, "tick", return_value=[]):
                report = orch.pulse()

            entry = orch.progress.get("AAA-001", {})
            # phase 应保持 GENERATING（derive 判 running）
            assert entry.get("phase") == "GENERATING", \
                f"phase should stay GENERATING, got {entry.get('phase')}"


# ---------------------------------------------------------------------------
# F2: label 冲突 fallback
# ---------------------------------------------------------------------------

class TestF2LabelConflict:
    def test_label_suffix_added_on_spawn_failure(self, mock_blackboard):
        """spawn_failures > 0 时，pulse 应在 worker label 追加时间戳后缀。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timeout_task="T-001"
            )
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=("T-001",)
            )
            # 模拟之前有 spawn 失败（label 冲突）
            orch.progress["AAA-001"] = {
                "task_attempts": {"T-001": 1},
                "spawn_failures": 3,  # 之前有 label 冲突
            }
            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()

            labels = [a["label"] for a in report["actions"]]
            # T-001 的 label 应带时间戳后缀
            t001_labels = [l for l in labels if "t-001" in l]
            assert len(t001_labels) >= 1, f"Expected T-001 label, got {labels}"
            # 后缀应是 _{digits}
            import re
            assert any(re.search(r"_\d{10,}$", l) for l in t001_labels), \
                f"Expected timestamp suffix, got {t001_labels}"

    def test_first_spawn_no_suffix(self, mock_blackboard):
        """首次 spawn（spawn_failures=0）不应加后缀，保持确定性格式。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timeout_task="T-001"
            )
            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002"], timed_out=("T-001",)
            )
            orch.progress["AAA-001"] = {"task_attempts": {"T-001": 1}}
            # 无 spawn_failures → 首次 spawn
            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()

            labels = [a["label"] for a in report["actions"]]
            t001_labels = [l for l in labels if "t-001" in l]
            assert len(t001_labels) >= 1
            # 不应有时间戳后缀
            import re
            assert not any(re.search(r"_\d{10,}$", l) for l in t001_labels), \
                f"First spawn should not have suffix, got {t001_labels}"

    def test_confirm_dispatches_strips_timestamp_suffix(self, mock_blackboard):
        """confirm_dispatches 应正确 strip 时间戳后缀匹配 dedup_key。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001", "T-002"])
            for t in ("T-001", "T-002"):
                (stages / "worker_outputs" / t).mkdir(parents=True)
            orch.progress["AAA-001"] = {
                "last_spawned_action": "spawn_workers:T-001,T-002",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": False,
            }
            # 模拟 label 带时间戳后缀（F2 fallback 生成）
            ts = str(int(time.time()))
            out = orch.confirm_dispatches([
                {"wp_id": "AAA-001", "label": f"deliver-worker-aaa-001-t-001_{ts}", "ok": False, "error": "label already in use"},
                {"wp_id": "AAA-001", "label": f"deliver-worker-aaa-001-t-002_{ts}", "ok": True, "error": None},
            ])
            assert out["rolled_back"] == 1
            assert out["confirmed"] == 1
            entry = orch.progress["AAA-001"]
            # T-001 应从 dedup_key 移除（strip 后缀后匹配上了）
            assert entry["last_spawned_action"] == "spawn_workers:T-002"
            assert entry["dispatch_confirmed"] is True

    def test_confirm_dispatches_contract_retry_label_strip(self, mock_blackboard):
        """F-B contract 重试 label 也带时间戳后缀时，confirm_dispatches 应正确 strip。

        F-B contract 重试使用相同的 _prepare_single_worker_spawn，label 格式一致。
        """
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-003"])
            (stages / "worker_outputs" / "T-003").mkdir(parents=True)
            orch.progress["AAA-001"] = {
                "last_spawned_action": "spawn_workers:T-003",
                "last_spawned_at": time.time(),
                "dispatch_confirmed": False,
                "task_attempts": {"T-003": 2},
            }
            ts = str(int(time.time()))
            # contract 重试 label 也带后缀
            out = orch.confirm_dispatches([
                {"wp_id": "AAA-001", "label": f"deliver-worker-aaa-001-t-003_{ts}", "ok": False, "error": "label already in use"},
            ])
            assert out["rolled_back"] == 1
            entry = orch.progress["AAA-001"]
            # T-003 应从 dedup_key 移除
            assert "last_spawned_action" not in entry or \
                "T-003" not in entry.get("last_spawned_action", "")

    def test_validate_label_suffix_on_spawn_failure(self, mock_blackboard):
        """P1-polish: validate action 也应在 spawn_failures > 0 时加时间戳后缀。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            (stages / "worker_outputs" / "T-001").mkdir(parents=True)
            # 模拟 validate action 且有 spawn 失败
            orch.progress["AAA-001"] = {
                "phase": "VALIDATING",
                "spawn_failures": 2,
                "last_spawned_action": "validate",
            }
            # Mock tick 返回 validate action
            validate_params = {
                "label": "deliver_validate_AAA-001_r1",
                "task": "validate task",
                "mode": "run",
            }
            with patch.object(orch, "_count_in_flight", return_value=0), \
                 patch.object(orch, "tick", return_value=[{
                     "wp_id": "AAA-001",
                     "action": "validate",
                     "spawn_params": validate_params,
                     "error": None,
                 }]):
                report = orch.pulse()

            labels = [a["label"] for a in report["actions"]]
            validate_labels = [l for l in labels if "validate" in l]
            assert len(validate_labels) >= 1, f"Expected validate label, got {labels}"
            import re
            assert any(re.search(r"_\d{10,}$", l) for l in validate_labels), \
                f"Expected timestamp suffix on validate label, got {validate_labels}"

    def test_package_label_suffix_on_spawn_failure(self, mock_blackboard):
        """P1-polish: package action 也应在 spawn_failures > 0 时加时间戳后缀。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            (stages / "worker_outputs" / "T-001").mkdir(parents=True)
            # 模拟 package action 且有 spawn 失败
            orch.progress["AAA-001"] = {
                "phase": "PACKAGING",
                "spawn_failures": 1,
                "last_spawned_action": "package",
            }
            # Mock tick 返回 package action
            package_params = {
                "label": "deliver_package_AAA-001",
                "task": "package task",
                "mode": "run",
            }
            with patch.object(orch, "_count_in_flight", return_value=0), \
                 patch.object(orch, "tick", return_value=[{
                     "wp_id": "AAA-001",
                     "action": "package",
                     "spawn_params": package_params,
                     "error": None,
                 }]):
                report = orch.pulse()

            labels = [a["label"] for a in report["actions"]]
            package_labels = [l for l in labels if "package" in l]
            assert len(package_labels) >= 1, f"Expected package label, got {labels}"
            import re
            assert any(re.search(r"_\d{10,}$", l) for l in package_labels), \
                f"Expected timestamp suffix on package label, got {package_labels}"

    def test_multi_param_wave_all_get_suffix(self, mock_blackboard):
        """P1-polish: 多 param wave 中所有 param 都应获后缀（reset 移出循环）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(
                bb_root, project, "AAA-001", ["T-001", "T-002", "T-003"],
                timeout_task="T-001"
            )
            # 构造多个 task 超时
            for t in ("T-002", "T-003"):
                t_dir = stages / "worker_outputs" / t
                t_dir.mkdir(parents=True, exist_ok=True)
                old = time.time() - 31 * 60
                os.utime(t_dir, (old, old))

            driver = _mock_driver_for_retry(
                bb_root, project, "AAA-001", ["T-001", "T-002", "T-003"],
                timed_out=("T-001", "T-002", "T-003")
            )
            # 模拟之前有 spawn 失败
            orch.progress["AAA-001"] = {
                "task_attempts": {"T-001": 1, "T-002": 1, "T-003": 1},
                "spawn_failures": 5,
            }
            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_count_in_flight", return_value=0):
                report = orch.pulse()

            labels = [a["label"] for a in report["actions"]]
            # 所有 3 个 task 的 label 都应带时间戳后缀
            import re
            for tid in ["t-001", "t-002", "t-003"]:
                tid_labels = [l for l in labels if tid in l]
                assert len(tid_labels) >= 1, f"Expected {tid} label, got {labels}"
                assert any(re.search(r"_\d{10,}$", l) for l in tid_labels), \
                    f"Expected timestamp suffix for {tid}, got {tid_labels}"


# ---------------------------------------------------------------------------
# F3: 僵尸 running_tasks 对账清理
# ---------------------------------------------------------------------------

class TestF3ReconcileRunningTasks:
    def test_zombie_cleared_when_manifest_exists(self, mock_blackboard):
        """running_tasks 中的 task 已有 MANIFEST → 僵尸 → 清除。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001", "T-002"])
            # T-001 有 MANIFEST（已完成）
            t1_dir = stages / "worker_outputs" / "T-001"
            t1_dir.mkdir(parents=True)
            (t1_dir / "MANIFEST.json").write_text(json.dumps({
                "task_id": "T-001", "status": "COMPLETE",
            }))
            # T-002 无 MANIFEST（仍在运行）
            t2_dir = stages / "worker_outputs" / "T-002"
            t2_dir.mkdir(parents=True)

            driver = MagicMock()
            driver.orch.state = SimpleNamespace(
                running_tasks=["T-001", "T-002"]
            )
            driver.orch._save_state = MagicMock()

            cleared = orch._reconcile_running_tasks("AAA-001", driver)
            assert cleared == 1
            assert "T-001" not in driver.orch.state.running_tasks
            assert "T-002" in driver.orch.state.running_tasks
            driver.orch._save_state.assert_called_once()

    def test_zombie_cleared_when_stale_no_manifest(self, mock_blackboard):
        """running_tasks 中的 task 超 WORKER_TIMEOUT_SECONDS 且无 MANIFEST → 僵尸 → 清除。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            # T-001 目录存在但无 MANIFEST，spawn 时间超 30min
            t1_dir = stages / "worker_outputs" / "T-001"
            t1_dir.mkdir(parents=True)
            orch.progress["AAA-001"] = {
                "task_spawned_at": {"T-001": time.time() - 31 * 60}
            }

            driver = MagicMock()
            driver.orch.state = SimpleNamespace(running_tasks=["T-001"])
            driver.orch._save_state = MagicMock()

            cleared = orch._reconcile_running_tasks("AAA-001", driver)
            assert cleared == 1
            assert "T-001" not in driver.orch.state.running_tasks

    def test_normal_entry_preserved(self, mock_blackboard):
        """running_tasks 中的 task 无 MANIFEST 且未超时 → 保留（仍在运行）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            t1_dir = stages / "worker_outputs" / "T-001"
            t1_dir.mkdir(parents=True)
            orch.progress["AAA-001"] = {
                "task_spawned_at": {"T-001": time.time() - 5 * 60}  # 5min 前，未超时
            }

            driver = MagicMock()
            driver.orch.state = SimpleNamespace(running_tasks=["T-001"])
            driver.orch._save_state = MagicMock()

            cleared = orch._reconcile_running_tasks("AAA-001", driver)
            assert cleared == 0
            assert "T-001" in driver.orch.state.running_tasks
            driver.orch._save_state.assert_not_called()

    def test_no_spawn_record_preserved_conservative(self, mock_blackboard):
        """无 task_spawned_at 记录但目录非空 → 保守保留。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            t1_dir = stages / "worker_outputs" / "T-001"
            t1_dir.mkdir(parents=True)
            # 写一个文件使目录非空
            (t1_dir / "DELIVERABLE.md").write_text("content")
            # 无 task_spawned_at 记录
            orch.progress["AAA-001"] = {}

            driver = MagicMock()
            driver.orch.state = SimpleNamespace(running_tasks=["T-001"])
            driver.orch._save_state = MagicMock()

            cleared = orch._reconcile_running_tasks("AAA-001", driver)
            assert cleared == 0
            assert "T-001" in driver.orch.state.running_tasks

    def test_reconcile_called_in_tick(self, mock_blackboard):
        """tick() 应在处理每个 WP 时调用 _reconcile_running_tasks。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project):
            stages = _setup_generating_wp(bb_root, project, "AAA-001", ["T-001"])
            orch.progress["AAA-001"] = {}

            driver = MagicMock()
            driver.orch.state = SimpleNamespace(running_tasks=[])
            driver.orch._save_state = MagicMock()
            driver.step1_analyze.side_effect = lambda: {
                "task": "analyze", "label": "analyze-aaa-001", "mode": "run",
            }

            with patch.object(orch, "_get_driver", return_value=driver), \
                 patch.object(orch, "_reconcile_running_tasks", wraps=orch._reconcile_running_tasks) as mock_reconcile:
                # tick 需要 get_next_actions 返回动作
                with patch.object(orch, "get_next_actions", return_value={
                    "layer": 0,
                    "actions": [{"wp_id": "AAA-001", "action": "spawn_workers",
                                 "spawn_params": [{"task_id": "T-001", "task": "do T-001",
                                                    "label": "deliver-worker-aaa-001-t-001",
                                                    "mode": "run"}]}],
                }):
                    orch.tick()

            mock_reconcile.assert_called_once_with("AAA-001", driver)
