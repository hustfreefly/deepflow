# DeepFlow 架构设计说明

> **文档版本**: 1.1  
> **日期**: 2026-04-24  
> **作者**: 姬忠礼  
> **状态**: 基于 V3.0 蓝图的投资分析场景适配

---

## 📋 文档目的

本文档说明 DeepFlow 的架构设计演进：
1. **原始蓝图设计（V3.0）**：配置驱动声明式多 Agent 协作平台
2. **当前实现（V4.0 / 0.1.0）**：针对投资分析场景的适配与取舍
3. **差异分析**：客观对比 V3.0 设计与 V4.0 实现的偏差

**参考文档**：
- `docs/deepdive_ARCHITECTURE_DESIGN_FINAL_COMPLETE.md` — V3.0 完整架构设计（37KB）
- `docs/deepdive_ARCHITECTURE_FINAL_REPORT.md` — V3.0 架构最终报告（43KB）

---

## 第一部分：原始蓝图设计（Deep Dive V3.0）

### 1.1 设计背景

**日期**: 2026-04-11  
**来源**: `memory/cold/projects/deep-dive-v3.0-architecture-final-2026-04-11/`  
**目标**: 构建配置驱动的声明式多 Agent 协作平台，加一个领域 = 加一份 YAML 配置（80% 场景）。

**设计哲学**:
> **"配置驱动，声明编排，智能控制反转，渐进交付，可观测优先，四层容错"**

**核心定位**: 从硬编码管线转变为配置驱动的声明式多 Agent 协作平台。

### 1.2 核心架构（三层架构）

```
┌─────────────────────────────────────────────────────────────────┐
│                    配置层（Configuration Layer）                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │   domains/  │ │  pipelines/ │ │   prompts/  │               │
│  │   *.yaml    │ │   *.yaml    │ │   *.md      │               │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
└────────────────────────────┬────────────────────────────────────┘
                             │声明式加载
┌────────────────────────────▼────────────────────────────────────┐
│                    运行时层（Runtime Layer）                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              PipelineEngine（Python ~300行）              │ │
│  │   Stage调度 │ Convergence │ Quality │ Checkpoint          │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │   iterative │ │    audit    │ │    gated    │              │
│  │    管线     │ │    管线     │ │    管线     │              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
└────────────────────────────┬────────────────────────────────────┘
                             │sessions_spawn
┌────────────────────────────▼────────────────────────────────────┐
│                    平台层（Platform Layer）                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ planner ││researcher││ auditor ││ fixer   ││summarizer│   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           Blackboard（文件共享 + shared_state）         │   │
│  │   ~/.openclaw/workspace/.v3/blackboard/{session_id}/   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 核心机制

| 机制 | 说明 | 目的 |
|:---|:---|:---|
| **PipelineEngine** | YAML 声明式 + 轻量 Python 引擎 | 兼顾灵活性与可维护性 |
| **IntentParser** | 自动解析用户意图 → DomainConfig | 自动匹配领域配置 |
| **PipelineSelector** | 选择管线模板（iterative/audit/gated） | 覆盖 6 大应用场景 |
| **质量门禁** | `QualityAssessor` 多维度评分 | 确保每阶段输出质量达标 |
| **收敛检测** | `ConvergenceChecker` 边际收益检测 | 自动迭代优化 |
| **渐进交付** | 30s/2min/8min/30min 分层 | 解决用户耐心上限 |
| **检查点** | `CheckpointManager` 每阶段保存 | 支持断点续传和故障恢复 |
| **故障隔离** | L1-L4 四层防护（Agent→Stage→Pipeline→System） | 生产级容错 |
| **人机回环** | HITL 门控节点（仅 gated 管线） | 关键决策点人工确认 |

### 1.4 设计哲学

> **"框架层通用，应用层垂直"**

**五大设计原则**:
1. **配置驱动**：80%场景纯YAML配置，20%复杂场景可扩展
2. **向后兼容**：现有4领域100%不损坏，自动化迁移零成本
3. **渐进交付**：洋葱式分层，用户可控，耐心上限管理
4. **故障隔离**：单Agent失败不影响全局，L1-L4四层防护
5. **可观测优先**：Phase 1纳入日志/指标/追踪，非事后补充

**Intelligent Inversion of Control**:
- 传统命令式：`代码 → 调用Agent → 等待结果 → 处理结果`
- V3.0声明式：`YAML声明期望状态 → PipelineEngine协调 → Agent自报告状态 → 自动状态转换`

### 1.5 FSM 状态机

```
                    ┌─────────────┐
         ┌─────────│   FAILED    │◄──── 任何状态异常/超时
         │         └──────┬──────┘      或L1-L4故障无法恢复
         │                │
         │                │ 恢复（从Checkpoint）
         ▼                ▼
┌──────────┐    ┌─────────────┐    ┌─────────────┐
│   INIT   │───►│  PLANNING   │───►│  EXECUTING  │
└──────────┘    └─────────────┘    └──────┬──────┘
                                          │
                                          ▼
┌──────────┐    ┌─────────────┐    ┌─────────────┐
│   DONE   │◄───│  DELIVERING │◄───│  CHECKING   │
└──────────┘    └──────┬──────┘    └──────┬──────┘
                       │        未收敛    │ 已收敛
                       │            ┌────┘
                       │            ▼
                       │    ┌─────────────┐
                       └────│   FIXING    │
                            └─────────────┘
                                          │
                                          ▼
                            ┌─────────────┐
                            │   HITL      │◄──── gated管线特有
                            │ 人工干预     │      人工确认/拒绝
                            └─────────────┘
```

### 1.6 渐进交付设计

```
T+30s   → 🚀 快速预览（意图解析结果 + 执行计划大纲 + 预估总时间）
T+2min  → 📄 初稿（核心框架/结构 + 关键发现Top 3 + 置信度评估）
T+8min  → 📊 完整报告（详细分析 + 多角度论证 + 可执行建议）
T+30min → 🔬 深度研究（全面覆盖 + 证据链完整 + 风险模拟）
[超时未完成的进入异步执行，完成后飞书推送通知]
```

---

## 第二部分：当前实现（DeepFlow V4.0 / 0.1.0）

### 2.1 实现背景

**日期**: 2026-04-24  
**版本**: 0.1.0（内部代号 V4.0）
**目标**: 将 V3.0 蓝图适配到"投资分析"垂直场景，快速验证端到端可行性。

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

| 维度 | Deep Dive V3.0（蓝图） | DeepFlow V4.0（实现） | 偏差说明 |
|:---|:---|:---|:---|
| **Orchestrator 实现** | `PipelineEngine` Python 类（~300行） | Agent 指南文本（`orchestrator_agent.py`） | 🔴 核心偏差：代码控制 → LLM 自主 |
| **质量门禁** | `QualityAssessor` 多维度评分（强制） | **无** | 🔴 缺失：无收敛检测 |
| **收敛检测** | `ConvergenceChecker` 边际收益检测 | **无** | 🔴 缺失：无自动迭代 |
| **渐进交付** | 30s/2min/8min/30min 分层 | 单一最终报告 | 🟡 用户体验差距 |
| **检查点恢复** | `CheckpointManager` 每阶段保存 | **无** | 🟡 故障后需重做 |
| **意图解析** | `IntentParser` 自动识别领域/深度 | 手动参数传递 | 🟡 灵活性降低 |
| **管线模板** | 3种模板（iterative/audit/gated） | 单一硬编码流程 | 🟡 无法复用 |
| **状态机** | FSM平铺结构（Task级+Stage级） | **无** | 🟡 状态不可追踪 |
| **故障隔离** | L1-L4 四层防护矩阵 | Worker失败不阻断管线 | 🟢 等效：实现方式不同 |
| **配置体系** | 完整 YAML Schema（领域/Agent/质量/收敛） | `domains/` 目录（部分配置） | 🟡 简化：无通用模板层 |

### 3.2 设计理念差异

#### 蓝图设计（V3.0）："配置驱动声明式编排"
```python
# V3.0：PipelineEngine 是 Python 类，FSM驱动状态流转
class PipelineEngine:
    def execute(self, blackboard: Blackboard) -> ExecutionResult:
        while self.state not in [DONE, FAILED]:
            stage_config = self.get_current_stage()
            result = self.execute_stage(stage_config, blackboard)
            self.state = self.transition(self.state, result)
            
            # 质量评估
            scores = QualityAssessor.assess(stage_output)
            if not scores.passed:
                self.state = FIXING
            
            # 收敛检测
            converged = ConvergenceChecker.check(scores)
            if converged:
                self.state = DELIVERING
            
            CheckpointManager.save(blackboard)
```

#### 当前实现（V4.0）："LLM 自主调度"
```python
# V4.0：Orchestrator 是 Agent 指南文本
# Agent 读取指南后，自主决定 spawn 哪些 Workers
# 无代码级质量门禁，无自动迭代，无检查点恢复
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

- [ ] **对齐 V3.0 设计**：将 Orchestrator 从 Agent 指南改为 `PipelineEngine` Python 类
- [ ] **质量门禁接入**：引入 `QualityAssessor` 模块（V3.0 设计已完整）
- [ ] **收敛检测机制**：`ConvergenceChecker` + `max_iterations` 自动迭代
- [ ] **检查点恢复**：`CheckpointManager` 每阶段保存，支持断点续传
- [ ] **渐进交付**：30s/2min/8min 分层返回，非单一最终报告
- [ ] **配置体系完善**：通用模板 + 领域 YAML 配置

### 4.3 长期（1.0.0）

- [ ] **完全对齐通用框架**：`MultiAgentOrchestrator` + `Workflow` + `AgentTask`
- [ ] **多领域支持**：投资、代码审查、研究报告等
- [ ] **可视化**：管线执行可视化、质量分数追踪

---

## 附录

### A. 相关文档索引

| 文档 | 位置 | 说明 |
|:---|:---|:---|
| **V3.0 架构设计最终版** | `docs/deepdive_ARCHITECTURE_DESIGN_FINAL_COMPLETE.md` | V3.0 完整架构设计（37KB） |
| **V3.0 架构最终报告** | `docs/deepdive_ARCHITECTURE_FINAL_REPORT.md` | V3.0 架构论证报告（43KB） |
| V3.0 架构图 | `~/.openclaw/canvas/v3-architecture-diagram.html` | 交互式架构图（6张核心图） |
| V1 蓝图 | `.deepflow/V1_BLUEPRINT.md` | 早期架构设计 |
| V4 架构计划 | `.deepflow/docs/V4_ARCHITECTURE_PLAN.md` | V4 重构方案 |
| 开发规范 | `.deepflow/DEVELOPMENT_RULES.md` | 契约笼子规范 |

### B. 版本对照表

| 版本 | 日期 | 定位 | Orchestrator | 质量门禁 | 收敛检测 | 渐进交付 | 检查点 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Deep Dive V3.0** | **2026-04-11** | **通用平台** | **PipelineEngine 类** | **✅ 多维度** | **✅ 边际收益** | **✅ 分层** | **✅ 每阶段** |
| V1 蓝图 | 2026-04-18 | 投资场景 | Python 类（设计） | ✅（设计） | ⚠️（设计） | ❌ | ⚠️（设计） |
| V3 协议 | 2026-04-15 | 投资场景 | Coordinator 类 | ✅（设计） | ⚠️（设计） | ⚠️（设计） | ⚠️（设计） |
| **DeepFlow V4.0** | **2026-04-24** | **投资场景** | **Agent 指南** | **❌** | **❌** | **❌** | **❌** |

---

*本文档客观记录 DeepFlow 的架构演进：以 Deep Dive V3.0 为蓝图基准，承认当前 V4.0 实现与蓝图的偏差，并为未来对齐提供路线图。*
