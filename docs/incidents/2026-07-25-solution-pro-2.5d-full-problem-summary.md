# Solution Pro 2.5D 项目实战问题全量总结（2026-07-25）

> 首次用 Pulse V3.2 + one-step V3.3 架构正式跑通完整流水线（planning → research → summary → validate → review → finalize）。
> 最终状态：✅ completed（11:50），quality_notes 双 CONDITIONAL。
> 本文档汇总全天暴露的 21 个问题，按层分类，标注修复状态。

---

## A. 平台层问题（OpenClaw 平台，未修复，需上报）

| # | 问题 | 证据 | 影响 |
|---|------|------|------|
| A1 | **depth-1 run-mode session 在 sessions_yield 后 ~200ms 被终止** | 07-18 平台更新后 5/5 复现（07-20×3、07-24×2 orchestrator 全部 yield 即死，trajectory `session.ended` status=success） | 长驻 orchestrator 架构整体不可用 |
| A2 | **完成事件重复投递**（同一 Worker 完成事件 2-15 秒内到达两次） | 4 次实证（03:17/07:46/09:15/09:41，session 日志 thinking 明确记录 "duplicate completion event"） | 诱发 NO_REPLY 连锁死亡 |
| A3 | **run-mode 语义：turn 结束 + 无 pending children = session 自动关闭** | 4 个模块实例死于 NO_REPLY 后 session 关闭 | 模块在步骤边界批量死亡 |
| A4 | **完成通告延迟 75 分钟** | orchestrator 03:12:40 死亡，main session 04:28 才收到通告 | 故障发现严重滞后 |
| A5 | **summary_worker_refiner 被 externalAbort**（非超时非自杀，平台外部中止） | trajectory: `session.ended: status=error, externalAbort=true`；当时正在写超大文档 | 新型死亡模式，疑似平台资源管控 |

## B. 架构层问题（已修复）

| # | 问题 | 修复 |
|---|------|------|
| B1 | V3.1 长驻 yield orchestrator 架构不可用 | → **Pulse V3.2**：cron 点火 + 确定性状态机 + 契约笼子（contracts/pulse_report.py） |
| B2 | depth-2 模块长驻事件驱动同样脆弱（4 实例死 4 次） | → **one-step 执行器 V3.3**：模块每次生命只做一件事，状态全在文件，pulse 4 分钟冷却重召唤 |
| B3 | **双 summarizer 竞态**：先 spawn 后写 in-flight 标记，两个模块实例同窗口重复 spawn | → 契约改为**预约-履约模式**（先写标记再 spawn） |
| B4 | pulse 自写 prompt 文件刷新 stages mtime → stall 检测被自己骗过 | → mtime 计算排除 pulse 自写文件清单 |
| B5 | end-of-loop 重置 last_progress_at → 30min 无进展规则永远触发不了 | → last_progress_at 仅由 mtime 检测和相位推进更新 |

## C. Prompt/契约层问题（行为偏离实证）

| # | 问题 | 性质 |
|---|------|------|
| C1 | **生存铁律概率性失效**（1胜2负）：prompt 禁令 vs 平台 spawn note 指令冲突时，LLM 服从平台 | 证明 prompt 约束是概率性约束，不是契约 → 必须配合架构消除决策点 |
| C2 | `base_synthesis` 只有 68 字符指针，2.4 万字正文写到 `base_solution` | worker prompt 输出契约未钉死 |
| C3 | `research_plan` 是 markdown 字符串而非结构化 JSON，下游被迫 regex 解析 | planner prompt 输出格式规范缺失 |
| C4 | CoWoS-S/L 斜杠写出嵌套目录（`expert_plans/CoWoS-S/L...`） | 无文件名 sanitize 规则（已修） |
| C5 | expert 产出写两个位置（`research_experts/` 和 stages/ 根目录） | 输出路径规范歧义 |
| C6 | planning checkpoint 停在 step1（step2 完成时未持久化） | checkpoint 即时性不足 |
| C7 | stage 名漂移：`planning_plan` vs `planning_tasks` | 契约不一致 |

## D. 代码缺陷（修复过程中引入的回归）

| # | 问题 | 教训 |
|---|------|------|
| D1 | **DryRun 修复引入新 bug**：`_run_post_validation` 用 `session_dir.parent` 当 blackboard 根，但 session_id 含 `/`（CoWoS-S/L）时 parent 只退一级 → 验证器读空目录 → 误判 POST_VALIDATION_FAILED → cron 按设计自删 → 系统假死 | ① 路径计算必须显式存储根，不能用相对推导 ② 修复本身需要回归测试（已加 slash session_id 测试）③ cron 自删后无外部看门狗 |

## E. 质量问题（L2 审查发现，交付物级）

| # | 问题 | 来源 |
|---|------|------|
| E1 | **solution_document 第 7-14 节重复出现两次**（~30% 冗余）——精炼版与基础版被拼接而非合并，追溯矩阵交叉引用矛盾 | 对抗审查 Agent（同时暴露 Summarizer prompt 未明确"合并去重"） |
| E2 | UC-036（Foundry 产能策略）Research 标 PARTIAL，Summary 直接标 COVERED 无缺口填补追溯 | 一致性检查 Agent |

## F. MD/JSON 架构偏离（本次新发现，见专项分析）

| # | 问题 | 详情 |
|---|------|------|
| F1 | **ADR-009 规定 MD 是 source of truth，实际产出全是 JSON** | `solution_document.json` = JSON 包裹的 62K markdown 字符串；无 final_solution.md；track 未生成 |
| F2 | `write_stage()` 只写 .json（Dict 类型签名），无 MD sidecar 通道 | 基础设施缺口 |
| F3 | `render_final_solution_md()` 存在但**未被任何地方调用** | MD 渲染层是死代码 |
| F4 | `summary_json_extractor.md` 错误声称"完整方案由 frozen_spec.md 承载"——frozen_spec 是**输入**不是输出 | prompt 级事实错误 |

---

## 根因模式提炼（21 个问题 → 5 个模式）

1. **平台事件机制不可信**（A1-A5）→ 架构必须不依赖事件/yield/session 长寿，文件系统是唯一真相
2. **Prompt 约束是概率性的**（C1-C7）→ 关键路径必须有代码级契约笼子，prompt 只做语义工作
3. **修复会引入回归**（B4/B5/D1）→ 每个修复必须带回归测试，DryRun 必须覆盖修复本身
4. **约定与实现漂移**（F1-F4/E1）→ ADR 写了 ≠ 实现了；死代码（render_final_solution_md）给人类虚假的安全感
5. **LLM 行为偏离多源于规范缺失**（C2-C5/E1）→ 输出契约（路径/格式/合并语义）必须钉死，不能靠 LLM 自由发挥
