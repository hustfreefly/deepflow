# 魔鬼代言人评审：脉冲式调度提案

> 评审人：Devil's Advocate（Pulse Review Devil）| 2026-07-23

---

## P0 问题：前提挑战

### P0-1: 脉冲调度不是最简方案——主 Agent 直驱才是

**挑战**：提案把"长寿 orchestrator 循环"和"cron 脉冲"当作仅有的两个选项，跳过了一个更简单的路径：**主 Agent 直接调 `drive_all()`，一次一个 WP 串行推进**。

**证据**：提案自认"对照组：主 Agent 直接 spawn 的 5 个 package agent：5/5 成功"。这说明主 Agent session 本身就是可靠的执行环境。问题不是"LLM session 不可靠"，而是"orchestrator 层叠加了不可靠的并发调度"。

**替代方案**：
1. 主 Agent 读 ship_package，按 layer 顺序逐个 WP 执行
2. 每个 WP：`driver.step1_analyze()` → spawn → yield → `step2_check` → ... → `step7_package` → 完成 → 下一个 WP
3. 串行：并发=1，零 429 风险，零 dedup 需求，零 batch_progress.json
4. 总代码量：~30 行主 Agent 指令，不需要 pulse()、cron、_pulse_actions.json

**对比**：
| 维度 | 脉冲方案 | 串行直驱 |
|---|---|---|
| 新增组件 | cron job + pulse() + _pulse_actions.json + prompt | 无 |
| 删除组件 | orchestrator 手册 | orchestrator.py 全部 |
| 残留状态文件 | batch_progress.json + _pulse_actions.json | 无 |
| 并发控制 | MAX_IN_FLIGHT=8 + dedup | 不需要（串行） |
| 5 分钟延迟 | 有（pulse 间隔） | 无（完成即下一个） |
| 失败恢复 | stale dispatch + 超时检测 | 主 Agent 直接看到错误，重试或跳过 |
| 代码净删 | ~40 行新增，保留 777 行 orchestrator | 删 777 行 orchestrator |

**结论**：如果目标是"26 个 WP 跑完 + 薄"，串行直驱比脉冲更薄、更可靠、更少新组件。脉冲是用一个新系统（cron + pulse + actions JSON）去替换旧系统（orchestrator + yield），复杂度平移而非消除。

---

### P0-2: 7/26 完成的真正原因不是架构，是 package agent 静默失败

**挑战**：提案说"7 DONE / 9 ASSEMBLING（假性推进）"。但 batch_progress.json 显示：**7 个 WP 卡在 PACKAGING，不是 ASSEMBLING**。它们的 `last_spawned_action = "package"`，说明 package agent 被 spawn 了但没有产出 `delivery_manifest.json` + `final_deliverable/`。

**证据**：
```json
"AI-001": {"phase": "PACKAGING", "last_spawned_action": "package", "last_spawned_at": 1784783524}
"AI-006": {"phase": "PACKAGING", "last_spawned_action": "package", ...}
"INGEST-001": {"phase": "PACKAGING", ...}
"PLAT-001": {"phase": "PACKAGING", ...}
// 共 7 个
```

这意味着：
1. 状态推导正确识别了需要 package
2. spawn 动作被返回了
3. **但 package agent 死了（和 worker agent 一样静默死亡）**
4. 脉冲方案会重新 spawn package agent——但如果 package agent 的死因是 prompt 问题或 provider 429，重新 spawn 只会再死一次

**结论**：脉冲方案假设"重新 spawn 就能恢复"，但今天的证据显示 agent 死亡有系统性原因（429 风暴 / prompt 错误）。脉冲不解决 agent 为什么死，只解决"死了没人发现"。如果 agent 死因未修复，脉冲会无限循环 spawn→死→spawn→死。

**建议**：在实施脉冲之前，先确认：
1. 7 个 PACKAGING 卡住的 WP，package agent 的实际死因是什么？
2. deliver_package.md 修复后，package agent 是否已经能跑通？
3. 如果死因是 429，MAX_IN_FLIGHT=8 是否仍然太高？

---

### P0-3: DONE 契约确实太死板——`final_deliverable` 非空是脆弱门槛

**挑战**：`derive_phase()` 的 DONE 判定：
```python
if manifest_file.exists() and final_dir.exists():
    if any(f.is_file() for f in final_dir.rglob("*")):
        return PHASE_DONE
```

这要求 `stages/final_deliverable/` 目录存在 **且** 内含至少一个文件。如果 package agent：
- 写了 `delivery_manifest.json` 但 `final_deliverable/` 是空目录 → 不是 DONE
- 写了 manifest 和文件但路径写错（今天的路径歧义 bug） → 不是 DONE
- 写了 manifest 但文件在 legacy 位置 → DONE（但有 deprecation warning）

**风险**：DONE 是整个流水线的终态。一个过于严格的 DONE 条件会让 WP 永远卡在 PACKAGING，脉冲会反复尝试 package，形成 retry storm。

**建议**：
1. 增加 `PACKAGING_STUCK` 检测：如果 `validation_result.json` 存在但 `delivery_manifest.json` 迟迟不出现（超过 N 分钟），标记为 PACKAGING_STUCK，触发告警而非无限重试
2. 或者放宽 DONE 条件：`delivery_manifest.json` 存在即可 DONE（manifest 本身就是交付清单，文件可以后补）

---

## P1 问题：残留石膏

### P1-1: batch_progress.json 是保留的石膏——与"文件系统是唯一真相"矛盾

**问题**：提案保留 `batch_progress.json` 作为 "dispatch 去重记录"。但这个文件本质上是 **状态文件**——记录"我上次 spawn 了什么"。它与 `phase_deriver.py` 的 "derive, don't sync" 哲学直接矛盾。

**今天的证据**：batch_progress.json 里存了 `last_spawned_action` 和 `last_spawned_at`，这正是同步状态。pulse 方案不但保留了它，还新增 `_pulse_actions.json`（另一个状态文件）。

**替代方案**：
- 去重可以从文件系统推导：检查 `stages/worker_outputs/{task_id}/` 是否存在 → 如果存在，说明已 spawn
- 或者用更简单的方式：不做去重，靠 `derive_worker_progress` 的 task 级推导（目录存在 = 已 spawn/running/completed）自然幂等

---

### P1-2: MAX_IN_FLIGHT=8 是拍脑袋的数字

**问题**：提案设 MAX_IN_FLIGHT=8 防 429 风暴，但今天高峰并发 15+ 导致 429。8 和 15 之间没有本质安全差异——都取决于 provider 的 rate limit。

**建议**：
- 如果用串行直驱（P0-1），MAX_IN_FLIGHT=1，彻底消除 429
- 如果坚持脉冲，MAX_IN_FLIGHT 应该基于实测的 provider rate limit，而非猜测。先用 3，观察 429 频率，逐步上调

---

### P1-3: stale dispatch 超时阈值是经验主义石膏

**问题**：`_STALE_DISPATCH_TIMEOUTS` 硬编码了 analyze=30min, spawn_workers=90min, validate=30min, package=30min。这些数字来自今天的经验，换一个项目/WP 规模可能完全不适用。

**建议**：超时应该是 WP 属性（从 ship_package 读取预估时间），而非全局常量。或者更简单：用 `worker_outputs/{task}/` 的 mtime 做动态超时（目录越老越可能是孤儿）。

---

## P1-4: 脉冲 vs watchdog 本质相同——同一错误换皮

**挑战**：提案说"watchdog 功能内卷进 pulse"。但 watchdog 的问题是**轮询间隔导致的延迟和盲区**，脉冲完美继承了这两个问题：

| 属性 | Watchdog | Pulse |
|---|---|---|
| 检查间隔 | 5 min | 5 min |
| 最坏延迟 | 5 min | 5 min |
| 间隔内盲区 | 有 | 有 |
| 误报处理 | 需要 | 需要 |
| 实现方式 | cron + isolated session | cron + isolated session |

**本质区别**：watchdog 只看不做，pulse 又看又做。但"做"的部分（spawn agent）正是今天失败的地方。所以 pulse = watchdog + 不可靠的 spawn 自动化。

**建议**：如果接受 P0-1（串行直驱），watchdog 和 pulse 都不需要——主 Agent 实时看到每个 WP 的状态，无需轮询。

---

## P2 问题

### P2-1: 每 5 分钟一个 isolated session 的成本未评估

**问题**：26 个 WP，每个需要 5-7 个 phase，最坏情况 26 × 7 = 182 次 pulse session。每个 session 有 bootstrap 开销（context 加载、prompt 解析）。如果流水线跑 24 小时 = 288 个 pulse session。

**建议**：评估 cron 的实际 token 消耗。如果每次 pulse session 消耗 ~2K tokens（context + tool calls），288 次 = 576K tokens，对比串行直驱可能只需要 1 个 session 跑完全程。

### P2-2: _pulse_actions.json 是新的竞态源

**问题**：pulse 写 `_pulse_actions.json`，然后 LLM 读它来 spawn。如果两个 pulse 重叠（前一个还没写完，后一个开始），或者 LLM 读文件时文件正在被写，会出现竞态。

**建议**：用原子写（写临时文件 + rename），或者——再次建议——串行直驱，完全不需要中间文件。

### P2-3: 提案没有回答"如果只能保留一个组件"

如果只能保留一个：**`phase_deriver.py`**。它的 "derive, don't sync" 理念是整个项目最有价值的部分。`orchestrator.py`（777 行）是累积的石膏，每次 bug fix 加一层逻辑。真正的极简方案是：保留 phase_deriver + driver，删掉 orchestrator，让主 Agent 用 driver 的 step API 直驱。

---

## 总体评估

脉冲方案的核心洞察是对的：**长寿 orchestrator session 不可靠**。但它选择的替代方案（cron 脉冲）引入了等量的新复杂度（新 cron job、新状态文件、新 prompt、并发控制），本质是**复杂度平移而非消除**。

今天的 7/26 完成率的真正瓶颈不是调度模式，而是 **agent 静默死亡**（package/worker agent spawn 后不产出就死了）。脉冲方案能发现死亡，但不能防止死亡。如果 agent 死因未修复（429 风暴、prompt 错误），脉冲会陷入 spawn→死→重 spawn→再死的循环。

**更简单的路径存在**：主 Agent + driver.step API + 串行执行。代码量更少（删 777 行 orchestrator），不需要 cron/脉冲/中间文件，并发=1 自然消除 429 和 dedup 需求，完成延迟更低（无需等 5 分钟间隔）。

---

*评审完成。以上每条挑战均基于提案自身数据和代码实证，不含"感觉可能有问题"。*
