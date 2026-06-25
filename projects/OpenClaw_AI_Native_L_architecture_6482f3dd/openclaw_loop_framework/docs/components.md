# Component Details and Public APIs

This document describes the public APIs exported by each `components/*/__init__.py` module and references the concrete implementation files.

## LLM Scheduler

Files:

- `components/llm_scheduler/token_bucket.py`
- `components/llm_scheduler/priority_queue.py`
- `components/llm_scheduler/model_router.py`
- `components/llm_scheduler/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `TokenBucket` | dataclass | Async token bucket limiter that waits for capacity instead of dropping calls. |
| `Priority` | `IntEnum` | `HIGH`, `MEDIUM`, `LOW`; lower values are processed first. |
| `PriorityRequest` | frozen dataclass | Request envelope with `request_id`, `payload`, and `priority`. |
| `RequestPriorityQueue` | dataclass | Stable heap-backed queue with FIFO ordering inside a priority tier. |
| `TaskComplexity` | `StrEnum` | `SIMPLE`, `MEDIUM`, `COMPLEX`. |
| `RouteDecision` | frozen dataclass | Routing result: complexity, model, tier, latency. |
| `ModelRouter` | class | Deterministic complexity-to-model router. |

### Key Methods

- `await TokenBucket(rate, burst).acquire(tokens=1) -> float`
- `RequestPriorityQueue.put(request) -> None`
- `RequestPriorityQueue.get() -> PriorityRequest`
- `len(RequestPriorityQueue) -> int`
- `RequestPriorityQueue.empty -> bool`
- `ModelRouter(routes=None).route(complexity) -> RouteDecision`

### Example

```python
from components.llm_scheduler import (
    ModelRouter,
    Priority,
    PriorityRequest,
    RequestPriorityQueue,
    TaskComplexity,
)

queue = RequestPriorityQueue()
queue.put(PriorityRequest("low-1", {"goal": "cleanup"}, Priority.LOW))
queue.put(PriorityRequest("high-1", {"goal": "incident"}, Priority.HIGH))

request = queue.get()
decision = ModelRouter().route(TaskComplexity.COMPLEX)
assert request.request_id == "high-1"
assert decision.tier == "premium"
```

## Blackboard

Files:

- `components/blackboard/atomic_writer.py`
- `components/blackboard/blackboard_interface.py`
- `components/blackboard/checkpoint_manager.py`
- `components/blackboard/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `atomic_write` | function | Atomic write with sidecar process lock, temp file, fsync, and rename. |
| `Blackboard` | class | JSON state persistence and checkpoint facade. |
| `CheckpointManager` | class | Full and incremental checkpoint manager. |
| `CheckpointLevel` | `StrEnum` | `FULL` and `INCREMENTAL`. |

### Key Methods

- `atomic_write(path, data) -> None`
- `Blackboard(root).write_state(state) -> None`
- `Blackboard(root).read_state() -> dict[str, Any]`
- `Blackboard(root).full_checkpoint(state=None) -> Path`
- `Blackboard(root).incremental_checkpoint(patch) -> Path`
- `Blackboard(root).restore_checkpoint() -> dict[str, Any]`
- `CheckpointManager(root).create_full_checkpoint(state) -> Path`
- `CheckpointManager(root).create_incremental_checkpoint(patch) -> Path`
- `CheckpointManager(root).restore() -> dict[str, Any]`

### Example

```python
from components.blackboard import Blackboard

bb = Blackboard("/tmp/openclaw_state")
bb.write_state({"step": 1, "data": {"status": "running"}})
bb.full_checkpoint()
bb.incremental_checkpoint({"data": {"status": "done"}})

restored = bb.restore_checkpoint()
assert restored["data"]["status"] == "done"
```

## Circuit Breaker

Files:

- `components/circuit_breaker/adaptive_threshold.py`
- `components/circuit_breaker/signal_detector.py`
- `components/circuit_breaker/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `Complexity` | `StrEnum` | `SIMPLE`, `MEDIUM`, `COMPLEX` thresholds for circuit-breaker checks. |
| `AdaptiveThreshold` | frozen dataclass | Resolves repeat thresholds by complexity. |
| `SignalType` | `StrEnum` | `PROGRESS_AWARE_REPEAT`, `TOKEN_ANOMALY`, `HEARTBEAT_TIMEOUT`, `NO_PROGRESS`. |
| `WorkerEvent` | frozen dataclass | Worker action sample with tokens, timestamp, and progress marker. |
| `WorkerSignal` | frozen dataclass | Detected circuit-breaker signal. |
| `SignalDetector` | class | Multi-dimensional dead-loop detector. |

### Key Methods

- `AdaptiveThreshold().repeat_threshold(complexity) -> int`
- `SignalDetector().detect(events, complexity=..., now=None) -> list[WorkerSignal]`
- `detect_progress_aware_repeat(events, complexity=...) -> WorkerSignal | None`
- `detect_token_anomaly(events) -> WorkerSignal | None`
- `detect_no_progress(events, complexity=...) -> WorkerSignal | None`
- `detect_heartbeat_timeout(events, now=None) -> WorkerSignal | None`

### Example

```python
from datetime import datetime, timedelta

from components.circuit_breaker import SignalDetector, WorkerEvent

events = [
    WorkerEvent("worker-1", "retry", 100, datetime.now() - timedelta(minutes=10), "same"),
    WorkerEvent("worker-1", "retry", 180, datetime.now() - timedelta(minutes=5), "same"),
    WorkerEvent("worker-1", "retry", 300, datetime.now(), "same"),
]

signals = SignalDetector(token_growth_streak_threshold=2).detect(events, complexity="simple")
```

## Quality Harness

Files:

- `components/quality_harness/input_gate.py`
- `components/quality_harness/tool_gate.py`
- `components/quality_harness/output_gate.py`
- `components/quality_harness/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `InputGateResult` | frozen dataclass | Admission result with `accepted` and `missing_fields`. |
| `InputGate` | class | Validates request fields before downstream execution. |
| `ToolGateResult` | frozen dataclass | Tool validation result with retry action and deviation log. |
| `ToolGate` | class | Validates tool results against required fields. |
| `Evaluation` | frozen dataclass | Evaluator score and rationale. |
| `OutputGateResult` | frozen dataclass | Final output decision: accept, retry, or human review. |
| `OutputGate` | class | Evaluator-Optimizer quality gate. |

### Key Methods

- `InputGate(required_fields=None).check(request) -> InputGateResult`
- `InputGateResult.should_forward -> bool`
- `ToolGate().check(tool_name, result, expected_schema) -> ToolGateResult`
- `ToolGateResult.should_retry -> bool`
- `OutputGate(evaluator, threshold=0.6, max_retries=3).check(worker_output, retry_count=0) -> OutputGateResult`
- `OutputGateResult.requires_retry -> bool`
- `OutputGateResult.escalate_to_human -> bool`

### Example

```python
from components.quality_harness import Evaluation, InputGate, OutputGate, ToolGate

request_result = InputGate().check({"task_id": "1", "action_type": "build"})
assert request_result.should_forward

tool_result = ToolGate().check(
    "filesystem",
    {"path": "docs/architecture.md"},
    {"required": ["path", "content"]},
)
assert tool_result.should_retry

gate = OutputGate(lambda output: Evaluation(score=0.82, rationale="complete"))
assert gate.check({"answer": "done"}).accepted
```

## DAG Scheduler

Files:

- `components/dag_scheduler/dag_decomposer.py`
- `components/dag_scheduler/topo_validator.py`
- `components/dag_scheduler/replanner.py`
- `components/dag_scheduler/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `DAGNode` | frozen dataclass | Executable unit with dependencies, status, and optional result. |
| `DAGPlan` | frozen dataclass | Goal plus nodes and metadata. |
| `DecompositionResult` | frozen dataclass | Plan, route, quality score, elapsed time. |
| `DAGDecomposer` | class | Creates DAG plans with optional LLM scheduler injection. |
| `TopologicalValidation` | frozen dataclass | Validation result with ordered IDs and errors. |
| `TopologicalValidator` | class | Checks missing dependencies, duplicates, and cycles. |
| `ReplanResult` | frozen dataclass | Replanned DAG, preserved results, validation, elapsed time. |
| `DAGReplanner` | class | Replaces failed nodes and downstream dependents while preserving successful results. |

### Key Methods

- `DAGPlan.node_map() -> dict[str, DAGNode]`
- `DAGDecomposer(llm_scheduler=None).decompose(goal) -> DecompositionResult`
- `DAGDecomposer().decompose_subgoal(goal, failed_node, inherited_dependencies) -> DAGPlan`
- `DAGDecomposer().route_model(goal) -> str`
- `DAGDecomposer().score_quality(plan) -> float`
- `TopologicalValidator().validate(plan) -> TopologicalValidation`
- `DAGReplanner().replan(plan, failed_node_id, blackboard_checkpoint) -> ReplanResult`

### Example

```python
from components.dag_scheduler import DAGDecomposer, DAGReplanner, TopologicalValidator

decomposition = DAGDecomposer().decompose("Build REST API with auth")
validation = TopologicalValidator().validate(decomposition.plan)
assert validation.is_valid

replanned = DAGReplanner().replan(
    decomposition.plan,
    failed_node_id="api",
    blackboard_checkpoint={"auth": {"status": "ok"}},
)
assert replanned.validation.is_valid
```

## Context Compressor

Files:

- `components/context_compressor/summarizer.py`
- `components/context_compressor/instruction_reinject.py`
- `components/context_compressor/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `ConversationTurn` | frozen dataclass | One active-context turn. |
| `CompressionResult` | frozen dataclass | Compression output and token metrics. |
| `BlackboardArchive` | class | Append-only archive of original detailed turns. |
| `HierarchicalSummarizer` | class | Produces summaries with overview, decisions, and state. |
| `ContextCompressor` | class | Applies compression on configured cadence. |
| `CoreInstructionSet` | frozen dataclass | Goal, Zone 0 safety rules, and key constraints. |
| `InstructionReinjector` | class | Reinjects core instructions on configured cadence. |

### Key Methods

- `BlackboardArchive().append(key, turns) -> None`
- `HierarchicalSummarizer().summarize(turns) -> list[dict[str, object]]`
- `ContextCompressor(blueprint).should_compress(iteration) -> bool`
- `ContextCompressor(blueprint).compress(turns, iteration, active_context_tail=None) -> CompressionResult`
- `ContextCompressor.count_tokens(texts) -> int`
- `InstructionReinjector(blueprint).should_reinject(iteration) -> bool`
- `InstructionReinjector(blueprint).build_payload(instructions) -> str`
- `InstructionReinjector(blueprint).reinject(active_context, iteration, instructions) -> list[dict[str, str]]`

### Example

```python
from components.context_compressor import (
    ContextCompressor,
    ConversationTurn,
    CoreInstructionSet,
    InstructionReinjector,
)

blueprint = {"sla_constraints": {"context_compression_every_rounds": 2}}
turns = [
    ConversationTurn("user", "decision: use DAG validation", 1),
    ConversationTurn("assistant", "state: DAG is valid", 2),
]

result = ContextCompressor(blueprint).compress(turns, iteration=2)
assert result.compressed

instructions = CoreInstructionSet("Ship docs", ["No destructive writes"], ["Use code refs"])
context = InstructionReinjector({"sla_constraints": {"instruction_reinject_every_rounds": 2}}).reinject(
    result.compressed_context,
    iteration=2,
    instructions=instructions,
)
```

## Dream Loop

Files:

- `components/dream_loop/l1_trajectory.py`
- `components/dream_loop/l1_5_cross_validate.py`
- `components/dream_loop/l2_effect_tracking.py`
- `components/dream_loop/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `TrajectoryRecord` | frozen dataclass | Failed or successful execution trace. |
| `L1ValidationResult` | frozen dataclass | L1 lesson validation result. |
| `TrajectoryValidator` | class | Verifies lessons against failed trajectory evidence. |
| `LessonVerifier` | protocol | Independent verifier contract with `name` and `validate`. |
| `FunctionVerifier` | frozen dataclass | Function-backed verifier adapter. |
| `CrossValidationResult` | frozen dataclass | L1.5 consensus result. |
| `CrossValidator` | class | Requires verifier consensus. |
| `EffectTracker` | class | Tracks later applied effects of lessons. |
| `EffectTrackingResult` | frozen dataclass | L2 effect metrics and status. |
| `LessonStatus` | literal alias | `verified`, `contested`, or `unverified`. |
| `IdleState` | frozen dataclass | Idle-loop trigger state. |
| `DreamLoopValidationResult` | frozen dataclass | Combined L1 and L1.5 result. |
| `DreamLoopValidator` | class | Coordinates L1, L1.5, and idle reflection checks. |

### Key Methods

- `TrajectoryValidator().validate(lesson, trajectories) -> L1ValidationResult`
- `FunctionVerifier(name, validator).validate(lesson) -> bool`
- `CrossValidator(required_consistency=0.6).validate(lesson, verifiers) -> CrossValidationResult`
- `EffectTracker().register_lesson(lesson_id, lesson, status, baseline_success_rate) -> None`
- `EffectTracker().record_application(lesson_id, task_id, success) -> None`
- `EffectTracker().evaluate(lesson_id) -> EffectTrackingResult`
- `DreamLoopValidator().validate_lesson(lesson, trajectories, verifiers) -> DreamLoopValidationResult`
- `DreamLoopValidator().should_trigger_reflection(idle_state, now, required_idle_rounds=3, required_inactivity=timedelta(minutes=15)) -> bool`
- `DreamLoopValidator().trigger_reflection_if_idle(idle_state, now) -> bool`

### Example

```python
from components.dream_loop import (
    DreamLoopValidator,
    FunctionVerifier,
    TrajectoryRecord,
)

lesson = "should avoid using unchecked shell method"
trajectories = [
    TrajectoryRecord(
        record_id="t1",
        prompt="run shell",
        action="unchecked shell method",
        outcome="failed",
        success=False,
    )
]
verifiers = [
    FunctionVerifier("policy", lambda text: "avoid" in text),
    FunctionVerifier("evidence", lambda text: "shell" in text),
]

result = DreamLoopValidator().validate_lesson(lesson, trajectories, verifiers)
assert result.status == "verified"
```

## Decision Benchmark

Files:

- `components/decision_benchmark/auto_evaluator.py`
- `components/decision_benchmark/human_labeler.py`
- `components/decision_benchmark/benchmark_runner.py`
- `components/decision_benchmark/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `AutoEvaluationResult` | frozen dataclass | Single automated evaluation result. |
| `AutoEvaluator` | class | Scores structured decision samples. |
| `DecisionSample` | frozen dataclass | Benchmark item derived from SLA constraints. |
| `BenchmarkReport` | frozen dataclass | Aggregated kappa, agreement, ICC, F1, and results. |
| `BenchmarkRunner` | class | Builds and runs decision quality benchmark. |
| `HumanLabel` | frozen dataclass | Multi-dimensional human/expert label. |
| `HumanLabeler` | class | Creates labels, consensus, and rating matrices. |

Additional public module functions in implementation files:

- `cohen_kappa(expected, observed) -> float` in `auto_evaluator.py`
- `f1_score(expected, observed, positive_label) -> float` in `auto_evaluator.py`
- `icc_two_way_random(rating_matrix) -> float` in `human_labeler.py`

### Key Methods

- `AutoEvaluator(threshold=0.70).evaluate(sample) -> AutoEvaluationResult`
- `AutoEvaluator().evaluate_many(samples) -> list[AutoEvaluationResult]`
- `HumanLabel.average_score -> float`
- `HumanLabeler().create_label(sample_id, annotator_id, scores, threshold=0.70) -> HumanLabel`
- `HumanLabeler().create_reference_labels(samples, annotators=3) -> list[HumanLabel]`
- `HumanLabeler().consensus_labels(labels) -> list[HumanLabel]`
- `HumanLabeler().rating_matrix(labels) -> list[list[float]]`
- `BenchmarkRunner().load_sla_constraints_samples(count=100) -> list[DecisionSample]`
- `BenchmarkRunner().run(samples=None, human_labels=None) -> BenchmarkReport`

### Example

```python
from components.decision_benchmark import BenchmarkRunner

runner = BenchmarkRunner()
samples = runner.load_sla_constraints_samples(count=12)
report = runner.run(samples)

assert report.sample_count == 12
assert set(report.f1_by_type) == {
    "dag_decomposition",
    "quality_assessment",
    "deviation_detection",
}
```

## Meta Loop

Files:

- `components/meta_loop/zone2_tuner.py`
- `components/meta_loop/__init__.py`

### Public API

| Symbol | Type | Purpose |
| --- | --- | --- |
| `SLAConstraints` | frozen dataclass | Blueprint-derived system SLA constraints. |
| `Blueprint` | frozen dataclass | Minimal blueprint contract for the tuner. |
| `Zone2Metrics` | frozen dataclass | Historical system metrics. |
| `TuningAction` | frozen dataclass | Concrete parameter adjustment with reason. |
| `Zone2TuningPlan` | frozen dataclass | Aggregate tuning result and updated settings. |
| `Zone2Tuner` | class | Emits deterministic Zone 2 tuning adjustments. |

### Key Methods

- `Zone2TuningPlan.triggered -> bool`
- `Zone2Tuner().analyze(blueprint, history) -> Zone2TuningPlan`

### Example

```python
from components.meta_loop import Blueprint, SLAConstraints, Zone2Metrics, Zone2Tuner

blueprint = Blueprint(SLAConstraints(token_budget=10_000))
history = [
    Zone2Metrics(token_consumed=5000, success_rate=0.65),
    Zone2Metrics(token_consumed=5200, success_rate=0.68),
    Zone2Metrics(token_consumed=4800, success_rate=0.66),
]

plan = Zone2Tuner().analyze(blueprint, history)
assert plan.triggered
assert any(action.parameter == "quality_gate_threshold" for action in plan.actions)
```

