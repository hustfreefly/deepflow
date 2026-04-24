# OpenClaw Agent 与多Agent协作 开发者手册

> **用途**：DeepFlow 后续开发的配置参考与架构输入  
> **来源**：OpenClaw 官方文档（docs.openclaw.ai）  
> **文档版本**：2026.4.15 最新  
> **生成时间**：2026-04-18

---

## 目录

- [一、Agent 核心机制](#一agent-核心机制)
- [二、多 Agent 协作机制](#二多-agent-协作机制)
- [三、会话管理机制](#三会话管理机制)
- [四、上下文与压缩机制](#四上下文与压缩机制)
- [五、Agent Loop 执行流程](#五agent-loop-执行流程)
- [六、Active Memory 主动记忆](#六active-memory-主动记忆)
- [七、关键配置参考](#七关键配置参考)
- [八、CLI 命令参考](#八cli-命令参考)
- [九、Plugin Hooks 扩展点](#九plugin-hooks-扩展点)
- [十、对 DeepFlow 的设计输入](#十对-deepflow-的设计输入)

---

## 一、Agent 核心机制

### 1.1 什么是 Agent

一个 **Agent** 是一个完全隔离的"大脑"，拥有独立的：

- **Workspace**（工作区）：文件、AGENTS.md/SOUL.md/USER.md、本地笔记、人格规则
- **State Directory**（状态目录）：`agentDir` 用于 auth profiles、model registry、per-agent 配置
- **Session Store**（会话存储）：聊天历史 + 路由状态，位于 `~/.openclaw/agents/<agentId>/sessions`

### 1.2 文件路径映射

| 资源 | 默认路径 | 可配置 |
|------|---------|--------|
| 配置文件 | `~/.openclaw/openclaw.json` | `OPENCLAW_CONFIG_PATH` |
| 状态目录 | `~/.openclaw` | `OPENCLAW_STATE_DIR` |
| Workspace | `~/.openclaw/workspace` | `agents.defaults.workspace` |
| Agent Dir | `~/.openclaw/agents/<agentId>/agent` | `agents.list[].agentDir` |
| Sessions | `~/.openclaw/agents/<agentId>/sessions` | 自动 |
| Auth Profiles | `~/.openclaw/agents/<agentId>/agent/auth-profiles.json` | 不可共享 |

### 1.3 Workspace 文件体系

| 文件 | 作用 | 加载时机 |
|------|------|---------|
| `AGENTS.md` | 操作指令、规则、行为准则 | 每次会话启动 |
| `SOUL.md` | 人格、边界、语气 | 每次会话启动 |
| `USER.md` | 用户信息、称呼方式 | 每次会话启动 |
| `IDENTITY.md` | Agent 名称、风格、emoji | 每次会话启动 |
| `TOOLS.md` | 工具使用笔记与约定 | 每次会话启动 |
| `HEARTBEAT.md` | 心跳检查清单（可选） | 心跳轮询 |
| `BOOT.md` | 启动检查清单（可选） | Gateway 重启 |
| `BOOTSTRAP.md` | 首次运行仪式 | 仅新建 workspace |
| `MEMORY.md` | 长期记忆（可选） | 主私有会话 |
| `memory/YYYY-MM-DD.md` | 每日记忆日志 | 按需读取 |
| `skills/` | Workspace 级技能 | 按需加载 SKILL.md |

### 1.4 Skills 加载优先级（从高到低）

1. Workspace: `<workspace>/skills`（最高优先级）
2. Project Agent Skills: `<workspace>/.agents/skills`
3. Personal Agent Skills: `~/.agents/skills`
4. Managed/Local: `~/.openclaw/skills`
5. Bundled: 随安装包 shipped
6. Extra: `skills.load.extraDirs`

### 1.5 内置工具

核心工具始终可用（受 tool policy 约束）：

- `read` / `write` / `edit` — 文件操作
- `exec` / `process` — 命令执行与进程管理
- `web_fetch` — 网页抓取
- `image` / `image_generate` — 图像分析与生成
- `message` — 消息发送
- `sessions_spawn` / `sessions_list` / `sessions_history` / `sessions_send` — 子Agent管理
- `browser` — 浏览器自动化
- `memory_search` / `memory_get` — 记忆检索

### 1.6 Model 引用规则

配置中的 model refs 按第一个 `/` 分割：

- 格式：`provider/model`
- 含 `/` 的模型 ID（OpenRouter 风格）：`openrouter/moonshotai/kimi-k2`
- 省略 provider 时：先尝试 alias → 唯一配置的 provider → fallback 到默认 provider

---

## 二、多 Agent 协作机制

### 2.1 核心概念

| 概念 | 说明 |
|------|------|
| `agentId` | 一个"大脑"（workspace + per-agent auth + per-agent session store） |
| `accountId` | 一个 channel 账号实例（如 WhatsApp "personal" vs "biz"） |
| `binding` | 将入站消息路由到 `agentId`，按 `(channel, accountId, peer)` 匹配 |
| 直接聊天 | 折叠到 agent 的 main session key |

### 2.2 路由规则（确定性，最具体优先）

绑定匹配优先级（从上到下，第一个匹配胜出）：

1. **`peer` 匹配**（精确 DM/group/channel id）
2. **`parentPeer` 匹配**（线程继承）
3. **`guildId + roles`**（Discord 角色路由）
4. **`guildId`**（Discord 服务器）
5. **`teamId`**（Slack 团队）
6. **`accountId` 匹配**（channel 账号）
7. **`accountId: "*"`**（channel 级 fallback）
8. **Fallback** → 默认 agent（`agents.list[].default`，否则列表第一个，默认 `main`）

**重要规则**：
- 同一层级多个匹配：配置顺序第一个胜出
- 绑定设置多个匹配字段（如 `peer` + `guildId`）：AND 语义
- 绑定省略 `accountId`：仅匹配默认账号
- `accountId: "*"`：channel 级 fallback（所有账号）

### 2.3 多 Agent 配置示例

```json5
{
  agents: {
    list: [
      {
        id: "home",
        default: true,
        name: "Home",
        workspace: "~/.openclaw/workspace-home",
        agentDir: "~/.openclaw/agents/home/agent",
      },
      {
        id: "work",
        name: "Work",
        workspace: "~/.openclaw/workspace-work",
        agentDir: "~/.openclaw/agents/work/agent",
      },
    ],
  },
  bindings: [
    { agentId: "home", match: { channel: "whatsapp", accountId: "personal" } },
    { agentId: "work", match: { channel: "whatsapp", accountId: "biz" } },
  ],
  // Agent 间通信（默认关闭，需显式启用+白名单）
  tools: {
    agentToAgent: {
      enabled: false,
      allow: ["home", "work"],
    },
  },
}
```

### 2.4 跨 Agent QMD 记忆搜索

如果一个 Agent 需要搜索另一个 Agent 的 QMD 会话记录：

```json5
{
  agents: {
    defaults: {
      memorySearch: {
        qmd: {
          extraCollections: [{ path: "~/agents/family/sessions", name: "family-sessions" }],
        },
      },
    },
    list: [
      {
        id: "main",
        memorySearch: {
          qmd: {
            extraCollections: [{ path: "notes" }], // workspace 内路径
          },
        },
      },
      { id: "family", workspace: "~/workspaces/family" },
    ],
  },
}
```

### 2.5 Agent 间通信

默认情况下，Agent 之间**不共享凭证**，也不自动通信。

- 主 Agent 凭证**不会自动共享**
- 如需共享，手动复制 `auth-profiles.json` 到另一个 Agent 的 `agentDir`
- Agent-to-Agent 消息默认关闭，需通过 `tools.agentToAgent` 显式启用 + 白名单

---

## 三、会话管理机制

### 3.1 消息路由行为

| 来源 | 行为 |
|------|------|
| 直接消息（DM） | 默认共享一个 session |
| 群聊 | 按群隔离 |
| Rooms/Channels | 按 room 隔离 |
| Cron Jobs | 每次运行新建 session |
| Webhooks | 按 hook 隔离 |

### 3.2 DM 隔离级别

```json5
{
  session: {
    dmScope: "per-channel-peer", // 推荐：按 channel + 发送者隔离
  },
}
```

选项：

| 值 | 行为 |
|---|------|
| `main`（默认） | 所有 DM 共享一个 session |
| `per-peer` | 按发送者隔离（跨 channel） |
| `per-channel-peer`（推荐） | 按 channel + 发送者隔离 |
| `per-account-channel-peer` | 按账号 + channel + 发送者隔离 |

### 3.3 Session 生命周期

| 重置类型 | 配置 | 说明 |
|---------|------|------|
| 每日重置 | 默认 4:00 AM 本地时间 | 每天自动新建 session |
| 空闲重置 | `session.reset.idleMinutes` | 无活动指定时间后新建 |
| 手动重置 | 用户输入 `/new` 或 `/reset` | `/new <model>` 同时切换模型 |

两者都配置时，先触发的胜出。

### 3.4 Session 存储位置

- **Store**：`~/.openclaw/agents/<agentId>/sessions/sessions.json`
- **Transcripts**：`~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`

### 3.5 Session 维护

```json5
{
  session: {
    maintenance: {
      mode: "enforce",     // "warn"（仅报告）或 "enforce"（自动清理）
      pruneAfter: "30d",   // 30天后修剪
      maxEntries: 500,     // 最大条目数
    },
  },
}
```

### 3.6 Steering（流中转向）

- **`steer` 模式**：入站消息注入当前运行，在当前 assistant turn 的工具调用执行完成后交付
- **`followup` 模式**：入站消息保持到当前 turn 结束，然后新 turn 开始
- **`collect` 模式**：类似 followup，但有 debounce/cap 行为

### 3.7 流式输出

- Block streaming 默认关闭（`agents.defaults.blockStreamingDefault: "off"`）
- 可配置边界（`text_end` vs `message_end`）
- 默认 chunk 大小 800-1200 字符，优先段落分割

---

## 四、上下文与压缩机制

### 4.1 上下文组成

"Context" = 模型在一次运行中接收的所有内容：

1. **System Prompt**（OpenClaw 构建）：规则、工具、技能列表、时间/运行时元数据、注入的 workspace 文件
2. **Conversation History**：用户消息 + assistant 消息
3. **Tool Calls/Results**：命令输出、文件读取、图片/音频等
4. **Attachments/Transcripts**：图片/音频/文件的转录
5. **Compaction Summaries**：压缩摘要

### 4.2 System Prompt 构建要素

- 工具列表 + 简短描述
- 技能列表（仅元数据，不含指令）
- Workspace 位置
- 时间（UTC + 用户时区）
- 运行时元数据（host/OS/model/thinking）
- 注入的 workspace bootstrap 文件（Project Context）

### 4.3 注入限制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `bootstrapMaxChars` | 20,000 字符 | 单文件注入上限 |
| `bootstrapTotalMaxChars` | 150,000 字符 | 所有文件总注入上限 |
| `bootstrapPromptTruncationWarning` | `once` | 截断警告（off/once/always） |

### 4.4 自动压缩（Auto-Compaction）

- **默认开启**，当 session 接近上下文窗口时触发
- 旧消息压缩为摘要，保留最近消息
- 压缩前自动提醒 Agent 将重要信息保存到 memory 文件
- 支持独立压缩模型：

```json5
{
  agents: {
    defaults: {
      compaction: {
        model: "openrouter/anthropic/claude-sonnet-4-6",
        notifyUser: false,  // 是否显示压缩通知
      },
    },
  },
}
```

- 保留标识符策略（`identifierPolicy: "strict"`）
- 支持插件注册自定义压缩 provider

### 4.5 压缩 vs 修剪

| | 压缩（Compaction） | 修剪（Pruning） |
|---|---|---|
| 作用 | 摘要化旧对话 | 裁剪旧 tool results |
| 持久化 | 是（写入 session transcript） | 否（仅内存中，每次请求） |
| 范围 | 整个对话 | 仅 tool results |

---

## 五、Agent Loop 执行流程

### 5.1 执行步骤

```
1. agent RPC → 验证参数 → 解析 session → 持久化 session metadata → 返回 {runId, acceptedAt}
2. agentCommand → 解析 model + thinking/verbose/trace → 加载 skills snapshot → 调用 runEmbeddedPiAgent
3. runEmbeddedPiAgent → 序列化 runs → 解析 model + auth profile → 订阅 pi events → 流式输出
4. subscribeEmbeddedPiSession → 桥接 pi-agent-core events 到 OpenClaw agent stream
5. agent.wait → 等待 lifecycle end/error → 返回 {status, startedAt, endedAt}
```

### 5.2 并发控制

- **Per-session 序列化**：每个 session key 一个执行队列
- **全局队列**：可选，通过全局 lane 控制
- 防止 tool/session 竞争，保持 session 历史一致性

### 5.3 超时配置

| 超时类型 | 配置项 | 默认值 |
|---------|--------|--------|
| Agent 执行超时 | `agents.defaults.timeoutSeconds` | 172800s（48小时） |
| LLM 空闲超时 | `agents.defaults.llm.idleTimeoutSeconds` | 120s（未设置时） |
| agent.wait 超时 | `timeoutMs` 参数 | 30s |

### 5.4 回复塑造

最终回复由以下组装：
- Assistant 文本（+ 可选 reasoning）
- Inline tool 摘要（verbose + 允许时）
- Assistant 错误文本

特殊标记 `NO_REPLY` / `no_reply` 从输出中过滤。

---

## 六、Active Memory 主动记忆

### 6.1 概念

Active Memory 是一个可选的**插件拥有的阻塞记忆子Agent**，在主回复之前运行。

**解决的问题**：大多数记忆系统是被动的，依赖主 Agent 决定何时搜索记忆。Active Memory 在生成回复前自动检索相关记忆。

### 6.2 配置示例

```json5
{
  plugins: {
    entries: {
      "active-memory": {
        enabled: true,
        config: {
          enabled: true,
          agents: ["main"],
          allowedChatTypes: ["direct"],
          modelFallback: "google/gemini-3-flash",
          queryMode: "recent",     // message | recent | full
          promptStyle: "balanced",
          timeoutMs: 15000,
          maxSummaryChars: 220,
          persistTranscripts: false,
          logging: true,
        },
      },
    },
  },
}
```

### 6.3 运行条件

```
plugin enabled
+ agent id targeted
+ allowed chat type
+ eligible interactive persistent chat session
= active memory runs
```

### 6.4 适用范围

| 场景 | 运行 Active Memory？ |
|------|---------------------|
| Control UI / Web Chat 持久会话 | 是 |
| 其他交互式 channel 会话 | 是 |
| 无头单次运行 | 否 |
| Heartbeat/后台运行 | 否 |
| 内部 agent-command 路径 | 否 |
| 子Agent/内部辅助执行 | 否 |

### 6.5 会话级控制

```
/active-memory status    # 查看状态
/active-memory off       # 暂停当前会话
/active-memory on        # 恢复当前会话
/active-memory off --global   # 全局暂停
```

---

## 七、关键配置参考

### 7.1 Agent 配置核心字段

```json5
{
  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
      model: "provider/model",
      modelFallback: "provider/model",
      timeoutSeconds: 172800,
      contextTokens: null,
      sandbox: { mode: "off" },
      skills: {},          // 共享技能基线
      compaction: {
        model: "provider/model",
        notifyUser: false,
      },
      llm: {
        idleTimeoutSeconds: 120,
      },
      bootstrapMaxChars: 20000,
      bootstrapTotalMaxChars: 150000,
      blockStreamingDefault: "off",
    },
    list: [
      {
        id: "main",
        default: true,
        name: "Main Agent",
        workspace: "~/.openclaw/workspace",
        agentDir: "~/.openclaw/agents/main/agent",
        skills: {},        // per-agent 技能替换
        identity: {
          name: "小满",
          emoji: "🦞",
        },
      },
    ],
  },
}
```

### 7.2 Session 配置

```json5
{
  session: {
    dmScope: "per-channel-peer",
    identityLinks: [],   // 跨 channel 身份链接
    reset: {
      idleMinutes: null, // 空闲重置
    },
    maintenance: {
      mode: "warn",      // "warn" | "enforce"
      pruneAfter: "30d",
      maxEntries: 500,
    },
  },
}
```

### 7.3 Bindings 配置

```json5
{
  bindings: [
    {
      agentId: "main",
      match: {
        channel: "feishu",
        accountId: "default",
      },
    },
    {
      agentId: "work",
      match: {
        channel: "whatsapp",
        accountId: "biz",
        peer: { kind: "group", id: "group_id@g.us" },
      },
    },
  ],
}
```

### 7.4 Agent-to-Agent 通信

```json5
{
  tools: {
    agentToAgent: {
      enabled: true,
      allow: ["main", "work"],  // 白名单
    },
  },
}
```

---

## 八、CLI 命令参考

### 8.1 Agent 管理

| 命令 | 说明 |
|------|------|
| `openclaw agents` | 列出所有 agent（同 `list`） |
| `openclaw agents list` | 列出 agent + 基本信息 |
| `openclaw agents list --bindings` | 含完整路由规则 |
| `openclaw agents add <name>` | 新建 agent |
| `openclaw agents add <name> --workspace <dir> --bind telegram:ops` | 一步创建+绑定 |
| `openclaw agents delete <id>` | 删除 agent（workspace 移到 Trash） |
| `openclaw agents bind --agent <id> --bind <channel[:accountId]>` | 添加路由绑定 |
| `openclaw agents unbind --agent <id> --bind <channel>` | 移除路由绑定 |
| `openclaw agents unbind --agent <id> --all` | 移除所有绑定 |
| `openclaw agents set-identity --agent <id> --name "X" --emoji "🦞"` | 设置身份 |

### 8.2 Agent 执行

| 命令 | 说明 |
|------|------|
| `openclaw agent --to <dest> --message "text"` | 运行 agent turn |
| `openclaw agent --agent <id> --message "text"` | 指定 agent 执行 |
| `openclaw agent --session-id <id> --message "text"` | 指定 session 执行 |
| `openclaw agent --local --message "text"` | 强制本地执行（不经 Gateway） |
| `openclaw agent --deliver --message "text"` | 发送回复到 channel |
| `openclaw agent --thinking medium` | 设置 thinking 级别 |
| `openclaw agent --timeout 600` | 覆盖超时设置 |

### 8.3 Session 管理

| 命令 | 说明 |
|------|------|
| `openclaw sessions` | 列出所有 session |
| `openclaw sessions --agent <id>` | 列出指定 agent 的 session |
| `openclaw sessions --all-agents` | 列出所有 agent 的 session |
| `openclaw sessions --active 120` | 仅最近 120 分钟活跃 |
| `openclaw sessions --json` | JSON 输出 |
| `openclaw sessions cleanup --dry-run` | 预览清理 |
| `openclaw sessions cleanup --enforce` | 执行清理 |
| `openclaw sessions cleanup --active-key <key>` | 保护指定 key |

### 8.4 上下文检查

| 命令 | 说明 |
|------|------|
| `/status` | 快速查看上下文使用情况 |
| `/context list` | 查看注入内容 + 大小 |
| `/context detail` | 详细分解（per-file, per-tool, per-skill） |
| `/compact` | 手动压缩 |
| `/compact Focus on <topic>` | 引导式压缩 |
| `/new` | 新建 session |
| `/new <model>` | 新建 session 并切换模型 |

### 8.5 Gateway 管理

| 命令 | 说明 |
|------|------|
| `openclaw gateway start` | 启动 Gateway |
| `openclaw gateway stop` | 停止 Gateway |
| `openclaw gateway restart` | 重启 Gateway |
| `openclaw gateway status` | 查看状态 |
| `openclaw doctor` | 诊断问题 |
| `openclaw doctor --fix` | 自动修复 |

---

## 九、Plugin Hooks 扩展点

### 9.1 Agent 生命周期 Hooks

| Hook | 时机 | 用途 |
|------|------|------|
| `before_model_resolve` | 会话前（无 messages） | 覆盖 provider/model |
| `before_prompt_build` | 会话加载后（有 messages） | 注入 prependContext / systemPrompt |
| `before_agent_start` | 兼容钩子 | 优先使用显式 hooks |
| `before_agent_reply` | inline actions 后，LLM 调用前 | 拦截 turn，返回合成回复 |
| `agent_end` | 完成后 | 检查最终消息列表和元数据 |
| `before_compaction` / `after_compaction` | 压缩前后 | 观察或标注压缩周期 |
| `before_tool_call` / `after_tool_call` | tool 调用前后 | 拦截 tool 参数/结果 |
| `message_received` / `message_sending` / `message_sent` | 消息生命周期 | 入站/出站消息拦截 |
| `session_start` / `session_end` | 会话生命周期 | 会话边界事件 |

### 9.2 Gateway Hooks

| Hook | 时机 | 用途 |
|------|------|------|
| `agent:bootstrap` | 构建 bootstrap 文件时 | 添加/移除 bootstrap 上下文文件 |
| `before_install` | 安装前 | 拦截 skill/plugin 安装 |
| `tool_result_persist` | 持久化前 | 转换 tool 结果 |
| `gateway_start` / `gateway_stop` | Gateway 生命周期 | Gateway 启动/停止事件 |

### 9.3 Hook 阻断规则

| Hook | 阻断返回 | 说明 |
|------|---------|------|
| `before_tool_call` | `{ block: true }` | 终端阻断，阻止低优先级处理 |
| `before_tool_call` | `{ block: false }` | 无操作，不清除已有阻断 |
| `before_install` | `{ block: true }` | 终端阻断 |
| `message_sending` | `{ cancel: true }` | 终端阻断 |

---

## 十、对 DeepFlow 的设计输入

### 10.1 架构对齐清单

| OpenClaw 机制 | DeepFlow 对应设计 | 状态 |
|--------------|------------------|------|
| Agent = Workspace + AgentDir + Sessions | DeepFlow 的每个角色应有独立 session | ✅ 已对齐 |
| Bindings 路由规则 | DeepFlow 的消息路由到对应 Agent | ⚠️ 需确认 |
| Session 隔离（per-channel-peer） | 每轮迭代独立 session | ✅ 已对齐 |
| Auto-Compaction | 每轮迭代后上下文压缩 | ⚠️ 需实现 |
| Active Memory | 审计前主动检索历史案例 | ⚠️ 需实现 |
| Agent-to-Agent | CriticManager 聚合多审计结果 | ✅ 概念对齐 |
| Plugin Hooks | DeepFlow 的 before/after 钩子 | ⚠️ 需设计 |
| Unknown-Tool Guard | 工具可用性预检 | ⚠️ 需实现 |
| IdempotencyKey | spawn 幂等性控制 | ⚠️ 需实现 |
| LLM Idle Timeout | 分层超时策略 | ⚠️ 需实现 |

### 10.2 DeepFlow 应实现的关键机制

#### 10.2.1 角色隔离（参考 Multi-Agent Routing）

```python
# DeepFlow 每个角色应有独立的 session 上下文
role_session_map = {
    "planner": "agent:deepflow-planner:<session_id>",
    "auditor_correctness": "agent:deepflow-auditor-correctness:<session_id>",
    "auditor_security": "agent:deepflow-auditor-security:<session_id>",
    "auditor_performance": "agent:deepflow-auditor-performance:<session_id>",
    "fixer": "agent:deepflow-fixer:<session_id>",
    "verifier": "agent:deepflow-verifier:<session_id>",
    "critic": "agent:deepflow-critic:<session_id>",
}
```

#### 10.2.2 上下文预算控制（参考 Compaction）

```python
# 每轮迭代后压缩上下文
def compact_iteration_context():
    return {
        "issues_found": p0_p1_list,        # 保留关键发现
        "fix_applied": fix_summary,        # 保留修复方案
        "verification": test_pass_rate,    # 保留验证结果
        # 丢弃中间推理步骤
    }
```

#### 10.2.3 主动记忆检索（参考 Active Memory）

```python
# 审计前主动检索历史
def preload_memory(task_description):
    return memory_search(
        query=task_description,
        maxResults=5,
        minScore=0.7,
    )
```

#### 10.2.4 工具可用性预检（参考 Unknown-Tool Guard）

```python
def validate_tools_before_spawn(agent_type):
    available = get_registered_tools()
    required = get_required_tools_for_agent(agent_type)
    missing = set(required) - set(available)
    if missing:
        raise ToolNotFoundError(f"Agent {agent_type} requires tools not available: {missing}")
```

#### 10.2.5 分层超时策略

```python
TIMEOUT_CONFIG = {
    "quick": {"execution": 60, "idle": 30},
    "analysis": {"execution": 360, "idle": 120},
    "fix": {"execution": 600, "idle": 180},
    "deep_research": {"execution": 900, "idle": 300},
}
```

### 10.3 配置模板参考

```json5
// DeepFlow 在 openclaw.json 中的多 Agent 配置参考
{
  agents: {
    list: [
      {
        id: "deepflow-main",
        default: true,
        workspace: "~/.openclaw/workspace-deepflow",
      },
      {
        id: "deepflow-auditor",
        workspace: "~/.openclaw/workspace-deepflow-auditor",
      },
      {
        id: "deepflow-fixer",
        workspace: "~/.openclaw/workspace-deepflow-fixer",
      },
      {
        id: "deepflow-verifier",
        workspace: "~/.openclaw/workspace-deepflow-verifier",
      },
    ],
    defaults: {
      timeoutSeconds: 600,
      llm: { idleTimeoutSeconds: 120 },
      compaction: {
        model: "openrouter/anthropic/claude-sonnet-4-6",
        notifyUser: false,
      },
    },
  },
  bindings: [
    {
      agentId: "deepflow-main",
      match: { channel: "feishu" },
    },
  ],
  tools: {
    agentToAgent: {
      enabled: true,
      allow: ["deepflow-main", "deepflow-auditor", "deepflow-fixer", "deepflow-verifier"],
    },
  },
}
```

---

*文档版本：v1.0 | 2026-04-18*  
*基于 OpenClaw 官方文档 2026.4.15 版本整理*  
*用途：DeepFlow 架构设计与开发配置参考*
