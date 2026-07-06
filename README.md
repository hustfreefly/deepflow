# DeepFlow

> ⚠️ **Platform Dependency**: DeepFlow currently **only supports the OpenClaw platform**. Core scheduling depends on OpenClaw native APIs such as `sessions_spawn` / `sessions_yield`. Standalone execution or integration with other agent frameworks (e.g., AutoGen, LangChain, CrewAI) is not yet supported.
> **Date**: 2026-06-23
> **Status**: ✅ Four-domain architecture complete: Spec Pro 2.0.0 + Solution Pro 2.0.0 + Ship Pro 2.0.0 + Research Pro
> **Version**: 2.0.0
> **Positioning**: DeepFlow is an **extensible multi-agent pipeline framework** that provides a general-purpose orchestration engine, Pydantic contract cages, and quality gates. Domain-specific applications are built on top of this framework.

> 🚀 **新用户？** 请看 [QUICKSTART.md](docs/guides/QUICKSTART.md) — 5 分钟上手指南

---

## 快速开始

```bash
# 1. 安装 OpenClaw
npm install -g openclaw

# 2. 克隆 DeepFlow
cd ~/.openclaw/workspace && git clone https://github.com/deepflow/deepflow .deepflow

# 3. 使用（在 OpenClaw 对话中）
/spec-pro          # 梳理需求
/solution-pro      # 设计方案
/research-pro      # 深度研究
```

详见 [QUICKSTART.md](docs/guides/QUICKSTART.md)

---

## Introduction

DeepFlow is a **multi-agent collaborative automation pipeline** running on the **OpenClaw** platform.

> **Architecture**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture design.

### Four-Domain Architecture

| Domain | Version | Positioning | Description |
|--------|---------|-------------|-------------|
| **Spec Pro** | 2.0.0 | 需求梳理引擎 | 苏格拉底式对话收集需求，输出 Living Spec（三层版本号体系） |
| **Solution Pro** | 2.0.0 | 方案设计引擎 | 固定 10 阶段 B 方案 + 契约笼子 + REQ-ID 追踪 + 状态持久化断点续接 |
| **Ship Pro** | 2.0.0 | 交付编译引擎 | Pydantic 契约笼子 + 5 Agent 管线，消费 Solution Pro 输出，生成 ship_package.json（AI Coding 工作包） |
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
│  (方案设计)      │  → 输出 final_result.json
└────────┬────────┘
         ↓ final_result.json 自动交接
┌─────────────────┐
│    Ship Pro     │  Pydantic 契约笼子
│  (交付编译)      │  → 输出 ship_package.json
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
| **Four-Domain Architecture** | Spec Pro → Solution Pro → Ship Pro → Research Pro |
| **Multi-Agent Pipeline** | 10-Stage (Solution) + 5-Agent (Ship) pipelines with parallel workers and quality gates |
| **Pydantic Contract Cage** | Pydantic 模型 = 唯一真相源，Schema/Gate/Prompt 自动对齐 |
| **Quality Gates** | Harness 2.0.0: Completeness / Necessity / Target Consistency / Global Impact + REQ-ID 追踪 |
| **Living Spec Handoff** | Spec Pro → Solution Pro → Ship Pro 无缝交接 |
| **Single Execution Engine** | `run_ship_pro()` 为唯一入口（Ship Pro 2.0.0 单入口架构） |
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
│  • Ship Pro (交付编译) ← 2.0.0 新增        │
│  • Research Pro (深度研究)                │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│      Pydantic Contract Cage Layer        │  ← 2.0.0 新增
│  contracts/architect.py (ArchitectOutput)│
│  contracts/packager.py  (ShipPackage)    │
│  contracts/pipeline_state.py (State)     │
│  contracts/generator.py  (Schema/Gate)   │
└──────────────────────────────────────────┘
```

**Key Components**:
- **MasterOrchestrator** (`core/master_orchestrator.py`): Main entry point for all domains
- **ModuleOrchestrator** (`core/module_orchestrator_base.py`): Base class for domain orchestrators
- **Three-Layer Separation**: MasterOrchestrator → ModuleOrchestrator → Workers

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

详见 [domains/solution_pro/SKILL.md](domains/solution_pro/SKILL.md)

### Ship Pro (交付编译)

```python
# Ship Pro 2.0.0 单入口架构
from domains.ship_pro import run_ship_pro
result = run_ship_pro(project_name="你的项目")
# Main Agent spawn Orchestrator → 全权调度
```

详见 [domains/ship_pro/SKILL.md](domains/ship_pro/SKILL.md)

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
│   ├── solution_pro/          # Solution Pro (方案设计引擎)
│   │   ├── prompts/           # Worker prompts (planner/researcher/reviewer/...)
│   │   ├── orchestrator_agent.py
│   │   ├── task_builder.py
│   │   └── SKILL.md           # Agent execution guide
│   ├── ship_pro/              # Ship Pro 2.0.0 (交付编译引擎) ← 新增
│   │   ├── contracts/         # Pydantic 契约模型 (唯一真相源)
│   │   │   ├── architect.py   # ArchitectOutput
│   │   │   ├── packager.py    # ShipPackage
│   │   │   ├── pipeline_state.py # PipelineState
│   │   │   └── generator.py   # Schema/Gate 自动生成
│   │   ├── scripts/
│   │   │   ├── __init__.py     # 唯一入口: run_ship_pro()
│   │   │   └── orchestrator.py # ⚠️ DEPRECATED
│   │   ├── prompts/           # 5 Agent prompt 模板
│   │   ├── eval/              # 质量门禁 (gates.py)
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
├── skills/                    # OpenClaw Skill 入口（用户触发）
│   ├── spec-pro/              # /spec-pro 触发入口
│   ├── solution-pro/          # /solution-pro 触发入口
│   ├── research-pro/          # /research-pro 触发入口
│   └── ...                    # 80+ 扩展 skills
├── blackboard/                # Runtime data (not versioned)
├── README.md                  # This file
├── QUICKSTART.md              # 5 分钟上手指南
├── CHANGELOG.md               # Change log
├── SKILL.md                   # DeepFlow skill definition
└── .gitignore                 # Git ignore rules
```

---

## `domains/` vs `skills/` — 两个目录的关系

DeepFlow 有两个容易混淆的目录，职责完全不同：

| 目录 | 面向 | 内容 | 类比 |
|------|------|------|------|
| `domains/` | AI Agent 内部 | Python 代码 + 执行指南 + 配置 | **引擎** |
| `skills/` | OpenClaw 用户 | 触发入口 (`/命令`) + 使用说明 | **方向盘** |

**用户在 `skills/` 里触发 → AI 读取 `domains/` 里的代码来执行。**

例如：
- 用户输入 `/research-pro` → 触发 `skills/research-pro/SKILL.md`
- AI 读取 `domains/research_pro/SKILL.md`（执行指南）
- AI 调用 `domains/research_pro/orchestrator.py`（代码）

> ⚠️ `domains/` 和 `skills/` 下都有 `SKILL.md`，但内容完全不同：
> - `skills/xxx/SKILL.md` = 用户触发入口（含 `triggers:` 字段）
> - `domains/xxx/SKILL.md` = AI 内部执行指南（Step 1-2-3 流程）

---

## Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](docs/guides/QUICKSTART.md) | 🚀 **5 分钟上手指南（新用户必看）** |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Complete architecture design |
| [Spec Pro](domains/spec_pro/_overview.md) | Spec Pro execution guide |
| [Solution Pro](domains/solution_pro/SKILL.md) | Solution Pro execution guide |
| [Ship Pro](domains/ship_pro/SKILL.md) | Ship Pro 2.0.0 execution guide |
| [Research Pro](domains/research_pro/README.md) | Research Pro module overview |
| [Spec → Solution Contract](contracts/integration/spec_to_solution.md) | Living Spec handoff contract |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Version History

See [CHANGELOG.md](CHANGELOG.md)

---

## Development Standards

- [docs/archive/DEVELOPMENT_RULES.md](docs/archive/DEVELOPMENT_RULES.md)
- [docs/archive/CODING_STANDARDS.md](docs/archive/CODING_STANDARDS.md)
