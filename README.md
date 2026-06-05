# DeepFlow

> ⚠️ **Platform Dependency**: DeepFlow currently **only supports the OpenClaw platform**. Core scheduling depends on OpenClaw native APIs such as `sessions_spawn` / `sessions_yield`. Standalone execution or integration with other agent frameworks (e.g., AutoGen, LangChain, CrewAI) is not yet supported.
> **Date**: 2026-06-05
> **Status**: ✅ Three-domain architecture complete: Spec Pro v2.4 + Solution Pro V4.4 + Research Pro
> **Version**: 0.4.0
> **Positioning**: DeepFlow is an **extensible multi-agent pipeline framework** that provides a general-purpose orchestration engine and quality gates. Domain-specific applications are built on top of this framework.

---

## Introduction

DeepFlow is a **multi-agent collaborative automation pipeline** running on the **OpenClaw** platform.

> **Architecture**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture design.

### Three-Domain Architecture

| Domain | Version | Positioning | Description |
|--------|---------|-------------|-------------|
| **Spec Pro** | v2.4 | 需求梳理引擎 | 苏格拉底式对话收集需求，输出 Living Spec（三层版本号体系） |
| **Solution Pro** | V4.4 | 方案设计引擎 | 固定 10 阶段 B 方案 + 契约笼子 + REQ-ID 追踪 + 状态持久化断点续接 |
| **Research Pro** | - | 深度研究引擎 | 多源搜索 → 分层研究 → 引用验证 → 研究报告 |

> **Note**: Investment domain was removed in v0.4.0 to reduce external dependencies (tushare/duckduckgo/google-genai). DeepFlow is now a cleaner, more focused framework for OpenClaw users.

### Domain Collaboration Flow

```
用户描述需求
    ↓
┌─────────────────┐
│    Spec Pro     │  苏格拉底式对话
│  (需求梳理)      │  → 输出 Living Spec
└────────┬────────┘
         ↓ Living Spec 交接
┌─────────────────┐
│  Solution Pro   │  10 阶段管线
│  (方案设计)      │  → 输出 final_solution.md
└─────────────────┘

或独立使用:
┌─────────────────┐
│   Research Pro  │
│  (深度研究)      │
└─────────────────┘
```

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **Three-Domain Architecture** | Spec Pro → Solution Pro → Research Pro |
| **Multi-Agent Pipeline** | 10-Stage full pipeline with parallel workers and quality gates |
| **Quality Gates** | Harness V4: Completeness / Necessity / Target Consistency / Global Impact + REQ-ID 追踪 |
| **Living Spec Handoff** | Spec Pro → Solution Pro 无缝交接，需求自动传递 |
| **Contract Cage** | 契约笼子验证框架，确保输出质量 |
| **Fault Tolerance** | Worker failures do not block the pipeline |
| **Configuration-Driven** | Domain YAML + Prompt Registry for extensibility |

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
│  Workers (Planner → Reviewers → Research │
│  → Consolidator → Auditors → Fix →       │
│  Harness Final → Summarizer)             │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│      Domain Application Layer            │
│  • Spec Pro (需求梳理)                    │
│  • Solution Pro (方案设计)                │
│  • Research Pro (深度研究)                │
└──────────────────────────────────────────┘
```

**Key Components**:
- **EntryHarness** (`core/entry_harness.py`): Startup validation, configuration check
- **PipelineOrchestrator** (`core/pipeline_orchestrator.py`): Schedules Workers by phase
- **Three-Layer Separation**: EntryHarness → PipelineOrchestrator → Workers

---

## Environment Requirements

| Dependency | Version | Notes |
|:---|:---|:---|
| **OpenClaw** | ≥ 2026.4.x | **Required**. Core scheduling depends on `sessions_spawn`. |
| Python | 3.10+ | Runtime environment |
| Node.js | 20+ | OpenClaw runtime requirement |

### Why OpenClaw is Required

DeepFlow's Orchestrator uses `sessions_spawn` to create child agents, which is an OpenClaw native tool API. The current implementation has not abstracted the platform layer.

### Future Plans

- **Short-term**: Deepen Spec Pro + Solution Pro integration, add more vertical domains
- **Medium-term**: Abstract an `AgentRuntime` interface for multi-platform support
- **Long-term**: Fully decouple platform dependencies

---

## Quick Start

### Spec Pro (需求梳理)

```python
# 通过 OpenClaw 命令触发
/spec-pro

# 或直接描述需求
"帮我梳理需求：我要做一个 AI 算力调度平台"
```

详见 [domains/spec_pro/_overview.md](domains/spec_pro/_overview.md)

### Solution Pro (方案设计)

```python
from core.unified_entry import UnifiedEntry

entry = UnifiedEntry()
result = entry.run({
    "domain": "solution",
    "topic": "设计一个智能物流仓储系统升级方案",
    "solution_type": "architecture",
    "constraints": ["预算500万", "周期6个月"],
    "session_prefix": "智能仓储"
})
```

**带 Living Spec（从 Spec Pro 传递）**:
```python
import json
from core.unified_entry import UnifiedEntry

with open("blackboard/spec_xxx/spec/living_spec.json") as f:
    living_spec = json.load(f)

entry = UnifiedEntry()
result = entry.run({
    "domain": "solution",
    "topic": living_spec["confirmed"]["objective"],
    "living_spec": living_spec,
    "session_prefix": "solution"
})
```

详见 [domains/solution/SKILL.md](domains/solution/SKILL.md)

### Research Pro (深度研究)

详见 [domains/research_pro/](domains/research_pro/)

### Research Pro (深度研究)

详见 [domains/research_pro/](domains/research_pro/)

---

## Project Structure

```
.deepflow/
├── core/                      # Core framework modules
│   ├── agents/                # Agent utilities (spawn_resolver)
│   ├── blackboard/            # Blackboard manager
│   ├── cage/                  # Contract cage loader/validator
│   ├── config/                # Path & data configuration
│   ├── data/                  # Data manager
│   ├── data_providers/        # Data source providers
│   ├── orchestrator/          # Pipeline orchestrator
│   ├── quality/               # Quality gate
│   └── search/                # Unified search interface
├── domains/                   # Three domain applications
│   ├── spec_pro/              # Spec Pro (需求梳理引擎)
│   │   ├── prompts/           # Worker prompts (guide/assess/parse/structure)
│   │   ├── coordinator.py     # Spec Pro Coordinator
│   │   └── merge_spec.py      # Living Spec merge logic
│   ├── solution/              # Solution Pro (方案设计引擎)
│   │   ├── prompts/           # Worker prompts (planner/researcher/reviewer/...)
│   │   ├── orchestrator_agent.py
│   │   ├── task_builder.py
│   │   └── SKILL.md           # Agent execution guide
│   └── research_pro/          # Research Pro (深度研究引擎)
├── config/                    # Configuration files
├── cage/                      # Contract Cage (契约笼子)
├── contracts/                 # Integration contracts
│   └── integration/           # Cross-domain contracts (spec_to_solution.md)
├── docs/                      # Documentation
│   ├── ARCHITECTURE.md
│   ├── QUICKSTART.md
│   └── ...
├── prompts/                   # Prompt templates (symlinks to domains/*/prompts)
├── scripts/                   # Scripts (ci/runners/maintenance/checks)
├── tests/                     # Tests (unit/integration)
├── tools/                     # CLI tools
├── frontend/                  # Frontend (independent project)
├── blackboard/                # Runtime data (not versioned)
├── README.md                  # This file
├── CHANGELOG.md               # Change log
├── SKILL.md                   # DeepFlow skill definition
└── .gitignore                 # Git ignore rules
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Complete architecture design |
| [QUICKSTART.md](docs/QUICKSTART.md) | Quick start guide |
| [Spec Pro SKILL](domains/spec_pro/_overview.md) | Spec Pro execution guide |
| [Solution Pro SKILL](domains/solution/SKILL.md) | Solution Pro execution guide |
| [Spec → Solution Contract](contracts/integration/spec_to_solution.md) | Living Spec handoff contract |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Version History

See [CHANGELOG.md](CHANGELOG.md)

---

## Development Standards

- [docs/archive/DEVELOPMENT_RULES.md](docs/archive/DEVELOPMENT_RULES.md)
- [docs/archive/CODING_STANDARDS.md](docs/archive/CODING_STANDARDS.md)
