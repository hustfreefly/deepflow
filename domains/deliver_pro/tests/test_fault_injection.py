"""故障注入测试：验证降级行为（Phase 4）

覆盖场景：
- MANIFEST.json 损坏（invalid_json / schema_validation_failed）
- batch_progress.json 损坏 → 从文件证据重建
- _pulse_state.json 损坏 → 保守重建
- delivery_state.json 损坏 → 显式降级
- SafeJsonLoader mtime 宽限
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader, LoadResult


# ---------------------------------------------------------------------------
# Fixtures
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
    project_name = "test-fault-injection"
    bb_root = tmp_path / "blackboard"
    ship_dir = bb_root / project_name / "ship_pro" / "stages"
    ship_dir.mkdir(parents=True)
    (ship_dir / "ship_package.json").write_text(json.dumps(ship_package_data))
    return bb_root, project_name


def _wp_dir(bb_root, project_name, wp_id):
    return bb_root / project_name / "deliver_pro" / wp_id.lower().replace("-", "_")


# ---------------------------------------------------------------------------
# SafeJsonLoader 单元测试
# ---------------------------------------------------------------------------

class TestSafeJsonLoader:
    """SafeJsonLoader 核心行为测试"""

    def test_load_valid_json(self, tmp_path):
        """正常 JSON → state=ok"""
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}')
        result = SafeJsonLoader.load_raw(f, mtime_window=0)
        assert result.state == "ok"
        assert result.data == {"key": "value"}

    def test_load_not_found(self, tmp_path):
        """文件不存在 → state=not_found"""
        result = SafeJsonLoader.load_raw(tmp_path / "nonexistent.json", mtime_window=0)
        assert result.state == "not_found"

    def test_load_invalid_json(self, tmp_path):
        """损坏 JSON → state=invalid_json + 备份"""
        f = tmp_path / "corrupted.json"
        f.write_text("{invalid json")
        result = SafeJsonLoader.load_raw(f, mtime_window=0)
        assert result.state == "invalid_json"
        assert result.error is not None
        assert result.backup_path is not None
        assert result.backup_path.exists()
        # 原文件已被移走
        assert not f.exists()

    def test_load_write_in_progress(self, tmp_path):
        """mtime < 60s → state=write_in_progress"""
        f = tmp_path / "writing.json"
        f.write_text('{"key": "value"}')
        # mtime_window=60 → 刚写入的文件会被跳过
        result = SafeJsonLoader.load_raw(f, mtime_window=60)
        assert result.state == "write_in_progress"

    def test_load_schema_validation_failed(self, tmp_path):
        """Schema 校验失败 → state=schema_validation_failed + 备份"""
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            required_field: str

        f = tmp_path / "schema_fail.json"
        f.write_text('{"wrong_field": 123}')
        result = SafeJsonLoader.load(f, TestSchema, mtime_window=0)
        assert result.state == "schema_validation_failed"
        assert result.backup_path is not None

    def test_load_schema_ok(self, tmp_path):
        """Schema 校验通过 → state=ok + parsed 对象"""
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            name: str
            value: int = 0

        f = tmp_path / "valid.json"
        f.write_text('{"name": "test", "value": 42}')
        result = SafeJsonLoader.load(f, TestSchema, mtime_window=0)
        assert result.state == "ok"
        assert result.parsed.name == "test"
        assert result.parsed.value == 42


# ---------------------------------------------------------------------------
# 故障注入：MANIFEST 损坏
# ---------------------------------------------------------------------------

class TestManifestCorruption:
    """MANIFEST.json 损坏场景"""

    def test_manifest_invalid_json_triggers_explicit_degradation(self, tmp_path):
        """MANIFEST 是无效 JSON → 显式降级（不静默跳过）"""
        from domains.deliver_pro.smart_assembler import SmartAssembler

        # 创建损坏的 MANIFEST
        task_dir = tmp_path / "worker_outputs" / "T-001"
        task_dir.mkdir(parents=True)
        (task_dir / "MANIFEST.json").write_text("{corrupted")
        (task_dir / "DELIVERABLE.md").write_text("# Content")
        (task_dir / "EVIDENCE.md").write_text("evidence")
        (task_dir / "ISSUES.md").write_text("issues")

        # SmartAssembler 应识别损坏并标记为 missing
        plan = {"tasks": [{"task_id": "T-001", "title": "Test"}], "task_graph": [{"task_id": "T-001"}]}
        assembler = SmartAssembler(
            worker_outputs_dir=tmp_path / "worker_outputs",
            plan_data=plan,
            output_dir=tmp_path / "output",
        )
        result = assembler.run()
        assert result.workers_failed == 1
        assert "T-001" in result.coverage_gaps

    def test_manifest_missing_triggers_explicit_degradation(self, tmp_path):
        """MANIFEST 不存在 → 显式降级"""
        from domains.deliver_pro.smart_assembler import SmartAssembler

        task_dir = tmp_path / "worker_outputs" / "T-001"
        task_dir.mkdir(parents=True)
        (task_dir / "DELIVERABLE.md").write_text("# Content")

        plan = {"tasks": [{"task_id": "T-001", "title": "Test"}], "task_graph": [{"task_id": "T-001"}]}
        assembler = SmartAssembler(
            worker_outputs_dir=tmp_path / "worker_outputs",
            plan_data=plan,
            output_dir=tmp_path / "output",
        )
        result = assembler.run()
        assert result.workers_failed == 1
        assert "T-001" in result.coverage_gaps


# ---------------------------------------------------------------------------
# 故障注入：batch_progress 损坏
# ---------------------------------------------------------------------------

class TestBatchProgressCorruption:
    """batch_progress.json 损坏场景"""

    def test_corrupted_batch_progress_triggers_rebuild(self, mock_blackboard):
        """batch_progress 损坏 → 备份 + 从文件证据重建"""
        bb_root, project_name = mock_blackboard

        # 写入损坏的 batch_progress
        progress_path = bb_root / project_name / "batch_progress.json"
        progress_path.write_text("{corrupted json")

        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            from domains.deliver_pro.orchestrator import DeliverOrchestrator
            orch = DeliverOrchestrator(project_name)
            # 应该不崩溃，progress 为空 dict（或从文件系统重建）
            assert isinstance(orch.progress, dict)

        # 损坏文件应被备份
        assert not progress_path.exists()  # 原文件已移走
        backups = list((bb_root / project_name).glob("batch_progress.corrupted.*"))
        assert len(backups) > 0

    def test_valid_batch_progress_loads_normally(self, mock_blackboard):
        """正常 batch_progress → 正常加载"""
        bb_root, project_name = mock_blackboard

        progress_path = bb_root / project_name / "batch_progress.json"
        progress_path.write_text(json.dumps({
            "AAA-001": {"phase": "DONE", "task_attempts": {}, "task_spawned_at": {},
                        "terminal_failed": False, "dispatch_confirmed": {}},
            "_meta": {"version": 1},
        }))

        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            from domains.deliver_pro.orchestrator import DeliverOrchestrator
            orch = DeliverOrchestrator(project_name)
            assert "AAA-001" in orch.progress
            assert orch.progress["AAA-001"]["phase"] == "DONE"


# ---------------------------------------------------------------------------
# 故障注入：_pulse_state 损坏
# ---------------------------------------------------------------------------

class TestPulseStateCorruption:
    """_pulse_state.json 损坏场景"""

    def test_corrupted_pulse_state_conservative_rebuild(self, mock_blackboard):
        """_pulse_state 损坏 → 保守重建（zero_progress_count 接近阈值）"""
        bb_root, project_name = mock_blackboard

        state_path = bb_root / project_name / "_pulse_state.json"
        state_path.write_text("{corrupted")

        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            from domains.deliver_pro.orchestrator import DeliverOrchestrator, STALLED_ALERT_THRESHOLD
            orch = DeliverOrchestrator(project_name)
            state, alert = orch._update_pulse_state(0, {
                "completed": 0, "terminal_failed": 0, "total_wps": 1,
            })
            # 保守策略：zero_progress_count 在阈值附近（重建后会被递增）
            assert state["zero_progress_count"] >= STALLED_ALERT_THRESHOLD - 2
            assert state.get("_recovered") is True


# ---------------------------------------------------------------------------
# 不变量测试
# ---------------------------------------------------------------------------

class TestInvariants:
    """不变量测试：验证系统状态一致性"""

    def _setup_completed_project(self, mock_blackboard):
        """设置已完成的项目（跳过 Final Synthesis 前置检查）"""
        bb_root, project_name = mock_blackboard
        # 写入 .deliver_completed.json 使 pulse 走快速通道
        completed_path = bb_root / project_name / ".deliver_completed.json"
        completed_path.write_text(json.dumps({
            "total_wps": 1, "completed": 1, "terminal_failed": 0,
        }))
        # 写入 living_spec（Final Synthesis 前置检查需要）
        spec_dir = bb_root / project_name / "data"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "living_spec.json").write_text(json.dumps({
            "requirements": [{"id": "R1", "text": "test"}],
        }))
        return bb_root, project_name

    def test_pulse_tick_preserves_parseable_state(self, mock_blackboard):
        """pulse tick 后所有状态文件仍可解析"""
        bb_root, project_name = self._setup_completed_project(mock_blackboard)

        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            from domains.deliver_pro.orchestrator import DeliverOrchestrator
            orch = DeliverOrchestrator(project_name)
            report = orch.pulse()

            # _pulse_actions 可解析
            actions_path = bb_root / project_name / "_pulse_actions.json"
            if actions_path.exists():
                result = SafeJsonLoader.load_raw(actions_path, mtime_window=0)
                assert result.state == "ok", f"_pulse_actions corrupted after pulse: {result.error}"

    def test_state_files_not_empty_after_pulse(self, mock_blackboard):
        """pulse 后状态文件不为空"""
        bb_root, project_name = self._setup_completed_project(mock_blackboard)

        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            from domains.deliver_pro.orchestrator import DeliverOrchestrator
            orch = DeliverOrchestrator(project_name)
            orch.pulse()

            # _pulse_actions 应有内容
            actions_path = bb_root / project_name / "_pulse_actions.json"
            if actions_path.exists():
                data = json.loads(actions_path.read_text())
                assert "pulse_id" in data, "_pulse_actions missing pulse_id after pulse"
