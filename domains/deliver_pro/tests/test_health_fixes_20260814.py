"""体检修复回归测试（2026-08-14 深度体检 → 根因修复）

覆盖四个修复点：
- P0-A: 前置条件缺失（living_spec）→ 结构化 blocked（不崩溃 / 告警降级防风暴 / 条件恢复自愈）
- P0-B: 终态自停 — all_resolved 但含永久失败 → 写 .deliver_completed.json + status=completed
       （根除僵尸项目被调度器无限轮询的生产事故）
- P1-C: SafeJsonLoader 熔断 — 同一文件连续损坏 ≥3 次 → CircuitBreakerTripped；
       成功读取清零；计数器独立文件；frozen 快速通道；circuit_breaker_freeze 助手；unfreeze 命令
- P1-D: ValidationVerdict.from_json / cmd_confirm 损坏输入显式处理（不裸 traceback）

验收证据：本文件全绿 + `pytest domains/deliver_pro` 全量回归。
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures（对齐 test_pulse.py / test_final_synthesis.py 风格）
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
    project_name = "test-health-fixes"
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


def _setup_living_spec(bb_root, project_name):
    data_dir = bb_root / project_name / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "requirements": [
            {"id": "R1", "text": "Test requirement", "priority": "MUST"},
        ],
        "sections": ["Introduction"],
    }
    (data_dir / "living_spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    return data_dir / "living_spec.json"


def _zeros_summary(report):
    return report["summary"]


# ---------------------------------------------------------------------------
# P1-C: SafeJsonLoader 熔断（单元层）
# ---------------------------------------------------------------------------

class TestCircuitBreakerLoader:
    def test_trips_after_consecutive_corruptions(self, tmp_path):
        """同一文件连续损坏 ≥ 阈值 → raise CircuitBreakerTripped。"""
        from domains.deliver_pro.utils.safe_json_loader import (
            CIRCUIT_BREAKER_THRESHOLD,
            CircuitBreakerTripped,
            SafeJsonLoader,
        )

        f = tmp_path / "manifest.json"
        for _ in range(CIRCUIT_BREAKER_THRESHOLD - 1):
            f.write_text("{broken")
            result = SafeJsonLoader.load_raw(f, mtime_window=0)
            assert result.state == "invalid_json"
            assert not f.exists()  # 损坏文件已被备份移走
        f.write_text("{broken")
        with pytest.raises(CircuitBreakerTripped) as exc_info:
            SafeJsonLoader.load_raw(f, mtime_window=0)
        assert exc_info.value.count == CIRCUIT_BREAKER_THRESHOLD
        assert exc_info.value.path == f

    def test_success_resets_counter(self, tmp_path):
        """成功读取 → 计数清零（瞬态损坏不应累积熔断）。"""
        from domains.deliver_pro.utils.safe_json_loader import (
            SafeJsonLoader,
            corruption_counter_path,
        )

        f = tmp_path / "state.json"
        # 损坏两次（未达阈值 3）
        for _ in range(2):
            f.write_text("{broken")
            SafeJsonLoader.load_raw(f, mtime_window=0)
        assert corruption_counter_path(f).exists()
        # 成功读取 → 清零
        f.write_text('{"ok": true}')
        result = SafeJsonLoader.load_raw(f, mtime_window=0)
        assert result.state == "ok"
        assert not corruption_counter_path(f).exists()
        # 清零后再次损坏 2 次仍不熔断
        for _ in range(2):
            f.unlink(missing_ok=True)
            f.write_text("{broken")
            result = SafeJsonLoader.load_raw(f, mtime_window=0)
            assert result.state == "invalid_json"

    def test_counter_file_is_independent(self, tmp_path):
        """计数器是独立隐藏文件（教训：retry counter 必须独立文件）。"""
        from domains.deliver_pro.utils.safe_json_loader import (
            SafeJsonLoader,
            corruption_counter_path,
        )

        f = tmp_path / "x.json"
        f.write_text("{broken")
        SafeJsonLoader.load_raw(f, mtime_window=0)
        counter = corruption_counter_path(f)
        assert counter.exists()
        assert counter.name == ".x.json.corrupt_count"
        assert counter.read_text().strip() == "1"

    def test_schema_failure_also_counts(self, tmp_path):
        """Schema 校验失败同样计入熔断。"""
        from pydantic import BaseModel

        from domains.deliver_pro.utils.safe_json_loader import (
            CircuitBreakerTripped,
            SafeJsonLoader,
        )

        class Strict(BaseModel):
            required_field: int

        f = tmp_path / "s.json"
        for _ in range(2):
            f.write_text('{"wrong": 1}')
            result = SafeJsonLoader.load(f, Strict, mtime_window=0)
            assert result.state == "schema_validation_failed"
        f.write_text('{"wrong": 1}')
        with pytest.raises(CircuitBreakerTripped):
            SafeJsonLoader.load(f, Strict, mtime_window=0)


# ---------------------------------------------------------------------------
# P0-A: 前置条件缺失 → 结构化 blocked
# ---------------------------------------------------------------------------

class TestBlockedPrecondition:
    def test_missing_living_spec_returns_blocked_not_crash(self, mock_blackboard):
        """无 living_spec → status=blocked + CRITICAL 告警 + 标记落盘（不再 raise）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project_name):
            report = orch.pulse()
        assert report["status"] == "blocked"
        assert report["actions"] == []
        assert any(
            a["code"] == "PRECONDITION_MISSING" and a["severity"] == "CRITICAL"
            for a in report["alerts"]
        )
        marker = bb_root / project_name / "_pulse_blocked.json"
        assert marker.exists()
        marker_data = json.loads(marker.read_text())
        assert marker_data["code"] == "PRECONDITION_MISSING"

    def test_second_pulse_alert_downgraded(self, mock_blackboard):
        """持续阻塞 → 告警降级 INFO（防飞书 5 分钟风暴）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project_name):
            orch.pulse()
            report2 = orch.pulse()
        assert report2["status"] == "blocked"
        assert all(a["severity"] != "CRITICAL" for a in report2["alerts"])
        assert any(a["code"] == "STILL_BLOCKED" for a in report2["alerts"])

    def test_precondition_recovery_self_heals(self, mock_blackboard):
        """living_spec 补齐 → 自动清除阻塞标记，正常产出 infer 动作。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project_name):
            orch.pulse()  # blocked
            assert (bb_root / project_name / "_pulse_blocked.json").exists()
            _setup_living_spec(bb_root, project_name)
            report = orch.pulse()
        assert report["status"] == "active"
        assert len(report["actions"]) == 1
        assert report["actions"][0]["action"] == "infer_deliverable_contract"
        assert not (bb_root / project_name / "_pulse_blocked.json").exists()


# ---------------------------------------------------------------------------
# P0-B: 终态自停（僵尸轮询根因修复）
# ---------------------------------------------------------------------------

class TestTerminalSelfStop:
    def _mark_all_terminal_failed(self, orch):
        for wp in ("AAA-001", "BBB-001"):
            orch.progress[wp] = {
                "terminal_failed": True,
                "task_attempts": {"T-001": 1},
                "phase": "PENDING",
            }
        orch._save_progress()

    def test_all_terminal_failed_writes_completed_marker(self, mock_blackboard):
        """全部 WP 永久失败 → 写终态标记 + status=completed + CRITICAL 告警。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project_name):
            self._mark_all_terminal_failed(orch)
            report = orch.pulse()

        assert report["status"] == "completed"
        assert any(a["code"] == "TERMINAL_SELF_STOP" for a in report["alerts"])

        completed_path = bb_root / project_name / ".deliver_completed.json"
        assert completed_path.exists()
        completed = json.loads(completed_path.read_text())
        assert completed["terminal_failed"] == 2
        assert completed["final_synthesis_done"] is False
        assert set(completed["terminal_failed_wps"]) == {"AAA-001", "BBB-001"}
        assert completed["outcome"] == "terminal_failed_self_stop"

    def test_second_pulse_takes_completed_fast_path(self, mock_blackboard):
        """终态标记写入后，后续 pulse 走 A8 快速通道（零工作）。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project_name):
            self._mark_all_terminal_failed(orch)
            orch.pulse()
            report2 = orch.pulse()
        assert report2["status"] == "completed"
        assert report2["actions"] == []
        assert report2["alerts"] == []
        assert report2["summary"]["terminal_failed"] == 2


# ---------------------------------------------------------------------------
# P1-C: 冻结通道 + freeze 助手 + unfreeze（编排层）
# ---------------------------------------------------------------------------

class TestCircuitBreakerFreeze:
    def test_frozen_fast_path_is_noop(self, mock_blackboard):
        """冻结标记存在 → pulse 零工作零告警。"""
        with _make_orchestrator(mock_blackboard) as (orch, bb_root, project_name):
            (bb_root / project_name / "_circuit_breaker.json").write_text(
                json.dumps({"frozen_at": 1.0})
            )
            report = orch.pulse()
        assert report["status"] == "frozen"
        assert report["actions"] == []
        assert report["alerts"] == []

    def test_circuit_breaker_freeze_helper(self, mock_blackboard):
        """freeze 助手：写标记 + 返回带 CRITICAL 告警的 frozen 报告。"""
        from domains.deliver_pro.orchestrator import circuit_breaker_freeze
        from domains.deliver_pro.utils.safe_json_loader import CircuitBreakerTripped

        bb_root, project_name = mock_blackboard
        exc = CircuitBreakerTripped(Path("/tmp/x.json"), 3)
        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            report = circuit_breaker_freeze(project_name, exc)
        assert report["status"] == "frozen"
        assert report["alerts"][0]["code"] == "CIRCUIT_BREAKER"
        assert report["alerts"][0]["severity"] == "CRITICAL"
        marker = bb_root / project_name / "_circuit_breaker.json"
        assert marker.exists()
        marker_data = json.loads(marker.read_text())
        assert marker_data["consecutive_corruptions"] == 3

    def test_unfreeze_clears_marker_and_counters(self, mock_blackboard):
        """unfreeze：清除冻结标记 + 全部损坏计数器。"""
        from domains.deliver_pro import pulse_cli

        bb_root, project_name = mock_blackboard
        project_dir = bb_root / project_name
        (project_dir / "_circuit_breaker.json").write_text(json.dumps({"frozen_at": 1.0}))
        (project_dir / ".a.json.corrupt_count").write_text("2")
        sub = project_dir / "deliver_pro" / "wp_001"
        sub.mkdir(parents=True)
        (sub / ".b.json.corrupt_count").write_text("1")

        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            rc = pulse_cli.cmd_unfreeze(
                SimpleNamespace(project=project_name, clear_blocked=False)
            )
        assert rc == 0
        assert not (project_dir / "_circuit_breaker.json").exists()
        assert list(project_dir.rglob(".*.corrupt_count")) == []

    def test_unfreeze_noop_when_not_frozen(self, mock_blackboard):
        from domains.deliver_pro import pulse_cli

        bb_root, project_name = mock_blackboard
        with patch("domains.deliver_pro.BLACKBOARD_ROOT", bb_root):
            rc = pulse_cli.cmd_unfreeze(
                SimpleNamespace(project=project_name, clear_blocked=False)
            )
        assert rc == 0


# ---------------------------------------------------------------------------
# P1-D: 损坏输入显式处理
# ---------------------------------------------------------------------------

class TestJsonHardening:
    def test_from_json_corrupted_raises_cleanly(self, tmp_path):
        """validation_result.json 损坏 → ValueError（带备份信息），非裸 JSONDecodeError。"""
        from domains.deliver_pro.contracts.validation_verdict import ValidationVerdict

        f = tmp_path / "validation_result.json"
        f.write_text("{broken")
        with pytest.raises(ValueError, match="不可读"):
            ValidationVerdict.from_json(f)
        # 损坏文件已被备份
        assert list(tmp_path.glob("*.corrupted.*"))

    def test_from_json_missing_raises_file_not_found(self, tmp_path):
        from domains.deliver_pro.contracts.validation_verdict import ValidationVerdict

        with pytest.raises(FileNotFoundError):
            ValidationVerdict.from_json(tmp_path / "nope.json")

    def test_from_json_fresh_valid_file_readable(self, tmp_path):
        """刚写入的合法文件必须可读（mtime_window=0，不误判写入中）。"""
        from domains.deliver_pro.contracts.validation_verdict import ValidationVerdict

        f = tmp_path / "validation_result.json"
        verdict = {
            "verdict": "PASS",
            "round": 1,
            "scores": {
                "completeness": {"score": 5, "weight": 0.2},
                "correctness": {"score": 5, "weight": 0.2},
                "credibility": {"score": 5, "weight": 0.2},
                "actionability": {"score": 5, "weight": 0.2},
                "consistency": {"score": 5, "weight": 0.1},
                "professionalism": {"score": 5, "weight": 0.1},
            },
            "fix_directives": [],
            "summary": "ok",
        }
        f.write_text(json.dumps(verdict))
        v = ValidationVerdict.from_json(f)
        assert v.verdict == "PASS"

    def test_cmd_confirm_bad_json_returns_1(self):
        """worker 回执 JSON 非法 → exit 1 + 明确错误信息（不裸 traceback）。"""
        from domains.deliver_pro import pulse_cli

        rc = pulse_cli.cmd_confirm(
            SimpleNamespace(project="x", results="{bad json", results_file=None)
        )
        assert rc == 1

    def test_assemble_missing_plan_raises(self, tmp_path):
        from domains.deliver_pro.smart_assembler import assemble

        with pytest.raises(FileNotFoundError):
            assemble(tmp_path / "outputs", tmp_path / "no_plan.json", tmp_path / "out")
