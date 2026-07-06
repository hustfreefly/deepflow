# OpenAI Codex 集成方式全面调研报告

**调研日期**: 2026-06-15  
**调研范围**: Codex CLI、App Server、MCP Server、Cloud API、Agent Loop

---

## 目录

1. [Codex CLI (`codex exec`)](#1-codex-cli-codex-exec)
2. [Codex App Server](#2-codex-app-server)
3. [Codex MCP Server](#3-codex-mcp-server)
4. [Codex Cloud / API](#4-codex-cloud--api)
5. [Codex Agent Loop 架构](#5-codex-agent-loop-架构)
6. [对比表格](#6-对比表格)
7. [推荐方案：项目管理引擎](#7-推荐方案项目管理引擎)
8. [关键发现与隐藏能力](#8-关键发现与隐藏能力)

---

## 1. Codex CLI (`codex exec`)

### 1.1 概述

`codex exec` 是 Codex CLI 的非交互模式，专为脚本化执行、CI/CD 集成和自动化工作流设计。它允许在不打开交互式 TUI 的情况下运行 Codex。

### 1.2 完整命令行参数和选项

#### 核心参数

```bash
codex exec [OPTIONS] <PROMPT>
codex exec -                    # 从 stdin 读取完整 prompt
codex exec resume --last        # 恢复上一次会话
codex exec resume <SESSION_ID>  # 恢复指定会话
```

#### 主要选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `--json` | 输出 JSONL 格式的事件流 | `codex exec --json "分析代码"` |
| `--output-schema <path>` | 指定 JSON Schema 生成结构化输出 | `codex exec --output-schema schema.json` |
| `-o, --output-last-message <path>` | 将最终消息写入文件 | `codex exec -o result.md` |
| `--sandbox <policy>` | 设置沙箱模式 | `--sandbox workspace-write` |
| `--ephemeral` | 不持久化会话文件 | `codex exec --ephemeral` |
| `--ask-for-approval <mode>` | 设置审批模式 | `--ask-for-approval never` |
| `--cd <path>` / `-C <path>` | 设置工作目录 | `codex exec --cd /path/to/project` |
| `-c key=value` | 覆盖配置值 | `-c model=gpt-5.4` |
| `--ignore-user-config` | 不加载用户配置 | 用于受控环境 |
| `--ignore-rules` | 跳过 execpolicy 规则 | 用于自动化 |
| `--skip-git-repo-check` | 跳过 Git 仓库检查 | 非 Git 环境使用 |

### 1.3 输入输出格式

#### 输入方式

1. **直接参数**: `codex exec "你的指令"`
2. **stdin 管道 + 参数**: 
   ```bash
   npm test 2>&1 | codex exec "分析失败的测试"
   ```
3. **stdin 作为完整 prompt**:
   ```bash
   cat prompt.txt | codex exec -
   ```

#### 输出格式

**标准输出 (stdout)**:
- 默认：仅输出最终的 agent 消息
- `--json` 模式：输出 JSONL 事件流

**标准错误 (stderr)**:
- 实时进度信息（命令执行、文件变更等）

**JSONL 事件类型**:

```jsonl
{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"bash -lc ls","status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"分析结果..."}}
{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122}}
```

**Item 类型**:
- `agent_message`: Agent 消息
- `reasoning`: 推理过程
- `command_execution`: 命令执行
- `file_change`: 文件变更
- `mcp_tool_call`: MCP 工具调用
- `web_search`: 网络搜索
- `plan`: 计划更新

### 1.4 沙箱模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `read-only` | 只读访问，不能修改文件或运行命令 | 代码审查、安全探索 |
| `workspace-write` | 可读写工作目录，可运行本地命令（默认） | 常规开发任务 |
| `danger-full-access` | 完全访问，无限制 | 系统管理、受控环境 |

**沙箱实现**:
- macOS: Seatbelt
- Linux: Bubblewrap
- Windows: 受限令牌

**配置方式**:
```bash
# 命令行参数
codex exec --sandbox workspace-write "任务"

# 配置文件 (~/.codex/config.toml)
sandbox_mode = "workspace-write"
```

### 1.5 结构化输出

**使用 `--output-schema`**:

```json
// schema.json
{
  "type": "object",
  "properties": {
    "project_name": { "type": "string" },
    "programming_languages": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "required": ["project_name", "programming_languages"],
  "additionalProperties": false
}
```

```bash
codex exec "提取项目元数据" \
  --output-schema ./schema.json \
  -o ./project-metadata.json
```

**输出示例**:
```json
{
  "project_name": "Codex CLI",
  "programming_languages": ["Rust", "TypeScript", "Shell"]
}
```

### 1.6 非交互模式的限制

1. **必须在 Git 仓库中运行**（除非使用 `--skip-git-repo-check`）
2. **不支持中途人工干预**（审批模式需预设）
3. **不支持交互式 TUI 功能**（如 `/model`、`/mcp` 等命令）
4. **会话恢复有限**（只能通过 `resume` 命令）

### 1.7 适用场景

- ✅ CI/CD 管道自动化
- ✅ 批量代码分析和报告生成
- ✅ 日志分析和故障诊断
- ✅ 代码审查和 PR 生成
- ✅ 与 shell 脚本集成
- ❌ 需要人工审批的复杂任务
- ❌ 需要实时交互的开发场景

---

## 2. Codex App Server

### 2.1 概述

Codex App Server 是 Codex 的核心接口层，为富客户端（如 VS Code 扩展、桌面应用）提供支持。它实现了完整的双向通信协议，支持认证、会话历史、审批和流式事件。

### 2.2 协议细节

#### JSON-RPC 2.0 协议

App Server 使用 JSON-RPC 2.0 进行双向通信（省略了 `"jsonrpc":"2.0"` 头部）。

**消息类型**:

1. **请求 (Request)**:
   ```json
   { "method": "thread/start", "id": 10, "params": { "model": "gpt-5.4" } }
   ```

2. **响应 (Response)**:
   ```json
   { "id": 10, "result": { "thread": { "id": "thr_123" } } }
   ```

3. **通知 (Notification)**: 无 `id` 字段
   ```json
   { "method": "turn/started", "params": { "turn": { "id": "turn_456" } } }
   ```

#### 核心概念

- **Thread**: 用户与 Codex agent 之间的对话，包含多个 Turn
- **Turn**: 单次用户请求及 agent 的响应工作，包含多个 Item
- **Item**: 输入或输出的基本单元（用户消息、agent 消息、命令执行、文件变更等）

### 2.3 传输方式

| 传输方式 | 启动命令 | 说明 |
|----------|----------|------|
| **stdio** (默认) | `codex app-server` | JSONL 格式，通过 stdin/stdout 通信 |
| **websocket** | `codex app-server --listen ws://127.0.0.1:4500` | 实验性支持，每帧一个 JSON-RPC 消息 |
| **unix socket** | `codex app-server --listen unix://` | WebSocket over Unix socket |
| **off** | `codex app-server --listen off` | 不暴露本地传输 |

**WebSocket 健康检查**:
- `GET /readyz`: 返回 200 OK（接受新连接）
- `GET /healthz`: 返回 200 OK（无 Origin 头部）

**WebSocket 认证**:
```bash
# Capability token
--ws-auth capability-token --ws-token-file /path/to/token

# Signed bearer token
--ws-auth signed-bearer-token --ws-shared-secret-file /path/to/secret
```

### 2.4 启动和连接

#### 启动 App Server

```bash
# stdio 模式（默认）
codex app-server

# WebSocket 模式
codex app-server --listen ws://127.0.0.1:4500

# Unix socket 模式
codex app-server --listen unix://
```

#### 连接流程

1. **初始化握手**:
   ```json
   // 客户端发送
   {
     "method": "initialize",
     "id": 0,
     "params": {
       "clientInfo": {
         "name": "my_product",
         "title": "My Product",
         "version": "0.1.0"
       },
       "capabilities": {
         "experimentalApi": true
       }
     }
   }
   
   // 客户端发送初始化完成通知
   { "method": "initialized", "params": {} }
   ```

2. **启动 Thread**:
   ```json
   {
     "method": "thread/start",
     "id": 1,
     "params": {
       "model": "gpt-5.4",
       "cwd": "/Users/me/project",
       "sandbox": "workspaceWrite"
     }
   }
   ```

3. **开始 Turn**:
   ```json
   {
     "method": "turn/start",
     "id": 2,
     "params": {
       "threadId": "thr_123",
       "input": [{ "type": "text", "text": "分析这个仓库" }]
     }
   }
   ```

4. **读取事件流**: 持续读取 stdout 的通知事件

### 2.5 双向通信能力

#### 中途发送指令

**`turn/steer` - 在活跃 turn 中追加输入**:

```json
{
  "method": "turn/steer",
  "id": 32,
  "params": {
    "threadId": "thr_123",
    "input": [{ "type": "text", "text": "优先关注失败的测试" }],
    "expectedTurnId": "turn_456"
  }
}
```

**`turn/interrupt` - 中断正在进行的 turn**:

```json
{
  "method": "turn/interrupt",
  "id": 31,
  "params": {
    "threadId": "thr_123",
    "turnId": "turn_456"
  }
}
```

#### 审批请求

App Server 可以向客户端发送审批请求：

**命令执行审批**:
```json
{
  "method": "item/commandExecution/requestApproval",
  "params": {
    "itemId": "item_1",
    "threadId": "thr_123",
    "turnId": "turn_456",
    "command": "npm test",
    "availableDecisions": ["accept", "decline", "cancel"]
  }
}
```

**客户端响应**:
```json
{
  "id": 100,
  "result": {
    "decision": "accept"
  }
}
```

### 2.6 会话持久化

#### Thread 管理 API

| 方法 | 说明 |
|------|------|
| `thread/start` | 创建新 thread |
| `thread/resume` | 恢复已存在的 thread |
| `thread/fork` | 从现有 thread 分叉出新 thread |
| `thread/read` | 读取 thread（不恢复） |
| `thread/list` | 列出所有 thread（支持分页和过滤） |
| `thread/archive` | 归档 thread |
| `thread/unarchive` | 取消归档 |
| `thread/compact/start` | 触发对话历史压缩 |
| `thread/rollback` | 回滚最近的 N 个 turn |

#### 恢复示例

```json
// 恢复 thread
{
  "method": "thread/resume",
  "id": 11,
  "params": {
    "threadId": "thr_123",
    "personality": "friendly"
  }
}

// 分叉 thread
{
  "method": "thread/fork",
  "id": 12,
  "params": {
    "threadId": "thr_123"
  }
}
```

### 2.7 SDK 支持

#### TypeScript SDK

**安装**:
```bash
npm install @openai/codex-sdk
```

**使用示例**:
```typescript
import { Codex } from "@openai/codex-sdk";

const codex = new Codex();
const thread = codex.startThread();

// 运行 prompt
const result = await thread.run("诊断并修复 CI 失败");
console.log(result);

// 继续同一 thread
const result2 = await thread.run("实施修复方案");

// 恢复历史 thread
const thread2 = codex.resumeThread("<thread-id>");
const result3 = await thread2.run("继续之前的工作");
```

**特性**:
- Thread 管理（创建、恢复、分叉）
- 结构化输出（JSON Schema）
- 流式响应
- 需要 Node.js 18+

#### Python SDK

**安装**:
```bash
pip install openai-codex
```

**使用示例**:
```python
from openai_codex import Codex, Sandbox

with Codex() as codex:
    thread = codex.thread_start(
        model="gpt-5.4",
        sandbox=Sandbox.workspace_write,
    )
    result = thread.run("诊断并修复 CI 失败")
    print(result.final_response)
```

**异步支持**:
```python
import asyncio
from openai_codex import AsyncCodex

async def main():
    async with AsyncCodex() as codex:
        thread = await codex.thread_start(model="gpt-5.4")
        result = await thread.run("实施修复方案")
        print(result.final_response)

asyncio.run(main())
```

**沙箱预设**:
- `Sandbox.read_only`: 只读访问
- `Sandbox.workspace_write`: 工作目录读写
- `Sandbox.full_access`: 无限制访问

**要求**: Python 3.10+

#### 其他 SDK

- **.NET SDK**: `ManagedCode.CodexSharpSDK`（第三方）
  - Thread-based API
  - 流式 JSONL 事件
  - 结构化输出支持

### 2.8 Schema 生成

App Server 可以生成 TypeScript 或 JSON Schema：

```bash
# 生成 TypeScript schema
codex app-server generate-ts --out ./schemas

# 生成 JSON Schema
codex app-server generate-json-schema --out ./schemas
```

生成的 schema 与运行的 Codex 版本完全匹配。

### 2.9 核心 API 方法

#### Thread 管理

| 方法 | 说明 |
|------|------|
| `thread/start` | 创建新 thread |
| `thread/resume` | 恢复 thread |
| `thread/fork` | 分叉 thread |
| `thread/read` | 读取 thread（不恢复） |
| `thread/list` | 列出 thread |
| `thread/archive` | 归档 |
| `thread/unarchive` | 取消归档 |
| `thread/compact/start` | 压缩历史 |
| `thread/rollback` | 回滚 turn |
| `thread/goal/set` | 设置 thread 目标 |
| `thread/goal/get` | 获取目标 |
| `thread/goal/clear` | 清除目标 |
| `thread/name/set` | 设置 thread 名称 |
| `thread/metadata/update` | 更新元数据（如 gitInfo） |

#### Turn 管理

| 方法 | 说明 |
|------|------|
| `turn/start` | 开始新 turn |
| `turn/steer` | 在活跃 turn 中追加输入 |
| `turn/interrupt` | 中断 turn |
| `thread/turns/list` | 列出 thread 的 turn 历史 |

#### 命令执行

| 方法 | 说明 |
|------|------|
| `command/exec` | 执行单个命令（不创建 thread） |
| `command/exec/write` | 向命令写入 stdin |
| `command/exec/resize` | 调整 PTY 大小 |
| `command/exec/terminate` | 终止命令 |

#### 模型和配置

| 方法 | 说明 |
|------|------|
| `model/list` | 列出可用模型 |
| `config/read` | 读取有效配置 |
| `config/value/write` | 写入配置值 |
| `config/batchWrite` | 批量写入配置 |

#### MCP 集成

| 方法 | 说明 |
|------|------|
| `mcpServerStatus/list` | 列出 MCP 服务器状态 |
| `mcpServer/resource/read` | 读取 MCP 资源 |
| `mcpServer/tool/call` | 调用 MCP 工具 |
| `mcpServer/oauth/login` | OAuth 登录 |
| `config/mcpServer/reload` | 重新加载 MCP 配置 |

#### Skills 管理

| 方法 | 说明 |
|------|------|
| `skills/list` | 列出可用 skills |
| `skills/config/write` | 启用/禁用 skills |

#### 插件管理

| 方法 | 说明 |
|------|------|
| `plugin/list` | 列出插件 |
| `plugin/read` | 读取插件详情 |
| `plugin/install` | 安装插件 |
| `plugin/uninstall` | 卸载插件 |
| `marketplace/add` | 添加远程市场 |
| `marketplace/upgrade` | 升级市场 |

#### 文件系统

| 方法 | 说明 |
|------|------|
| `fs/readFile` | 读取文件 |
| `fs/writeFile` | 写入文件 |
| `fs/createDirectory` | 创建目录 |
| `fs/getMetadata` | 获取元数据 |
| `fs/readDirectory` | 读取目录 |
| `fs/remove` | 删除文件/目录 |
| `fs/copy` | 复制文件 |
| `fs/watch` | 监视文件变更 |
| `fs/unwatch` | 取消监视 |

#### 认证

| 方法 | 说明 |
|------|------|
| `account/login/start` | 开始登录（API key 或 ChatGPT） |
| `account/login/complete` | 完成登录（ChatGPT） |
| `account/login/cancel` | 取消登录 |
| `account/logout` | 登出 |
| `account/status/read` | 读取账户状态 |
| `account/rateLimits/read` | 读取速率限制 |

### 2.10 事件通知

#### Thread 事件

| 通知 | 说明 |
|------|------|
| `thread/started` | Thread 已启动 |
| `thread/archived` | Thread 已归档 |
| `thread/unarchived` | Thread 已取消归档 |
| `thread/closed` | Thread 已关闭（卸载） |
| `thread/status/changed` | Thread 状态变更 |
| `thread/name/updated` | Thread 名称更新 |
| `thread/goal/updated` | Thread 目标更新 |
| `thread/goal/cleared` | Thread 目标已清除 |
| `thread/tokenUsage/updated` | Token 使用量更新 |

#### Turn 事件

| 通知 | 说明 |
|------|------|
| `turn/started` | Turn 已开始 |
| `turn/completed` | Turn 已完成 |
| `turn/diff/updated` | Turn 的 diff 更新 |
| `turn/plan/updated` | Turn 的计划更新 |

#### Item 事件

| 通知 | 说明 |
|------|------|
| `item/started` | Item 已开始 |
| `item/completed` | Item 已完成 |
| `item/agentMessage/delta` | Agent 消息流式更新 |
| `item/plan/delta` | 计划流式更新 |
| `item/reasoning/summaryTextDelta` | 推理摘要流式更新 |
| `item/reasoning/textDelta` | 推理文本流式更新 |
| `item/commandExecution/outputDelta` | 命令输出流式更新 |
| `item/fileChange/outputDelta` | 文件变更输出（已弃用） |

#### 审批请求

| 通知 | 说明 |
|------|------|
| `item/commandExecution/requestApproval` | 请求命令执行审批 |
| `item/fileChange/requestApproval` | 请求文件变更审批 |
| `item/tool/requestUserInput` | 请求用户输入 |
| `serverRequest/resolved` | 审批请求已解决 |

### 2.11 适用场景

- ✅ 构建自定义 Codex 客户端（IDE 扩展、桌面应用）
- ✅ 需要完整会话管理和历史记录
- ✅ 需要双向通信和实时审批
- ✅ 需要流式事件和实时进度
- ✅ 需要 thread 分叉、归档、恢复等高级功能
- ❌ 简单的 CI/CD 自动化（使用 `codex exec` 更简单）
- ❌ 一次性任务执行

---

## 3. Codex MCP Server

### 3.1 概述

Codex 既可以作为 **MCP 客户端**（连接外部 MCP 服务器），也可以作为 **MCP 服务器**（暴露自身能力给其他 agent）。

### 3.2 Codex 作为 MCP 客户端

#### 支持的 MCP 服务器类型

1. **STDIO 服务器**: 本地进程，通过 stdin/stdout 通信
   ```toml
   [mcp_servers.context7]
   command = "npx"
   args = ["-y", "@upstash/context7-mcp"]
   env_vars = ["LOCAL_TOKEN"]
   ```

2. **Streamable HTTP 服务器**: 通过 URL 访问，支持 Bearer token 和 OAuth
   ```toml
   [mcp_servers.figma]
   url = "https://mcp.figma.com/mcp"
   bearer_token_env_var = "FIGMA_OAUTH_TOKEN"
   http_headers = { "X-Figma-Region" = "us-east-1" }
   ```

#### 配置管理

**CLI 命令**:
```bash
# 添加 MCP 服务器
codex mcp add <server-name> --env VAR1=VALUE1 -- <command>

# 示例：添加 Context7
codex mcp add context7 -- npx -y @upstash/context7-mcp

# 查看帮助
codex mcp --help

# 在 TUI 中查看
/mcp
```

**配置文件** (`~/.codex/config.toml` 或 `.codex/config.toml`):

```toml
[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
enabled = true
required = false
startup_timeout_sec = 10
tool_timeout_sec = 60

# 工具控制
enabled_tools = ["read", "search"]
disabled_tools = ["dangerous_tool"]
default_tools_approval_mode = "prompt"

# 单个工具审批
[mcp_servers.context7.tools.search]
approval_mode = "approve"
```

#### 常用 MCP 服务器

| 服务器 | 用途 |
|--------|------|
| **OpenAI Docs MCP** | 搜索和阅读 OpenAI 开发者文档 |
| **Context7** | 连接最新的开发者文档 |
| **Figma** | 访问 Figma 设计稿 |
| **Playwright** | 控制和检查浏览器 |
| **Chrome Developer Tools** | 检查 DOM、控制台、网络 |
| **Sentry** | 访问 Sentry 日志 |
| **GitHub** | 管理 PR 和 issues |

#### OAuth 认证

```bash
# 登录支持 OAuth 的 MCP 服务器
codex mcp login <server-name>
```

**配置 OAuth 回调**:
```toml
mcp_oauth_callback_port = 5555
mcp_oauth_callback_url = "https://devbox.example.internal/callback"
```

### 3.3 Codex 作为 MCP 服务器

#### 暴露的工具

当 Codex 作为 MCP 服务器运行时（使用 `codex mcp-server` 命令），它暴露以下工具：

1. **`codex()`**: 启动新的 Codex 对话
   - 参数：初始 prompt、审批策略、基础指令、工作目录
   
2. **`codex-reply()`**: 继续已存在的 Codex 会话
   - 参数：thread ID、下一个 prompt

#### 使用场景

这使得其他 AI agent（如使用 OpenAI Agents SDK 构建的 agent）可以：
- 编排和驱动 Codex 执行编码任务
- 生成代码、调试问题
- 创建多 agent 工作流

#### 启动 MCP 服务器

```bash
codex mcp-server
```

然后在其他 agent 的配置中添加 Codex 作为 MCP 服务器。

### 3.4 插件系统

插件可以捆绑 skills、app 集成和 MCP 服务器：

```toml
[plugins."sample@test".mcp_servers.sample]
enabled = true
default_tools_approval_mode = "prompt"
enabled_tools = ["read", "search"]
```

### 3.5 适用场景

#### Codex 作为 MCP 客户端

- ✅ 访问第三方文档（Context7、OpenAI Docs）
- ✅ 与开发工具集成（Figma、Playwright、Chrome DevTools）
- ✅ 管理代码仓库（GitHub MCP）
- ✅ 访问企业系统（内部 API、数据库）
- ✅ 处理生产错误（Sentry、Linear）

#### Codex 作为 MCP 服务器

- ✅ 构建多 agent 系统
- ✅ 让其他 agent 编排 Codex
- ✅ 将 Codex 能力暴露给外部系统
- ❌ 不适合直接用户交互（使用 App Server 或 CLI）

---

## 4. Codex Cloud / API

### 4.1 概述

Codex Cloud 提供基于云的任务执行环境，每个任务在隔离的沙箱中运行。可以通过 REST API 提交任务并获取结果。

### 4.2 认证方式

#### 方式 1: ChatGPT 账户登录（订阅制）

**流程**:
1. 打开浏览器完成 ChatGPT 登录
2. 返回 access token 给客户端
3. 集成 ChatGPT 工作区权限、RBAC、数据保留策略

**适用场景**:
- 使用 ChatGPT Plus/Pro/Business 订阅
- 需要企业级数据治理
- 交互式使用（CLI、IDE、Web）

**设备代码认证**:
可在 ChatGPT 安全设置或工作区权限中启用。

#### 方式 2: API Key（按量计费）

**获取**: OpenAI Dashboard

**类型**:
- **Secret keys**: 长期有效，适合服务端使用
- **Short-lived keys**: 可设置过期时间和请求限制，适合不受信任的客户端

**使用**:
```bash
# 环境变量
export CODEX_API_KEY="***"

# 单次使用
CODEX_API_KEY=*** codex exec "任务"

# HTTP 请求
Authorization: Bearer ***
```

**适用场景**:
- CI/CD 自动化
- 程序化工作流
- 按量计费需求

**安全注意**:
- 不要将 API key 设置为 job 级环境变量
- 仅在单个 `codex exec` 调用中设置
- 使用 GitHub Actions 时，使用 `openai/codex-action`

### 4.3 REST API

#### 任务提交

Codex Cloud 的任务通过 API 提交，在云沙箱中异步执行。

**认证头部**:
```http
Authorization: Bearer YOUR_A…OKEN
```

#### Webhook 回调

**Webhook 认证头部**:

1. `X-Webhook-Timestamp`: Unix 时间戳（秒）
2. `X-Webhook-Signature`: HMAC-SHA256 签名（小写十六进制）

**签名计算**:
```python
import hmac
import hashlib

signature = hmac.new(
    security_token.encode(),
    f"{timestamp}.{raw_body}".encode(),
    hashlib.sha256
).hexdigest()
```

**注意**: 
- 旧的 "body hash" 字段已弃用
- 截至 2026 年 4 月，不支持入站 webhook 触发任务
- 需要使用中间件（如 serverless 函数）接收 webhook 后调用 API

### 4.4 Codex Cloud 任务

#### 任务执行环境

- 隔离的云沙箱
- 支持后台运行
- 可并行执行多个任务
- 可链接仓库、修复 bug、生成测试、提出 PR

#### 从 CLI 使用 Codex Cloud

```bash
# 启动 Codex Cloud 任务
codex cloud "修复这个 bug"

# 查看任务状态
codex cloud status <task-id>

# 应用 diff
codex cloud apply <task-id>
```

### 4.5 适用场景

- ✅ 大规模并行任务执行
- ✅ 不需要本地环境的任务
- ✅ 企业级安全和合规需求
- ✅ 长时间运行的工程任务
- ❌ 需要本地文件系统访问的任务（使用 CLI 或 App Server）
- ❌ 低延迟需求（云任务有启动开销）

---

## 5. Codex Agent Loop 架构

### 5.1 概述

Codex 的核心是一个迭代式 agent loop，协调用户、语言模型和外部工具之间的交互。

### 5.2 Agent Loop 工作流程

```
用户输入
    ↓
构建 Prompt（包含上下文、工具定义、AGENTS.md）
    ↓
模型推理
    ↓
是否需要工具调用？
    ↓ 是                    ↓ 否
执行工具 → 获取输出 → 追加到 Prompt → 返回模型推理 → 生成最终消息
    ↓
完成 Turn
```

#### 关键阶段

1. **Plan（规划）**: 模型分析任务，制定执行计划
2. **Act（执行）**: 通过工具执行动作（shell 命令、文件编辑等）
3. **Observe（观察）**: 获取工具输出，观察结果和错误
4. **Reflect & Iterate（反思与迭代）**: 根据结果调整后续步骤

### 5.3 Tool Use 能力

#### 内置工具

1. **Shell 执行** (`container.exec`):
   - 在沙箱中执行 shell 命令
   - 支持 PTY 会话
   - 可流式输出 stdout/stderr
   
2. **文件编辑**:
   - 读取、修改、创建文件
   - 理解代码库结构
   - 应用上下文相关的变更

3. **Git 操作**:
   - 读取仓库状态
   - 创建 commit
   - 生成 diff

4. **网络搜索**:
   - 搜索最新信息
   - 获取文档

#### MCP 工具

通过 MCP 协议连接的外部工具：
- 第三方文档（Context7）
- 浏览器控制（Playwright）
- 设计工具（Figma）
- 代码管理（GitHub）
- 错误追踪（Sentry）
- 自定义工具

#### 工具审批模式

| 模式 | 说明 |
|------|------|
| **Suggest** | 每个步骤都需要审批 |
| **Auto Edit** | 自动文件编辑，shell 命令需审批 |
| **Full Auto** | 沙箱内完全自主执行 |

### 5.4 上下文管理

#### AGENTS.md

**作用**: 为 agent 提供持久化指令，是最重要的上下文管理工具。

**层级结构**:

1. **全局** (`~/.codex/AGENTS.md`):
   - 适用于所有项目
   - 通用编码风格、偏好

2. **项目** (`<repo>/AGENTS.md`):
   - 项目特定指令
   - 构建、测试、lint 命令
   - 代码规范

3. **嵌套覆盖** (`<subdir>/AGENTS.override.md`):
   - 子目录特定规则
   - 单仓多项目场景

**内容示例**:
```markdown
# 项目概述
这是一个 React + TypeScript 前端项目。

# 构建命令
- 安装依赖: `npm install`
- 开发服务器: `npm run dev`
- 构建: `npm run build`
- 测试: `npm test`
- Lint: `npm run lint`

# 代码规范
- 使用函数组件和 Hooks
- 使用 TypeScript strict 模式
- 组件文件使用 PascalCase
- 工具函数文件使用 camelCase

# PR 要求
- 所有测试必须通过
- 代码覆盖率 > 80%
- 需要至少一个 review
```

**自动加载**: Codex 在每次任务开始时自动读取 AGENTS.md。

**脚手架生成**:
```bash
codex agents init
```
扫描代码库，推断代码风格、测试偏好，生成初始 AGENTS.md。

#### Skills

**作用**: 可重用的指令、模板和脚本包，在特定场景激活。

**与 AGENTS.md 的区别**:
- AGENTS.md: 始终生效的指令
- Skills: 按需激活的能力包

**使用**:
```bash
# 在 prompt 中调用
$skill-creator 创建一个新的 skill

# 列出可用 skills
skills/list
```

#### Context Window 管理

**上下文窗口大小**: ~192,000 tokens

**动态构建**:
1. 仓库内容（通过工具访问）
2. AGENTS.md 指令
3. Skills 指令
4. 当前任务 prompt
5. 对话历史
6. MCP 服务器指令

**对话压缩**:
当 token 数超过限制时，Codex 会压缩对话历史：
- 替换冗长的输入为简洁表示
- 保留关键信息
- 确保任务连续性

**Prompt 缓存**:
- 优化静态信息（指令、工具定义）
- 减少重复计算
- 提升性能

### 5.5 子 Agent（Subagents）

#### 概述

子 agent 是 Codex 生成的专用 agent，可并行工作，每个子 agent 有独立的上下文窗口、模型配置和沙箱策略。

#### 特性

1. **隔离上下文**: 防止"上下文污染"
2. **独立配置**: 每个子 agent 可配置不同的模型和沙箱
3. **并行执行**: 多个子 agent 可同时工作
4. **结果整合**: 主 agent 编排并整合子 agent 输出

#### 使用方式

用户需要明确指示 Codex 生成子 agent：

```
请并行分析以下 5 个模块的代码质量：
- 模块 A
- 模块 B
- 模块 C
- 模块 D
- 模块 E
```

Codex 会：
1. 生成 5 个子 agent
2. 每个子 agent 负责一个模块
3. 并行执行分析
4. 整合结果返回

#### 适用场景

- ✅ 大型代码库探索
- ✅ 多步骤功能实现
- ✅ 批量数据处理（如 CSV 文件）
- ✅ 并行代码审查
- ❌ 顺序依赖的任务
- ❌ 简单的单线程任务

### 5.6 Codex Harness

**作用**: 管理 agent loop 的基础设施组件。

**职责**:
1. **工具执行**: 安全地执行工具调用
2. **Prompt 构建**: 高效地组织 prompt 结构
3. **上下文窗口管理**: 管理 token 使用、触发压缩
4. **会话持久化**: 保存和恢复会话状态

---

## 6. 对比表格

### 6.1 集成方式对比

| 特性 | Codex CLI (`exec`) | App Server | MCP Server | Cloud API |
|------|-------------------|------------|------------|-----------|
| **使用复杂度** | 低 | 高 | 中 | 中 |
| **交互性** | 无 | 双向 | 单向/双向 | 异步 |
| **会话管理** | 有限 | 完整 | 无 | 完整 |
| **流式事件** | JSONL | 完整 | 无 | Webhook |
| **审批控制** | 预设 | 实时 | 无 | 预设 |
| **SDK 支持** | 无 | TS/Python/.NET | 标准 MCP | REST |
| **本地文件访问** | ✅ | ✅ | ✅ | ❌ |
| **云沙箱** | ❌ | ❌ | ❌ | ✅ |
| **并行任务** | ❌ | ✅ | ✅ | ✅ |
| **适用场景** | CI/CD、脚本 | 自定义客户端 | 多 agent | 大规模任务 |

### 6.2 详细对比

#### 1. Codex CLI (`exec`)

**优势**:
- ✅ 简单易用，无需编程
- ✅ 与 shell 脚本无缝集成
- ✅ 支持 JSON 输出和结构化数据
- ✅ 适合 CI/CD 自动化
- ✅ 快速启动，低开销

**劣势**:
- ❌ 无交互性，不能中途干预
- ❌ 会话管理有限
- ❌ 不支持实时审批
- ❌ 无法构建自定义 UI

**最佳场景**:
- CI/CD 管道
- 批量代码分析
- 日志处理
- 自动化报告生成

#### 2. App Server

**优势**:
- ✅ 完整的双向通信
- ✅ 丰富的会话管理（thread/turn/item）
- ✅ 实时审批和流式事件
- ✅ 官方 SDK 支持（TypeScript/Python）
- ✅ 会话持久化（恢复、分叉、归档）
- ✅ 完整的 API 表面

**劣势**:
- ❌ 复杂度高，需要编程
- ❌ 需要管理进程生命周期
- ❌ 协议细节较多
- ❌ 本地运行，无云沙箱

**最佳场景**:
- 构建 IDE 扩展
- 构建桌面应用
- 需要完整会话管理的工具
- 需要实时审批的工作流

#### 3. MCP Server

**优势**:
- ✅ 标准化协议（MCP）
- ✅ 可被其他 agent 编排
- ✅ 支持多 agent 工作流
- ✅ 可连接外部工具和数据源
- ✅ 插件生态系统

**劣势**:
- ❌ 作为服务器时能力有限（仅 2 个工具）
- ❌ 不适合直接用户交互
- ❌ 需要理解 MCP 协议
- ❌ 配置复杂

**最佳场景**:
- 多 agent 系统
- 让其他 AI agent 使用 Codex
- 连接外部工具和数据源
- 构建可复用的能力包

#### 4. Cloud API

**优势**:
- ✅ 隔离的云沙箱
- ✅ 大规模并行执行
- ✅ 企业级安全和合规
- ✅ 无需本地环境
- ✅ 长时间运行任务

**劣势**:
- ❌ 启动开销大
- ❌ 无法访问本地文件
- ❌ 延迟较高
- ❌ 成本较高（云资源）

**最佳场景**:
- 大规模并行任务
- 企业级应用
- 不需要本地环境的任务
- 长时间运行的工程任务

### 6.3 性能对比

| 指标 | CLI | App Server | MCP | Cloud |
|------|-----|------------|-----|-------|
| **启动时间** | <1s | <1s | <1s | 5-10s |
| **延迟** | 低 | 低 | 低 | 高 |
| **吞吐量** | 单任务 | 多 thread | 多工具 | 并行任务 |
| **资源占用** | 低 | 中 | 低 | 高（云） |
| **成本** | API 费用 | API 费用 | API 费用 | API + 云资源 |

---

## 7. 推荐方案：项目管理引擎

### 7.1 需求分析

构建一个"项目管理引擎"来指挥 Codex 干活，需要以下能力：

1. **任务编排**: 创建、分配、跟踪任务
2. **会话管理**: 维护任务上下文和历史
3. **进度监控**: 实时了解任务执行状态
4. **结果收集**: 获取任务输出和产物
5. **错误处理**: 处理失败和重试
6. **并行执行**: 同时运行多个任务
7. **审批控制**: 必要时人工干预
8. **集成能力**: 与现有工具链集成

### 7.2 推荐方案：App Server + TypeScript SDK

**核心选择**: **Codex App Server + TypeScript SDK**

**理由**:

1. **完整的会话管理**:
   - Thread/Turn/Item 模型完美匹配项目管理概念
   - 支持任务恢复、分叉、归档
   - 可以追踪完整的任务历史

2. **双向通信**:
   - 可以中途发送指令（`turn/steer`）
   - 可以中断任务（`turn/interrupt`）
   - 可以实时审批（命令执行、文件变更）

3. **流式事件**:
   - 实时进度更新
   - 可以构建实时 dashboard
   - 支持通知和告警

4. **SDK 支持**:
   - TypeScript SDK 易于集成到 Node.js 应用
   - 类型安全，开发体验好
   - 官方维护，持续更新

5. **灵活性**:
   - 可以控制沙箱策略
   - 可以配置模型和参数
   - 可以集成 MCP 工具

### 7.3 架构设计

```
┌─────────────────────────────────────────────────────┐
│              项目管理引擎 (Node.js)                  │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 任务队列 │  │ 进度跟踪 │  │ 结果收集 │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│         ↓           ↓           ↓                   │
│  ┌──────────────────────────────────────┐          │
│  │      Codex TypeScript SDK            │          │
│  │  - thread.start()                    │          │
│  │  - thread.run()                      │          │
│  │  - thread.steer()                    │          │
│  │  - thread.interrupt()                │          │
│  └──────────────────────────────────────┘          │
└─────────────────────────────────────────────────────┘
                         ↓
              ┌─────────────────────┐
              │  Codex App Server   │
              │   (JSON-RPC 2.0)    │
              └─────────────────────┘
                         ↓
              ┌─────────────────────┐
              │   Codex Agent Loop  │
              │  - Shell 执行       │
              │  - 文件编辑         │
              │  - Git 操作         │
              │  - MCP 工具         │
              └─────────────────────┘
```

### 7.4 实现示例

```typescript
import { Codex, Thread, Turn } from "@openai/codex-sdk";

class ProjectManagementEngine {
  private codex: Codex;
  private activeThreads: Map<string, Thread> = new Map();

  constructor() {
    this.codex = new Codex();
  }

  // 创建任务
  async createTask(
    projectId: string,
    description: string,
    options: {
      model?: string;
      sandbox?: "read_only" | "workspace_write" | "full_access";
      cwd?: string;
    } = {}
  ): Promise<string> {
    const thread = this.codex.startThread({
      model: options.model || "gpt-5.4",
      sandbox: options.sandbox || "workspace_write",
      cwd: options.cwd,
    });

    const threadId = thread.id;
    this.activeThreads.set(threadId, thread);

    // 设置任务目标
    await thread.setGoal({
      objective: description,
      status: "active",
    });

    return threadId;
  }

  // 执行任务
  async executeTask(
    threadId: string,
    prompt: string,
    onProgress?: (event: any) => void
  ): Promise<any> {
    const thread = this.activeThreads.get(threadId);
    if (!thread) {
      throw new Error(`Thread ${threadId} not found`);
    }

    // 订阅事件
    if (onProgress) {
      thread.on("item/started", onProgress);
      thread.on("item/completed", onProgress);
      thread.on("turn/completed", onProgress);
    }

    // 执行
    const result = await thread.run(prompt);
    return result;
  }

  // 中途调整任务
  async steerTask(threadId: string, additionalInput: string): Promise<void> {
    const thread = this.activeThreads.get(threadId);
    if (!thread) {
      throw new Error(`Thread ${threadId} not found`