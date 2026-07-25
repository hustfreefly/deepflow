# Solution Pro 中断根因分析（2026-07-25）

> 项目：2.5D封装设计团队组建框架：面向CoWoS-S/L的PDK驱动型团队（两年路线图）
> 证据来源：session d1cfc179（orchestrator）、92a7345d（planning module）的 jsonl + trajectory 全量消息记录

## 一、完整时间线（UTC+8）

| 时间 | 事件 |
|------|------|
| 03:11:52 | Main spawn `solution_orchestrator`（depth-1, run-mode） |
| 03:12:36 | Orchestrator spawn `planning_module_v3`（depth-2），平台返回 accepted |
| 03:12:40.4 | Orchestrator 调 `sessions_yield`（距 spawn 仅 3.1 秒） |
| **03:12:40.6** | **Orchestrator session.ended — yield 后 200ms 被终止** ❌ 死因 1 |
| 03:13~03:14 | Planning Module 正常运行：checkpoint 恢复（step1→step2）、spawn planner worker、yield 等待 |
| 03:17:22 | Planner worker 完成事件到达，Planning Module 被唤醒，验证输出：`PLANNING_PLAN_OK` 但 `PLANNING_TASKS_MISSING`（stage 名漂移）⚠️ 问题 3 |
| 03:17:26 | Planning Module 收到**重复完成事件** → 回复 `NO_REPLY` → 无 pending children → run-mode session 自动关闭 ❌ 死因 2 |
| 03:16:52 | planning_plan.json（13KB）落盘——这是全部产出 |
| 04:28 | Main 收到 orchestrator 完成通告（"No completion text"），延迟 ~75 分钟 ⚠️ 问题 4 |

## 二、根因（三层）

### 死因 1：Orchestrator「yield 即自杀」（平台语义，主因）

Orchestrator 在 spawn 子 Agent 后 3.1 秒调 `sessions_yield`，**200ms 后 session 被平台终止**（trajectory: `session.ended` @ 19:12:40.665Z）。此后 Planning Module 的完成事件（03:17:26）到达时，父 session 已死 → 事件孤儿化 → 流水线无人调度 Research/Summary。

这与 MEMORY.md Pulse V1 条目记录的 Deliver Pro「07-23 E2E 实证 5 连死」是**同一平台语义**：run-mode session 在 yield 时若判定无 pending children（或注册竞态）即自杀。Solution Pro V3.1 的 Orchestrator 仍使用 spawn→yield 等待模式，踩中同一个坑。

**对比证据**：Planning Module（depth-2）同样 spawn 后 2.2 秒 yield，却**活下来**并被 worker 完成事件正常唤醒。说明该自杀不是 100% 触发，而是竞态/层级相关的不确定性行为——这更危险，因为测试时可能通过、生产时随机死。

### 死因 2：Planning Module「NO_REPLY 自杀」（Agent 行为 + 平台语义叠加）

Planning Module 被重复完成事件唤醒后，thinking 显示它知道该继续（"Contin..." 被截断），但输出了 `NO_REPLY`。run-mode 语义：turn 结束 + 无 pending children = session 自动关闭。它就此死在 Step 2，从未 spawn 6 个专家 Worker（Step 3）。

### 死因 3（次要）：checkpoint 未持久化 + stage 名漂移

- Step 2 完成后 checkpoint 未更新（仍记录 step1，时间戳停留在 23:42 首次尝试）→ 断点续跑会重做 Step 2
- Worker 写了 `planning_plan`，prompt 期望 `planning_tasks`（契约漂移，非致命）

### 问题 4（观察项）：完成通告延迟 75 分钟

Orchestrator 03:12:40 死亡，Main 04:28 才收到通告。期间 04:12 有一个 `solution-pro-progress-check` cron 触发（之前设置的兜底），可能才 flush 了通告队列。延迟本身不致命，但导致故障发现滞后。

## 三、修复方案

### P0：结构性修复（防复发）

**方案 A（推荐）：Main-Agent 直驱模式**
- 取消 depth-1 Orchestrator 的 yield 等待职责：由 Main Agent（持久 session，能可靠接收完成事件）直接顺序 spawn planning → research → summary 三个 Module Agent
- Orchestrator 降级为"prompt 生成器"（纯 Python，`run_solution_pro()` 已有），不再作为长驻调度者
- 依据：Main session 是唯一能可靠接收子 Agent 完成事件的层级；depth-1 run-mode yield 已被两次实证不可靠（Deliver Pro 5连死 + 本次）
- 改动量：orchestrator.md 重写为 3 段式指令给 Main Agent；Python 层零改动

**方案 B（重，仅当 A 不够时）：Pulse 化**
- 照搬 Deliver Pro Pulse V1：cron 点火 + 单次扫描 + 契约落盘
- 成本：Solution Pro 三模块状态机要重写，~2-3 天工作量

### P1：Agent 行为修复（prompt 层）

1. **NO_REPLY 禁令**：所有 Module Agent prompt 增加硬约束——"任务未完成时禁止输出 NO_REPLY。收到重复/意外完成事件 → 先验证 blackboard 状态 → 若仍有未完成步骤，继续执行（spawn 下一批 Worker），绝不用 NO_REPLY 结束 turn"
2. **checkpoint 即时持久化**：每个 Step 验证通过后**立即**写 checkpoint，再 spawn 下一批 Worker（当前顺序反了）
3. **stage 名契约对齐**：统一 `planning_plan` vs `planning_tasks`，改 prompt 或改验证代码（一处）

### P2：可观测性

4. **进度 cron 成为标配**：spawn Orchestrator/Module 时自动创建 progress-check cron（本次 04:12 的 cron 证明这个直觉是对的，但它救不了已死的 session，只能发现尸体）
5. **死亡检测**：progress-check 发现 session status=done 但 blackboard 无 `.completed` 标记 → 直接告警"流水线中断"，并附 checkpoint 状态

### 本次运行的恢复（立即执行）

1. 手动把 checkpoint 更新为 step2 完成（planning_plan.json 已验证 OK，6769 chars）
2. 重 spawn Planning Module，从 Step 3（6 专家并行）续跑
3. Planning 完成后，按方案 A 由 Main Agent 顺序驱动 Research → Summary

## 四、教训（建议入 MEMORY.md）

> `"depth-1 run-mode yield = 已两次实证必死（Deliver Pro 5连死 + Solution Pro 本次）。Module 级调度必须由 Main Agent 直驱或 Pulse 化，不再用 depth-1 长驻 Orchestrator yield 等待。"`

> `"NO_REPLY + 无 pending children = run-mode session 自杀。Module Agent prompt 必须禁止任务未完成时输出 NO_REPLY。"`
