# 专家 2 报告：AI Agent 编排专家（业界对比视角）

> **日期**: 2026-06-18
> **角色**: AI Agent 编排系统专家
> **研究范围**: Manus / Hermes / Claude Code / Devin / OpenAI Codex / Factory.ai
> **任务**: 对比业界"方案→执行"模式，为 DeepFlow 架构重设计提供建议

---

## 一、业界 6 大 Agent 框架"方案→执行"模式对比表

| 维度 | Manus Agent | Hermes Agent | Claude Code | Devin (Cognition) | OpenAI Codex (2025-26) | Factory.ai |
|------|------------|--------------|-------------|-------------------|----------------------|------------|
| **核心范式** | Plan-driven + File-as-Truth | Iteration Budget + 三层记忆 | Agent Harness + Multi-Agent | Parallel Fleet + DeepWiki | Cloud Sandbox + Skills | Coordinator-Droid |
| **方案表示** | `todo.md` 文件（Markdown + YAML front matter） | `user.md` + `memory.md` + Skills 文件 | `CLAUDE.md` + Dynamic Workflow（JS 代码） | Playbooks（自定义 system prompt） | `SKILL.md` + 自然语言任务描述 | Linear/Jira ticket + 验收合同 |
| **任务分解方式** | Planner Module → 有序子任务序列 | Judge Model 评估 + 子 Agent 独立预算 | Plan-and-Execute：协调 Agent 分解 → 专业 Agent 执行 | DeepWiki 索引 → 拆分为可并行的独立工作单元 | 自然语言 → 自动分解 → 多 Agent 并行 | Coordinator → 拆分子任务 → 分配给专业 Droid |
| **执行模型** | CodeAct（动态写代码执行）+ 多 Agent 协作 | 90 turn 默认预算，子 Agent 50 turn 上限 | 单 Agent → 4-Agent Ultra Plan（3 Explorer + 1 Critic） | 沙盒环境（shell + editor + browser） | 云端沙盒，每个任务独立环境 | 每个 Droid 独立沙盒云环境 |
| **记忆/状态管理** | Plan 文件持久化到文件系统，注入上下文 | 三层：Durable Files → SQLite FTS5 → 外部 Provider | CLAUDE.md 持久上下文 + 上下文压缩 | DeepWiki 持续更新索引 + 文件系统即记忆 | 仓库级理解 + Skills 持久化 | Knowledge Droid 记忆层（GitHub/Notion/Slack 聚合） |
| **验证机制** | Verification Agent 独立验证 | Judge Model 每 turn 评估 | Critic Agent 评审 + 多 Explorer 对比 | 自动 PR review + CI/CD 集成 | 测试驱动（生成→运行→迭代直到通过） | 双层 TDD（Worker 级 + Mission 级验证合同） |
| **关键创新** | 文件即计划（plan as file），上下文工程 | 自改进循环（Skills 自动生成），Iteration Budget | Dynamic Workflows（计划嵌入代码），Anti-anchoring | 并行 Agent 舰队 + 深度代码库理解 | Codex Desktop 作为"Agent 指挥中心" | Agent Readiness 评估（100+ 信号） |
| **方案→执行的桥梁** | todo.md 是唯一真相源 | memory.md 是工作模型 | CLAUDE.md + 动态生成的 JS harness | Playbook 定义执行路径 | SKILL.md 定义工作流 | 验收合同定义正确性标准 |

---

## 二、对 Q1-Q4 的明确建议

### Q1: Blueprint 层是否保留？

**明确建议：选项 B — 砍掉 frozen_blueprint，Ship Pro 直接消费 final_result**

**业界依据**：

1. **Manus 的教训**：Manus 的核心创新是"文件即计划"（plan as file），但关键是——它只有**一个**文件（todo.md），不是三个。Manus 没有"living plan → frozen plan → execution plan"的三层转换。Plan 是唯一的真相源，直接注入上下文。

2. **Claude Code 的做法**：Claude Code 的 `CLAUDE.md` 是持久上下文，但它不是"方案"的三层表示。它是**一个**文件，包含构建命令、代码风格、仓库约定。执行时，Agent 直接读这个文件，不经过"freeze"步骤。

3. **DeepFlow 当前问题的根因**：frozen_blueprint 的 44.5KB 比 final_result 的 21.4KB 大了一倍，但信息量反而更少。这说明 frozen_blueprint 不是 final_result 的"浓缩"，而是"膨胀+丢失"。这是典型的**中间表示层反模式**——增加了一层抽象，既没减少复杂度，又丢了信息。

4. **Factory.ai 的双层 TDD 启示**：Factory.ai 有"Mission 级验证合同"和"Worker 级实现"两层，但 Mission 级合同是**直接从需求生成的**，不是从另一个中间格式转换的。

**结论**：frozen_blueprint 是一个**有害的中间层**。它应该被删除。Ship Pro 直接消费 final_result（最丰富的信息源），按需从中提取和重组信息。

---

### Q2: Solution Pro 应该输出什么？

**明确建议：Solution Pro 只输出一个文件——`solution.json`（即当前的 final_result 改名）**

**业界依据**：

1. **Hermes 的三层记忆原则**：Hermes 的记忆系统分为 Durable Files（持久）→ Session Search（会话级）→ External Provider（外部）。关键是：每一层有**明确的职责边界**。`user.md` 存偏好，`memory.md` 存环境上下文，Skills 存过程记忆。它们不互相重复。

2. **DeepFlow 当前的输出膨胀问题**：
   - `final_result.json`（21.4KB）— 最丰富
   - `living_blueprint.json`（36.8KB）— 膨胀但信息变少
   - `frozen_blueprint.json`（44.5KB）— 最大但最空
   
   三个文件总共 102.7KB，但有效信息集中在 final_result 的 21.4KB 中。这是**信息熵的浪费**。

3. **Manus 的单文件原则**：Manus 的 todo.md 同时包含任务定义、上下文需求、状态追踪、输出策略。一个文件，多个维度。不需要三个文件来表达同一个方案。

**推荐的 Solution Pro 输出结构**（`solution.json`）：

```json
{
  "meta": {
    "project_name": "跨境AI算力中转站",
    "version": "1.0",
    "generated_at": "2026-06-18T21:00:00+08:00",
    "solution_pro_version": "x.y.z"
  },
  "architecture": {
    "modules": [...],          // 模块定义（含技术栈、职责、依赖）
    "data_flow": "...",        // 数据流描述
    "tech_stack": {...},       // 整体技术栈
    "deployment": {...}        // 部署方案
  },
  "implementation_plan": {
    "mvp_timeline": "15天",
    "phases": [...],           // 阶段定义（含 tasks + milestones）
    "risk_assessment": {...}
  },
  "constraints": {
    "technical": [...],        // 技术约束
    "business": [...],         // 业务约束
    "compliance": [...]        // 合规约束
  },
  "acceptance_criteria": {
    "functional": [...],       // 功能验收标准
    "non_functional": [...]    // 非功能验收标准
  }
}
```

**关键原则**：
- 一个 JSON 文件，包含方案的所有维度
- 不区分"living"和"frozen"——版本控制由 Git 负责
- `implementation_plan` 必须填充（不能像当前 delivery 一样永远是空数组）
- `acceptance_criteria` 是新增的关键维度——Factory.ai 的"验证合同"思想

---

### Q3: Ship Pro 应该做什么？

**明确建议：Ship Pro 应该从"格式转换器"升级为"执行规划器"（Execution Planner）**

**业界依据**：

1. **Factory.ai 的 Coordinator-Droid 模式**：Factory.ai 的 Coordinator 不只是把任务从一种格式翻译成另一种格式。它做的是：
   - 接收 Mission 级目标
   - 拆分为 Worker 级子任务
   - 为每个子任务定义**验证合同**（正确性标准）
   - 管理依赖关系和执行顺序
   - 在关键里程碑设置验证检查点

2. **Claude Code 的 Plan-and-Execute 分离**：Claude Code Ultra Plan 的 4-Agent 架构（3 Explorer + 1 Critic）的核心思想是：**规划和执行是不同的心智活动**。规划者不需要知道怎么拧螺丝，但需要知道哪颗螺丝在哪、什么时候拧。

3. **OpenAI Codex 的 Skills 模式**：Codex 的 SKILL.md 不只是描述"做什么"，还描述"怎么做"——包含具体的工具调用序列、错误处理策略、验证步骤。

**Ship Pro 的新职责定义**：

| 职责 | 当前状态 | 目标状态 |
|------|---------|---------|
| 任务分解 | module → WP（加"实现"二字） | 从 implementation_plan.phases 生成可执行的工作包 |
| 工时估算 | 无 | 基于模块复杂度和依赖关系估算工时 |
| 验收标准 | "功能实现完成，满足设计规格"（模板废话） | 从 solution.acceptance_criteria 推导每个 WP 的具体验收条件 |
| 技术约束 | "上游未提供具体约束" | 从 solution.constraints + architecture 提取每个 WP 的技术边界 |
| 依赖管理 | ✅ 依赖关系推导 + phase 拓扑排序（唯一有价值的部分） | 保留并增强：生成 DAG，支持并行执行 |
| 集成检查点 | 无 | 在关键依赖边界设置集成验证点 |
| 执行引擎适配 | 无 | 针对不同执行引擎（Hermes/Codex/Claude Code）输出不同格式 |

**Ship Pro 的输出结构**（`ship_package.json`）：

```json
{
  "meta": {
    "source_solution": "solution.json",
    "target_engine": "hermes",  // hermes | codex | claude-code
    "generated_at": "..."
  },
  "work_packages": [
    {
      "id": "WP-001",
      "title": "注册域名并配置 DNS",
      "source_phase": 1,
      "source_task": "注册域名",
      "estimated_effort": "0.5h",
      "acceptance_criteria": [
        "域名注册成功，whois 可查",
        "DNS 解析指向 Railway 部署地址"
      ],
      "technical_constraints": [
        "使用 Cloudflare 作为 DNS 提供商",
        "启用 DNSSEC"
      ],
      "dependencies": [],
      "integration_checkpoints": []
    }
  ],
  "execution_dag": {
    "nodes": ["WP-001", "WP-002", ...],
    "edges": [["WP-001", "WP-003"], ...],
    "parallel_groups": [["WP-001", "WP-002"], ["WP-003", "WP-004"]]
  },
  "milestones": [
    {
      "name": "核心基础设施就绪",
      "trigger_wps": ["WP-001", "WP-002", "WP-003"],
      "verification": "所有基础设施 WP 验收通过"
    }
  ]
}
```

---

### Q4: 三个模块的数据流最优设计是什么？

**明确建议：两阶段管线 + 单一真相源**

```
┌─────────────────────────────────────────────────────────────────┐
│                        DeepFlow 数据流                          │
│                                                                 │
│  ┌──────────────┐    solution.json     ┌──────────────┐         │
│  │  Spec Pro    │ ──────────────────→  │ Solution Pro │         │
│  │  (需求收集)  │    requirements.json  │  (方案设计)   │         │
│  └──────────────┘                      └──────┬───────┘         │
│                                               │                 │
│                                    solution.json (唯一真相源)    │
│                                               │                 │
│                                               ▼                 │
│                                        ┌──────────────┐         │
│                                        │  Ship Pro    │         │
│                                        │ (执行规划)    │         │
│                                        └──────┬───────┘         │
│                                               │                 │
│                                    ship_package.json            │
│                                               │                 │
│                                               ▼                 │
│                                        ┌──────────────┐         │
│                                        │ Super Loop   │         │
│                                        │  (执行代码)   │         │
│                                        └──────────────┘         │
│                                                                 │
│  文件清单（一次完整运行）：                                       │
│  blackboard/项目名/                                             │
│  ├── requirements.json      ← Spec Pro 输出                    │
│  ├── solution.json          ← Solution Pro 输出（唯一真相源）   │
│  └── ship_package.json      ← Ship Pro 输出                    │
│                                                                 │
│  删除：living_blueprint, frozen_blueprint, control_contract,    │
│        execution_plan, tasks.json（内部中间产物不应持久化）       │
└─────────────────────────────────────────────────────────────────┘
```

**业界依据**：

1. **Manus 的单文件原则**：todo.md 是唯一真相源。没有"living todo"和"frozen todo"的区分。
2. **Hermes 的记忆分层**：每层有明确职责，不互相重复。`user.md` 和 `memory.md` 不存储相同信息的不同版本。
3. **Claude Code 的 CLAUDE.md**：一个文件包含所有持久上下文。不区分"活"版本和"冻结"版本。
4. **Factory.ai 的 Mission → Worker 两层**：不是三层，不是五层。两层足够。

**DeepFlow 的最优设计**：
- **Spec Pro → requirements.json**：需求真相源
- **Solution Pro → solution.json**：方案真相源（替代 final_result + living_blueprint + frozen_blueprint）
- **Ship Pro → ship_package.json**：执行真相源
- **Super Loop 消费 ship_package.json**

**三个文件，三个真相源，零冗余**。

---

## 三、DeepFlow 应该借鉴的 3 个关键设计理念

### 1. 文件即计划（Plan-as-File）— 来自 Manus

**核心理念**：方案不是一个抽象的数据结构，而是一个**人类可读的文件**。这个文件同时是：
- Agent 的执行指南
- 人类的审计轨迹
- 版本控制的对象

**DeepFlow 的应用**：
- `solution.json` 应该同时包含机器可读的结构化数据和人类可读的描述
- 考虑增加 `solution.md`（Markdown 渲染版本），让忠礼可以直接阅读方案摘要
- Ship Pro 的 `ship_package.json` 同理，应该有一个 `ship_package.md` 的渲染版本

**为什么重要**：当前 DeepFlow 的 Blueprint 是纯 JSON，人类无法直接阅读。44.5KB 的 frozen_blueprint.json 对人类来说是天书。Manus 证明了：用 Markdown 作为计划的载体，既对人类友好，又对 Agent 友好。

---

### 2. 验证合同前置（Acceptance Contract First）— 来自 Factory.ai

**核心理念**：在开始执行之前，先定义"什么算完成"。Factory.ai 的双层 TDD 模式：
- **Mission 级**：定义验证合同（正确性标准），在开发前就确定
- **Worker 级**：先写测试，再写代码

**DeepFlow 的应用**：
- Solution Pro 必须在 `solution.json` 中输出 `acceptance_criteria`（功能 + 非功能）
- Ship Pro 必须为每个 Work Package 推导具体的验收条件
- Super Loop 执行时，必须验证每个 WP 的验收条件，而不只是"代码能跑"

**为什么重要**：当前 DeepFlow 的 Ship Pro 输出的验收标准是"功能实现完成，满足设计规格"——这是**零信息量**的模板废话。Factory.ai 证明了：验收标准必须是具体的、可验证的、从需求推导出来的。

---

### 3. 上下文工程优于提示工程（Context Engineering > Prompt Engineering）— 来自 Manus + Claude Code

**核心理念**：Agent 的表现不取决于提示词写得多好，而取决于**给 Agent 的上下文是否精准**。Manus 的 todo.md 会显式声明每个任务需要的上下文（`Context Requirements`），然后由 Context Engineering Module 自动收集。Claude Code 的 `CLAUDE.md` 确保 Agent 拥有项目特定的知识。

**DeepFlow 的应用**：
- Ship Pro 在为每个 WP 生成执行指令时，必须显式声明该 WP 需要的上下文（哪些模块的代码、哪些配置、哪些文档）
- Super Loop 在执行每个 WP 时，应该只注入该 WP 相关的上下文，而不是整个 solution.json
- 考虑引入"上下文预算"（Context Budget）概念——类似 Hermes 的 Iteration Budget，限制每个执行步骤的上下文大小，防止上下文腐化

**为什么重要**：当前 DeepFlow 的 Super Loop 可能会收到整个 frozen_blueprint（44.5KB）作为上下文，其中大量是空值或无关信息。这会导致 Agent 的注意力分散，执行质量下降。

---

## 四、推荐的架构数据流图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DeepFlow 推荐架构数据流                               │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ Phase 1: 需求收集 (Spec Pro)                                     │   │
│  │                                                                   │   │
│  │  输入: 用户对话 / 文档 / 参考项目                                  │   │
│  │  输出: requirements.json                                          │   │
│  │  内容: 功能需求、非功能需求、约束条件、利益相关者                    │   │
│  │  验证: 需求完整性检查（覆盖率 > 90%）                              │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
│                                  │                                       │
│                          requirements.json                              │
│                                  │                                       │
│                                  ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ Phase 2: 方案设计 (Solution Pro)                                  │   │
│  │                                                                   │   │
│  │  角色: 架构师（出蓝图，不管施工）                                   │   │
│  │  输入: requirements.json                                          │   │
│  │  输出: solution.json（唯一真相源）                                 │   │
│  │                                                                   │   │
│  │  solution.json 结构:                                              │   │
│  │  ├── meta: 项目元信息                                              │   │
│  │  ├── architecture: 模块定义 + 技术栈 + 部署方案 + 数据流           │   │
│  │  ├── implementation_plan: phases + tasks + milestones（必须填充）  │   │
│  │  ├── constraints: 技术/业务/合规约束                               │   │
│  │  └── acceptance_criteria: 功能/非功能验收标准                      │   │
│  │                                                                   │   │
│  │  验证: 需求追溯矩阵（每个需求 → 至少一个架构模块）                  │   │
│  │  可选输出: solution.md（人类可读渲染版本）                          │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
│                                  │                                       │
│                            solution.json                                │
│                                  │                                       │
│                                  ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ Phase 3: 执行规划 (Ship Pro)                                      │   │
│  │                                                                   │   │
│  │  角色: 项目经理（翻译蓝图为施工任务单）                             │   │
│  │  输入: solution.json                                              │   │
│  │  输出: ship_package.json                                          │   │
│  │  适配: target_engine 参数（hermes / codex / claude-code）          │   │
│  │                                                                   │   │
│  │  Ship Pro 核心逻辑:                                               │   │
│  │  1. 从 implementation_plan.phases 提取任务                        │   │
│  │  2. 为每个任务生成 Work Package:                                   │   │
│  │     - 具体验收条件（从 acceptance_criteria 推导）                  │   │
│  │     - 技术约束（从 constraints + architecture 提取）               │   │
│  │     - 工时估算（基于复杂度和依赖）                                 │   │
│  │  3. 构建执行 DAG（依赖关系 + 并行组）                              │   │
│  │  4. 设置集成检查点（关键依赖边界的验证点）                         │   │
│  │  5. 根据 target_engine 适配输出格式                                │   │
│  │                                                                   │   │
│  │  验证: 每个 WP 必须有 ≥2 条具体验收条件                            │   │
│  │  可选输出: ship_package.md（人类可读渲染版本）                      │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
│                                  │                                       │
│                          ship_package.json                              │
│                                  │                                       │
│                                  ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ Phase 4: 执行 (Super Loop)                                        │   │
│  │                                                                   │   │
│  │  角色: 施工队                                                      │   │
│  │  输入: ship_package.json + 按需注入的上下文                        │   │
│  │  执行模式:                                                         │   │
│  │  - 按 DAG 顺序执行 Work Packages                                  │   │
│  │  - 并行组内的 WP 可同时执行                                        │   │
│  │  - 每个 WP 完成后验证验收条件                                      │   │
│  │  - 集成检查点触发时，验证跨 WP 的集成正确性                        │   │
│  │                                                                   │   │
│  │  上下文策略（借鉴 Manus + Hermes）:                                 │   │
│  │  - 每个 WP 只注入相关上下文（不是整个 ship_package）                │   │
│  │  - 上下文预算: 每个 WP 最多 32K tokens 的上下文                    │   │
│  │  - 迭代预算: 每个 WP 最多 N 轮执行尝试（类似 Hermes）              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 删除的文件:                                                        │   │
│  │ ❌ living_blueprint.json    — 信息被 solution.json 覆盖            │   │
│  │ ❌ frozen_blueprint.json    — 信息丢失且被 solution.json 覆盖      │   │
│  │ ❌ control_contract.json    — Solution Pro 内部产物，不应持久化     │   │
│  │ ❌ execution_plan.json      — 信息被 solution.implementation_plan  │   │
│  │                               覆盖                                │   │
│  │ ❌ tasks.json               — Solution Pro 内部产物，不应持久化     │   │
│  │ ❌ ship_review_data.json    — 可合并到 ship_package.json 的 meta   │   │
│  │ ❌ domain_config.json       — 可合并到 ship_package.json 的 meta   │   │
│  │                                                                   │   │
│  │ 保留的文件（3 个真相源）:                                          │   │
│  │ ✅ requirements.json        — Spec Pro 输出                       │   │
│  │ ✅ solution.json            — Solution Pro 输出                   │   │
│  │ ✅ ship_package.json        — Ship Pro 输出                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 五、最大风险

### 风险 1: Solution Pro 的 implementation_plan 继续为空（🔴 最高风险）

**描述**：当前 Solution Pro 的 `delivery` section 永远是空数组。如果重设计后 `solution.json` 的 `implementation_plan` 仍然无法填充，整个下游管线（Ship Pro → Super Loop）将失去输入。

**根因分析**：Solution Pro 的 10 阶段管线可能没有"生成实施计划"这个阶段。当前的管线可能专注于"架构设计"，而把"实施计划"视为下游责任。

**缓解措施**：
1. 在 Solution Pro 的管线中**显式增加**"实施计划生成"阶段
2. 如果 Solution Pro 的 LLM 无法可靠生成实施计划，考虑用独立的 LLM 调用（类似 Factory.ai 的 Coordinator 单独生成 Mission 级计划）
3. 设置验证门控：`implementation_plan.phases` 不能为空，否则 Ship Pro 拒绝消费

**业界参考**：Factory.ai 的 Coordinator 在拆分任务前，必须先生成 Mission 级验证合同。如果合同为空，整个 Mission 不会启动。

---

### 风险 2: Ship Pro 的"智能"不足，退化为格式转换器（🟡 高风险）

**描述**：即使删除了 frozen_blueprint，Ship Pro 仍可能退化为"从 solution.json 提取字段 → 填入 ship_package.json 模板"的简单转换器，无法生成真正有价值的验收条件、技术约束和工时估算。

**根因分析**：Ship Pro 的 LLM 可能缺乏"从架构方案推导实施细节"的能力。这不是 prompt 问题，而是**任务定义**问题——如果 Ship Pro 的 prompt 只说"转换为 Work Package 格式"，它当然只会做格式转换。

**缓解措施**：
1. 重新定义 Ship Pro 的 prompt：不是"转换"，而是"规划"——你需要为每个 WP 思考"怎么验收"、"有什么技术风险"、"需要多少时间"
2. 引入 Few-shot 示例：展示一个"好的 WP"和一个"差的 WP"的对比
3. 设置质量门控：每个 WP 的验收条件必须 ≥2 条且不能包含模板废话

**业界参考**：Factory.ai 的 Coordinator 不只是分配任务，它会为每个子任务生成"验证合同"。这是 Coordinator 的核心价值——不是翻译，是规划。

---

### 风险 3: 过度简化导致信息丢失（🟡 中风险）

**描述**：从 10 个文件简化到 3 个文件，可能会丢失某些有价值的中间信息（如需求追溯矩阵、领域配置）。

**缓解措施**：
1. 需求追溯矩阵：合并到 `solution.json` 的 `meta.traceability` 字段
2. 领域配置：合并到 `ship_package.json` 的 `meta.domain_config` 字段
3. 内部中间产物（control_contract, execution_plan, tasks）：保留为 Solution Pro 的**临时文件**（不纳入 blackboard 的正式输出），或在 solution.json 中增加 `_internal` 字段

**业界参考**：Hermes 的记忆系统虽然分为三层，但每层的信息不重复。如果某个信息在多个地方需要，它只存储在"最权威"的那一层，其他地方用引用。

---

## 六、总结：3 个最关键的设计决策

| 优先级 | 决策 | 理由 | 业界参考 |
|--------|------|------|---------|
| 🔴 P0 | 删除 frozen_blueprint，Ship Pro 直接消费 solution.json | 消除信息损耗的根因，减少 50% 的文件数量 | Manus 单文件原则、Claude Code CLAUDE.md |
| 🔴 P0 | Solution Pro 必须输出 implementation_plan + acceptance_criteria | 这是下游管线的输入前提，没有它 Ship Pro 无法工作 | Factory.ai 验证合同前置、Codex Skills |
| 🟡 P1 | Ship Pro 升级为"执行规划器"，为每个 WP 生成验收条件和技术约束 | 这是 Ship Pro 存在的核心价值，不做这个它就只是格式转换器 | Factory.ai Coordinator、Claude Code Plan-and-Execute |

---

*报告完成。以上建议基于 2025-2026 年业界 6 大 Agent 框架的实际架构和最新实践。*
