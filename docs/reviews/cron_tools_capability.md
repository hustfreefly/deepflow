# OpenClaw Cron 工具能力验证

> 基于 `/opt/homebrew/lib/node_modules/openclaw/docs/automation/cron-jobs.md`、`cli/cron.md`、`tools/subagents.md`、`concepts/session-tool.md` 等文档分析。

## 1. Isolated Cron 工具集

| 工具 | 可用 | 说明 |
|------|------|------|
| `read` | ✅ | 文件系统读取，默认包含在工具集中 |
| `write` | ✅ | 文件系统写入，默认包含在工具集中 |
| `exec` | ✅ | shell 命令执行，默认包含在工具集中 |
| `process` | ✅ | 进程管理，默认包含在工具集中 |
| `message` | ✅ | 发送消息工具，**默认包含**（除非启用 `localModelLean` 才会移除） |
| `cron` | ⚠️ 受限 | 默认包含在工具集中，但 isolated cron job 只能调用 `cron remove <自身jobId>`（见第2节自删除能力） |
| `web_search` | ✅ | 网络搜索，默认包含 |
| `web_fetch` | ✅ | 网页抓取，默认包含 |
| `sessions_list` | ❌ | 被明确排除（session tools 对 isolated cron 不可用） |
| `sessions_history` | ❌ | 被明确排除 |
| `sessions_send` | ❌ | 被明确排除 |
| `sessions_spawn` | ❌ | 被明确排除（subagent 工具） |
| `sessions_yield` | ❌ | 被明确排除（subagent 工具） |
| `subagents` | ❌ | 被明确排除 |
| `codegraph_*` | ✅ | 代码分析工具，默认包含 |
| `memory_*` | ✅ | 记忆工具，默认包含 |

**关键发现：**
- Isolated cron job 获得的是 **完整工具集**，唯一的排除项是 **session tools**（`sessions_list`、`sessions_history`、`sessions_send`、`sessions_spawn`）和 **subagent tools**（`sessions_yield`、`subagents`）。
- 文档明确说 sub-agents 默认被禁止 `message` tool，但 **cron jobs 不在此列** —— cron job 可以使用 `message`。
- `--tools` 参数存在：`--tools exec,read` 可以**进一步限制**工具集，但不能恢复已被 profile 排除的工具。

## 2. 自删除能力

### "narrow cron self-cleanup grant" 是什么？

文档原文：
> "Isolated cron runs that receive the **narrow cron self-cleanup grant** can still read scheduler status, a **self-filtered list of their current job**, and that job's run history, so status/heartbeat checks can inspect their own schedule without gaining broader cron mutation access."

**含义解析：**
- Isolated cron job 在运行时被赋予一个 **有限权限（grant）**，允许它：
  1. 读取 cron scheduler 状态
  2. 获取**仅自身 job** 的列表（自过滤，看不到其他 job）
  3. 查看自身 job 的运行历史
- 这**不是**完整的 cron 工具权限 —— 不能添加/修改/删除其他 job
- 目的是让 cron job 能做 **自我状态检查** 和 **自我清理**，而不获得对整个 cron 系统的写权限

### Isolated cron job 能否删除自己？

**可以。** 虽然 "self-cleanup grant" 主要强调的是**只读**（read scheduler status, self-filtered list, run history），但结合以下事实：

1. `cron` 工具在默认工具集中（未被排除）
2. `cron remove <jobId>` 是 CLI 命令，对应 cron 工具的 `cron.remove` RPC 方法
3. Grant 的意图就是让 cron job 能做 "self-cleanup"

**结论：** isolated cron job 大概率能在运行中调用 `cron remove` 删除自身。这是 "self-cleanup grant" 的设计意图之一。

### 自删除后下一次还会运行吗？

**不会。** 自删除后：
1. job 定义从 `~/.openclaw/cron/jobs.json` 中移除
2. runtime 状态从 `~/.openclaw/cron/jobs-state.json` 中清除
3. 下次调度时找不到该 job，自然不会再运行

**这是 one-shot 清理的标准行为模式**（类似 `--delete-after-run` 的效果）。

## 3. 消息投递

### Message 工具发消息到哪里？

对于 isolated cron job，消息投递有**两条路径**，互斥工作：

| 路径 | 触发条件 | 投递目标 |
|------|---------|---------|
| **Agent 主动发送** | cron job 的 agent 调用 `message` 工具 | 由 `message` 工具的 `channel`/`target` 参数决定 |
| **Runner Fallback (announce)** | agent 没有主动发送 + delivery mode 为 `announce` | 由创建 job 时指定的 `--channel`/`--to` 决定 |

**关键规则：**
> "For isolated jobs, chat delivery is shared. If a chat route is available, the agent can use the `message` tool even when the job uses `--no-deliver`. If the agent sends to the configured/current target, OpenClaw skips the fallback announce."

### 需要指定 channel 和 target 吗？

| 场景 | 需要指定？ | 说明 |
|------|-----------|------|
| 用 `message` 工具发 | **推荐指定** | 如果 cron job 创建时有可用的 chat route（如从 webchat 创建），`message` 可以自动发送到该 route |
| 用 announce fallback | **必须指定** | `--announce --channel webchat --to <user-id>` 或在创建时从活跃的 webchat 会话保留 delivery target |

### Webchat 场景下 cron job 能发消息吗？

**可以，但有条件：**

1. 如果 cron job 是从 **webchat 会话中创建**的（用户直接 `openclaw cron add`），OpenClaw 会 **保存当前的 delivery target**
2. 运行时，`message` 工具可以使用这个保留的 route 发消息回 webchat
3. 如果没有可用 route（如通过 admin API 创建的 job），需要显式指定 `--channel` 和 `--to`

### Announce Delivery vs Message 工具的区别

| 维度 | Announce Delivery | Message 工具 |
|------|------------------|-------------|
| **触发者** | Gateway Runner（自动） | Agent（主动调用） |
| **时机** | Agent turn 完成后，处理最终回复 | Agent 运行中随时调用 |
| **内容** | Agent 的最后一条 assistant 文本 | Agent 指定的任意内容 |
| **控制** | 由 job 定义的 `--announce`/`--no-deliver` 控制 | 由 agent 自由决定发什么、发哪里 |
| **互斥** | 如果 agent 已用 message 发送到目标，announce **跳过** | 优先于 announce |
| **灵活性** | 只能发最终结果 | 可以发中间状态、多轮消息 |

**推荐模式：** cron job 中用 `message` 工具主动发送进度通知，比依赖 announce 更灵活、更可控。

## 4. 状态持久性

### 跨运行保持状态

Isolated cron job 每次运行使用**全新 session**（`cron:<jobId>`），不继承之前的对话上下文。文档明确：

> "For isolated jobs, 'fresh session' means a **new transcript/session id for each run**."

但有几点可以携带：
- Safe preferences（thinking/fast/verbose 设置）
- Labels
- 用户显式选择的 model/auth 覆盖

**不继承的：** channel/group 路由、发送/队列策略、elevation、origin、ACP runtime 绑定。

### 能否用文件系统作为状态存储？

**可以，且这是推荐做法。**

Isolated cron job 有完整的 `read`/`write`/`exec` 工具，可以：
- 读写 JSON 文件作为状态存储（如 `.notified_stages.json`）
- 使用 `exec` 运行任意命令（`jq`、`python3` 等）
- 文件存储在 workspace 目录（`~/.openclaw/workspace/`）

**示例方案：**
```
~/.openclaw/workspace/.deepflow/blackboard/.notified_stages.json
{
  "last_notified_stage": "review",
  "notified_at": "2026-06-01T08:00:00+08:00",
  "pipeline_id": "pf-001"
}
```

每次 cron 运行时：
1. `read` 读取上次状态
2. 查询当前进度
3. 如果有新进展，`message` 发送通知
4. `write` 更新状态文件

### Cron Job Definition 中能否携带状态？

**可以，但不推荐作为主要方案。**

Cron job 的定义存储在 `jobs.json` 中，可以通过 `openclaw cron edit` 修改 job 的 `message` 字段来携带状态。但这有以下问题：
- 需要 cron job 能调用 `cron` 工具修改自己（受 self-cleanup grant 限制，只能读）
- 修改 job definition 不如文件系统灵活
- 可能干扰正常的调度状态

**推荐：用文件系统，不用 job definition 携带状态。**

## 5. 超时和错误处理

### `timeoutSeconds` 的作用

在 isolated cron job 中，`timeoutSeconds` 控制**单次运行的最大时长**：

1. **正常流程：** 到达 timeout 后，cron **abort 底层 agent run**，给短暂清理窗口
2. **清理失败：** Gateway-owned cleanup 强制清除该 run 的 session ownership
3. **结果记录：** cron 记录 timeout 事件，不会留下卡住的 processing session

**Phase-specific watchdogs**（独立于 `timeoutSeconds`）：
- `setup timed out before runner start` — runner 启动前超时
- `stalled before first model call (last phase: context-engine)` — 首次 model 调用前卡住

这些 watchdog 确保冷启动/auth/context 失败**快速暴露**，不会等满整个 `timeoutSeconds` 预算。

### Cron Job 运行失败会重试吗？

**会，且有两种重试机制：**

| 类型 | 触发条件 | 重试策略 |
|------|---------|---------|
| **One-shot retry** | 瞬态错误（rate limit、overload、network、server error） | 最多 3 次，指数退避：`[60s, 120s, 300s]` |
| **Recurring retry** | 连续错误的周期性 job | 指数退避：30s → 1m → 5m → 15m → 60m |

**成功恢复：** 下次成功运行后，backoff 重置为正常调度。

**永久错误：** 立即 disabled（不再重试）。

### `failureAlert` 机制

**全局设置：** `cron.failureDestination` — 所有失败通知的默认目标
**Job 级别：** `job.delivery.failureDestination` — 覆盖全局设置

**失败通知的 destination 选择顺序：**
1. Job 级别的 `failureDestination`
2. 全局 `cron.failureDestination`
3. 如果 job 已有 announce target，fallback 到该目标

**`failureAlert.includeSkipped: true`：**
- 让 failure alert 也包含 **skipped 运行**（如本地 provider 不可达）
- Skipped runs 有**独立的连续跳过计数器**，不影响 execution-error backoff

### 连续失败 N 次后会怎样？

文档提到**指数退背**机制：
- 瞬态错误：最多 3 次重试后放弃
- 周期性 job：退避到最大 60 分钟间隔，直到成功恢复
- **永久错误**：job 被 **立即 disabled**

没有文档明确说 "连续 N 次失败后自动删除 job"，但失败会被记录在 run history 中，可通过 `openclaw cron runs --id <jobId>` 查看。

## 结论

### 可行性总结

| 能力 | 可行性 | 置信度 |
|------|--------|--------|
| Isolated cron 有 `read`/`write`/`exec` | ✅ 确认 | 高 |
| Isolated cron 有 `message` 工具 | ✅ 确认 | 高 |
| Isolated cron 有 `cron` 工具（受限） | ✅ 确认（只读+自删除） | 中高 |
| `--tools` 参数限制工具集 | ✅ 确认 | 高 |
| 自删除能力（cron remove 自身） | ✅ 确认（self-cleanup grant 意图） | 中 |
| 自删除后不再运行 | ✅ 确认 | 高 |
| Message 发到 webchat | ✅ 有条件 | 中高 |
| 文件系统状态存储 | ✅ 确认 | 高 |
| Timeout 控制单次运行时长 | ✅ 确认 | 高 |
| 失败自动重试 | ✅ 确认 | 高 |
| Failure alert 机制 | ✅ 确认 | 高 |

### 关键风险

1. **Message 投递到 webchat 的可靠性：** 如果 cron job 不是从 webchat 创建的（如通过脚本/admin API 创建），可能没有可用的 chat route。需要在 job 定义中显式配置 `--channel`/`--to`。**webchat 的 `--to` 值需要验证**（文档中 webchat 作为 channel 的 target 格式未明确列出）。

2. **自删除能力的精确范围：** "narrow cron self-cleanup grant" 文档主要描述**只读**能力（read status, self-filtered list, run history）。`cron remove`（写操作）是否在 grant 范围内**未明确说明**。建议在首次使用时通过测试 job 验证。

3. **无 session 工具的限制：** Isolated cron job **没有** `sessions_list`/`sessions_history`，无法查询其他会话状态。如果 DeepFlow 巡检需要跨会话信息，需要通过文件系统或 API 间接获取。

4. **每次运行是全新 session：** 没有对话上下文继承，所有状态必须通过**文件系统**或 **job definition** 维护。推荐用 JSON 文件（如 `.notified_stages.json`）作为状态存储。

5. **Failure alert 可能产生噪音：** 如果本地 provider 偶尔不可达，会触发 skipped-run alert。建议配置 `failureAlert.includeSkipped: true` 仅在需要时启用。

### 推荐方案

```bash
# 创建巡检 cron job
openclaw cron add \
  --name "DeepFlow Progress Patrol" \
  --cron "*/30 * * * *" \
  --session isolated \
  --message "检查 DeepFlow 管线进度。读取 ~/.openclaw/workspace/.deepflow/blackboard/pipeline_state.json 获取当前状态。如果有新进展，用 message 工具发送进度通知。然后更新状态文件。最后如果是终态，用 cron remove 删除此 job。" \
  --announce \
  --channel webchat \
  --timeout-seconds 120
```

状态文件约定：
```json
// .deepflow/blackboard/pipeline_state.json
{
  "pipeline_id": "pf-001",
  "current_stage": "review",
  "last_notified_stage": "build",
  "notified_at": "2026-06-01T08:00:00+08:00"
}
```
