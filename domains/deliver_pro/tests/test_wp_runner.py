"""Tests for DeliverWPRunner."""

import json
from pathlib import Path

import pytest

from domains.deliver_pro.contracts import (
    ConcurrencyPlan,
    DeliveryManifest,
    DeliveryStatus,
    ExecutionPlan,
    FixDirective,
    IntegrationReport,
    PipelinePhase,
    RecoveryAction,
    RecoveryStrategy,
    ScoreDimension,
    TaskNode,
    ValidationVerdict,
    Wave,
    WorkerError,
    WorkerOutputMeta,
    WorkPackage,
)
from domains.deliver_pro.wp_runner import (
    MAX_VALIDATE_ROUNDS,
    MAX_WORKER_RECOVERY_ATTEMPTS,
    DeliverWPRunner,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def wp():
    return WorkPackage(
        wp_id="WP-001",
        title="Test Feature",
        objective="Build a test feature",
        scenario="code",
    )


@pytest.fixture
def bb_path(tmp_path):
    return tmp_path / "blackboard" / "test_project"


@pytest.fixture
def orchestrator(wp, bb_path):
    return DeliverWPRunner(wp, bb_path, project_name="test_project")


@pytest.fixture
def sample_plan():
    return ExecutionPlan(
        wp_id="WP-001",
        scenario="code",
        task_graph=[
            TaskNode(task_id="T-001", title="Root task", scenario_type="code"),
            TaskNode(task_id="T-002", title="Child task", depends_on=["T-001"], scenario_type="code"),
        ],
        concurrency_plan=ConcurrencyPlan(
            suggested_parallelism=2,
            waves=[
                Wave(wave=1, task_ids=["T-001"]),
                Wave(wave=2, task_ids=["T-002"]),
            ],
        ),
    )


# ============================================================================
# Initialization
# ============================================================================

class TestInit:
    def test_creates_directories(self, orchestrator, bb_path):
        assert (bb_path / "deliver_pro" / "wp_001" / "data").is_dir()
        assert (bb_path / "deliver_pro" / "wp_001" / "stages").is_dir()
        assert (bb_path / "deliver_pro" / "wp_001" / "stages" / "worker_outputs").is_dir()

    def test_writes_wp_json(self, orchestrator, bb_path):
        wp_path = bb_path / "deliver_pro" / "wp_001" / "data" / "wp.json"
        assert wp_path.exists()
        data = json.loads(wp_path.read_text(encoding="utf-8"))
        assert data["wp_id"] == "WP-001"

    def test_state_initialized(self, orchestrator):
        assert orchestrator.state.wp_id == "WP-001"
        assert orchestrator.state.phase == PipelinePhase.INIT

    def test_wp_not_overwritten(self, wp, bb_path):
        """If wp.json already exists, don't overwrite."""
        orch1 = DeliverWPRunner(wp, bb_path)
        # Modify the file
        wp_path = bb_path / "deliver_pro" / "wp_001" / "data" / "wp.json"
        wp_path.write_text('{"modified": true}', encoding="utf-8")

        orch2 = DeliverWPRunner(wp, bb_path)
        data = json.loads(wp_path.read_text(encoding="utf-8"))
        assert data.get("modified") is True


# ============================================================================
# Phase 1: Analyze
# ============================================================================

class TestPrepareAnalyzeSpawn:
    def test_returns_spawn_params(self, orchestrator):
        params = orchestrator.prepare_analyze_spawn()
        assert params["runtime"] == "subagent"
        assert params["mode"] == "run"
        assert "deliver_analyze_WP-001" in params["label"]
        assert "task" in params
        assert len(params["task"]) > 0

    def test_state_transitions_to_analyzing(self, orchestrator):
        orchestrator.prepare_analyze_spawn()
        assert orchestrator.state.phase == PipelinePhase.ANALYZING


class TestVerifyAnalyzeOutput:
    def test_valid_plan(self, orchestrator, sample_plan):
        # Must transition to ANALYZING first (prepare_analyze_spawn does this)
        orchestrator.state.phase = PipelinePhase.ANALYZING
        plan_data = sample_plan.model_dump(mode="json")
        passed, msg = orchestrator.verify_analyze_output(plan_data)
        assert passed is True
        assert msg == ""

    def test_wp_id_mismatch(self, orchestrator, sample_plan):
        orchestrator.state.phase = PipelinePhase.ANALYZING
        plan_data = sample_plan.model_dump(mode="json")
        plan_data["wp_id"] = "WP-999"
        passed, msg = orchestrator.verify_analyze_output(plan_data)
        assert passed is False
        assert "mismatch" in msg

    def test_empty_task_graph(self, orchestrator):
        """P1-5 fix: zero-worker plan → auto-COMPLETED (not rejected)."""
        orchestrator.state.phase = PipelinePhase.ANALYZING
        plan_data = {
            "wp_id": "WP-001",
            "scenario": "code",
            "task_graph": [],
        }
        passed, msg = orchestrator.verify_analyze_output(plan_data)
        assert passed is True
        assert "zero_worker" in msg
        # Verify state transitioned to COMPLETED
        assert orchestrator.state.phase == PipelinePhase.COMPLETED

    def test_invalid_dag(self, orchestrator):
        orchestrator.state.phase = PipelinePhase.ANALYZING
        plan_data = {
            "wp_id": "WP-001",
            "scenario": "code",
            "task_graph": [
                {"task_id": "T-001", "title": "A", "depends_on": ["T-002"]},
                {"task_id": "T-002", "title": "B", "depends_on": ["T-001"]},
            ],
        }
        passed, msg = orchestrator.verify_analyze_output(plan_data)
        assert passed is False
        assert "cycle" in msg.lower() or "validation" in msg.lower()

    def test_state_transitions_on_success(self, orchestrator, sample_plan):
        orchestrator.state.phase = PipelinePhase.ANALYZING
        plan_data = sample_plan.model_dump(mode="json")
        orchestrator.verify_analyze_output(plan_data)
        assert orchestrator.state.phase == PipelinePhase.GENERATING
        assert "T-001" in orchestrator.state.pending_tasks
        assert "T-002" in orchestrator.state.pending_tasks


# ============================================================================
# Phase 2: Workers
# ============================================================================

class TestPrepareWorkersSpawn:
    def test_ready_tasks(self, orchestrator, sample_plan):
        # Set state to GENERATING with pending tasks
        orchestrator.state.phase = PipelinePhase.GENERATING
        orchestrator.state.pending_tasks = ["T-001", "T-002"]

        params_list = orchestrator.prepare_workers_spawn(sample_plan, completed_tasks=set())
        assert len(params_list) == 1  # Only T-001 is ready (no deps)
        assert params_list[0]["runtime"] == "subagent"
        assert "deliver-worker-wp-001-t-001" in params_list[0]["label"]

    def test_no_ready_tasks(self, orchestrator, sample_plan):
        params_list = orchestrator.prepare_workers_spawn(sample_plan, completed_tasks={"T-001", "T-002"})
        assert params_list == []

    def test_respects_parallelism(self, wp, bb_path):
        plan = ExecutionPlan(
            wp_id="WP-001",
            scenario="code",
            task_graph=[
                TaskNode(task_id=f"T-{i:03d}", title=f"Task {i}") for i in range(5)
            ],
            concurrency_plan=ConcurrencyPlan(suggested_parallelism=2),
        )
        orch = DeliverWPRunner(wp, bb_path)
        orch.state.phase = PipelinePhase.GENERATING
        params_list = orch.prepare_workers_spawn(plan, completed_tasks=set())
        assert len(params_list) == 2  # limited by suggested_parallelism

    def test_after_completed_first_wave(self, orchestrator, sample_plan):
        params_list = orchestrator.prepare_workers_spawn(sample_plan, completed_tasks={"T-001"})
        assert len(params_list) == 1
        assert "deliver-worker-wp-001-t-002" in params_list[0]["label"]


class TestVerifyWorkerOutput:
    def test_valid_output(self, orchestrator, tmp_path):
        task_id = "T-001"
        output_dir = tmp_path / task_id
        output_dir.mkdir()
        # 足够长的内容以通过 MIN_DELIVERABLE_LENGTH=50 检查
        deliverable_content = (
            "# Task Output\n\n"
            "This is a valid deliverable with sufficient content "
            "to pass the minimum length check (50 chars).\n"
        )
        (output_dir / "DELIVERABLE.md").write_text(deliverable_content, encoding="utf-8")
        # P1-2: Create all 4 files for COMPLETE status
        (output_dir / "EVIDENCE.md").write_text("# Evidence\n", encoding="utf-8")
        (output_dir / "ISSUES.md").write_text("无\n", encoding="utf-8")
        manifest = {
            "task_id": task_id,
            "wp_id": "WP-001",
            "scenario": "code",
            "status": "COMPLETE",
        }
        (output_dir / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

        orchestrator.state.running_tasks = [task_id]
        passed, msg, meta = orchestrator.verify_worker_output(task_id, output_dir)
        assert passed is True
        assert meta is not None
        assert meta.status == "COMPLETE"
        assert task_id in orchestrator.state.completed_tasks

    def test_partial_missing_optional_files(self, orchestrator, tmp_path):
        """P1-2: Missing EVIDENCE.md/ISSUES.md should result in PARTIAL status."""
        task_id = "T-001"
        output_dir = tmp_path / task_id
        output_dir.mkdir()
        deliverable_content = (
            "# Task Output\n\n"
            "This is a valid deliverable with sufficient content "
            "to pass the minimum length check (50 chars).\n"
        )
        (output_dir / "DELIVERABLE.md").write_text(deliverable_content, encoding="utf-8")
        # Only create required files, not optional ones
        manifest = {
            "task_id": task_id,
            "wp_id": "WP-001",
            "scenario": "code",
            "status": "COMPLETE",
        }
        (output_dir / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

        orchestrator.state.running_tasks = [task_id]
        passed, msg, meta = orchestrator.verify_worker_output(task_id, output_dir)
        assert passed is True  # Still passes (non-blocking)
        assert meta is not None
        assert meta.status == "PARTIAL"  # But status is overridden to PARTIAL
        assert task_id in orchestrator.state.completed_tasks

    def test_missing_deliverable(self, orchestrator, tmp_path):
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        (output_dir / "MANIFEST.json").write_text("{}", encoding="utf-8")

        passed, msg, meta = orchestrator.verify_worker_output("T-001", output_dir)
        assert passed is False
        assert "DELIVERABLE.md" in msg

    def test_missing_manifest(self, orchestrator, tmp_path):
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        (output_dir / "DELIVERABLE.md").write_text("# Output", encoding="utf-8")

        passed, msg, meta = orchestrator.verify_worker_output("T-001", output_dir)
        assert passed is False
        assert "MANIFEST.json" in msg

    def test_empty_deliverable_rejected(self, orchestrator, tmp_path):
        """Doctor #4: write 空内容 → verify 应拒绝"""
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        # DELIVERABLE.md 存在但内容为空
        (output_dir / "DELIVERABLE.md").write_text("   \n  \n  ", encoding="utf-8")
        (output_dir / "MANIFEST.json").write_text(
            '{"task_id": "T-001", "wp_id": "WP-001", "scenario": "code", '
            '"status": "COMPLETE", "outputs": [], "interfaces": {}, '
            '"quality_self_check": {}, "tool_calls": {}}',
            encoding="utf-8",
        )

        passed, msg, meta = orchestrator.verify_worker_output("T-001", output_dir)
        assert passed is False
        assert "too short" in msg

    def test_short_deliverable_rejected(self, orchestrator, tmp_path):
        """Doctor #4: 内容过短（<50 字符）也应拒绝"""
        output_dir = tmp_path / "T-001"
        output_dir.mkdir()
        (output_dir / "DELIVERABLE.md").write_text("Short content", encoding="utf-8")
        (output_dir / "MANIFEST.json").write_text(
            '{"task_id": "T-001", "wp_id": "WP-001", "scenario": "code", '
            '"status": "COMPLETE", "outputs": [], "interfaces": {}, '
            '"quality_self_check": {}, "tool_calls": {}}',
            encoding="utf-8",
        )

        passed, msg, meta = orchestrator.verify_worker_output("T-001", output_dir)
        assert passed is False
        assert "too short" in msg


# ============================================================================
# Phase 3: Integrate
# ============================================================================

class TestPrepareIntegrateSpawn:
    def test_returns_spawn_params(self, orchestrator, sample_plan):
        orchestrator.state.phase = PipelinePhase.GENERATING
        params = orchestrator.prepare_integrate_spawn(sample_plan)
        assert params["runtime"] == "subagent"
        assert params["mode"] == "run"
        assert "deliver_integrate" in params["label"]

    def test_with_fix_directives(self, orchestrator, sample_plan):
        # prepare_integrate_spawn transitions to INTEGRATING, which requires
        # the state to be GENERATING or WORKER_RETRY. For fix directives,
        # use prepare_fix_integrate_spawn instead (stays in FIX_LOOP).
        orchestrator.state.phase = PipelinePhase.GENERATING
        directives = [
            FixDirective(target="T-001", issue="Bug", fix_instruction="Fix it", priority="high"),
        ]
        params = orchestrator.prepare_integrate_spawn(sample_plan, fix_directives=directives)
        # Bootstrap pattern: task is a reference, content is in the bootstrap file
        import re
        bootstrap_match = re.search(r'`read` 工具读取: `([^`]+)`', params["task"])
        assert bootstrap_match, "Expected bootstrap reference in task"
        bootstrap_content = Path(bootstrap_match.group(1)).read_text(encoding='utf-8')
        assert "修复指令" in bootstrap_content


class TestVerifyIntegrateOutput:
    def test_valid_output(self, orchestrator, tmp_path):
        output_dir = tmp_path / "integrated_draft"
        output_dir.mkdir()
        (output_dir / "DELIVERABLE.md").write_text("# Draft", encoding="utf-8")
        report = {
            "workers_integrated": 2,
            "workers_failed": 0,
            "status": "READY_FOR_VALIDATE",
        }
        (output_dir / "integration_report.json").write_text(json.dumps(report), encoding="utf-8")

        # verify_integrate_output transitions INTEGRATING → VALIDATING
        orchestrator.state.phase = PipelinePhase.INTEGRATING
        passed, msg = orchestrator.verify_integrate_output(output_dir)
        assert passed is True
        assert orchestrator.state.phase == PipelinePhase.VALIDATING
        assert orchestrator.state.round_count == 1

    def test_missing_deliverable(self, orchestrator, tmp_path):
        output_dir = tmp_path / "integrated_draft"
        output_dir.mkdir()
        report = {"workers_integrated": 2, "status": "READY_FOR_VALIDATE"}
        (output_dir / "integration_report.json").write_text(json.dumps(report), encoding="utf-8")

        orchestrator.state.phase = PipelinePhase.INTEGRATING
        passed, msg = orchestrator.verify_integrate_output(output_dir)
        assert passed is False
        assert "DELIVERABLE.md" in msg

    def test_wrong_status(self, orchestrator, tmp_path):
        output_dir = tmp_path / "integrated_draft"
        output_dir.mkdir()
        (output_dir / "DELIVERABLE.md").write_text("# Draft", encoding="utf-8")
        report = {"workers_integrated": 2, "status": "ASSEMBLY_FAILED"}
        (output_dir / "integration_report.json").write_text(json.dumps(report), encoding="utf-8")

        orchestrator.state.phase = PipelinePhase.INTEGRATING
        passed, msg = orchestrator.verify_integrate_output(output_dir)
        assert passed is False
        assert "ASSEMBLY_FAILED" in msg


# ============================================================================
# Phase 4: Validate
# ============================================================================

class TestPrepareValidateSpawn:
    def test_returns_spawn_params(self, orchestrator, sample_plan):
        params = orchestrator.prepare_validate_spawn(sample_plan, round_num=1)
        assert params["runtime"] == "subagent"
        assert "deliver_validate" in params["label"]
        assert "r1" in params["label"]


class TestVerifyValidateOutput:
    def test_valid_verdict(self, orchestrator):
        verdict_data = {
            "round": 1,
            "verdict": "PASS",
            "scores": {
                "completeness": {"score": 4, "max": 5, "weight": 0.25, "notes": ""},
                "correctness": {"score": 4, "max": 5, "weight": 0.25, "notes": ""},
                "credibility": {"score": 4, "max": 5, "weight": 0.20, "notes": ""},
                "actionability": {"score": 4, "max": 5, "weight": 0.15, "notes": ""},
                "consistency": {"score": 3, "max": 5, "weight": 0.10, "notes": ""},
                "professionalism": {"score": 3, "max": 5, "weight": 0.05, "notes": ""},
            },
            "weighted_score": 3.8,
        }
        passed, msg, verdict = orchestrator.verify_validate_output(verdict_data)
        assert passed is True
        assert verdict is not None
        assert verdict.verdict == "PASS"

    def test_invalid_verdict_data(self, orchestrator):
        verdict_data = {"round": 1, "verdict": "INVALID"}
        passed, msg, verdict = orchestrator.verify_validate_output(verdict_data)
        assert passed is False
        assert verdict is None


class TestDecideValidateLoop:
    def _make_verdict(self, verdict="PASS", **kwargs):
        scores = {
            "completeness": ScoreDimension(score=4, weight=0.25),
            "correctness": ScoreDimension(score=4, weight=0.25),
            "credibility": ScoreDimension(score=4, weight=0.20),
            "actionability": ScoreDimension(score=4, weight=0.15),
            "consistency": ScoreDimension(score=3, weight=0.10),
            "professionalism": ScoreDimension(score=3, weight=0.05),
        }
        defaults = dict(
            round=1,
            verdict=verdict,
            scores=scores,
            weighted_score=3.8,
            has_fixable=True,
            should_continue=True,
        )
        defaults.update(kwargs)
        return ValidationVerdict(**defaults)

    def test_pass_goes_to_phase5(self, orchestrator):
        verdict = self._make_verdict("PASS")
        result = orchestrator.decide_validate_loop(verdict)
        assert result == "pass"

    def test_max_rounds_stop(self, orchestrator):
        orchestrator.state.round_count = MAX_VALIDATE_ROUNDS
        verdict = self._make_verdict("CONDITIONAL", weighted_score=3.2)
        result = orchestrator.decide_validate_loop(verdict)
        assert result == "stop"

    def test_should_continue_false_stop(self, orchestrator):
        verdict = self._make_verdict(
            "CONDITIONAL",
            weighted_score=3.2,
            should_continue=False,
            should_continue_reason="No progress",
        )
        result = orchestrator.decide_validate_loop(verdict)
        assert result == "stop"

    def test_no_fixable_stop(self, orchestrator):
        verdict = self._make_verdict(
            "CONDITIONAL",
            weighted_score=3.2,
            has_fixable=False,
        )
        result = orchestrator.decide_validate_loop(verdict)
        assert result == "stop"

    def test_fixable_enters_fix_loop(self, orchestrator):
        orchestrator.state.phase = PipelinePhase.VALIDATING
        verdict = self._make_verdict(
            "CONDITIONAL",
            weighted_score=3.2,
            has_fixable=True,
            should_continue=True,
        )
        result = orchestrator.decide_validate_loop(verdict)
        assert result == "fix"
        assert orchestrator.state.phase == PipelinePhase.FIX_LOOP
        assert orchestrator.state.round_count == 1

    def test_fix_increments_round(self, orchestrator):
        orchestrator.state.phase = PipelinePhase.VALIDATING
        orchestrator.state.round_count = 2
        verdict = self._make_verdict(
            "CONDITIONAL",
            round=3,
            weighted_score=3.2,
            has_fixable=True,
            should_continue=True,
        )
        result = orchestrator.decide_validate_loop(verdict)
        assert result == "fix"
        assert orchestrator.state.round_count == 3


# ============================================================================
# Phase 5: Package
# ============================================================================

class TestPreparePackageSpawn:
    def test_returns_spawn_params(self, orchestrator, sample_plan):
        orchestrator.state.phase = PipelinePhase.VALIDATING
        params = orchestrator.prepare_package_spawn(sample_plan)
        assert params["runtime"] == "subagent"
        assert "deliver_package" in params["label"]

    def test_state_transitions_to_packaging(self, orchestrator, sample_plan):
        orchestrator.state.phase = PipelinePhase.VALIDATING
        orchestrator.prepare_package_spawn(sample_plan)
        assert orchestrator.state.phase == PipelinePhase.PACKAGING


# ============================================================================
# Worker Failure Recovery
# ============================================================================

class TestDiagnosisSpawn:
    def test_returns_spawn_params(self, orchestrator):
        error = WorkerError(
            task_id="T-001",
            error_type="timeout",
            message="Worker timed out after 300s",
        )
        task = TaskNode(task_id="T-001", title="Test task", scenario_type="code")
        params = orchestrator.prepare_diagnosis_spawn(error, task)
        assert params["runtime"] == "subagent"
        assert "deliver_diagnosis_WP-001_T-001" in params["label"]
        # Bootstrap pattern: task is a reference, content is in the bootstrap file
        import re
        bootstrap_match = re.search(r'`read` 工具读取: `([^`]+)`', params["task"])
        assert bootstrap_match, "Expected bootstrap reference in task"
        bootstrap_content = Path(bootstrap_match.group(1)).read_text(encoding='utf-8')
        assert "timeout" in bootstrap_content


class TestVerifyDiagnosisOutput:
    def test_valid_diagnosis(self, orchestrator):
        data = {
            "task_id": "T-001",
            "diagnosis": "Model capacity issue",
            "recovery_action": "switch_model",
            "specific_changes": "Use gpt-4o instead",
            "confidence": 0.8,
            "suggested_model": "gpt-4o",
        }
        passed, msg, action = orchestrator.verify_diagnosis_output(data)
        assert passed is True
        assert action is not None
        assert action.recovery_action == RecoveryStrategy.SWITCH_MODEL

    def test_invalid_diagnosis(self, orchestrator):
        data = {"task_id": "T-001", "recovery_action": "invalid_action"}
        passed, msg, action = orchestrator.verify_diagnosis_output(data)
        assert passed is False
        assert action is None


class TestShouldRetryWorker:
    def test_below_max(self, orchestrator):
        assert orchestrator.should_retry_worker("T-001", 1) is True
        assert orchestrator.should_retry_worker("T-001", 2) is True

    def test_at_max(self, orchestrator):
        assert orchestrator.should_retry_worker("T-001", MAX_WORKER_RECOVERY_ATTEMPTS) is False

    def test_above_max(self, orchestrator):
        assert orchestrator.should_retry_worker("T-001", 5) is False


class TestMarkWorkerFailed:
    def test_marks_failed(self, orchestrator):
        orchestrator.state.running_tasks = ["T-001"]
        orchestrator.mark_worker_failed("T-001", "Unrecoverable error")
        assert "T-001" in orchestrator.state.failed_tasks
        assert "T-001" not in orchestrator.state.running_tasks


# ============================================================================
# State Query
# ============================================================================

class TestPipelineSummary:
    def test_summary_structure(self, orchestrator):
        summary = orchestrator.get_pipeline_summary()
        assert summary["wp_id"] == "WP-001"
        assert summary["phase"] == "INIT"
        assert summary["is_terminal"] is False
        assert "completed_tasks" in summary
        assert "failed_tasks" in summary


class TestLoadFromBlackboard:
    def test_load_execution_plan_none(self, orchestrator):
        assert orchestrator.load_execution_plan() is None

    def test_load_execution_plan(self, orchestrator, sample_plan):
        plan_path = orchestrator.stages_dir / "execution_plan.json"
        plan_path.write_text(
            json.dumps(sample_plan.model_dump(mode="json")),
            encoding="utf-8",
        )
        loaded = orchestrator.load_execution_plan()
        assert loaded is not None
        assert loaded.wp_id == "WP-001"
        assert loaded.task_count == 2

    def test_load_validation_verdict_none(self, orchestrator):
        assert orchestrator.load_validation_verdict() is None

    def test_load_validation_verdict(self, orchestrator):
        verdict_data = {
            "round": 1,
            "verdict": "PASS",
            "scores": {
                "completeness": {"score": 4, "max": 5, "weight": 0.25, "notes": ""},
            },
            "weighted_score": 4.0,
        }
        verdict_path = orchestrator.stages_dir / "validation_result.json"
        verdict_path.write_text(json.dumps(verdict_data), encoding="utf-8")
        loaded = orchestrator.load_validation_verdict()
        assert loaded is not None
        assert loaded.verdict == "PASS"


# ============================================================================
# ADR-009: Track JSON Generation
# ============================================================================

class TestGenerateTrackJson:
    """Integration tests for generate_track_json() — 3 scenarios."""

    def test_graceful_skip_when_extractor_unavailable(self, orchestrator):
        """(1) import 降级：_HAS_TRACK_EXTRACTOR=False 时跳过，不报错。"""
        import domains.deliver_pro.wp_runner as orch_module

        original = orch_module._HAS_TRACK_EXTRACTOR
        try:
            orch_module._HAS_TRACK_EXTRACTOR = False
            # Should not raise, should not create file
            orchestrator.generate_track_json()
            track_path = orchestrator.stages_dir / "deliver_track.json"
            assert not track_path.exists(), "track.json should not be created when extractor unavailable"
        finally:
            orch_module._HAS_TRACK_EXTRACTOR = original

    def test_skip_when_deliverable_missing(self, orchestrator):
        """(2) DELIVERABLE.md 不存在时跳过，不报错。"""
        import domains.deliver_pro.wp_runner as orch_module

        original = orch_module._HAS_TRACK_EXTRACTOR
        try:
            orch_module._HAS_TRACK_EXTRACTOR = True
            # No DELIVERABLE.md exists
            orchestrator.generate_track_json()
            track_path = orchestrator.stages_dir / "deliver_track.json"
            assert not track_path.exists(), "track.json should not be created when DELIVERABLE.md missing"
        finally:
            orch_module._HAS_TRACK_EXTRACTOR = original

    def test_normal_path_generates_track_json(self, orchestrator):
        """(3) 正常路径：合法 MD → 生成 track.json。"""
        import domains.deliver_pro.wp_runner as orch_module

        original = orch_module._HAS_TRACK_EXTRACTOR
        try:
            orch_module._HAS_TRACK_EXTRACTOR = True

            # Create a valid DELIVERABLE.md
            deliverable_dir = orchestrator.stages_dir / "final_deliverable"
            deliverable_dir.mkdir(parents=True, exist_ok=True)
            valid_md = """---
domain: deliver_pro
version: "1.0.0"
session: deliver_test
upstream: ship_001
created: "2026-07-11T20:30:00Z"
---

# Deliver Final: Test Project

## meta_info

| 字段 | 值 |
|------|-----|
| deliverable_version | 1.0.0 |
| total_files | 5 |
| total_size_kb | 100 |
| format | code_bundle |

## deliverables

| 交付物 | 类型 | 来源 WP | 路径 |
|--------|------|---------|------|
| API Code | TypeScript | WP-001 | src/api/ |
| Frontend | Vue | WP-002 | src/ui/ |

## execution_guide

1. Install dependencies
2. Run database migration
3. Start API server
4. Deploy frontend

## acceptance_summary

| REQ-ID | 验收标准 | 验证方法 |
|--------|----------|----------|
| REQ-001 | API responds | curl test |
| REQ-002 | UI loads | browser test |

## gate_decisions

> **Gate 结果语义**: PASS=*** CONDITIONAL=needs verification, FAIL=blocked

| check_layer | result | reason |
|--------|------|------|
| L1 (完整性) | PASS | All WP have deliverables |
| L2 (LLM Judge) | PASS (90/100) | Complete and clear |
| L3 (合并) | PASS | Delivery complete |
"""
            (deliverable_dir / "DELIVERABLE.md").write_text(valid_md, encoding="utf-8")

            # Execute
            orchestrator.generate_track_json()

            # Verify track.json was created
            track_path = orchestrator.stages_dir / "deliver_track.json"
            assert track_path.exists(), "track.json should be created"

            # Verify content
            track_data = json.loads(track_path.read_text(encoding="utf-8"))
            assert track_data["schema_version"] == "3.1.0"
            assert track_data["domain"] == "deliver_pro"
            assert "REQ-001" in track_data["metrics"]["req_ids"]
            assert "REQ-002" in track_data["metrics"]["req_ids"]
            assert track_data["metrics"]["req_count"] == 2
            assert len(track_data["gate_summary"]) > 0
            assert len(track_data["anchors"]) > 0

        finally:
            orch_module._HAS_TRACK_EXTRACTOR = original
