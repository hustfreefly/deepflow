# DeepFlow

> ⚠️ **Platform Dependency**: DeepFlow currently **only supports the OpenClaw platform**. Core scheduling depends on OpenClaw native APIs such as `sessions_spawn` / `sessions_yield`. Standalone execution or integration with other agent frameworks (e.g., AutoGen, LangChain, CrewAI) is not yet supported.
> **Date**: 2026-05-31
> **Status**: ✅ Four-domain architecture complete: Spec Pro v2.3 + Solution Pro v3.2 + Investment + Research Pro
> **Version**: 0.2.0
> **Positioning**: DeepFlow is an **extensible multi-agent pipeline framework** that provides a general-purpose orchestration engine and quality gates. Domain-specific applications are built on top of this framework.

---

## Introduction

DeepFlow is a **multi-agent collaborative automation pipeline** running on the **OpenClaw** platform.

> **Architecture**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture design.

### Four-Domain Architecture

| Domain | Version | Positioning | Description |
|--------|---------|-------------|-------------|
| **Spec Pro** | v2.3 | 需求梳理引擎 | 苏格拉底式对话收集需求，输出 Living Spec |
| **Solution Pro** | v3.2 | 方案设计引擎 | 10 阶段管线：理解需求 → 并行研究/评审 → 整合审计 → 质量门禁输出方案 |
| **Investment** | - | 投资分析引擎 | 投资研究管线：数据收集 → 多维分析 → 审计 → 投资简报 |
| **Research Pro** | - | 深度研究引擎 | 多源搜索 → 分层研究 → 引用验证 → 研究报告 |

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
┌─────────────────┐     ┌─────────────────┐
│   Investment    │     │   Research Pro  │
│  (投资分析)      │     │  (深度研究)      │
└─────────────────┘     └─────────────────┘
```

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **Four-Domain Architecture** | Spec Pro → Solution Pro → Investment → Research Pro |
| **Multi-Agent Pipeline** | 10-Stage full pipeline with parallel workers and quality gates |
| **Quality Gates** | Harness V3: Completeness / Necessity / Target Consistency / Global Impact |
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
│  • Investment (投资分析)                  │
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

详见 [domains/spec_pro/SKILL.md](domains/spec_pro/_overview.md)

### Solution Pro (方案设计)

```python
# 正确方式：通过 sessions_spawn 执行
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="solution_pro",
    task="""
你是 DeepFlow Solution Pro Orchestrator Agent。

任务: 设计一个智能物流仓储系统升级方案
类型: architecture
约束: 预算500万，周期6个月
利益相关者: 技术团队，财务总监
session_prefix: 智能仓储
""",
    timeout_seconds=1800
)
sessions_yield()  # 等待完成推送
```

**带 Living Spec（从 Spec Pro 传递）**:
```python
import json
with open("blackboard/spec_xxx/spec/living_spec.json") as f:
    living_spec = json.load(f)

sessions_spawn(
    runtime="subagent",
    mode="run",
    label="solution_pro",
    task=f"""
你是 DeepFlow Solution Pro Orchestrator Agent。
任务: {living_spec['confirmed']['objective']}
living_spec: {json.dumps(living_spec, ensure_ascii=False)}
...""",
    timeout_seconds=1800
)
sessions_yield()
```

详见 [domains/solution/SKILL.md](domains/solution/SKILL.md)

### Investment (投资分析)

```bash
# CLI 入口
python3 tools/deepflow_cli.py --code 688981.SH --name SMIC --industry "Semiconductor Manufacturing"
```

详见 [domains/investment/](domains/investment/)

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
├── domains/                   # Four domain applications
│   ├── spec_pro/              # Spec Pro (需求梳理引擎)
│   │   ├── prompts/           # Worker prompts (guide/assess/parse/structure)
│   │   ├── coordinator.py     # Spec Pro Coordinator
│   │   └── merge_spec.py      # Living Spec merge logic
│   ├── solution/              # Solution Pro (方案设计引擎)
│   │   ├── prompts/           # Worker prompts (planner/researcher/reviewer/...)
│   │   ├── orchestrator_agent.py
│   │   ├── task_builder.py
│   │   └── SKILL.md           # Agent execution guide
│   ├── investment/            # Investment (投资分析引擎)
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
