# DeepFlow Overview

> **Version**: V3.0.0 | **Last updated**: 2026-07-20

---

## What is DeepFlow?

DeepFlow is a **multi-agent pipeline framework** running on the OpenClaw platform. Its core mission is transforming user requirements into executable engineering plans.

**Core principle**: Code handles deterministic filtering; LLM handles semantic judgment.

---

## Five-Domain Architecture

```
User Request (natural language)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Spec Pro V2.2.0 (Requirements Collection & Structuring)        │
│  Socratic multi-round dialog → LivingSpec                      │
│  DAL: LLM domain self-inference + domain context injection     │
│  Three-layer gate: L1(code) + L2(LLM) + L3(merge)             │
└─────────────────────────────────────────────────────────────────┘
    │ living_spec.json + handoff_package
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Solution Pro V2.1.1 (Solution Design & Review)                 │
│  Three-module pipeline: Planning → Research → Summary          │
│  DAL: DomainProfile end-to-end propagation + 4 YAML configs    │
│  AI Native: code pre-filter + LLM semantic judgment            │
└─────────────────────────────────────────────────────────────────┘
    │ final_result.json (auto-handoff)
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Ship Pro V2.0.0 (Delivery Package Generation)                  │
│  PipelineDesigner → Orchestrator → Workers → Consolidator      │
│  Domain-adaptive + AI Native generalization                    │
│  Pydantic contract cage + Orchestrator full delegation          │
└─────────────────────────────────────────────────────────────────┘
    │ ship_package.md (Work Packages + dependency graph)
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Deliver Pro V1.0.0 (Execution & Delivery)                       │
│  5 Phase: Analyze → Generate → Integrate → Validate → Package  │
│  Code-First Assembly: deterministic concat, zero LLM, ≥95%     │
│  18 Pydantic contracts + 6 prompts                             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
  Final Deliverable (deliver_final.md)

Standalone Domain:
┌─────────────────────────────────────────────────────────────────┐
│ Research Pro V2.0.0 (Deep Research)                            │
│  Independent — no dependency on main pipeline                  │
│  DuckDuckGo search + multi-source analysis + citation verify   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Domain Statistics

| Domain | Version | Tests | Prompts | Modules |
|:---|:---|:---|:---|:---|
| Spec Pro | V2.2.0 | 52 | 8 | 18 |
| Solution Pro | V2.1.1 | 137 | 39 | 26 |
| Ship Pro | V2.0.0 | 19 | 1 | 3 |
| Research Pro | V2.0.0 | 136 | 8 | 10 |
| Core + Integration | — | 187 | — | — |
| **Total** | — | **531** | **56** | **57** |

---

## DAL (Domain Adaptation Layer)

DAL enables DeepFlow to handle requirements from any domain without hardcoded rules.

### Design Principles

| Principle | Description |
|:---|:---|
| LLM domain self-inference | No if/else for domain detection — LLM infers from input text |
| 4 YAML references | software/investment/hardware/business serve as few-shot examples |
| Zero-config onboarding | New domains require no code changes |
| End-to-end propagation | DomainProfile flows from Spec Pro through Ship Pro |

### Data Flow

```
Spec Pro                     Solution Pro                   Ship Pro
────────                     ────────────                   ────────
parse.md infers domain_id → domain_analysis.py         → context.json
       generates DomainProfile   generates DomainProfile      trims worker context
       injects domain context    propagates to all modules
```

---

## Three-Layer Gate Architecture

Quality assurance follows a three-layer gate pattern:

```
LLM Output
    │
    ▼
┌──────────────────────────────────┐
│ L1: Deterministic Checks (Code)  │  ← Fast, zero-cost
│  - Pydantic Schema validation    │
│  - Field existence               │
│  - Type checking                 │
│  - Format constraints            │
└──────────────────────────────────┘
    │ Pass
    ▼
┌──────────────────────────────────┐
│ L2: Semantic Check (LLM)        │  ← Understands meaning
│  - Semantic reasonableness       │
│  - Architectural soundness       │
│  - Principle alignment           │
│  - Quality assessment            │
└──────────────────────────────────┘
    │ Score
    ▼
┌──────────────────────────────────┐
│ L3: Merge Decision (Code)        │  ← Final verdict
│  - Combine L1 + L2 results       │
│  - PASS / CONDITIONAL / FAIL    │
│  - Advance to next round/stage?  │
└──────────────────────────────────┘
```

---

## Key Components

### Blackboard (Data Exchange Layer)

File-system directory. Each run produces a directory containing inputs, stage outputs, state files, and deliverables. All I/O goes through `BlackboardManager` API — no direct path concatenation.

### Core Infrastructure

| Module | Path | Responsibility |
|:---|:---|:---|
| BlackboardManager | `core/blackboard/` | File I/O abstraction |
| PathConfig | `core/config/path_config.py` | Path resolution |
| PromptRegistry | `core/prompt_registry.py` | Prompt loading & rendering |
| Cage | `core/cage/` | Contract cage (checkpoint + validator) |
| Trace | `core/trace.py` | Cross-domain tracing |

### AI Native Design

| # | Principle | Practice |
|:---|:---|:---|
| 1 | Code does deterministic pre-filtering | Pydantic validation, format checks |
| 2 | LLM does semantic judgment | Domain inference, quality assessment |
| 3 | No if/else for classification | Domain detection via LLM, not keywords |
| 4 | No regex for semantic matching | Semantic anchors, not regex |
| 5 | Prompts are collaboration contracts | Role + Context + Constraints + Examples + Output |

---

## Data Flow

```
User Input (natural language)
    │
    ▼
┌─ Spec Pro ──────────────────────────────────────────────┐
│  coordinator.py → Worker (parse.md + domain context)    │
│  merge_spec.py → living_spec.json                       │
│  contracts/gate.py → harness_report.json                │
│  handoff.py → handoff_package                           │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Solution Pro ──────────────────────────────────────────┐
│  MasterOrchestrator                                      │
│    ├─→ PlanningOrchestrator → expert results             │
│    ├─→ ResearchOrchestrator → research results           │
│    └─→ SummaryOrchestrator (5+1 Phase) → final_result   │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Ship Pro ──────────────────────────────────────────────┐
│  PipelineDesigner → PipelinePlan                         │
│  Orchestrator → Workers (parallel) → WP outputs          │
│  Consolidator → ship_package.json                        │
└──────────────────────────────────────────────────────────┘
    │
    ▼
  Delivery Package
```

---

## Running Tests

```bash
cd /Users/allen/.openclaw/workspace

# All tests (excluding archived)
python3 -m pytest .deepflow/ --ignore=.deepflow/_archive --ignore=.deepflow/tests/_archived -q

# Per-domain
python3 -m pytest .deepflow/domains/spec_pro/tests/ -q      # 52 tests
python3 -m pytest .deepflow/domains/solution_pro/tests/ -q   # 137 tests
python3 -m pytest .deepflow/domains/ship_pro/tests/ -q       # 19 tests
python3 -m pytest .deepflow/domains/research_pro/tests/ -q   # 136 tests
python3 -m pytest .deepflow/tests/ --ignore=.deepflow/tests/_archived -q  # 187 tests
```

---

## Documentation

Full documentation is in the `wiki/` directory:

| Document | Content |
|:---|:---|
| [README.md](README.md) | Documentation index + system status |
| [1-系统总览.md](1-系统总览.md) | Architecture + DAL + three-layer gate (Chinese) |
| [2-域详解.md](2-域详解.md) | Per-domain workflows + components (Chinese) |
| [3-Blackboard结构.md](3-Blackboard结构.md) | File organization + formats |
| [4-Prompt注册表.md](4-Prompt注册表.md) | 56 prompt templates |
| [5-测试覆盖地图.md](5-测试覆盖地图.md) | 531 test cases |
| [6-恢复手册.md](6-恢复手册.md) | Disaster recovery |
| [7-CodeGraph.md](7-CodeGraph.md) | Function call graphs |
| [changelog.md](changelog.md) | Version history |
