# OpenClaw AI Native Loop Engineering Framework

OpenClaw is a componentized Python framework for AI-native loop engineering.
It coordinates request admission, model routing, DAG execution, durable state,
quality gates, loop protection, context compression, reflection, benchmarking,
and system-level tuning.

Each component exposes a focused public API through `components/*/__init__.py`.
The integration suite verifies that those contracts compose into a working loop.

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from components.quality_harness import InputGate
from components.llm_scheduler import ModelRouter, TaskComplexity
result = InputGate().check({"task_id": "t1", "action_type": "build", "goal": "Build API"})
route = ModelRouter().route(TaskComplexity.COMPLEX)
print(result.should_forward, route.model)
```

## Architecture Overview

- Task Loop: validates requests, schedules work, routes models, decomposes goals,
  validates DAG topology, gates tool output, and records state.
- Dream Loop: validates failed trajectories, cross-checks independent verifiers,
  and tracks whether lessons improve later outcomes.
- Meta Loop: reviews system metrics and tunes model choice, compression cadence,
  quality thresholds, review ratios, parallelism, and dependency structure.

## Components

1. `quality_harness`

Input, tool, and output gates for loop quality control.

2. `llm_scheduler`

Token bucket, priority queue, task complexity labels, and deterministic model routing.

3. `dag_scheduler`

Goal decomposition, topological validation, and DAG replanning.

4. `blackboard`

Atomic file-backed state, full checkpoints, and incremental checkpoint restore.

5. `circuit_breaker`

Repeated-action, token-anomaly, no-progress, and heartbeat-timeout detection.

6. `context_compressor`

Hierarchical summaries, detail archives, and periodic instruction reinjection.

7. `dream_loop`

Trajectory validation, verifier cross-checks, idle reflection, and effect tracking.

8. `decision_benchmark`

Benchmark execution, human labels, automatic evaluation, and decision reports.

9. `meta_loop`

Zone 2 tuning for models, compression, gates, review, parallelism, and dependencies.

## Runtime Flow

1. `InputGate` accepts or rejects an incoming engineering request.
2. `RequestPriorityQueue` orders accepted work by priority.
3. `ModelRouter` selects an execution model from task complexity.
4. `DAGDecomposer` creates a plan of dependent work nodes.
5. `TopologicalValidator` verifies that the plan can execute safely.
6. Workers execute nodes and submit tool results through `ToolGate`.
7. `OutputGate` accepts, retries, or escalates final output.
8. `Blackboard` records state and checkpoints progress.
9. Protection, reflection, benchmarking, and tuning loops improve future runs.

## Testing Status

The framework test suite is passing:

- 70 unit tests
- 4 integration tests
- All tests passing

Run the suite with:

```bash
pytest
```

Run only the integration path with:

```bash
pytest tests/test_integration.py
```

## Repository Layout

```text
components/
  blackboard/
  circuit_breaker/
  context_compressor/
  dag_scheduler/
  decision_benchmark/
  dream_loop/
  llm_scheduler/
  meta_loop/
  quality_harness/
docs/
tests/
```

## Notes

Most cross-component records are dataclasses or enums. Mutable state is isolated
in queues, persistence helpers, archives, effect trackers, and tuning outputs.
