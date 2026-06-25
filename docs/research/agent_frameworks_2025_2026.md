# AI Agent 编排框架趋势调研（2025-2026）

> 调研日期：2026-06-25
> 调研人：技术调研 Agent

---

## 调研摘要（TL;DR）

1. **混合架构成为共识**：纯 LLM 控制（monolithic agent）在 2025 年被证明不适合生产环境。行业主流转向"确定性控制流 + LLM 推理层"的混合架构，LangGraph、Microsoft Agent Framework 等均提供图结构编排 + LLM 动态决策的混合模式。

2. **图编排（Graph-based Orchestration）成为标准范式**：LangGraph 的"有环图 + 状态机"、MAF 的"有向图 + 消息传递"、CrewAI 的"层级流程"本质上都是图编排。静态 DAG 已被淘汰，支持条件分支、循环、动态路由的图结构成为标配。

3. **协议层标准化加速**：2025 年出现两大互补协议——Anthropic MCP（Agent↔Tool）和 Google A2A（Agent↔Agent）。这意味着 Agent 系统正在从"框架锁定"走向"协议互通"，类似当年 HTTP 对 Web 的意义。

4. **Human-in-the-loop 从可选变为必选**：所有主流框架都内置了 HITL 机制（LangGraph 的 interrupt_before、OpenAI Agents SDK 的 guardrails、MAF 的审批节点）。这反映了企业部署的现实需求。

5. **AutoGen 衰落，MAF 崛起**：微软在 2025 年 9 月将 AutoGen 置于维护模式，推出 Microsoft Agent Framework（MAF）作为企业级替代品。这标志着"社区驱动"与"企业驱动"两条路线的分化。

---

## 框架对比表

| 框架 | 编排模式 | 状态管理 | 错误恢复 | 全LLM控制? | HITL 支持 |
|------|---------|---------|---------|-----------|----------|
| **LangGraph** | 有环图 + 条件路由（混合） | Reducer 驱动 + Checkpoint 持久化 | RetryPolicy + TimeoutPolicy + SAGA 模式 | ❌ 混合（代码定义图结构，LLM 做节点内决策） | ✅ interrupt_before/after |
| **CrewAI** | 角色驱动 + 层级/顺序执行（混合） | Crew 级共享状态 + Flow 事件驱动 | 内置 guardrails + 重试 | ❌ 混合（角色/流程由代码定义，Agent 内部自主决策） | ✅ Flow 审批节点 |
| **AutoGen/AG2** | 对话驱动 + 消息传递（偏 LLM 控制） | 聊天历史即状态 | 有限（依赖 LLM 自我纠正） | ⚠️ 偏全 LLM 控制（对话即编排） | ⚠️ 有限（需手动实现） |
| **OpenAI Agents SDK** | Handoff 链 + Guardrails（混合） | 对话历史 + Context 传递 | Guardrails tripwire 中断 | ❌ 混合（handoff 由 LLM 决策，流程由代码约束） | ✅ Input/Output guardrails |
| **Anthropic Claude + MCP** | 工具调用 + 编程式编排（混合） | 对话上下文 + Tool Search 按需加载 | Programmatic tool calling 减少错误 | ❌ 混合（LLM 选工具，代码控流程） | ✅ Claude Code 沙箱审批 |
| **Google A2A** | 跨 Agent 任务委托（协议层） | Task 对象 + Artifact 持久化 | 异步通知 + SSE 流式状态更新 | N/A（协议层，不涉及框架内决策） | ✅ Agent Card 声明认证方案 |
| **Microsoft Agent Framework** | 图编排 + 多种模式（混合） | Durable Task Scheduler + 自动 Checkpoint | 持久化工作流 + 故障恢复 + 重试 | ❌ 混合（图结构代码定义，Agent 节点内 LLM 决策） | ✅ 审批节点 + OpenTelemetry |
| **Mastra** | TypeScript 工作流 + 持久化（混合） | 内置内存管理 + 持久化工作流 | 工作流级错误处理 | ❌ 混合 | ⚠️ 有限 |

---

## 各框架详细分析

### LangGraph

**定位**：LangChain 生态中的有状态 Agent 编排引擎，2025 年 10 月发布 1.0。

**编排模式**：
- **有环图（Cyclic Graph）**，不是传统 DAG。支持循环、条件分支、动态路由。
- 节点 = 状态处理函数（可以是 LLM 调用、工具调用、纯代码）
- 边 = 条件路由（由代码或 LLM 输出决定下一步）
- 本质是**状态机**：每个节点执行后状态更新，条件边决定下一个状态

**状态管理**：
- Reducer 模式：状态是显式定义的 Schema，每个节点通过 reducer 函数修改状态
- Checkpoint 机制：每个节点执行后自动持久化状态快照
- 支持从任意 checkpoint 恢复（"时间旅行"）
- 与向量数据库集成用于长期记忆

**错误恢复**：
- `RetryPolicy`：自动重试 + 退避 + 抖动
- `TimeoutPolicy`：超时控制
- Error Handler 节点：重试耗尽后的自定义降级逻辑
- SAGA 模式：分布式事务的部分回滚
- Checkpoint 恢复：从失败点继续，避免重复副作用

**HITL**：
- `interrupt_before`：在指定节点前暂停，等待人类审批
- 人类可以审查状态、修改变量、批准/拒绝
- 恢复后从暂停点继续执行

**立场**：**混合架构**。图结构由代码定义（确定性），节点内部可以用 LLM 做决策（概率性）。这是"代码控骨架，LLM 填血肉"的思路。

---

### CrewAI

**定位**：角色驱动的多 Agent 协作框架，强调"AI 团队"隐喻。

**编排模式**：
- **角色驱动**：每个 Agent 有明确的 role（如 Researcher、Writer、Manager）
- 两种执行策略：
  - `Sequential`：线性流水线
  - `Hierarchical`：Manager Agent 动态分配任务给 Specialist
- **Crews + Flows 架构**（2025 年核心升级）：
  - Crews = 自主协作的 Agent 团队（偏 LLM 决策）
  - Flows = 事件驱动的企业级控制流（偏确定性）
  - 两者结合 = 混合编排

**状态管理**：
- Crew 级别共享状态（Agent 间通过消息传递）
- Flow 提供事件驱动的状态管理
- 内置记忆系统（短期/长期/实体记忆）

**错误恢复**：
- Guardrails 验证 Agent 输出
- 内置重试机制
- 相对 LangGraph 较弱，更多依赖 LLM 自我纠正

**HITL**：
- Flow 中支持审批节点
- 不如 LangGraph 的 interrupt 机制灵活

**立场**：**混合偏自主**。角色和流程结构由代码定义，但 Agent 内部有较高的自主决策权。Hierarchical 模式下 Manager Agent 有较大的 LLM 控制权。

---

### AutoGen / AG2（微软）

**定位**：对话驱动的多 Agent 框架。2025 年经历重大分裂。

**编排模式**：
- **对话即编排**：Agent 间通过结构化聊天消息通信
- 编排模式由对话模式隐式决定
- v0.4 引入分层架构 + 异步消息传递
- AG2 = 社区分支，延续 0.2 路线

**状态管理**：
- 聊天历史即状态（隐式）
- 没有显式的 checkpoint 机制（v0.2/AG2）
- v0.4 改善了可观测性

**错误恢复**：
- 主要依赖 LLM 自我纠正（"再试一次"对话）
- 缺乏系统级的错误恢复原语
- 这是其被诟病的主要问题之一

**HITL**：
- 需要手动实现
- 可以通过"用户代理"模式模拟，但不是原生支持

**立场**：**偏全 LLM 控制**。对话驱动的编排本质上是让 LLM 通过对话决定下一步。灵活但不可控。

**⚠️ 重要变化**：2025 年 9 月微软将 AutoGen 置于维护模式，推荐迁移到 Microsoft Agent Framework（MAF）。

---

### OpenAI Agents SDK

**定位**：OpenAI 官方 Agent 构建 SDK，2025 年发布。轻量、生产导向。

**编排模式**：
- **Handoff 机制**：Agent 间任务委托，handoff 对 LLM 表现为"工具调用"
- 完整对话历史传递给目标 Agent（上下文无缝转移）
- 编排模式：
  - Triage Agent（路由）→ Specialist Agent（执行）
  - Manager Agent（控制对话流）→ Worker Agent
- 流程由代码定义 Agent 集合，LLM 决定 handoff 目标

**Guardrails 设计**：
- Input Guardrails：验证用户输入（LLM 或规则驱动）
- Output Guardrails：验证 Agent 输出
- 可以并行执行或阻塞执行
- Tripwire：违规时直接中断执行
- 支持 LLM 驱动（推理密集）和规则驱动（关键词检测）两种模式

**状态管理**：
- 对话历史即状态
- Handoff 时完整传递上下文
- Input/Output filter 可以修改传递的内容

**错误恢复**：
- Guardrails tripwire 提供安全中断
- 重试依赖外层控制逻辑
- 相对简单，依赖 OpenAI API 本身的可靠性

**HITL**：
- Guardrails 本身就是一种 HITL（自动化的"人类意图"守卫）
- 可以配置为需要人类审批的节点
- 不如 LangGraph 灵活，但足够实用

**立场**：**实用混合**。代码定义 Agent 集合和 handoff 规则，LLM 在运行时决定具体路由。"给 LLM 选择权，但不给无限权"。

---

### Anthropic Claude + MCP（Model Context Protocol）

**定位**：MCP 是 Agent↔Tool 的通信协议，不是编排框架。Claude 是模型+工具调用架构。

**编排模式**：
- **工具调用模式**：LLM 决定调用哪些工具，工具结果作为消息返回
- **Programmatic Tool Calling**（2025.11）：Claude 写代码（Python）来编排多工具调用，减少推理次数
- **Tool Search Tool**：按需发现工具，而非一次性加载所有工具定义
- MCP 本身不管编排，它只管 Agent 如何连接工具

**状态管理**：
- 对话上下文窗口即状态
- MCP Server 可以维护外部状态
- Tool Search 减少上下文占用

**错误恢复**：
- Programmatic Tool Calling 通过代码处理中间结果，减少 LLM 幻觉
- 工具结果可以包含错误信息，LLM 据此调整
- 没有框架级的 checkpoint/retry（需要外层实现）

**HITL**：
- Claude Code 的沙箱模式：执行文件操作/Shell 命令前需要人类确认
- 这是 Anthropic 的安全哲学：本地操作必须有人类监督

**MCP 架构**：
- Host（Claude）→ Client（连接管理器）→ Server（暴露工具/文件/提示）
- 基于 JSON-RPC，类似 LSP
- 与 A2A 互补：MCP 管 Agent↔Tool，A2A 管 Agent↔Agent

**立场**：**协议中立**。MCP 不关心编排策略，它只提供通信管道。Claude 模型本身倾向于"LLM 选工具，代码控流程"的混合模式。

---

### Google A2A（Agent-to-Agent Protocol）

**定位**：跨 Agent 通信的开放协议，2025 年 4 月发布，已捐赠给 Linux Foundation。

**编排模式**：
- **任务委托模式**：Client Agent 创建 Task → Remote Agent 执行 → 返回 Artifact
- 不涉及 Agent 内部编排（那是各框架的事）
- A2A 只管 Agent 间如何发现、通信、协作

**核心机制**：
- **Agent Card**：JSON 元数据文件（`/.well-known/agent.json`），声明 Agent 的能力、认证方式
- **Task 生命周期**：支持即时任务和长时间运行任务
- **通信方式**：JSON-RPC 2.0 + SSE（实时流）+ Push Notification（异步）
- **认证**：API Key / OAuth2 / OpenID Connect / mTLS

**状态管理**：
- Task 对象自带状态（lifecycle）
- Artifact 作为任务输出持久化
- 支持长时间运行任务的状态追踪

**错误恢复**：
- 异步通知机制（失败时推送通知）
- SSE 流式状态更新（实时监控）
- 协议级重试由实现方决定

**HITL**：
- Agent Card 声明支持的认证方案
- 协议本身不强制 HITL，但支持需要人类授权的认证流程

**与 MCP 的关系**：
- MCP = Agent 如何连接工具（纵向）
- A2A = Agent 如何与 Agent 通信（横向）
- 两者互补，不竞争

**立场**：**协议层**。不涉及"全 LLM 控制 vs 混合"的讨论，它只定义通信标准。

---

### Microsoft Agent Framework（MAF）

**定位**：AutoGen 的企业级替代品，2025 年 10 月公开预览。统一 Semantic Kernel + AutoGen 的能力。

**编排模式**：
- **图编排**：节点 = Agent/Tool/Executor，边 = 消息/数据流
- 支持多种编排模式：
  - Sequential（顺序）
  - Concurrent（并行）
  - Group Chat（多 Agent 讨论）
  - Handoff（任务委托）
  - **Magentic**（Manager Agent 动态构建任务账本，协调 Specialist + 人类）
- 支持代码定义或 YAML/JSON 声明式定义

**状态管理**：
- **Durable Task Scheduler**：有状态工作流，自动 checkpoint
- 支持进程重启后恢复
- 分布式执行，跨机器协调

**错误恢复**：
- 持久化工作流 + 自动 checkpoint = 故障恢复
- 内置重试机制
- OpenTelemetry 全链路可观测

**HITL**：
- 原生审批节点
- OpenTelemetry 可视化每个 Agent 动作
- Azure AI Foundry 集成（企业级合规）

**立场**：**强混合架构**。图结构由代码/配置定义（确定性），Agent 节点内 LLM 做推理（概率性）。Magentic 模式给 Manager Agent 较大自主权，但仍在图约束内。

---

### 其他新兴框架

#### Mastra
- **TypeScript-first** Agent 框架
- 持久化工作流 + 内置内存管理
- 集成 Vercel AI SDK（模型路由/流式）+ AG-UI 协议（前端交互）
- 定位：TS 生态的 LangGraph 替代品

#### AG-UI（Agent-User Interaction Protocol）
- 开源事件驱动协议，CopilotKit 主导
- 标准化 Agent 后端 → 前端的通信
- 支持 React/Angular/Mobile/SMS
- 与 Mastra 配合使用

#### Vercel AI SDK
- 本质是**流式 UI 库**，不是编排框架
- 抽象了不同 AI Provider 的差异
- 适合构建聊天 UI，但不提供工作流/内存/编排能力
- 常与 Mastra/LangGraph 配合使用

---

## 关键趋势总结

### 1. 图编排取代线性链
2024 年的"LangChain 式线性链"已被淘汰。2025 年的主流是**有环图 + 条件路由**，支持循环、分支、动态决策。LangGraph、MAF 都以图为核心。

### 2. 混合架构成为共识
"全 LLM 控制"在 2025 年被证明不可靠（幻觉、遗忘、不可观测）。行业共识是：**代码定义骨架（确定性），LLM 填充决策（概率性）**。这类似于 MVC 模式——框架提供结构，开发者填充逻辑。

### 3. 协议标准化（MCP + A2A）
- MCP 解决 Agent↔Tool 的互操作性（"AI 的 USB 接口"）
- A2A 解决 Agent↔Agent 的互操作性（"AI 的 HTTP"）
- 两者结合意味着 Agent 系统正在从"框架锁定"走向"可组合架构"

### 4. Human-in-the-loop 从可选变为必选
所有主流框架都内置了 HITL。这不是技术选择，是企业部署的合规要求。LangGraph 的 interrupt、OpenAI 的 guardrails、MAF 的审批节点都是 HITL 的实现。

### 5. AutoGen 衰落，生态整合
AutoGen 的"对话即编排"过于灵活，缺乏企业需要的可控性。微软转向 MAF（图编排 + 持久化工作流），标志着"对话驱动"让位于"结构驱动"。

### 6. TypeScript 生态崛起
Mastra、Vercel AI SDK、AG-UI 都是 TypeScript-first。这反映了前端/全栈开发者在 Agent 领域的参与度提升。

---

## 对 Ship Pro AI Native 改造的启示

### 值得借鉴的模式

1. **LangGraph 的图编排 + Checkpoint**
   - 用有环图定义 DeepFlow 的 Agent 协作流程
   - Checkpoint 机制保证长任务的可恢复性
   - `interrupt_before` 用于关键决策点的人类审批

2. **OpenAI Agents SDK 的 Handoff + Guardrails**
   - Handoff 模式适合 DeepFlow 的"路由器 → 专家"架构
   - Guardrails 用于输入/输出验证，防止 Agent 幻觉导致错误操作
   - 轻量级设计哲学：不要过度抽象

3. **MCP 的工具标准化**
   - DeepFlow 的各种工具（飞书 API、数据库、监控系统）可以通过 MCP 标准化
   - 这样不同 Agent 框架都可以复用同一套工具

4. **MAF 的 Magentic 编排**
   - Manager Agent 动态构建任务计划 → 适合 DeepFlow 的"目标分解"需求
   - 但需要在图约束内运行，不能完全放开

### 需要避免的坑

1. **❌ 不要用"对话即编排"（AutoGen 路线）**
   - 过于灵活，难以调试，生产环境不可控
   - 对话历史作为唯一状态管理是脆弱的

2. **❌ 不要让 LLM 完全控制流程**
   - 纯 LLM 控制 = 不可预测 = 无法通过企业审计
   - 必须有代码级的流程约束

3. **❌ 不要忽视错误恢复**
   - Agent 失败是常态，不是异常
   - 必须有 checkpoint + retry + fallback 机制

4. **❌ 不要过早优化"跨 Agent 通信"**
   - A2A 还很早期，大多数场景不需要跨框架 Agent 通信
   - 先把单个框架内的编排做好

### 推荐架构方向

```
┌─────────────────────────────────────────────┐
│           DeepFlow 编排层（混合架构）          │
├─────────────────────────────────────────────┤
│  图编排引擎（类 LangGraph/MAF）               │
│  ├─ 节点 = Agent/Tool/Decision              │
│  ├─ 边 = 条件路由（代码定义）                  │
│  └─ Checkpoint = 每步持久化                   │
├─────────────────────────────────────────────┤
│  Agent 层（LLM 驱动）                        │
│  ├─ 每个 Agent 有明确角色和工具集              │
│  ├─ Agent 内部自主决策                         │
│  └─ Guardrails 约束输入/输出                   │
├─────────────────────────────────────────────┤
│  工具层（MCP 标准化）                         │
│  ├─ 飞书 API / 数据库 / 监控 / 代码执行        │
│  └─ 统一接口，Agent 无关                       │
├─────────────────────────────────────────────┤
│  HITL 层                                    │
│  ├─ 关键决策前 interrupt                      │
│  ├─ 高风险操作需审批                           │
│  └─ 全链路 OpenTelemetry 可观测               │
└─────────────────────────────────────────────┘
```

**核心原则**：代码控骨架，LLM 填血肉，人类把关口。
