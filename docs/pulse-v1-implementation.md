# Pulse V1 落地记录（版本固化）

> 2026-07-24 | 状态：已固化（生产验证通过）
> 前置文档：pulse-scheduling-proposal.md（方案）→ pulse-review-{reliability,ainative,platform,devil}.md（4 专家评审）→ pulse-review-synthesis.md（裁决 A1-A8）

---

## 1. 版本定义

**Pulse V1 = Deliver Pro 的脉冲式调度架构**，替代 V2 薄层 LLM Orchestrator 的 yield 循环调度模式。

核心形态：cron 每 5 分钟点火一个全新 isolated session → exec 跑 `DeliverOrchestrator.pulse()`（单次全量扫描，决策全部在 Python 完成）→ 动作落盘 `_pulse_actions.json`（Pydantic 契约验证）→ pulse agent 逐条 spawn + confirm 回执 → session 结束。不依赖任何 session 长寿、不依赖事件投递，文件系统是唯一真相。

## 2. A1-A8 裁决落地对照

| 裁决 | 实现 | 位置 |
|---|---|---|
| A1 原子写+文件锁 | `tempfile+os.replace` 全落盘；`fcntl.flock` 非阻塞；锁持有 >10min → LOCK_STALE 告警 | orchestrator.py `_atomic_write_json` / `_acquire_pulse_lock` |
| A2 重试预算 | task 级 attempts ≥3 → 合成 MANIFEST FAILED 终态；WP 级 action_retries >3 → terminal_failed；终态 all_resolved = done + terminal_failed | `_prepare_worker_retries` / tick stale-clear |
| A3 超时矛盾消除 | derive 判 timed_out → 独立重试路径无视 stale dedup 直接重派 + touch 目录；确认 dispatch 保持 30/90min 两常数 | `_prepare_worker_retries` |
| A4 孤儿窗口 10min | 两阶段 dispatch（未确认 10min / 已确认 30-90min）+ `_orphan_sweep()` 清空目录 + `confirm_dispatches` spawn 失败回滚 | `_is_stale_dispatch` / `_orphan_sweep` / `confirm_dispatches` |
| A5 MAX_IN_FLIGHT=8 | 预算在 tick 记录 dispatch **之前**注入；被截 task 删空目录下轮立即可重派；另有 MAX_SPAWN_PER_PULSE=5（对齐平台 maxChildrenPerAgent 默认值） | `tick(max_spawn_budget=)` / `_count_in_flight` |
| A6 刷屏防护 | cron `--no-deliver`；pulse agent 只在 WARN/CRITICAL/完成时发一条合并飞书；worker prompt 加最终输出纪律 | deliver_pulse.md / deliver_worker_base.md |
| A7 STALLED 冷却 | `_pulse_state.json` 零进展计数（≥3 告警）+ 30min 冷却 | `_update_pulse_state` |
| A8 空转成本 | cron `--light-context` + 完成标记快速通道 + completed 后 agent 自删 cron（已实测成功） | pulse() 快速通道 / deliver_pulse.md Step 5 |

**契约笼子**：`contracts/pulse_report.py` — PulseAction/PulseAlert/PulseSummary/PulseReport/SpawnConfirmation 五模型，`extra="forbid"`，写入必须过 model_validate，回执必须过 SpawnConfirmation 验证。

## 3. 生产验证（2026-07-24，全链路可观测性平台_E2E，26 WP）

| 指标 | 数值 |
|---|---|
| 启动时状态 | 7 DONE / 19 卡死（昨天 5 orchestrator 全灭） |
| 最终结果（~5.5h） | **26/26 DONE，0 terminal_failed，0 人工干预** |
| 测试 | **240/240 passed**（新增 17 个 pulse 测试） |
| cron 自删 | ✅ 成功（P2-6 平台未证实项，现验证通过） |
| spawn 失败自动回滚 | 4 次（疑似 429），全部自愈 |
| worker 超时自动重派 | AI-002 T-001 等，重试后产出真实内容 |

**调度层目标（"26 个 WP 无人值守跑完"）：达成。**

## 4. 已知问题（随版本固化记录，不阻塞）

| # | 问题 | 严重度 | 说明 |
|---|---|---|---|
| K1 | 交付质量与调度完成度分离 | 认知 | 26/26 DONE ≠ 质量合格：5 COMPLETE / 8 PARTIAL / 13 FAILED。根因是前日 worker 批量死亡的历史遗留（blocked 级联 → 空 assembly → FAIL 交付）。Pulse 设计目标是"跑完"，质量修复需重置重跑（用户已决定暂缓） |
| K2 | package agent 输出污染 | P2 | SDK-001：package agent 把 284MB 原始 worker_outputs 灌进 final_deliverable（23,610 文件）。deliver_package.md 需加"禁止复制 worker_outputs"约束 |
| K3 | package agent 写空 DELIVERABLE.md | P2 | STORE-003：final DELIVERABLE.md = 0B（draft 有 23KB）。verify_package_output 只查 manifest 未查交付物内容长度，建议加 ≥50 字符下限（对齐 worker 的 MIN_DELIVERABLE_LENGTH） |
| K4 | in_flight 计数保守高估 | P3 | 计数含 30min 窗口内"新鲜但已结束"的目录，瞬时可达 11 > MAX_IN_FLIGHT=8。方向保守（高估→少派活），不影响安全 |
| K5 | blocked 级联 → 空 assembly | 设计权衡 | 基础任务终败时，依赖它的任务全部 blocked → resolved=total → assembly 拼空内容 → FAIL 交付。这是"跑完优先"的设计选择，质量场景需人工重置 |
| K6 | IN_FLIGHT_CAP 曾误标 WARN | 已修 | 首轮刷屏 15 条。已降级 INFO（飞书只发 WARN/CRITICAL） |

## 5. 文件清单

**新增**：
- `domains/deliver_pro/contracts/pulse_report.py`（契约笼子，5 模型）
- `domains/deliver_pro/pulse_cli.py`（exec 入口：pulse/confirm/check）
- `domains/deliver_pro/prompts/deliver_pulse.md`（pulse agent 说明书，~45 行）
- `domains/deliver_pro/tests/test_pulse.py`（17 测试）

**修改**：
- `domains/deliver_pro/orchestrator.py`（+~430 行：pulse/lock/retry/orphan/budget/confirm/stalled）
- `domains/deliver_pro/wp_runner.py`（spawn params 增加 task_id 字段）
- `domains/deliver_pro/contracts/__init__.py`（导出 pulse 模型）
- `domains/deliver_pro/prompts/deliver_orchestrator.md`（废弃声明：yield 循环模式退役，仅供单 WP 手动调试）
- `domains/deliver_pro/prompts/deliver_worker_base.md`（最终输出纪律）

**运行时产物**（blackboard/{project}/）：
- `_pulse_actions.json`（每 pulse 重写，PulseReport 契约）
- `_pulse_state.json`（零进展计数 + 告警冷却）
- `_pulse.lock`（单实例锁）
- `.deliver_completed.json`（终态标记）
- `batch_progress.json`（dispatch 记录 + task_attempts 账本 + _meta.version=1）

## 6. 调度架构演进

```
V2（已废弃）: Main Agent → spawn Orchestrator Agent → drive_all 循环 yield 等待
              → run-mode session「yield 时无 pending children = 自杀」→ 5 连死

V1（当前）:   cron 5min → isolated pulse session → pulse() 单次扫描 → spawn → 结束
              → 无长寿依赖、无事件依赖、文件系统唯一真相
```

---

*固化时间：2026-07-24 21:06+ | 固化人：小满（主 Agent）| 用户裁决：跑完优先，质量修复暂缓*
