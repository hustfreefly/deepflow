# DeepFlow Architecture Design

> **Document Version**: 2.0
> **Date**: 2026-06-23
> **Author**: Zhongli Ji (姬忠礼)
> **Status**: Four-domain architecture — Spec Pro v2.4 + Solution Pro 2.0.0 + Ship Pro 2.0.0 + Research Pro

---

## 📋 Document Purpose

This document describes the architectural evolution of DeepFlow:
1. **Original Blueprint (2.0.0)**: Configuration-driven declarative multi-agent collaboration platform
2. **Current Implementation (2.0.0 / 2026-06-23)**: Four-domain architecture with Spec Pro v2.4 + Solution Pro 2.0.0 + Ship Pro 2.0.0 + Research Pro. Phase 0-3 architecture hardening completed (Pydantic contract cage + single execution engine + state unification).
3. **Gap Analysis**: Objective comparison between the 2.0.0 blueprint and the current implementation

**Reference Documents**:
- `docs/deepdive_ARCHITECTURE_DESIGN_FINAL_COMPLETE.md` - 2.0.0 full architecture design (37KB)
- `docs/deepdive_ARCHITECTURE_FINAL_REPORT.md` - 2.0.0 architecture final report (43KB)

---

## Part 1: Original Blueprint Design (Deep Dive 2.0.0)

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
2. **Backward Compatible**: Existing 3 domains remain 100% intact, automated migration with zero cost
3. **Progressive Delivery**: Onion-style layering, user-controllable, patience ceiling management
4. **Fault Isolation**: Single Agent failure does not affect the global state, L1-L4 four-layer protection
5. **Observability-First**: Phase 1 includes logging/metrics/tracing, not an afterthought

**Intelligent Inversion of Control**:
- Traditional imperative: `code → call Agent → wait for result → process result`
- 2.0.0 declarative: `YAML declares desired state → PipelineEngine coordinates → Agent self-reports state → automatic state transition`

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

## Part 2: Current Implementation (DeepFlow 2.0.0 / 2026-06-23)

### 2.1 Implementation Background

**Date**: 2026-06-23
**Version**: 0.5.0
**Goal**: Four-domain architecture with Pydantic contract cage hardening. Phase 0-3 completed: schema error elimination, Pydantic single source of truth, execution engine unification, state file consolidation.

### 2.2 Current Architecture (Solution Pro as Core Framework)

```
Main Agent (depth-0)
  └── sessions_spawn → EntryHarness (depth-1)
        └── validate_and_start() → PipelineOrchestrator (depth-1)
              ├── sessions_spawn → Planner Worker (depth-2)
              ├── sessions_spawn → Reviewers ×3 (depth-2, parallel)
              ├── sessions_spawn → Researchers ×N (depth-2, parallel)
              ├── sessions_spawn → Consolidator Worker (depth-2)
              ├── sessions_spawn → Auditors ×3 (depth-2, parallel)
              ├── sessions_spawn → Fixer Worker (depth-2)
              ├── sessions_spawn → Fixer Expert Worker (depth-2)
              ├── sessions_spawn → Harness Final Worker (depth-2)
              └── sessions_spawn → Summarizer Worker (depth-2)
```

### 2.3 Core Components

| Component | File | Responsibility | Status |
|:---|:---|:---|:---:|
| **Entry Harness** | `core/quality/entry_harness.py` | Startup validation, configuration check, generate execution_plan | ✅ |
| **Pipeline Orchestrator** | `core/orchestrator/pipeline_orchestrator.py` | Read execution_plan, schedule Workers by phase | ✅ |
| **Blackboard** | `core/blackboard/` | File persistence | ✅ |
| **Contract Cage** | `core/cage/` | Validation framework | ✅ |
| **PathConfig** | `core/config/path_config.py` | Cross-platform path management | ✅ |
| **Prompt Registry** | `core/prompt_registry.py` | Centralized prompt registry | ✅ |
| **Spawn Resolver** | `core/agents/spawn_resolver.py` | Safe spawn_fn resolution | ✅ |

### 2.4 Verified Capabilities

| Capability | Verification Status | Notes |
|:---|:---:|:---|
| Multi-Agent Collaboration | ✅ | 3 Reviewers + N Researchers + Consolidator + 3 Auditors + Fixer + Harness Final + Summarizer |
| File Persistence | ✅ | Blackboard file system |
| Fault Tolerance | ✅ | Worker failure does not block the pipeline |
| End-to-End Report | ✅ | final_report.md |
| Configuration-Driven | ✅ | Domain YAML + Prompt Registry |
| Zero External Dependencies | ✅ | OpenClaw 用户 clone 即跑 |

### 2.5 Ship Pro Architecture (2.0.0, 2026-06-23) ← NEW

**Positioning**: AI-native delivery compilation engine. Consumes Solution Pro's `final_result.json`, produces `ship_package.json` (AI Coding work packages) through a 5-Agent pipeline with Pydantic contract cage.

**Architecture**:
```
Architect → Decomposer → Specifier → Reviewer ↔ 反馈闭环 → Packager
```

**Pydantic Contract Cage** (Single Source of Truth):
```
contracts/architect.py    → ArchitectOutput Pydantic 模型
contracts/packager.py     → ShipPackage Pydantic 模型
contracts/pipeline_state.py → PipelineState 模型
contracts/generator.py    → 自动从模型生成 JSON Schema + Prompt 段落 + Gate 清单
```

**Single Execution Engine** (`run_pipeline.py`):
```
python3 run_pipeline.py prepare <input> <output_dir>
python3 run_pipeline.py task <agent_name> <output_dir>
python3 run_pipeline.py gate <agent_name> <output_dir>
python3 run_pipeline.py update-status <output_dir> <agent> <PASS|CONDITIONAL|FAIL>
python3 run_pipeline.py validate <output_dir>
python3 run_pipeline.py status <output_dir>
```

**Phase 0-3 Architecture Hardening**:

| Phase | Goal | Status | Result |
|-------|------|--------|--------|
| **Phase 0** | 止血: 128 Schema 错误 → 0 | ✅ | Schema consistency validated |
| **Phase 1** | Pydantic 真相源 | ✅ | contracts/ = 唯一真相源，改一处三处对齐 |
| **Phase 2** | 执行引擎化 | ✅ | orchestrator.py DEPRECATED, run_pipeline.py 唯一入口 |
| **Phase 3** | 状态单一化 | ✅ | pipeline_state.json 唯一状态文件，pipeline_status.json 已删除 |

---

### 2.6 Solution Pro Architecture (2.0.0, 2026-06-05)

**Positioning**: The core framework layer of DeepFlow, providing general-purpose orchestration and quality gates for all domain-specific applications.

**Architecture Features**:
- **Three-Layer Separation**: EntryHarness → PipelineOrchestrator → Workers
- **Harness 2.0.0 Quality Gates**: Completeness / Necessity / Target Consistency / Global Impact + REQ-ID 追踪 + Schema 分层验证
- **Layer 2 Constraint Validation**: Planning dynamically generates constraints, Researchers explicitly validate them
- **10-Stage Complete Pipeline**: Data Collection → Planning → Reviewers → Research → Consolidator → Audit → Fix → Fixer Expert → Harness Final → Summarizer
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
              ├── Stage 7: Fixer Expert (expert-level fix)
              ├── Stage 8: Harness Final (final quality gate)
              └── Stage 9: Summarizer (generate report)
```

**Verified Capabilities**:
| Capability | Verification Status | Notes |
|:---|:---:|:---|
| Quality Gate | ✅ | ✅ Harness 2.0.0: 4D scoring + REQ-ID 追踪 + Schema 分层验证 |
| Convergence Detection | ✅ | Planning Harness scoring + iterative fixes |
| Progressive Delivery | ✅ | 30s quick preview → 2min first draft → 8min full report |
| Configuration-Driven | ✅ | Domain YAML + Prompt Registry |
| Path Decoupling | ✅ | PathConfig cross-platform path management |

---

## Part 3: Gap Analysis (Blueprint vs. Implementation)

### 3.1 Architecture Level Differences

| Dimension | Deep Dive 2.0.0 (Blueprint) | Solution Pro 2.0.0 (Solution Design) | Deviation Notes |
|:---|:---|:---|:---|
| **Orchestrator Implementation** | `PipelineEngine` Python class (~300 lines) | `pipeline_orchestrator.py` pure scheduling | 🟢 Solution uses Python pure scheduling |
| **Quality Gate** | `QualityAssessor` multi-dimensional scoring (mandatory) | ✅ Harness 2.0.0: 4D scoring + REQ-ID 追踪 | 🟢 Solution has implemented |
| **Convergence Detection** | `ConvergenceChecker` marginal benefit detection | ✅ Planning Harness + iterative fixes | 🟢 Solution has implemented |
| **Progressive Delivery** | 30s/2min/8min/30min layered delivery | ✅ 30s preview → 2min first draft → 8min report | 🟢 Solution has implemented |
| **Checkpoint Recovery** | `CheckpointManager` save per stage | **None** | 🟡 Still not implemented |
| **Intent Parsing** | `IntentParser` auto-recognize domain/depth | Manual parameter passing | 🟡 Still not implemented |
| **Pipeline Templates** | 3 templates (iterative/audit/gated) | Single hard-coded flow | 🟡 Still not implemented |
| **State Machine** | FSM flat structure (Task-level + Stage-level) | **None** | 🟡 Still not implemented |
| **Fault Isolation** | L1-L4 four-layer protection matrix | Worker failure does not block pipeline | 🟢 Equivalent implementation |
| **Configuration System** | Full YAML Schema (domain/agent/quality/convergence) | `domains/` + Prompt Registry | 🟡 Partially implemented |

### 3.2 Design Philosophy Differences

#### Blueprint Design (2.0.0): "Configuration-Driven Declarative Orchestration"
```python
# 2.0.0: PipelineEngine is a Python class, FSM-driven state transition
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

#### Current Implementation (2.0.0): "Python Pure Scheduling"
```python
# 2.0.0: PipelineOrchestrator is a Python class with explicit phase scheduling
# Reads execution_plan.json, spawns Workers by phase, handles completion via Blackboard polling
# Quality gates via Harness 2.0.0, REQ-ID tracking via covered_req_ids
```

### 3.3 Trade-off Analysis

#### ✅ Reasonable Aspects of Current Implementation

1. **Rapid Validation**: Skip complex Python Orchestrator development, use explicit phase scheduling to quickly validate end-to-end feasibility.
2. **Flexibility**: Python scheduling can handle edge cases (e.g., Worker failure does not block pipeline).
3. **OpenClaw Integration**: Directly leverage `sessions_spawn` and `sessions_yield`, no additional abstraction layer needed.

#### ❌ Shortcomings of Current Implementation

1. **No State Machine**: No FSM flat structure, cannot auto-transition between states.
2. **No Convergence Mechanism**: No `max_iterations` and convergence detection, cannot auto-iteratively optimize.
3. **Hard to Extend**: Adding a new domain requires writing a new orchestrator, rather than adding YAML config.

---

## Part 4: Evolution Roadmap

### 4.1 Short-term (0.4.0) — Completed ✅

- [x] **Investment Module Removed**: Simplified framework, zero external Python dependencies
- [x] **Force Rebuild Mechanism**: `force_rebuild` parameter
- [x] **Path Decoupling**: PathConfig cross-platform path management
- [x] **Prompt Registry**: Centralized registry
- [x] **Solution Pro 2.0.0**: Fixed 10-stage pipeline + Harness 2.0.0 + REQ-ID tracking + State persistence + Contract Cage

### 4.2 Medium-term (0.5.0) — In Progress

- [x] **Ship Pro 2.0.0**: Pydantic contract cage + 5-Agent pipeline + single execution engine
- [x] **Pydantic Contract Cage**: Single source of truth, auto Schema/Gate/Prompt alignment
- [x] **State Unification**: `pipeline_state.json` as single state file
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
| **2.0.0 Architecture Design Final** | `docs/deepdive_ARCHITECTURE_DESIGN_FINAL_COMPLETE.md` | 2.0.0 full architecture design (37KB) |
| **2.0.0 Architecture Final Report** | `docs/deepdive_ARCHITECTURE_FINAL_REPORT.md` | 2.0.0 architecture justification report (43KB) |
| Solution Pro Design | `docs/SOLUTION_PRO_MODE_DESIGN.md` | Solution Pro detailed design |
| Harness 2.0.0 Design | `docs/harness_architecture_v4.md` | Harness quality gate with REQ-ID tracking |
| Path Specification Design | `docs/PATH_DESIGN_SPEC.md` | PathConfig path management |
| Configuration Guide | `docs/configuration.md` | User configuration documentation |
| Quick Execution Card | `docs/QUICKSTART.md` | Quick start guide |
| Contract Cage Bans | `docs/CAGE_PREREQUISITE_BANS.md` | Mandatory prerequisite bans |
| Changelog | `CHANGELOG.md` | Version history |
| Prompt Registry RFC | `docs/RFC-001-prompt-registry.md` | Prompt registry design |

### B. Version Comparison Table

| Version | Date | Positioning | Orchestrator | Quality Gate | Convergence | Progressive Delivery | Checkpoint |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Deep Dive 2.0.0** | **2026-04-11** | **General Platform** | **PipelineEngine Class** | **✅ Multi-dimensional** | **✅ Marginal benefit** | **✅ Layered** | **✅ Per stage** |
| **Solution Pro 2.0.0** | **2026-06-05** | **Fixed 10-Stage Pipeline** | **Python Pure Scheduling** | **✅ Harness 2.0.0** | **✅ REQ-ID Tracking** | **✅ State Persistence** | **✅ Contract Cage** |
| **Ship Pro 2.0.0** | **2026-06-23** | **5-Agent Delivery** | **run_pipeline.py CLI** | **✅ Pydantic Gates** | **✅ Contract Cage** | **✅ Single State File** | **✅ Pydantic SSoT** |

---

*This document objectively records the architectural evolution of DeepFlow: using Deep Dive 2.0.0 as the blueprint baseline, comparing it with the current 2.0.0 implementation (Solution Pro 2.0.0 + Ship Pro 2.0.0), and providing a roadmap for future alignment. Investment module was removed in v0.4.0. Phase 0-3 hardening completed on 2026-06-23.*
