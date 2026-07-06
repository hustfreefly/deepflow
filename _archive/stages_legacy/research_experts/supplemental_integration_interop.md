# 工具集成与互操作性专家 研究报告

## 研究范围

本报告针对 Gap Analysis 识别出的 4 条未被深入分析的需求进行补充研究：
- **REQ-008**: 入口通过自然语言对话明确需求（宽松版 Spec Pro）
- **REQ-041**: 忠礼通过飞书或桌面 UI 向 OpenClaw 下达一个目标
- **REQ-079**: 工具集成: openclaw, codex_cli, hermes, claude_code, feishu
- **REQ-030**: Hermes 是对等协作伙伴不是子 Agent

同时回应 Devil's Advocate 指出的隐藏风险：Hermes 对等协作的 message passing 语义未明确，可能存在隐藏依赖。

研究覆盖 5 个核心领域：
1. 自然语言入口（Spec Pro lite）的 intent extraction 与对话式澄清
2. Hermes 对等协作协议的消息传递语义
3. 多工具集成架构的统一 Tool Adapter Interface（UC-008）
4. 外部工具故障隔离（Circuit Breaker / Bulkhead Pattern）
5. Codex CLI / Claude Code 作为外部 coding agent 的协作模式

---

## 发现与分析

### Finding 1: 自然语言入口 - LLM-based Intent Extraction + Slot Filling 架构

#### 1.1 问题定义

REQ-008 和 REQ-041 共同定义了系统的入口机制：用户（姬忠礼）通过飞书或桌面 UI 以自然语言下达目标，系统需要将其转化为结构化的 Goal（living spec）。这不是简单的 NLU 任务，而是一个**对话式需求工程**过程 - 需要在"追问以获取更多信息"和"假设并快速行动"之间取得平衡。

#### 1.2 技术方案：三阶段 Pipeline

**阶段 1: Intent Classification + Entity Extraction**

采用 LLM-based structured output（对应 UC-022 Worker Agent task prompt 结构化 Schema）。定义 Goal Schema 如下：

```json
{
  "goal_id": "auto-generated",
  "objective": "string - one-line summary of user objective",
  "context": "string - background information",
  "constraints": ["string - constraint list"],
  "success_criteria": ["string - success criteria list"],
  "priority": "P0 | P1 | P2",
  "scope": "code | doc | research | mixed",
  "affected_repos": ["string - involved repositories"],
  "dependencies": ["string -前置dependencies"],
  "ambiguities": ["string - points needing clarification"]
}
```

使用 LLM 的 structured output 能力（如 OpenAI 的 response_format 或 Anthropic 的 tool_use）进行 slot filling。关键设计决策：
- **不追求一次性提取所有字段**：初始提取只填充 objective、scope、priority 三个核心字段，其余字段标记为 TBD
- **ambiguities 字段是追问触发器**：LLM 在提取时同时输出"哪些信息缺失或歧义"，作为后续对话策略的输入

**阶段 2: 对话式澄清策略 - Confidence-Threshold Gating**

追问 vs 假设的决策不应硬编码，而应基于 LLM 对自身提取结果的 confidence score 动态判断：

| Confidence | 策略 | 行为 |
|-----------|------|------|
| >= 0.85 | Auto-commit | 直接生成 Goal，显示解析结果供用户确认 |
| 0.60 - 0.85 | Confirm & Proceed | 显示解析结果 + 标注低置信度字段，让用户一键确认或修改 |
| < 0.60 | Clarify | 生成最多 3 个澄清问题（按影响度排序），暂停等待用户回答 |

**关键设计原则**：
- **最多 2 轮澄清**：避免陷入"需求分析瘫痪"。2 轮后仍有歧义的字段，采用"合理默认值 + 显式标注假设"策略
- **可跳过**：用户可以说"直接开始"跳过所有澄清，系统采用最大假设集
- **渐进式细化**：Goal 创建后仍可通过对话修改（living spec 的核心特征）

**阶段 3: Goal 验证与确认**

生成 Goal 后，向用户展示结构化摘要（非 JSON，而是自然语言 + 关键点列表），请求确认。确认方式：
- 飞书：Interactive Card（按钮确认/修改）
- 桌面 UI：确认对话框 + 可编辑字段
- 文本：回复"确认"或提出修改意见

#### 1.3 与 OpenClaw 平台的映射

OpenClaw 当前已有 `sessions_spawn` 的 task 参数作为结构化输入通道。自然语言入口的输出应直接映射为 Goal 对象的初始化参数，通过 Blackboard 的 `goal_management` 阶段写入。

飞书集成已有 `feishu_doc`、`feishu_chat` 等工具。自然语言入口的飞书端实现可复用现有 feishu plugin 的消息接收能力，只需在上游增加 intent extraction pipeline。

#### 1.4 Evidence

- OpenClaw 当前 sessions_spawn 的 task 参数已支持自然语言 task description（见 OpenClaw 系统 prompt 中 sessions_spawn 工具定义）
- Anthropic 的 structured output（tool_use）和 OpenAI 的 response_format 均支持 JSON Schema 约束输出
- Google A2A Protocol 的 Agent Card 采用类似的 capability schema 描述（见 Finding 2）
- 业界实践（如 Linear、Jira AI）普遍采用 2-3 轮对话式澄清而非一次性表单

#### 1.5 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 过度追问导致用户不耐烦 | 用户体验差 | 硬性限制最多 2 轮澄清 |
| LLM 错误假设导致方向偏离 | 浪费执行时间 | Goal 确认步骤 + 执行初期设置方向检查点 |
| 飞书消息格式限制 | 无法展示复杂交互 | 降级为纯文本 + 编号选项 |

---

### Finding 2: Hermes 对等协作协议 - 基于 A2A/MCP 的 Peer-to-Peer Message Passing

#### 2.1 问题定义

REQ-030 明确 Hermes 是"对等协作伙伴不是子 Agent"。Devil's Advocate 指出消息传递语义未明确，可能存在隐藏依赖。核心问题：
- Hermes 与 OpenClaw Loop 的关系是 peer-to-peer 还是 client-server？
- 消息格式是什么？同步还是异步？
- 如何处理超时、重试、幂等性？
- 与 sessions_spawn 的子 Agent 通信有何本质区别？

#### 2.2 Hermes Agent 当前能力（2025-2026 实证）

根据 NousResearch 官方文档和社区进展：

1. **MCP 双模能力**：Hermes 既是 MCP client（调用外部工具）也是 MCP server（暴露自身能力）。这意味着 OpenClaw 可以通过 MCP 协议调用 Hermes 的能力，反之亦然。
2. **A2A 协议支持（开发中）**：NousResearch 正在为 Hermes 集成 Google A2A Protocol（2025 年 4 月发布，6 月捐赠给 Linux Foundation）。A2A 基于 HTTP/JSON-RPC 2.0/SSE，提供 Agent Card（能力发现）、Task 生命周期管理、Message/Part 多模态消息。
3. **内部多 Agent 通信**：Hermes 当前通过 `delegate_task` 工具 spawn 子 agent，这是 client-server 模式，不是 peer-to-peer。真正的 peer collaboration 通过 Telegram 群组等共享消息通道实现。
4. **Kanban 工作流**：Hermes 支持基于 Kanban 的多 agent 任务协调，agent 通过共享看板认领和完成任务。

#### 2.3 推荐协议架构：三层消息传递

**Layer 1: 控制平面（Control Plane） - A2A Protocol**

用于 OpenClaw <-> Hermes 的对等协商：
- **Agent Card 交换**：双方通过 A2A Agent Card 声明各自能力（如 Hermes 的"代码审查"能力、OpenClaw 的"任务分解"能力）
- **Task 协商**：一方发起 `tasks/send` 请求，另一方返回 `tasks/status` 响应。支持 SSE 流式进度更新
- **消息格式**：JSON-RPC 2.0，Message 对象包含多个 Part（text/file/json）
- **超时/重试**：HTTP 层超时 30s，应用层通过 Task 状态机管理长时任务（pending -> in-progress -> completed/failed）

**Layer 2: 数据平面（Data Plane） - Blackboard 共享**

用于结构化的中间产物交换：
- Hermes 将分析结果写入 Blackboard 的特定 stage（如 `hermes_analysis`）
- OpenClaw Loop 将任务上下文写入 Blackboard 的共享 stage
- 双方通过 Blackboard 的读写事件实现松耦合通信

**Layer 3: 事件平面（Event Plane） - 飞书/桌面通知**

用于人类可观测的协作状态：
- 协作进度通过飞书消息/桌面通知推送给用户
- 用户可通过飞书 Interactive Card 介入协作过程

#### 2.4 与 sessions_spawn 的本质区别

| 维度 | sessions_spawn（子 Agent） | Hermes 对等协作 |
|------|---------------------------|----------------|
| 生命周期 | 父 Agent 控制子 Agent 的 spawn/kill | 各自独立生命周期 |
| 状态共享 | 继承父 workspace，通过 context="fork" 共享 transcript | 通过 Blackboard/A2A 显式共享 |
| 通信模式 | 单向 task 下发 + 结果 auto-announce | 双向消息传递，支持协商 |
| 故障影响 | 子 Agent 失败触发父 Agent 的失败决策树 | Hermes 失败不阻塞 OpenClaw Loop（降级继续） |
| 结果质量 | 父 Agent 通过 Gate 验证子 Agent 结果 | 双方各自验证，通过协商达成一致 |

#### 2.5 Devil's Advocate 隐藏依赖分析

Devil's Advocate 指出"Hermes 对等协作的 message passing 语义未明确，可能存在隐藏依赖"。具体分析：

**隐藏依赖 1: 上下文一致性**
- 问题：如果 OpenClaw 和 Hermes 各自维护独立的上下文（对话历史、代码状态），如何保证双方对"当前任务状态"的理解一致？
- 缓解：Blackboard 作为 single source of truth，双方都从 Blackboard 读取最新状态，而非依赖本地缓存

**隐藏依赖 2: 时序假设**
- 问题：A2A 的 SSE 流式更新假设网络连通性。如果 Hermes 在离线状态下完成任务，OpenClaw 如何感知？
- 缓解：引入 Heartbeat 机制。Hermes 每 5 分钟向 Blackboard 写入 heartbeat 时间戳。OpenClaw 超过 15 分钟未收到 heartbeat 则标记 Hermes 为 UNAVAILABLE，触发降级策略

**隐藏依赖 3: 能力漂移**
- 问题：Hermes 的 Agent Card 声明的能力与实际能力可能不一致（如 Hermes 升级后某些能力变更）
- 缓解：OpenClaw 维护 Hermes 能力的历史表现统计（成功率、平均耗时），作为实际能力的 empirical 评估，而非完全信任 Agent Card 的自声明

#### 2.6 Evidence

- Google A2A Protocol specification（2025-04-09, Apache 2.0, Linux Foundation）：HTTP + JSON-RPC 2.0 + SSE + Agent Card
- NousResearch Hermes Agent 文档：MCP client/server 双模、delegate_task 子 agent、Kanban 工作流
- MCP Protocol（Anthropic, 2024-11）：标准化的 tool/data source 连接协议
- OpenClaw 当前 sessions_spawn 工具定义：task/context/mode 参数，subagent runtime，auto-announce 完成机制

---

### Finding 3: 多工具集成架构 - Unified Tool Adapter Interface (UC-008)

#### 3.1 问题定义

REQ-079 要求集成 5 个外部工具：openclaw（自身）、codex_cli、hermes、claude_code、feishu。UC-008 要求设计统一的 Tool Adapter Interface。核心挑战：
- 每个工具有不同的 API 风格（CLI vs HTTP vs MCP vs 飞书 API）
- 能力发现机制不同（静态配置 vs Agent Card vs MCP tool listing）
- 输入/输出格式不统一

#### 3.2 工具集成模式对比

| 模式 | 描述 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|----------|
| **Adapter** | 为每个工具实现一个 Adapter，将外部 API 转换为统一接口 | 解耦、可测试、可替换 | 需要为每个工具写 Adapter | 工具 API 差异大 |
| **Facade** | 在 Adapter 之上提供简化的高层接口 | 使用简单、隐藏复杂性 | Facade 可能过度简化 | 工具组合使用场景 |
| **Proxy** | 透明代理工具调用，增加缓存/日志/限流 | 对调用方透明 | 不够灵活 | 需要统一管控的场景 |

**推荐：Adapter + Facade 混合模式**

- 每个工具一个 **Tool Adapter**（实现统一接口）
- 在 Adapter 之上提供 **Tool Facade**（高层编排接口，支持工具组合）
- 全局 **Tool Registry**（工具注册表，支持动态发现）

#### 3.3 Tool Adapter Interface 设计

```python
class ToolAdapter(Protocol):
    """统一工具适配器接口"""

    @property
    def tool_id(self) -> str:
        """工具唯一标识"""
        ...

    @property
    def capabilities(self) -> list['CapabilityDescriptor']:
        """工具能力描述列表，用于 LLM-based routing"""
        ...

    @property
    def health_status(self) -> 'HealthStatus':
        """工具健康状态，用于 circuit breaker"""
        ...

    async def invoke(self, capability: str, params: dict, context: 'InvocationContext') -> 'ToolResult':
        """调用工具的某个能力"""
        ...

    async def validate(self, result: 'ToolResult') -> 'ValidationResult':
        """验证工具调用结果"""
        ...
```

**CapabilityDescriptor** 设计（参考 A2A Agent Card + MCP tool listing）：

```python
@dataclass
class CapabilityDescriptor:
    name: str                    # 能力名称, e.g. "code_review"
    description: str             # 自然语言描述，供 LLM 理解
    input_schema: dict           # 输入参数 JSON Schema
    output_schema: dict          # 输出结果 JSON Schema
    examples: list[dict]         # 使用示例，few-shot for LLM
    constraints: dict            # 约束: timeout, rate_limit, preconditions
```

#### 3.4 各工具 Adapter 实现策略

| 工具 | 集成方式 | Adapter 实现要点 |
|------|----------|-----------------|
| **openclaw** | 本地进程内调用 | 直接调用 sessions_spawn / exec 等内置工具，Adapter 最薄 |
| **codex_cli** | CLI 子进程（`codex` 命令） | 通过 exec 工具调用 codex CLI，解析 stdout/stderr，支持 `--full-auto` 模式 |
| **hermes** | A2A Protocol (HTTP) + MCP | 通过 HTTP client 发送 JSON-RPC 请求，支持 SSE 流式响应 |
| **claude_code** | CLI 子进程（`claude` 命令）或 SDK | 通过 exec 调用 claude CLI，或通过 Anthropic SDK 的 tool_use，支持 `--print` 模式 |
| **feishu** | 飞书 Open API (HTTP) | 已有 feishu_doc/feishu_chat/feishu_drive 等 plugin，Adapter 封装现有能力 |

#### 3.5 工具发现与 LLM-based Routing

**动态工具注册（Dynamic Tool Registration）**：
- 系统启动时，各 Adapter 向 Tool Registry 注册自身 capabilities
- Hermes 通过 A2A Agent Card 动态发现（HTTP GET `/.well-known/agent.json`）
- MCP 工具通过 MCP tool listing 动态发现
- 注册结果写入 Blackboard 的 `tool_registry` stage

**LLM-based Routing（工具选择）**：
- 将 Tool Registry 中所有 capabilities 的 description 注入 LLM context
- LLM 根据当前任务需求，选择最合适的工具组合
- 对于模糊匹配（如"帮我审查这段代码"可能选 hermes 或 claude_code），LLM 基于以下因素决策：
  - 工具当前健康状态（health_status）
  - 历史成功率（从审计日志统计）
  - 任务类型与工具能力的匹配度
  - 成本（token 消耗、API 调用费用）

#### 3.6 Evidence

- OpenClaw 当前已有 MCP 集成（mcporter skill）：支持 stdio 和 HTTP 两种 MCP server 连接
- OpenClaw sessions_spawn 已支持 subagent runtime，可映射为 openclaw 内部工具调用
- Codex CLI 开源（2025-04），支持 `--full-auto` 无人值守模式，适合作为外部 coding agent
- Claude Code CLI（2025-02 GA）支持 `--print` 非交互模式和 piping，可集成到自动化流程
- A2A Protocol Agent Card 规范：`/.well-known/agent.json` 标准发现端点
- 业界实践：Anthropic 的 Tool Search Tool（2025-11）实现了 LLM 按需发现工具的模式

---

### Finding 4: 外部工具故障隔离 - Circuit Breaker + Bulkhead + Retry Budget

#### 4.1 问题定义

当某个外部工具（如 GitHub API、Hermes、Codex CLI）不可用时，如何：
1. 防止故障级联（一个工具失败拖垮整个系统）
2. 优雅降级（跳过/重试/切换替代工具）
3. 验证工具调用结果的正确性

#### 4.2 Circuit Breaker Pattern for AI Agent Tools

**三态状态机**：

```
CLOSED (normal) --> OPEN (tripped) --> HALF_OPEN (probing) --> CLOSED
```

| 状态 | 行为 | 转换条件 |
|------|------|----------|
| CLOSED | 正常调用，记录失败率 | 5 分钟内失败率 > 50% 则转 OPEN |
| OPEN | 拒绝所有调用，立即返回降级响应 | 等待 60 秒后转 HALF_OPEN |
| HALF_OPEN | 允许 1 次探测调用 | 成功则 CLOSED；失败则 OPEN |

**AI Agent 特有的增强**：
- **质量熔断**：不仅检测 HTTP 错误，还检测结果质量（schema 违规、语义不变量违反）。如果工具返回了"技术上成功但质量不合格"的结果，也计为失败
- **成本熔断**：监控单个工具的累计 token 消耗和 API 费用。超过预算时触发熔断，防止 agent 陷入无限重试循环
- **自适应参数**：失败率阈值和恢复等待时间可根据历史表现动态调整（参考 Meta-Loop 参数调优）

#### 4.3 Bulkhead Pattern (Bulkhead Isolation)

**资源隔离策略**：
- 每个外部工具分配独立的资源池（并发连接数、token 预算、超时时间）
- 工具 A 的资源耗尽不影响工具 B 的可用性
- 实现方式：Python asyncio.Semaphore per tool + 独立的 token budget counter

```python
# 每个工具有独立的信号量和预算
tool_resources = {
    "hermes": {"semaphore": asyncio.Semaphore(2), "token_budget": 500_000},
    "codex_cli": {"semaphore": asyncio.Semaphore(1), "token_budget": 200_000},
    "claude_code": {"semaphore": asyncio.Semaphore(1), "token_budget": 300_000},
    "feishu": {"semaphore": asyncio.Semaphore(5), "token_budget": 50_000},
}
```

#### 4.4 降级策略决策树

当工具调用失败时，LLM 基于以下决策树选择降级策略：

```
工具调用失败
|-- 可重试错误（超时、429 Rate Limit、503）
|   |-- 重试次数 < 3: 指数退避重试（1s, 2s, 4s）
|   +-- 重试次数 >= 3: 触发 Circuit Breaker, 降级
|-- 不可重试错误（400 Bad Request、403 Forbidden、schema 违规）
|   +-- 立即降级
+-- 降级选项（LLM 决策）
    |-- 跳过：该步骤非关键路径，可省略
    |-- 替代工具：选择具有相同能力的替代工具
    |-- 人工介入：通过飞书通知用户，请求手动处理
    +-- 暂停等待：工具暂时不可用，等待恢复后重试
```

#### 4.5 工具调用结果验证

三层验证（复用 UC-003 的 Gate 架构）：
- **Layer 1 确定性检查**：输出 schema 是否符合预期？必填字段是否存在？类型是否正确？
- **Layer 2 LLM 语义检查**：结果是否真正解决了问题？是否与预期方向一致？
- **Layer 3 一致性检查**：结果与其他工具的输出是否矛盾？是否与 Blackboard 中的当前状态一致？

#### 4.6 Evidence

- Circuit Breaker pattern 在 AI Agent 中的 2025 实践：自适应熔断器可根据历史表现调整参数
- Bulkhead pattern（Microsoft Azure Architecture Patterns）：资源池隔离防止级联故障
- OpenClaw 当前 reliability_engineer 专家已提出 MTBF>4h 的目标，故障隔离是其实现前提
- Anthropic 的 Advanced Tool Use（2025-11）：Programmatic Tool Calling 在 sandbox 中执行工具调用，天然支持故障隔离

---

### Finding 5: Codex CLI / Claude Code 集成 - 外部 Coding Agent 协作模式

#### 5.1 问题定义

Codex CLI 和 Claude Code 作为外部 coding agent，如何与 OpenClaw Loop 协作？核心决策：
- 任务委托模式：fire-and-forget vs supervised？
- 结果回传机制：同步等待 vs 异步通知？
- 上下文共享：如何传递代码仓库上下文、任务描述、约束条件？

#### 5.2 Codex CLI 集成方案

**调用方式**：
```bash
# 非交互模式（适合自动化）
codex --full-auto -q "Refactor the auth module to use JWT tokens" --model gpt-5.2-codex

# 带工作目录
cd /path/to/repo && codex --full-auto -q "Fix failing tests in test_auth.py"
```

**任务委托模式：Supervised with Checkpoints**
- 不采用 fire-and-forget（风险太高，coding agent 可能做出不可逆的代码修改）
- 采用 supervised 模式：Codex 在沙箱目录中工作，完成后由 Judge LLM 审查 diff
- 审查通过后，由 OpenClaw 的 exec 工具执行 `git apply` 或 `git merge`

**上下文共享**：
- 通过 task prompt 传递：仓库路径、相关文件列表、编码规范、约束条件
- 通过文件系统共享：Codex 直接访问 workspace 中的代码文件
- 通过 Blackboard 传递结构化约束：如 Zone 0 安全规则（不可修改特定文件）

**结果回传**：
- Codex CLI 的 stdout 包含代码变更的 diff
- 解析 stdout 提取 diff，写入 Blackboard 的 `pending_review` stage
- Judge LLM 审查 diff 后，通过/拒绝/请求修改

#### 5.3 Claude Code 集成方案

**调用方式**：
```bash
# 非交互模式（--print 输出到 stdout）
claude --print "Review this code for security vulnerabilities" < input.py

# 带 MCP 工具
claude --print --mcp-config mcp_servers.json "Analyze the codebase and suggest improvements"

# SDK 方式（更精细控制）
python3 -c "
import anthropic
client = anthropic.Anthropic()
# use tool_use for structured output
"
```

**任务委托模式：Tool-as-a-Service**
- Claude Code 作为"代码分析服务"，接受特定类型的请求（代码审查、安全分析、重构建议）
- OpenClaw 通过 Tool Adapter 调用 Claude Code，传入结构化请求，接收结构化响应
- 适合短任务（< 5 分钟），不适合长时间编码任务

**与 Codex CLI 的分工**：

| 任务类型 | 推荐工具 | 原因 |
|----------|----------|------|
| 代码生成/修改 | Codex CLI | 速度快，适合日常编码 |
| 代码审查/安全分析 | Claude Code | 分析深度更好 |
| 重构建议 | Claude Code | 架构理解能力更强 |
| 测试编写 | Codex CLI | 模式匹配能力强 |
| 复杂 debug | Hermes | 持久记忆，可跨 session 追踪问题 |

#### 5.4 沙箱安全

**关键约束**：外部 coding agent 的代码修改必须在沙箱中执行：
- Codex CLI：在独立的 git worktree 或 tmpdir 中工作
- Claude Code：通过 `--print` 模式只输出建议，不直接修改文件
- 所有修改必须经过 Judge LLM 审查后才能 merge 到主分支
- Zone 0 规则通过 task prompt 传递给外部 agent（如"不得修改 Zone 0 配置文件"）

#### 5.5 Evidence

- Codex CLI 开源（2025-04），支持 `--full-auto` 无人值守模式
- Claude Code CLI（2025-02 GA），支持 `--print` 非交互模式和 piping
- OpenClaw 当前 exec 工具已支持 CLI 子进程调用
- OpenClaw 当前 codegraph 工具可提供代码上下文，可作为传递给外部 agent 的上下文源
- 业界实践：Codex Autofix 在 CI 中自动修复代码，验证了 CLI 集成的可行性

---

## 技术推荐

### 推荐 1: 自然语言入口采用三阶段 Pipeline
- Intent Extraction -> Confidence-Gated Clarification -> Goal Confirmation
- 复用 OpenClaw 现有 sessions_spawn 的 task 参数作为结构化输出通道
- 飞书端通过 Interactive Card 实现确认交互

### 推荐 2: Hermes 对等协作采用 A2A + Blackboard 混合协议
- 控制平面用 A2A Protocol（HTTP + JSON-RPC 2.0 + SSE）
- 数据平面用 Blackboard 共享（结构化中间产物）
- 事件平面用飞书通知（人类可观测性）
- 引入 Heartbeat 机制解决时序假设问题

### 推荐 3: Tool Adapter Interface 采用 Adapter + Facade 混合模式
- 每个工具一个 Adapter（统一接口）
- 上层 Tool Facade 提供编排能力
- Tool Registry 支持动态发现（A2A Agent Card + MCP tool listing）
- LLM-based routing 基于 capability description + health_status + 历史表现

### 推荐 4: 故障隔离采用 Circuit Breaker + Bulkhead + Retry Budget
- 每个工具独立的 Circuit Breaker（三态状态机）
- 资源隔离通过 asyncio.Semaphore per tool 实现
- 降级策略由 LLM 基于决策树选择（跳过/替代/人工/等待）

### 推荐 5: 外部 Coding Agent 采用 Supervised with Checkpoints 模式
- Codex CLI 用于代码生成/修改（速度快）
- Claude Code 用于代码审查/安全分析（分析深度好）
- 所有代码修改在沙箱中执行，经 Judge LLM 审查后 merge
- 通过 task prompt 传递 Zone 0 约束

---

## 风险识别

| 风险 ID | 风险描述 | 概率 | 影响 | 缓解策略 |
|---------|----------|------|------|----------|
| R-001 | Hermes A2A 协议支持尚未 GA，API 可能变更 | 中 | 中 | 设计 A2A Adapter 时预留版本兼容层，优先使用 MCP 作为稳定后备 |
| R-002 | Codex CLI / Claude Code 的 full-auto 模式可能执行不可逆操作 | 中 | 高 | 强制沙箱隔离 + git worktree + Judge LLM 审查 |
| R-003 | LLM-based routing 可能因 prompt injection 选择错误工具 | 低 | 高 | 工具选择结果需通过 Zone 0 安全检查（如不允许选择未注册的工具） |
| R-004 | Circuit Breaker 的自适应参数可能在初期缺乏历史数据 | 高 | 低 | 使用保守默认值（失败率阈值 30%，恢复等待 120s），随运行积累逐步放宽 |
| R-005 | 自然语言入口的 LLM 可能过度追问导致用户放弃 | 中 | 中 | 硬性限制最多 2 轮澄清 + 提供"直接开始"跳过选项 |
| R-006 | 多工具并行调用时的 token 消耗可能超出预算 | 中 | 高 | Bulkhead 模式中每个工具独立的 token budget + 全局 token 硬限 |
| R-007 | Hermes 与 OpenClaw 的上下文不一致导致协作失败 | 中 | 高 | Blackboard 作为 single source of truth + Heartbeat 机制 |

---

## 覆盖需求

covered_req_ids: [REQ-008, REQ-030, REQ-041, REQ-079]

### 需求覆盖详情

| REQ ID | 覆盖 Finding | 覆盖程度 |
|--------|-------------|----------|
| REQ-008 | Finding 1（自然语言入口 Pipeline） | 完整覆盖：intent extraction + slot filling + 对话式澄清 + 验证 |
| REQ-030 | Finding 2（Hermes 对等协作协议） | 完整覆盖：消息传递语义 + 与子 Agent 区别 + 隐藏依赖分析 |
| REQ-041 | Finding 1 + Finding 3（飞书入口 + 工具集成） | 完整覆盖：飞书 Interactive Card 确认 + 目标下达流程 |
| REQ-079 | Finding 3 + 4 + 5（统一 Tool Adapter + 故障隔离 + Coding Agent） | 完整覆盖：5 个工具的集成方案 + 故障隔离 + 协作模式 |

### 关联约束覆盖

| UC ID | 覆盖 Finding |
|-------|-------------|
| UC-008（进度通知自适应分级策略） | Finding 2 的事件平面（飞书通知） |
| UC-020（外部工具集成超时保护和降级策略） | Finding 4（Circuit Breaker + Bulkhead + 降级决策树） |
| UC-022（Worker Agent task prompt 结构化 Schema） | Finding 1（Goal Schema）+ Finding 5（外部 agent 上下文传递） |
