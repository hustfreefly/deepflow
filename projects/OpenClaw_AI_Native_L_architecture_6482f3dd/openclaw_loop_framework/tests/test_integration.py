"""End-to-end integration test for the three-layer loop architecture."""

from __future__ import annotations

from datetime import datetime, timedelta

from components.blackboard import Blackboard
from components.dag_scheduler import DAGDecomposer, TopologicalValidator
from components.dream_loop import DreamLoopValidator, IdleState
from components.llm_scheduler import ModelRouter, Priority, PriorityRequest, RequestPriorityQueue, TaskComplexity
from components.meta_loop import Blueprint, SLAConstraints, Zone2Metrics, Zone2Tuner
from components.quality_harness import InputGate


def test_task_loop_flow() -> None:
    """Verify Task Loop: input gate → model routing → DAG decomposition → validation."""
    user_request = {
        "task_id": "e2e-001",
        "action_type": "build_api",
        "goal": "Build REST API with auth",
    }

    # Input gate validation
    gate = InputGate()
    result = gate.check(user_request)
    assert result.accepted, "Valid request should pass input gate"

    # Model routing
    router = ModelRouter()
    decision = router.route(TaskComplexity.COMPLEX)
    assert decision.model in {"opus", "gpt-4"}, f"Complex task should route to premium, got {decision.model}"

    # DAG decomposition
    decomposer = DAGDecomposer()
    result = decomposer.decompose(user_request["goal"])
    assert len(result.plan.nodes) >= 3, "Should have at least 3 nodes"

    # Topological validation
    validator = TopologicalValidator()
    validation = validator.validate(result.plan)
    assert validation.is_valid, "DAG should be valid"

    # Priority queue scheduling
    queue = RequestPriorityQueue()
    queue.put(PriorityRequest("low-1", {}, Priority.LOW))
    queue.put(PriorityRequest("high-1", {}, Priority.HIGH))
    queue.put(PriorityRequest("medium-1", {}, Priority.MEDIUM))
    first = queue.get()
    assert first.request_id == "high-1", "High priority should be first"

    # Blackboard state management
    bb = Blackboard("/tmp/e2e_bb")
    bb.write_state({"step": 1, "data": {"value": "test"}})
    bb.full_checkpoint()
    state = bb.read_state()
    assert state["step"] == 1, "State should be preserved"


def test_dream_loop_idle_detection() -> None:
    """Verify Dream Loop idle detection triggers correctly."""
    dream_validator = DreamLoopValidator()
    idle_state = IdleState(
        rounds_without_new_nodes=3,
        last_activity_at=datetime.now() - timedelta(minutes=15),
        active_subagents=0,
    )
    should_trigger = dream_validator.trigger_reflection_if_idle(idle_state, datetime.now())
    assert should_trigger is True, "Should trigger reflection when all conditions met"

    # Should NOT trigger with active subagents
    idle_state_with_active = IdleState(
        rounds_without_new_nodes=3,
        last_activity_at=datetime.now() - timedelta(minutes=20),
        active_subagents=1,
    )
    should_not_trigger = dream_validator.trigger_reflection_if_idle(
        idle_state_with_active, datetime.now()
    )
    assert should_not_trigger is False, "Should not trigger with active subagents"


def test_meta_loop_tuning() -> None:
    """Verify Meta Loop Zone 2 tuning responds to system metrics."""
    tuner = Zone2Tuner()
    blueprint = Blueprint(SLAConstraints(token_budget=10000))

    # Test: Three consecutive low success rates raises quality gate threshold
    history = [
        Zone2Metrics(
            token_consumed=5000, success_rate=0.65, model="opus", quality_gate_threshold=0.6
        ),
        Zone2Metrics(
            token_consumed=5200, success_rate=0.68, model="opus", quality_gate_threshold=0.6
        ),
        Zone2Metrics(
            token_consumed=4800, success_rate=0.66, model="opus", quality_gate_threshold=0.6
        ),
    ]
    plan = tuner.analyze(blueprint, history)
    assert plan.triggered, "Should trigger tuning for low success rates"
    assert any(
        action.parameter == "quality_gate_threshold" and action.after == 0.7
        for action in plan.actions
    ), "Should raise quality gate threshold to 0.7"

    # Test: Max concurrent agents reduces parallelism
    history = [
        Zone2Metrics(
            token_consumed=3000,
            success_rate=0.9,
            model="opus",
            concurrent_agents=6,
            parallelism=6,
        ),
    ]
    plan = tuner.analyze(blueprint, history)
    assert plan.triggered, "Should trigger tuning for max concurrent agents"
    assert any(
        action.parameter == "parallelism" and action.after == 5 for action in plan.actions
    ), "Should reduce parallelism to 5"


def test_cross_component_imports() -> None:
    """Verify all components can be imported and initialized."""
    from components.circuit_breaker import SignalDetector
    from components.dream_loop import DreamLoopValidator
    from components.meta_loop import Zone2Tuner
    from components.quality_harness import InputGate

    # Just verify initialization doesn't raise
    SignalDetector()
    DreamLoopValidator()
    Zone2Tuner()
    InputGate()
    
    # Verify other components can be imported
    from components.context_compressor import ContextCompressor
    from components.decision_benchmark import BenchmarkRunner
    from components.quality_harness import OutputGate, ToolGate
    
    # Verify classes exist
    assert ContextCompressor is not None
    assert BenchmarkRunner is not None
    assert OutputGate is not None
    assert ToolGate is not None
