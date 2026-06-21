# Cancel Diagnosis: "Background task cancelled" 触发机制分析

**任务**: ship_orchestrator_ship_20260620_190416 (run 1f8a617d)
**诊断时间**: 2026-06-20
**诊断人**: cancel_diagnosis_expert (subagent)

---

## 1. 精确的 "Background task cancelled" 触发条件（源码确认）

### 1.1 消息生成链

```
task-registry-kPLgAJMa.js:132
  if (task.status === "cancelled")
    return `Background task cancelled: ${title}${runLabel}.`;
```

`runLabel` = ` (run ${shortId})` 当 task 有 runId 时。

### 1.2 status="cancelled" 的写入路径

**路径 A: `cancelTaskById()` (显式取消)**
- 调用 `updateTaskRecordExpectedRevision()` 将 status 设为 "cancelled"
- 同时设置 endedAt
- 触发 `syncManagedFlowCancellationFromTask()` 传播到父 flow

**路径 B: `mapAgentRunTerminalOutcomeToTaskStatus()` (run 结束映射)**
```javascript
// task-registry-kPLgAJMa.js:1456-1462
function mapAgentRunTerminalOutcomeToTaskStatus(outcome) {
  if (outcome === "completed") return "completed";
  if (outcome === "failed") return "failed";
  if (outcome === "cancelled" || outcome === "aborted") return "cancelled";
  return "failed";
}
```

当 agent run 的 terminal outcome 是 `"cancelled"` 或 `"aborted"` 时，task status 被映射为 `"cancelled"`。

### 1.3 agent run 变为 "aborted" 的触发条件

**触发点 1: `abortEmbeddedAgentRun(sessionId)`**
- 位于 `runs-DI_L8C_8.js:256`
- 设置 abort signal，终止正在进行的 LLM fetch
- 触发 `AbortError: This operation was aborted`

**触发点 2: 新消息中断 (handleSessionInterrupt)**
```javascript
// sessions-Dw172JRZ.js:394
if (hasEmbeddedRun && params.sessionId) abortEmbeddedAgentRun(params.sessionId);
```
当用户向一个有活跃 agent run 的 session 发送新消息时，先 abort 当前 run。

**触发点 3: Stuck session recovery**
```
stuck session recovery: sessionId=xxx age=376s action=abort_embedded_run
```
当 session 的 run 超过阈值时间（无响应），diagnostic 子系统自动 abort。

**触发点 4: Gateway shutdown/restart**
- `run-ELm7DZny.js:444-485` 中多处调用 `abortEmbeddedAgentRun()` 来清理活跃 runs

### 1.4 Task 通知链

```
cancelTaskById() / mapAgentRunTerminalOutcomeToTaskStatus()
  → updateTaskStatus() → status = "cancelled", endedAt = now
  → notifyTaskStatusChange()
  → formatTaskStatusChangeUserMessage()
    → "Background task cancelled: {title} (run {shortId})."
  → 通过 feishu channel 发送给用户
```

---

## 2. 这次事件的具体触发原因

### 2.1 时间线重建（从日志）

| 时间 | 事件 | 来源 |
|------|------|------|
| 19:05:16 | Orchestrator spawn 启动 | 任务描述 |
| 19:05:17 | Subagent tool policy applied (5 tools denied) | log:49595 |
| 19:05:30 | Cron job "deepflow_watcher_ship_202" created | log:49597 |
| **19:05:48** | **CRITICAL memory pressure: heap=2.45 GiB (122.3% of 2 GiB)** | log:49603 |
| 19:06:18 | Memory pressure warning: RSS=1.83 GiB (121.7% of 1.5 GiB) | log:49649 |
| 19:06:38 | Worker subagent tool policy applied (9 tools denied) | log:49669 |
| **19:06:45** | **agent.wait 88744ms completed** (parent session turn ended) | log:49670 |
| 19:06:48 | Orchestrator 开始执行 ("I'll execute the full 5-stage pipeline") | log:49673 |
| 19:08:30 | 另一个 feishu[default] session 收到消息（不相关） | log:49806 |
| ~19:09 | 用户收到 "Background task cancelled" 通知 | 用户报告 |
| 19:09:24 | 用户发消息给 feishu[product] 确认问题 | log:49849 |

### 2.2 根因分析

**最可能的触发原因：父 session turn 结束后的级联清理**

关键证据：
1. `agent.wait` 在 19:06:45 完成（88744ms = ~89秒），这标志着父 session (`agent:main2:feishu:product`) 的 agent turn 结束
2. Orchestrator 在 19:06:48 才开始输出（晚于 agent.wait 完成 3 秒）
3. 但 Orchestrator 的 endedAt 被设置为 19:06:45（与 agent.wait 完成时间一致）

**机制推断**：

当 Ship Pro 通过 cron job 触发时，流程是：
```
cron job → sessions_spawn (parent session turn) → sessions_spawn (Orchestrator) → sessions_yield
```

`sessions_yield` 让出当前 turn。当父 session 的 turn 被系统视为"完成"（agent.wait 返回），系统可能执行了 turn 结束后的清理逻辑。由于 Orchestrator 是作为 `mode="run"` 的 background task 注册的，当父 session 的 task 状态变化时，关联的子 task 也被清理。

**加剧因素：Critical Memory Pressure**

- 19:05:48 时 heap 达到 2.45 GiB（122.3% of 2 GiB threshold）
- 这是一个危险水位，可能触发 Gateway 的内存保护措施
- 内存压力可能导致某些 session/run 被提前回收

### 2.3 排除的原因

| 假设 | 排除依据 |
|------|---------|
| Gateway 重启 | 日志中无 shutdown/restart 记录 |
| API 超时 | bailian timeoutSeconds=600，实际只运行了 ~90s |
| 用户消息中断 | 用户在 19:09 才发消息，cancel 在此之前 |
| Stuck session recovery | 无 "stuck session recovery" 日志 |
| 显式 cancelTaskById | 无相关日志（但可能有遗漏） |

---

## 3. 推荐的避免方案

### 3.1 短期修复

**方案 A: 使用 `context: "isolated"` + 独立 session**

确保 Orchestrator 完全独立于父 session 的生命周期：
```javascript
sessions_spawn({
  runtime: "subagent",
  mode: "run",
  context: "isolated",  // 不继承父 session context
  task: "...",
  runTimeoutSeconds: 1800,  // 显式设置足够长的超时
})
```

**方案 B: 避免 sessions_yield 后立即结束父 turn**

在 Ship Pro 的 cron 触发模式中，确保父 session 的 turn 不会在 Orchestrator 完成前结束。可以用 `sessions_yield()` 等待完成事件。

### 3.2 中期优化

**方案 C: 降低内存压力**

当前 heap 经常超过阈值（2.45 GiB vs 2 GiB threshold），这增加了 Gateway 执行保护性清理的风险：
- 减少并发 subagent 数量
- 增加 compaction 频率
- 考虑重启 Gateway 释放内存

**方案 D: 使用 taskName + completion event 追踪**

给每个 Orchestrator spawn 设置 `taskName`，并在父 session 中等待 completion event，避免父 turn 过早结束。

### 3.3 长期架构

**方案 E: Ship Pro 管线改为单一长 session**

避免多层 spawn（cron → parent → orchestrator → workers），改为：
- Cron 直接触发 Orchestrator session
- Orchestrator 在同一 session 内顺序执行 workers
- 减少 session 层级，降低级联取消风险

---

## 4. 关键源码位置索引

| 文件 | 行号 | 功能 |
|------|------|------|
| task-registry-kPLgAJMa.js | 132 | "Background task cancelled" 消息格式 |
| task-registry-kPLgAJMa.js | 1456-1462 | outcome→status 映射（cancelled/aborted→cancelled） |
| task-registry-kPLgAJMa.js | 1704-1724 | Flow 级联取消逻辑 |
| runs-DI_L8C_8.js | 256 | abortEmbeddedAgentRun 定义 |
| sessions-Dw172JRZ.js | 394 | 新消息中断时 abort embedded run |
| run-ELm7DZny.js | 444-485 | Gateway shutdown 时 abort active runs |
| subagent-control-DDvyUyBI.js | 99 | killSubagent 调用 abortEmbeddedAgentRun |

---

## 5. 结论

**根因**: 父 session turn 结束（agent.wait 在 19:06:45 返回）后，系统清理了关联的 Orchestrator background task，将其 status 设为 "cancelled"，触发了通知。

**加剧因素**: Critical memory pressure (heap 2.45 GiB, 122.3% of threshold) 可能加速了清理决策。

**核心矛盾**: Ship Pro 的 cron 触发模式创建了一个"fire-and-forget"的 subagent，但 OpenClaw 的 task 生命周期与父 session turn 绑定。当父 turn 结束时，子 task 被视为 orphan 并被清理。

**推荐方案**: 使用 `context: "isolated"` + 显式 `runTimeoutSeconds` + 降低内存压力。
