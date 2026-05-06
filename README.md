# DeepFlow

> ⚠️ **平台依赖声明**:DeepFlow 当前**仅适配 OpenClaw 平台**,核心调度依赖 `sessions_spawn` / `sessions_yield` 等 OpenClaw 原生 API。暂不支持独立运行或其他 Agent 框架(如 AutoGen、LangChain、CrewAI 等)。
> **日期**: 2026-05-06
> **状态**: ✅ Phase 1 完成 + PromptRegistry 迁移完成 + Solution Pro V3.1 发布
> **版本**: 0.1.1 (V4.0 投资分析 + V3.1 方案设计)
> **定位**: 基于通用多 Agent 协作框架的垂直场景适配,支持投资分析 + 方案设计双领域

---

## 简介

DeepFlow 是一个 **多 Agent 协作自动化管线**,运行在 **OpenClaw** 平台上。

> **架构说明**: DeepFlow 的完整架构设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),包含原始蓝图(Deep Dive V3.0)与当前实现的差异分析。

### 核心能力

| 能力 | 说明 |
|------|------|
| **多 Agent 协作** | 6 Researchers + 3 Auditors + Fixer + Summarizer |
| **数据驱动** | DataManager Worker 统一采集 + 搜索 |
| **契约验证** | 契约笼子(Contract Cage)验证框架 |
| **容错设计** | Worker 失败不阻断管线 |
| **配置化** | 搜索策略、输出渠道、凭证分离配置 |

---

## 架构

### 三层架构(V4.0)

```
┌──────────────────────────────────────────┐
│           OpenClaw 平台层                 │  ← 必需依赖
│  ┌────────────────────────────────────┐  │
│  │   sessions_spawn / sessions_yield  │  │
│  │        Agent 调度引擎               │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────┐
│           DeepFlow 管线层                 │
│  EntryHarness → PipelineOrchestrator → Workers │
│  (6 Researchers + 3 Auditors + ...)      │
└──────────────────────────────────────────┘
```

**执行链路(三层架构)**:
```
主Agent(depth-0)
  └── sessions_spawn → EntryHarness(depth-1)
        └── validate_and_start() → PipelineOrchestrator(depth-1)
              ├── sessions_spawn → DataManager Worker(depth-2)
              ├── sessions_spawn → Researchers ×6 (并行)
              ├── sessions_spawn → Auditors ×3 (并行)
              ├── sessions_spawn → Fixer Worker
              └── sessions_spawn → Summarizer Worker
```

**新组件**:
- **EntryHarness** (`core/entry_harness.py`): 启动验证、配置检查、生成 execution_plan
- **PipelineOrchestrator** (`core/pipeline_orchestrator.py`): 读取 execution_plan,按 phase 调度 Workers
- **三层分离**: EntryHarness 负责启动,PipelineOrchestrator 负责调度,Workers 负责执行

---

## 环境要求

| 依赖 | 版本 | 说明 |
|:---|:---|:---|
| **OpenClaw** | ≥ 2026.4.x | **必需**。核心调度依赖 OpenClaw 的 `sessions_spawn` 工具 |
| Python | 3.10+ | 运行时环境 |
| Node.js | 20+ | OpenClaw 运行时要求 |

### 为什么必须 OpenClaw?

DeepFlow 的 Orchestrator 使用 `sessions_spawn` 创建子 Agent,这是 OpenClaw 的原生工具 API。当前实现未抽象平台层,无法脱离 OpenClaw 独立运行。

### 未来计划

- **短期**:保持 OpenClaw 独占,深耕投资分析场景
- **中期**:抽象 `AgentRuntime` 接口,支持多平台适配(OpenClaw / 独立 Python / 其他框架)
- **长期**:完全解耦平台依赖,成为通用多 Agent 管线引擎

---

## 快速开始

### Investment 模块(投资分析)

```bash
# 方式一:统一入口(推荐)
python3 deepflow.py --code 688981.SH --name 中芯国际 --industry 半导体制造

# 方式二:Python API(集成使用)
from domains.investment import InvestmentOrchestrator

orch = InvestmentOrchestrator(spawn_fn=your_spawn_adapter)
result = orch.run({
    "code": "688981.SH",
    "name": "中芯国际"
})
```

### Solution Pro 模块(方案设计)

```python
from core.entry_harness import EntryHarness

# 方式一:使用 EntryHarness 启动完整管线(推荐)
harness = EntryHarness()
orchestrator = harness.validate_and_start(
    domain="solution",
    context={
        "topic": "设计一个智能物流仓储系统升级方案",
        "solution_type": "architecture",
        "constraints": ["预算500万", "周期6个月"],
        "stakeholders": ["技术团队", "财务总监"],
        "session_prefix": "智能仓储",  # ← V3 短命名
    },
    spawn_fn=your_spawn_adapter,
)
result = orchestrator.run_pipeline()

# 方式二:直接调用 SolutionOrchestratorV21(向后兼容)
from domains.solution import SolutionOrchestratorV21
import asyncio

result = await SolutionOrchestratorV21.run(
    topic="设计一个智能物流仓储系统升级方案",
    solution_type="architecture",
    constraints=["预算500万", "周期6个月"],
    stakeholders=["技术团队", "财务总监"],
    session_prefix="智能仓储",  # ← V3 短命名
    spawn_fn=your_spawn_adapter,
)
```

**新特性(V3 命名修复)**:
- ✅ **session_prefix 短命名**: 支持显式传入前缀,避免超长 session_id
- ✅ **三层架构**: EntryHarness → PipelineOrchestrator → Workers
- ✅ **Harness V2 质量门控**: 中期检查(Reviewers)+ 最终把关(Harness Final)
- ✅ **Layer 2 约束验证**: Planning 动态生成约束,Researcher 显式验证
- ✅ **10阶段完整闭环**: Data Collection → Planning → Reviewers → Research → Consolidator → Audit → Fix → Harness Final → Summarizer

**session_id 格式**:
- 有前缀: `{prefix}_{type}_{hash8}`(如 `智能仓储_architecture_a1b2c3d4`)
- 无前缀: `{topic前20字}_{type}_{hash8}`
- 确保长度 ≤ 50 字符

详见 [docs/SOLUTION_PRO_MODE_DESIGN.md](docs/SOLUTION_PRO_MODE_DESIGN.md)

### 强制重新分析

```bash
python3 deepflow.py --code 688981.SH --name 中芯国际 --force-rebuild
```

---

## 项目结构

```
.deepflow/
├── core/                      # 核心模块
│   ├── master_agent.py        # Master Agent
│   ├── task_builder.py        # Task Builder
│   ├── data_manager_worker.py # DataManager
│   ├── search_engine.py       # 统一搜索接口
│   ├── config_loader.py       # 配置加载器
│   ├── blackboard_manager.py  # Blackboard
│   ├── pipeline_orchestrator.py  # ← Pipeline Orchestrator(depth-1)
│   ├── entry_harness.py       # ← Entry/Startup Harness
│   └── unified_entry.py       # 统一入口(使用 EntryHarness)
├── domains/                   # 领域适配
│   ├── investment/            # 投资分析领域
│   └── solution/              # 方案设计领域(Solution Pro)
├── data/                      # 配置文件
│   ├── search_config.yaml     # 搜索配置
│   ├── output_config.yaml     # 输出配置
│   └── credentials.yaml       # 凭证配置
├── cage/                      # 契约笼子
├── data_sources/              # 数据源配置
├── data_providers/            # 数据源提供者
├── docs/                      # 架构文档
│   └── ARCHITECTURE.md        # 架构设计说明
├── prompts/                   # Prompt 模板
└── orchestrator_agent.py      # Orchestrator 指南
```

## 架构文档

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 完整架构设计说明（蓝图 vs 实现）
- [docs/SOLUTION_PRO_MODE_DESIGN.md](docs/SOLUTION_PRO_MODE_DESIGN.md) — Solution Pro 详细设计
- [docs/SOLUTION_MODULE_DESIGN.md](docs/SOLUTION_MODULE_DESIGN.md) — Solution 模块架构
- [docs/configuration.md](docs/configuration.md) — 用户配置文档
- [docs/STANDARD_EXECUTION.md](docs/STANDARD_EXECUTION.md) — 投资分析标准执行流程
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — 快速开始指南
- [docs/harness_architecture_v2_final.md](docs/harness_architecture_v2_final.md) — Harness V2 质量门禁设计
- [docs/PATH_DESIGN_SPEC.md](docs/PATH_DESIGN_SPEC.md) — PathConfig 路径管理规范
- [docs/CAGE_PREREQUISITE_BANS.md](docs/CAGE_PREREQUISITE_BANS.md) — 契约笼子前置禁令（**强制必读**）

---

## 版本历史

见 [CHANGELOG.md](CHANGELOG.md)

---

## 开发规范

见 [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) 和 [CODING_STANDARDS.md](CODING_STANDARDS.md)
