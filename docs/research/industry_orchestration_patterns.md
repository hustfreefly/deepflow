# 业界 Coding Agent 编排模式调研报告

> 调研日期：2026-03-09
> 调研范围：Devin、Factory AI、Cursor/Windsurf、GitHub Copilot Workspace、Amazon Q Developer、Google Jules、开源框架（SWE-agent/OpenDevin/Aider）、多 Agent 协作框架（ChatDev/MetaGPT）

---

## 一、各产品/框架编排模式分析

### 1. Devin (Cognition AI)

#### 架构定位
- **独立引擎**：Devin 是一个完全自主的 AI 软件工程师，运行在独立的沙箱环境中（包含浏览器、CLI、代码编辑器）
- **2025 年演进**：Devin 2.0 引入了专门的 IDE，2025 年 7 月收购 Windsurf，形成"Agent-first 架构"

#### 编排模式
- **单体自主 Agent**：Devin 本身是一个完整的"大脑 + 双手"系统
- **无外部编排器**：Devin 不接受外部编排器的调用，它是独立的执行单元
- **人机协作边界**：
  - 人类：高层架构设计、需求定义、最终审查
  - Devin：规划、编码、测试、部署的全流程执行
  - 关键决策点需要人类确认

#### 核心技术特征
- **大脑**：多模型混合（GPT-4o、Claude 等 + 自研推理引擎）
- **双手**：沙箱化的完整开发环境（bash、编辑器、浏览器）
- **通信**：内部闭环，不暴露 API 供外部编排

#### 长任务管理
- 支持长时间运行的自主任务（小时级别）
- 通过"年度绩效评估"机制自我优化
- 任务失败时能自我反思并调整策略

---

### 2. Factory AI

#### 架构定位
- **平台服务**：Factory 是一个"Agent-driven software development"平台
- **企业级编排**：提供"Command Center"用于管理多个 coding agent

#### 编排模式
- **多 Agent 专业化系统**：
  - Code Droid：代码实现
  - Review Droid：代码审查
  - Knowledge Droid：研究和文档
- **中央编排层**：
  - 统一接口分配角色
  - 任务分发和进度监控
  - 依赖管理

#### 多项目并行处理
- **Git Worktrees 隔离**：每个 agent 独立工作目录，避免冲突
- **角色分配机制**：Frontend/Backend/QA/DevOps/Architect 专业化分工
- **任务管理集成**：与 Linear、Jira 等项目管理工具集成，将 ticket 转化为可执行工作单元

#### 核心技术特征
- **大脑**：LLM 编排器 + 规则引擎混合
- **双手**：多个专业化 coding agent
- **通信**：中央编排器 → Agent 的星型拓扑
- **环境感知**：Agent 能与现有开发工具、可观测性系统、知识库交互

---

### 3. Cursor / Windsurf

#### Cursor IDE

##### 架构定位
- **IDE 内嵌**：VS Code fork，AI 能力内置于 IDE
- **受控自主**：所有 AI 生成的编辑以 diff 形式呈现，需开发者确认

##### 编排模式
- **Cursor 2 多 Agent 编排**（2025 年新特性）：
  - 多个后台 agent 并发运行
  - 实时仪表板监控每个 agent 活动
  - 开发者可随时介入或提供 follow-up
- **上下文管理**：`@codebase` 和 `@files` 标签，手动精确控制 AI 范围
- **Composer 功能**：多文件支持，自动索引 + embeddings 搜索

##### 核心技术特征
- **大脑**：多模型支持（GPT-4o、Claude 3.5/3.7/4.0、Gemini 2.5）
- **双手**：IDE 内嵌的代码编辑 + 终端命令执行
- **通信**：IDE 内部闭环，Agent Mode 需确认后才提交变更

---

#### Windsurf IDE

##### 架构定位
- **Agent-native IDE**：自称"第一个 agent-native IDE"（原 Codeium，2025 年 1 月更名）
- **自主流式**：AI 编辑直接应用于编辑器，无需确认对话框

##### 编排模式
- **Cascade Agent**：
  - 全仓库扫描
  - 智能选择相关文件
  - 自主执行测试和命令
  - 直接修补代码
- **Cascade 2.0**（开发中）：多 agent 协作，一个写代码，另一个审查和基准测试
- **自动上下文检索**：全仓库 embeddings，特别适合 monorepo

##### 核心技术特征
- **大脑**：自研推理模型 + 多模型支持
- **双手**：IDE 内嵌 + 终端执行
- **通信**：IDE 内部闭环，高度自主

---

### 4. GitHub Copilot Workspace

#### 架构定位
- **云端 Agentic 开发环境**：GitHub.com 上的独立开发环境
- **Issue → PR 全流程**：从 GitHub Issue 到 Pull Request 的端到端自动化

#### 编排模式
- **任务导向多步骤流程**：
  1. **任务定义**：从 GitHub Issue 或自然语言描述开始
  2. **规格生成**：生成详细 spec（当前状态 vs 期望状态），开发者可编辑
  3. **计划创建**：基于 spec 生成具体计划（哪些文件创建/修改/删除）
  4. **代码生成和细化**：生成代码变更，开发者可迭代
  5. **PR 创建**：自动生成 PR 摘要并提交

- **Copilot Cloud Agent**（2025 年新特性）：
  - 可分配 issue 给 coding agent
  - Agent 主动规划工作、打开 PR、编写代码、运行测试、请求审查
  - 能响应审查评论和修复失败的 CI 检查

#### 核心技术特征
- **大脑**：GPT-4o（持续评估新模型）
- **双手**：GitHub 生态集成（Issues、PRs、CI/CD）
- **上下文模型**：远程语义索引，全项目搜索（文件、文件夹、符号、函数签名）
- **可引导性**：开发者可在 spec、plan、code 各阶段引导 AI

#### 人机协作边界
- **Human-in-the-Loop**：所有 AI 生成的计划和代码都需开发者审查和确认
- **Token 配额管理**：显示配额计数器，用户可管理使用量

---

### 5. Amazon Q Developer

#### 架构定位
- **AWS 生态深度集成**：AI 对程序员，专注 AWS 应用开发
- **IDE 扩展 + AWS Console**：VS Code、JetBrains IntelliJ 扩展 + 控制台集成

#### 编排模式
- **GitHub 集成编排**：
  - 分配 GitHub issue 给 Q Developer agent
  - Agent 自主探索代码库、提出修复、提交 PR
  - 自动代码审查：分析 PR、识别问题、提供修复建议
- **CI/CD 集成**：
  - 与 GitHub Actions、Jenkins 等集成
  - 自动生成基础设施即代码模板（AWS CodePipeline）
  - 安全扫描和合规检查（"shift-left"安全方法）

#### 核心技术特征
- **大脑**：Amazon Bedrock + 多种基础模型（包括 Claude）
- **双手**：AWS 服务集成 + IDE 扩展
- **通信**：AWS 生态内部闭环

---

### 6. Google Jules

#### 架构定位
- **异步 Coding Agent**：任务型异步 agent（2025 年 5 月公测，2025 年 GA）
- **从 Co-pilot 到 Agent**：从"副驾驶"模式转向更自主的 agent 模式

#### 编排模式
- **任务型异步工作流**：
  1. 开发者分配范围明确的编码任务（修 bug、迁移模块、添加功能、写测试）
  2. Agent 克隆仓库到安全 Google Cloud VM
  3. 分析相关代码库上下文（200 万 token 上下文窗口）
  4. 使用 Gemini Pro 编写分步实施计划
  5. 执行计划（写代码、运行测试、修复错误）
  6. 打开 PR（包含描述、diff、变更摘要）

- **CI/CD 集成**（2026 年愿景）：
  - 自动接收 CI/CD 流水线的错误反馈
  - 分析错误、应用修复、重新推送提交
  - 通常无需人工干预

#### 核心技术特征
- **大脑**：Gemini 3 Flash + Gemini 3.1 Pro
- **双手**：Google Cloud VM + GitHub 集成
- **上下文窗口**：200 万 token（截至 I/O 2026）

---

### 7. 开源框架

#### SWE-agent

##### 架构定位
- **研究型 Agent**：Princeton + Stanford 开发，专注自主解决 GitHub issue
- **ACI 创新**：Agent-Computer Interface，优化 AI 与代码库交互

##### 编排模式
- **单体自主 Agent**：无外部编排，独立执行
- **简化命令集**：通过 ACI 提供简化命令和反馈
- **输出形式**：生成 patch 文件而非明文修复代码

##### 核心技术特征
- **大脑**：LLM（支持多种模型）
- **双手**：ACI 接口 + 代码库交互
- **状态**：维护模式，开发重点转向 mini-swe-agent

---

#### OpenDevin (OpenHands)

##### 架构定位
- **开源 Devin 替代品**：自主 AI 软件工程师
- **端到端自动化**：需求理解 → 规划 → 编码 → 测试 → 调试 → 迭代

##### 编排模式
- **多 Agent 系统**：
  - Developer Agent：编码
  - Executor Agent：安全 shell 和 web 交互
- **核心组件**：Planner、Shell、Scratchpad、Browser、Workspace
- **沙箱化环境**：Docker 容器内执行

##### 核心技术特征
- **大脑**：LLM + 规划引擎
- **双手**：沙箱化完整开发环境
- **通信**：内部闭环，高度自主

---

#### Aider

##### 架构定位
- **终端 AI 结对编程**：直接在开发者终端运行
- **协作助手**：需要更多开发者提示和指导

##### 编排模式
- **单体协作 Agent**：无外部编排，但与开发者紧密协作
- **交互模式**：
  - `/code`：直接编辑
  - `/ask`：问答
  - `/architect`：复杂重构
- **Git 集成**：自动原子提交，tree-sitter 驱动的 repo-map

##### 核心技术特征
- **大脑**：LiteLLM 支持 100+ 模型（OpenAI、Anthropic、Google、Ollama）
- **双手**：终端 + Git + 100+ 编程语言
- **通信**：终端交互，开发者驱动

---

### 8. 多 Agent 编码协作框架

#### ChatDev

##### 架构定位
- **虚拟软件公司**：模拟完整软件团队（CEO、CTO、程序员、测试员、设计师）

##### 编排模式
- **ChatChain 工作流**：
  - 修改版瀑布模型：设计 → 编码 → 测试 → 文档
  - 每个阶段分解为子任务
  - **双 Agent 通信**：每个子任务由 instructor agent + assistant agent 对话完成
- **Communicative Dehallucination**：防止幻觉的通信机制
- **共享内存**：消息、输出、上下文更新存储在共享内存缓冲区

##### ChatDev 2.0 (DevAll)
- **三层架构**：Server、Runtime、Workflow
- **MacNet**：Modular Agent Collaboration Network，支持 DAG（有向无环图）
- **零代码编排平台**：灵活配置 agent 交互

##### 核心技术特征
- **大脑**：LLM（多模型支持）
- **双手**：代码生成 + 测试执行
- **通信**：双 Agent 对话 + 共享内存

---

#### MetaGPT

##### 架构定位
- **SOP 驱动**：集成人类标准操作流程（Standard Operating Procedures）
- **完整软件公司**：产品经理、架构师、项目经理、工程师、QA 工程师

##### 编排模式
- **SOP 编码到 Prompt 序列**：结构化工作流
- **结构化通信协议**：
  - 强调文档和图表输出（而非纯对话）
  - 架构师生成系统接口设计和序列流程图 → 工程师基于此实现
- **全局消息池 + 发布-订阅机制**：
  - 所有 agent 发布输出到全局消息池
  - Agent 根据角色订阅感兴趣的消息类型
  - 高效信息分发，避免直接调用
- **装配线范式**：复杂任务分解 + 专业化 agent 委派
- **分层规划架构**：问题分解为可管理组件

##### 核心技术特征
- **大脑**：LLM + SOP 规则引擎
- **双手**：代码生成 + 文档生成
- **通信**：发布-订阅 + 结构化输出

---

## 二、编排模式分类

基于调研，归纳出 **5 种典型编排模式**：

### 模式 1：单体自主 Agent（Monolithic Autonomous Agent）

**代表**：Devin、OpenDevin、SWE-agent

**特征**：
- 单个 agent 包含完整的"大脑 + 双手"
- 无外部编排器，独立运行
- 内部闭环：规划 → 执行 → 反思 → 迭代
- 沙箱化环境，长时间自主运行

**适用场景**：
- 范围明确的独立任务（修 bug、实现功能）
- 不需要跨 agent 协作
- 可接受较长运行时间（小时级）

**优劣势**：
| 优势 | 劣势 |
|------|------|
| 架构简单，无编排开销 | 单点失败，无冗余 |
| 上下文完整，无跨 agent 通信损耗 | 无法并行处理多个独立子任务 |
| 适合端到端自动化 | 难以扩展到新领域 |

---

### 模式 2：IDE 内嵌多 Agent（IDE-Embedded Multi-Agent）

**代表**：Cursor 2、Windsurf Cascade 2.0

**特征**：
- 多个 agent 在 IDE 内并发运行
- 实时仪表板监控
- 开发者可随时介入
- 上下文管理：`@codebase`、`@files` 标签

**适用场景**：
- 开发者主导的协作开发
- 需要实时反馈和迭代
- 多文件/多模块并行修改

**优劣势**：
| 优势 | 劣势 |
|------|------|
| 开发者保持控制权 | 依赖 IDE 环境 |
| 实时可见性和可干预性 | 难以完全自动化 |
| 利用 IDE 生态（插件、工具） | 跨 IDE 一致性挑战 |

---

### 模式 3：平台化编排（Platform-Based Orchestration）

**代表**：Factory AI、GitHub Copilot Workspace

**特征**：
- 中央编排器管理多个专业化 agent
- 与项目管理工具集成（Linear、Jira、GitHub Issues）
- 任务分解 → 分配 → 监控 → 合并
- Git Worktrees 隔离，避免冲突

**适用场景**：
- 企业级多项目并行
- 需要从 ticket 到 PR 的全流程自动化
- 多 agent 协作完成复杂功能

**优劣势**：
| 优势 | 劣势 |
|------|------|
| 可扩展，支持大规模并行 | 编排复杂度高 |
| 专业化 agent，各司其职 | 需要解决 agent 间冲突 |
| 与现有工作流集成 | 平台锁定风险 |

---

### 模式 4：CI/CD 集成编排（CI/CD-Integrated Orchestration）

**代表**：Amazon Q Developer、Google Jules

**特征**：
- Agent 与 CI/CD 流水线深度集成
- 自动接收 CI 失败反馈并修复
- 异步任务型工作流
- 云环境沙箱化执行

**适用场景**：
- 持续集成/持续部署场景
- 需要自动修复 CI 失败
- 云原生应用开发

**优劣势**：
| 优势 | 劣势 |
|------|------|
| 闭环反馈，自动修复 | 依赖特定云平台 |
| 减少人工干预 | 需要成熟的 CI/CD 基础设施 |
| 适合重复性维护任务 | 复杂架构决策仍需人工 |

---

### 模式 5：角色仿真编排（Role-Simulation Orchestration）

**代表**：ChatDev、MetaGPT

**特征**：
- 模拟软件团队角色（CEO、架构师、工程师、测试员）
- 结构化通信协议（ChatChain、SOP、发布-订阅）
- 共享内存/消息池
- 文档驱动输出（而非纯代码）

**适用场景**：
- 从零开始的全新项目开发
- 需要完整软件生命周期模拟
- 研究和实验性质

**优劣势**：
| 优势 | 劣势 |
|------|------|
| 模拟真实团队协作流程 | 开销大，效率低于单 agent |
| 结构化输出，可追溯性强 | 角色间通信可能引入噪声 |
| 适合复杂项目规划 | 实际代码质量不稳定 |

---

## 三、各模式优劣势对比

| 模式 | 自主性 | 可控性 | 可扩展性 | 复杂度 | 成熟度 | 适用规模 |
|------|--------|--------|----------|--------|--------|----------|
| 单体自主 Agent | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | 小-中 |
| IDE 内嵌多 Agent | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | 中 |
| 平台化编排 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 中-大 |
| CI/CD 集成编排 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中-大 |
| 角色仿真编排 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | 小-中 |

---

## 四、DeepFlow 场景推荐

### 场景描述
**DeepFlow 产出方案 → 编排引擎 → Codex/Claude Code 执行**

- **DeepFlow**：方案产出（需求分析、架构设计、任务分解）
- **编排引擎**：任务分配、进度监控、冲突解决
- **Codex/Claude Code**：代码执行（实际编码、测试、调试）

### 推荐模式：模式 3（平台化编排）+ 模式 4（CI/CD 集成）混合

#### 理由

1. **DeepFlow 作为"大脑"**：
   - 对应平台化编排的"中央编排器"角色
   - 负责高层规划、任务分解、依赖管理
   - 类似 Factory AI 的 Command Center

2. **Codex/Claude Code 作为"双手"**：
   - 对应专业化 coding agent（类似 Factory 的 Code Droid）
   - 接受编排器指令，执行具体编码任务
   - 每个 agent 独立工作目录（Git Worktrees 隔离）

3. **CI/CD 集成**：
   - 自动接收测试失败反馈
   - Agent 自动修复并重新提交
   - 闭环质量保证

#### 架构设计建议

```
┌─────────────────────────────────────────────────────────────┐
│                    DeepFlow 编排引擎                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ 需求分析     │  │ 架构设计     │  │ 任务分解     │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         任务调度器（Task Scheduler）                 │    │
│  │  - 任务分配 → Coding Agent                          │    │
│  │  - 进度监控                                         │    │
│  │  - 冲突解决                                         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Codex Agent  │  │ Claude Agent  │  │  其他 Agent   │
│  (Git Worktree│  │ (Git Worktree │  │  (可扩展)     │
│   隔离)       │  │  隔离)        │  │               │
└───────────────┘  └───────────────┘  └───────────────┘
        ↓                  ↓                  ↓
        └──────────────────┼──────────────────┘
                           ↓
              ┌─────────────────────┐
              │   CI/CD Pipeline    │
              │  - 自动测试         │
              │  - 代码审查         │
              │  - 安全扫描         │
              └─────────────────────┘
                           ↓
                    反馈回编排引擎
```

#### 关键实现要点

1. **任务协议**：
   - DeepFlow 输出结构化任务描述（JSON/YAML）
   - 包含：任务目标、约束条件、验收标准、依赖关系

2. **Agent 隔离**：
   - 每个 Codex/Claude Code 实例独立 Git Worktree
   - 避免文件冲突

3. **进度监控**：
   - Agent 定期上报进度（类似 Factory 的仪表板）
   - 失败时自动重试或上报编排器

4. **CI/CD 集成**：
   - PR 自动创建
   - 测试失败自动反馈给 Agent
   - Agent 自动修复并重新提交

5. **人机协作边界**：
   - 架构决策：DeepFlow + 人类专家
   - 代码审查：自动 + 人类最终确认
   - 合并决策：人类控制

---

## 五、关键洞察：LLM 编排器调 Coding Agent 的成功案例

### 案例 1：Factory AI

**架构**：
- **LLM 编排器**：中央 Command Center，基于 LLM 的任务分解和分配
- **Coding Agent**：Code Droid、Review Droid 等专业化 agent
- **通信**：编排器 → Agent 的星型拓扑

**成功要素**：
- 专业化 agent 各司其职
- Git Worktrees 隔离，避免冲突
- 与 Linear/Jira 集成，任务驱动

---

### 案例 2：OpenAI Symphony

**架构**：
- **项目管理板作为控制平面**：将 Linear/Jira 等工具转化为 agent 编排器
- **Codex Agent**：执行具体编码任务
- **开源**：2025 年开源（https://openai.com/index/open-source-codex-orchestration-symphony/）

**成功要素**：
- 利用现有项目管理工具作为编排器
- 无需构建全新编排系统
- 任务状态自动同步

---

### 案例 3：GitHub Copilot Cloud Agent

**架构**：
- **GitHub Issues 作为任务入口**
- **Copilot Agent**：自主规划、编码、测试、提交 PR
- **CI/CD 集成**：自动响应审查和 CI 失败

**成功要素**：
- 与 GitHub 生态深度集成
- Human-in-the-Loop 设计，开发者保持控制
- 渐进式自主（从建议到自主执行）

---

### 案例 4：Google Jules

**架构**：
- **异步任务型**：开发者分配任务，Agent 异步执行
- **Gemini Pro 规划**：LLM 生成分步实施计划
- **Google Cloud VM 沙箱**：隔离执行环境

**成功要素**：
- 200 万 token 上下文窗口，理解大型代码库
- 异步执行，不阻塞开发者
- 自动 CI 反馈和修复

---

### 案例 5：开源编排器（Composio、Claude Squad、AgentsRoom）

**架构**：
- **通用编排框架**：支持多种 coding agent（Aider、OpenCode、SWE-agent 等）
- **并行执行**：多 agent 并发运行
- **生命周期管理**：启动、监控、终止、处理 CI 失败和审查评论

**成功要素**：
- Agent 无关（agent-agnostic），可插拔
- 开源，可定制
- 社区驱动

---

### 核心洞察总结

1. **"LLM 编排器调 Coding Agent" 已成为主流模式**：
   - Factory AI、OpenAI Symphony、GitHub Copilot Cloud Agent 都采用此模式
   - 编排器负责"想"，Coding Agent 负责"做"

2. **任务管理工具是天然的编排器**：
   - Linear、Jira、GitHub Issues 可作为控制平面
   - 无需从零构建编排系统

3. **隔离是关键**：
   - Git Worktrees 是标准做法，避免多 agent 文件冲突
   - 沙箱化环境（Docker、Cloud VM）保证安全

4. **CI/CD 集成是闭环质量保证的核心**：
   - 自动测试 → 失败反馈 → Agent 修复 → 重新提交
   - 减少人工干预，提高自动化程度

5. **Human-in-the-Loop 仍是必需**：
   - 完全自主的 agent 仍不可靠（Devin 早期成功率个位数到两位数百分比）
   - 关键决策点需要人类确认
   - 渐进式自主（从建议到执行）是更稳妥的路径

6. **专业化 > 通用化**：
   - Factory AI 的 Code Droid / Review Droid / Knowledge Droid 分工
   - 专业化 agent 更可靠，易于优化

---

## 六、对 DeepFlow 的具体建议

### 短期（0-3 个月）

1. **采用"任务管理工具作为编排器"模式**：
   - 利用现有的项目管理工具（如 Linear）作为任务入口
   - DeepFlow 输出任务描述 → 创建 Linear ticket
   - 编排引擎监听 ticket → 分配给 Codex/Claude Code

2. **Git Worktrees 隔离**：
   - 每个 agent 实例独立 worktree
   - 避免文件冲突

3. **CI/CD 集成**：
   - PR 自动创建
   - 测试失败自动反馈给 agent

### 中期（3-6 个月）

1. **构建中央编排器**：
   - 类似 Factory AI 的 Command Center
   - 实时仪表板监控 agent 活动
   - 任务依赖管理和冲突解决

2. **专业化 Agent**：
   - 前端 Agent、后端 Agent、测试 Agent、文档 Agent
   - 每个 agent 针对特定领域优化

3. **渐进式自主**：
   - 初期：agent 提出建议，人类确认
   - 中期：agent 自主执行，人类审查
   - 后期：agent 完全自主（仅限低风险任务）

### 长期（6-12 个月）

1. **多 Agent 协作**：
   - Agent 间可互相审查和验证
   - 类似 Windsurf Cascade 2.0：一个写代码，另一个审查

2. **自优化系统**：
   - Agent 从失败中学习
   - 类似 Devin 的"年度绩效评估"机制

3. **跨项目知识共享**：
   - 全局知识库，agent 可查询历史解决方案
   - 类似 Factory 的 Knowledge Droid

---

## 七、参考资源

### 产品/框架官网
- Devin: https://cognition.ai/
- Factory AI: https://factory.ai/
- Cursor: https://cursor.com/
- Windsurf: https://windsurf.com/
- GitHub Copilot Workspace: https://github.com/features/copilot
- Amazon Q Developer: https://aws.amazon.com/q/developer/
- Google Jules: https://blog.google/innovation-and-ai/models-and-research/google-labs/jules/

### 开源框架
- SWE-agent: https://swe-agent.com/
- OpenDevin: https://github.com/OpenDevin/OpenDevin
- Aider: https://github.com/paul-gauthier/aider
- ChatDev: https://github.com/OpenBMB/ChatDev
- MetaGPT: https://github.com/geekan/MetaGPT
- OpenAI Symphony: https://openai.com/index/open-source-codex-orchestration-symphony/

### 编排器
- Composio Agent Orchestrator: https://composio.dev/
- Claude Squad: https://github.com/anthropics/claude-squad
- AgentsRoom: https://agentsroom.dev/

### 技术文章
- Addy Osmani: "Code Agent Orchestra" - https://addyosmani.com/blog/code-agent-orchestra/
- Redis: "AI Agent Orchestration" - https://redis.io/blog/ai-agent-orchestration/
- IBM: "Multi-Agent Collaboration" - https://www.ibm.com/think/topics/multi-agent-collaboration

---

> **报告完成日期**：2026-03-09
> **调研人**：OpenClaw Subagent
> **版本**：v1.0
