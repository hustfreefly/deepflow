# "全 LLM 控制" vs "混合架构" 业界实践调研

> 调研日期：2026-06-25
> 调研范围：2025-2026 年业界最新实践

---

## 核心发现（TL;DR）

1. **纯 LLM 控制在生产中已被证伪** — Devin 仅 15% 成功率，33% PR 被拒绝；Gartner 预测 40%+ 的 Agent 项目将在 2027 年前被放弃。
2. **业界共识已收敛到"混合架构"** — LLM 做语义决策，确定性代码做流程控制、安全校验、状态管理。
3. **Anthropic 的"简单循环 + 环境约束"模式胜出** — 单线程 master loop + 分层防御，比多 Agent 编排更可靠。
4. **护栏设计的关键是"环境层"而非"模型层"** — 模型对齐是概率性的（有漏网率），进程沙箱/VM/网络隔离才是硬边界。
5. **2026 年趋势：自适应 HITL（Human-in-the-Loop）** — 不是"全自主"也不是"每步审批"，而是按风险等级动态决定人工介入点。

---

## 各方立场

### Anthropic — "简单循环 + 环境约束"

**核心理念：a simple, single-threaded master loop combined with disciplined tools and planning**

Anthropic 是"反复杂编排"的代表。Claude Code 的架构刻意保持简单：

| 设计选择 | 具体做法 | 原因 |
|:---|:---|:---|
| **单线程主循环** | while-loop（内部代号 "nO"），有 tool call 就继续，纯文本就终止 | 避免多 Agent 竞争导致不可预测行为 |
| **扁平消息历史** | 无嵌套对话、无竞争 persona | 可调试性 > 花哨架构 |
| **环境层约束** | claude.ai → gVisor 容器；Claude Code → OS 级沙箱；Claude Cowork → 完整 VM | 模型对齐是概率性的，环境隔离是硬边界 |
| **Lazy Degradation** | 先尝试最便宜/最快/最小破坏的修复，逐步升级 | 减少爆炸半径 |
| **减少审批疲劳** | 发现用户 93% 的审批都是不看就过 → 转向自动化安全审批 | human-in-the-loop 不等于每一步都弹窗 |

**关键洞察：三层防御模型**
```
┌─────────────────────────────────────┐
│  External Content Layer             │  ← MCP tools、网页、文件（攻击面）
├─────────────────────────────────────┤
│  Model Layer                        │  ← 训练对齐（概率性，有漏网率）
├─────────────────────────────────────┤
│  Environment Layer                  │  ← 沙箱/VM/网络隔离（硬边界）
└─────────────────────────────────────┘
```

**核心原则：deny-first evaluation** — deny 规则永远优先于 allow。

**结果**：Claude Code 用户平均每周使用 20 小时（2025.10-2026.04），证明"简单但有纪律"的方法有效。

---

### OpenAI — "SDK 化 + Guardrails 原语"

**核心理念：给开发者提供 Guardrails 原语，让应用层决定自主性边界**

OpenAI 的 Agents SDK（2025.03 发布）将自主性控制抽象为代码原语：

| 组件 | 作用 |
|:---|:---|
| **Agent** | 有 tools、instructions 的 LLM 实例 |
| **Runner** | 执行循环，管理 Agent 间的 handoff |
| **Handoff** | Agent 间的任务转移机制 |
| **Guardrail** | 输入/输出/工具调用的校验层 |

**Guardrails 设计**：
- **Input Guardrails**：处理前过滤恶意/越界输入
- **Output Guardrails**：返回前检查响应安全性
- **Tool Guardrails**：函数工具调用前后的校验
- 支持 **blocking mode**（违规即停）和 **parallel mode**（异步检查）
- 推荐用快速廉价模型做 guardrail，省计算成本

**自主性演进**：
| 时间 | 产品 | 自主性级别 |
|:---|:---|:---|
| 2025.01 | Operator | 首个真自主 Agent，控制浏览器执行任务 |
| 2025 | Agent Mode | 在 ChatGPT 内执行任务，CUA 模型 |
| 2026.04 | Agents SDK 更新 | 原生沙箱执行，变成完整执行 harness |
| 2026 路线图 | Universal Agent | 跨 web + 本地界面的通用 Agent |

**关键教训**：Agent Builder 和 Evals 产品将于 2026.11 下线 → 代码优先的 workflow 比可视化编排更受开发者信任。

---

### Google DeepMind — "三层 Agent 安全 + 系统之系统"

**核心理念：Containment-First Architecture + 标准化 Agent Stack**

Google 在 2025.11 发布了 "Introduction to Agents" 论文，将 Agent 架构标准化为三层：

| 层 | 角色 | 类比 |
|:---|:---|:---|
| **The Brain** | 模型（推理/决策） | 大脑 |
| **The Hands** | 工具（执行能力） | 手 |
| **The Nervous System** | 编排（协调控制） | 神经系统 |

**Gemini 2.5 的 "System of Systems" 架构**：
- 主 Agent（Gemini 2.5 Pro）做决策
- 另一个 Gemini 实例做 "critique"（批评/校验）
- 通过 XML 文件维护记忆状态
- Sparse MoE + 百万 token 上下文窗口

**2026 年的三协议栈**：
| 协议 | 作用 |
|:---|:---|
| **MCP** (Model Context Protocol) | 工具/API 交互 |
| **A2A** (Agent-to-Agent Protocol) | Agent 间协作 |
| **安全层** | 沙箱执行 + 网络隔离 + 短时效凭证 |

**专门 Agent 系统**：
- **Aletheia**（2026.02）：数学研究 Agent，用 Deep Think + 自然语言验证器
- **Co-Scientist**（2026.05）：多 Agent 科学发现系统，Agent 间辩论和演化假设
- **Deep Research Max**（2026.04）：自主研究 Agent

**关键论文结论**：多 Agent 系统的有效性高度依赖"正确的架构"，更聪明的模型增强（而非替代）良好设计的多 Agent 系统。

---

### 业界实践

#### Devin（Cognition）— 全自主编程 Agent 的教训

**架构**：
- 独立云沙箱环境（shell + code editor + browser）
- 32B 专用模型 + 强化学习
- 长期规划 + 自我纠正
- 2.0 版引入 "Interactive Planning"（先让人看计划再执行）

**实际结果（惨痛教训）**：
| 指标 | 数据 |
|:---|:---|
| 任务成功率 | **15%**（20 个任务只完成 3 个） |
| PR 拒绝率 | **~33%**（2026.03） |
| 常见问题 | 技术死胡同、过度复杂代码、自造 bug 再自修 |
| 调试方式 | 依赖 print 语句而非高级调试工具 |

**核心问题**：
- "senior-level at codebase understanding but **junior at execution**"
- 不可预测哪些任务能完成，简单任务也可能灾难性失败
- Demo 涉嫌 cherry-picking，隐瞒关键限制
- 需要大量 human "babysitting"

**架构调整**：V3 转向企业安全（SOC 2、VPC 部署、零留存），2.0 引入人工审批计划步骤。

---

#### Cursor / Windsurf — AI 辅助编程的编排模式

**Cursor 的演进**：
| 版本 | 架构 | 特点 |
|:---|:---|:---|
| Cursor 1.x | 单 Agent | 开发者手动 `@` 引用上下文 |
| Cursor 2.0（2025.10） | **多 Agent 并行** | 同时编排 8 个 AI Agent 做不同任务 |

**关键设计**：
- **Agent Mode**：理解高层需求 → 搜索代码库 → 规划变更 → 修改文件 → 执行命令 → 验证结果
- **Composer Model**：专有模型，专为多文件变更编排优化
- **Developer-Driven Context**：开发者手动策展 AI 的上下文（`@file`、`@folder`）
- 核心理念：**开发者保持控制权**，AI 是加速器而非替代者

**Windsurf 的方法**：
- **Cascade Technology**：全代码库深度上下文感知
- 更偏 "agentic IDE"，AI 主动建议改进
- 适合大型复杂项目
- 2025 年被 Cognition 收购

**共同模式**：两者都是 **"LLM 做语义理解 + 确定性代码做文件操作/命令执行/验证"** 的混合架构。

---

#### SWE-Agent / OpenHands — 开源编程 Agent

**SWE-Agent（Princeton）**：
- **Multi-Agent 架构**：Action Agent + Value Agent + Discriminator Agent
- **Agent-Computer Interface (ACI)**：专为 LLM 设计的抽象层（非人类 UI）
  - 简洁反馈（解决 verbose output 问题）
  - 内置 guardrails
  - 高效上下文管理
- **MCTS 决策**：每个决策点用 Monte Carlo Tree Search 选择行动
- **Live-SWE-Agent**（2025 末）：运行时自修改 scaffold 和工具集
- 沙箱 Docker 执行

**OpenHands（前 OpenDevin）**：
- **V1 架构**（2025.11）：完全重新设计
  - Stateless Agent → 发出 actions
  - Conversation → 管理交互循环 + append-only EventLog
  - Workspace → 执行 actions（本地进程或 Docker）
  - LLM Wrapper → LiteLLM 跨模型可移植
- **四包 SDK**：`sdk` / `tools` / `workspace` / `agent_server`
- **核心原则**：
  - Stateless by default（不可变 Pydantic models）
  - 严格关注点分离
  - 可选隔离（默认 in-process，需要时才 Docker）
  - 组件可组合（Agent = graph of interchangeable components）

**共同趋势**：都从"让 LLM 直接操作"演进到"通过抽象层/SDK 控制 LLM 的操作范围"。

---

#### ChatDev / MetaGPT — 多 Agent 软件开发

**MetaGPT**：
- **核心公式**：`Code = SOP(Team)` — 将人类 SOP 嵌入 AI 流程
- 角色：Product Manager、Architect、Project Manager、Engineer、QA
- 层级规划架构 + 标准化通信协议
- 一行需求 → PRD + 系统设计 + API 规格 + 实现代码
- 2025 新增 "Foundation Agent" + MGX + AFlow

**ChatDev**：
- **Chat Chains**：序列化的 Agent 对话，连接高层规划与代码生成
- 角色：CEO、CTO、CPO、Programmer、Designer、Tester、Reviewer
- Waterfall 生命周期：设计 → 编码 → 测试 → 文档
- 2.0（DevAll）：零代码编排平台 + MacNet 架构

**关键洞察**：多 Agent 的价值不在于"每个 Agent 更自主"，而在于**角色分工 + 结构化通信 = 减少幻觉和错误传播**。

---

## 失败模式分析

### 全 LLM 控制的常见失败模式

| 失败模式 | 描述 | 案例 | 发生率 |
|:---|:---|:---|:---|
| **工具误用** | Agent 传错参数、调错工具、工具链断裂 | 2024-2025 生产部署中 **~31% 的失败** 归因于此 | 🔴 高 |
| **级联错误** | 一个小错误在自主 workflow 中静默传播，污染下游 | 数据损坏、流程中断 | 🔴 高 |
| **行动幻觉** | 不仅编造文本，还编造错误的行动/工具参数 | 错误的 API 调用、无效的文件操作 | 🔴 高 |
| **过度自信** | Agent 不识别自己的知识边界，盲目执行 | 47% 的商业领导者基于 AI 幻觉做重大决策 | 🟡 中 |
| **上下文碎片化** | 跨系统工作时信息不完整或过时 | 错误的 handoff 导致关键信息丢失 | 🟡 中 |
| **审批疲劳** | 人工审批太多 → 用户不看就过 → 形同虚设 | Claude Code 用户 93% 审批不看就过 | 🟡 中 |
| **技术死胡同** | Agent 进入无法退出的错误路径 | Devin 频繁卡在不可用方案上 | 🟡 中 |
| **提示注入/记忆投毒** | 攻击者通过外部内容覆盖 Agent 指令 | 2025 年首个 AI 编排的网络间谍活动 | 🟠 低但严重 |
| **静默模型漂移** | 模型更新后性能退化但不易察觉 | 随时间推移错误率悄悄上升 | 🟠 低但隐蔽 |
| **范围蠕变** | Agent 被赋予超出基础设施能力的任务 | 给 Agent 太多工具/权限导致失控 | 🟡 中 |

### 失败根因分析

```
                    ┌──────────────────────┐
                    │  根本原因：概率性系统   │
                    │  被当作确定性系统使用   │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
    │ 缺乏环境约束   │  │ 缺乏状态管理   │  │ 缺乏验证机制   │
    │ (沙箱/隔离)   │  │ (EventLog/    │  │ (output check/│
    │               │  │  checkpoint)  │  │  test runner) │
    └───────────────┘  └───────────────┘  └───────────────┘
```

---

## 最佳实践总结

### 1. 架构原则：LLM 做什么 vs 代码做什么

| 职责 | 归属 | 原因 |
|:---|:---|:---|
| **意图理解/分类** | LLM | 语义理解是 LLM 强项 |
| **方案规划/排序** | LLM + 代码约束 | LLM 生成选项，代码过滤不可行方案 |
| **工具选择** | LLM | 自然语言 → 工具映射 |
| **工具参数校验** | 确定性代码 | 类型检查、范围检查、权限检查 |
| **执行流程控制** | 确定性代码 | while/for/if，不依赖 LLM 判断 |
| **状态管理** | 确定性代码 | EventLog/数据库，不用 LLM "记住" |
| **安全边界** | 确定性代码 | 沙箱、网络隔离、权限控制 |
| **结果验证** | 确定性代码 | 测试运行、类型检查、schema 验证 |
| **错误恢复策略** | 确定性代码 + LLM | 代码检测错误，LLM 建议修复方案 |
| **人工介入判断** | 确定性代码（基于风险规则） | 不能靠 LLM 自己判断是否需要帮助 |

### 2. 护栏设计：分层防御

```
Layer 1: Input Guardrails     ← 确定性代码：schema 校验、注入检测
Layer 2: Model Alignment      ← LLM 训练：对齐、指令遵循
Layer 3: Output Guardrails    ← 确定性代码：结果校验、敏感信息过滤
Layer 4: Environment          ← 确定性代码：沙箱、网络隔离、文件系统边界
Layer 5: Execution Verify     ← 确定性代码：测试、dry-run、回滚机制
Layer 6: Human Escalation     ← 混合：按风险等级动态触发
```

**关键原则**：
- **deny-first**：deny 规则永远优先
- **环境层 > 模型层**：不信任模型能 100% 自我约束
- **减少审批疲劳**：自动化低风险审批，人工聚焦高风险决策

### 3. 自主性分级（Adaptive HITL）

| 风险等级 | 自主性级别 | 人工介入 | 示例 |
|:---|:---|:---|:---|
| **Low** | 全自动 | 事后审计 | 代码格式化、文档生成 |
| **Medium** | 自动 + 通知 | 执行后通知 | 文件编辑（有回滚） |
| **High** | 半自动 | 执行前审批 | 数据库变更、API 调用 |
| **Critical** | 人工主导 | 每步审批 | 生产部署、资金操作 |

### 4. 编排模式选择

| 模式 | 适用场景 | 代表 | 优劣 |
|:---|:---|:---|:---|
| **单 Agent 循环** | 明确任务、单步可验证 | Claude Code | ✅ 可调试 ❌ 不擅长复杂多步 |
| **多 Agent 并行** | 独立子任务可并行 | Cursor 2.0 | ✅ 高吞吐 ❌ 协调复杂 |
| **角色分工** | 需要不同专业视角 | MetaGPT | ✅ 减少幻觉 ❌ 通信开销大 |
| **Handoff 链** | 任务需要不同能力 | OpenAI Agents SDK | ✅ 灵活 ❌ handoff 易丢信息 |
| **Workflow + Agent** | 固定流程 + 灵活决策 | 混合编排 | ✅ 可控 ❌ 设计复杂 |

---

## 对 Ship Pro 的建议

### 核心建议：采用"确定性骨架 + LLM 肌肉"的混合架构

```
┌─────────────────────────────────────────────────────────┐
│                    确定性代码层                           │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ 流程控制 │  │ 状态管理  │  │ 安全边界  │  │ 结果验证 │ │
│  │ (DAG/   │  │(EventLog/│  │(沙箱/权限/│  │(测试/    │ │
│  │ while/  │  │ checkpoint│  │ 网络隔离) │  │ schema/ │ │
│  │ if/for) │  │ /rollback)│  │          │  │ dry-run)│ │
│  └─────────┘  └──────────┘  └──────────┘  └─────────┘ │
├─────────────────────────────────────────────────────────┤
│                     LLM 层                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ 意图理解  │  │ 方案生成  │  │ 代码编写  │              │
│  │ 工具选择  │  │ 错误分析  │  │ 文档生成  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
├─────────────────────────────────────────────────────────┤
│                  人工介入层（Adaptive HITL）              │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Low → 自动  │ Medium → 通知  │ High → 审批       │   │
│  │ (事后审计)   │ (执行后通知)   │ (执行前确认)       │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 具体建议

1. **流程控制绝不用 LLM**
   - 用确定性代码定义 workflow DAG
   - LLM 只负责在每个节点做"语义决策"（分类、提取、生成）
   - 参考：Anthropic 的单线程 master loop

2. **状态管理用 EventLog，不用 LLM 记忆**
   - 参考 OpenHands 的 append-only EventLog 设计
   - 所有可变状态集中在一个地方，方便调试和回滚
   - LLM 的上下文是"投影"，不是"真相来源"

3. **安全边界用环境隔离，不靠模型对齐**
   - 参考 Anthropic 的三层防御：Environment > Model > External Content
   - 沙箱执行、网络隔离、短时效凭证
   - deny-first 权限模型

4. **工具调用用 ACI 抽象层**
   - 参考 SWE-Agent 的 Agent-Computer Interface
   - 为 LLM 设计的接口 ≠ 人类 UI
   - 简洁反馈、内置 guardrails、上下文管理

5. **验证用确定性检查，不用 LLM 自评**
   - 代码生成后跑测试
   - 文件操作后验证 schema
   - 危险操作前 dry-run
   - LLM 不擅长评估自己的工作

6. **人工介入按风险分级，不搞一刀切**
   - 低风险：全自动 + 事后审计
   - 中风险：自动 + 通知
   - 高风险：执行前审批
   - 参考 OpenAI 的 Guardrails 原语设计

7. **从单 Agent 开始，按需扩展**
   - 不要一开始就搞多 Agent 编排
   - 单 Agent + 好工具 > 多 Agent + 混乱协调
   - 参考 Anthropic："简单但有纪律" > "复杂但脆弱"

### 反模式警告

| ❌ 反模式 | ✅ 正确做法 |
|:---|:---|
| 让 LLM 决定下一步执行什么流程分支 | 确定性代码控制流程，LLM 只做节点内决策 |
| 用 LLM 的对话历史当状态 | 用独立的 EventLog/数据库 |
| 靠 prompt 约束安全边界 | 靠沙箱/权限/网络隔离 |
| 让 LLM 自己判断是否需要人工帮助 | 用风险规则自动触发人工介入 |
| 让 LLM 评估自己的输出质量 | 用确定性测试/校验 |
| 一开始就搞 5 个 Agent 协作 | 先 1 个 Agent 跑通，再按需拆分 |
| 每步都弹窗让人审批 | 按风险分级，低风险自动化 |

---

## 参考来源

- Anthropic, "How we contain Claude across products" (2025)
- Anthropic, Claude Code architecture documentation (2025)
- OpenAI, Agents SDK documentation (2025.03)
- OpenAI, "Introducing AgentKit" (2025.10)
- Google DeepMind, "Introduction to Agents" (2025.11)
- Google DeepMind, "Securing the Future of AI Agents" (2026.06)
- Cognition, Devin architecture and V3 release notes (2025-2026)
- Princeton NLP, SWE-Agent / SWE-Search papers (2025)
- OpenHands, "The Path to OpenHands V1" (2025.11)
- MetaGPT project documentation (2025)
- ChatDev / DevAll project documentation (2025)
- Cursor 2.0 release notes (2025.10)
- Gartner, "AI Agent Predictions 2025-2027"
- Forbes, "From Generative to Agentic: The New Era of AI Autonomy" (2025.11)
- IBM, "AI Agents 2025: Expectations vs Reality"
- MIT Sloan, "Agentic AI Explained" (2025)
