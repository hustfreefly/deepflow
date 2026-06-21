# 编排引擎架构选型调研：独立引擎 vs 嵌入式编排

> **调研日期**: 2026-07-13
> **调研目标**: 对比编排引擎的三种架构模式，分析"A 引擎调 B 引擎"的业界案例，给出 DeepFlow 场景的推荐方案
> **状态**: 调研完成

---

## 目录

1. [系统上下文](#1-系统上下文)
2. [三种模式详细对比](#2-三种模式详细对比)
3. ["A 引擎调 B 引擎"案例研究](#3-a-引擎调-b-引擎案例研究)
4. [Loop 实现技术方案](#4-loop-实现技术方案)
5. [推荐方案](#5-推荐方案)
6. [演进路径](#6-演进路径)
7. [参考资料](#7-参考资料)

---

## 1. 系统上下文

```
上游：DeepFlow（产出 Ship Package，包含 Work Packages + AC + Dependencies）
中间：编排引擎（理解方案 → 拆分任务 → 调度执行 → 评估结果 → 循环）
下游：Codex / Claude Code（实际执行编码）
用户：人类（监控、偶尔介入）
```

**核心问题**：中间这个"编排引擎"应该怎么架构？

---

## 2. 三种模式详细对比

### 模式 A：编排引擎嵌入在对话平台内（如 OpenClaw sub-agent）

#### 架构描述

编排逻辑作为对话平台（OpenClaw）的 sub-agent 运行，复用平台的 LLM 调用、工具执行、会话管理能力。编排引擎本质上是平台 Agent 的一个"技能"或"子代理"。

```
┌─────────────────────────────────────────┐
│           OpenClaw Platform             │
│  ┌─────────────────────────────────┐    │
│  │     Main Agent (Orchestrator)   │    │
│  │  ┌─────────┐  ┌─────────────┐  │    │
│  │  │ DeepFlow │  │  编排逻辑    │  │    │
│  │  │ Skill   │  │ (sub-agent) │  │    │
│  │  └─────────┘  └──────┬──────┘  │    │
│  │                      │         │    │
│  │         ┌────────────┼──────┐  │    │
│  │         ▼            ▼      ▼ │    │
│  │    Codex SDK   Claude SDK  ... │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

#### 业界案例

| 案例 | 描述 |
|------|------|
| **OpenClaw sub-agent** | 主 Agent 通过 `sessions_spawn` 创建子 Agent，子 Agent 可调用 Codex/Claude SDK 执行编码任务 |
| **ChatGPT Orchestrator Pattern** | OpenAI 的 orchestrator-subagent 模式，主 Agent 分解任务后委派给专业子 Agent（coder、tester、reviewer） |
| **LangChain Multi-Agent** | LangGraph 中的 supervisor 模式，一个 supervisor agent 调度多个 specialist agent |
| **Microsoft Agent Framework** | 提供 orchestrator-sub-agent 架构模板，主 agent 通过 Task tool 调度子 agent |

#### 优势

| 维度 | 具体优势 |
|------|----------|
| **开发成本** | ⭐⭐⭐⭐⭐ 极低。复用平台的 LLM 调用、会话管理、工具系统、认证体系 |
| **快速验证** | ⭐⭐⭐⭐⭐ 可以在几天内搭建原型并验证核心逻辑 |
| **用户体验** | ⭐⭐⭐⭐ 用户在已有的对话界面中操作，无需新 UI |
| **LLM 能力** | ⭐⭐⭐⭐ 直接借用平台的多模型路由、fallback、缓存能力 |
| **运维负担** | ⭐⭐⭐⭐ 无需独立部署和监控新服务 |

#### 劣势

| 维度 | 具体劣势 |
|------|----------|
| **上下文窗口限制** | 编排逻辑占用主 Agent 的上下文窗口，复杂编排会挤压实际编码的可用上下文 |
| **生命周期耦合** | 编排引擎的生命周期受限于平台会话，平台重启/崩溃 = 编排状态丢失 |
| **并发能力** | 受平台的 sub-agent 数量和并发限制（OpenClaw 默认限制嵌套深度和并发数） |
| **状态持久化** | 平台的会话状态不一定适合长时间运行的编排任务（小时/天级别） |
| **模型选择受限** | 编排逻辑和编码任务可能最适合不同模型，但在同一 Agent 内切换模型有限制 |
| **调试困难** | 编排逻辑混在对话上下文中，难以独立调试和测试 |

#### 天花板分析

- **短期可行**：原型验证、小团队（1-3人）、单次任务 < 30分钟的场景
- **中期瓶颈**：
  - 上下文窗口成为硬约束（编排元数据 + 多轮对话 + 编码结果 = 快速耗尽）
  - 无法支持并行执行多个 Work Package
  - 状态丢失风险随任务时长线性增长
- **长期不可行**：当需要同时编排 5+ 个并行编码任务、每个任务持续数小时，嵌入式架构会达到极限

---

### 模式 B：编排引擎作为独立服务

#### 架构描述

编排引擎是一个独立的进程/服务，有自己的状态管理、持久化、错误恢复机制。通过 API 与上游平台（DeepFlow）和下游执行器（Codex/Claude Code）通信。

```
┌──────────────┐     ┌──────────────────────┐     ┌──────────────┐
│   DeepFlow   │────▶│  编排引擎 (独立服务)   │────▶│  Codex CLI   │
│  (Ship PKG)  │     │  ┌────────────────┐  │     │  Claude Code │
└──────────────┘     │  │ 状态管理器      │  │     │  ...         │
                     │  │ 任务调度器      │  │     └──────────────┘
┌──────────────┐     │  │ 评估引擎        │  │
│   用户 UI    │────▶│  │ 错误恢复器      │  │
│  (监控面板)  │     │  └────────────────┘  │
└──────────────┘     │         │            │
                     │    ┌────▼────┐       │
                     │    │ 持久化层 │       │
                     │    │(Redis/DB)│       │
                     │    └─────────┘       │
                     └──────────────────────┘
```

#### 业界案例

| 案例 | 架构 | 技术栈 |
|------|------|--------|
| **Devin (Cognition)** | Brain (云端无状态服务) + Devbox (沙箱执行环境) | 自研 32B 专用模型 + 知识图谱 + RAG |
| **Factory AI** | Orchestrator Agent + 专业化 Droids (code droid, test droid, knowledge droid) | 多 Agent 编排层 + 隔离沙箱 |
| **OpenAI Codex** | Codex App Server (双向协议) + Cloud Sandbox | Rust CLI + GPT-5-Codex + 异步任务队列 |
| **Claude Code (Anthropic)** | Agent SDK (subprocess 架构) + stdin/stdout JSON-lines 通信 | Python/TypeScript SDK + claude CLI 子进程 |
| **SWE-Agent** | Agent-Computer Interface (ACI) + 独立 Agent Loop | Python + Docker 沙箱 |

#### 技术栈选择分析

| 技术栈 | 适用场景 | 优势 | 劣势 |
|--------|----------|------|------|
| **Python (推荐)** | 快速迭代、AI 生态丰富 | LangChain/LangGraph/Temporal SDK 成熟；与 LLM API 集成最简单；团队已有 Python 经验 | 性能不如 Go/Rust；GIL 限制并发（但 asyncio 可缓解） |
| **Node.js/TypeScript** | 与 OpenClaw 生态集成 | OpenClaw 原生语言；JSON 处理自然；Claude Agent SDK 有 TS 版本 | AI/ML 生态不如 Python |
| **Go** | 高并发、长运行服务 | 天然并发（goroutine）；单二进制部署；内存效率高 | AI 生态较弱；开发速度较慢 |
| **Rust** | 极致性能和可靠性 | 内存安全；零成本抽象 | 开发成本高；AI 生态不成熟 |

**推荐**：**Python + FastAPI + Temporal/Restate** 或 **Python + asyncio + 轻量状态机**

#### 与上层平台的通信方式

| 通信方式 | 适用场景 | 实现复杂度 |
|----------|----------|------------|
| **REST API** | 同步请求-响应；简单任务提交 | ⭐ 低 |
| **WebSocket/SSE** | 实时状态推送；进度监控 | ⭐⭐ 中 |
| **消息队列 (Redis/RabbitMQ)** | 异步任务分发；削峰填谷 | ⭐⭐⭐ 中高 |
| **gRPC** | 高性能内部通信；流式传输 | ⭐⭐⭐ 中高 |
| **文件系统** | Ship Package 传递（大文件/目录） | ⭐ 低 |

**推荐组合**：
- Ship Package 传递 → **文件系统**（已有约定）
- 任务提交/状态查询 → **REST API**
- 实时进度推送 → **SSE (Server-Sent Events)**
- 任务队列 → **Redis** (轻量) 或 **Temporal** (重量级但可靠)

#### 状态管理和持久化

| 方案 | 描述 | 适用规模 |
|------|------|----------|
| **SQLite + 文件锁** | 单文件数据库，零依赖 | 单机、< 10 并发任务 |
| **Redis** | 内存 KV 存储，支持 pub/sub | 单机/小规模集群 |
| **PostgreSQL + 任务表** | 关系型数据库，事务保证 | 中等规模、需要强一致性 |
| **Temporal (推荐)** | 持久化执行平台，自动重试/恢复 | 生产级、需要高可靠 |
| **Restate** | 轻量持久化执行引擎 | 介于 Redis 和 Temporal 之间 |

---

### 模式 C：混合模式（独立进程 + 借用平台 LLM 能力）

#### 架构描述

编排引擎有自己的独立进程和状态管理，但通过 API 调用对话平台（OpenClaw）的 LLM 能力。编排逻辑和 LLM 推理分离。

```
┌──────────────────────────────────────────────────┐
│                  混合架构                         │
│                                                  │
│  ┌────────────────────────────────────────┐      │
│  │        编排引擎 (独立进程)              │      │
│  │  ┌──────────┐  ┌───────────────────┐  │      │
│  │  │ 状态管理  │  │ 任务调度 & 评估    │  │      │
│  │  └──────────┘  └───────────────────┘  │      │
│  │         │              │              │      │
│  │    ┌────▼──────────────▼────┐         │      │
│  │    │    LLM 调用抽象层      │         │      │
│  │    │  (可切换: 直连/平台)   │         │      │
│  │    └────────────┬───────────┘         │      │
│  └─────────────────┼────────────────────┘      │
│                    │                            │
│         ┌──────────┼──────────┐                │
│         ▼          ▼          ▼                │
│    OpenClaw    Claude API   OpenAI API         │
│    LLM API    (直连)       (直连)              │
│                                                  │
│  ┌────────────────────────────────────────┐      │
│  │        执行层 (subprocess)             │      │
│  │  Codex CLI  │  Claude Code  │  ...    │      │
│  └────────────────────────────────────────┘      │
└──────────────────────────────────────────────────┘
```

#### 业界案例

| 案例 | 描述 |
|------|------|
| **Devin** | Brain (独立云服务) 使用自研模型，但 Devbox 可调用外部工具和服务 |
| **Factory AI** | Orchestrator 是独立服务，droids 可使用不同 LLM provider |
| **Claude Agent SDK** | 独立 Python/TS 进程通过 subprocess 调用 claude CLI，CLI 连接 Anthropic API |
| **Temporal + LLM** | Temporal workflow 调用任意 LLM API，状态管理与 LLM 推理完全分离 |
| **LangGraph Platform** | 独立部署的 LangGraph Server，可通过 API 调用不同 LLM provider |

#### 技术可行性分析

| 维度 | 评估 | 说明 |
|------|------|------|
| **LLM 调用抽象** | ✅ 完全可行 | 标准做法：定义统一的 LLM 接口，底层可切换 OpenAI/Anthropic/本地模型 |
| **状态持久化** | ✅ 完全可行 | 独立进程天然支持，可用 Temporal/Restate/自建 |
| **与平台集成** | ✅ 可行 | 通过 API 调用平台的 LLM 能力，或直接调用 LLM provider API |
| **错误恢复** | ✅ 完全可行 | 独立进程可自行实现重试、断点续接 |
| **开发成本** | ⭐⭐⭐ 中等 | 需要自建状态管理，但 LLM 调用部分可复用现有 SDK |

#### 混合模式的关键设计决策

1. **LLM 调用路径**：
   - 方案 A：编排引擎直接调用 Claude/OpenAI API（绕过平台）
   - 方案 B：编排引擎通过平台 API 调用 LLM（借用平台的模型管理）
   - 方案 C：可配置，默认直连，fallback 到平台

2. **状态存储**：
   - 推荐 Temporal（生产级）或 SQLite + 文件（原型阶段）

3. **与 OpenClaw 的关系**：
   - OpenClaw 作为"用户入口"和"监控面板"
   - 编排引擎作为"后端服务"
   - 两者通过 REST API + SSE 通信

---

### 三种模式综合对比矩阵

| 维度 | 模式 A (嵌入式) | 模式 B (独立服务) | 模式 C (混合) |
|------|:---:|:---:|:---:|
| **开发成本** | ⭐⭐⭐⭐⭐ 极低 | ⭐⭐ 较高 | ⭐⭐⭐ 中等 |
| **验证速度** | ⭐⭐⭐⭐⭐ 天级 | ⭐⭐ 周级 | ⭐⭐⭐ 周级 |
| **扩展性** | ⭐⭐ 受限 | ⭐⭐⭐⭐⭐ 无上限 | ⭐⭐⭐⭐ 高 |
| **状态持久化** | ⭐⭐ 弱 | ⭐⭐⭐⭐⭐ 强 | ⭐⭐⭐⭐⭐ 强 |
| **错误恢复** | ⭐⭐ 弱 | ⭐⭐⭐⭐⭐ 强 | ⭐⭐⭐⭐⭐ 强 |
| **并发能力** | ⭐⭐ 受限 | ⭐⭐⭐⭐⭐ 无上限 | ⭐⭐⭐⭐ 高 |
| **调试难度** | ⭐⭐ 困难 | ⭐⭐⭐⭐ 容易 | ⭐⭐⭐⭐ 容易 |
| **运维负担** | ⭐⭐⭐⭐ 低 | ⭐⭐ 较高 | ⭐⭐⭐ 中等 |
| **天花板** | 低 | 极高 | 高 |
| **适合阶段** | 原型验证 | 生产系统 | 渐进演进 |

---

## 3. "A 引擎调 B 引擎"案例研究

### 3.1 核心发现：业界已有成熟的"引擎调引擎"模式

**结论**：业界不仅有"A 引擎调 B 引擎"的案例，而且这正在成为主流架构模式。关键协议和标准已经成熟。

### 3.2 具体案例

#### 案例 1：Claude Agent SDK 调用 Claude CLI（生产级案例）

```
┌─────────────────────┐     stdin/stdout      ┌─────────────────┐
│  Python/TS 应用     │ ◄──── JSON-lines ────▶ │  claude CLI     │
│  (Claude Agent SDK) │     (subprocess)       │  (Agent 引擎)   │
└─────────────────────┘                        └─────────────────┘
        │                                              │
        │ 编程控制                                      │ 连接 Anthropic API
        ▼                                              ▼
   你的业务逻辑                                   LLM 推理 + 工具执行
```

**关键设计**：
- SDK 是"编排引擎"，claude CLI 是"执行引擎"
- 通信方式：subprocess + stdin/stdout + JSON-lines
- 每个 SDK `query()` 调用启动一个独立的 claude CLI 进程
- 进程有自己的内存和执行线程，完全隔离

**对我们的启示**：
- ✅ 这就是我们想要的模式：编排引擎（DeepFlow/自建）调用 Codex/Claude Code
- ✅ Claude Agent SDK 已经提供了现成的集成方式
- ✅ 通信协议简单可靠（JSON-lines over subprocess）

#### 案例 2：OpenAI Codex 的 Agent Loop 架构

```
┌─────────────────────────────────────────────────┐
│              Codex App Server                   │
│  ┌─────────────────────────────────────────┐   │
│  │         双向协议层 (Bidirectional)       │   │
│  │    解耦 Agent 核心逻辑 与 客户端界面     │   │
│  └─────────────────────────────────────────┘   │
│                      │                         │
│         ┌────────────┼────────────┐            │
│         ▼            ▼            ▼            │
│      CLI UI      Web App     VS Code Ext      │
│                                                  │
│  ┌─────────────────────────────────────────┐   │
│  │         Agent Loop (核心)               │   │
│  │  Context Assembly → Model Inference     │   │
│  │  → Decision → Tool Execution → Iterate  │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

**关键设计**：
- Codex App Server 提供统一的双向协议，解耦 Agent 逻辑和客户端
- Agent Loop 是独立的核心模块，可被不同客户端调用
- 支持异步执行：任务可在后台运行数小时
- 支持并行 Agent：多个 Codex 实例同时工作

#### 案例 3：Google A2A (Agent-to-Agent) 协议

```
┌──────────────┐                    ┌──────────────┐
│  Agent A     │   JSON-RPC 2.0     │  Agent B     │
│  (Client)    │ ◄───────────────▶ │  (Remote)    │
│              │   over HTTPS       │              │
│  ┌────────┐  │                    │  ┌────────┐  │
│  │Agent   │  │   SSE (实时流)     │  │Agent   │  │
│  │Card    │  │ ◄──────────────── │  │Card    │  │
│  └────────┘  │                    │  └────────┘  │
└──────────────┘                    └──────────────┘
```

**关键设计**：
- Agent Card：机器可读的能力描述文件（`/.well-known/agent.json`）
- Task 管理：结构化的任务生命周期（pending → in-progress → completed/failed）
- 通信：JSON-RPC 2.0 + SSE + HTTPS
- 认证：API Key / OAuth 2.0 / JWT
- 与 MCP 互补：MCP 管 Agent-to-Tool，A2A 管 Agent-to-Agent

**对我们的启示**：
- ✅ 如果 DeepFlow 编排引擎需要调用多个异构 Agent，A2A 是标准协议
- ✅ Agent Card 机制可以用于发现可用的编码 Agent（Codex、Claude Code 等）
- ✅ Task 生命周期管理是我们需要的核心能力

#### 案例 4：MCP (Model Context Protocol) 在编排中的角色

```
┌─────────────────────────────────────────────────┐
│              MCP 在编排中的角色                   │
│                                                  │
│  ┌──────────┐    MCP     ┌──────────────┐       │
│  │ 编排引擎  │ ◄────────▶ │  MCP Server  │       │
│  │(MCP Client)│  (工具调用) │  - 文件系统   │       │
│  └──────────┘            │  - Git       │       │
│        │                  │  - Docker    │       │
│        │ A2A              │  - CI/CD     │       │
│        ▼                  └──────────────┘       │
│  ┌──────────┐                                    │
│  │ 编码Agent │  ◄── Agent 也可以是 MCP Server    │
│  │(Codex等) │                                    │
│  └──────────┘                                    │
└─────────────────────────────────────────────────┘
```

**MCP 的关键作用**：
1. **Agent-to-Tool 标准化**：编排引擎通过 MCP 访问文件系统、Git、CI/CD 等工具
2. **Agent 即 Server**：编码 Agent（如 Claude Code）本身可以作为 MCP Server，暴露其能力
3. **可组合性**：新的工具/Agent 只需实现 MCP Server 即可被编排引擎调用

### 3.3 案例总结

| 模式 | 代表案例 | 通信方式 | 适用场景 |
|------|----------|----------|----------|
| **SDK 调用 CLI** | Claude Agent SDK → claude CLI | subprocess + stdin/stdout | 单机、同语言生态 |
| **App Server 模式** | Codex App Server → Agent Loop | 双向协议（内部） | 多客户端、统一入口 |
| **A2A 协议** | Google A2A | JSON-RPC + SSE + HTTPS | 跨组织、异构 Agent |
| **MCP** | Anthropic MCP | JSON-RPC | Agent-to-Tool 标准化 |
| **混合** | Devin / Factory AI | 多种组合 | 生产级复杂系统 |

---

## 4. Loop 实现技术方案

### 4.1 Agent Loop 核心模式

业界主流的 Agent Loop 实现都遵循 **ReAct (Reason + Act)** 模式：

```
┌─────────────────────────────────────────────────────┐
│                  Agent Loop                         │
│                                                      │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│   │ Context  │───▶│  Model   │───▶│ Decision │     │
│   │ Assembly │    │ Inference│    │ & Action │     │
│   └──────────┘    └──────────┘    └────┬─────┘     │
│        ▲                               │            │
│        │          ┌──────────┐         │            │
│        │          │  Tool    │◄────────┘            │
│        └──────────│ Execution│                      │
│     (观察结果)     └──────────┘                      │
│                                                      │
│   终止条件:                                          │
│   - 模型输出最终消息（不再请求工具调用）              │
│   - 达到最大迭代次数                                  │
│   - 检测到目标完成                                    │
│   - 检测到停滞（连续 N 次无进展）                    │
└─────────────────────────────────────────────────────┘
```

### 4.2 长时间 Loop 的 Token 管理策略

#### 问题：Token 消耗随 Loop 轮次二次增长

 naive 的 Agent Loop 每轮都发送完整对话历史，导致：
- 20 轮 Loop 可能消耗超过 10 倍于单轮的 token
- 上下文窗口被历史对话填满，挤压可用空间
- "Lost-in-the-Middle" 问题：LLM 难以检索长上下文中间的信息

#### 业界解决方案

| 策略 | 描述 | 效果 | 实现复杂度 |
|------|------|------|------------|
| **自动压缩 (Auto-Compaction)** | 当上下文接近窗口限制时，自动压缩历史对话（保留关键信息，丢弃细节） | ⭐⭐⭐⭐ | ⭐⭐ |
| **分层摘要 (Hierarchical Summarization)** | 将历史对话分层摘要：近期详细、远期概要 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **RAG 检索** | 将历史存入向量数据库，每轮只检索最相关的片段 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Scope Limiting** | 每轮只发送当前步骤需要的上下文，而非全部历史 | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Memory-First Design** | 结构化记忆层：Agent 主动记住关键发现，丢弃无关信息 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Prompt Caching** | 利用 LLM API 的 prompt caching（如 Anthropic 的 cache）减少重复计算 | ⭐⭐⭐ (成本) | ⭐ |

#### 推荐组合策略

```
┌─────────────────────────────────────────────────┐
│              Token 管理策略栈                    │
│                                                  │
│  Layer 1: Scope Limiting (每轮只发必要上下文)    │
│  Layer 2: Auto-Compaction (接近窗口时压缩)       │
│  Layer 3: Structured Memory (关键发现持久化)     │
│  Layer 4: Prompt Caching (减少重复 token 成本)   │
└─────────────────────────────────────────────────┘
```

### 4.3 错误恢复和断点续接

#### 错误类型分类

| 错误类型 | 示例 | 恢复策略 |
|----------|------|----------|
| **瞬时错误** | 网络超时、API 限流 (429) | 自动重试 + 指数退避 |
| **LLM 错误** | 模型拒绝、输出格式错误 | 重试 / 换模型 / 调整 prompt |
| **工具执行错误** | 命令失败、文件不存在 | LLM 分析错误 → 调整策略重试 |
| **上下文溢出** | Token 超限 | 压缩上下文 / 路由到更大窗口模型 |
| **基础设施错误** | 进程崩溃、机器重启 | 从 checkpoint 恢复 |
| **逻辑错误** | 无限循环、停滞 | 检测停滞 → 人工介入 / 回退 |

#### 业界最佳实践

**1. Durable Execution (持久化执行)**

```python
# Temporal Workflow 示例
@workflow.defn
class CodingTaskWorkflow:
    @workflow.run
    async def run(self, task: CodingTask):
        # 每个步骤自动持久化，崩溃后自动恢复
        plan = await workflow.execute_activity(create_plan, task)
        
        for work_package in plan.packages:
            # 即使这里崩溃，恢复后从上次完成的 package 继续
            result = await workflow.execute_activity(
                execute_work_package, work_package
            )
            
            # 评估结果，如果需要重试则重试
            evaluation = await workflow.execute_activity(
                evaluate_result, result
            )
            
            if evaluation.needs_retry:
                result = await workflow.execute_activity(
                    execute_work_package, work_package, 
                    retry_context=evaluation.feedback
                )
```

**2. Checkpoint 机制**

```python
# 轻量级 checkpoint（不依赖 Temporal）
class CheckpointManager:
    def save_checkpoint(self, task_id, state):
        checkpoint = {
            "task_id": task_id,
            "current_step": state.current_step,
            "completed_packages": state.completed,
            "failed_packages": state.failed,
            "llm_conversation_summary": state.summary,  # 压缩后的对话
            "timestamp": time.time()
        }
        # 原子写入
        with open(f"checkpoints/{task_id}.json", "w") as f:
            json.dump(checkpoint, f)
    
    def load_checkpoint(self, task_id):
        path = f"checkpoints/{task_id}.json"
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return None
```

**3. 错误传播与 LLM 推理恢复**

```
工具执行失败
    │
    ▼
结构化错误报告（错误类型 + 上下文 + 已尝试的方案）
    │
    ▼
LLM 分析错误原因
    │
    ├── 可重试 → 调整参数重试
    ├── 可换路径 → 选择替代工具/方案
    ├── 需要信息 → 请求更多上下文
    └── 无法解决 → 上报人工介入
```

**4. Guardrails（防护栏）**

| Guardrail | 描述 | 阈值建议 |
|-----------|------|----------|
| **最大迭代次数** | 防止无限循环 | 50-100 次/任务 |
| **Token 预算断路器** | 超过预算自动停止 | 根据任务复杂度设定 |
| **停滞检测** | 连续 N 次无进展则停止 | N=5-10 |
| **时间超时** | 任务总时长上限 | 根据 SLA 设定 |
| **成本上限** | 单次任务最大花费 | 根据业务价值设定 |

### 4.4 实现方案对比

| 方案 | 技术栈 | 持久化 | 错误恢复 | 开发成本 | 推荐场景 |
|------|--------|--------|----------|----------|----------|
| **轻量 Loop** | Python + asyncio | SQLite checkpoint | 手动重试 | ⭐⭐⭐⭐⭐ 低 | 原型阶段 |
| **Temporal** | Python + Temporal Server | 内置 | 自动 | ⭐⭐ 高 | 生产级 |
| **Restate** | Python + Restate Server | 内置 | 自动 | ⭐⭐⭐ 中 | 中等规模 |
| **LangGraph** | Python + LangGraph | Checkpoint | 部分自动 | ⭐⭐⭐ 中 | 复杂图逻辑 |

---

## 5. 推荐方案

### 5.1 核心推荐：分阶段演进

**不推荐一步到位选择最复杂的方案。** 推荐渐进式演进：

```
Phase 1 (现在)          Phase 2 (验证后)         Phase 3 (规模化)
─────────────          ──────────────          ──────────────
模式 A                 模式 C                   模式 B
嵌入式编排              混合模式                 独立服务
OpenClaw sub-agent     独立进程 + LLM API       Temporal + 多 Agent
                      
开发周期: 1-2 周        开发周期: 2-4 周         开发周期: 4-8 周
```

### 5.2 Phase 1 详细设计（立即可执行）

#### 架构

```
┌─────────────────────────────────────────────────────────┐
│                    OpenClaw Platform                     │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Main Agent (DeepFlow Orchestrator)  │   │
│  │                                                   │   │
│  │  Skills:                                          │   │
│  │  - deepflow-parser: 解析 Ship Package             │   │
│  │  - task-planner: 拆分 Work Packages → 执行计划    │   │
│  │  - executor-dispatcher: 调度 Codex/Claude Code    │   │
│  │  - result-evaluator: 评估执行结果                  │   │
│  │                                                   │   │
│  │  Sub-agents (并行执行):                           │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐            │   │
│  │  │Worker 1 │ │Worker 2 │ │Worker 3 │            │   │
│  │  │(Codex)  │ │(Claude) │ │(Codex)  │            │   │
│  │  └─────────┘ └─────────┘ └─────────┘            │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  状态文件: .deepflow/state/{task_id}.json               │
└─────────────────────────────────────────────────────────┘
```

#### 核心组件

1. **Ship Package Parser**
   - 输入：DeepFlow 产出的 Ship Package 目录
   - 输出：结构化的 Work Packages 列表 + Dependencies 图

2. **Task Planner**
   - 输入：Work Packages + Dependencies
   - 输出：执行计划（拓扑排序后的执行顺序，可并行的分组）

3. **Executor Dispatcher**
   - 输入：单个 Work Package + 执行上下文
   - 动作：通过 Claude Agent SDK / Codex SDK 启动编码任务
   - 输出：执行结果（代码变更 + 测试报告）

4. **Result Evaluator**
   - 输入：执行结果 + AC (Acceptance Criteria)
   - 动作：检查 AC 是否满足、运行测试、评估代码质量
   - 输出：通过/失败 + 反馈（如果失败）

5. **Loop Controller**
   - 驱动整个循环：Plan → Execute → Evaluate → (Retry/Complete)
   - 管理状态持久化到文件
   - 处理错误恢复

#### 状态文件格式

```json
{
  "task_id": "ship-2026-07-13-001",
  "status": "in_progress",
  "ship_package": {
    "name": "user-auth-feature",
    "work_packages": [
      {
        "id": "wp-1",
        "name": "implement-login-api",
        "status": "completed",
        "assigned_to": "claude-code",
        "attempts": [
          {
            "timestamp": "2026-07-13T10:00:00Z",
            "result": "failed",
            "feedback": "Missing error handling for invalid credentials"
          },
          {
            "timestamp": "2026-07-13T10:30:00Z",
            "result": "passed",
            "artifacts": ["src/api/login.ts", "tests/login.test.ts"]
          }
        ]
      },
      {
        "id": "wp-2",
        "name": "implement-session-management",
        "status": "in_progress",
        "depends_on": ["wp-1"],
        "assigned_to": "codex",
        "attempts": []
      }
    ]
  },
  "checkpoint": {
    "last_updated": "2026-07-13T10:30:00Z",
    "completed_wps": ["wp-1"],
    "current_wp": "wp-2",
    "llm_context_summary": "..."
  }
}
```

### 5.3 Phase 2 演进触发条件

当以下任一条件满足时，应演进到 Phase 2（混合模式）：

- [ ] 单个 Ship Package 包含 5+ 个 Work Packages
- [ ] 需要并行执行 3+ 个编码任务
- [ ] 单次编排任务持续超过 1 小时
- [ ] 出现状态丢失导致的工作重复
- [ ] 上下文窗口成为瓶颈（编排元数据 + 编码结果 > 可用窗口）

### 5.4 Phase 2 架构预览

```
┌──────────────────────────────────────────────────────┐
│                  混合模式架构                         │
│                                                       │
│  ┌────────────────────────────────────────────┐      │
│  │        编排引擎 (独立 Python 进程)          │      │
│  │                                             │      │
│  │  技术栈:                                    │      │
│  │  - FastAPI (API 服务)                       │      │
│  │  - asyncio (并发执行)                       │      │
│  │  - SQLite/PostgreSQL (状态持久化)           │      │
│  │  - Claude Agent SDK (调用 Claude Code)      │      │
│  │  - OpenAI SDK (调用 Codex)                  │      │
│  │                                             │      │
│  │  API:                                       │      │
│  │  POST /tasks        - 提交编排任务          │      │
│  │  GET  /tasks/{id}   - 查询任务状态          │      │
│  │  GET  /tasks/{id}/events - SSE 实时进度     │      │
│  │  POST /tasks/{id}/cancel - 取消任务         │      │
│  └────────────────────────────────────────────┘      │
│                       │                               │
│         ┌─────────────┼─────────────┐                │
│         ▼             ▼             ▼                │
│    Claude Code    Codex CLI     其他 Agent           │
│    (via SDK)      (via SDK)     (via A2A/MCP)        │
│                                                       │
│  ┌────────────────────────────────────────────┐      │
│  │        OpenClaw (用户入口 & 监控)           │      │
│  │  - 提交任务到编排引擎 API                   │      │
│  │  - 通过 SSE 展示实时进度                    │      │
│  │  - 人工介入接口                            │      │
│  └────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────┘
```

---

## 6. 演进路径

### 6.1 Phase 1 → Phase 2 可行性分析

**结论：完全可行，且是推荐路径。**

| 维度 | 分析 |
|------|------|
| **代码复用** | Phase 1 的核心逻辑（Task Planner、Executor Dispatcher、Result Evaluator）可以直接迁移到 Phase 2 的独立进程中 |
| **状态格式** | Phase 1 的状态文件格式可以设计成与 Phase 2 兼容，平滑迁移 |
| **接口约定** | Phase 1 的组件接口在 Phase 2 中保持不变，只是运行环境从 sub-agent 变为独立进程 |
| **风险** | 极低。Phase 1 是 Phase 2 的"子集"，演进是"提取"而非"重写" |

### 6.2 演进路径图

```
Week 1-2: Phase 1 (MVP)
────────────────────────
✓ 在 OpenClaw 中实现编排 Skill
✓ 支持串行执行 Work Packages
✓ 状态持久化到文件
✓ 基本的错误重试
✓ 验证核心循环逻辑

Week 3-4: Phase 1.5 (增强)
────────────────────────────
✓ 支持并行执行 (通过 sub-agents)
✓ 改进 Token 管理 (auto-compaction)
✓ 结构化记忆 (关键发现持久化)
✓ 更智能的 Result Evaluator
✓ 识别 Phase 1 的天花板

Week 5-8: Phase 2 (独立服务)
─────────────────────────────
✓ 提取核心逻辑到独立 Python 进程
✓ FastAPI 服务 + REST API
✓ SQLite → PostgreSQL (可选)
✓ Claude Agent SDK 集成
✓ SSE 实时进度推送
✓ OpenClaw 作为用户入口

Week 9+: Phase 3 (生产级, 按需)
────────────────────────────────
□ Temporal 集成 (如果需要持久化执行)
□ A2A 协议支持 (如果需要跨组织 Agent 协作)
□ 多租户支持
□ 监控和可观测性
□ 自动扩缩容
```

### 6.3 关键迁移步骤

从 Phase 1 迁移到 Phase 2 的具体步骤：

1. **抽象接口层**
   ```python
   # Phase 1 中就定义好接口，Phase 2 直接实现
   class OrchestrationEngine(Protocol):
       def submit_task(self, ship_package: ShipPackage) -> TaskID: ...
       def get_status(self, task_id: TaskID) -> TaskStatus: ...
       def cancel_task(self, task_id: TaskID) -> None: ...
   ```

2. **状态存储抽象**
   ```python
   # Phase 1: 文件存储
   class FileStateStore(StateStore):
       def save(self, state: TaskState) -> None: ...
   
   # Phase 2: 数据库存储（实现相同接口）
   class DBStateStore(StateStore):
       def save(self, state: TaskState) -> None: ...
   ```

3. **执行器抽象**
   ```python
   # Phase 1: 直接调用 SDK
   class DirectExecutor(CodeExecutor):
       def execute(self, work_package: WorkPackage) -> ExecutionResult: ...
   
   # Phase 2: 通过 API 调用远程执行器
   class RemoteExecutor(CodeExecutor):
       def execute(self, work_package: WorkPackage) -> ExecutionResult: ...
   ```

---

## 7. 参考资料

### 业界产品和架构

| 产品/项目 | 架构特点 | 参考链接 |
|-----------|----------|----------|
| **Devin (Cognition)** | Brain + Devbox 双组件；专用 32B 模型；知识图谱 + RAG | https://docs.devin.ai |
| **Factory AI** | Orchestrator + 专业化 Droids；隔离沙箱 | https://factory.ai |
| **OpenAI Codex** | App Server + Agent Loop；Rust CLI；异步任务 | https://openai.com/index/unrolling-the-codex-agent-loop/ |
| **Claude Code SDK** | subprocess 架构；stdin/stdout JSON-lines | https://code.claude.com/docs/en/agent-sdk/hosting |
| **OpenClaw** | sub-agent 编排；Skills 系统；多模型路由 | https://docs.openclaw.ai |

### 协议和标准

| 协议 | 用途 | 参考 |
|------|------|------|
| **MCP (Model Context Protocol)** | Agent-to-Tool 标准化 | https://modelcontextprotocol.io |
| **A2A (Agent-to-Agent)** | Agent 间发现和任务委派 | https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/ |
| **JSON-RPC 2.0** | 结构化 RPC 通信 | https://www.jsonrpc.org |

### 持久化执行框架

| 框架 | 特点 | 适用场景 |
|------|------|----------|
| **Temporal** | 生产级、强一致、可视化 | 需要高可靠的生产系统 |
| **Restate** | 轻量、易集成、Virtual Objects | 中等规模、快速迭代 |
| **LangGraph** | 图结构、Checkpoint | 复杂编排逻辑 |

### 设计模式

| 模式 | 描述 | 参考 |
|------|------|------|
| **Orchestrator-Subagent** | 主 Agent 调度专业子 Agent | Microsoft Agent Framework |
| **ReAct** | Reason + Act 循环 | Codex Agent Loop |
| **Plan-Then-Execute** | 先生成计划，再逐步执行 | LangGraph |
| **Durable Execution** | 自动 checkpoint + 恢复 | Temporal / Restate |

---

## 附录：决策检查清单

在最终选择架构时，逐项确认：

- [ ] **当前阶段目标是什么？** 原型验证 → Phase 1；生产系统 → Phase 2/3
- [ ] **团队规模和技术栈？** 小团队 Python → Phase 1/2；有专职后端 → Phase 2
- [ ] **任务复杂度？** 单任务 < 30min → Phase 1；多任务并行数小时 → Phase 2
- [ ] **可靠性要求？** 实验性 → Phase 1；生产级 → Phase 2 + Temporal
- [ ] **预算约束？** 低成本 → Phase 1（复用平台）；可投入 → Phase 2
- [ ] **演进计划？** 明确 Phase 1 → Phase 2 路径；预留抽象接口

---

*报告完成。建议立即开始 Phase 1 实现，在 1-2 周内验证核心编排逻辑。*
