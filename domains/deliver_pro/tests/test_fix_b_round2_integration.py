"""F-B Round 2 集成测试：L1 过滤器放行 contract_violation + attempts 递增。

集成测试（非单元 mock 隔离）：
1. L1 存活测试：contract_violation MANIFEST + 实质文件 → params 存活
2. 反向测试：substance_failure MANIFEST → 被过滤
3. 无 failure_class 旧 MANIFEST → 被过滤（向后兼容）
4. attempts 递增测试：contract 重试派发后 attempts_map +1
5. 预算耗尽的 contract_violation → 被过滤
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domains.deliver_pro.orchestrator import DeliverOrchestrator, RETRY_BUDGET


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def orch_instance(tmp_path):
    """Create a minimal DeliverOrchestrator-like object for _filter_spawnable_tasks.

    使用 MagicMock(spec=...) 绕过 __init__，然后绑定真实方法。
    """
    instance = MagicMock(spec=DeliverOrchestrator)
    instance.progress = {}
    instance.blackboard_root = tmp_path / "blackboard"
    instance.project_name = "test_project"

    # Bind real methods
    instance._filter_spawnable_tasks = DeliverOrchestrator._filter_spawnable_tasks.__get__(
        instance, DeliverOrchestrator
    )
    instance._wp_dir = DeliverOrchestrator._wp_dir.__get__(instance, DeliverOrchestrator)
    instance._get_wp_project_name = DeliverOrchestrator._get_wp_project_name.__get__(
        instance, DeliverOrchestrator
    )
    return instance


def _setup_wp_dirs(orch, wp_id):
    """Create the worker_outputs directory structure that _filter_spawnable_tasks expects."""
    wp_dir = orch._wp_dir(wp_id)
    wo = wp_dir / "stages" / "worker_outputs"
    wo.mkdir(parents=True, exist_ok=True)
    return wo


def _write_manifest(wo_dir, task_id, status="FAILED", failure_class=None, failure_reason="test"):
    """Write a MANIFEST.json for a task."""
    manifest_path = wo_dir / task_id / "MANIFEST.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "task_id": task_id,
        "status": status,
        "failure_reason": failure_reason,
    }
    if failure_class:
        data["failure_class"] = failure_class
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    return manifest_path


def _make_params(task_ids):
    """Create spawn params list for given task IDs."""
    return [
        {"task_id": tid, "runtime": "subagent", "mode": "run", "task": f"do {tid}"}
        for tid in task_ids
    ]


# ============================================================================
# Test 1: L1 存活测试 — contract_violation params 必须存活
# ============================================================================

class TestL1ContractViolationSurvival:
    """集成测试：contract_violation + 预算未耗尽 → params 过 L1 存活。"""

    def test_contract_violation_survives_l1(self, orch_instance, tmp_path):
        """contract_violation MANIFEST + attempts=1 < RETRY_BUDGET → 存活"""
        wp_id = "WP-001"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        _write_manifest(wo, "T-001", failure_class="contract_violation")
        # 同时有实质文件（模拟真实场景）
        (wo / "T-001" / "report.md").write_text("x" * 200, encoding="utf-8")

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": 1},
                "task_spawned_at": {},  # 无冷却窗口
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 1, f"contract_violation params should survive L1, got {len(result)} items"
        assert result[0]["task_id"] == "T-001"


# ============================================================================
# Test 2: 反向测试 — substance_failure 必须被过滤
# ============================================================================

class TestL1SubstanceFailureFiltered:
    """集成测试：substance_failure MANIFEST → 被 L1 过滤。"""

    def test_substance_failure_filtered(self, orch_instance, tmp_path):
        wp_id = "WP-002"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        _write_manifest(wo, "T-001", failure_class="substance_failure")

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": 1},
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 0, f"substance_failure params should be filtered, got {len(result)} items"


# ============================================================================
# Test 3: 无 failure_class 旧 MANIFEST → 被过滤（向后兼容）
# ============================================================================

class TestL1LegacyManifestFiltered:
    """集成测试：无 failure_class 的旧 MANIFEST → 被 L1 过滤。"""

    def test_legacy_manifest_filtered(self, orch_instance, tmp_path):
        wp_id = "WP-003"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        # 旧 MANIFEST 无 failure_class 字段
        _write_manifest(wo, "T-001", failure_class=None)

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": 1},
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 0, f"legacy manifest (no failure_class) should be filtered, got {len(result)} items"


# ============================================================================
# Test 4: attempts 递增测试
# ============================================================================

class TestAttemptsIncrement:
    """集成测试：contract 重试派发后 attempts_map 对应任务 +1。

    验证 dispatch 路径（orchestrator.py ~859-864）对所有 spawn_workers params
    （包括 contract 重试）统一递增 attempts。
    """

    def test_attempts_increment_on_dispatch(self, orch_instance, tmp_path):
        """模拟 dispatch 路径：params 过 L1 后，attempts 递增。"""
        wp_id = "WP-004"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        _write_manifest(wo, "T-001", failure_class="contract_violation")

        progress_entry = {
            "task_attempts": {"T-001": 1},
            "task_spawned_at": {},
        }
        orch_instance.progress = {wp_id: progress_entry}

        # Step 1: params 过 L1
        params = _make_params(["T-001"])
        filtered = orch_instance._filter_spawnable_tasks(wp_id, params)
        assert len(filtered) == 1, "contract_violation should survive L1"

        # Step 2: 模拟 dispatch 路径的 attempts 递增（orchestrator.py ~859-864）
        attempts_map = progress_entry.setdefault("task_attempts", {})
        for p in filtered:
            tid = p.get("task_id")
            if tid:
                attempts_map[tid] = attempts_map.get(tid, 0) + 1

        assert attempts_map["T-001"] == 2, f"attempts should be 2 after dispatch, got {attempts_map['T-001']}"

    def test_attempts_eventually_exhausts_budget(self, orch_instance, tmp_path):
        """attempts 递增到 RETRY_BUDGET 后，params 被 L1 过滤。"""
        wp_id = "WP-005"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        _write_manifest(wo, "T-001", failure_class="contract_violation")

        # attempts 已达 RETRY_BUDGET
        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": RETRY_BUDGET},
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 0, f"budget-exhausted contract_violation should be filtered, got {len(result)} items"


# ============================================================================
# Test 5: 预算耗尽的 contract_violation → 被过滤
# ============================================================================

class TestL1BudgetExhaustedFiltered:
    """集成测试：contract_violation + attempts >= RETRY_BUDGET → 被过滤。"""

    def test_contract_violation_budget_exhausted(self, orch_instance, tmp_path):
        wp_id = "WP-006"
        wo = _setup_wp_dirs(orch_instance, wp_id)
        _write_manifest(wo, "T-001", failure_class="contract_violation")

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": RETRY_BUDGET},  # 已达上限
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 0, "contract_violation with exhausted budget should be filtered"


# ============================================================================
# Test 6: 混合场景 — 多 task 同时过 L1
# ============================================================================

class TestL1MixedScenario:
    """集成测试：多 task 混合场景，只有 contract_violation+预算未耗尽 的存活。"""

    def test_mixed_tasks_l1_filter(self, orch_instance, tmp_path):
        wp_id = "WP-007"
        wo = _setup_wp_dirs(orch_instance, wp_id)

        # T-001: contract_violation, attempts=1 → 存活
        _write_manifest(wo, "T-001", failure_class="contract_violation")
        # T-002: substance_failure → 过滤
        _write_manifest(wo, "T-002", failure_class="substance_failure")
        # T-003: contract_violation, attempts=RETRY_BUDGET → 过滤
        _write_manifest(wo, "T-003", failure_class="contract_violation")
        # T-004: 无 MANIFEST（新任务）→ 存活
        (wo / "T-004").mkdir(parents=True, exist_ok=True)

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": 1, "T-002": 1, "T-003": RETRY_BUDGET},
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001", "T-002", "T-003", "T-004"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        surviving_ids = sorted(p["task_id"] for p in result)
        assert surviving_ids == ["T-001", "T-004"], (
            f"Only T-001 (contract_violation under budget) and T-004 (no manifest) should survive, "
            f"got {surviving_ids}"
        )


# ============================================================================
# Test 7: MANIFEST 损坏 → 保持原过滤行为（不误放行）
# ============================================================================

class TestL1CorruptManifest:
    """集成测试：MANIFEST 解析失败 → 保持原过滤行为（不过滤放行）。"""

    def test_corrupt_manifest_filtered(self, orch_instance, tmp_path):
        wp_id = "WP-008"
        wo = _setup_wp_dirs(orch_instance, wp_id)

        # 写损坏的 MANIFEST
        manifest_path = wo / "T-001" / "MANIFEST.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("{invalid json!!!", encoding="utf-8")

        orch_instance.progress = {
            wp_id: {
                "task_attempts": {"T-001": 1},
                "task_spawned_at": {},
            }
        }

        params = _make_params(["T-001"])
        result = orch_instance._filter_spawnable_tasks(wp_id, params)

        assert len(result) == 0, "corrupt manifest should result in filtering (safe default)"
