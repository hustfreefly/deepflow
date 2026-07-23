# Deliver Pro 脉冲式调度架构平台语义评审

> 评审人：OpenClaw 平台工程专家  
> 依据：OpenClaw 官方文档（`/opt/homebrew/lib/node_modules/openclaw/docs`）及 2026-07-23 今日实证  
> 结论：方案在平台语义上**基本可行**，但有 3 个 P0/P1 级平台语义风险必须修复，另有 2 个 P1 级成本/告警风险需要加固。

---

## 1. 平台语义匹配结论（按评审维度）

### 1.1 cron `agentTurn` + `isolated` 里调用 `sessions_spawn` 是否可行？

**可行，但子 agent 完成通知语义与长寿 session 不同。**

- cron 支持 `agentTurn` + `isolated`，每次运行创建 `cron:<jobId>` 的独立 session（`automation/cron-jobs.md` 执行风格表）。
- `sessions_spawn` 是 agent tool，`tools.profile: "coding"` 或 `alsoAllow` 后即可在普通 agent turn 中使用；pulse 本身是顶层 cron agent turn，不是 sub-agent，因此不被 "sub-agents always lose `cron`" 限制（`tools/subagents.md` Tool policy 段）。
- **关键区别**：原 V3 的 orchestrator 是 depth-1 sub-agent（`maxSpawnDepth >= 2`），它的 children 是 depth-2 worker，完成事件会回传到 orchestrator session；而 pulse 是顶层 cron session，spawn 完即结束。Sub-agent 完成后的 announce 链目标是 requester session，若该 session 已结束，OpenClaw 会走 fallback 到 queue routing 或直接投递到 cron 的 chat channel（`tools/subagents.md` Completion delivery、Announce 段）。
- 因此：
  - 子 agent **会继续运行**，因为每个子 agent 都是独立 background task（`automation/tasks.md` What creates a task）。
  - 但它们的完成通知**可能丢失、延迟，或被投递到飞书**；方案不依赖事件，所以功能上可接受，但必须防止飞书刷屏。

### 1.2 每 5 分钟一个 isolated session 的 token 成本与配额影响？空转 pulse 每次烧多少？

**空转成本不可忽视，必须做两件事：启用 `--light-context` + 使用 cron event trigger 跳过无事可派的 pulse。**

- 默认 isolated agent turn 会注入完整 workspace bootstrap（`AGENTS.md`、`SOUL.md`、`TOOLS.md`、`MEMORY.md` 等），总计被 `agents.defaults.bootstrapTotalMaxChars` 默认限制为 **60,000 字符**（`reference/token-use.md`）。
- 即使空转，每个 pulse 也要：构建系统 prompt → 至少一次模型调用（读取 `_pulse_actions.json`、决定无操作、输出汇报）。按 5 分钟间隔计算，一天 288 次；空转一天的 prompt 字符就可达 **~17M chars/day**，按 ~4 chars/token 估算约 **4M tokens/day 仅用于空转**，再叠加输出 token。
- cron 支持 `--light-context`：isolated cron 运行可跳过完整 bootstrap（`automation/cron-jobs.md` CLI examples / `cli/cron.md`）。这能显著降低空转成本，但需要把 pulse 指令做到 prompt 自包含。
- 更进一步：cron 的 **event trigger** 可以在调度点先运行一段 headless script，仅当 `fire: true` 时才启动 agent turn（`automation/cron-jobs.md` Event triggers 段）。该 script 30s 预算、最多 5 次 tool call，可读取 `.deliver_completed.json` 与 `_pulse_actions.json` 决定是否点火。这样绝大多数空转 pulse 根本不会启动 LLM。

**配额影响**：
- 请求频次：每 5 分钟 1 次 + 最多 8 个并发 worker，对大多数 provider 不构成 rate-limit 压力。
- 但子 agent 的 token 累积是主要成本；建议把 worker 子 agent 配置为更便宜的模型（`agents.defaults.subagents.model`），并在 pulse job 上 `--model` 指定最便宜/最快的模型。

### 1.3 pulse 完成后能否自我删除 cron job？isolated session 的 cron 权限如何？

**可以删除自己的 job，但依赖 agent 正确调用 `cron` tool，且要在最后一步执行。**

- 文档明确说明：isolated run 拥有 **narrow cron self-cleanup grant**，只能查看自己的 job、自己的 run history，并且 **只能 remove 自己的 job**（`automation/cron-jobs.md` Isolated run hardening Accordion）。
- 因此 pulse 在检测到 `all_done == true` 后，可以调用 `cron(action: "remove", jobId: <self>)` 自我删除。
- 风险：
  1. 如果删除调用过早（例如在 spawn 动作落盘之后、子 agent 还没跑完），后续恢复会中断。应在 `all_done` 文件写入且**确认没有未完成的 worker** 后再删除。
  2. 如果删除失败（例如 agent 未拿到 `cron` tool，或权限受限），job 会永远每 5 分钟空转一次。必须在测试里验证 isolated cron 的 `cron` tool 可见性，并在外部保留一个手动清理后门。

### 1.4 网关重启后 cron job 的持久性？

**Job 定义持久，但运行中子 agent 的完成通知可能丢失。**

- cron job 定义、runtime state、run history 存在 OpenClaw 共享 SQLite state DB，**restart 不丢 schedule**（`automation/cron-jobs.md` How cron works、Retention）。
- 子 agent 的 announce 是 best-effort，**gateway restart 会丢失待处理的 announce back work**（`tools/subagents.md` Limitations）。
- 对 pulse 方案影响有限：因为状态以文件系统为准，下次 pulse 会从文件推导进度。但需要确保 worker 子 agent 把产物写到磁盘，而不是只返回在 announce text 里；当前 V3 已经是文件系统驱动，符合要求。
- 注意：gateway 重启期间正在运行的 pulse 可能被中断，其产生的 task 可能被标记 `lost`；下次 pulse 会重新 drive，但需保证 `drive_all`/`tick` 的幂等性（当前已有 dedup + stale 恢复）。

### 1.5 announce 到飞书的投递语义，STALLED 报警会不会刷屏？

**会刷屏，需要显式配置 failure-alert 冷却与 `failure-alert-after`。**

- `--announce` 会把最终回复 fallback 投递到指定 channel；pulse 计划每 5 分钟输出一行汇报，所以正常情况每 5 分钟就会有一条飞书消息（`automation/cron-jobs.md` Delivery、CLI examples）。
- 当 STALLED 时，pulse 自己报警，若没有抑制，将**每 5 分钟重复报警**。
- cron 原生支持告警收敛：`--failure-alert-after <n>`、 `--failure-alert-cooldown <duration>`、`--failure-alert-mode`（`automation/cron-jobs.md` Failure notifications）。应在 job 创建时设置这些参数，例如连续 3 次无进展才报警、冷却后 30 分钟/1 小时只报一次。
- 另外，子 agent 完成事件如果 fallback 到飞书 channel，也会产生额外消息。需要先跑一轮实测观察 subagent announce 在父 session 已结束时的行为，必要时把 pulse cron 设为 `--no-deliver` 并改为让 pulse 主动用 `message` tool 发送汇总，同时依赖 subagent 不对外 announce（需要验证）。

### 1.6 有没有平台原生机制可以替代这个方案的部分组件？

**有，以下原生机制应优先复用或对齐，而不是全部自己实现：**

1. **subagent 全局超时**：虽然 `sessions_spawn` 没有 per-call 超时参数，但可通过 `agents.defaults.subagents.runTimeoutSeconds` 设置默认超时（`tools/subagents.md` Tool parameters）。建议把 worker 超时与 `_STALE_DISPATCH_TIMEOUTS` 对齐，而不是完全靠文件推导的 stale 超时。
2. **并发上限**：`agents.defaults.subagents.maxConcurrent`（默认 8）是全局 subagent lane 上限；`maxChildrenPerAgent`（默认 5）限制每个父 session 的活跃子 agent 数（`tools/subagents.md` Nested sub-agents）。`cron.maxConcurrentRuns`（默认 8）限制 cron 自身并发。提案的 `MAX_IN_FLIGHT=8` 与这些默认值一致，但应明确说明它是**对每次 pulse  spawn 数量的额外硬限制**，以防止排队导致 dedup 失效。
3. **cron retry/backoff**：cron 对 transient 错误有 3 次重试（30s/60s/5m），连续错误会进入更长 backoff（`automation/cron-jobs.md` Configuration retry 段）。pulse 不必自己实现指数退避，但需要区分"真正无工作"与"provider 失败"。
4. **cron event trigger**：如 1.2 所述，可用来跳过空转。
5. **TaskFlow / background tasks**：`automation/taskflow.md` 提供持久化多步骤流程，是比文件+json 更原生的状态机。但用户要求"薄调度"，所以当前方案可以接受；若后续要泛化，应考虑 TaskFlow 替代 hand-rolled `_pulse_actions.json` + `.deliver_completed.json`。

---

## 2. 按 P0/P1/P2 分级的问题清单

### P0-1：并发 pulse 可能损坏 `batch_progress.json`（文件级竞态）

- **证据**：`orchestrator.py` 使用 `self.progress_path.write_text(json.dumps(...))` 直接覆写文件，没有文件锁或原子 rename（POSIX `rename` 才是原子写）。cron 的 `maxConcurrentRuns` 默认 8，且 `cron` schedule 每 5 分钟触发一次；如果某次 pulse 因模型/网络延迟超过 5 分钟，两个 isolated session 会同时读写 `batch_progress.json`，导致 JSON 损坏或 dedup 记录丢失。
- **建议**：所有落盘（`batch_progress.json`、`_pulse_actions.json`、`.deliver_completed.json`）改为 "write to temp + atomic rename"；或在 `pulse()` 入口用文件锁/目录锁保证同一 project 只有一个 pulse 在执行。最简方案：把 `_pulse_actions.json` 与进度文件写到不同文件，并对进度文件加 `fcntl.lockf`。

### P0-2：子 agent 在父 pulse session 结束后仍可能往飞书发 announce，导致刷屏

- **证据**：`tools/subagents.md` 说明 sub-agent 完成后会 announce 回 requester chat channel；当 requester session 已结束时会尝试 fallback 到 queue routing / direct delivery。pulse 方案 spawn 完即结束 session，因此 worker 完成时可能把结果推到 cron 的 `--announce` 飞书目标。
- **建议**：先做一次受控实验：创建 isolated cron job，spawn 一个 sleep 30s 的 sub-agent，job 在 spawn 后立即结束，观察飞书是否收到 worker 的 announce。若会刷屏，应把 subagent 的 delivery 设为 silent（当前 `sessions_spawn` 没有 `notify` 参数，但可在子 agent 的 task prompt 里要求最终只返回 `NO_REPLY`，并确保子 agent 没有 `message` tool）；同时把 pulse cron 的 `--announce` 改为 `--no-deliver` + pulse 主动 `message` 发送汇总，避免双重投递。

### P1-3：空转 pulse 的 token 成本高，且无原生 skip 机制

- **证据**：默认 isolated agent turn 注入 60k 字符 workspace bootstrap（`reference/token-use.md`），每 5 分钟 288 次/天。即使空转，一天也会消耗约 4M tokens 的 prompt。
- **建议**：
  1. pulse cron 加 `--light-context`，并在 `prompts/deliver_pulse.md` 中自包含所有必需上下文；
  2. 使用 cron event trigger 在启动 agent turn 前检查 `.deliver_completed.json` 与未完成的 worker 数量，无事时 `fire: false` 直接跳过，完全不调用 LLM（`automation/cron-jobs.md` Event triggers）。

### P1-4：STALLED 报警缺少冷却，可能每 5 分钟刷屏

- **证据**：cron failure notifications 支持 `--failure-alert-after`、`--failure-alert-cooldown`（`automation/cron-jobs.md` Failure notifications）。提案只提到"连续 N 次 pulse 零进展 → pulse 自己报警"，没有说明如何利用 cron 原生冷却。
- **建议**：在创建 cron job 时显式设置 `--failure-alert-after 3 --failure-alert-cooldown 30m`，并在 pulse 内部把"零进展"作为非致命状态报告；避免在每次 pulse 里主动调用 `message` 发送告警。若需要 pulse 内自定义报警文本，则自己维护一个 `last_alert_at` 文件做时间冷却。

### P1-5：`_STALE_DISPATCH_TIMEOUTS` 过长，死掉的 worker 会阻塞流水线长达 30–90 分钟

- **证据**：`orchestrator.py` 中 worker 的 stale timeout 为 5400s（90 min），analyze/validate/package 为 1800s。如果 worker 像 2026-07-23 那样"一行代码没写就死了"，在 90 分钟内不会重派，导致"无人值守跑完"目标被大幅拖慢。
- **建议**：把 worker timeout 降到与预期实际耗时匹配的值（例如 15–20 min 对于简单 package；大任务可更长），并把重派次数/总耗时上限写进契约。或者引入 worker 级 liveness：子 agent 启动后先写 heartbeat 文件，pulse 检测 heartbeat 超时即可提前判定死亡。

### P2-6：`cron` tool 在 isolated session 中是否可见需实测确认

- **证据**：文档说 isolated run 有 narrow cron self-cleanup grant（`automation/cron-jobs.md`），但并未明确说明该 grant 通过 agent `cron` tool 暴露；同时 `tools/subagents.md` 说 sub-agents lose `cron`，而 pulse 是顶层 cron turn，因此大概率可见。
- **建议**：在第一次部署 pulse 时，先用一个测试 job 验证 `cron(action: "list")` 能否返回且仅返回自己的 job；若不可见，则无法自我删除，需要把"完成后的 job 清理"改为外部二次 cron 或手动命令，而不是依赖 self-delete。

### P2-7：没有利用原生 `agents.defaults.subagents.runTimeoutSeconds`

- **证据**：`tools/subagents.md` 说明 `sessions_spawn` 没有 per-call timeout，但全局 `agents.defaults.subagents.runTimeoutSeconds` 可以控制子 agent 运行时长。提案在平台约束里写了"无 per-call spawn 超时参数"，但未说明如何设置全局超时。
- **建议**：在 agent config 中为 Deliver Pro worker 设置合适的 `runTimeoutSeconds`（例如 900–1800s），并把该值与 `_STALE_DISPATCH_TIMEOUTS` 对齐，避免子 agent 实际已被 kill 但 stale 恢复还要等更久。

---

## 3. 总体评估

脉冲式调度把"持续驱动"改成"无状态 tick + 文件系统真相"，与 OpenClaw 的 run-mode session 语义和 cron isolated session 模型**高度匹配**，解决了长寿 orchestrator session 自杀的核心问题。该方案在平台层可行，且 cron job 持久化、self-cleanup grant、subagent background task 等原生机制都能支撑。

但方案在**并发安全、飞书投递副作用、空转成本、STALLED 报警收敛、worker 死亡检测延迟**五个方面存在可落地的缺陷。建议在实施前：
1. 把所有进度/动作文件改为原子写或加锁；
2. 用 event trigger 跳过空转，并加 `--light-context`；
3. 做一轮 subagent announce 行为实测，避免飞书刷屏；
4. 调整 stale timeout 并配置全局 subagent timeout；
5. 显式配置 cron failure-alert 冷却。

修复后，该方案具备让 26 个 WP 无人值守跑完的基础，且泛化成本较低。
