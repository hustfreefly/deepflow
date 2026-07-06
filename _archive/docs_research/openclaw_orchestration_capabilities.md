# OpenClaw 编排能力边界调研报告

> 调研日期: 2026-06-16
> 调研方法: 官方文档分析 + 配置审查 + 最佳实践案例研究 (Solution Pro / Ship Pro / Spec Pro)

---

## 一、OpenClaw 能力清单（能做什么）

### 1.1 sessions_spawn 能力

| 能力维度 | 具体能力 | 配置/限制 |
|---------|---------|----------|
| **嵌套深度** | 支持最多 5 层嵌套（默认 1 层） | `maxSpawnDepth: 1-5`，推荐 depth 2 |
| **并发控制** | 全局并发 + 每 Agent 并发 | `maxConcurrent` (默认 8)，`maxChildrenPerAgent` (默认 5) |
| **运行超时** | 可配置默认超时 | `runTimeoutSeconds` (默认 0=无超时) |
| **上下文模式** | isolated（隔离）/ fork（继承父上下文） | 默认 isolated，fork 用于需要父上下文的场景 |
| **模型覆盖** | 子 Agent 可使用不同模型 | `model` 参数，支持为子 Agent 设置更便宜的模型 |
| **工具策略** | 可配置子 Agent 可用工具 | `tools.subagents.tools.allow/deny` |
| **线程绑定** | 支持绑定到消息线程 | `thread: true`，`mode: "session"` |
| **完成通知** | Push-based，自动通知父 Agent | 无需轮询，完成后自动 announce |

**关键能力**:
- ✅ 子 Agent 可以再 spawn 子 Agent（当 `maxSpawnDepth >= 2`）
- ✅ Depth-1 orchestrator 可获得 `sessions_spawn`, `subagents`, `sessions_list`, `sessions_history`
- ✅ Depth-2 leaf worker 不能再 spawn
- ✅ 级联停止：停止父 Agent 会自动停止所有子 Agent

### 1.2 exec 工具能力

| 能力 | 说明 |
|------|------|
| **执行环境** | `auto` / `sandbox` / `gateway` / `node` |
| **后台执行** | `background: true`，`yieldMs` 控制自动后台化 |
| **PTY 支持** | `pty: true` 用于需要 TTY 的 CLI |
| **超时控制** | `timeout` 参数，默认 1800s |
| **进程管理** | `process` 工具管理后台会话 |
| **安全控制** | `security`: deny/allowlist/full |

**可以运行**:
- ✅ 任何 shell 命令（受安全策略控制）
- ✅ 外部 CLI 工具（codex, claude, gemini 等）
- ✅ Python/Node 脚本
- ✅ 长时间运行的进程（后台模式）

**限制**:
- ❌ 不能直接运行需要 GUI 的程序
- ❌ 沙箱环境无法访问宿主机文件系统

### 1.3 ACP (Agent Client Protocol) 能力

| 能力 | 说明 |
|------|------|
| **支持的外部 Harness** | Claude Code, Codex, Gemini CLI, Cursor, OpenCode, Droid, Kiro, Kimi 等 |
| **会话模式** | `oneshot`（一次性）/ `persistent`（持久化） |
| **线程绑定** | 支持绑定到 Discord/Telegram 线程 |
| **会话恢复** | `resumeSessionId` 恢复之前的会话 |
| **流式输出** | `streamTo: "parent"` 流式传输进度 |

**关键能力**:
- ✅ 可以通过 `sessions_spawn({ runtime: "acp" })` 启动外部编码工具
- ✅ 支持会话绑定，后续消息自动路由到同一 ACP 会话
- ✅ OpenClaw 拥有路由、任务状态、交付、绑定和策略控制

### 1.4 Cron 和定时任务

| 能力 | 说明 |
|------|------|
| **调度类型** | `at`（一次性）/ `every`（固定间隔）/ `cron`（cron 表达式） |
| **时区支持** | `--tz` 参数支持时区 |
| **会话模式** | `main`（主会话）/ `isolated`（隔离会话）/ `session:<id>`（持久会话） |
| **交付方式** | `announce`（公告）/ `none`（无交付） |
| **超时控制** | `timeoutSeconds` |
| **失败通知** | `failureDestination` |

**关键能力**:
- ✅ 可以创建定时巡检任务（Solution Pro 的 cron watcher 模式）
- ✅ 隔离 cron 任务可以有自己的子 Agent
- ✅ 支持 webhook 触发
- ✅ 任务状态持久化，重启后恢复

### 1.5 Task Flow（流程编排）

| 能力 | 说明 |
|------|------|
| **同步模式** | `managed`（完全控制）/ `mirrored`（观察外部任务） |
| **持久化状态** | 跨重启保存进度 |
| **修订追踪** | 冲突检测 |
| **取消行为** | 级联取消所有子任务 |

**关键能力**:
- ✅ 可以编排多步骤工作流（A → B → C）
- ✅ 支持审批门控（approval gates）
- ✅ 与 Lobster 结合可实现确定性管线

### 1.6 Lobster（确定性工作流）

| 能力 | 说明 |
|------|------|
| **管线执行** | 多步骤 CLI 管线，一次调用 |
| **审批门控** | `approve` 步骤暂停等待人工确认 |
| **可恢复** | `resumeToken` 恢复暂停的工作流 |
| **JSON 管道** | 步骤间传递结构化数据 |

### 1.7 Plugin 系统

| 能力 | 说明 |
|------|------|
| **Provider 插件** | 文本推理、语音、图像生成、视频生成等 |
| **Channel 插件** | Discord, Telegram, Slack, WhatsApp 等 |
| **Hook 插件** | `before_tool_call`, `after_tool_call` 等生命周期钩子 |
| **工具插件** | 添加新工具（如 `llm-task`） |

**当前已安装插件** (8/99 enabled):
- `active-memory`: 记忆子 Agent
- `lossless-claw`: 无损上下文管理
- `feishu`: 飞书集成
- `openai`: OpenAI 集成
- `qwen-code`: 通义灵码
- `session-logs`: 会话日志
- `skill-workshop`: 技能工坊
- `telegram`: Telegram 集成

### 1.8 记忆和状态管理

| 能力 | 说明 |
|------|------|
| **Blackboard 文件系统** | 通过文件系统进行状态传递（DeepFlow 模式） |
| **会话存储** | SQLite 持久化 (`sessions.json`) |
| **记忆搜索** | QMD/LanceDB 后端，语义搜索 |
| **跨会话状态** | `sessions_history` 访问其他会话历史 |

---

## 二、OpenClaw 限制清单（不能做什么）

### 2.1 sessions_spawn 限制

| 限制 | 说明 |
|------|------|
| **最大嵌套深度** | 5 层（`maxSpawnDepth` 范围 1-5） |
| **每 Agent 最大子代** | 默认 5（范围 1-20） |
| **全局并发** | 默认 8（可配置） |
| **子 Agent 工具限制** | 默认无 `message`, `sessions_spawn`(depth-1 leaf), `sessions_send` |
| **上下文注入限制** | 只注入 `AGENTS.md` 和 `TOOLS.md`，不注入 `SOUL.md`, `MEMORY.md` 等 |
| **Announce 丢失** | Gateway 重启时，待处理的 announce 会丢失 |

### 2.2 exec 限制

| 限制 | 说明 |
|------|------|
| **沙箱隔离** | 默认关闭，需显式启用 |
| **PATH 覆盖** | `env.PATH` 覆盖被拒绝（安全考虑） |
| **LD_/DYLD_ 覆盖** | 被拒绝（防止二进制劫持） |
| **交互式命令** | `openclaw channels login` 被阻止 |

### 2.3 ACP 限制

| 限制 | 说明 |
|------|------|
| **沙箱不兼容** | ACP 会话不在沙箱内运行 |
| **工具暴露** | OpenClaw 工具默认不暴露给 ACP harness |
| **外部 Harness 依赖** | 需要目标 CLI 已安装且已认证 |
| **模型不便携** | 模型 ID 在不同 harness 间不通用 |

### 2.4 Cron 限制

| 限制 | 说明 |
|------|------|
| **非实时** | 最小粒度为分钟级 |
| **隔离会话无历史** | 隔离 cron 每次都是新会话，无上下文延续 |
| **超时处理** | 超时后强制终止，无法优雅恢复 |

### 2.5 记忆和状态限制

| 限制 | 说明 |
|------|------|
| **会话重置** | 每日 4:00 AM 自动重置（可配置） |
| **空闲重置** | 可配置空闲超时 |
| **记忆搜索延迟** | 语义搜索需要索引时间 |
| **跨 Agent 记忆** | 需要显式配置 `extraCollections` |

### 2.6 已知系统限制

| 限制 | 说明 |
|------|------|
| **Token 消耗** | 每个子 Agent 有独立的上下文和 token 使用 |
| **Gateway 单点** | 所有编排通过单一 Gateway 进程 |
| **重启影响** | 子 Agent announce 丢失，cron 任务恢复 |
| **并发限制** | 共享 Gateway 进程资源 |

---

## 三、作为"编排 Codex 的平台"，OpenClaw 的优劣势分析

### 3.1 优势

| 优势 | 说明 |
|------|------|
| **多 Harness 支持** | 不仅支持 Codex，还支持 Claude Code, Gemini CLI, Cursor 等 |
| **灵活的编排模式** | sessions_spawn + ACP + Cron + Task Flow 组合使用 |
| **消息通道集成** | 原生支持 Discord, Telegram, Slack, 飞书等 |
| **任务追踪** | Background Tasks 提供完整的状态追踪 |
| **会话绑定** | 可以将消息线程绑定到持久的 Codex 会话 |
| **定时巡检** | Cron watcher 模式适合长时间任务的进度监控 |
| **记忆系统** | 跨会话的记忆持久化 |

### 3.2 劣势

| 劣势 | 说明 |
|------|------|
| **复杂度** | 配置项繁多，学习曲线陡峭 |
| **单点故障** | Gateway 重启会导致进行中的编排丢失 |
| **Token 成本** | 每个子 Agent 独立上下文，重复传递上下文会消耗大量 token |
| **调试困难** | 多层嵌套 + 异步完成 = 调试复杂 |
| **状态管理分散** | 状态分散在文件系统、SQLite、会话存储中 |

### 3.3 与纯 Codex CLI 对比

| 维度 | OpenClaw 编排 | 纯 Codex CLI |
|------|--------------|-------------|
| **多 Agent 协作** | ✅ 原生支持 | ❌ 需要自己实现 |
| **进度通知** | ✅ Cron watcher | ❌ 需要轮询 |
| **会话持久化** | ✅ 会话绑定 | ⚠️ 需要手动管理 |
| **消息通道** | ✅ 多通道支持 | ❌ 仅 CLI |
| **定时任务** | ✅ 原生 Cron | ❌ 需要外部调度 |
| **启动开销** | ❌ Gateway 进程 | ✅ 直接启动 |
| **调试透明度** | ❌ 多层抽象 | ✅ 直接可见 |

---

## 四、关键发现：被忽略的编排能力

### 4.1 Task Flow（未被充分利用）

Task Flow 是 OpenClaw 的流程编排层，但 DeepFlow 目前主要依赖 sessions_spawn + cron watcher 模式。Task Flow 提供：
- 持久化的多步骤流程
- 修订追踪和冲突检测
- managed/mirrored 同步模式

**建议**: 对于 Solution Pro 的 10 阶段管线，可以考虑使用 Task Flow 替代文件系统状态管理。

### 4.2 Lobster（确定性管线）

Lobster 提供了确定性的管线执行，适合：
- 多步骤 CLI 调用
- 需要审批门控的工作流
- 可恢复的暂停/恢复模式

**建议**: 对于 Ship Pro 的编译流程，Lobster 可以提供更清晰的管线定义。

### 4.3 Depth-2 Orchestrator 模式

当 `maxSpawnDepth >= 2` 时，Depth-1 子 Agent 可以获得 `sessions_spawn` 能力，成为 orchestrator。这允许：
- 主 Agent → Orchestrator → Workers 的三层架构
- Orchestrator 可以动态 spawn Workers
- 主 Agent 不需要知道 Worker 细节

**当前 DeepFlow 模式**: 主 Agent 直接 spawn orchestrator，orchestrator 不再 spawn。

### 4.4 ACP 会话恢复

`resumeSessionId` 允许恢复之前的 ACP 会话，这支持：
- 跨设备的会话延续
- 中断后的恢复
- 会话的长期演进

### 4.5 Hooks 系统

OpenClaw 的 Hooks 系统可以响应各种生命周期事件：
- `session:compact:before/after`
- `message:received/sent`
- `gateway:startup/shutdown`

**建议**: 可以用于 DeepFlow 的状态检查和清理。

---

## 五、建议：OpenClaw 最适合的编排角色

### 5.1 最佳角色：**人机交互编排层**

OpenClaw 最适合做**人机交互的编排层**，而不是纯粹的后台任务调度器：

```
┌─────────────────────────────────────────────────────────────┐
│                    人机交互层                                │
│  (Discord/Telegram/飞书/Web → OpenClaw Gateway)             │
├─────────────────────────────────────────────────────────────┤
│                    编排决策层                                │
│  (主 Agent 理解意图，决定编排策略)                           │
├─────────────────────────────────────────────────────────────┤
│                    执行编排层                                │
│  (sessions_spawn / ACP / Cron / Task Flow)                  │
├─────────────────────────────────────────────────────────────┤
│                    工作执行层                                │
│  (子 Agents / Codex / Claude Code / Gemini CLI)             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 适合的场景

| 场景 | 为什么适合 |
|------|-----------|
| **需要人工介入的长流程** | 消息通道 + 审批门控 |
| **多工具协作** | ACP 支持多种 Harness |
| **需要进度通知** | Cron watcher + 消息交付 |
| **需要会话延续** | 会话绑定 + 记忆系统 |
| **需要定时触发** | 原生 Cron 支持 |

### 5.3 不适合的场景

| 场景 | 为什么不适合 |
|------|-------------|
| **纯后台批处理** | 启动开销大，不如直接用 CLI |
| **高并发任务** | 单 Gateway 进程限制 |
| **实时性要求极高** | 消息传递有延迟 |
| **简单的单次任务** | 过度工程化 |

### 5.4 对 DeepFlow 的建议

#### 当前架构评估

DeepFlow 当前的编排模式（Solution Pro / Ship Pro / Spec Pro）：
- ✅ 充分利用了 sessions_spawn
- ✅ 使用文件系统做状态管理（Blackboard）
- ✅ 使用 Cron 做进度巡检
- ⚠️ 状态管理分散在文件系统中
- ⚠️ 没有使用 Task Flow 的流程编排能力

#### 改进建议

1. **考虑使用 Task Flow 替代部分文件系统状态**
   - 对于 Solution Pro 的 10 阶段管线，Task Flow 可以提供更结构化的流程管理
   - 但需要评估迁移成本

2. **利用 Lobster 做确定性管线**
   - Ship Pro 的编译流程可以用 Lobster 定义
   - 获得审批门控和可恢复能力

3. **优化 Token 使用**
   - 为子 Agent 配置更便宜的模型
   - 使用 `context: "isolated"` 避免不必要的上下文传递

4. **增强错误恢复**
   - 利用 Task Flow 的持久化状态
   - 实现更优雅的断点续接

---

## 六、总结

### OpenClaw 的核心编排能力

| 能力 | 成熟度 | 适用场景 |
|------|--------|---------|
| sessions_spawn | ⭐⭐⭐⭐⭐ | 子 Agent 编排 |
| ACP | ⭐⭐⭐⭐ | 外部 Harness 集成 |
| Cron | ⭐⭐⭐⭐⭐ | 定时任务和巡检 |
| Task Flow | ⭐⭐⭐ | 多步骤流程编排 |
| Lobster | ⭐⭐⭐ | 确定性管线 |
| Plugin 系统 | ⭐⭐⭐⭐ | 能力扩展 |

### 关键限制

1. **单 Gateway 进程** - 扩展性受限
2. **重启丢失** - announce 和进行中的任务可能丢失
3. **Token 成本** - 多 Agent 编排的 token 消耗
4. **复杂度** - 配置和调试复杂

### 最终建议

**OpenClaw 适合做"有人参与的自动化编排"**，而不是"无人值守的后台调度"。

它的核心价值在于：
1. 将人的意图转化为编排动作
2. 通过消息通道与人保持交互
3. 协调多种工具和人协作完成任务

对于 DeepFlow 这样的复杂工作流系统，OpenClaw 提供了足够的能力基础，但需要：
- 清晰的状态管理策略
- 合理的 Token 优化
- 完善的错误恢复机制

---

*报告完成 | 2026-06-16*
