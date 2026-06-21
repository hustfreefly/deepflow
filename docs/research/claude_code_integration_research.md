# Claude Code 集成方式全面调研报告

> 调研日期：2026-06-15
> 数据来源：Anthropic 官方文档 (code.claude.com)、GitHub、社区讨论、技术博客

---

## 目录

1. [Claude Code CLI（命令行集成）](#1-claude-code-cli命令行集成)
2. [Claude Agent SDK（编程集成）](#2-claude-agent-sdk编程集成)
3. [Anthropic Messages API（底层 API）](#3-anthropic-messages-api底层-api)
4. [MCP 协议集成](#4-mcp-协议集成)
5. [Sub-agent 模式与编排](#5-sub-agent-模式与编排)
6. [Agent Loop 内部架构](#6-agent-loop-内部架构)
7. [对比表格](#7-对比表格)
8. [与 Codex 的对比](#8-与-codex-的对比)
9. [推荐方案：项目管理引擎如何指挥 Claude Code](#9-推荐方案项目管理引擎如何指挥-claude-code)

---

## 1. Claude Code CLI（命令行集成）

### 1.1 核心模式

Claude Code CLI 是最直接的集成入口。通过 `-p` / `--print` 标志进入**非交互模式（headless mode）**：

```bash
# 基本用法
claude -p "Find and fix the bug in auth.py" --allowedTools "Read,Edit,Bash"

# 管道输入
cat build-error.txt | claude -p 'concisely explain the root cause' > output.txt

# CI/CD 场景（bare 模式，跳过所有自动发现）
claude --bare -p "Summarize this file" --allowedTools "Read"
```

### 1.2 关键 CLI 参数

| 参数 | 作用 | 适用场景 |
|------|------|----------|
| `-p` / `--print` | 非交互模式，处理完直接输出退出 | 脚本、CI/CD、自动化 |
| `--output-format text` | 纯文本输出（默认） | 人类阅读 |
| `--output-format json` | 结构化 JSON（含 result、session_id、cost） | 程序解析 |
| `--output-format stream-json` | NDJSON 流式输出 | 实时处理 |
| `--json-schema '<schema>'` | 强制输出符合 JSON Schema | 结构化数据提取 |
| `--allowedTools "Read,Edit,Bash"` | 自动批准指定工具 | 免交互审批 |
| `--dangerously-skip-permissions` | 跳过所有权限检查 | 完全自动化（危险） |
| `--bare` | 跳过 hooks/skills/plugins/MCP/CLAUDE.md 自动发现 | CI 环境、快速启动 |
| `--continue` | 恢复上一次会话 | 上下文连续 |
| `--append-system-prompt` | 追加系统提示词 | 自定义行为 |
| `--settings <file-or-json>` | 加载设置文件 | 配置管理 |
| `--mcp-config <file-or-json>` | 加载 MCP 服务器配置 | 外部工具连接 |
| `--agents <json>` | 定义自定义 agent | 子 agent 编排 |
| `--plugin-dir <path>` | 加载插件目录 | 扩展功能 |
| `--verbose --include-partial-messages` | 流式事件详情 | 实时监控 |

### 1.3 输出格式详解

**JSON 输出**（`--output-format json`）包含：
- `result`: 文本结果
- `session_id`: 会话 ID
- `total_cost_usd`: 总费用
- 按模型的费用明细

**Stream JSON 输出**（`--output-format stream-json`）事件类型：
- `system/init`: 会话元数据（模型、工具、MCP 服务器、插件）
- `system/api_retry`: API 重试事件（含 attempt、max_retries、delay、error 类型）
- `plugin_install`: 插件安装进度
- `stream_event` + `text_delta`: 文本增量

**结构化输出**（`--json-schema`）：
```bash
claude -p "Extract function names from auth.py" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}'
# 结果在 .structured_output 字段中
```

### 1.4 沙箱与权限控制

| 控制维度 | 机制 |
|----------|------|
| 工具白名单 | `--allowedTools` 指定可自动批准的工具 |
| 权限模式 | `acceptEdits`（自动批准编辑）、完全跳过 |
|  stdin 限制 | 管道输入上限 10MB（v2.1.128+） |
| 后台任务 | 结果返回后约 5 秒终止后台进程 |
| 退出码 | 0=成功, 1=通用错误, 2=认证错误 |

### 1.5 适用场景

- ✅ CI/CD 管线中的代码审查、lint、文档生成
- ✅ Shell 脚本和 Cron 任务
- ✅ 批量处理（同一 prompt 对多个文件）
- ✅ 构建日志分析
- ✅ Git diff 审查

### 1.6 限制

- ❌ 每次 `-p` 调用默认启动新上下文（`--continue` 可恢复）
- ❌ stdin 10MB 上限
- ❌ 无持久会话状态（需自行管理）
- ❌ 需要安装 Claude Code CLI 环境

---

## 2. Claude Agent SDK（编程集成）

### 2.1 概述

Claude Agent SDK（原名 Claude Code SDK）是 Anthropic 提供的**官方编程集成库**，将 Claude Code 的全部能力（agent loop、工具、上下文管理）封装为可编程库。

| 语言 | 包名 | 安装 |
|------|------|------|
| Python | `claude-agent-sdk` | `pip install claude-agent-sdk` |
| TypeScript | `@anthropic-ai/claude-agent-sdk` | `npm install @anthropic-ai/claude-agent-sdk` |

> **重要**：SDK 内部会 spawn Claude Code CLI 作为子进程，通过 stdio 通信。TypeScript SDK 自带原生二进制文件，无需单独安装 Claude Code。

### 2.2 核心 API

**Python - 单次交互（query）：**
```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    ):
        print(message)

asyncio.run(main())
```

**Python - 多轮会话（ClaudeSDKClient）：**
```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Bash"],
        # cwd="/path/to/project"
    )
) as client:
    async for message in client.send(prompt="Create hello.txt"):
        if message.type == "tool_use":
            print(f"Using tool: {message.tool_name}")
        elif message.type == "text":
            print(f"Response: {message.text}")
```

**TypeScript：**
```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Find and fix the bug in auth.ts",
  options: { allowedTools: ["Read", "Edit", "Bash"] }
})) {
  console.log(message);
}
```

### 2.3 内置工具（20+）

| 工具 | 功能 |
|------|------|
| **Read** | 读取工作目录中的文件 |
| **Write** | 创建新文件 |
| **Edit** | 精确编辑现有文件 |
| **Bash** | 运行终端命令、脚本、git 操作 |
| **Monitor** | 监听后台脚本输出，逐行作为事件响应 |
| **Glob** | 按模式查找文件（`**/*.ts`） |
| **Grep** | 正则搜索文件内容 |
| **WebSearch** | 搜索网页 |
| **WebFetch** | 获取和解析网页内容 |
| **AskUserQuestion** | 向用户提出澄清问题（多选） |
| **Agent** | 调用自定义子 agent |

### 2.4 Hooks（生命周期钩子）

Hooks 是在 agent 生命周期关键点执行自定义代码的机制：

| Hook | 触发时机 |
|------|----------|
| `PreToolUse` | 工具调用前（可拦截/修改/阻止） |
| `PostToolUse` | 工具调用后（可审计/转换） |
| `Stop` | Agent 停止时 |
| `SessionStart` | 会话开始 |
| `SessionEnd` | 会话结束 |
| `UserPromptSubmit` | 用户提交 prompt |

**示例 - 审计文件变更：**
```python
async def log_file_change(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "unknown")
    with open("./audit.log", "a") as f:
        f.write(f"{datetime.now()}: modified {file_path}\n")
    return {}

options = ClaudeAgentOptions(
    permission_mode="acceptEdits",
    hooks={
        "PostToolUse": [
            HookMatcher(matcher="Edit|Write", hooks=[log_file_change])
        ]
    },
)
```

Hook 类型支持：`command`（shell）、`http`（HTTP 请求）、`mcp_tool`（MCP 工具）、`prompt`（单轮 LLM 评估）、`agent`（多轮 agent 验证，实验性）。

### 2.5 子 Agent 定义

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Agent"],
    agents={
        "code-reviewer": AgentDefinition(
            description="Expert code reviewer for quality and security reviews.",
            prompt="Analyze code quality and suggest improvements.",
            tools=["Read", "Glob", "Grep"],
        ),
        "test-writer": AgentDefinition(
            description="Unit test specialist.",
            prompt="Write comprehensive unit tests.",
            tools=["Read", "Write", "Bash"],
        )
    },
)
```

### 2.6 MCP 服务器集成

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]},
        "database": {"command": "python", "args": ["db_mcp_server.py"]},
    }
)
```

### 2.7 认证方式

| 方式 | 环境变量 |
|------|----------|
| Anthropic API | `ANTHROPIC_API_KEY` |
| Amazon Bedrock | `CLAUDE_CODE_USE_BEDROCK=1` + AWS 凭证 |
| Google Vertex AI | `CLAUDE_CODE_USE_VERTEX=1` + GCP 凭证 |
| Azure AI Foundry | `CLAUDE_CODE_USE_FOUNDRY=1` + Azure 凭证 |
| Claude Platform on AWS | `CLAUDE_CODE_USE_ANTHROPIC_AWS=1` |

### 2.8 适用场景

- ✅ 构建自定义 AI agent 应用
- ✅ 将 Claude Code 嵌入现有软件系统
- ✅ 需要精细控制工具权限和生命周期
- ✅ 多 agent 编排系统
- ✅ 需要流式消息处理和结构化输出
- ✅ 生产环境部署

### 2.9 限制

- ❌ Python 3.10+ 要求
- ❌ 内部依赖 Claude Code CLI 子进程
- ❌ 2026-06-15 起，订阅计划的 Agent SDK 使用独立月度额度
- ❌ 不允许第三方产品使用 claude.ai 登录或共享速率限制

---

## 3. Anthropic Messages API（底层 API）

### 3.1 是否有专门的 "Coding Agent" API？

**没有。** Claude Code 底层使用的是标准的 **Messages API** (`POST /v1/messages`) + **Tool Use** 机制。不存在一个独立的 "coding agent API" 端点。

Claude Code 产品 = Messages API + 预定义的系统提示词 + 内置工具集 + Agent Loop + 上下文管理

### 3.2 Messages API + Tool Use 工作流

```
用户 Prompt
    ↓
POST /v1/messages (model + messages + tools + system)
    ↓
Claude 响应 → stop_reason: "tool_use"
    ↓
应用执行工具 → 获取结果
    ↓
POST /v1/messages (追加 tool_result)
    ↓
重复直到 stop_reason: "end_turn"
```

**工具类型：**

| 类型 | 执行方 | 示例 |
|------|--------|------|
| Client-executed（用户定义） | 开发者应用 | 数据库查询、HTTP 调用、文件操作 |
| Server-executed（Anthropic 提供） | Anthropic 基础设施 | Web 搜索、代码执行、Web 获取 |

### 3.3 Programmatic Tool Calling

高级特性：Claude 可以编写 Python 脚本来编排整个工作流，在沙箱代码执行环境中运行。工具结果由脚本处理而非直接消费，显著减少 token 使用和延迟。

### 3.4 Computer Use API

Computer Use 是一个**独立的 beta 功能**，允许 Claude 直接控制鼠标、键盘和屏幕。

- **可以用于编码**：理论上可以通过 GUI 操作 IDE
- **但不是 Claude Code 的方式**：Claude Code 使用专门的代码工具（Read/Edit/Bash），不依赖屏幕控制
- **适用场景**：测试 Web 应用、填写表单、操作无 API 的系统
- **2025 年进展**：Claude for Chrome 允许浏览器控制

### 3.5 其他 API 端点

| API | 用途 |
|-----|------|
| Messages API | 核心对话交互 |
| Message Batches API | 大批量异步处理（成本更低） |
| Token Counting API | 成本和速率管理 |
| Files API (beta) | 文件上传管理 |
| Skills API (beta) | 自定义 agent 技能 |
| Agents API (beta) | 可复用 agent 配置 |
| Sessions API (beta) | 有状态 agent 会话 |
| Environments API (beta) | 沙箱模板配置 |

### 3.6 Extended Thinking

| 级别 | 关键词 | Token 预算 |
|------|--------|-----------|
| 标准 | "think" | ~4,000 |
| 深度 | "think hard" / "megathink" | ~10,000 |
| 超深 | "think harder" / "ultrathink" | ~31,999 |

- 使用内部"scratchpad"进行推理
- 支持交错思考（interleaved thinking）：在工具调用之间推理
- 新模型可能默认启用自适应思考

### 3.7 适用场景

- ✅ 完全自定义 agent 行为（不依赖 Claude Code 的工具集）
- ✅ 需要用自己的工具执行框架
- ✅ 构建自己的 IDE/编辑器集成
- ✅ 需要批量处理大量请求（Batches API）
- ✅ 需要精确控制 token 使用和成本

### 3.8 限制

- ❌ 需要自己实现 agent loop
- ❌ 需要自己管理上下文窗口
- ❌ 需要自己实现工具执行逻辑
- ❌ 没有 Claude Code 的内置代码理解能力（需要自己实现或借助 MCP）

---

## 4. MCP 协议集成

### 4.1 Claude Code 的角色

| 角色 | 支持 | 说明 |
|------|------|------|
| **MCP Client** | ✅ 完整支持 | Claude Code 消费 MCP 服务器暴露的工具 |
| **MCP Server** | ❌ 不支持 | Claude Code 不能作为 MCP 服务器被其他系统调用 |

> **关键发现**：Claude Code 是 MCP 的**消费者**而非**提供者**。如果你想让其他系统调用 Claude Code 的能力，不能通过 MCP 实现，需要用 Agent SDK 或 CLI。

### 4.2 通信协议

- **协议**：JSON-RPC 2.0
- **会话**：有状态（stateful session）
- **传输方式**：
  - **Stdio**：本地服务器（Claude Code spawn 进程，通过 stdin/stdout 通信）
  - **SSE**：远程服务器（HTTP Server-Sent Events）

### 4.3 MCP 暴露的能力

MCP 服务器可以向 Claude Code 暴露：

| 能力类型 | 说明 | 示例 |
|----------|------|------|
| **Tools** | 可执行的工具 | JIRA 操作、Sentry 分析、数据库查询、Figma 设计获取 |
| **Resources** | 上下文数据 | 文件内容、查询结果 |
| **Prompts** | 可复用的提示模板 | 预定义的工作流模板 |

### 4.4 连接流程

1. Claude Code 启动时读取 MCP 配置（`~/.claude/settings.json` 或 `.claude/settings.json`）
2. 连接到每个配置的 MCP 服务器
3. 发送 `initialize` 请求（协议版本 + 能力）
4. 请求 `tools/list` 获取工具列表
5. 当模型判断需要某工具时，路由调用到对应 MCP 服务器

### 4.5 常见 MCP 服务器集成

| 类别 | 服务器 | 功能 |
|------|--------|------|
| 浏览器自动化 | Playwright MCP | 控制浏览器 |
| 数据库 | PostgreSQL MCP | 查询数据库 |
| 项目管理 | JIRA MCP | 操作 Issue |
| 监控 | Sentry MCP | 分析错误 |
| 设计 | Figma MCP | 获取设计稿 |
| 通信 | Gmail/Slack MCP | 发送邮件/消息 |
| Webhook | 自定义 MCP | 响应外部事件 |

### 4.6 配置示例

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]
    }
  }
}
```

### 4.7 适用场景

- ✅ 扩展 Claude Code 的外部系统访问能力
- ✅ 连接数据库、API、第三方服务
- ✅ 标准化集成（一次编写，任何 MCP 客户端可用）
- ✅ 模块化架构（每个服务独立部署）

### 4.8 限制

- ❌ Claude Code 只能作为 client，不能作为 server
- ❌ 需要额外进程运行 MCP 服务器
- ❌ 安全性需考虑（prompt 注入、敏感数据访问）
- ❌ 需要 MCP 网关做集中治理

---

## 5. Sub-agent 模式与编排

### 5.1 内部子 Agent

Claude Code 支持在内部生成子 agent 来处理隔离的子任务：

**特性：**
- 每个子 agent 有独立的上下文窗口、系统提示词、工具访问权限
- 支持并行执行多个子 agent
- 子 agent 只返回结果摘要给父 agent（不污染主上下文）
- 可为不同子 agent 指定不同模型（Opus 做复杂推理，Haiku 做快速执行）

**通过 Agent SDK 定义子 agent：**
```python
agents={
    "code-reviewer": AgentDefinition(
        description="Expert code reviewer.",
        prompt="Analyze code quality.",
        tools=["Read", "Glob", "Grep"],
    ),
    "test-runner": AgentDefinition(
        description="Test execution specialist.",
        prompt="Run and analyze tests.",
        tools=["Bash", "Read"],
    ),
}
```

**通过 CLI 定义子 agent：**
```bash
claude -p "Review the codebase" --agents '{"code-reviewer": {...}}'
```

### 5.2 Headless 模式

Claude Code 的 headless 模式（`-p` 标志）天然支持被外部系统调用：

```bash
# 作为构建脚本的一部分
claude -p "Analyze this PR diff" --output-format json | jq '.result'

# 在 GitHub Actions 中
- run: claude --bare -p "Review this PR" --output-format json --allowedTools "Read,Bash"
```

### 5.3 动态工作流

Claude Code 支持**动态 JavaScript 工作流**，AI 自己可以编写和重新运行编排逻辑：

- 主 agent 作为编排器（orchestrator）
- 决定生成哪个子 agent、分配什么任务
- 管理循环、分支逻辑、中间结果
- 合并子 agent 结果到主上下文

"ultracode" 设置可启用自动规划和工作流执行。

### 5.4 外部系统编排 Claude Code

| 方式 | 被编排能力 | 说明 |
|------|-----------|------|
| CLI (`-p`) | ✅ 高 | 任何 shell 脚本/CI 系统可调用 |
| Agent SDK | ✅ 最高 | Python/TypeScript 程序完全控制 |
| Messages API | ✅ 最高 | 完全自定义 agent loop |
| MCP | ❌ 不支持 | Claude Code 是 client 不是 server |

---

## 6. Agent Loop 内部架构

### 6.1 核心循环

```
┌─────────────────────────────────────────────┐
│                 Agent Loop                   │
│                                              │
│  1. 接收输入（prompt + 历史 + 工具定义）       │
│                    ↓                         │
│  2. Claude 评估当前状态                       │
│                    ↓                         │
│  3. 决策：文本回复 / 工具调用 / 两者兼有       │
│                    ↓                         │
│  4. 如果工具调用：                            │
│     a. 检查权限（hooks PreToolUse）           │
│     b. 执行工具                              │
│     c. 收集结果                              │
│     d. 执行后 hooks（PostToolUse）            │
│     e. 将结果作为 tool_result 追加到历史      │
│     f. 回到步骤 2                            │
│                    ↓                         │
│  5. 如果纯文本回复：任务完成，退出循环          │
│                                              │
└─────────────────────────────────────────────┘
```

### 6.2 上下文管理

| 机制 | 说明 |
|------|------|
| **CLAUDE.md** | 项目级持久化上下文，每次会话自动加载 |
| **层级记忆** | 递归搜索和合并不同目录的 CLAUDE.md |
| **Compaction** | 将长对话压缩为摘要，释放上下文空间 |
| **Memory** | 持久化外部存储，跨会话读写笔记 |
| **子 Agent 隔离** | 子任务在独立上下文窗口中执行 |
| **@imports** | 模块化加载其他 Markdown 文件 |
| **Token 监控** | `/context status` 和 `/context summary` |

**CLAUDE.md 最佳实践：**
- 保持在 200 行以内
- 包含架构、编码规范、常用命令、团队工作流
- 避免包含 Claude 已知的信息
- 每行都消耗 token，保持简洁

### 6.3 自动修复和重试

| 能力 | 机制 |
|------|------|
| API 重试 | 自动重试可恢复的 API 错误，发出 `system/api_retry` 事件 |
| 测试验证 | 修改代码后自动运行测试套件验证 |
| 构建修复 | 检测构建错误并自动修复 |
| 交错思考 | 在工具调用之间进行推理，做出更复杂的决策 |
| 上下文压缩 | 接近上下文窗口限制时自动压缩 |

### 6.4 代码审查能力

- 完整的代码库理解（不需要手动选择上下文）
- 多文件协调修改
- 自动搜索代码模式（Grep/Glob）
- 运行测试验证修改
- Git 操作（diff、commit、PR）
- 通过 hooks 实现确定性审查规则

---

## 7. 对比表格

### 集成方式对比

| 维度 | CLI (`-p`) | Agent SDK | Messages API | MCP |
|------|-----------|-----------|--------------|-----|
| **集成难度** | 低 | 中 | 高 | 中 |
| **控制粒度** | 中 | 高 | 最高 | N/A（被调用方） |
| **编程接口** | Shell | Python/TS | REST API | JSON-RPC |
| **流式输出** | ✅ stream-json | ✅ 消息流 | ✅ SSE | ✅ |
| **结构化输出** | ✅ json-schema | ✅ 原生对象 | ✅ 需自行解析 | N/A |
| **多轮会话** | ✅ --continue | ✅ ClaudeSDKClient | ✅ 自行管理 | N/A |
| **子 Agent** | ✅ --agents | ✅ AgentDefinition | ✅ 自行实现 | ❌ |
| **Hooks** | ❌ | ✅ 回调函数 | ✅ 自行实现 | N/A |
| **MCP 连接** | ✅ --mcp-config | ✅ mcp_servers | ✅ 自行实现 | N/A |
| **工具控制** | --allowedTools | allowed_tools | 自行定义 | N/A |
| **上下文管理** | 自动 | 自动+可定制 | 完全手动 | N/A |
| **费用追踪** | ✅ json 输出 | ✅ 消息内 | ✅ API 响应 | N/A |
| **CI/CD 友好** | ✅ 最佳 | ✅ 好 | ✅ 好 | ❌ |
| **生产部署** | 一般 | ✅ 推荐 | ✅ 推荐 | N/A |

### Claude Code vs Codex 对比

| 维度 | Claude Code | OpenAI Codex CLI |
|------|-------------|------------------|
| **底层模型** | Claude Opus 4.8 / Sonnet 4.6 | GPT-4.1 / o3 / o4-mini |
| **上下文窗口** | 最大 1M tokens | 较小（具体取决于模型） |
| **CLI 非交互模式** | `-p` + `--output-format json` | `codex exec` |
| **SDK** | Agent SDK (Python/TS) | 无官方 SDK（只有 CLI） |
| **Agent Loop** | while loop + tools | 类似 while loop + tools |
| **子 Agent** | ✅ AgentDefinition + Agent tool | ✅ subagents + custom agents |
| **多 Agent 编排** | 动态 JS 工作流 | **Symphony** 开源编排器 |
| **项目管理集成** | 通过 MCP 连接 JIRA 等 | Symphony 直接集成 Linear |
| **MCP 支持** | ✅ 完整 client | ❌ 不支持 |
| **Hooks/生命周期** | ✅ 丰富的 hooks 系统 | ❌ 无 |
| **上下文管理** | CLAUDE.md + compaction + memory | 基本上下文管理 |
| **Extended Thinking** | ✅ 多级思考 | ❌ 无（依赖模型能力） |
| **开源** | ❌ 闭源 | ✅ CLI 开源 |
| **代码库理解** | 自动 agentic search | 需要手动索引或探索 |
| **IDE 集成** | VS Code + JetBrains | VS Code |
| **Computer Use** | ✅ beta（独立功能） | ❌ |
| **被外部编排** | SDK/CLI/API 三种方式 | 主要靠 CLI + Symphony |
| **沙箱控制** | 权限模式 + allowedTools | 沙箱策略 + 审批 |
| **批量任务** | Batches API | Symphony 编排器 |

---

## 8. 与 Codex 的对比：被编排能力深度分析

### 8.1 编排入口

| 方面 | Claude Code | Codex |
|------|-------------|-------|
| **CLI 调用** | `claude -p` + JSON 输出 | `codex exec` |
| **编程 SDK** | ✅ 官方 Agent SDK（Python/TS） | ❌ 无官方 SDK |
| **API 直接调用** | ✅ Messages API + tool use | ✅ Responses API |
| **项目管理系统** | 通过 MCP 或 SDK 间接集成 | Symphony 直接集成 |

### 8.2 关键差异

**Claude Code 的优势：**
1. **Agent SDK 是杀手锏**：提供完整的编程控制，包括 hooks、子 agent 定义、MCP 连接、流式消息
2. **MCP 生态**：可连接数百个外部工具，扩展能力边界
3. **结构化输出**：`--json-schema` 强制输出符合预定义格式
4. **Hooks 系统**：在 agent 生命周期的每个关键点插入确定性逻辑
5. **大上下文窗口**：1M tokens 适合大型代码库分析

**Codex 的优势：**
1. **Symphony 编排器**：开源的、专为项目管理设计的多 agent 编排系统
2. **开源**：可以修改和自定义 CLI 行为
3. **Linear 集成**：与项目管理工具的原生集成
4. **透明性**：agent loop 实现完全可见

### 8.3 "被编排"成熟度评估

| 能力 | Claude Code | Codex |
|------|:-----------:|:-----:|
| 被 shell 脚本调用 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 被编程语言调用 | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 被项目管理系统调用 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 结构化输出 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 多 agent 并行 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 生命周期控制 | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 错误恢复和重试 | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| 成本追踪 | ⭐⭐⭐⭐ | ⭐⭐⭐ |

---

## 9. 推荐方案：项目管理引擎如何指挥 Claude Code

### 9.1 推荐架构

**首选方案：Agent SDK（Python/TypeScript）作为核心集成层**

```
┌──────────────────────────────────────────────────────┐
│                 项目管理引擎                            │
│  (任务分配 / 优先级排序 / 依赖管理 / 进度追踪)           │
└─────────────────────┬────────────────────────────────┘
                      │
                      ↓
┌──────────────────────────────────────────────────────┐
│            Agent SDK 编排层                            │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Task Agent   │  │ Review Agent│  │ Test Agent   │  │
│  │ (编码任务)   │  │ (代码审查)   │  │ (测试验证)   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                      │
│  Hooks: 审计日志 / 权限控制 / 结果验证                  │
│  MCP: JIRA / Slack / 数据库 / 监控系统                 │
└─────────────────────┬────────────────────────────────┘
                      │
                      ↓
┌──────────────────────────────────────────────────────┐
│            Claude Code Agent Loop                     │
│  (工具执行 / 上下文管理 / 自动修复 / 子 agent)          │
└──────────────────────────────────────────────────────┘
```

### 9.2 具体实现建议

#### 方案 A：Agent SDK（推荐）

**优点：**
- 完整的编程控制
- 原生子 agent 支持
- Hooks 实现确定性控制
- 流式消息实时监控
- 结构化输出便于解析

**实现路径：**
```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

# 定义专业化 agent
agents = {
    "implementer": AgentDefinition(
        description="Feature implementation specialist",
        prompt="Implement features following project conventions in CLAUDE.md.",
        tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    ),
    "reviewer": AgentDefinition(
        description="Code quality reviewer",
        prompt="Review code for quality, security, and performance.",
        tools=["Read", "Glob", "Grep"],
    ),
    "tester": AgentDefinition(
        description="Test writing and execution",
        prompt="Write and run tests. Verify all pass.",
        tools=["Read", "Write", "Bash"],
    ),
}

# 编排任务
async def execute_task(task_description, task_type="implementer"):
    results = []
    async for message in query(
        prompt=task_description,
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Write", "Edit", "Bash", "Agent"],
            agents=agents,
            hooks={
                "PostToolUse": [
                    HookMatcher(matcher="Edit|Write", hooks=[audit_and_validate])
                ],
                "Stop": [check_test_coverage],
            },
        ),
    ):
        results.append(message)
    return results
```

#### 方案 B：CLI 集成（简单场景）

**优点：**
- 集成简单
- 适合 CI/CD
- 无需维护 SDK 依赖

**实现路径：**
```bash
# 项目管理引擎通过 shell 调用
claude -p "$TASK_DESCRIPTION" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"status":{"type":"string"},"files_changed":{"type":"array"},"test_results":{"type":"string"}},"required":["status","files_changed"]}' \
  --allowedTools "Read,Write,Edit,Bash" \
  --bare
```

#### 方案 C：Messages API（完全自定义）

**优点：**
- 完全控制 agent loop
- 可实现自定义工具
- 适合构建自己的 IDE 集成

**缺点：**
- 需要自己实现所有基础设施
- 开发成本高

### 9.3 关键设计决策

| 决策点 | 推荐选择 | 理由 |
|--------|----------|------|
| 集成方式 | Agent SDK | 控制力最强，生态最完善 |
| 语言 | Python 或 TypeScript | 两者功能对等，选团队熟悉的 |
| 子 Agent 策略 | 按任务类型定义 | 实现者/审查者/测试者分离 |
| 上下文管理 | CLAUDE.md + 子 agent 隔离 | 项目规范持久化，子任务不污染主上下文 |
| 权限控制 | Hooks + allowedTools | 确定性控制 + 白名单 |
| 输出格式 | JSON Schema | 便于项目管理引擎解析 |
| 监控 | stream-json + Hooks | 实时进度 + 审计日志 |
| 错误处理 | 内置重试 + Hook 拦截 | 自动恢复 + 确定性兜底 |
| MCP 连接 | 按需连接 | JIRA（任务同步）、Slack（通知）、数据库（状态查询） |

### 9.4 不推荐的方案

| 方案 | 不推荐原因 |
|------|-----------|
| MCP 作为集成入口 | Claude Code 是 MCP client 不是 server |
| Computer Use API | 不适合编码任务，效率低下 |
| 纯 Messages API | 需要重新实现 Claude Code 的全部基础设施 |
| 仅 CLI 无 SDK | 缺乏 hooks、子 agent 编程控制 |

---

## 附录：关键资源链接

| 资源 | URL |
|------|-----|
| Claude Code 官方文档 | https://code.claude.com/docs |
| Agent SDK 概览 | https://code.claude.com/docs/en/agent-sdk/overview |
| Headless 模式 | https://code.claude.com/docs/en/headless |
| Agent Loop 详解 | https://code.claude.com/docs/en/agent-sdk/agent-loop |
| MCP 文档 | https://code.claude.com/docs/en/mcp |
| Hooks 指南 | https://code.claude.com/docs/en/hooks-guide |
| CLI 参数参考 | https://code.claude.com/docs/en/cli-reference |
| Agent SDK Python | https://github.com/anthropics/claude-agent-sdk-python |
| Agent SDK Demos | https://github.com/anthropics/claude-agent-sdk-demos |
| Messages API | https://platform.claude.com/docs/en/api/overview |
| Tool Use | https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview |
| Extended Thinking | https://platform.claude.com/docs/en/build-with-claude/extended-thinking |
| MCP 协议规范 | https://modelcontextprotocol.io |

---

*报告完成。本文档基于 2026 年 6 月的公开信息编写，Claude Code 功能迭代快速，建议定期查阅官方文档获取最新信息。*
