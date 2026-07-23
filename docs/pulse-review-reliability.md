# Deliver Pro 脉冲式调度 — 可靠性评审报告

> 2026-07-23 | 评审人：分布式系统与可靠性工程专家 | 评审对象：pulse-scheduling-proposal.md V1

---

## 总评

提案方向正确——"derive-don't-sync" 文件系统契约 + 无状态 pulse 模型消除了长寿 session 破产风险，是今日 E2E 故障的正确解。但**现有代码与提案之间存在 4 个 P0 级差距**：`_save_progress()` 非原子写、孤儿 dispatch 恢复窗口长达 30-90 分钟、零重试预算、worker 超时与 stale 超时自相矛盾——这些在提案中均未提及对策。此外，cron 丢失恢复、429 后 dedup 死锁、`_pulse_actions.json` 作为进程内 IPC 三个 P1 问题必须在第一版 pulse 落地前解决。

---

## P0 级问题（不改会导致 pipeline 卡死/失控）

### P0-1: 两个 pulse 重叠 → batch_progress.json 竞态写 + 双派 worker

**证据**：
- `_save_progress()` 使用 `Path.write_text()`（orchestrator.py:121），不是原子 rename。两个 pulse 同时写入会截断对方数据，最坏情况丢失 dispatch 记录。
- `tick()` 的 dedup 逻辑（orchestrator.py:357-370）依赖 `batch_progress.json` 中 `last_spawned_action` 的一致性。若竞态导致记录丢失，两个 pulse 都会认为"未 dispatch"→ 双重 spawn 同一批 worker。
- 提案未提及任何文件锁或原子写入策略。

**建议**：
1. 用 `tempfile + os.replace` 实现原子写入（`os.replace` 在 macOS 上原子）。
2. 在 pulse 入口处加 PID 文件锁（`fcntl.flock`），确保同一时刻只有一个 pulse 运行。
3. 若锁已存在且超过 2 个 pulse 周期（10 min），强制清除锁并记录告警。

---

### P0-2: pulse session 在 tick 记录 dispatch 后、spawn 前死亡 → 孤儿 dispatch 卡 30-90 分钟

**证据**：
- `tick()` 在 line 407 写 `_save_progress()` 记录 dispatch 状态，但 `sessions_spawn` 由 LLM agent 在 pulse session 后续步骤执行（提案 3.1 节步骤 2-3）。
- 若 session 在 `_save_progress()` 后、`sessions_spawn` 前死亡 → `batch_progress.json` 有 dispatch 记录但 worker 从未被 spawn。
- 恢复依赖 `_is_stale_dispatch()`（orchestrator.py:420-427），超时阈值：`spawn_workers=5400s`（90 min），`analyze/validate/package=1800s`（30 min）。
- **提案将 pulse 周期设为 5 分钟，但恢复窗口是 30-90 分钟**——孤儿 dispatch 会阻塞该 WP 6-18 个 pulse 周期。

**建议**：
1. 将 dispatch 记录拆分为两阶段：`dispatch_intended`（tick 时写入）→ `dispatch_confirmed`（spawn 成功后写入）。`_is_stale_dispatch` 只检查 `dispatch_intended` 无 `dispatch_confirmed` 的记录，超时降为 2 个 pulse 周期（10 min）。
2. 或在 pulse 的 `exec` 阶段直接 spawn（若平台支持），消除记录与执行的时间差。

---

### P0-3: 永久性失败 worker → 无重试预算 → 每个 pulse 都重派，token 无限燃烧

**证据**：
- `error_count` 字段仅在 `report_done()` 中递增（orchestrator.py:391），**从未被任何条件检查读取**——它是计数器，不是限流器。
- `_is_stale_dispatch()` 只检查时间，不检查重试次数（orchestrator.py:420-427）。
- `derive_worker_progress()` 判定 worker 超时失败（phase_deriver.py:87-97）后，下次 pulse 的 `tick()` 会重新返回 `spawn_workers` action——没有任何上限。
- 今日故障证据：package prompt 路径歧义导致 5 个 agent 确定性失败（提案 1 节），若在 pulse 模型下，每 5 分钟重派 5 个 agent × 24 小时 = 1440 次无效重试。

**建议**：
1. 在 `batch_progress.json` 中维护 `retry_count` 字段，`_is_stale_dispatch` 读取并在超过阈值（如 3 次）后不再返回 `stale`，而是转入 `terminal_failed`。
2. `derive_worker_progress` 检测到同一 task_id 连续超时失败 ≥3 次时，写入 `blocklist.json`，后续 pulse 跳过该 task。
3. 配合 pulse 自报警：连续 N 次 pulse 零进展 → 飞书告警（提案已提，需落地）。

---

### P0-4: Worker 超时（30 min）与 stale dispatch 超时（90 min）自相矛盾

**证据**：
- `WORKER_TIMEOUT_SECONDS = 1800`（30 min）在 `phase_deriver.py:25`。worker 目录存在 30 分钟无 MANIFEST → `derive_worker_progress` 判 `failed`。
- `_STALE_DISPATCH_TIMEOUTS["spawn_workers"] = 5400`（90 min）在 `orchestrator.py:34`。
- 场景：worker 在 T+30min 被 derive 判 failed → pulse 想重派 → `tick()` dedup 检查 `last_spawned_action` → `_is_stale_dispatch` 返回 False（才过了 30min，没到 90min）→ dedup 跳过，WP 卡在 GENERATING 状态。
- **结果：worker 被 derive 判定失败，但调度层拒绝重派，WP 卡死 60 分钟。**

**建议**：
1. `_STALE_DISPATCH_TIMEOUTS["spawn_workers"]` 改为与 `WORKER_TIMEOUT_SECONDS` 一致或略高（如 35 min），确保 derive 判 failed 后下一次 pulse 即可重派。
2. 或者在 `tick()` 的 dedup 逻辑中增加一条：若 derive 已判该 worker 为 failed/timed_out，则无视 stale 超时直接允许重派。

---

## P1 级问题（特定条件下卡死/失控）

### P1-1: 429 限流时 spawn 失败 → dispatch 记录已写 → dedup 死锁 30-90 分钟

**证据**：
- `tick()` 在 line 407 先写 `_save_progress()` 记录 dispatch，再返回 spawn 列表给 LLM agent。
- 若 LLM agent 调用 `sessions_spawn` 时遇到 429 → spawn 失败，但 `batch_progress.json` 已记录 `last_spawned_action`。
- 下次 pulse 的 `tick()` dedup 检查（line 357）看到 `last_spawned_action == dedup_key` → 跳过。
- 恢复依赖 `_is_stale_dispatch`，超时 30-90 min。**429 是瞬时故障，但恢复窗口是 30-90 分钟。**

**建议**：
1. 在 `sessions_spawn` 失败时，调用 `report_done(wp_id, action, success=False)` 清除 `last_spawned_action` 记录。
2. 或在 pulse 执行流程中增加 spawn 失败回滚步骤：若任意 spawn 失败（429），同步清除对应 `batch_progress.json` 的 dispatch 记录。
3. MAX_IN_FLIGHT=8 硬上限可缓解 429 频率，但不能消除单次 spawn 的 429 可能性。

---

### P1-2: 网关重启后 cron 任务丢失 → pipeline 静默停摆

**证据**：
- 提案 3.2 节："cron 任务：`agentTurn` + `isolated`，每 5 分钟"。未提及持久化或恢复机制。
- 今日 watchdog cron 实证可用（提案 4 节），但**未说明 cron 注册方式及重启后是否自动恢复**。
- 若 cron 依赖内存注册（如 gateway 进程内调度器），重启后丢失，pipeline 无人触发。

**建议**：
1. 明确 cron 的持久化机制：若 gateway 支持持久化 cron（如 SQLite 存储），需验证重启恢复行为。
2. 增加 pulse 心跳监控：独立的 watchdog ping 检查最近一次 pulse 时间戳，超过 2 个周期（10 min）→ 飞书告警。
3. 将 `.deliver_completed.json` 的缺失作为辅助判断：若 pipeline 未完成 + 超过 10 min 无 pulse 记录 → 告警。

---

### P1-3: MAX_IN_FLIGHT=8 未实现，且与 pulse 周期无关联

**证据**：
- 提案 3.1 节声明 "MAX_IN_FLIGHT=8 并发硬上限"，但当前 `orchestrator.py` 中 `tick()` 和 `drive_once()` 返回所有符合条件的 spawn 动作，无任何并发控制。
- 提案说在 `pulse()` 方法中实现，但 `pulse()` 代码尚未存在。
- 今日 E2E 故障：15+ agent 同时打同一 provider → 疑似 429 加剧死亡（提案 1 节）。

**建议**：
1. 在 `pulse()` 中计算 `in_flight = running + 本次计划 spawn`，若超过 MAX_IN_FLIGHT 则截断 spawn 列表。
2. running 数量从 `derive_worker_progress` 的 `running` 集合获取（已在 phase_deriver.py 实现）。
3. 截断策略：优先 spawn 低 layer 的 WP（按 `execution_layers` 排序），已被截断的放入下个 pulse 优先队列。

---

### P1-4: 永久失败 WP 导致 all_done 永假 → pulse 无限循环

**证据**：
- `get_status()` 中 `all_done = completed == total_wps`（orchestrator.py:402），不包含 `terminal_failed`。
- 若某 WP 进入 `terminal_failed`（如 assembly 崩溃），`completed` 永远 < `total_wps`，`all_done` 永假。
- 提案的 ".deliver_completed.json" 写入条件为 `all_done`——永远不会写入。
- 提案未定义终端状态：pipeline 什么时候算"完成（含失败）"？

**建议**：
1. 定义 `all_resolved = completed + terminal_failed == total_wps`，作为 pipeline 终态。
2. 终态时写入 `.deliver_completed.json` 并包含 `terminal_failed` WP 列表。
3. 若存在 `terminal_failed`，pulse 输出明确告警并停止调度（不再每 5 分钟空转）。

---

### P1-5: 并发 pulse 写 `_pulse_actions.json` 竞态

**证据**：
- 提案 3.1 节："exec 跑 DeliverOrchestrator.pulse() → spawn 动作落盘 stages/_pulse_actions.json"。
- 两个 pulse 同时执行 → 同时写 `_pulse_actions.json` → 后写覆盖先写。
- 被覆盖的 pulse 的 spawn 动作丢失，但 **该 pulse 的 `batch_progress.json` 已写入 dispatch 记录** → 孤儿 dispatch（回 P0-2）。

**建议**：
1. 合并 P0-1 的 PID 文件锁方案，确保同一时刻只有一个 pulse 运行。
2. 若不做文件锁，则 `_pulse_actions.json` 应改为 per-pulse 命名（如 `_pulse_actions_{timestamp}.json`），避免跨 pulse 覆盖。

---

## P2 级问题（设计缺陷，不致命但会劣化）

### P2-1: `_pulse_actions.json` 作为进程内 IPC 是反模式

**证据**：
- 提案 3.1 节："exec 跑 pulse() → 落盘 _pulse_actions.json → 读文件 → 逐条 sessions_spawn"。
- 这是同一 session 内的 exec → LLM 通信。`exec` 的 stdout 已经是 IPC 通道，不需要额外文件。
- 额外文件增加失败点：文件写入失败、格式错误、LLM 解析错误。

**建议**：
- 让 `pulse()` 直接输出 JSON 到 stdout，LLM agent 从 exec 输出中解析 spawn 指令。
- 或反过来：LLM agent 先调用 `pulse()` 获取 spawn 列表（Python 返回值），再逐条 spawn——不需要文件。

---

### P2-2: `drive_all()` max_iterations=50 可能不够

**证据**：
- `drive_all()` 参数 `max_iterations=50`（orchestrator.py:499）。
- 26 个 WP × 多 phase × 多层 layer，极端情况下 50 次 tick 可能不够。
- 若 50 次内未完成，返回 `error: "max_iterations reached"` 但没有 spawn 动作——pulse 认为"无事可做"。

**建议**：
- `drive_all()` 在 pulse 模式下不应被调用（pulse 用 `drive_once()` 或新 `pulse()` 方法）。
- 若保留，将 `max_iterations` 调大到 200 或改为基于超时（如 60 秒 wall clock）。

---

### P2-3: 无 circuit breaker — 失败级联时 pulse 持续空转

**证据**：
- Layer 0 的 WP 若全部 `terminal_failed`，Layer 1+ 的所有 WP 因依赖不满足而卡在 PENDING。
- 每次 pulse 检查所有 WP → 没有任何可 spawn 的动作 → 输出空报告 → 下一个 pulse 同样结果。
- 提案的 "连续 N 次 pulse 零进展 → 报警" 可发现此问题，但未定义 N 的值和报警后的行为。

**建议**：
1. 定义 "零进展" 阈值：连续 3 次 pulse（15 min）无任何 spawn 动作且 `all_done` 为 false → 告警。
2. 告警后 pulse 行为：继续运行（人工介入）还是停止（避免空转）？需明确决策。

---

### P2-4: 提案未处理 `batch_progress.json` 的 Schema 演进

**证据**：
- `batch_progress.json` 结构在 `tick()` 中隐式定义（`last_spawned_action`, `last_spawned_at`, `last_action`, `action_count`, `error_count` 等）。
- 新增 `retry_count`、`dispatch_confirmed` 等字段时，旧 pulse 写入的 JSON 缺少这些字段。
- 无 version 字段，无迁移逻辑。

**建议**：
- 在 `batch_progress.json` 根对象增加 `"version": 1` 字段。
- `_load_progress()` 增加版本检测和迁移逻辑。

---

## 问题汇总

| ID | 严重度 | 问题 | 核心机制缺陷 |
|---|---|---|---|
| P0-1 | P0 | Pulse 重叠 → batch_progress.json 竞态 + 双派 | 非原子写 |
| P0-2 | P0 | 孤儿 dispatch 卡 30-90 min | 记录与执行分离 + 超时过长 |
| P0-3 | P0 | 无重试预算 → token 无限燃烧 | 无重试上限 |
| P0-4 | P0 | Worker 超时 30min vs stale 90min 矛盾 | 两个超时未对齐 |
| P1-1 | P1 | 429 spawn 失败 → dedup 死锁 | dispatch 记录无回滚 |
| P1-2 | P1 | Cron 丢失 → 静默停摆 | 无持久化/心跳 |
| P1-3 | P1 | MAX_IN_FLIGHT 未实现 | 代码缺失 |
| P1-4 | P1 | terminal_failed → all_done 永假 | 无终态定义 |
| P1-5 | P1 | _pulse_actions.json 竞态 | 共享文件竞态 |
| P2-1 | P2 | _pulse_actions.json 反模式 | 架构设计 |
| P2-2 | P2 | max_iterations=50 可能不够 | 参数选择 |
| P2-3 | P2 | 无 circuit breaker | 缺失机制 |
| P2-4 | P2 | Schema 无版本/迁移 | 工程实践 |

---

## 对提案的补充建议

1. **P0 修复优先级**：P0-1（文件锁）是 P0-2/P0-4/P1-5 的前置条件，应先修。
2. **P0-3（重试预算）**：建议与提案 3.4 节 "不做 retry 预算之外的高级重试策略" 形成互补——提案说的是不做指数退避等高级策略，但基本重试上限（3 次）是必须的硬约束。
3. **P1-2（cron 持久化）**：需在实现前确认 gateway cron 机制的重启行为，若不可靠则需外部 crontab 或 launchd 作为 fallback。
4. **P1-4（终态定义）**：影响 `.deliver_completed.json` 的写入条件，必须在第一版 pulse 落地前定义 pipeline 终态。
5. **提案 3.4 节 "不做跨域抽象"**：正确。但 `batch_progress.json` 的原子写、重试预算、终态定义是**跨域通用模式**，在 Deliver Pro 验证后应提取为可复用契约。