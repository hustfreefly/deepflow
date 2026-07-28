# Deliver Pro 稳健性与自主完成能力分析

> 分析日期：2026-07-28
> 分析范围：orchestrator.py (1458L), wp_runner.py (1656L), failure_recovery.py (191L), pulse_cli.py (115L)
> 对标：Solution Pro post_validator.py (282L)

---

## 1. 失败模式清单

| # | 失败类型 | 发生概率 | 影响范围 | 当前恢复机制 | 评估 |
|---|---------|---------|---------|-------------|------|
| F1 | **Agent spawn 429 限流** | 高（并发 8+ Worker 时） | 全局阻塞 | MAX_IN_FLIGHT=8 硬上限 + MAX_SPAWN_PER_PULSE=5 软上限 | ✅ 充分。两阶段限流（全局+单次）有效防风暴 |
| F2 | **Agent spawn 超时/context 截断** | 中（大任务 90min+） | 单个 WP 阻塞 | _is_stale_dispatch 超时检测 + 孤儿清扫 | ⚠️ 部分。30/90min 超时窗口合理，但恢复依赖下一 pulse 周期（5min 延迟） |
| F3 | **Worker 产出质量不达标** | 高（LLM 固有） | 单 task 级联 blocked | RETRY_BUDGET=3 + 合成 MANIFEST FAILED + 级联 blocked | ✅ 充分。3 次重试 + 终态标记防止无限重试 |
| F4 | **状态机卡死（phase 转换失败）** | 低 | 单 WP 永久停摆 | phase_derive 文件系统推导 + B2 phase alias 修复 | ✅ 充分。V3 架构"derive don't sync"消除了状态不一致根因 |
| F5 | **Blackboard 文件丢失/损坏** | 低（磁盘故障） | 单 WP 回退 | 原子写（temp+os.replace）+ corrupted state backup | ⚠️ 部分。原子写防截断，但无备份恢复机制（corrupted 文件只 rename，不自动重建） |
| F6 | **依赖图循环** | 极低（Ship Pro 保证 DAG） | 分层执行死锁 | _topo_layers 检测循环 → 强制 break 一个节点 | ⚠️ 粗暴。break 后该 WP 可能依赖未完成的前置，但无告警 |
| F7 | **Pulse 锁竞争** | 低（单 cron 实例） | 单次 pulse 跳过 | fcntl.flock 非阻塞 + stale lock 告警（10min） | ✅ 充分。flock 进程死亡自动释放，无 stale lock 残留 |
| F8 | **Validate agent 死亡/未分发** | 中 | Layer 0 不 DONE → 后续所有 layer 锁死 | 孤儿 validate 恢复（重新分发） | ✅ 充分。2026-07-23 事故后修复，覆盖未分发和已分发两种场景 |
| F9 | **Assembly 零产出** | 低（Worker 全失败时） | WP 浪费 validate/package 两轮 LLM | K5-B: ASSEMBLY_EMPTY → terminal_failed | ✅ 充分。快速失败，不烧后续 LLM 预算 |
| F10 | **Ship package 缺失** | 低（上游故障） | 整个项目无法启动 | _find_ship_package 多路径搜索 + B1 空 package fallback | ⚠️ 部分。空 package fallback 导致后续所有 WP 为空，不如直接报错 |

---

## 2. 恢复机制评估

### 2.1 Pulse 调度（orchestrator.py pulse()）

**设计成熟度：⭐⭐⭐⭐ (4/5)**

| 机制 | 实现 | 评价 |
|------|------|------|
| MAX_IN_FLIGHT | 全局在途 agent 硬上限 8 | ✅ 防 429 风暴，值合理 |
| MAX_SPAWN_PER_PULSE | 单次 pulse spawn 上限 5 | ✅ 对齐平台 maxChildrenPerAgent |
| ORPHAN_DISPATCH_WINDOW | 未确认 dispatch 10min 过期 | ✅ 2 个 pulse 周期，平衡误杀和恢复速度 |
| RETRY_BUDGET | task/WP 级重试上限 3 | ✅ 防止无限重试烧 token |
| Stale dispatch 分类超时 | analyze 30min / spawn_workers 90min / validate 30min / package 30min | ✅ 按任务复杂度差异化 |
| 两阶段 dispatch | dispatch_confirmed=False → confirm 后 True | ✅ 精确区分"已记录"和"已运行" |
| 孤儿清扫 (_orphan_sweep) | 未确认 spawn_workers 过期 → 清记录 + 删空目录 | ✅ 解决"目录已建但 agent 未跑"的死锁 |
| 零进展检测 (A7) | 连续 3 次零进展 → STALLED 告警，30min 冷却 | ✅ 防流水线静默卡死 |
| 预算截断 (A5) | in_flight 超限时截断 spawn list + 删空目录 | ✅ 被截断的 task 下次 pulse 立即可重派 |
| 完成快速通道 (A8) | .deliver_completed.json 存在 → 零扫描退出 | ✅ 终态后零资源消耗 |

**差距**：
- ❌ 无 pulse 级联恢复：pulse 进程被 kill → 无自动重启（依赖 cron 下次触发）
- ❌ 无跨项目资源隔离：多个项目共享 MAX_IN_FLIGHT=8，大项目可能饿死小项目

### 2.2 failure_recovery.py

**设计成熟度：⭐⭐⭐ (3/5)**

| 机制 | 实现 | 评价 |
|------|------|------|
| AI Native 诊断 | LLM 端到端诊断，不预定义故障类型 | ✅ 灵活，适应未知故障模式 |
| 轮次计数器 | attempts < max_attempts（唯一代码逻辑） | ✅ 简洁，符合 AI Native 原则 |
| 策略历史 | recovery_history 记录每轮 action/result | ✅ 防 LLM 重复推荐失败策略 |
| 启发式降级 | retry → add_context → simplify → split_wp → skip | ⚠️ 仅辅助，实际决策由 LLM 做出 |

**差距**：
- ❌ **未被 orchestrator 实际调用**：`WorkerFailureRecovery` 类在 wp_runner.py 中 import 了，但 `prepare_diagnosis_spawn` 方法在 pulse 模式下从未被调用。Pulse 调度走的是 `_prepare_worker_retries`（直接重派），不经过 LLM 诊断。
- ❌ **无跨 WP 故障关联**：同一类型 task 在多个 WP 失败时，无全局模式识别
- ❌ **无故障知识库**：每次诊断从零开始，不积累历史经验

### 2.3 原子写与锁机制

**设计成熟度：⭐⭐⭐⭐⭐ (5/5)**

| 机制 | 实现 | 评价 |
|------|------|------|
| 原子写 JSON | temp file + os.replace（orchestrator + wp_runner 各一份） | ✅ 防并发截断 |
| fsync | wp_runner 版有 os.fsync，orchestrator 版无 | ⚠️ 微小不一致，但 macOS APFS _journal 兜底 |
| Pulse 锁 | fcntl.flock 非阻塞 + PID 写入 + mtime 作为持有起始 | ✅ 进程死亡自动释放，无 stale lock |
| Corrupted state backup | state 加载失败 → rename 为 .corrupted | ✅ 保留现场供人工分析 |
| Phase alias 修复 | ASSEMBLING/ASSEMBLE → INTEGRATING 自动映射 | ✅ 历史兼容，防 phase 枚举扩展导致的回退失败 |

---

## 3. 自主完成能力评分

| 环节 | 自主性 | 瓶颈 | 改进建议 |
|------|-------|------|---------|
| **Phase 1: Analyze** | 🟢 高（90%） | plan 损坏后需重新 analyze，消耗 1 轮 pulse | 增加 plan 缓存（analyze 结果校验失败时 fallback 到上次有效 plan） |
| **Phase 2: Workers** | 🟢 高（85%） | 超时 task 需等 30/90min stale 窗口 | 增加 heartbeat 机制（worker 定期 touch 文件 → 缩短超时判定） |
| **Phase 3: Assembly** | 🟢 极高（99%） | 纯确定性代码，零 LLM 依赖 | 已是最优 |
| **Phase 4: Validate** | 🟡 中（70%） | Validate agent 死亡 → 需等孤儿检测 + 重分发（5-10min 延迟） | 增加 validate 结果 heartbeat；或双 validate agent 冗余 |
| **Phase 5: Package** | 🟢 高（85%） | Package agent 失败 → terminal_failed（无重试） | Package 失败应区分"可重试"（超时）和"不可重试"（零产出） |
| **依赖图执行** | 🟢 高（90%） | Layer 间串行，Layer 内并行 | 已是最优（依赖关系决定） |
| **故障恢复** | 🟡 中（60%） | failure_recovery.py 未被 pulse 模式调用；LLM 诊断路径未接入 | 将 LLM 诊断接入 pulse 重试路径（第 2 次重试时触发诊断） |
| **终态判定** | 🟢 高（95%） | all_resolved = done + terminal_failed | 已是最优 |

**综合自主性评分：82%** — 大部分场景可无人值守完成，主要瓶颈在 validate 孤儿恢复延迟和故障诊断路径未接入。

### 3.1 必须人工介入的环节

| 环节 | 触发条件 | 介入方式 |
|------|---------|---------|
| Ship package 缺失 | 上游 Ship Pro 未产出 | 人工触发 Ship Pro 或手动创建 ship_package.json |
| STALLED 告警 | 连续 3 次 pulse 零进展 | 人工检查是否有隐性阻塞（网络、模型配额） |
| LOCK_STALE 告警 | Pulse 锁持有超 10min | 人工 kill holder 进程或删除锁文件 |
| 循环依赖 | dependency_graph 有环 | 人工修正 ship_package.json 的依赖关系 |
| 全部 WP terminal_failed | 所有 WP 重试预算耗尽 | 人工分析失败模式，调整 WP 定义或模型配置 |

### 3.2 无需人工介入的自动恢复

| 场景 | 自动恢复机制 | 恢复时间 |
|------|------------|---------|
| Worker 超时 | _prepare_worker_retries 重派（最多 3 次） | 下一 pulse（5min） |
| Validate agent 死亡 | 孤儿 validate 检测 + 重新分发 | 5-10min |
| Spawn 429 | MAX_IN_FLIGHT 限流 + 下 pulse 重试 | 5min |
| Plan 损坏 | 删除坏 plan + 清除 dispatch 记录 + 重新 analyze | 5-10min |
| 空 task 目录（孤儿） | _orphan_sweep 清理 | 下一 pulse（5min） |
| 原子写中断 | temp 文件清理 + 原文件不变 | 透明恢复 |

---

## 4. 对标 Solution Pro

| 稳健性维度 | Solution Pro | Deliver Pro | 差距 |
|-----------|-------------|-------------|------|
| **状态管理** | BlackboardManager 内存+文件双写 | 文件系统即真相（V3 derive） | Deliver Pro 更稳健（无状态不一致风险） |
| **质量验证** | post_validator 三层检查（Schema + Coverage + Conservation） | validate agent LLM 评分 + 代码门禁交叉验证 | Solution Pro 更结构化；Deliver Pro 更灵活（LLM 语义判断） |
| **信息守恒** | semantic_anchors 保留率检查（V4 quality_utils） | N6 锚点检查（仅 warning，不 auto-fail） | ⚠️ Deliver Pro 弱于 Solution Pro（锚点丢失不阻断） |
| **需求覆盖** | requirement_index 覆盖率（双层阈值 50%/80%） | AC 覆盖率 < 80% → auto FAIL | 基本对等，Deliver Pro 更严格（硬门禁） |
| **故障恢复** | 无专门故障恢复模块（Agent 层重试） | failure_recovery.py + pulse 重试预算 | Deliver Pro 更完善（有独立恢复模块） |
| **并发控制** | 无（单 Agent 串行） | MAX_IN_FLIGHT + 两阶段 dispatch + 孤儿清扫 | Deliver Pro 远超 Solution Pro（多 Agent 并发必需） |
| **原子写** | BlackboardManager 内置 | 独立实现（orchestrator + wp_runner 各一份） | 基本对等，但 Deliver Pro 有代码重复 |
| **Pydantic 验证** | FinalSolutionSchema 完整验证（Cage 验证器） | ExecutionPlan / ValidationVerdict / WorkerOutputMeta 验证 | 基本对等 |
| **可观测性** | 无专门告警机制 | PulseReport + STALLED/LOCK_STALE/CRITICAL 告警 | Deliver Pro 远超 Solution Pro |
| **终态管理** | 无（Agent 完成即结束） | .deliver_completed.json + terminal_failed 终态判定 | Deliver Pro 更完善 |
| **通用工具复用** | V4 重构调用 core.quality_utils | 独立实现（未复用 quality_utils） | ⚠️ Deliver Pro 有重复实现 |

### 4.1 Solution Pro 有但 Deliver Pro 缺失的稳健性设计

| 设计 | Solution Pro 实现 | Deliver Pro 缺失影响 | 优先级 |
|------|-----------------|-------------------|------|
| **信息守恒硬门禁** | 锚点丢失率 > 50% → critical failure | Deliver Pro 仅 warning，可能交付丢失核心锚点的文档 | P1 |
| **后置验证持久化** | bb.write_stage('l0_validation_result', result) | Deliver Pro 验证结果不持久化，无法审计 | P2 |
| **通用质量工具复用** | core.quality_utils 统一阈值和逻辑 | Deliver Pro 独立实现，阈值可能不一致 | P2 |

### 4.2 Deliver Pro 有但 Solution Pro 缺失的设计（过度设计评估）

| 设计 | 是否过度 | 评价 |
|------|---------|------|
| 两阶段 dispatch（dispatch_confirmed） | ❌ 不过度 | 精确区分"已记录"和"已运行"，解决孤儿问题 |
| 零进展检测（A7） | ❌ 不过度 | 防流水线静默卡死，生产必需 |
| 按 action 类型差异化超时 | ❌ 不过度 | spawn_workers 90min vs analyze 30min 合理 |
| failure_recovery.py 完整模块 | ⚠️ 部分过度 | 类设计完善但 pulse 模式未调用，属于"准备了但未接入" |
| LLM 诊断 prompt（prepare_diagnosis_spawn） | ⚠️ 部分过度 | 在 pulse 模式下从未使用，drive_once 模式也未调用 |

---

## 5. 重构优先级

### P0（必须 — 影响自主完成能力）

| # | 改进项 | 预期收益 | 实现复杂度 |
|---|--------|---------|-----------|
| P0-1 | **接入 failure_recovery 到 pulse 重试路径**：第 2 次 task 重试时触发 LLM 诊断，根据诊断结果调整 prompt 而非原样重派 | 重试成功率从 ~30% 提升到 ~60%（LLM 诊断可识别根因） | 中（需在 _prepare_worker_retries 中增加诊断分支） |
| P0-2 | **信息守恒硬门禁**：semantic_anchors 丢失率 > 50% → validate auto FAIL（对齐 Solution Pro） | 防止交付丢失核心决策依据的文档 | 低（在 verify_validate_output 中改 warning 为 fail） |

### P1（重要 — 提升稳健性）

| # | 改进项 | 预期收益 | 实现复杂度 |
|---|--------|---------|-----------|
| P1-1 | **Worker heartbeat 机制**：Worker 执行中定期 touch task_dir/.heartbeat → stale 判定改为 heartbeat 超时（而非 spawn 时间） | 大任务（90min）的超时判定从"盲等"变为"活性检测"，减少误杀 | 中（需 Worker prompt 加入 heartbeat 指令 + phase_deriver 读取 heartbeat） |
| P1-2 | **Package 失败分级**：区分"可重试"（超时/429）和"不可重试"（零产出），可重试时允许重新分发 | 减少因临时错误导致的 terminal_failed | 低 |
| P1-3 | **复用 core.quality_utils**：Deliver Pro 的验证逻辑调用通用函数，统一阈值 | 消除重复实现，确保阈值一致性 | 低 |
| P1-4 | **循环依赖告警**：_topo_layers 强制 break 时输出 CRITICAL 告警（当前仅 warning） | 提高依赖图问题的可观测性 | 低 |

### P2（可选 — 锦上添花）

| # | 改进项 | 预期收益 | 实现复杂度 |
|---|--------|---------|-----------|
| P2-1 | **验证结果持久化**：validate 结果写入 blackboard stage（对齐 Solution Pro 的 l0_validation_result） | 支持审计和事后分析 | 低 |
| P2-2 | **跨项目资源隔离**：MAX_IN_FLIGHT 按项目分配（如按 WP 数量加权） | 防止大项目饿死小项目 | 中 |
| P2-3 | **故障知识库**：LLM 诊断结果写入 blackboard（failure_knowledge.json），后续诊断时注入历史经验 | 诊断质量随使用提升 | 中 |
| P2-4 | **Ship package 缺失时直接报错**：移除 B1 空 package fallback，改为 raise FileNotFoundError | 避免空跑 | 低 |
| P2-5 | **原子写统一**：orchestrator 和 wp_runner 共用同一个 atomic_write_json（消除代码重复） | 减少维护成本 | 低 |

---

## 6. 总结

### 稳健性总评：⭐⭐⭐⭐ (4/5)

Deliver Pro 的稳健性设计在 **多 Agent 并发调度** 领域达到生产级水平：
- ✅ Pulse 调度 V1（A1-A8）覆盖了并发控制、孤儿恢复、零进展检测等核心场景
- ✅ 文件系统即真相（V3 derive）消除了状态不一致的根因
- ✅ 原子写 + 文件锁防止并发截断
- ✅ 差异化超时 + 重试预算平衡了恢复速度和资源消耗

### 主要差距

1. **failure_recovery.py 未接入**（P0-1）：这是最大的"断头路"——模块设计完善但从未被 pulse 模式调用，导致重试是"盲重派"而非"诊断后重派"
2. **信息守恒软门禁**（P0-2）：semantic_anchors 丢失仅 warning，可能交付质量不达标
3. **无 heartbeat 机制**（P1-1）：大任务超时判定依赖 spawn 时间，可能误杀正常运行的 agent

### 自主完成能力结论

**Deliver Pro 可以在无 Main Agent 干预下完成 80%+ 的正常流程**，前提是：
- Ship package 正确生成
- 模型服务稳定（无持续 429）
- 无循环依赖

主要需要人工介入的场景是 **上游输入缺失** 和 **全局资源耗尽**，这些是架构边界而非设计缺陷。
