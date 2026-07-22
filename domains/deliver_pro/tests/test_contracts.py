"""Tests for Deliver Pro Pydantic Contracts (18 models)."""

import pytest
from pydantic import ValidationError

from domains.deliver_pro.contracts import (
    AcceptanceCriterion,
    ComponentStatus,
    ConcurrencyPlan,
    DeliveryManifest,
    DeliveryStatus,
    ExecutionPlan,
    FixDirective,
    IntegrationReport,
    PipelinePhase,
    PipelineState,
    RecoveryAction,
    RecoveryStrategy,
    ScoreDimension,
    TaskNode,
    ValidationVerdict,
    Wave,
    WorkerError,
    WorkerOutputMeta,
    WorkerResult,
    WorkerTask,
    WorkPackage,
)


# ============================================================================
# WorkPackage & AcceptanceCriterion
# ============================================================================

class TestAcceptanceCriterion:
    def test_basic_creation(self):
        ac = AcceptanceCriterion(id="AC-001", description="Must work")
        assert ac.id == "AC-001"
        assert ac.description == "Must work"
        assert ac.priority == "must"

    def test_custom_priority(self):
        ac = AcceptanceCriterion(id="AC-002", description="Nice to have", priority="should")
        assert ac.priority == "should"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            AcceptanceCriterion(id="AC-001")  # missing description


class TestWorkPackage:
    def test_basic_creation(self):
        wp = WorkPackage(wp_id="WP-001", title="Test", objective="Test obj")
        assert wp.wp_id == "WP-001"
        assert wp.scenario == "code"
        assert wp.acceptance_criteria == []
        assert wp.constraints == {}
        assert wp.dependencies == []
        assert wp.interface_contract is None
        assert wp.context == {}

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            WorkPackage(wp_id="WP-001")  # missing title, objective

    def test_must_criteria_property(self):
        wp = WorkPackage(
            wp_id="WP-001",
            title="Test",
            objective="Test obj",
            acceptance_criteria=[
                AcceptanceCriterion(id="AC-001", description="Must 1", priority="must"),
                AcceptanceCriterion(id="AC-002", description="Should 1", priority="should"),
                AcceptanceCriterion(id="AC-003", description="Must 2", priority="must"),
            ],
        )
        assert len(wp.must_criteria) == 2
        assert wp.must_criteria[0].id == "AC-001"
        assert wp.must_criteria[1].id == "AC-003"

    def test_total_ac_count(self):
        wp = WorkPackage(
            wp_id="WP-001",
            title="Test",
            objective="Test obj",
            acceptance_criteria=[
                AcceptanceCriterion(id="AC-001", description="A", priority="must"),
            ],
        )
        assert wp.total_ac_count == 1

    def test_total_ac_count_empty(self):
        wp = WorkPackage(wp_id="WP-001", title="Test", objective="Test obj")
        assert wp.total_ac_count == 0

    def test_full_creation(self):
        wp = WorkPackage(
            wp_id="WP-001",
            title="Test",
            objective="Test obj",
            scenario="report",
            acceptance_criteria=[],
            constraints={"tech_stack": "python"},
            dependencies=["WP-000"],
            interface_contract="def foo(): ...",
            context={"summary": "test"},
        )
        assert wp.scenario == "report"
        assert wp.constraints["tech_stack"] == "python"
        assert wp.dependencies == ["WP-000"]


# ============================================================================
# ExecutionPlan, TaskNode, ConcurrencyPlan, Wave
# ============================================================================

class TestTaskNode:
    def test_basic_creation(self):
        t = TaskNode(task_id="T-001", title="Task 1")
        assert t.task_id == "T-001"
        assert t.depends_on == []
        assert t.estimated_complexity == "medium"
        assert t.acceptance_criteria == []
        assert t.expected_outputs == []
        assert t.forced_actions == []
        assert t.suggested_model is None

    def test_with_dependencies(self):
        t = TaskNode(task_id="T-002", title="Task 2", depends_on=["T-001"])
        assert t.depends_on == ["T-001"]


class TestWave:
    def test_basic_creation(self):
        w = Wave(wave=1, task_ids=["T-001", "T-002"])
        assert w.wave == 1
        assert w.task_ids == ["T-001", "T-002"]

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            Wave(wave=1)  # missing task_ids


class TestConcurrencyPlan:
    def test_defaults(self):
        cp = ConcurrencyPlan()
        assert cp.suggested_parallelism == 3
        assert cp.safety_cap == 8
        assert cp.waves == []

    def test_constraints(self):
        with pytest.raises(ValidationError):
            ConcurrencyPlan(suggested_parallelism=0)  # ge=1
        with pytest.raises(ValidationError):
            ConcurrencyPlan(suggested_parallelism=11)  # le=10
        with pytest.raises(ValidationError):
            ConcurrencyPlan(safety_cap=0)
        with pytest.raises(ValidationError):
            ConcurrencyPlan(safety_cap=21)


class TestExecutionPlan:
    def _make_plan(self, tasks=None, **kwargs):
        defaults = dict(
            wp_id="WP-001",
            scenario="code",
            task_graph=tasks if tasks is not None else [TaskNode(task_id="T-001", title="Task 1")],
        )
        defaults.update(kwargs)
        return ExecutionPlan(**defaults)

    def test_basic_creation(self):
        plan = self._make_plan()
        assert plan.wp_id == "WP-001"
        assert plan.scenario == "code"
        assert plan.schema_version == "1.0.0"
        assert plan.task_count == 1

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ExecutionPlan(scenario="code", task_graph=[])  # missing wp_id

    def test_root_tasks(self):
        tasks = [
            TaskNode(task_id="T-001", title="Root 1"),
            TaskNode(task_id="T-002", title="Root 2"),
            TaskNode(task_id="T-003", title="Child", depends_on=["T-001"]),
        ]
        plan = self._make_plan(tasks=tasks)
        roots = plan.root_tasks
        assert len(roots) == 2
        root_ids = {r.task_id for r in roots}
        assert root_ids == {"T-001", "T-002"}

    def test_get_task(self):
        tasks = [
            TaskNode(task_id="T-001", title="Task 1"),
            TaskNode(task_id="T-002", title="Task 2"),
        ]
        plan = self._make_plan(tasks=tasks)
        assert plan.get_task("T-001") is not None
        assert plan.get_task("T-001").title == "Task 1"
        assert plan.get_task("T-999") is None

    def test_get_ready_tasks(self):
        tasks = [
            TaskNode(task_id="T-001", title="Root"),
            TaskNode(task_id="T-002", title="Child", depends_on=["T-001"]),
            TaskNode(task_id="T-003", title="Grandchild", depends_on=["T-002"]),
        ]
        plan = self._make_plan(tasks=tasks)

        ready = plan.get_ready_tasks(set())
        assert len(ready) == 1
        assert ready[0].task_id == "T-001"

        ready = plan.get_ready_tasks({"T-001"})
        assert len(ready) == 1
        assert ready[0].task_id == "T-002"

        ready = plan.get_ready_tasks({"T-001", "T-002"})
        assert len(ready) == 1
        assert ready[0].task_id == "T-003"

        ready = plan.get_ready_tasks({"T-001", "T-002", "T-003"})
        assert len(ready) == 0

    def test_dag_cycle_detection(self):
        tasks = [
            TaskNode(task_id="T-001", title="A", depends_on=["T-002"]),
            TaskNode(task_id="T-002", title="B", depends_on=["T-001"]),
        ]
        with pytest.raises(ValidationError, match="cycle"):
            self._make_plan(tasks=tasks)

    def test_dag_self_cycle(self):
        tasks = [
            TaskNode(task_id="T-001", title="A", depends_on=["T-001"]),
        ]
        with pytest.raises(ValidationError, match="cycle"):
            self._make_plan(tasks=tasks)

    def test_dag_unknown_dependency(self):
        tasks = [
            TaskNode(task_id="T-001", title="A", depends_on=["T-999"]),
        ]
        with pytest.raises(ValidationError, match="unknown task"):
            self._make_plan(tasks=tasks)

    def test_valid_dag(self):
        tasks = [
            TaskNode(task_id="T-001", title="A"),
            TaskNode(task_id="T-002", title="B", depends_on=["T-001"]),
            TaskNode(task_id="T-003", title="C", depends_on=["T-001"]),
            TaskNode(task_id="T-004", title="D", depends_on=["T-002", "T-003"]),
        ]
        plan = self._make_plan(tasks=tasks)
        assert plan.task_count == 4

    def test_empty_task_graph(self):
        plan = self._make_plan(tasks=[])
        assert plan.task_count == 0
        assert plan.root_tasks == []

    def test_quality_gates_default(self):
        plan = self._make_plan()
        assert "code" in plan.quality_gates
        assert "report" in plan.quality_gates


# ============================================================================
# PipelineState & PipelinePhase
# ============================================================================

class TestPipelinePhase:
    def test_enum_values(self):
        assert PipelinePhase.INIT.value == "INIT"
        assert PipelinePhase.COMPLETED.value == "COMPLETED"
        assert PipelinePhase.FAILED.value == "FAILED"

    def test_string_enum(self):
        assert PipelinePhase.INIT == "INIT"


class TestPipelineState:
    def test_basic_creation(self):
        state = PipelineState(wp_id="WP-001")
        assert state.wp_id == "WP-001"
        assert state.phase == PipelinePhase.INIT
        assert state.completed_tasks == []
        assert state.failed_tasks == []
        assert state.round_count == 0
        assert state.max_rounds == 5
        assert state.validation_score is None
        assert state.last_verdict is None
        assert state.error is None
        assert state.completed_at is None

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            PipelineState()  # missing wp_id

    def test_valid_transition(self):
        state = PipelineState(wp_id="WP-001")
        state.transition_to(PipelinePhase.ANALYZING)
        assert state.phase == PipelinePhase.ANALYZING

    def test_invalid_transition(self):
        """V3: transition_to 降级为日志语义，非法转换不再 raise（只记 warning）。"""
        state = PipelineState(wp_id="WP-001")
        # V3: 不再 raise，phase 决策由 phase_deriver 从文件系统推导
        state.transition_to(PipelinePhase.GENERATING)  # INIT → GENERATING 非标准但不 raise
        assert state.phase == PipelinePhase.GENERATING

    def test_transition_to_completed_sets_timestamp(self):
        state = PipelineState(wp_id="WP-001")
        state.transition_to(PipelinePhase.ANALYZING)
        state.transition_to(PipelinePhase.GENERATING)
        state.transition_to(PipelinePhase.INTEGRATING)
        state.transition_to(PipelinePhase.VALIDATING)
        state.transition_to(PipelinePhase.PACKAGING)
        state.transition_to(PipelinePhase.COMPLETED)
        assert state.completed_at is not None

    def test_completed_is_terminal(self):
        assert PipelineState(wp_id="WP-001", phase=PipelinePhase.COMPLETED).is_terminal
        assert PipelineState(wp_id="WP-001", phase=PipelinePhase.FAILED).is_terminal
        assert not PipelineState(wp_id="WP-001", phase=PipelinePhase.INIT).is_terminal

    def test_can_continue_validate(self):
        state = PipelineState(
            wp_id="WP-001",
            phase=PipelinePhase.VALIDATING,
            round_count=2,
            max_rounds=5,
        )
        assert state.can_continue_validate

        state2 = PipelineState(
            wp_id="WP-001",
            phase=PipelinePhase.VALIDATING,
            round_count=5,
            max_rounds=5,
        )
        assert not state2.can_continue_validate

        state3 = PipelineState(
            wp_id="WP-001",
            phase=PipelinePhase.GENERATING,
            round_count=2,
            max_rounds=5,
        )
        assert not state3.can_continue_validate

    def test_mark_task_completed(self):
        state = PipelineState(
            wp_id="WP-001",
            pending_tasks=["T-001", "T-002"],
            running_tasks=["T-001"],
        )
        state.mark_task_completed("T-001")
        assert "T-001" in state.completed_tasks
        assert "T-001" not in state.pending_tasks
        assert "T-001" not in state.running_tasks
        assert "T-002" in state.pending_tasks

    def test_mark_task_completed_idempotent(self):
        state = PipelineState(wp_id="WP-001")
        state.mark_task_completed("T-001")
        state.mark_task_completed("T-001")
        assert state.completed_tasks.count("T-001") == 1

    def test_mark_task_failed(self):
        state = PipelineState(
            wp_id="WP-001",
            pending_tasks=["T-001"],
            running_tasks=["T-001"],
        )
        state.mark_task_failed("T-001")
        assert "T-001" in state.failed_tasks
        assert "T-001" not in state.pending_tasks
        assert "T-001" not in state.running_tasks

    def test_failed_transition_to_init(self):
        state = PipelineState(wp_id="WP-001", phase=PipelinePhase.FAILED)
        state.transition_to(PipelinePhase.INIT)
        assert state.phase == PipelinePhase.INIT

    def test_completed_is_terminal_no_transitions(self):
        """V3: 终态转换同样不 raise（日志语义），phase 字段被记录。"""
        state = PipelineState(wp_id="WP-001", phase=PipelinePhase.COMPLETED)
        state.transition_to(PipelinePhase.INIT)
        assert state.phase == PipelinePhase.INIT


# ============================================================================
# ValidationVerdict, ScoreDimension, FixDirective
# ============================================================================

class TestScoreDimension:
    def test_basic_creation(self):
        sd = ScoreDimension(score=4, weight=0.25)
        assert sd.score == 4
        assert sd.max == 5
        assert sd.weight == 0.25

    def test_constraints(self):
        with pytest.raises(ValidationError):
            ScoreDimension(score=0, weight=0.25)  # ge=1
        with pytest.raises(ValidationError):
            ScoreDimension(score=6, weight=0.25)  # le=5
        with pytest.raises(ValidationError):
            ScoreDimension(score=3, weight=-0.1)  # ge=0.0
        with pytest.raises(ValidationError):
            ScoreDimension(score=3, weight=1.1)  # le=1.0


class TestFixDirective:
    def test_basic_creation(self):
        fd = FixDirective(
            target="T-001",
            issue="Bug found",
            fix_instruction="Fix the bug",
        )
        assert fd.target == "T-001"
        assert fd.priority == "medium"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            FixDirective(target="T-001")  # missing issue, fix_instruction


class TestValidationVerdict:
    def _make_scores(self, **overrides):
        defaults = {
            "completeness": ScoreDimension(score=4, weight=0.25),
            "correctness": ScoreDimension(score=4, weight=0.25),
            "credibility": ScoreDimension(score=4, weight=0.20),
            "actionability": ScoreDimension(score=4, weight=0.15),
            "consistency": ScoreDimension(score=3, weight=0.10),
            "professionalism": ScoreDimension(score=3, weight=0.05),
        }
        defaults.update(overrides)
        return defaults

    def test_basic_creation(self):
        v = ValidationVerdict(
            round=1,
            verdict="PASS",
            scores=self._make_scores(),
            weighted_score=3.8,
        )
        assert v.round == 1
        assert v.verdict == "PASS"
        assert v.is_pass
        assert not v.is_fail

    def test_invalid_verdict(self):
        with pytest.raises(ValidationError, match="verdict"):
            ValidationVerdict(
                round=1,
                verdict="MAYBE",
                scores={},
                weighted_score=3.0,
            )

    def test_is_fail(self):
        v = ValidationVerdict(
            round=1,
            verdict="FAIL",
            scores=self._make_scores(),
            weighted_score=1.5,
        )
        assert v.is_fail
        assert not v.is_pass

    def test_compute_verdict_pass(self):
        scores = self._make_scores()
        assert ValidationVerdict.compute_verdict(3.5, scores) == "PASS"
        assert ValidationVerdict.compute_verdict(4.0, scores) == "PASS"

    def test_compute_verdict_conditional(self):
        scores = {
            "a": ScoreDimension(score=3, weight=0.5),
            "b": ScoreDimension(score=2, weight=0.5),
        }
        assert ValidationVerdict.compute_verdict(3.0, scores) == "CONDITIONAL"

    def test_compute_verdict_fail(self):
        scores = {
            "a": ScoreDimension(score=1, weight=0.5),
            "b": ScoreDimension(score=1, weight=0.5),
        }
        assert ValidationVerdict.compute_verdict(1.0, scores) == "FAIL"

    def test_compute_verdict_empty_scores(self):
        assert ValidationVerdict.compute_verdict(3.0, {}) == "FAIL"

    def test_compute_weighted_score(self):
        scores = {
            "a": ScoreDimension(score=4, weight=0.5),
            "b": ScoreDimension(score=2, weight=0.5),
        }
        result = ValidationVerdict.compute_weighted_score(scores)
        assert abs(result - 3.0) < 0.01

    def test_compute_weighted_score_empty(self):
        assert ValidationVerdict.compute_weighted_score({}) == 0.0

    def test_compute_weighted_score_zero_weights(self):
        scores = {
            "a": ScoreDimension(score=4, weight=0.0),
        }
        assert ValidationVerdict.compute_weighted_score(scores) == 0.0


# ============================================================================
# DeliveryManifest, ComponentStatus, DeliveryStatus
# ============================================================================

class TestDeliveryStatus:
    def test_enum_values(self):
        assert DeliveryStatus.COMPLETE.value == "COMPLETE"
        assert DeliveryStatus.PARTIAL.value == "PARTIAL"
        assert DeliveryStatus.FAILED.value == "FAILED"


class TestComponentStatus:
    def test_basic_creation(self):
        cs = ComponentStatus(task_id="T-001", title="Task", status="PASS")
        assert cs.artifacts == []
        assert cs.failure_reason is None
        assert cs.user_actions == []


class TestDeliveryManifest:
    def test_basic_creation(self):
        dm = DeliveryManifest(wp_id="WP-001")
        assert dm.delivery_status == DeliveryStatus.COMPLETE
        assert dm.components == []
        assert dm.pass_count == 0
        assert dm.fail_count == 0
        assert dm.total_count == 0

    def test_counts(self):
        dm = DeliveryManifest(
            wp_id="WP-001",
            components=[
                ComponentStatus(task_id="T-001", title="A", status="PASS"),
                ComponentStatus(task_id="T-002", title="B", status="FAILED"),
                ComponentStatus(task_id="T-003", title="C", status="PASS"),
            ],
        )
        assert dm.pass_count == 2
        assert dm.fail_count == 1
        assert dm.total_count == 3

    def test_validation_summary_default(self):
        dm = DeliveryManifest(wp_id="WP-001")
        assert dm.validation_summary["rounds_run"] == 0


# ============================================================================
# IntegrationReport
# ============================================================================

class TestIntegrationReport:
    def test_basic_creation(self):
        ir = IntegrationReport(workers_integrated=3)
        assert ir.workers_integrated == 3
        assert ir.workers_failed == 0
        assert ir.consistency_checks_passed is True
        assert ir.conflicts_found == []
        assert ir.status == "READY_FOR_VALIDATE"

    def test_coverage_ratio(self):
        ir = IntegrationReport(
            workers_integrated=2,
            coverage={"acceptance_criteria_total": 10, "covered": 7, "gaps": []},
        )
        assert abs(ir.coverage_ratio - 0.7) < 0.01

    def test_coverage_ratio_zero_total(self):
        ir = IntegrationReport(
            workers_integrated=0,
            coverage={"acceptance_criteria_total": 0, "covered": 0, "gaps": []},
        )
        assert ir.coverage_ratio == 0.0

    def test_coverage_ratio_default(self):
        ir = IntegrationReport(workers_integrated=0)
        assert ir.coverage_ratio == 0.0


# ============================================================================
# RecoveryAction, WorkerError, RecoveryStrategy
# ============================================================================

class TestRecoveryStrategy:
    def test_enum_values(self):
        assert RecoveryStrategy.RETRY.value == "retry"
        assert RecoveryStrategy.SKIP.value == "skip"
        assert RecoveryStrategy.SWITCH_MODEL.value == "switch_model"


class TestWorkerError:
    def test_basic_creation(self):
        we = WorkerError(
            task_id="T-001",
            error_type="timeout",
            message="Worker timed out",
        )
        assert we.context == {}
        assert we.recovery_history == []


class TestRecoveryAction:
    def test_basic_creation(self):
        ra = RecoveryAction(
            task_id="T-001",
            diagnosis="LLM diagnosis",
            recovery_action=RecoveryStrategy.RETRY,
            specific_changes="Retry the task",
        )
        assert ra.confidence == 0.5
        assert ra.should_retry is True

    def test_should_retry_skip(self):
        ra = RecoveryAction(
            task_id="T-001",
            diagnosis="Unrecoverable",
            recovery_action=RecoveryStrategy.SKIP,
            specific_changes="Skip this task",
        )
        assert ra.should_retry is False

    def test_confidence_constraints(self):
        with pytest.raises(ValidationError):
            RecoveryAction(
                task_id="T-001",
                diagnosis="test",
                recovery_action=RecoveryStrategy.RETRY,
                specific_changes="test",
                confidence=-0.1,
            )
        with pytest.raises(ValidationError):
            RecoveryAction(
                task_id="T-001",
                diagnosis="test",
                recovery_action=RecoveryStrategy.RETRY,
                specific_changes="test",
                confidence=1.1,
            )


# ============================================================================
# WorkerTask, WorkerOutputMeta, WorkerResult
# ============================================================================

class TestWorkerTask:
    def test_basic_creation(self):
        wt = WorkerTask(
            task_id="T-001",
            wp_id="WP-001",
            title="Task 1",
            scenario="code",
            prompt="Do something",
        )
        assert wt.model == "qwen3.7-plus"
        assert wt.timeout_seconds == 300
        assert wt.dependencies == []

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            WorkerTask(task_id="T-001")  # missing wp_id, title, scenario, prompt


class TestWorkerOutputMeta:
    def test_basic_creation(self):
        wom = WorkerOutputMeta(
            task_id="T-001",
            wp_id="WP-001",
            scenario="code",
            status="COMPLETE",
        )
        assert wom.outputs == []
        assert wom.interfaces == {"provides": [], "requires": []}
        assert wom.quality_self_check["acceptance_criteria_met"] is False
        assert wom.tool_calls["exec"] == 0

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            WorkerOutputMeta(task_id="T-001")  # missing wp_id, scenario, status


class TestWorkerResult:
    def test_basic_creation(self):
        wr = WorkerResult(task_id="T-001", status="COMPLETE")
        assert wr.is_success is True
        assert wr.is_failed is False
        assert wr.attempts == 1
        assert wr.error is None

    def test_failed_status(self):
        wr = WorkerResult(task_id="T-001", status="FAILED", error="Something broke")
        assert wr.is_failed is True
        assert wr.is_success is False
        assert wr.error == "Something broke"

    def test_partial_is_success(self):
        wr = WorkerResult(task_id="T-001", status="PARTIAL")
        assert wr.is_success is True
        assert wr.is_failed is False
