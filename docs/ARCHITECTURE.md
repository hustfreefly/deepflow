# DeepFlow 架构设计说明

> **文档版本**: 1.0  
> **日期**: 2026-04-24  
> **作者**: 姬忠礼  
> **状态**: 基于通用框架的垂直场景适配

---

## 📋 文档目的

本文档说明 DeepFlow 的架构设计演进：
1. **原始蓝图设计**：通用多 Agent 协作框架的设计理念
2. **当前实现（0.1.0）**：针对投资分析场景的适配与取舍
3. **差异分析**：客观对比设计与实现的偏差

---

## 第一部分：原始蓝图设计（通用多 Agent 协作框架）

### 1.1 设计背景

**日期**: 2026-03-14  
**位置**: `~/.openclaw/workspace/.multi-agent-framework/`  
**目标**: 构建通用的多 Agent 协作工作流框架，不限定于任何垂直领域。

### 1.2 核心架构

```
┌─────────────────────────────────────────────┐
│         多 Agent 协作框架（通用层）           │
│  ┌──────────────────────────────────────┐   │
│  │   MultiAgentOrchestrator（协调器）    │   │
│  │   - Python 类，代码控制流程           │   │
│  │   - 顺序/并行执行模式                 │   │
│  │   - 质量门禁（quality_gate）          │   │
│  │   - 迭代重试（max_iterations）        │   │
│  └──────────────────────────────────────┘   │
│                    │                        │
│     ┌──────────────┼──────────────┐         │
│     ▼              ▼              ▼         │
│  ┌──────┐    ┌──────┐    ┌──────┐         │
│  │Workflow│   │AgentTask│  │Template│       │
│  └──────┘    └──────┘    └──────┘         │
│     │              │              │         │
│     ▼              ▼              ▼         │
│  ┌────────┐  ┌────────┐  ┌────────┐       │
│  │顺序执行 │  │质量门禁 │  │预定义   │       │
│  │并行执行 │  │迭代重试 │  │工作流   │       │
│  └────────┘  └────────┘  └────────┘       │
└─────────────────────────────────────────────┘
```

### 1.3 核心机制

| 机制 | 说明 | 目的 |
|:---|:---|:---|
| **Workflow** | 工作流定义（顺序/并行） | 灵活编排 Agent 执行顺序 |
| **AgentTask** | 单个任务定义（prompt、input_key、output_key） | 标准化 Agent 输入输出 |
| **质量门禁** | `quality_gate` 函数，返回 bool | 确保每阶段输出质量达标 |
| **迭代重试** | `max_iterations` 参数 | 质量不通过时自动重试 |
| **状态持久化** | JSON 状态文件 | 支持断点续传和故障恢复 |
| **模板系统** | 预定义工作流模板 | 快速复用常见模式 |

### 1.4 设计哲学

> **"框架层通用，应用层垂直"**

- **框架不负责领域知识**：框架只提供编排能力，领域逻辑由 AgentTask 的 prompt 承载。
- **代码控制优于 LLM 控制**：Orchestrator 是 Python 类，流程由代码决定，而非 LLM 自主决策。
- **质量是强制要求**：没有质量门禁，管线不能进入下一阶段。

### 1.5 示例工作流

```python
# 系统设计模板
Product（需求分析）
  → Programmer（架构设计）
  → Programmer（代码实现）
  → Auditor（质量审计，>= 8分通过）
  → [不通过则返回 Programmer 重试，最多3次]
```

---

## 第二部分：当前实现（DeepFlow 0.1.0）

### 2.1 实现背景

**日期**: 2026-04-24  
**版本**: 0.1.0  
**目标**: 将通用框架适配到"投资分析"垂直场景，快速验证端到端可行性。

### 2.2 当前架构

```
主 Agent（depth-0）
  └── sessions_spawn → Orchestrator Agent（depth-1）
        ├── 读取 tasks.json + execution_plan.json
        ├── sessions_spawn → DataManager Worker（depth-2）
        ├── sessions_spawn → Planner Worker（depth-2）
        ├── sessions_spawn → Researchers ×6（depth-2，并行）
        ├── sessions_spawn → Auditors ×3（depth-2，并行）
        ├── sessions_spawn → Fixer Worker（depth-2）
        ├── sessions_spawn → Summarizer Worker（depth-2）
        └── sessions_spawn → SendReporter Worker（depth-2）
```

### 2.3 核心组件

| 组件 | 文件 | 职责 | 状态 |
|:---|:---|:---|:---:|
| **Master Agent** | `core/master_agent.py` | 生成 session、构建 Tasks | ✅ |
| **Task Builder** | `core/task_builder.py` | 构建各 Worker Task | ✅ |
| **Orchestrator** | `orchestrator_agent.py` | Agent 指南（LLM 自主调度） | ⚠️ |
| **DataManager** | `core/data_manager_worker.py` | 数据采集 + 统一搜索 | ✅ |
| **Blackboard** | `blackboard/{session_id}/` | 文件持久化 | ✅ |
| **契约笼子** | `cage/` | 验证框架 | ✅ |

### 2.4 已验证的能力

| 能力 | 验证状态 | 说明 |
|:---|:---:|:---|
| 多 Agent 协作 | ✅ | 6 Researchers + 3 Auditors + Fixer + Summarizer |
| 数据驱动 | ✅ | DataManager 统一采集，Tushare + fallback |
| 文件持久化 | ✅ | Blackboard 文件系统 |
| 容错设计 | ✅ | Worker 失败不阻断管线 |
| 端到端报告 | ✅ | final_report.md + 飞书发送 |
| 搜索配置化 | ✅ | `search_config.yaml` + `SearchEngine` 接口 |
| 凭证安全 | ✅ | `credentials.yaml` 集中管理 |

---

## 第三部分：差异分析（蓝图 vs 实现）

### 3.1 架构层级差异

| 维度 | 通用框架（蓝图） | DeepFlow 0.1.0（实现） | 偏差说明 |
|:---|:---|:---|:---|
| **Orchestrator 实现** | Python 类（`orchestrator.py`） | Agent 指南文本（`orchestrator_agent.py`） | 🔴 核心偏差：代码控制 → LLM 自主 |
| **质量门禁** | `quality_gate` 函数（强制） | **无** | 🔴 缺失：无收敛检测 |
| **迭代重试** | `max_iterations`（自动） | **无** | 🔴 缺失：无自动重试 |
| **模板系统** | JSON 模板（通用） | `domains/` 目录（领域特定） | 🟡 简化：无通用模板层 |
| **状态持久化** | JSON 状态文件（细粒度） | Blackboard 文件（粗粒度） | 🟢 等效：实现方式不同 |
| **模块间依赖** | 零依赖 | Task Builder 依赖 DataManager | 🟡 偏离：task_builder 导入 data_manager_worker |

### 3.2 设计理念差异

#### 蓝图设计："代码控制流程"
```python
# 通用框架：Orchestrator 是 Python 类
class MultiAgentOrchestrator:
    def run(self):
        for task in self.workflow.tasks:
            result = self.execute_task(task)
            if not task.quality_gate(result):
                for _ in range(task.max_iterations):
                    result = self.retry(task)
                    if task.quality_gate(result):
                        break
```

#### 当前实现："LLM 自主调度"
```python
# DeepFlow 0.1.0：Orchestrator 是 Agent 指南
# Agent 读取指南后，自主决定 spawn 哪些 Workers
# 无代码级质量门禁，无自动迭代
```

### 3.3 取舍分析

#### ✅ 当前实现的合理之处

1. **快速验证**：跳过复杂的 Python Orchestrator 开发，用 Agent 指南快速验证端到端可行性。
2. **灵活性**：LLM 自主调度可以处理未预见的边界情况（如 Worker 失败时的动态调整）。
3. **与 OpenClaw 集成**：直接利用 `sessions_spawn` 和 `sessions_yield`，无需额外抽象层。

#### ❌ 当前实现的不足之处

1. **不可预测性**：LLM 可能复用历史数据（已发生）、跳过步骤、或错误理解指南。
2. **无质量保障**：没有 `quality_gate`，管线可能产出低质量报告。
3. **无收敛机制**：没有 `max_iterations` 和收敛检测，无法自动迭代优化。
4. **难以扩展**：新增领域需要重写 Agent 指南，而非复用模板。

---

## 第四部分：演进路线图

### 4.1 短期（0.2.0）

- [ ] **强制重建机制**：`force_rebuild` 参数（已实现）
- [ ] **质量检测**：手动检查 final_report.md 质量
- [ ] **文档对齐**：README 明确框架定位（通用 vs 投资）

### 4.2 中期（0.3.0）

- [ ] **回归 Blueprint 设计**：将 Orchestrator 从 Agent 指南改为 Python 类
- [ ] **质量门禁接入**：引入 `QualityGate` 模块（代码已存在，但未调用）
- [ ] **迭代机制**：`max_iterations` + 收敛检测
- [ ] **模板系统**：通用模板 + 领域覆盖

### 4.3 长期（1.0.0）

- [ ] **完全对齐通用框架**：`MultiAgentOrchestrator` + `Workflow` + `AgentTask`
- [ ] **多领域支持**：投资、代码审查、研究报告等
- [ ] **可视化**：管线执行可视化、质量分数追踪

---

## 附录

### A. 相关文档索引

| 文档 | 位置 | 说明 |
|:---|:---|:---|
| 通用框架 README | `~/.openclaw/workspace/.multi-agent-framework/README.md` | 原始蓝图 |
| 通用框架 Orchestrator | `~/.openclaw/workspace/.multi-agent-framework/orchestrator.py` | Python 实现 |
| V1 蓝图 | `.deepflow/V1_BLUEPRINT.md` | 早期架构设计 |
| V4 架构计划 | `.deepflow/docs/V4_ARCHITECTURE_PLAN.md` | V4 重构方案 |
| 开发规范 | `.deepflow/DEVELOPMENT_RULES.md` | 契约笼子规范 |

### B. 版本对照表

| 版本 | 日期 | 定位 | Orchestrator | 质量门禁 |
|:---:|:---:|:---:|:---:|:---:|
| 通用框架 1.0 | 2026-03-14 | 通用 | Python 类 | ✅ |
| V1 蓝图 | 2026-04-18 | 投资场景 | Python 类（设计） | ✅（设计） |
| V3 协议 | 2026-04-15 | 投资场景 | Coordinator 类 | ✅（设计） |
| **0.1.0** | **2026-04-24** | **投资场景** | **Agent 指南** | **❌** |

---

*本文档客观记录 DeepFlow 的架构演进，承认当前实现与蓝图的偏差，并为未来对齐提供路线图。*
