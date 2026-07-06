# 工具有效性评审

> 评审日期: 2026-06-01
> 评审目标: 验证 OpenClaw 工具链是否满足 DeepFlow 子 Agent 通知机制的设计需求
> 数据来源: OpenClaw 2026.5.20 官方文档

---

## 1. Sub-Agent 工具可用性

### 1.1 默认工具集

Sub-agent **不获得**以下工具（默认被排除）：

| 工具类别 | 具体工具 | 说明 |
|---------|---------|------|
| 消息工具 | `message` | sub-agent 不能直接向用户发消息 |
| 会话工具 | `sessions_list`, `sessions_history`, `sessions_send`, `sessions_spawn` | sub-agent 不能操控其他会话 |
| 系统工具 | `gateway` 等 | 系统级管理工具 |

**结论**: sub-agent（leaf，depth=1）默认 **不能** 使用 `sessions_send`。

### 1.2 `toolsAllow` 在 `sessions_spawn` 中是否支持？

**不支持。** `sessions_spawn` 的 schema 参数列表中没有 `toolsAllow`、`tools`、`toolsAllow` 或类似字段。可用参数为：

`task`, `taskName`, `label`, `agentId`, `runtime`, `resumeSessionId`, `streamTo`, `model`, `thinking`, `runTimeoutSeconds`, `thread`, `mode`, `cleanup`, `sandbox`, `context`

### 1.3 如何给 sub-agent 开放更多工具？

工具策略只能通过 **Gateway 配置** 修改，不能通过单次 spawn 调用动态指定：

```json5
{
  tools: {
    subagents: {
      tools: {
        deny: ["gateway", "cron"],   // deny 优先
        allow: ["read", "exec", "process"]  // allow-only 模式（不能加回 profile 移除的工具）
      }
    }
  }
}
```

**重要限制**: `tools.subagents.tools.allow` 是最终过滤器，只能 **收窄** 已解析的工具集，**不能** 加回 `tools.profile` 移除的工具。要让 sub-agent 获得 `message` 或 `sessions_send`，需要先在 profile 阶段包含它们（例如 `tools.profile: "coding"` 或 `tools.alsoAllow`），再用 allow 过滤器收窄。

### 1.4 开放 `sessions_send` 的安全风险

| 风险 | 评估 |
|------|------|
| 循环消息 | **高**。Sub-agent 通过 `sessions_send` 向主 Agent 发消息，主 Agent 回复，可能形成无限 ping-pong（虽然有 `maxPingPongTurns` 保护，默认 5 轮） |
| 权限泄露 | **中**。Sub-agent 获得的工具仍受主 Agent 的 tool policy 约束，但如果配置了 `allow: ["*"]` 级别的宽泛策略，sub-agent 可能获得超出预期的权限 |
| 跨会话污染 | **高**。`sessions_send` 可以向任何可见会话发消息（取决于 `tools.sessions.visibility` 配置），sub-agent 可能向无关会话注入消息 |
| ANNOUNCE_SKIP 绕过 | **低**。即使 sub-agent 回复 `ANNOUNCE_SKIP`，它仍可通过 `sessions_send` 主动发消息 |

**推荐做法**: 如果需要 sub-agent 主动通知主 Agent，使用 `sessions_spawn` 的默认 announce 机制即可，不需要额外开放 `sessions_send`。

### 1.5 深度嵌套时的工具策略

| 深度 | 角色 | 获得的会话工具 |
|------|------|---------------|
| Depth 0 | 主 Agent | 全部 |
| Depth 1 (maxSpawnDepth=1) | Leaf sub-agent | **无** |
| Depth 1 (maxSpawnDepth≥2) | Orchestrator sub-agent | `sessions_spawn`, `subagents`, `sessions_list`, `sessions_history` |
| Depth 2 | Worker sub-sub-agent | **无**（`sessions_spawn` 始终被拒绝） |

---

## 2. Cron 能力

### 2.1 Cron 能否在 sub-agent session 中运行？

**Cron 不在 sub-agent session 中运行。** Cron 是 Gateway 内置调度器，运行在 Gateway 进程内（不在 model 中）。

但有两种关联方式：

1. **Isolated cron jobs**：每个 run 创建独立的 `cron:<jobId>` 会话，不是 sub-agent 会话
2. **Isolated cron 可以编排 sub-agents**：文档明确提到 "When isolated cron runs orchestrate subagents, delivery also prefers the final descendant output"

### 2.2 Cron 能否动态添加/删除？

**可以。** 支持完整的 CRUD 操作：

| 操作 | CLI 命令 | API |
|------|---------|-----|
| 添加 | `openclaw cron add --name "..." --cron "0 * * * *" --session isolated --message "..."` | `POST /hooks/agent` 或 admin HTTP RPC `cron.add` |
| 编辑 | `openclaw cron edit <jobId> --message "Updated prompt"` | admin HTTP RPC `cron.update` |
| 删除 | `openclaw cron remove <jobId>` | admin HTTP RPC `cron.remove` |
| 手动触发 | `openclaw cron run <jobId> [--wait]` | admin HTTP RPC `cron.run` |
| 查询 | `openclaw cron list / get / show / runs` | admin HTTP RPC `cron.list / cron.get / cron.runs` |

Job 定义持久化在 `~/.openclaw/cron/jobs.json`，Gateway 运行中编辑后自动重新加载。

### 2.3 Cron 能否读写文件系统？

**可以。** Isolated cron jobs 运行在完整的 Gateway 环境中，拥有与正常 Agent 相同的 `exec`、`read`、`write` 工具（除非通过 `--tools` 参数限制）：

```bash
openclaw cron add --name "File watcher" --cron "*/5 * * * *" \
  --session isolated \
  --message "Check /tmp/status.txt and process if changed"
```

### 2.4 Cron 能否给用户发消息？

**可以。** 当 isolated cron job 有可用的聊天路由时，agent 可以使用 `message` 工具直接发送消息：

> "For isolated jobs, chat delivery is shared. If a chat route is available, the agent can use the `message` tool even when the job uses `--no-deliver`."

也可以通过 `--announce --channel <channel> --to <target>` 配置自动递送。

---

## 3. Announce 机制

### 3.1 Announce 流程

```
Sub-agent 完成 → Gateway 内 announce 步骤 → 结果回传 → 主 Agent 收到 completion event
```

1. Sub-agent 完成后，announce 步骤在 **sub-agent 会话内**运行（不在 requester 会话内）
2. 如果 sub-agent 回复恰好是 `ANNOUNCE_SKIP`，不发布任何内容
3. 如果最新回复是 `NO_REPLY`/`no_reply`，announce 输出被抑制

### 3.2 Announce 传递的元数据

| 字段 | 内容 |
|------|------|
| Source | `"subagent"` 或 `"cron"` |
| Session IDs | 子会话的 session key/id |
| Type | Announce 类型 + task label |
| Status | `success` / `error` / `timeout` / `unknown`（来自运行时，不是从文本推断） |
| Result content | 子 agent 最新可见的 assistant 文本 |
| 统计行 | runtime 时长、token 使用量（input/output/total）、成本估算 |
| 路径 | `sessionKey`、`sessionId`、**transcript path**（文件路径） |
| 后续指导 | 何时回复 vs 保持沉默的指令 |

**关键发现**: Announce **不包含文件路径列表**。它只包含 transcript path（会话日志文件路径），不包含 sub-agent 在执行过程中创建或修改的文件路径。

### 3.3 主 Agent 收到 announce 后的处理

1. Completion 作为内部 `agent` turn 回传到 requester 会话（带稳定幂等键）
2. 如果 requester 仍然活跃，OpenClaw 尝试唤醒/转向该 run
3. 如果无法唤醒，回退到 requester-agent handoff
4. 最终通过 queue routing 或 direct delivery 返回到用户 channel

对于嵌套场景（depth=2）：
1. Depth-2 worker 完成 → announce 给 depth-1 orchestrator
2. Depth-1 orchestrator 综合结果后完成 → announce 给 main
3. Main agent 收到后向用户交付

---

## 4. 轮询方案

### 4.1 主 Agent 能否在 turn 中反复 exec 检查文件？

**技术上可以，但不推荐。** `exec` 工具支持：
- 前台/后台执行
- `background: true` + `yieldMs` 启动后台进程
- `process` 工具轮询后台进程状态
- `timeout` 参数控制超时
- 后台 exec 完成时通过 `tools.exec.notifyOnExit`（默认 true）触发 heartbeat wake

### 4.2 推荐的轮询机制（按优先级）

| 机制 | 适用场景 | 推荐度 |
|------|---------|--------|
| **sessions_yield** | 等待 sub-agent 完成 | ⭐⭐⭐⭐⭐ |
| **Background task delivery** | 所有 detached work 完成后自动通知 | ⭐⭐⭐⭐⭐ |
| **exec notifyOnExit** | 后台 exec 完成后触发 heartbeat | ⭐⭐⭐⭐ |
| **Cron + isolated session** | 定期检查文件/状态 | ⭐⭐⭐ |
| **sessions_list + sessions_history** | 按需调试检查 | ⭐⭐⭐ |
| **exec sleep + 轮询** | **不推荐** | ❌ |

### 4.3 DeepFlow 推荐方案

对于子 Agent 通知机制，推荐以下组合：

```
方案 A（推荐）: sessions_spawn → sessions_yield → auto-announce
  - 主 Agent spawn sub-agent
  - 调用 sessions_yield 结束当前 turn
  - sub-agent 完成后自动 announce 回传
  - 零轮询，完全 push-based

方案 B（定期检查）: isolated cron job
  - 创建 cron job 定期检查 blackboard 文件
  - 有结果时通过 announce 或 message 通知
  - 适合需要周期性而非一次性的场景

方案 C（嵌套编排）: maxSpawnDepth=2
  - Main → Orchestrator sub-agent → Worker sub-sub-agents
  - Orchestrator 综合多个 worker 结果后 announce 给 main
```

**不要使用** exec sleep 循环或反复调用 sessions_list 轮询 sub-agent 状态 — OpenClaw 文档明确警告这是反模式。

---

## 结论

### 技术可行性总结

| 需求 | 可行性 | 路径 |
|------|--------|------|
| Sub-agent 向主 Agent 传递结果 | ✅ 原生支持 | Announce 机制（push-based） |
| Sub-agent 使用 `sessions_send` 主动通知 | ⚠️ 需配置 | Gateway config `tools.subagents.tools.allow`，有安全风险 |
| `sessions_spawn` 动态指定工具 | ❌ 不支持 | 无 `toolsAllow` 参数 |
| Cron 在 sub-agent 中运行 | ❌ 不运行在 sub-agent 中 | Cron 是 Gateway 进程级调度器 |
| Cron 动态添加/删除 | ✅ 支持 | CLI + HTTP RPC API |
| Cron 读写文件系统 | ✅ 支持 | 通过 exec/read/write 工具 |
| Cron 发消息给用户 | ✅ 支持 | message 工具 + 聊天路由 |
| Announce 传递文件路径 | ⚠️ 有限 | 仅传递 transcript path，不传递业务文件路径 |
| Exec 轮询文件变化 | ⚠️ 可行但不推荐 | push-based 方案更优 |

### 核心建议

1. **使用 announce 机制作为主要通知通道**：它是 OpenClaw 原生支持的 push-based 机制，无需轮询
2. **不要尝试通过 `sessions_send` 绕过 announce**：安全风险大于收益
3. **如果需要 sub-agent 创建文件并通知主 Agent**：在 sub-agent 的回复文本中包含文件路径，主 Agent 在收到 announce 后通过 `read` 工具读取
4. **Cron 适合定期任务，不适合一次性通知**：用 cron 做心跳检查，用 sub-agent 做一次性工作
5. **嵌套场景需要 `maxSpawnDepth: 2`**：否则 sub-agent 无法再 spawn worker

### 风险项

| 风险 | 影响 | 缓解 |
|------|------|------|
| Announce 是 best-effort，Gateway 重启会丢失 | 中等 | 配合 background task 记录做最终一致性检查 |
| Sub-agent 不获得 message 工具 | 高（如果依赖主动推送） | 使用 announce 或配置 allow |
| Announce 不包含业务文件路径 | 中 | 在 sub-agent 回复文本中显式包含路径 |
| maxSpawnDepth 默认 1 | 高（如果需要嵌套编排） | 配置 `maxSpawnDepth: 2` |
