# 脉冲式调度方案 — 4 专家评审综合裁决

> 2026-07-24 00:10 | 主 Agent 裁决 | 评审稿：pulse-scheduling-proposal.md
> 评审报告：pulse-review-{reliability,ainative,platform,devil}.md

## 总体结论

**4/4 专家认可方案方向，0 个要求推翻。** 收敛意见：落地前必修一组 P0（竞态/重试/超时）。
分专家判定：
- 可靠性（DS4 Pro）：方向正确，4 P0 必修
- AI Native（K2.6）：方向正确，纯度有问题（部分我不采纳，见 R1）
- 平台（Kimi Code）：与平台语义高度匹配，修复后可行
- 魔鬼代言人（Qwen Max）：核心洞察正确，但主张更简路径（我不采纳为主方案，见 R2）

## 采纳（v1 必修，8 项）

| # | 修复 | 来源 | 收敛度 |
|---|---|---|---|
| A1 | batch_progress/_pulse_actions 原子写（temp+rename）+ pulse 单实例文件锁（锁超时 10min 强清+告警） | 可靠性 P0-1 / 平台 P0-1 | 2 专家独立命中 |
| A2 | 重试预算：retry_count≥3 → terminal_failed + 飞书告警；终态定义 all_resolved = done + terminal_failed | 可靠性 P0-3/P1-4 / 魔鬼"无限重试" | 3 专家命中 |
| A3 | 超时矛盾消除：derive 判 failed 的 task 无视 stale dedup 直接重派；统一 30min/90min 两个常数 | 可靠性 P0-4 / 平台 P1 | 2 专家命中 |
| A4 | 孤儿 dispatch 窗口 30-90min → ~10min（2 pulse 周期）；spawn 失败回滚 dispatch 记录 | 可靠性 P0-2/P1-1 | — |
| A5 | MAX_IN_FLIGHT=8 在 pulse() 中真实实现（当前代码没有） | 可靠性 P1-3 | — |
| A6 | 飞书刷屏防护实测：worker announce 发往已死 pulse session 的行为未验证；必要时 --no-deliver + 主动 message | 平台 P0-2 | — |
| A7 | STALLED 报警冷却（last_alert_at 文件，30min 冷却） | 平台 P1-2 | — |
| A8 | 空转成本控制：lightContext + all_done 时快速退出（不烧 LLM tokens） | 平台 P1-1 / 魔鬼 P2 | 2 专家命中 |

## 部分采纳（2 项）

- **B1**（AI Native P0-2：phase→action 应全在 Python）：**设计本已如此**——drive_all 是 Python，LLM 只做 exec→读 JSON→spawn→汇报。spawn 必须由 Agent 执行（Zone 3.0 铁律）。→ 文档澄清，不改代码。
- **B2**（魔鬼 P0-3：DONE 契约过严）：不放宽契约（契约铁律），但增加 PACKAGING_STUCK 检测（validation_result 存在但 manifest 迟迟不出 → 告警）。

## 不采纳（3 项，附理由）

- **R1**（AI Native P0-1：derive_phase 的 if-else 规则链应交 LLM 判断）→ **拒绝**。"哪个 artifact 存在决定 phase"是文件存在性优先级链，与 Pydantic schema 同类——确定性契约，正是代码该做的（能力正交）。交给 LLM = 增加成本+不确定性，零语义收益。这是"凡 if-else 皆规则引擎"的洁癖。
- **R2**（魔鬼 P0-1：主 Agent 串行直驱替代脉冲，删 777 行 orchestrator）→ **拒绝为主方案**。违反用户核心目标"无人值守自动跑完"：主 Agent 自身也不是可靠常驻进程（我会被压缩、会死、要服务用户）。脉冲的价值恰恰是"驱动者不依赖任何单点 session"。记录为 fallback：若脉冲模式实测仍不稳，再降级到此方案。
- **R3**（魔鬼 P1：删 batch_progress，纯文件系统去重）→ **拒绝**。worker 目录在 spawn params 生成时即创建（driver 行为），文件系统无法区分"已生成未 spawn"与"已 spawn 运行中"，时间戳记录是必要补钉。原子化即可，不删。

## TODO（不阻塞 v1，记入 backlog）

- T1：超时阈值下沉到 task 级（execution_plan 加 expected_duration_seconds）
- T2：phase 规则外化为 YAML 契约（等第二个域出现时再做，YAGNI）
- T3：全局 agents.defaults.subagents.runTimeoutSeconds 与 stale 超时对齐
- T4：worker heartbeat 文件机制（替代纯超时判死，降低误判）

## v1 落地清单（在原方案基础上合入 A1-A8）

1. `orchestrator.py`：pulse() 方法（单次 get_next_actions 全量扫描，非 drive_all 循环）+ 原子写 + 文件锁 + 重试预算 + 超时对齐 + MAX_IN_FLIGHT + 孤儿窗口 10min + spawn 回滚
2. `prompts/deliver_pulse.md`：~40 行（exec → 读 JSON → spawn → 一行汇报；禁止 yield/等待/NO_REPLY；announce 纪律）
3. cron：agentTurn + isolated + lightContext，每 5 分钟，STALLED 冷却 30min
4. 测试：原子写/锁/重试预算/超时对齐/并发上限/孤儿回滚（+~8 个）
5. 实测 A6（announce 行为）→ 决定 --no-deliver
6. 删除：watchdog cron（功能并入 pulse）、orchestrator 手册调度部分加废弃声明

## 关键分歧点记录（给未来参考）

魔鬼代言人的最有价值质疑不是"串行直驱"，而是：**"脉冲只解决发现，不解决防止 agent 死亡"**。裁决：agent 静默死亡是平台属性（空回合/429/事件丢失），无法被我们的代码"防止"，只能"容忍"（检测+重试+预算+告警）。这正是脉冲的设计目标，串行直驱同样无法防止 worker 死亡，只是把"发现者"换成了我——而我不可靠常驻。
