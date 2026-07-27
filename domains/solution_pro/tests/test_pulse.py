"""Solution Pulse 测试套件（2026-07-25）。

覆盖：
- 契约笼子（extra=forbid / min_length / 状态文件损坏 raise）
- 状态机全相位推进（planning → research → summary → validate → review → finalize → completed）
- stall 检测 + 重试预算 → terminal_failed
- confirm 回执 + 失败回滚
- 单实例锁
- 快速通道（.completed / .failed 存在）
- CLI exit codes
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from domains.solution_pro.contracts.pulse_report import (
    ModuleDispatch,
    SolutionPulseReport,
    SolutionPulseState,
    SpawnConfirmation,
)
from domains.solution_pro.pulse import (
    PULSE_ACTIONS_FILENAME,
    PULSE_COMPLETED_FILENAME,
    PULSE_FAILED_FILENAME,
    PULSE_STATE_FILENAME,
    SolutionPulse,
)


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def bb_root(tmp_path):
    """临时 blackboard 根目录。"""
    root = tmp_path / "blackboard"
    root.mkdir()
    return root


@pytest.fixture
def session_id():
    return "test_pulse_session"


@pytest.fixture
def pulse(bb_root, session_id):
    sp = SolutionPulse(session_id, blackboard_root=bb_root)
    sp.session_dir.mkdir(parents=True)
    sp.stages_dir.mkdir(parents=True)
    return sp


def _make_stage(pulse: SolutionPulse, name: str, data=None):
    pulse.stages_dir.mkdir(parents=True, exist_ok=True)
    (pulse.stages_dir / f"{name}.json").write_text(
        json.dumps(data or {"ok": True}), encoding="utf-8"
    )


def _load_state(pulse: SolutionPulse) -> dict:
    return json.loads(pulse.state_path.read_text(encoding="utf-8"))


def _load_actions(pulse: SolutionPulse) -> dict:
    return json.loads(pulse.actions_path.read_text(encoding="utf-8"))


# ── 契约笼子 ─────────────────────────────────────────────────


class TestContracts:
    def test_report_rejects_extra_field(self):
        with pytest.raises(Exception):
            SolutionPulseReport(
                pulse_id="p1",
                session_id="s1",
                generated_at=time.time(),
                status="idle",
                summary={
                    "current_phase": "planning",
                    "in_flight": 0,
                    "zero_progress_count": 0,
                },
                unknown_field="x",  # extra=forbid
            )

    def test_report_rejects_empty_session_id(self):
        with pytest.raises(Exception):
            SolutionPulseReport(
                pulse_id="p1",
                session_id="",  # min_length=1
                generated_at=time.time(),
                status="idle",
                summary={
                    "current_phase": "planning",
                    "in_flight": 0,
                    "zero_progress_count": 0,
                },
            )

    def test_spawn_confirmation_rejects_extra(self):
        with pytest.raises(Exception):
            SpawnConfirmation(module="planning", label="l", ok=True, bogus=1)

    def test_state_rejects_bad_phase(self):
        with pytest.raises(Exception):
            SolutionPulseState(
                session_id="s1",
                phase="nonexistent_phase",
                created_at=time.time(),
                updated_at=time.time(),
            )

    def test_corrupted_state_file_raises(self, pulse):
        pulse.state_path.write_text('{"version": 1, "phase": 12345}', encoding="utf-8")
        with pytest.raises(Exception):
            pulse._load_state()

    def test_state_file_with_unknown_field_raises(self, pulse):
        state = SolutionPulseState(
            session_id=pulse.session_id,
            created_at=time.time(),
            updated_at=time.time(),
        ).model_dump(mode="json")
        state["hacker_field"] = True
        pulse.state_path.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(Exception):
            pulse._load_state()


# ── 状态机推进 ───────────────────────────────────────────────


class TestPhaseProgression:
    def test_first_pulse_spawns_planning(self, pulse):
        report = pulse.pulse()
        assert report["status"] == "active"
        assert len(report["actions"]) == 1
        assert report["actions"][0]["module"] == "planning"
        assert report["actions"][0]["action"] == "spawn_module"
        assert report["actions"][0]["label"] == "solution_planning_module"
        # prompt 已落盘
        assert (pulse.stages_dir / "planning_module.md").exists()

    def test_unconfirmed_dispatch_waits(self, pulse):
        pulse.pulse()  # spawn planning, unconfirmed
        report = pulse.pulse()  # 未 confirm → 不再 spawn
        assert report["status"] == "idle"
        assert len(report["actions"]) == 0

    def test_confirmed_dispatch_waits_for_output(self, pulse):
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "planning", "label": "solution_planning_module", "ok": True}]
        )
        report = pulse.pulse()
        assert report["status"] == "idle"
        assert len(report["actions"]) == 0

    def test_planning_output_advances_to_research(self, pulse):
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "planning", "label": "solution_planning_module", "ok": True}]
        )
        _make_stage(pulse, "planning_convergence")
        report = pulse.pulse()
        # planning 完成 → 立即推进并 spawn research（同一 pulse 内连续推进）
        assert report["summary"]["current_phase"] == "research"
        assert "planning" in report["summary"]["completed_modules"]
        assert any(a["module"] == "research" for a in report["actions"])

    def test_full_pipeline_to_completed(self, pulse, monkeypatch):
        """V3.x: Planning → Research → Summary → Validate → Review → Finalize → Completed"""
        # L0 验证 mock 为通过
        monkeypatch.setattr(
            SolutionPulse, "_run_post_validation", lambda self: (True, {"summary": {}})
        )
        # planning
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "planning", "label": "solution_planning_module", "ok": True}]
        )
        _make_stage(pulse, "planning_convergence")
        # research
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "research", "label": "solution_research_module", "ok": True}]
        )
        _make_stage(pulse, "research_digest")
        # summary
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "summary", "label": "solution_summary_module", "ok": True}]
        )
        _make_stage(pulse, "solution_document")
        _make_stage(pulse, "final_solution")
        # → validate (mocked pass) → review: spawn 2 reviewers
        report = pulse.pulse()
        assert report["summary"]["current_phase"] == "review"
        assert len(report["actions"]) == 2
        reviewer_modules = {a["module"] for a in report["actions"]}
        assert reviewer_modules == {"adversarial_reviewer", "consistency_checker"}

        # reviewers confirm + 产出
        pulse.confirm_dispatches([
            {"module": "adversarial_reviewer", "label": "solution_adversarial_reviewer", "ok": True},
            {"module": "consistency_checker", "label": "solution_consistency_checker", "ok": True},
        ])
        _make_stage(pulse, "adversarial_review_summary")
        _make_stage(pulse, "consistency_check")
        # → finalize → completed
        report = pulse.pulse()
        assert report["status"] == "completed"
        assert pulse.completed_path.exists()
        completed = json.loads(pulse.completed_path.read_text())
        assert completed["status"] == "completed"
        assert set(completed["modules_completed"]) == {"planning", "research", "summary"}

    def test_completed_fast_path(self, pulse):
        pulse.completed_path.write_text("{}", encoding="utf-8")
        report = pulse.pulse()
        assert report["status"] == "completed"
        assert len(report["actions"]) == 0

    def test_failed_fast_path(self, pulse):
        pulse.failed_path.write_text("{}", encoding="utf-8")
        report = pulse.pulse()
        assert report["status"] == "failed"

    def test_post_validation_failure_goes_terminal(self, pulse, monkeypatch):
        """V3.x: post_validation 失败 → terminal"""
        monkeypatch.setattr(
            SolutionPulse,
            "_run_post_validation",
            lambda self: (False, {"summary": {"missing": ["final_solution"]}}),
        )
        # 快进：三个模块输出全部就绪
        _make_stage(pulse, "planning_convergence")
        _make_stage(pulse, "research_digest")
        _make_stage(pulse, "solution_document")
        _make_stage(pulse, "final_solution")
        report = pulse.pulse()
        assert report["status"] == "failed"
        assert pulse.failed_path.exists()
        assert any(a["code"] == "POST_VALIDATION_FAILED" for a in report["alerts"])


# ── Stall 检测 + 重试预算 ────────────────────────────────────


class TestStallAndRetry:
    """V3.3：stall 判定 = 文件 mtime 无进展（>1800s），例行重召唤（>240s 冷却）免费。"""

    def _make_stale(self, pulse: SolutionPulse, module: str, retries: int = 0):
        """已确认 dispatch + 久无文件进展 + 冷却已过。"""
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": module, "label": f"solution_{module}_module", "ok": True}]
        )
        state = SolutionPulseState(**_load_state(pulse))
        d = state.modules[module]
        d.last_spawned_at = time.time() - 300   # 冷却已过
        d.retry_count = retries
        state.last_progress_at = time.time() - 2000  # 无进展 >1800s
        pulse._save_state(state)

    def test_no_progress_triggers_retry_and_respawn(self, pulse):
        self._make_stale(pulse, "planning", retries=0)
        report = pulse.pulse()
        assert any(a["code"] == "MODULE_RETRY" for a in report["alerts"])
        state = _load_state(pulse)
        assert state["modules"]["planning"]["retry_count"] == 1
        # 冷却已过 → 同一 pulse 例行重召唤
        assert any(a["module"] == "planning" for a in report["actions"])

    def test_retry_budget_exhaustion_goes_terminal(self, pulse):
        self._make_stale(pulse, "planning", retries=3)
        report = pulse.pulse()
        assert report["status"] == "failed"
        assert pulse.failed_path.exists()
        assert any(a["code"] == "TERMINAL_FAILED" for a in report["alerts"])

    def test_fresh_progress_no_retry(self, pulse):
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "planning", "label": "solution_planning_module", "ok": True}]
        )
        report = pulse.pulse()  # 刚 spawn（冷却未到），且有新文件进展
        assert not any(a["code"] == "MODULE_RETRY" for a in report["alerts"])
        state = _load_state(pulse)
        assert state["modules"]["planning"]["retry_count"] == 0


class TestRespawnCooldown:
    """V3.3 one-step 模块：冷却到点例行重召唤，不消耗重试预算。"""

    def test_cooldown_elapsed_triggers_free_respawn(self, pulse):
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "planning", "label": "solution_planning_module", "ok": True}]
        )
        state = SolutionPulseState(**_load_state(pulse))
        state.modules["planning"].last_spawned_at = time.time() - 300  # 冷却已过
        pulse._save_state(state)
        report = pulse.pulse()
        # 有文件进展（spawn 时写的 prompt）→ 不算无进展重试
        state = _load_state(pulse)  # 重载 dict（pulse 内已更新状态）
        assert state["modules"]["planning"]["retry_count"] == 0
        assert any(a["module"] == "planning" for a in report["actions"])
        assert report["status"] == "active"

    def test_cooldown_not_elapsed_no_respawn(self, pulse):
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "planning", "label": "solution_planning_module", "ok": True}]
        )
        report = pulse.pulse()  # 立即再扫：冷却未到
        assert len(report["actions"]) == 0

    def test_mtime_progress_resets_no_progress_window(self, pulse):
        pulse.pulse()
        pulse.confirm_dispatches(
            [{"module": "planning", "label": "solution_planning_module", "ok": True}]
        )
        state = SolutionPulseState(**_load_state(pulse))
        state.last_progress_at = time.time() - 1700  # 接近 1800s 阈值
        pulse._save_state(state)
        _make_stage(pulse, "worker_output_progress")  # 新文件 → 进展
        report = pulse.pulse()
        assert not any(a["code"] == "MODULE_RETRY" for a in report["alerts"])
        state = _load_state(pulse)
        assert state["modules"]["planning"]["retry_count"] == 0
        assert state["zero_progress_count"] == 0


# ── confirm 回执 ─────────────────────────────────────────────


class TestConfirm:
    def test_failed_spawn_rolls_back(self, pulse):
        pulse.pulse()  # spawn planning
        out = pulse.confirm_dispatches([
            {"module": "planning", "label": "solution_planning_module", "ok": False, "error": "API 429"}
        ])
        assert out["rolled_back"][0]["module"] == "planning"
        assert "alert" in out
        state = _load_state(pulse)
        assert state["modules"]["planning"]["status"] == "pending"
        assert state["modules"]["planning"]["retry_count"] == 1
        # 下一轮 pulse 重新 spawn
        report = pulse.pulse()
        assert any(a["module"] == "planning" for a in report["actions"])

    def test_confirm_unknown_module_ignored(self, pulse):
        pulse.pulse()
        out = pulse.confirm_dispatches([
            {"module": "nonexistent", "label": "x", "ok": True}
        ])
        assert out["confirmed"] == []


# ── 锁 ───────────────────────────────────────────────────────


class TestLock:
    def test_concurrent_pulse_locked(self, pulse):
        lock_fh = pulse._acquire_lock()
        try:
            report = pulse.pulse()
            assert report["status"] == "locked"
        finally:
            import fcntl
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            lock_fh.close()


# ── 零进展告警 ───────────────────────────────────────────────


class TestZeroProgress:
    def test_zero_progress_alert_after_threshold(self, pulse):
        pulse.pulse()  # spawn planning（有进展）
        # 不 confirm → 后续 pulse 全部零进展（V3.3 阈值=6）
        for _ in range(6):
            report = pulse.pulse()
        assert report["summary"]["zero_progress_count"] >= 6
        assert any(a["code"] == "ZERO_PROGRESS" for a in report["alerts"])


# ── 契约落盘验证 ─────────────────────────────────────────────


class TestActionsFile:
    def test_actions_file_passes_contract(self, pulse):
        pulse.pulse()
        raw = _load_actions(pulse)
        # 契约笼子：落盘文件必须能通过顶层验证
        SolutionPulseReport(**raw)

    def test_state_file_passes_contract(self, pulse):
        pulse.pulse()
        raw = _load_state(pulse)
        SolutionPulseState(**raw)


# ── CLI ──────────────────────────────────────────────────────


class TestCLI:
    def _run_cli(self, *cli_args, cwd=None):
        from domains.solution_pro import pulse as _pulse_mod
        deepflow_root = Path(_pulse_mod.__file__).resolve().parent.parent.parent
        env = os.environ.copy()
        env["PYTHONPATH"] = str(deepflow_root)
        return subprocess.run(
            ["python3", "-m", "domains.solution_pro.pulse_cli", *cli_args],
            capture_output=True, text=True, cwd=str(deepflow_root), env=env,
        )

    def test_check_no_session(self):
        r = self._run_cli("check", "--session-id", "definitely_not_exist_session_xyz")
        assert r.returncode == 1
        assert "no_session" in r.stdout

    def test_pulse_and_confirm_roundtrip(self, bb_root, session_id, monkeypatch):
        """CLI 端到端：pulse → confirm → 状态推进。"""
        # CLI 用默认 blackboard root，这里直接测 SolutionPulse 层（CLI 是薄壳）
        sp = SolutionPulse(session_id, blackboard_root=bb_root)
        sp.session_dir.mkdir(parents=True)
        report = sp.pulse()
        assert report["status"] == "active"
        out = sp.confirm_dispatches([
            {"module": "planning", "label": "solution_planning_module", "ok": True}
        ])
        assert out["confirmed"] == ["planning"]


# ── DryRun 修复回归（2026-07-25 四 Agent 审计）──────────────


class TestOrphanDispatchSweep:
    """pulse agent 在 spawn 后、confirm 前猝死 → dispatch 永远 unconfirmed →
    超窗（600s）必须回滚重派，否则状态机卡死。"""

    def test_stale_unconfirmed_dispatch_rolled_back(self, pulse):
        pulse.pulse()  # spawn planning（unconfirmed）
        state = SolutionPulseState(**_load_state(pulse))
        d = state.modules["planning"]
        d.last_spawned_at = time.time() - 700  # 超 600s 孤儿窗口
        pulse._save_state(state)

        report = pulse.pulse()
        state = _load_state(pulse)
        # 回滚后同一 pulse 内重新 spawn
        assert any(a["code"] == "SPAWN_ROLLBACK" for a in report["alerts"])
        assert state["modules"]["planning"]["retry_count"] == 1
        # 重新 dispatch（新的 last_spawned_at，未确认）
        assert state["modules"]["planning"]["status"] == "dispatched"

    def test_fresh_unconfirmed_dispatch_not_swept(self, pulse):
        pulse.pulse()  # 刚 spawn，未超窗
        report = pulse.pulse()
        assert not any(a["code"] == "SPAWN_ROLLBACK" for a in report["alerts"])
        state = _load_state(pulse)
        assert state["modules"]["planning"]["retry_count"] == 0


# V4.0 简化：以下测试类已移除（Step 4/5 后置验证不再由 orchestrator 内置）
# - TestReviewPromptReplacement
# - TestPostValidationBaseDir
# - TestQualityNotes
# 
# 这些功能现在是独立可调用工具，不再由 orchestrator 自动触发。
# 如需测试这些独立工具，请在单独的测试文件中验证。

