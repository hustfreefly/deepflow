# 第三轮评审报告：分布式系统专家

> **评审人角色**: 分布式系统专家（并发安全、状态一致性、故障传播方向）  
> **评审日期**: 2026-06-25  
> **评审对象**: SHIP_PRO_AI_NATIVE_PROPOSAL.md V3  
> **评审轮次**: 第三轮（首次评审此方案）

---

## 总评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **状态一致性** | 7/10 | 原子写入+枚举校验到位，但 pipeline_state.json 存在 TOCTOU 竞态 |
| **并发安全** | 6/10 | 树状依赖图规避了多数问题，但 `runTimeoutSeconds` 参数不存在是 P0 |
| **故障隔离与恢复** | 7/10 | 断点恢复设计合理，但 announce 丢失场景未覆盖 |
| **超时与重试设计** | 5/10 | `runTimeoutSeconds` 不是 per-call 参数（P0），重试幂等性未讨论 |
| **总评分** | **6.5/10** | 架构方向正确，但有一个关键 API 误解需修复 |

**核心判断**: V3 方案的架构分层（LLM 决策 + Python 护栏）是正确的分布式系统思维，但 `sessions_spawn(runTimeoutSeconds=300)` 这个关键假设是错误的——该参数不存在于 per-call API 中，超时必须在 config 层设置。此 P0 修复后，方案可进入实施。

---

## 发现的问题

### P0

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P0-1 | **`sessions_spawn` 不接受 `runTimeoutSeconds` 参数** | 方案 §5.1 和 §6.1 多处使用 `sessions_spawn(runTimeoutSeconds=300)` 和 `sessions_spawn(runTimeoutSeconds=1800)`。根据 OpenClaw 官方文档（subagents.md），`sessions_spawn` **不接受 per-call timeout 参数**。超时只能通过 `agents.defaults.subagents.runTimeoutSeconds` 在 config 层全局设置，或 `agents.list[].subagents.runTimeoutSeconds` per-agent 设置。方案中的 Worker 300s / Orchestrator 1800s 超时分层设计无法实现。 | **方案 A**（推荐）：在 `start_ship_pro.py` 中通过 `openclaw config set` 动态设置 `agents.defaults.subagents.runTimeoutSeconds`，完成后恢复。**方案 B**：配置两个不同 agent id（`ship-worker` 和 `ship-orchestrator`），各自配置不同超时。**方案 C**：放弃分层超时，统一设置一个足够大的超时（如 1800s），在 io_helper.py 的 `check-budget` 中做软超时控制。无论哪种方案，§5.1 prompt 中的 `runTimeoutSeconds=300` 必须删除。 |
| P0-2 | **pipeline_state.json 并发读写竞态（TOCTOU）** | `write-status` 使用 `atomic_write`（write-to-temp + rename），保证单次写入原子性。但 `check-retry-limit` 读取 `retry_count` 和 `write-status` 更新 `retry_count` 之间无原子保证。如果 Orchestrator 在并行阶段场景下对同一阶段快速连续调用（虽然当前树状图不太可能），会出现：读 retry_count=2 → 另一进程写入 retry_count=3 → 本进程基于旧值判断 allowed=true → 超限重试。当前树状依赖图降低了风险，但代码层面未防护。 | 在 `check-retry-limit` + `write-status` 的组合操作上引入文件级 flock（`fcntl.flock`），或使用 write-status 内部自增 retry_count 并返回结果（check-and-set 语义），避免 read-then-write 竞态。建议实现 `io_helper.py increment-retry <output_dir> <stage>` 命令，原子地自增并返回是否超限。 |

### P1

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P1-1 | **Announce 丢失导致 Orchestrator 永久阻塞** | 官方文档明确："Sub-agent announce is **best-effort**. If the gateway restarts, pending 'announce back' work is lost." 如果 Worker 完成但 announce 在 gateway 重启中丢失，Orchestrator 调用 `sessions_yield()` 后将永远等不到 completion event，直到自身超时。方案 §3.4 的 .heartbeat 只解决 Orchestrator 自身的存活检测，不解决 Worker announce 丢失。 | 在 Orchestrator prompt 中增加"announce 丢失恢复"策略：如果 `sessions_yield` 后超过 Worker 预期时间 2 倍仍未收到 announce，主动调用 `subagents list` 检查 Worker 状态，如果 Worker 已完成但 announce 丢失，手动读取 Worker 输出文件继续流程。或者在 `io_helper.py` 中增加 `check-worker-status <label>` 命令封装此逻辑。 |
| P1-2 | **重试缺乏幂等性保障** | Worker 重试时，方案未讨论 Worker 自身是否幂等。如果 Worker 在写入部分输出后崩溃（如 architect 写了 `architecture_output.json` 但只完成 60%），重试时新 Worker 会覆盖文件。但如果新 Worker 读取了旧的部分输出作为输入（通过 `build-prompt` 注入），可能产生不一致。 | 在 `io_helper.py` 的 `write-status` 中，状态为 `running` 时清除该阶段的输出文件（或在 resume-context 中清除 `running` 状态阶段的输出），确保重试从干净状态开始。当前 resume-context 的文件扫描逻辑需要区分"完整输出"和"部分输出"——建议 Worker 写入时使用 temp+rename 模式，且 resume-context 对 `running` 状态阶段不信任其输出文件。 |
| P1-3 | **Orchestrator 与 Watcher 的状态冲突** | Watcher 独立监控 `.heartbeat` 和 `.completed`，Orchestrator 写入 `pipeline_state.json`。两者无共享状态锁。如果 Orchestrator 正在写 `pipeline_state.json`（rename 瞬间之前），Watcher 读取到旧状态并做出错误决策（如认为 Orchestrator 卡住而启动新实例），会导致两个 Orchestrator 并行运行。 | 在 `start_ship_pro.py` 中引入 PID 文件锁（`<output_dir>/.orchestrator.pid`），Watcher 启动前检查锁。或使用 `flock` 对 `<output_dir>/.lock` 加锁，Orchestrator 和 Watcher 共享。 |

### P2

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P2-1 | **decisions.jsonl 无大小限制** | 长时间运行的管线（多次重试、多阶段）会产生大量 decisions.jsonl 条目。`compact-history` 读取时会全量加载。 | 增加 `decisions.jsonl` 的 rotation 策略（如超过 200 行时由 compact-history 截断旧条目）。 |
| P2-2 | **`os.rename` 跨文件系统不原子** | `tempfile.mkstemp(dir=os.path.dirname(path))` 确保同目录，在 APFS/ext4 上 rename 是原子的。但如果 output_dir 在 network mount（NFS/SMB）上，rename 不保证原子性。 | 在方案中注明 output_dir 必须在本地文件系统。或增加 `fsync` 调用确保 durability。 |
| P2-3 | **check-budget 的时间源不可靠** | `check-budget` 计算 elapsed_minutes，但时间源是 Orchestrator 调用时的当前时间。如果 Orchestrator 的 exec 环境时钟被修改（罕见但可能），预算判断会出错。 | 使用 monotonic clock（`time.monotonic()`）而非 wall clock，在管线启动时记录基准时间。 |
| P2-4 | **并行阶段的 compact-history 时序** | 方案说"每完成 2 个阶段调用 compact-history"。并行阶段同时完成时，两个 completion event 几乎同时到达 Orchestrator，可能导致 compact-history 被调用两次（处理第一个 announce 时调一次，处理第二个时又调一次）。 | 在 compact-history 内部使用文件锁，或在 pipeline_state.json 中记录 `last_compact_at` 字段，避免 30s 内重复压缩。 |

---

## V3 P2 修复评估（重点关注 #13 #15 #16）

### #13 并行 blackboard 写入安全

**方案做法**：标注为 TODO，理由是"当前树状依赖图无风险"。

**评估**：**可接受，但需补充条件**。当前依赖图确实是树状：
```
architect → decomposer → specifier
         → reviewer → packager
```
可并行的组合只有 `decomposer + reviewer`（两者写不同文件）或 `specifier + reviewer`（不同文件）。无冲突。

**但**：方案应明确记录"blackboard 文件级锁是未来 work item，当且仅当依赖图出现两个并行阶段写同一文件时触发"。当前 §4 末尾的备注已做到这点，✅ 合格。

### #15 并行失败处理策略

**方案做法**：等待其他并行阶段完成 → 保留成功结果 → 仅重做失败阶段。

**评估**：**设计合理，但有一个边界条件未覆盖**。如果两个并行阶段 A 和 B，A 成功但 B 失败，B 的重试依赖 A 的输出（通过 build-prompt 注入）。如果 A 的输出在 B 重试期间被 compact-history 压缩（摘要替代完整输出），B 的重试可能拿到不完整的信息。

**建议**：在并行失败场景下，暂停 compact-history 直到失败阶段重试完成。或在 compact-history 中检查是否有 `running`/`gate_fail` 状态的阶段，有则跳过压缩。

### #16 write-status 时序窗口

**方案做法**：resume-context 扫描 blackboard 目录实际文件，自动修正 pipeline_state.json。

**评估**：**✅ 优秀设计**。这是经典的"trust but verify"模式，解决了 TOCTOU 中最危险的"写完成但状态未更新"场景。文件扫描 + state_corrections 输出的设计让 Orchestrator 能感知修正过程。

**一个建议**：修正时应验证输出文件的完整性（如 JSON 是否可解析、是否包含必要字段），而非仅检查文件存在。防止 Worker 崩溃时留下空文件或不完整 JSON，被误判为"已完成"。

---

## 其他观察

### 正面评价

1. **LLM 决策 + Python 护栏的分层设计** 是分布式系统中"flexible control + safety envelope"的正确实践。
2. **stage-dependencies.json 显式声明依赖** 避免了隐式耦合，使得 can-parallel 判断有确定性基础。
3. **check-retry-limit 从 stage-dependencies.json 读取（不可被 Orchestrator 覆盖）** 是正确的"不可信任 LLM 自限"思维。
4. **resume-context 的断点恢复设计** 考虑了多种故障场景，且与 .heartbeat 互补。
5. **三层验证（format → quality → LLM 评估）** 的分层质量门控，硬约束和软约束分离清晰。

### 风险提醒

1. **Orchestrator 是单点**：整个管线依赖一个 Orchestrator sub-agent 的 LLM 判断。如果 Orchestrator 进入死循环（反复重试同一阶段），只能靠 check-budget 和 runTimeoutSeconds 兜底。建议增加"连续 N 次相同决策"的检测（可在 io_helper.py 中实现）。
2. **上下文膨胀是渐进风险**：compact-history 每 2 阶段调用一次，但如果单阶段决策量极大（如 architect 反复修改），2 阶段内的上下文可能已经很大。建议增加 token 估算，当上下文超过阈值时触发压缩，而非仅按阶段数。

---

## 是否可以进入实施阶段？

- [ ] 是
- [x] 需要修复 P0 后进入实施（不需要第四轮全面评审）

**具体修复要求**：
1. **P0-1 必须修复**：删除 `sessions_spawn(runTimeoutSeconds=...)` 的错误用法，选择方案 A/B/C 之一实现超时控制。
2. **P0-2 建议修复**：实现 `increment-retry` 原子命令，或将 check-retry-limit + write-status 合并为单次原子操作。
3. **P1-1 建议在 prompt 中补充**：announce 丢失的降级策略。
4. **P1-2 建议在 resume-context 中处理**：`running` 状态阶段的输出文件不信任。

修复 P0 后，方案可以进入实施阶段，无需第四轮全面评审。P1 可在实施过程中解决。
