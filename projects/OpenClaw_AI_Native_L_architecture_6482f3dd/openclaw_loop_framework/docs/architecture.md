# OpenClaw AI Native Loop Engineering Framework Architecture

## Introduction

OpenClaw AI Native Loop Engineering Framework is a componentized Python framework for AI-native engineering work. It separates active execution, idle-time reflection, and system-level self-tuning into three cooperating loops.

The Task Loop handles the live user request. The Dream Loop validates lessons discovered during idle reflection. The Meta Loop tunes policy from blueprint constraints, SLA targets, and observed metrics.

The implementation lives under `components/`. The cross-component runtime contract is covered by `tests/test_integration.py`.

## Three-Layer Architecture

```text
+----------------------------------------------------------------------------+
|              OpenClaw AI Native Loop Engineering Framework                  |
+----------------------------------------------------------------------------+
|                                                                            |
|  TASK LOOP: active execution path                                           |
|                                                                            |
|  WP-001 Input Gate                                                          |
|      |                                                                     |
|      v                                                                     |
|  WP-002 Model Router                                                        |
|      |                                                                     |
|      v                                                                     |
|  WP-003 Priority Queue + Token Bucket                                       |
|      |                                                                     |
|      v                                                                     |
|  WP-004 DAG Decomposer                                                      |
|      |                                                                     |
|      v                                                                     |
|  WP-005 Topological Validator                                               |
|      |                                                                     |
|      v                                                                     |
|  WP-006 Blackboard State + Checkpoints                                      |
|      |                                                                     |
|      v                                                                     |
|  WP-007 Tool Gate                                                           |
|      |                                                                     |
|      v                                                                     |
|  WP-008 Output Gate                                                         |
|      |                                                                     |
|      v                                                                     |
|  WP-009 Context Compressor + Instruction Reinjection                        |
|      |                                                                     |
|      v                                                                     |
|  WP-010 Circuit Breaker + DAG Replanner                                     |
|                                                                            |
+----------------------------------------------------------------------------+
|                                                                            |
|  DREAM LOOP: idle reflection and lesson validation                          |
|                                                                            |
|  WP-011 Idle Detection + DreamLoopValidator                                 |
|      |                                                                     |
|      v                                                                     |
|  WP-012 L1 Trajectory Validation                                            |
|         L1.5 Cross Validation                                               |
|         L2 Applied-Effect Tracking                                          |
|                                                                            |
+----------------------------------------------------------------------------+
|                                                                            |
|  META LOOP: system-level adaptation                                         |
|                                                                            |
|  WP-013 Blueprint + SLA Constraints                                         |
|      |                                                                     |
|      v                                                                     |
|  WP-014 Zone 2 Metrics History                                              |
|      |                                                                     |
|      v                                                                     |
|  WP-015 Zone2Tuner                                                          |
|      |                                                                     |
|      v                                                                     |
|  WP-016 Decision Benchmark + Human/Auto Evaluation                          |
|                                                                            |
+----------------------------------------------------------------------------+
```

## Component List

- **WP-001: Input Gate** (`components.quality_harness.input_gate`): `InputGate` rejects malformed requests before scheduling. The default required fields are `task_id` and `action_type`; `InputGateResult` reports `accepted`, `missing_fields`, and `should_forward`.
- **WP-002: Model Router** (`components.llm_scheduler.model_router`): `ModelRouter` maps `TaskComplexity` to model tiers. Defaults are `simple -> flash`, `medium -> standard`, and `complex -> opus`; `RouteDecision` records model, tier, complexity, and latency.
- **WP-003: Priority Queue and Token Bucket** (`components.llm_scheduler.priority_queue`, `components.llm_scheduler.token_bucket`): `RequestPriorityQueue` orders work by priority while preserving FIFO order inside a priority. `TokenBucket` provides async refill-rate and burst-capacity throttling.
- **WP-004: DAG Decomposer** (`components.dag_scheduler.dag_decomposer`): `DAGDecomposer` turns a goal into a `DAGPlan` through an injected scheduler or deterministic fallback. `DecompositionResult` includes the plan, route hint, and quality score.
- **WP-005: Topological Validator** (`components.dag_scheduler.topo_validator`): `TopologicalValidator` checks missing dependencies, cycles, and executable order. Workers should only consume validated plans.
- **WP-006: Blackboard State and Checkpoints** (`components.blackboard`): `Blackboard` stores JSON-compatible state. `CheckpointManager` maintains full and incremental checkpoints. `atomic_write` uses same-directory temp files, fsync, and atomic replacement.
- **WP-007: Tool Gate** (`components.quality_harness.tool_gate`): `ToolGate` validates tool output against required schema fields and returns missing fields, deviation logs, and an `accept` or `retry` action.
- **WP-008: Output Gate** (`components.quality_harness.output_gate`): `OutputGate` applies an evaluator-optimizer split, accepting output above threshold, retrying while budget remains, and escalating exhausted retries to human review.
- **WP-009: Context Compressor and Instruction Reinjection** (`components.context_compressor`): `ContextCompressor` summarizes long-running context, `BlackboardArchive` preserves original detail, and `InstructionReinjector` restores goals, Zone 0 safety rules, and key constraints on cadence.
- **WP-010: Circuit Breaker and DAG Replanner** (`components.circuit_breaker`, `components.dag_scheduler.replanner`): `SignalDetector` detects repeated actions, token anomalies, heartbeat timeouts, and no-progress streaks. `AdaptiveThreshold` scales thresholds by complexity. `DAGReplanner` replaces failed work while preserving successful nodes.
- **WP-011: Idle Detection and DreamLoopValidator** (`components.dream_loop`): `DreamLoopValidator` decides whether reflection should run. `IdleState` tracks rounds without new nodes, last activity time, and active subagent count.
- **WP-012: Lesson Validation Pipeline** (`components.dream_loop.l1_trajectory`, `l1_5_cross_validate`, `l2_effect_tracking`): `TrajectoryValidator` checks lessons against trajectory evidence. `CrossValidator` requires independent verifier agreement. `EffectTracker` measures applied effect and can contest lessons.
- **WP-013: Blueprint and SLA Constraints** (`components.meta_loop.zone2_tuner`): `Blueprint` carries the Meta Loop contract. `SLAConstraints` defines token budget, success-rate floor, concurrency limit, target quality threshold, and manual review step size.
- **WP-014: Zone 2 Metrics History** (`components.meta_loop.zone2_tuner`): `Zone2Metrics` captures token use, success rate, concurrent agents, model, compression frequency, quality threshold, manual review ratio, parallelism, and serial dependency ratio.
- **WP-015: Zone2Tuner** (`components.meta_loop.zone2_tuner`): `Zone2Tuner` analyzes constraints and metrics, then emits `TuningAction` records with parameter, before value, after value, and reason. It can tune model tier, compression cadence, quality threshold, manual review, parallelism, and dependency ratio.
- **WP-016: Decision Benchmark and Evaluation** (`components.decision_benchmark`): `BenchmarkRunner` creates samples and reports. `AutoEvaluator` scores samples automatically. `HumanLabeler` creates reference labels, consensus labels, and rating matrices.

## Data Flow Diagram

```text
User Request
    |
    v
InputGate
    | accepted request
    v
ModelRouter
    | route decision
    v
RequestPriorityQueue -----> TokenBucket
    | scheduled capacity
    v
DAGDecomposer
    | DAGPlan + quality score
    v
TopologicalValidator
    | valid DAG
    v
Blackboard
    | durable state + checkpoints
    v
Worker / Tool Execution
    | tool result
    v
ToolGate
    | accepted result or retry request
    v
OutputGate
    | accepted output, retry, or human review
    v
ContextCompressor + InstructionReinjector
    | compact context + restored core instructions
    v
SignalDetector
    | no signal -------------------------------+
    | signal                                  |
    v                                         |
DAGReplanner                                 |
    | replacement nodes                        |
    +---------------------> Blackboard <------+
```

## Cross-Loop Feedback

```text
Task Loop outcomes
    |
    +-- state, checkpoints, retries, failures
    v
Dream Loop idle reflection
    |
    +-- L1 trajectory evidence
    +-- L1.5 independent verification
    +-- L2 applied-effect evidence
    v
Verified or contested lessons
    |
    v
Meta Loop metrics history
    |
    +-- token consumption
    +-- success rate
    +-- model tier
    +-- compression frequency
    +-- quality threshold
    +-- parallelism pressure
    v
Zone2Tuner
    |
    +-- tuning actions applied back to Task Loop policy
```

## Integration Points

- **External request boundary**: callers provide a mapping with at least `task_id` and `action_type`; planning paths also require a goal-like field.
- **LLM provider boundary**: provider-specific model IDs stay behind `ModelRouter`, so downstream components consume model-tier decisions.
- **Scheduler boundary**: priority and token controls decide when expensive work may start and can integrate with worker pools, API clients, or subagent dispatchers.
- **DAG boundary**: `DAGPlan` and `DAGNode` are the planning exchange format; validation precedes execution, and replanning should preserve successful nodes.
- **Persistence boundary**: Blackboard stores JSON-compatible state, full checkpoints, and incremental patches under a configured root.
- **Tool boundary**: `ToolGate` validates schema-sensitive tool output before final synthesis consumes it.
- **Quality boundary**: `OutputGate` centralizes accept, retry, and human-review decisions behind a configurable evaluator.
- **Context boundary**: compression and reinjection keep long-running sessions bounded while preserving original detail in an archive.
- **Recovery boundary**: worker telemetry enters as `WorkerEvent`, becomes `WorkerSignal`, and can trigger targeted replanning.
- **Dream Loop boundary**: idle detection integrates with orchestrator activity tracking and should not run while subagents remain active.
- **Meta Loop boundary**: blueprints, SLA constraints, and metrics history produce auditable tuning actions with old values, new values, and reasons.
- **Benchmark boundary**: automatic scores and human labels calibrate evaluator quality and policy changes before promotion.

## Verification Contract

`test_task_loop_flow` verifies input validation, model routing, DAG decomposition, topological validation, scheduling, and Blackboard checkpointing.

`test_dream_loop_idle_detection` verifies idle reflection trigger behavior.

`test_meta_loop_tuning` verifies Zone 2 tuning for success-rate degradation and parallelism pressure.

`test_cross_component_imports` verifies public component imports and basic initialization.

Future architecture changes should update this document and the relevant contract tests together.
