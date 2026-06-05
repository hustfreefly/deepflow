# DeepFlow Architecture Design

> **Document Version**: 1.3
> **Date**: 2026-06-03
> **Author**: Zhongli Ji (姬忠礼)
> **Status**: Four-domain architecture — Spec Pro v2.4 + Solution Pro V4.4 + Investment + Research Pro

---

## 📋 Document Purpose

This document describes the architectural evolution of DeepFlow:
1. **Original Blueprint (V3.0)**: Configuration-driven declarative multi-agent collaboration platform
2. **Current Implementation (V0.3.0 / 2026-06-03)**: Four-domain architecture with Spec Pro v2.4 + Solution Pro V4.4 + Investment + Research Pro
3. **Gap Analysis**: Objective comparison between the V3.0 blueprint and the current implementation

**Reference Documents**:
- `docs/deepdive_ARCHITECTURE_DESIGN_FINAL_COMPLETE.md` - V3.0 full architecture design (37KB)
- `docs/deepdive_ARCHITECTURE_FINAL_REPORT.md` - V3.0 architecture final report (43KB)

---

## Part 1: Original Blueprint Design (Deep Dive V3.0)

### 1.1 Design Background

**Date**: 2026-04-11
**Source**: `memory/cold/projects/deep-dive-v3.0-architecture-final-2026-04-11/`
**Goal**: Build a configuration-driven declarative multi-agent collaboration platform where adding a new domain equals adding a YAML configuration (for 80% of scenarios).

**Design Philosophy**:
> **"Configuration-driven, declarative orchestration, intelligent inversion of control, progressive delivery, observability-first, four-layer fault tolerance"**

**Core Positioning**: Transition from hard-coded pipelines to a configuration-driven declarative multi-agent collaboration platform.

### 1.2 Core Architecture (Three-Layer Architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│                 Configuration Layer                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │   domains/  │ │  pipelines/ │ │   prompts/  │               │
│  │   *.yaml    │ │   *.yaml    │ │   *.md      │               │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
└────────────────────────────┬────────────────────────────────────┘
                             │ Declarative Loading
┌────────────────────────────▼────────────────────────────────────┐
│                    Runtime Layer                                │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              PipelineEngine (Python ~300 lines)           │ │
│  │   Stage Scheduling │ Convergence │ Quality │ Checkpoint  │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │   iterative │ │    audit    │ │    gated    │              │
│  │   pipeline  │ │   pipeline  │ │   pipeline  │              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
└────────────────────────────┬────────────────────────────────────┘
                             │ sessions_spawn
┌────────────────────────────▼────────────────────────────────────┐
│                   Platform Layer                                │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ planner ││researcher││ auditor ││ fixer   ││summarizer│   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           Blackboard (file sharing + shared_state)      │   │
│  │   ~/.openclaw/workspace/.v3/blackboard/{session_id}/   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Core Mechanisms

| Mechanism | Description | Purpose |
|:---|:---|:---|
| **PipelineEngine** | YAML declarative + lightweight Python engine | Balance flexibility and maintainability |
| **IntentParser** | Auto-parse user intent → DomainConfig | Auto-match domain configuration |
| **PipelineSelector** | Select pipeline template (iterative/audit/gated) | Cover 6 major application scenarios |
| **Quality Gate** | `QualityAssessor` multi-dimensional scoring | Ensure each stage output meets quality standards |
| **Convergence Detection** | `ConvergenceChecker` marginal benefit detection | Auto-iterative optimization |
| **Progressive Delivery** | 30s/2min/8min/30min layered delivery | Solve user patience ceiling |
| **Checkpoint** | `CheckpointManager` save per stage | Support resume and fault recovery |
| **Fault Isolation** | L1-L4 four-layer protection (Agent→Stage→Pipeline→System) | Production-grade fault tolerance |
| **Human-in-the-Loop** | HITL gating node (only gated pipeline) | Human confirmation/rejection at critical decision points |

### 1.4 Design Philosophy

> **"Framework layer is general-purpose, application layer is vertical"**

**Five Design Principles**:
1. **Configuration-Driven**: 80% of scenarios use pure YAML configuration, 20% complex scenarios are extensible
2. **Backward Compatible**: Existing 4 domains remain 100% intact, automated migration with zero cost
3. **Progressive Delivery**: Onion-style layering, user-controllable, patience ceiling management
4. **Fault Isolation**: Single Agent failure does not affect the global state, L1-L4 four-layer protection
5. **Observability-First**: Phase 1 includes logging/metrics/tracing, not an afterthought

**Intelligent Inversion of Control**:
- Traditional imperative: `code → call Agent → wait for result → process result`
- V3.0 declarative: `YAML declares desired state → PipelineEngine coordinates → Agent self-reports state → automatic state transition`

### 1.5 FSM State Machine

```
                    ┌─────────────┐
         ┌─────────│   FAILED    │◄──── Any abnormal/timeout state
         │         └──────┬──────┘      or L1-L4 fault unrecoverable
         │                │
         │                │ Recovery (from Checkpoint)
         ▼                ▼
┌──────────┐    ┌─────────────┐    ┌─────────────┐
│   INIT   │───►│  PLANNING   │───►│  EXECUTING  │
└──────────┘    └─────────────┘    └──────┬──────┘
                                          │
                                          ▼
┌──────────┐    ┌─────────────┐    ┌─────────────┐
│   DONE   │◄───│  DELIVERING │◄───│  CHECKING   │
└──────────┘    └──────┬──────┘    └──────┬──────┘
                       │      Not Converged│ Converged
                       │            ┌────┘
                       │            ▼
                       │    ┌─────────────┐
                       └────│   FIXING    │
                            └─────────────┘
                                          │
                                          ▼
                            ┌─────────────┐
                            │   HITL      │◄──── Gated pipeline only
                            │  (Human)     │      Human confirm/reject
                            └─────────────┘
```

### 1.6 Progressive Delivery Design

```
T+30s   → 🚀 Quick Preview (Intent parse result + execution plan outline + estimated total time)
T+2min  → 📄 First Draft (Core framework/structure + Top 3 key findings + confidence assessment)
T+8min  → 📊 Full Report (Detailed analysis + multi-angle argumentation + actionable recommendations)
T+30min → 🔬 Deep Research (Full coverage + complete evidence chain + risk simulation)
[If timeout, enters async execution, completion notification pushed via Feishu]
```

---

## Part 2: Current Implementation (DeepFlow V0.3.0 / 2026-06-03)

### 2.1 Implementation Background

**Date**: 2026-04-24
**Version**: 0.3.0 (internal codename V4.0 → evolved to 0.3.0)
**Goal**: Adapt the V3.0 blueprint to "Investment Analysis" and "Solution Design" vertical scenarios to quickly validate end-to-end feasibility.

### 2.2 Current Architecture (Solution Pro as Core Framework)

```
Main Agent (depth-0)
  └── sessions_spawn → EntryHarness (depth-1)
        └── validate_and_start() → PipelineOrchestrator (depth-1)
              ├── sessions_spawn → DataManager Worker (depth-2)
              ├── sessions_spawn → Planner Worker (depth-2)
              ├── sessions_spawn → Reviewers ×3 (depth-2, parallel)
              ├── sessions_spawn → Researchers ×N (depth-2, parallel)
              ├── sessions_spawn → Consolidator Worker (depth-2)
              ├── sessions_spawn → Auditors ×3 (depth-2, parallel)
              ├── sessions_spawn → Fixer Worker (depth-2)
              ├── sessions_spawn → Harness Final Worker (depth-2)
              └── sessions_spawn → Summarizer Worker (depth-2)
```

**Domain-Specific Application (Investment Analysis)**:
```
Main Agent (depth-0)
  └── sessions_spawn → Orchestrator Agent (depth-1)
        ├── Read tasks.json + execution_plan.json
        ├── sessions_spawn → DataManager Worker (depth-2)
        ├── sessions_spawn → Planner Worker (depth-2)
        ├── sessions_spawn → Researchers ×6 (depth-2, parallel)
        ├── sessions_spawn → Auditors ×3 (depth-2, parallel)
        ├── sessions_spawn → Fixer Worker (depth-2)
        ├── sessions_spawn → Summarizer Worker (depth-2)
        └── sessions_spawn → SendReporter Worker (depth-2)
```

### 2.3 Core Components

| Component | File | Responsibility | Status |
|:---|:---|:---|:---:|
| **Master Agent** | `core/master_agent.py` | Generate session, build Tasks | ✅ |
| **Entry Harness** | `core/entry_harness.py` | Startup validation, configuration check, generate execution_plan | ✅ |
| **Pipeline Orchestrator** | `core/pipeline_orchestrator.py` | Read execution_plan, schedule Workers by phase | ✅ |
| **Task Builder** | `core/task_builder.py` | Build Worker Tasks | ✅ |
| **Orchestrator** | `orchestrator_agent.py` | Agent guide (LLM autonomous scheduling) | ⚠️ Investment module still uses this |
| **DataManager** | `core/data_manager_worker.py` | Data collection + unified search | ✅ |
| **Blackboard** | `blackboard/{session_id}/` | File persistence | ✅ |
| **Contract Cage** | `cage/` | Validation framework | ✅ |
| **PathConfig** | `core/config/path_config.py` | Cross-platform path management | ✅ |
| **Prompt Registry** | `prompts/prompt_registry.py` | Centralized prompt registry | ✅ |

### 2.4 Verified Capabilities

| Capability | Verification Status | Notes |
|:---|:---:|:---|
| Multi-Agent Collaboration | ✅ | 6 Researchers + 3 Auditors + Fixer + Summarizer |
| Data-Driven | ✅ | DataManager unified collection, Tushare + fallback |
| File Persistence | ✅ | Blackboard file system |
| Fault Tolerance | ✅ | Worker failure does not block the pipeline |
| End-to-End Report | ✅ | final_report.md + Feishu send |
| Search Configuration | ✅ | `search_config.yaml` + `SearchEngine` interface |
| Credential Security | ✅ | `credentials.yaml` centralized management |

---

### 2.5 Solution Pro Architecture (V4.4, 2026-06-03)

**Positioning**: The core framework layer of DeepFlow, providing general-purpose orchestration and quality gates for all domain-specific applications.

**Architecture Features**:
- **Three-Layer Separation**: EntryHarness → PipelineOrchestrator → Workers
- **Harness V4 Quality Gates**: Completeness / Necessity / Target Consistency / Global Impact + REQ-ID 追踪 + Schema 分层验证
- **Layer 2 Constraint Validation**: Planning dynamically generates constraints, Researchers explicitly validate them
- **10-Stage Complete Pipeline**: Data Collection → Planning → Reviewers → Research → Consolidator → Audit → Fix → Harness Final → Summarizer
- **Centralized Writes**: All Worker outputs are written through a unified BlackboardManager

**Execution Flow**:
```
Main Agent (depth-0)
  └── sessions_spawn → EntryHarness (depth-1)
        └── validate_and_start() → PipelineOrchestrator (depth-1)
              ├── Stage 1: Planner (create research plan)
              ├── Stage 2: Reviewers ×3 (parallel plan review)
              ├── Stage 3: Researchers ×N (parallel research)
              ├── Stage 4: Consolidator (integrate research results)
              ├── Stage 5: Auditors ×3 (parallel audit)
              ├── Stage 6: Fixer (fix issues)
              ├── Stage 7: Harness Final (final quality gate)
              └── Stage 8: Summarizer (generate report)
```

**Verified Capabilities**:
| Capability | Verification Status | Notes |
|:---|:---:|:---|
| Quality Gate | ✅ | ✅ Harness V4: 4D scoring + REQ-ID 追踪 + Schema 分层验证 |
| Convergence Detection | ✅ | Planning Harness scoring + iterative fixes |
| Progressive Delivery | ✅ | 30s quick preview → 2min first draft → 8min full report |
| Configuration-Driven | ✅ | Domain YAML + Prompt Registry |
| Path Decoupling | ✅ | PathConfig cross-platform path management |

---

## Part 3: Gap Analysis (Blueprint vs. Implementation)

### 3.1 Architecture Level Differences

| Dimension | Deep Dive V3.0 (Blueprint) | Investment Analysis | Solution Pro V4.4 (Solution Design) | Deviation Notes |
|:---|:---|:---|:---|:---|
| **Orchestrator Implementation** | `PipelineEngine` Python class (~300 lines) | Agent guide text (`orchestrator_agent.py`) | `orchestrator_agent.py` pure scheduling | 🔴 Investment module still uses LLM autonomy, Solution has moved to code control |
| **Quality Gate** | `QualityAssessor` multi-dimensional scoring (mandatory) | **None** | ✅ Harness V4: 4D scoring + REQ-ID 追踪 | 🟢 Solution has implemented |
| **Convergence Detection** | `ConvergenceChecker` marginal benefit detection | **None** | ✅ Planning Harness + iterative fixes | 🟢 Solution has implemented |
| **Progressive Delivery** | 30s/2min/8min/30min layered delivery | Single final report | ✅ 30s preview → 2min first draft → 8min report | 🟢 Solution has implemented |
| **Checkpoint Recovery** | `CheckpointManager` save per stage | **None** | **None** | 🟡 Still not implemented |
| **Intent Parsing** | `IntentParser` auto-recognize domain/depth | Manual parameter passing | Manual parameter passing | 🟡 Still not implemented |
| **Pipeline Templates** | 3 templates (iterative/audit/gated) | Single hard-coded flow | Single hard-coded flow | 🟡 Still not implemented |
| **State Machine** | FSM flat structure (Task-level + Stage-level) | **None** | **None** | 🟡 Still not implemented |
| **Fault Isolation** | L1-L4 four-layer protection matrix | Worker failure does not block pipeline | Worker failure does not block pipeline | 🟢 Equivalent implementation |
| **Configuration System** | Full YAML Schema (domain/agent/quality/convergence) | `domains/` directory (partial configuration) | `domains/` + Prompt Registry | 🟡 Partially implemented |

### 3.2 Design Philosophy Differences

#### Blueprint Design (V3.0): "Configuration-Driven Declarative Orchestration"
```python
# V3.0: PipelineEngine is a Python class, FSM-driven state transition
class PipelineEngine:
    def execute(self, blackboard: Blackboard) -> ExecutionResult:
        while self.state not in [DONE, FAILED]:
            stage_config = self.get_current_stage()
            result = self.execute_stage(stage_config, blackboard)
            self.state = self.transition(self.state, result)

            # Quality assessment
            scores = QualityAssessor.assess(stage_output)
            if not scores.passed:
                self.state = FIXING

            # Convergence detection
            converged = ConvergenceChecker.check(scores)
            if converged:
                self.state = DELIVERING

            CheckpointManager.save(blackboard)
```

#### Current Implementation (V4.0): "LLM Autonomous Scheduling"
```python
# V4.0: Orchestrator is an Agent guide text
# Agent reads the guide and autonomously decides which Workers to spawn
# No code-level quality gate, no auto-iteration, no checkpoint recovery
```

### 3.3 Trade-off Analysis

#### ✅ Reasonable Aspects of Current Implementation

1. **Rapid Validation**: Skip complex Python Orchestrator development, use Agent guide to quickly validate end-to-end feasibility.
2. **Flexibility**: LLM autonomous scheduling can handle unforeseen edge cases (e.g., dynamic adjustment when Workers fail).
3. **OpenClaw Integration**: Directly leverage `sessions_spawn` and `sessions_yield`, no additional abstraction layer needed.

#### ❌ Shortcomings of Current Implementation

1. **Unpredictability**: LLM may reuse historical data (has occurred), skip steps, or misinterpret the guide.
2. **No Quality Assurance**: No `quality_gate`, pipeline may produce low-quality reports.
3. **No Convergence Mechanism**: No `max_iterations` and convergence detection, cannot auto-iteratively optimize.
4. **Hard to Extend**: Adding a new domain requires rewriting the Agent guide, rather than reusing templates.

---

## Part 4: Evolution Roadmap

### 4.1 Short-term (0.2.0) — Completed ✅

- [x] **Force Rebuild Mechanism**: `force_rebuild` parameter
- [x] **Path Decoupling**: PathConfig cross-platform path management
- [x] **Prompt Registry**: Centralized registry
- [x] **Solution Pro V4.4**: Fixed 10-stage pipeline + Harness V4 + REQ-ID tracking + State persistence + Contract Cage

### 4.2 Medium-term (0.3.0)

- [ ] **Align with V3.0 Design**: Transition Investment module Orchestrator from Agent guide to `PipelineEngine` Python class
- [ ] **Checkpoint Recovery**: `CheckpointManager` save per stage, support resume
- [ ] **Intent Parsing**: `IntentParser` auto-recognize domain/depth
- [ ] **Pipeline Templates**: 3 templates (iterative/audit/gated)
- [ ] **State Machine**: FSM flat structure (Task-level + Stage-level)

### 4.3 Long-term (1.0.0)

- [ ] **Fully Align with General Framework**: `MultiAgentOrchestrator` + `Workflow` + `AgentTask`
- [ ] **Multi-Domain Extension**: Code review, research reports, legal documents, etc.
- [ ] **Visualization**: Pipeline execution visualization, quality score tracking

---

## Appendix

### A. Related Document Index

| Document | Location | Description |
|:---|:---|:---|
| **V3.0 Architecture Design Final** | `docs/deepdive_ARCHITECTURE_DESIGN_FINAL_COMPLETE.md` | V3.0 full architecture design (37KB) |
| **V3.0 Architecture Final Report** | `docs/deepdive_ARCHITECTURE_FINAL_REPORT.md` | V3.0 architecture justification report (43KB) |
| V3.0 Architecture Diagram | `~/.openclaw/canvas/v3-architecture-diagram.html` | Interactive architecture diagram (6 core diagrams) |
| V1 Blueprint | `.deepflow/V1_BLUEPRINT.md` | Early architecture design |
| **V4 Architecture Plan (Historical)** | `docs/archive/V4_ARCHITECTURE_PLAN.md` | V4 refactoring plan (archived) |
| Solution Pro Design | `docs/SOLUTION_PRO_MODE_DESIGN.md` | Solution Pro detailed design |
| Solution Module Design | `docs/SOLUTION_MODULE_DESIGN.md` | Solution module architecture |
| Harness V4 Design | `docs/harness_architecture_v4.md` | Harness quality gate with REQ-ID tracking |
| Path Specification Design | `docs/PATH_DESIGN_SPEC.md` | PathConfig path management |
| Standard Execution Manual | `docs/STANDARD_EXECUTION.md` | Investment Analysis standard execution |
| Configuration Guide | `docs/configuration.md` | User configuration documentation |
| Quick Execution Card | `docs/QUICKSTART.md` | Quick start guide |
| Development Standards | `DEVELOPMENT_RULES.md` | Contract Cage standards |
| Coding Standards | `CODING_STANDARDS.md` | Code quality standards |
| Prompt Registry RFC | `docs/RFC-001-prompt-registry.md` | Prompt registry design |
| Launch Protocol | `docs/LAUNCH_PROTOCOL.md` | Orchestrator launch specification |
| Contract Cage Bans | `docs/CAGE_PREREQUISITE_BANS.md` | Mandatory prerequisite bans |
| Changelog | `CHANGELOG.md` | Version history |
| Investment Module Changes | `domains/investment/CHANGES.md` | Investment fix records |

### B. Version Comparison Table

| Version | Date | Positioning | Orchestrator | Quality Gate | Convergence | Progressive Delivery | Checkpoint |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Deep Dive V3.0** | **2026-04-11** | **General Platform** | **PipelineEngine Class** | **✅ Multi-dimensional** | **✅ Marginal benefit** | **✅ Layered** | **✅ Per stage** |
| V1 Blueprint | 2026-04-18 | Investment Scenario | Python class (design) | ✅ (design) | ⚠️ (design) | ❌ | ⚠️ (design) |
| V3 Protocol | 2026-04-15 | Investment Scenario | Coordinator class | ✅ (design) | ⚠️ (design) | ⚠️ (design) | ⚠️ (design) |
| DeepFlow V4.0 | 2026-04-24 | Investment Scenario | Agent guide | ❌ | ❌ | ❌ | ❌ |
| **Solution Pro V4.4** | **2026-06-03** | **Fixed 10-Stage Pipeline** | **Python Pure Scheduling** | **✅ Harness V4** | **✅ REQ-ID Tracking** | **✅ State Persistence** | **✅ Contract Cage** |

---

*This document objectively records the architectural evolution of DeepFlow: using Deep Dive V3.0 as the blueprint baseline, showing the differences between the Investment Analysis module and the Solution Pro V4.4 Solution Design module, and providing a roadmap for future alignment.*
