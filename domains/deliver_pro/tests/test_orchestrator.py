"""
Tests for DeliverOrchestrator — 批量驱动 + Stuck Detection。
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ship_package_data():
    """标准 15 WP ship_package 数据（简化版）。"""
    return {
        "work_packages": [
            {"wp_id": "CORE-001", "dependencies": [], "title": "Core 1"},
            {"wp_id": "CORE-002", "dependencies": ["CORE-001"], "title": "Core 2"},
            {"wp_id": "CORE-003", "dependencies": ["CORE-001"], "title": "Core 3"},
            {"wp_id": "CORE-004", "dependencies": ["CORE-001"], "title": "Core 4"},
            {"wp_id": "CORE-005", "dependencies": ["CORE-004"], "title": "Core 5"},
            {"wp_id": "FMV-001", "dependencies": [], "title": "Feature 1"},
            {"wp_id": "FMV-002", "dependencies": ["FMV-001"], "title": "Feature 2"},
            {"wp_id": "RPT-001", "dependencies": [], "title": "Report 1"},
            {"wp_id": "RPT-002", "dependencies": ["RPT-001"], "title": "Report 2"},
            {"wp_id": "FIX-001", "dependencies": [], "title": "Fix 1"},
            {"wp_id": "FIX-002", "dependencies": [], "title": "Fix 2"},
            {"wp_id": "FIX-003", "dependencies": ["FIX-001", "FIX-002"], "title": "Fix 3"},
        ],
        "dependency_graph": {
            "execution_layers": [
                ["CORE-001", "FMV-001", "RPT-001", "FIX-001", "FIX-002"],
                ["CORE-002", "CORE-003", "CORE-004", "FMV-002", "RPT-002", "FIX-003"],
                ["CORE-005"],
            ]
        },
    }


@pytest.fixture
def mock_blackboard(tmp_path, ship_package_data):
    """创建临时 blackboard 目录结构。"""
    project_name = "test-project"
    bb_root = tmp_path / "blackboard"
    bb_root.mkdir()

    # 写 ship_package.json
    ship_dir = bb_root / project_name / "ship_pro" / "stages"
    ship_dir.mkdir(parents=True)
    (ship_dir / "ship_package.json").write_text(json.dumps(ship_package_data))

    return bb_root, project_name


@contextmanager
def _make_orchestrator(tmp_path, mock_blackboard):
    """创建 DeliverOrchestrator（mock BLACKBOARD_ROOT）。

    Usage:
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            result = driver.get_next_actions()
    """
    bb_root, project_name = mock_blackboard
    with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
        from domains.deliver_pro.orchestrator import DeliverOrchestrator
        driver = DeliverOrchestrator(project_name)
        yield driver


# ---------------------------------------------------------------------------
# Task 1: _topo_layers 测试
# ---------------------------------------------------------------------------

class TestTopoLayers:
    """_topo_layers 静态方法测试。"""

    def test_no_dependencies_all_layer_0(self):
        """无依赖 → 全在 Layer 0。"""
        from domains.deliver_pro.orchestrator import DeliverOrchestrator

        wp_deps = {
            "A": [],
            "B": [],
            "C": [],
        }
        layers = DeliverOrchestrator._topo_layers(wp_deps)
        assert len(layers) == 1
        assert sorted(layers[0]) == ["A", "B", "C"]

    def test_linear_dependency_each_layer_one(self):
        """线性依赖 → 每层 1 个。"""
        from domains.deliver_pro.orchestrator import DeliverOrchestrator

        wp_deps = {
            "A": [],
            "B": ["A"],
            "C": ["B"],
        }
        layers = DeliverOrchestrator._topo_layers(wp_deps)
        assert len(layers) == 3
        assert layers[0] == ["A"]
        assert layers[1] == ["B"]
        assert layers[2] == ["C"]

    def test_diamond_dependency_three_layers(self):
        """菱形依赖 → 3 层。"""
        from domains.deliver_pro.orchestrator import DeliverOrchestrator

        # A → B, C → D (B and C depend on A, D depends on B and C)
        wp_deps = {
            "A": [],
            "B": ["A"],
            "C": ["A"],
            "D": ["B", "C"],
        }
        layers = DeliverOrchestrator._topo_layers(wp_deps)
        assert len(layers) == 3
        assert layers[0] == ["A"]
        assert sorted(layers[1]) == ["B", "C"]
        assert layers[2] == ["D"]


# ---------------------------------------------------------------------------
# Task 2: _compute_layers 测试
# ---------------------------------------------------------------------------

class TestComputeLayers:
    """_compute_layers 从 execution_layers 获取。"""

    def test_from_execution_layers(self, tmp_path, mock_blackboard):
        """优先用 execution_layers。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert len(driver.layers) == 3
            assert sorted(driver.layers[0]) == sorted(["CORE-001", "FMV-001", "RPT-001", "FIX-001", "FIX-002"])
            assert driver.layers[2] == ["CORE-005"]

    def test_fallback_topo_sort(self, tmp_path):
        """无 execution_layers 时 fallback 到拓扑排序。"""
        bb_root = tmp_path / "blackboard"
        bb_root.mkdir()
        project_name = "test-fallback"

        ship_data = {
            "work_packages": [
                {"wp_id": "A", "dependencies": []},
                {"wp_id": "B", "dependencies": ["A"]},
                {"wp_id": "C", "dependencies": ["A"]},
            ],
            "dependency_graph": {},  # No execution_layers
        }
        ship_dir = bb_root / project_name / "ship_pro" / "stages"
        ship_dir.mkdir(parents=True)
        (ship_dir / "ship_package.json").write_text(json.dumps(ship_data))

        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            from domains.deliver_pro.orchestrator import DeliverOrchestrator
            driver = DeliverOrchestrator(project_name)

        assert len(driver.layers) == 2
        assert driver.layers[0] == ["A"]
        assert sorted(driver.layers[1]) == ["B", "C"]


# ---------------------------------------------------------------------------
# Task 3: _get_wp_project_name 映射
# ---------------------------------------------------------------------------

class TestWpProjectName:
    """WP → project_name 映射（V3: 统一到项目自己的 blackboard）。"""

    def test_mapping(self, tmp_path, mock_blackboard):
        bb_root, project_name = mock_blackboard
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            # V3: 所有 WP 输出统一写到项目自己的 blackboard（self.project_name）
            assert driver._get_wp_project_name("CORE-001") == project_name
            assert driver._get_wp_project_name("FMV-002") == project_name
            assert driver._get_wp_project_name("RPT-003") == project_name
            assert driver._get_wp_project_name("FIX-001") == project_name


# ---------------------------------------------------------------------------
# Task 4: _check_wp_phase 测试
# ---------------------------------------------------------------------------

class TestCheckWpPhase:
    """_check_wp_phase 从文件系统检测。"""

    def test_pending_empty_dir(self, tmp_path, mock_blackboard):
        """空目录 → PENDING。"""
        bb_root, project_name = mock_blackboard
        # Create deliver_pro dir but no stages
        wp_project = project_name
        stages_dir = bb_root / wp_project / "deliver_pro" / "core_001" / "stages"
        stages_dir.mkdir(parents=True)

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert driver._check_wp_phase("CORE-001") == "PENDING"

    def test_pending_no_dir(self, tmp_path, mock_blackboard):
        """目录不存在 → PENDING。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert driver._check_wp_phase("CORE-001") == "PENDING"

    def test_done_final_deliverable_has_files(self, tmp_path, mock_blackboard):
        """final_deliverable 有文件 + delivery_manifest.json → DONE (P1-8 fix)。"""
        bb_root, project_name = mock_blackboard
        wp_project = project_name
        stages_dir = bb_root / wp_project / "deliver_pro" / "core_001" / "stages"
        final_dir = stages_dir / "final_deliverable"
        final_dir.mkdir(parents=True)
        (final_dir / "DELIVERABLE.md").write_text("# Done")
        # P1-8 fix: DONE also requires delivery_manifest.json
        (stages_dir / "delivery_manifest.json").write_text("{}")

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert driver._check_wp_phase("CORE-001") == "DONE"

    def test_done_terminal_state(self, tmp_path, mock_blackboard):
        """V3: DONE 由 delivery_manifest.json + final_deliverable 推导（不再读 state 文件）。"""
        bb_root, project_name = mock_blackboard
        wp_project = project_name
        deliver_pro_dir = bb_root / wp_project / "deliver_pro" / "core_001"
        deliver_pro_dir.mkdir(parents=True)
        stages_dir = deliver_pro_dir / "stages"
        stages_dir.mkdir(parents=True)
        final_dir = stages_dir / "final_deliverable"
        final_dir.mkdir(parents=True)
        (final_dir / "DELIVERABLE.md").write_text("# Done")
        # V3: delivery_manifest.json 存在 + final_deliverable 非空 → DONE
        (stages_dir / "delivery_manifest.json").write_text('{"wp_id": "CORE-001"}')

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert driver._check_wp_phase("CORE-001") == "DONE"

    def test_not_done_without_manifest(self, tmp_path, mock_blackboard):
        """final_deliverable 有文件但无 manifest 且非终态 → 不是 DONE (P1-8 fix)。"""
        bb_root, project_name = mock_blackboard
        wp_project = project_name
        final_dir = bb_root / wp_project / "deliver_pro" / "core_001" / "stages" / "final_deliverable"
        final_dir.mkdir(parents=True)
        (final_dir / "DELIVERABLE.md").write_text("# Done")
        # No delivery_manifest.json, no terminal state → falls through

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            phase = driver._check_wp_phase("CORE-001")
            assert phase != "DONE"

    def test_packaging_validation_result_exists(self, tmp_path, mock_blackboard):
        """validation_result.json 存在 → PACKAGING。"""
        bb_root, project_name = mock_blackboard
        wp_project = project_name
        stages_dir = bb_root / wp_project / "deliver_pro" / "core_001" / "stages"
        stages_dir.mkdir(parents=True)
        (stages_dir / "validation_result.json").write_text("{}")

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert driver._check_wp_phase("CORE-001") == "PACKAGING"

    def test_validating_integrated_draft_exists(self, tmp_path, mock_blackboard):
        """integrated_draft/DELIVERABLE.md 存在 → VALIDATING。"""
        bb_root, project_name = mock_blackboard
        wp_project = project_name
        draft_dir = bb_root / wp_project / "deliver_pro" / "core_001" / "stages" / "integrated_draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "DELIVERABLE.md").write_text("# Draft")

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert driver._check_wp_phase("CORE-001") == "VALIDATING"

    def test_generating_execution_plan_exists(self, tmp_path, mock_blackboard):
        """execution_plan.json 有 task_count → GENERATING。"""
        bb_root, project_name = mock_blackboard
        wp_project = project_name
        stages_dir = bb_root / wp_project / "deliver_pro" / "core_001" / "stages"
        stages_dir.mkdir(parents=True)
        plan = {"task_count": 3, "task_graph": {"nodes": []}}
        (stages_dir / "execution_plan.json").write_text(json.dumps(plan))

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            assert driver._check_wp_phase("CORE-001") == "GENERATING"


# ---------------------------------------------------------------------------
# Task 5: get_status 测试
# ---------------------------------------------------------------------------

class TestGetStatus:
    """get_status 初始状态。"""

    def test_initial_all_pending(self, tmp_path, mock_blackboard):
        """初始状态全 PENDING。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            status = driver.get_status()

        assert status["total_wps"] == 12
        assert status["completed"] == 0
        assert status["failed"] == 0
        assert status["in_progress"] == 12
        assert status["current_layer"] == 0
        assert status["all_done"] is False


# ---------------------------------------------------------------------------
# Task 6: report_done 测试
# ---------------------------------------------------------------------------

class TestReportDone:
    """report_done 更新进度。"""

    def test_report_success(self, tmp_path, mock_blackboard):
        """报告成功 → 更新 progress。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.report_done("CORE-001", "analyze", success=True)

        assert "CORE-001" in driver.progress
        assert driver.progress["CORE-001"]["last_action"] == "analyze"
        assert driver.progress["CORE-001"]["last_success"] is True
        assert driver.progress["CORE-001"]["action_count"] == 1

    def test_report_failure(self, tmp_path, mock_blackboard):
        """报告失败 → 更新 error_count。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.report_done("CORE-001", "analyze", success=False, error="timeout")

        assert driver.progress["CORE-001"]["last_error"] == "timeout"
        assert driver.progress["CORE-001"]["error_count"] == 1
        assert driver.progress["CORE-001"].get("action_count", 0) == 0


# ---------------------------------------------------------------------------
# Task 7: reset_wp 测试
# ---------------------------------------------------------------------------

class TestResetWp:
    """reset_wp 重置状态。"""

    def test_reset_single_wp(self, tmp_path, mock_blackboard):
        """重置单个 WP → 清除该 WP 的 progress。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.report_done("CORE-001", "analyze", success=True)
            driver.report_done("CORE-002", "analyze", success=True)

        driver.reset_wp("CORE-001")
        assert "CORE-001" not in driver.progress
        assert "CORE-002" in driver.progress

    def test_reset_all(self, tmp_path, mock_blackboard):
        """重置所有 → 清空 progress。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.report_done("CORE-001", "analyze", success=True)
            driver.report_done("CORE-002", "analyze", success=True)

        driver.reset_all()
        assert driver.progress == {}


# ---------------------------------------------------------------------------
# Task 8: get_next_actions 测试
# ---------------------------------------------------------------------------

class TestGetNextActions:
    """get_next_actions 返回当前层动作。"""

    def test_first_layer_pending(self, tmp_path, mock_blackboard):
        """第一层全部 PENDING → 返回 Layer 0 的动作。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            result = driver.get_next_actions()

        assert result["layer"] == 0
        assert len(result["actions"]) == 5  # 5 WPs in layer 0
        for action in result["actions"]:
            assert action["action"] == "analyze"

    def test_all_done_returns_empty(self, tmp_path, mock_blackboard):
        """全部完成 → layer=-1, actions=[]。"""
        bb_root, project_name = mock_blackboard

        # 让所有 WP 都 DONE（V3: 统一到项目自己的 blackboard + delivery_manifest.json）
        for wp_id in ["CORE-001", "CORE-002", "CORE-003", "CORE-004", "CORE-005",
                       "FMV-001", "FMV-002", "RPT-001", "RPT-002",
                       "FIX-001", "FIX-002", "FIX-003"]:
            wp_project = project_name
            wp_subdir = wp_id.lower().replace('-', '_')
            stages_dir = bb_root / wp_project / "deliver_pro" / wp_subdir / "stages"
            final_dir = stages_dir / "final_deliverable"
            final_dir.mkdir(parents=True)
            (final_dir / "DELIVERABLE.md").write_text("# Done")
            (stages_dir / "delivery_manifest.json").write_text("{}")

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            result = driver.get_next_actions()

        assert result["layer"] == -1
        assert result["actions"] == []


class TestStaleDispatchRecovery:
    """孤儿分发恢复：dedup 记录过期后允许重新分发（2026-07-23 smk_001 停摆事故）。

    事故根因：drive_all 标记 last_spawned_action=analyze 后 session 死亡，
    agent 从未真正运行，但 dedup 记录永久阻塞后续分发。
    """

    def test_legacy_record_without_timestamp_is_stale(self, tmp_path, mock_blackboard):
        """旧代码写入的记录（无 last_spawned_at）→ 视为过期 → 重新分发。"""
        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.progress["CORE-001"] = {
                "phase": "PENDING",
                "last_spawned_action": "analyze",  # 旧记录，无时间戳
            }
            results = driver.tick()

        actions = [r for r in results if r["wp_id"] == "CORE-001"]
        assert len(actions) == 1
        assert actions[0]["action"] == "analyze"
        # 重新分发后应写入时间戳
        assert "last_spawned_at" in driver.progress["CORE-001"]

    def test_fresh_dispatch_not_redispatched(self, tmp_path, mock_blackboard):
        """新鲜分发记录（未超时）→ 跳过，不重复分发。"""
        import time as _time

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.progress["CORE-001"] = {
                "phase": "PENDING",
                "last_spawned_action": "analyze",
                "last_spawned_at": _time.time(),  # 刚刚分发
            }
            results = driver.tick()

        actions = [r for r in results if r["wp_id"] == "CORE-001"]
        assert actions == []

    def test_expired_dispatch_redispatched(self, tmp_path, mock_blackboard):
        """过期分发记录（超过 analyze 的 1800s 阈值）→ 清除并重新分发。"""
        import time as _time

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.progress["CORE-001"] = {
                "phase": "PENDING",
                "last_spawned_action": "analyze",
                "last_spawned_at": _time.time() - 2000,  # 超过阈值
            }
            results = driver.tick()

        actions = [r for r in results if r["wp_id"] == "CORE-001"]
        assert len(actions) == 1
        assert actions[0]["action"] == "analyze"


class TestOrphanValidateRecovery:
    """孤儿 validate 恢复（2026-07-23 E2E 停摆事故）。

    事故根因：validate agent 死亡/从未分发时 validation_result.json 永远缺失，
    VALIDATING 分支无条件 skip → Layer 0 不 DONE → 全管线锁死。
    """

    def _setup_validating_wp(self, bb_root, project_name, wp_id="CORE-001"):
        """构造 VALIDATING 状态的 WP：plan + integrated_draft 存在，无 validation_result。"""
        wp_subdir = wp_id.lower().replace('-', '_')
        stages = bb_root / project_name / "deliver_pro" / wp_subdir / "stages"
        (stages / "integrated_draft").mkdir(parents=True)
        (stages / "integrated_draft" / "DELIVERABLE.md").write_text("# Draft")
        (stages / "execution_plan.json").write_text(json.dumps({
            "wp_id": wp_id, "task_graph": [],
        }))
        return stages

    def test_orphan_validate_never_dispatched(self, tmp_path, mock_blackboard):
        """validate 从未分发（last_spawned=spawn_workers）→ 重新分发 validate。"""
        bb_root, project_name = mock_blackboard
        self._setup_validating_wp(bb_root, project_name)

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.progress["CORE-001"] = {
                "phase": "VALIDATING",
                "last_spawned_action": "spawn_workers:deliver-worker-t-002",
                "last_spawned_at": 1784767544.0,  # 旧时间戳
            }
            action = driver._get_wp_next_action("CORE-001")

        assert action["action"] == "validate", f"expected validate, got {action}"
        assert action["spawn_params"] is not None

    def test_orphan_validate_stale_dispatch(self, tmp_path, mock_blackboard):
        """validate 已分发但 agent 死亡（>30min）→ 重新分发 validate。"""
        import time as _time
        bb_root, project_name = mock_blackboard
        self._setup_validating_wp(bb_root, project_name)

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.progress["CORE-001"] = {
                "phase": "VALIDATING",
                "last_spawned_action": "validate",
                "last_spawned_at": _time.time() - 2000,  # 超过 1800s 阈值
            }
            action = driver._get_wp_next_action("CORE-001")

        assert action["action"] == "validate", f"expected validate, got {action}"

    def test_fresh_validate_not_redispatched(self, tmp_path, mock_blackboard):
        """validate agent 正常运行中（<30min）→ skip，不重复分发。"""
        import time as _time
        bb_root, project_name = mock_blackboard
        self._setup_validating_wp(bb_root, project_name)

        with _make_orchestrator(tmp_path, mock_blackboard) as driver:
            driver.progress["CORE-001"] = {
                "phase": "VALIDATING",
                "last_spawned_action": "validate",
                "last_spawned_at": _time.time() - 60,  # 1 分钟前，正常
            }
            action = driver._get_wp_next_action("CORE-001")

        assert action["action"] == "skip", f"expected skip, got {action}"


class TestLegacyFinalDeliverablePath:
    """Legacy final_deliverable 路径兼容（2026-07-23 prompt 路径歧义事故）。

    package prompt 曾漏 stages/ 前缀，agent 把交付物写到 WP 根目录。
    derive_phase 应接受该位置（DeprecationWarning），保证旧交付不丢失。
    """

    def test_legacy_wp_root_final_deliverable_is_done(self, tmp_path, mock_blackboard):
        """交付物在 WP 根目录 final_deliverable/（legacy）→ DONE + 警告。"""
        import warnings
        bb_root, project_name = mock_blackboard
        wp_dir = bb_root / project_name / "deliver_pro" / "core_001"
        stages = wp_dir / "stages"
        stages.mkdir(parents=True)
        (stages / "delivery_manifest.json").write_text('{"wp_id": "CORE-001"}')
        # legacy 位置：WP 根目录而非 stages/
        legacy = wp_dir / "final_deliverable"
        legacy.mkdir()
        (legacy / "README.md").write_text("# Deliverable")

        from domains.deliver_pro.phase_deriver import derive_phase
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert derive_phase(wp_dir) == "DONE"
            assert any(issubclass(x.category, DeprecationWarning) for x in w)

    def test_stages_path_preferred_no_warning(self, tmp_path, mock_blackboard):
        """交付物在契约位置 stages/final_deliverable/ → DONE 且无警告。"""
        import warnings
        bb_root, project_name = mock_blackboard
        wp_dir = bb_root / project_name / "deliver_pro" / "core_001"
        final_dir = wp_dir / "stages" / "final_deliverable"
        final_dir.mkdir(parents=True)
        (final_dir.parent / "delivery_manifest.json").write_text("{}")
        (final_dir / "README.md").write_text("# Deliverable")

        from domains.deliver_pro.phase_deriver import derive_phase
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert derive_phase(wp_dir) == "DONE"
            assert not any(issubclass(x.category, DeprecationWarning) for x in w)
