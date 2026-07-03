# Ship Pro V6 — AI Native 架构设计

> **版本**: 6.0.0 | **日期**: 2026-07-03 | **状态**: 设计定稿  
> **依赖**: Solution Pro `final_solution.json`（唯一输入源）

---

## 1. 核心定位

> **Solution Pro 产出"做什么+为什么做"，Ship Pro 产出"怎么拆+怎么交付"。**

Ship Pro 是通用的"方案→可执行交付物"转化引擎。不关心上游是什么领域，只关心：拿到一份结构化方案后，怎么把它变成一组可执行、可追踪、可验证的工作包。

### 泛化场景

| 场景 | Solution Pro 输出 | Ship Pro 交付物 |
|------|------------------|----------------|
| 工程项目 | 架构方案 + UC 约束 | WP + AC + 依赖图 + 交付清单 |
| 研究项目 | 研究维度 + 分析框架 | 调研任务 + 数据源清单 + 报告模板 |
| 投资分析 | 评估维度 + 方法论 | 检查清单 + 数据采集任务 + 报告结构 |

---

## 2. 设计原则（优先级排序）

| 优先级 | 原则 | 说明 |
|--------|------|------|
| **P0** | AI Native | LLM 做语义决策，代码做确定性执行 |
| **P1** | 高质量输出 | 固定 Harness + LLM 语义验证双层保障 |
| **P2** | 泛化能力 | 换任何 Solution Pro 输出都能处理 |

---

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Ship Pro V6 AI Native                          │
│                                                                   │
│  输入: Solution Pro final_solution.json（唯一输入源）              │
│  原则: AI Native > 高质量 > 泛化                                 │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 1: Planner（规划，全动态）                         │     │
│  │                                                           │     │
│  │  Input Analyzer (LLM):                                   │     │
│  │  - 分析输入类型 + 复杂度 + 领域                          │     │
│  │  - 规划拆解策略（几个角色？什么依赖？什么格式？）         │     │
│  │  - 决定哪些角色需要 web search（转化执行级搜索）          │     │
│  │  - 输出: PlannerOutput（结构化 JSON，含 WorkerSpec 列表） │     │
│  └─────────────────────────────────────────────────────────┘     │
│                            ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 2: Build（拆解执行，全动态）                       │     │
│  │                                                           │     │
│  │  Orchestrator (固定编排器):                              │     │
│  │  - 读取 PlannerOutput 中的 WorkerSpec 列表               │     │
│  │  - 程序化拼接 Worker Prompt（WorkerSpec + 约束笼子模板）  │     │
│  │  - 动态 spawn Agent × N（2 ≤ N ≤ 8）                    │     │
│  │  - 部分 Agent 获得 web_search 权限（Phase 1 决定）       │     │
│  │  - spawn → yield → gate → next 循环                     │     │
│  └─────────────────────────────────────────────────────────┘     │
│                            ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 3: Shipper（交付整合，半固定）                     │     │
│  │                                                           │     │
│  │  动态层 (LLM):                                           │     │
│  │  ├── Meta Shipper: 规划整合策略                          │     │
│  │  └── Consolidator: 合并产出，解决冲突                     │     │
│  │                                                           │     │
│  │  固定层 (确定性验证，每次必须跑):                         │     │
│  │  ├── Pydantic Gate: Schema 格式验证                      │     │
│  │  ├── 信息守恒检查: MUST 约束保留率                       │     │
│  │  ├── 完整性检查: 需求 → 产出 全覆盖                      │     │
│  │  └── Harness V3: AC 质量 + 依赖合理性 + 可操作性         │     │
│  │                                                           │     │
│  │  Gate 结果:                                              │     │
│  │  → PASS → 最终交付                                      │     │
│  │  → FAIL → Fix Agent 定向修复 → 重跑 Phase 3            │     │
│  └─────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 与 Solution Pro 的结构对应

| Solution Pro | Ship Pro V6 | 同构点 |
|-------------|-------------|--------|
| Planning (Meta-Planner + Experts) | Phase 1 Planner | LLM 规划，动态 Agent |
| Research (Experts × N + web_search) | Phase 2 Build | 动态 spawn，部分 Agent 有搜索权限 |
| Summary (Base + Analyzer + Summarizer) | Phase 3 Shipper | LLM 整合 + 固定 Harness |
| ModuleOrchestrator (固定编排) | ShipOrchestrator (固定编排) | 同构的编排器基类 |
| Blackboard + StateManager | Blackboard + StateManager | 复用 |
| _shared_subagent_rules | _shared_subagent_rules | 复用 |

---

## 5. 关键设计决策

### D1: Planner 输出必须结构化（Pydantic Schema）

Planner 不直接生成 Worker Prompt，而是输出 **PlannerOutput**（结构化 JSON）。Orchestrator 根据 PlannerOutput + 约束笼子模板 **程序化拼接** Worker Prompt。

**理由**: LLM 直接生成完整 Prompt 的解析可靠性只有 ~80%，结构化输出 + 程序化拼接可达 ~99%。

### D2: 输入契约严格（只接受 final_solution.json）

Ship Pro 只接受 Solution Pro 的 `final_solution.json`，不接受任意格式。

**理由**: 严格契约保证信息守恒，避免 LLM 自由发挥导致质量失控。

### D3: Web Search 聚焦"转化执行"

Ship Pro 的 web search 是 **转化执行性质**（搜索实施细节），不是 **研究性质**（搜索领域知识）。

| 搜索目的 | 例子 |
|---------|------|
| 拆解 WP 时搜索技术栈实践 | "Python asyncio 并发模型最佳实践" |
| 写 AC 时搜索可量化标准 | "API 性能基准测试标准" |
| 依赖分析时搜索兼容性 | "Pydantic v2 与 FastAPI 版本兼容性" |

### D4: Worker 数量上限控制

Worker 数量上限 `MAX_WORKERS = 8`，超过时 Planner 必须合并角色。

**理由**: 避免 API 并发限制、总超时不可控、Token 消耗爆炸。

### D5: 复用 V5 Pydantic 模型

Phase 3 最终输出复用 `ShipPackage`（或 `ShipPackageExtras`），减少 Schema 设计工作。

### D6: Optional Suggestion 物理隔离

LLM 想加的额外建议存储在 `ship_package.metadata.optional_suggestions`，与主交付物物理隔离。Summarizer 禁止读取该字段。

---

## 6. 发散风险控制

### 风险来源

| 阶段 | 风险 | 严重性 |
|------|------|--------|
| Phase 1 Planner | LLM 过度分析任务类型，讨论"该不该拆" | 中高 |
| Phase 2 Workers | LLM 在写 AC 时讨论架构设计 | 低 |
| Phase 3 Shipper | LLM 在汇总时加入不必要的"建议" | 低 |

### 三层约束笼子

**约束 1: 任务边界约束**
- Ship Pro 只做"拆解 + 交付"，不做"设计 + 决策"
- Solution Pro 没说的不补充，说了的不修改

**约束 2: 角色边界约束**
- Planner: 只规划"怎么拆"，不讨论"该不该拆"
- Workers: 只生成"交付物"，不讨论"方案优劣"
- Shipper: 只汇总"已有产出"，不补充"新内容"

**约束 3: 输出边界约束**
- 每个阶段输出必须符合 Pydantic Schema
- Schema 没有的字段不能自由发挥
- 额外内容必须标记为 `optional_suggestion`

### Planner Gate（重点加固）

```
Planner 产出必须通过 Gate:
  1. Agent 数量: 2 ≤ N ≤ 8（硬约束）
  2. 角色名称: 必须在允许列表内或 LLM 自定义但说明理由
  3. 依赖图: 无环检测（代码确定性检查）
  4. Prompt 引用: 每个 WorkerSpec 必须引用 Solution Pro 的具体字段
  5. web_search 分配: 必须说明理由（"为什么这个角色需要搜索？"）
```

---

## 7. 实现估算

| 阶段 | 工作内容 | 人天 |
|------|---------|------|
| Phase 1 Planner | Pydantic Schema + Prompt + 解析 | 2 |
| Phase 2 Build | Worker 引擎 + Prompt 组装 + search | 1.5 |
| Phase 3 Shipper | 4 层验证 + Fix Agent | 2.5 |
| Orchestrator | ShipOrchestrator + state + checkpoint | 1 |
| Schema | PlannerOutput + WorkerDeliverable | 1 |
| 测试 | L1 单元 + L2 集成 + fixture | 1.5 |
| **总计** | | **9.5** |

**关键路径**: Phase 1 Planner Schema → Phase 2 Worker Prompt 模板 → Phase 3 信息守恒检查

---

## 8. Solution Pro V2 经验教训追溯

> 以下每条教训都已在设计中有明确对应，确保不重复犯错。

| # | Solution Pro 教训 | 严重性 | Ship Pro V6 设计对应 |
|---|------------------|--------|-------------------|
| S1 | stage_progress 缺失 | 🔴 | Orchestrator 统一管理 PipelineStateManager，每个 stage 完成时自动写入 |
| S2 | convergence 未聚合 | 🟡 | Phase 3 Shipper 整合所有 Worker 产出，输出统一的 ship_package |
| S3 | 状态写入不统一 | 🟡 | Orchestrator 是唯一状态写入入口，Worker 只写自己的 stage |
| S5 | 无 state machine | 🟡 | convergence_design.md 定义了合法状态转换路径，非法转换 raise Error |
| D1-D4 | Blackboard 格式混乱 | 🔴 | 代码层 read_json() 已修复 + Worker prompt 模板注入类型检查规则 |
| A1-A4 | Agent 编码质量 | 🟡 | Worker prompt 模板统一注入防御性编码规则 + web_search 失败策略 |
| I1-I3 | 信息守恒失效 | 🔴 | Phase 3 四层 Gate（Pydantic + 信息守恒 + 完整性 + Harness）+ 独立 Harness Judge |
| M1 | spawn 不是 Python 函数 | 🔴 | Orchestrator 铁律 1：sessions_spawn 是 Agent tool，禁止 Python import |
| M2 | Subagent 不知受限 | 🟡 | Worker prompt 注入禁止操作清单（cron main/sessions_list/PYTHONPATH） |
| M3 | yield 后生成文字 | 🔴 | Orchestrator 铁律 2：yield 唤醒后第一个 action 必须是 exec |
| G1 | 运动员=裁判 | 🔴 | Harness Judge 独立于 Workers，使用不同 prompt + 独立 session |
| G2 | Planner 输出解析脆弱 | 🟡 | PlannerOutput 结构化 Pydantic Schema，Orchestrator 程序化拼接 Prompt |

---

## 9. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V6.0 | 2026-07-03 | AI Native 架构设计（全动态 + 约束笼子） |
| V5.0 | 2026-06-28 | Phase 1+2 多 Agent（未完成） |
| V4.0 | 2026-06-26 | Generator + Judge 两阶段闭环 |
| V3.2 | 2026-06-23 | Pydantic 契约笼子 + CLI 引擎 |
| V2.0 | 2026-06-15 | LLM 引导 + 确定性编译 + 质量门禁 |
