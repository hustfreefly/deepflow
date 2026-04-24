# DeepFlow

> ⚠️ **平台依赖声明**：DeepFlow 当前**仅适配 OpenClaw 平台**，核心调度依赖 `sessions_spawn` / `sessions_yield` 等 OpenClaw 原生 API。暂不支持独立运行或其他 Agent 框架（如 AutoGen、LangChain、CrewAI 等）。
>
> **版本**: 0.1.0 (V4.0 内部代号)  
> **日期**: 2026-04-24  
> **状态**: ✅ Phase 1 完成  
> **定位**: 基于通用多 Agent 协作框架的垂直场景适配，当前重点适配投资分析场景

---

## 简介

DeepFlow 是一个 **多 Agent 协作自动化管线**，运行在 **OpenClaw** 平台上。

> **架构说明**: DeepFlow 的完整架构设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，包含原始蓝图（Deep Dive V3.0）与当前实现的差异分析。

### 核心能力

| 能力 | 说明 |
|------|------|
| **多 Agent 协作** | 6 Researchers + 3 Auditors + Fixer + Summarizer |
| **数据驱动** | DataManager Worker 统一采集 + 搜索 |
| **契约验证** | 契约笼子（Contract Cage）验证框架 |
| **容错设计** | Worker 失败不阻断管线 |
| **配置化** | 搜索策略、输出渠道、凭证分离配置 |

---

## 架构

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
│  Master Agent → Orchestrator → Workers   │
│  (6 Researchers + 3 Auditors + ...)      │
└──────────────────────────────────────────┘
```

**执行链路**:
```
主Agent(depth-0)
  └── sessions_spawn → Orchestrator Agent(depth-1)
        ├── sessions_spawn → DataManager Worker(depth-2)
        ├── sessions_spawn → Researchers ×6 (并行)
        ├── sessions_spawn → Auditors ×3 (并行)
        ├── sessions_spawn → Fixer Worker
        └── sessions_spawn → Summarizer Worker
```

---

## 环境要求

| 依赖 | 版本 | 说明 |
|:---|:---|:---|
| **OpenClaw** | ≥ 2026.4.x | **必需**。核心调度依赖 OpenClaw 的 `sessions_spawn` 工具 |
| Python | 3.10+ | 运行时环境 |
| Node.js | 20+ | OpenClaw 运行时要求 |

### 为什么必须 OpenClaw？

DeepFlow 的 Orchestrator 使用 `sessions_spawn` 创建子 Agent，这是 OpenClaw 的原生工具 API。当前实现未抽象平台层，无法脱离 OpenClaw 独立运行。

### 未来计划

- **短期**：保持 OpenClaw 独占，深耕投资分析场景
- **中期**：抽象 `AgentRuntime` 接口，支持多平台适配（OpenClaw / 独立 Python / 其他框架）
- **长期**：完全解耦平台依赖，成为通用多 Agent 管线引擎

---

## 快速开始

### 方式一：统一入口（推荐）

```bash
# 一键初始化并生成调用指令
python3 deepflow.py --code 688981.SH --name 中芯国际 --industry 半导体制造

# 输出 JSON 包含 session_id 和 sessions_spawn 调用参数
# 主 Agent 解析后执行 sessions_spawn + sessions_yield
```

### 方式二：分步执行（保留）

```bash
# Step 1: 初始化
python3 core/master_agent.py --code 688981.SH --name 中芯国际

# Step 2: 手动 spawn Orchestrator（主 Agent 执行）
# 读取 blackboard/{session_id}/orchestrator_task.txt
# sessions_spawn(...)
# sessions_yield()
```

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
│   └── blackboard_manager.py  # Blackboard
├── domains/                   # 领域适配（当前：investment）
│   └── investment/
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
- [docs/configuration.md](docs/configuration.md) — 用户配置文档
- [docs/STANDARD_EXECUTION.md](docs/STANDARD_EXECUTION.md) — 标准执行流程

---

## 版本历史

见 [CHANGELOG.md](CHANGELOG.md)

---

## 开发规范

见 [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) 和 [CODING_STANDARDS.md](CODING_STANDARDS.md)
