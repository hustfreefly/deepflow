# Deliver Pro 脉冲式调度架构提案（专家评审稿 V1）

> 2026-07-23 | 作者：小满（主 Agent）| 评审目标：找不足，不是找认同

---

## 1. 背景：2026-07-23 真实 E2E 故障证据

项目「全链路可观测性平台_E2E」，26 个 WP。今日全程证据：

| 证据 | 数据 |
|---|---|
| 最终状态 | 7 DONE / 9 ASSEMBLING（假性推进）/ 10 未启动 |
| Orchestrator 死亡 | 5 个，全部同一模式：`sessions_yield()` 时无 pending children → run-mode session 直接终结（最后一条消息 NO_REPLY / 空输出，runtime 8-36s） |
| Worker 死亡 | ~20 个被 spawn，0 个 MANIFEST、0 个产出文件——一行代码没写就死了 |
| 完成事件 | 延迟 45 分钟到达 / 发往已死父 session 丢失 |
| 对照组 | 主 Agent 直接 spawn 的 5 个 package agent：5/5 成功（父是长寿 session、并发低、一次性任务无 yield） |
| 高峰并发 | 15+ agent 同时打同一 provider（疑似 429 加剧死亡） |
| 全天卡死根因之一 | package prompt 路径歧义（`final_deliverable/` 漏 `stages/` 前缀）→ 5 个 agent 全写错位置 → 确定性 DONE 检查永不满足 → 永远 PACKAGING |

## 2. 诊断：四层根因

1. **表层**：Worker 静默死亡，无人发现无人重试
2. **中层**：架构假设"长寿 LLM orchestrator 循环 yield 等待"，但 run-mode session 语义是"yield 时无 pending children = 自杀"
3. **深层**：事件投递不可靠（延迟/丢失），但调度逻辑依赖事件唤醒
4. **根因**：V3 架构改了状态层（derive-don't-sync：文件系统是唯一真相 ✅ 这个改对了），**没改调度层**——把"持续驱动"押在平台不保证的原语（长寿 session）上

另有架构理念层面（用户本人指出）：Deliver Pro 一直干不好，是因为试图设计"完美厚重系统"对抗平台不可靠，补丁摞补丁，厚度自己成了故障源。应该：厚 LLM 语义、薄调度（skill 级）、薄但硬的契约。

## 3. 提案：脉冲式调度（Pulse Scheduling）

### 3.1 核心形态

```
cron 每 5 分钟触发一个全新 isolated session（"脉冲"）：
  1. exec 跑 DeliverOrchestrator.pulse()
     → drive_all()（现有逻辑：derive 状态 → 决定该干什么）
     → spawn 动作落盘 stages/_pulse_actions.json
     → all_done 时写 .deliver_completed.json
  2. 读 _pulse_actions.json，逐条 sessions_spawn（作为本 session 的 children）
  3. 输出一行可见文字汇报，session 结束
```

**关键性质**：
- 不依赖任何 session 长寿（pulse 从不 yield，跑完即结束，死了下次 cron 再来）
- 不依赖事件投递（worker 完成事件丢了无所谓，下次 pulse 从文件系统推导状态）
- worker 静默死亡 → 任务目录超时 → derive 判 failed → 下次 pulse 自动重派（复用今日已落地的 stale-dispatch 恢复机制）
- MAX_IN_FLIGHT=8 并发硬上限（防 429 风暴）
- watchdog 功能内卷进 pulse：连续 N 次 pulse 零进展 → pulse 自己报警

### 3.2 改动清单

| 组件 | 改动 | 规模 |
|---|---|---|
| `orchestrator.py` | 新增 `pulse()` 方法（drive_all 包装 + 动作落盘 + 并发上限 + 完成标记） | +~40 行 |
| `prompts/deliver_pulse.md` | 新建：一次性 tick 说明书（禁止 yield / 禁止等待 / 禁止 NO_REPLY） | ~40 行，替代 800 行 orchestrator 手册 |
| cron 任务 | `agentTurn` + `isolated`，每 5 分钟，announce 到飞书 | 1 个 job |
| `deliver_orchestrator.md` | 顶部加废弃声明，保留仅供单 WP 手动调试 | 标注 |
| 测试 | pulse 落盘格式 / all_done 标记 / 并发上限 | +3 个 |

### 3.3 保留 vs 删除

**保留（骨头，今日全部工作正常）**：
- `phase_deriver.py`：derive_phase / derive_worker_progress / 超时判 failed
- Pydantic 契约（contracts/）、DONE 检查（`stages/final_deliverable` 非空）
- stale-dispatch 恢复（dispatch 时间戳 + 分 action 超时阈值）
- batch_progress.json（dispatch 去重记录，防 pulse 重叠时双派）
- 所有 phase agent（analyze / worker / validate / package）——LLM 语义层不动

**删除（石膏）**：
- orchestrator 的 yield 循环调度模式（今日 5 次实证必死）
- 独立 watchdog cron（功能并入 pulse 自报警）
- orchestrator 厚手册的调度编排部分

### 3.4 明确不做（YAGNI）

- 不重写 phase agent（它们今天是好的）
- 不动 derive 契约层
- 不做跨域抽象（先在 Deliver Pro 验证，模式成立后再谈推广）
- 不做 retry 预算之外的高级重试策略（指数退避等）

## 4. 设计目标与约束

**目标**：
1. 26 个 WP 无人值守跑完
2. 薄调度 + 硬契约（用户明确要求）
3. 高泛化性（无项目特定控制规则）

**平台约束（已知事实）**：
- `sessions_spawn` 是 Agent tool，Python 代码无法调用（Zone 3.0 铁律）
- run-mode session：yield 时无 pending children = 终结；空输出回合 = 终结
- 无 per-call spawn 超时参数（全局配置）
- 子 agent 完成事件可延迟/丢失
- cron `agentTurn` + `isolated` 可用（今日 watchdog 实证）

**设计公理**（用户三公理）：
- 能力正交：LLM 做语义判断，代码做确定性执行
- 信息守恒：状态全在文件系统，不丢
- 契约铁律：不可信的约束不是约束（LLM 自报"完成"不可信，文件证据才算）

## 5. 评审请求

请重点找**不足**，按你的专业视角回答：

1. **失败模式**：这个方案在什么情况下会失败/卡死/失控？越具体越好
2. **残留石膏**：方案里还有哪些过度设计或不必要的东西？
3. **削得太薄**：缺了哪些必要的防护/契约？（如：重试风暴？并发竞态？）
4. **泛化性**：换一个项目/换一个域，这个模式还成立吗？哪里有隐藏的项目耦合？
5. **AI Native 纯度**：有没有代码做语义判断、或 LLM 被迫做确定性工作的地方？

输出要求：问题按 P0/P1/P2 分级，每条 ≤100 字 + 改进建议 ≤150 字。证据优先，不接受"感觉可能有问题"。

---

*相关代码文件（评审时可读）*：
- `.deepflow/domains/deliver_pro/orchestrator.py`（drive_all / stale 恢复）
- `.deepflow/domains/deliver_pro/phase_deriver.py`（derive 契约）
- `.deepflow/domains/deliver_pro/prompts/deliver_orchestrator.md`（被替代的厚手册）
- `.deepflow/domains/deliver_pro/prompts/deliver_package.md`（今日路径事故修复后版本）
