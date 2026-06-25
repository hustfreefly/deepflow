# 评审报告：可靠性工程专家

> **评审人**: 可靠性工程专家（AI Agent）  
> **评审日期**: 2026-06-25  
> **评审对象**: Ship Pro AI Native 改造方案  
> **评审维度**: 容错、状态恢复、错误处理

---

## 总评

- **总评分**: 4.5/10
- **核心判断**: 方案将控制流从确定性 Python 状态机交给 LLM，但**没有提供等价的可靠性保障机制**。当前 V4 的硬编码重试、Pydantic 状态契约、Watcher 熔断是被删除了，但替代方案只有一句 "Orchestrator 自己判断"。这不是 AI Native，这是**可靠性裸奔**。

---

## 逐维度评审

### 1. 状态一致性 (4/10)

**当前 V4 做得好的地方**：
- `pipeline_state.json` 由 Python `_save_status()` 独占写入，LLM 不直接操作状态文件
- `PipelineState` Pydantic 模型做写入前验证（`contracts/pipeline_state.py`）
- 状态枚举是封闭的：`pending | running | gate_pass | gate_conditional | gate_fail | skipped | done`
- `_update_gate_status()` 是唯一状态转换函数，保证转换逻辑一致

**新方案的问题**：

1. **谁写 `pipeline_state.json`？** 方案说 `io_helper.py write-status`，但这是 LLM 通过 `exec` 调用的。LLM 决定**何时**调用、传**什么参数**。如果 LLM 忘记调用 `write-status`（prompt 没强制），状态文件就不更新。
   
2. **LLM 可以传任意值**。`io_helper.py write-status <output_dir> <stage> <status>` — `<status>` 是自由字符串，不是枚举。LLM 可能写入 `"status": "almost_done"` 或 `"stage": "architec"`（拼写错误），io_helper 如果不做校验就会写入脏数据。

3. **并发写入风险**。Orchestrator 可能在 sessions_spawn 的 worker 还没写完输出文件时就调用 `write-status`，导致状态和实际文件不一致。当前 V4 不存在这个问题，因为 gate check 在 Python 控制流内同步执行。

4. **`decisions.jsonl` 不是状态文件**。方案提到用 `decisions.jsonl` 记录决策，但没有说明它和 `pipeline_state.json` 的关系。如果两者冲突，以谁为准？

**建议**：
- `io_helper.py write-status` 必须做枚举校验（只接受预定义状态值）
- 增加 `io_helper.py` 的原子写入（write-to-temp + rename）
- 明确 `decisions.jsonl` 是审计日志，不是状态源

### 2. 断点续接 (3/10)

**当前 V4 的断点机制**：
- `pipeline_state.json` 记录每个 agent 的精确状态
- `.stage_progress.json` 记录 `current_stage`、`completed_stages`、`failed_stages`
- Watcher 通过扫描这些文件检测卡住
- `prepare_pipeline()` 清理旧状态文件防止误判

**新方案的问题**：

1. **没有断点恢复设计**。方案完全没有提到 "如果 Orchestrator 崩溃，如何恢复"。当前 V4 的 `pipeline_state.json` 可以在 Orchestrator 重启后被读取恢复进度，但新方案的 Orchestrator 是 LLM，它没有 "读取状态文件 → 恢复执行" 的机制。

2. **LLM 不会自动恢复**。sessions_spawn 创建的 Orchestrator 如果中途超时（session 被回收），新的 session 不会自动继承上下文。方案没有设计 "从 pipeline_state.json 重建 Orchestrator 上下文" 的流程。

3. **并行阶段增加恢复复杂度**。方案说 "决定哪些阶段可以并行"，但没有说明：
   - 如果 3 个并行 Worker 中 1 个失败，其他 2 个的结果怎么处理？
   - 恢复时是否需要重做已完成的并行阶段？

4. **`io_helper.py scan-progress` 是给 Watcher 用的，不是给恢复用的**。方案没有设计 Orchestrator 自身的恢复命令（如 `io_helper.py resume-from <output_dir>`）。

**建议**：
- 必须设计 `io_helper.py resume-context <output_dir>` 命令，输出 Orchestrator 恢复所需的完整上下文（哪些阶段完成、哪些进行中、哪些失败）
- Orchestrator prompt 必须包含 "启动时先检查是否有未完成的状态" 的指令
- 并行阶段的恢复策略需要明确定义

### 3. 错误传播 (5/10)

**当前 V4 做得好的地方**：
- 硬编码 `GATE_CONFIG` 保证每个阶段有明确的重试上限
- Gate 函数返回结构化结果（critical/major/minor），反馈精确
- Skip 机制：重试耗尽后标记为 skipped，不阻塞管线
- Feedback task 自动生成，包含具体失败点和修正要求

**新方案的问题**：

1. **"最多 3 次" 在 prompt 里，不在代码里**。方案说 "遇到问题自己尝试解决（最多 3 次）"，但这是 LLM 的 prompt 约束，不是代码约束。LLM 可能因为上下文窗口丢失而忘记这个限制，导致无限重试。

2. **重试策略由 LLM 决定的风险**：
   - LLM 可能对同一个问题反复重试（"我觉得这次能过"），而不是分析失败原因换方案
   - LLM 可能过早放弃（"这个太难了，跳过吧"），而实际上只差一步
   - LLM 没有 "失败记忆"——每次重试它需要重新读 gate 反馈，但上下文窗口可能已经丢失之前的失败细节

3. **Worker 失败 → Orchestrator 处理的流程不明确**。方案只说 "评估输出质量 → 通过/改进/重做/换方案"，但没有定义：
   - Worker session 超时怎么办？（sessions_spawn 有 timeout 但 Orchestrator 怎么处理 timeout 事件？）
   - Worker 输出了非法 JSON 怎么办？（`validate-format` 返回 fail 后 Orchestrator 的具体流程）
   - Worker 输出格式正确但内容完全是胡话怎么办？（LLM 质量评估的 false positive）

4. **没有全局错误升级机制**。当前 V4 的 skip 机制保证管线不会因为单个阶段失败而卡死。新方案说 "实在不行再上报"，但上报的触发条件、上报格式、上报后的恢复都没有定义。

**建议**：
- 重试上限必须在 `io_helper.py` 中用代码强制执行，不能只靠 prompt
- 增加 `io_helper.py check-retry-limit <output_dir> <stage> <max>` 命令，返回是否超限
- 定义 Worker 失败的分类处理流程（超时 vs 格式错误 vs 内容错误）
- 设计明确的升级条件和升级消息格式

### 4. 超时保护 (3/10)

**当前 V4 的超时机制**：
- `watcher_config.json` → `limits.timeout_minutes: 30`
- `limits.max_runs: 15`（最多 15 次 cron 巡检）
- `circuit_breaker_threshold: 3`（连续 3 次无输出触发熔断）
- Watcher cron 每 3 分钟独立运行，不依赖 Orchestrator
- `AGENT_TIMEOUTS` 每个 Worker 有独立超时（180-300 秒）

**新方案的问题**：

1. **Orchestrator 本身没有超时保护**。当前 V4 的 Orchestrator 是 Python 脚本，有 Watcher 监控。新方案的 Orchestrator 是 LLM session，如果它进入无限循环（规划 → 执行 → 评估 → 再规划 → ...），谁来终止它？

2. **Watcher 能检测 "无输出"，但检测不了 "LLM 空转"**。如果 Orchestrator 一直在调 `io_helper.py`（有文件变化），Watcher 不会触发熔断，但实际上 Orchestrator 可能在反复重试同一个失败阶段。

3. **没有全局 token/时间预算**。方案提到 "Token 消耗增加" 是风险，但应对措施只有 "Orchestrator 用 strong 模型，Worker 可降级"。没有设计：
   - Orchestrator session 的最大 token 消耗上限
   - 管线的最大 wall-clock 时间
   - 超预算时的降级策略

4. **并行 Worker 的超时叠加**。如果 Orchestrator 并行启动 3 个 Worker，每个 Worker 300 秒超时，Orchestrator 自身可能等待 300 秒后才继续。如果 Orchestrator 没有设置总超时，它可能串行等待多个 300 秒。

**建议**：
- 必须为 Orchestrator session 设置 `runTimeoutSeconds`（建议 1800 秒 = 30 分钟）
- `io_helper.py` 增加 `check-budget <output_dir> <max_minutes>` 命令，检查是否超预算
- Watcher 增加 "重试次数异常" 检测（同一阶段 retry > 3 次触发告警）
- 设计 Orchestrator 的 "自杀条件"：总时间 > X 分钟 或 总重试 > Y 次 → 上报并终止

### 5. 回滚能力 (7/10)

**当前 V4 做得好的地方**：
- 方案明确说 "保留旧 run_pipeline.py 作为 backup"
- `pipeline_state.json` 格式稳定，有 Pydantic schema 约束
- Watcher 配置独立于 Orchestrator 实现

**新方案的问题**：

1. **状态文件兼容性未定义**。如果 AI Native 版本运行到一半崩溃，`pipeline_state.json` 可能处于中间状态。回滚到 V4 后，V4 的 `prepare_pipeline()` 会清理旧状态文件——这意味着 AI Native 版本已完成的部分输出也会被清理。

2. **`io_helper.py` 和 `run_pipeline.py` 的 CLI 接口不同**。回滚需要切换 CLI 调用（从 `io_helper.py task` 切回 `run_pipeline.py task`），但 Main Agent 的 SKILL.md 已经更新为新接口，回滚时需要同时回滚 SKILL.md。

3. **Blackboard 文件兼容**。好消息是 blackboard 文件（各阶段输出）的格式不变（都是 JSON），所以回滚后 V4 可以读取 AI Native 版本已完成的阶段输出。但 V4 的 `prepare_pipeline()` 会主动删除这些文件（"Clean up stale state files"），需要修改 V4 的清理逻辑才能支持 "从中间恢复"。

4. **没有回滚演练**。方案说 "随时可以切回 V4.0"，但没有定义回滚的具体步骤和验证方式。

**建议**：
- 定义明确的回滚 SOP（Standard Operating Procedure）
- AI Native 版本的状态文件增加 `"version": "ai_native"` 标记，V4 能识别并跳过不兼容的状态
- 修改 V4 的 `prepare_pipeline()` 增加 `--resume` 模式，不清理已有的阶段输出
- 至少做一次回滚演练并记录结果

---

## 必须修改的问题（P0/P1）

| # | 严重度 | 问题 | 建议 |
|---|--------|------|------|
| 1 | **P0** | Orchestrator 无超时保护，可能无限循环 | 为 Orchestrator session 设置 `runTimeoutSeconds`；`io_helper.py` 增加 budget check 命令；设计自杀条件 |
| 2 | **P0** | 重试上限只在 prompt 中，无代码强制 | `io_helper.py` 增加 `check-retry-limit` 命令，Orchestrator 每次重试前必须调用 |
| 3 | **P0** | 无断点恢复设计 | 增加 `io_helper.py resume-context` 命令；Orchestrator prompt 必须包含启动时恢复检查 |
| 4 | **P1** | `write-status` 无枚举校验，LLM 可写脏数据 | `io_helper.py write-status` 必须校验 stage 名称和 status 值的合法性 |
| 5 | **P1** | 状态文件无原子写入 | 使用 write-to-temp + os.rename 保证原子性 |
| 6 | **P1** | 回滚时 V4 会清理 AI Native 版本的中间输出 | 增加版本标记 + resume 模式 |
| 7 | **P1** | 并行阶段失败处理未定义 | 明确并行 Worker 部分失败时的策略（等待全部？取消未完成？重做失败？） |

## 建议改进（P2）

- **`decisions.jsonl` 结构化**：定义 schema（timestamp, decision_type, reason, stage, outcome），方便后续 Dream Loop 消费
- **增加 dry-run 模式**：`io_helper.py` 支持 `--dry-run` 参数，模拟状态变更但不实际写入，用于调试
- **Orchestrator 心跳**：Orchestrator 每次循环写一个 `.heartbeat` 文件（含时间戳），Watcher 用它判断 Orchestrator 是否存活
- **状态文件版本化**：`pipeline_state.json` 增加 `schema_version` 字段，便于未来迁移
- **错误分类体系**：定义 Worker 错误的分类（transient/permanent/unknown），不同类别不同处理策略
- **回滚演练**：在测试环境实际执行一次 AI Native → V4 回滚，验证状态兼容性

## 亮点

- **`io_helper.py` 的 I/O 与 LLM 分离设计是正确的**。Python 做文件读写和格式校验，LLM 做决策——这是 AI Native 的核心原则，方案把握住了。
- **保留旧 `run_pipeline.py` 不删除**是明智的，为回滚留了后路。
- **`decisions.jsonl` 审计日志**是个好想法，为未来的 Dream Loop 和调试提供了可追溯性。
- **Pydantic 契约层保留做格式校验**（不做质量判断），边界划得清楚。
- **Watcher V3 已经是 AI Native**，说明团队有实践经验，新方案可以借鉴 Watcher V3 的可靠性设计（如 `max_runs` 超时、`circuit_breaker_threshold` 熔断）。

---

## 总结

方案的方向是对的（LLM 控制流 + Python I/O），但**可靠性工程严重不足**。当前 V4 的可靠性不是"多余的复杂度"，而是从多次生产事故中积累的防护。AI Native 改造不能把这些防护当作"硬编码"一删了之，必须用**等价或更强的机制**替代。

核心建议：**在 `io_helper.py` 中增加"护栏命令"（guard commands）**——retry-limit check、budget check、state validation、resume context。这些命令是 Python 代码（确定性），Orchestrator 在关键决策点**必须调用**（在 prompt 中强制）。这样既保持了 LLM 做控制流的灵活性，又有代码级的安全保障。

> **"LLM 做决策，代码做护栏。没有护栏的 LLM 控制流 = 生产事故。"**
