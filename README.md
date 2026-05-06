# DeepFlow

> ⚠️ **Platform Dependency**: DeepFlow currently **only supports the OpenClaw platform**. Core scheduling depends on OpenClaw native APIs such as `sessions_spawn` / `sessions_yield`. Standalone execution or integration with other agent frameworks (e.g., AutoGen, LangChain, CrewAI) is not yet supported.
> **Date**: 2026-05-06
> **Status**: ✅ Phase 1 complete + PromptRegistry migration complete + Solution Pro V3.1 released
> **Version**: 0.1.1
> **Positioning**: DeepFlow is an **extensible multi-agent pipeline framework** that provides a general-purpose orchestration engine and quality gates. Domain-specific applications (e.g., Investment Analysis) are built on top of this framework.

---

## Introduction

DeepFlow is a **multi-agent collaborative automation pipeline** running on the **OpenClaw** platform.

> **Architecture**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture design, including the original blueprint (Deep Dive V3.0) and analysis of deviations in the current implementation.

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **Multi-Agent Collaboration** | 6 Researchers + 3 Auditors + Fixer + Summarizer |
| **Data-Driven** | DataManager Worker for unified data collection and search |
| **Contract Validation** | Contract Cage verification framework |
| **Fault Tolerance** | Worker failures do not block the pipeline |
| **Configuration-Driven** | Search strategy, output channel, and credential separation |

---

## Architecture

### Three-Layer Architecture

```
┌──────────────────────────────────────────┐
│         OpenClaw Platform Layer          │  ← Required dependency
│  ┌────────────────────────────────────┐  │
│  │   sessions_spawn / sessions_yield │  │
│  │        Agent Scheduling Engine     │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│      DeepFlow Framework Layer            │
│  EntryHarness → PipelineOrchestrator →   │
│  Workers (6 Researchers + 3 Auditors + ...)│
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│      Domain Application Layer            │
│  • Solution Pro (General-purpose)        │
│  • Investment Analysis (Vertical)        │
└──────────────────────────────────────────┘
```

**Execution Flow (Three-Layer)**:
```
Main Agent (depth-0)
  └── sessions_spawn → EntryHarness (depth-1)
        └── validate_and_start() → PipelineOrchestrator (depth-1)
              ├── sessions_spawn → DataManager Worker (depth-2)
              ├── sessions_spawn → Researchers ×6 (parallel)
              ├── sessions_spawn → Auditors ×3 (parallel)
              ├── sessions_spawn → Fixer Worker
              └── sessions_spawn → Summarizer Worker
```

**Key Components**:
- **EntryHarness** (`core/entry_harness.py`): Startup validation, configuration check, and execution plan generation.
- **PipelineOrchestrator** (`core/pipeline_orchestrator.py`): Reads the execution plan and schedules Workers by phase.
- **Three-Layer Separation**: EntryHarness handles startup, PipelineOrchestrator handles scheduling, and Workers handle execution.

---

## Environment Requirements

| Dependency | Version | Notes |
|:---|:---|:---|
| **OpenClaw** | ≥ 2026.4.x | **Required**. Core scheduling depends on OpenClaw's `sessions_spawn` tool. |
| Python | 3.10+ | Runtime environment |
| Node.js | 20+ | OpenClaw runtime requirement |

### Why OpenClaw is Required

DeepFlow's Orchestrator uses `sessions_spawn` to create child agents, which is an OpenClaw native tool API. The current implementation has not abstracted the platform layer and cannot run independently without OpenClaw.

### Future Plans

- **Short-term**: Maintain OpenClaw exclusivity and deepen the Investment Analysis scenario.
- **Medium-term**: Abstract an `AgentRuntime` interface to support multi-platform adaptation (OpenClaw / standalone Python / other frameworks).
- **Long-term**: Fully decouple platform dependencies to become a general-purpose multi-agent pipeline engine.

---

## Quick Start

### Investment Module (Domain-Specific Application)

```bash
# Method 1: Unified entry (recommended)
python3 deepflow.py --code 688981.SH --name SMIC --industry "Semiconductor Manufacturing"

# Method 2: Python API (for integration)
from domains.investment import InvestmentOrchestrator

orch = InvestmentOrchestrator(spawn_fn=your_spawn_adapter)
result = orch.run({
    "code": "688981.SH",
    "name": "SMIC"
})
```

### Solution Pro Module (Core Framework)

```python
from core.entry_harness import EntryHarness

# Method 1: Launch full pipeline via EntryHarness (recommended)
harness = EntryHarness()
orchestrator = harness.validate_and_start(
    domain="solution",
    context={
        "topic": "Design an intelligent logistics warehouse upgrade plan",
        "solution_type": "architecture",
        "constraints": ["Budget 5M", "Timeline 6 months"],
        "stakeholders": ["Tech Team", "CFO"],
        "session_prefix": "smart-warehouse",  # ← V3 short naming
    },
    spawn_fn=your_spawn_adapter,
)
result = orchestrator.run_pipeline()

# Method 2: Direct SolutionOrchestratorV21 call (backward compatible)
from domains.solution import SolutionOrchestratorV21
import asyncio

result = await SolutionOrchestratorV21.run(
    topic="Design an intelligent logistics warehouse upgrade plan",
    solution_type="architecture",
    constraints=["Budget 5M", "Timeline 6 months"],
    stakeholders=["Tech Team", "CFO"],
    session_prefix="smart-warehouse",  # ← V3 short naming
    spawn_fn=your_spawn_adapter,
)
```

**New Features (V3 Naming Fix)**:
- ✅ **Short session_prefix**: Supports explicit prefix input to avoid超长 session_id.
- ✅ **Three-Layer Architecture**: EntryHarness → PipelineOrchestrator → Workers.
- ✅ **Harness V2 Quality Gates**: Mid-term review (Reviewers) + Final gate (Harness Final).
- ✅ **Layer 2 Constraint Validation**: Planning dynamically generates constraints; Researchers explicitly validate them.
- ✅ **10-Stage Complete Pipeline**: Data Collection → Planning → Reviewers → Research → Consolidator → Audit → Fix → Harness Final → Summarizer.

**session_id Format**:
- With prefix: `{prefix}_{type}_{hash8}` (e.g., `smart-warehouse_architecture_a1b2c3d4`)
- Without prefix: `{topic_first_20_chars}_{type}_{hash8}`
- Ensures length ≤ 50 characters.

See [docs/SOLUTION_PRO_MODE_DESIGN.md](docs/SOLUTION_PRO_MODE_DESIGN.md) for details.

### Force Rebuild

```bash
python3 deepflow.py --code 688981.SH --name SMIC --force-rebuild
```

---

## Project Structure

```
.deepflow/
├── core/                      # Core framework modules
│   ├── master_agent.py        # Master Agent
│   ├── task_builder.py        # Task Builder
│   ├── data_manager_worker.py # DataManager
│   ├── search_engine.py       # Unified search interface
│   ├── config_loader.py       # Configuration loader
│   ├── blackboard_manager.py  # Blackboard
│   ├── pipeline_orchestrator.py  # ← Pipeline Orchestrator (depth-1)
│   ├── entry_harness.py       # ← Entry/Startup Harness
│   └── unified_entry.py       # Unified entry (uses EntryHarness)
├── domains/                   # Domain-specific applications
│   ├── investment/            # Investment Analysis (vertical scenario)
│   └── solution/              # Solution Pro (core framework)
├── data/                      # Configuration files
│   ├── search_config.yaml     # Search configuration
│   ├── output_config.yaml     # Output configuration
│   └── credentials.yaml       # Credential configuration
├── cage/                      # Contract Cage
├── data_sources/              # Data source configurations
├── data_providers/            # Data source providers
├── docs/                      # Architecture documents
│   └── ARCHITECTURE.md        # Architecture design documentation
├── prompts/                   # Prompt templates
└── orchestrator_agent.py      # Orchestrator guide
```

## Architecture Documents

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Complete architecture design (blueprint vs. implementation)
- [docs/SOLUTION_PRO_MODE_DESIGN.md](docs/SOLUTION_PRO_MODE_DESIGN.md) — Solution Pro detailed design
- [docs/SOLUTION_MODULE_DESIGN.md](docs/SOLUTION_MODULE_DESIGN.md) — Solution module architecture
- [docs/configuration.md](docs/configuration.md) — User configuration documentation
- [docs/STANDARD_EXECUTION.md](docs/STANDARD_EXECUTION.md) — Investment Analysis standard execution flow
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — Quick start guide
- [docs/harness_architecture_v2_final.md](docs/harness_architecture_v2_final.md) — Harness V2 quality gate design
- [docs/PATH_DESIGN_SPEC.md](docs/PATH_DESIGN_SPEC.md) — PathConfig path management specification
- [docs/CAGE_PREREQUISITE_BANS.md](docs/CAGE_PREREQUISITE_BANS.md) — Contract Cage prerequisite bans (**mandatory reading**)

---

## Version History

See [CHANGELOG.md](CHANGELOG.md)

---

## Development Standards

See [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) and [CODING_STANDARDS.md](CODING_STANDARDS.md)
