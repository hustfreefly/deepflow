# P2 修复清单（V2 → V3）

> **日期**: 2026-06-25
> **输入**: 4 位专家 V2 评审共 17 个 P2 + 1 个 P3
> **目标**: 全部修复后，请 3 位 **新专家** 进行第三轮评审

---

## 修复汇总

| # | 来源 | 严重度 | 问题 | 修复方案 | V3 章节 |
|---|------|--------|------|---------|---------|
| 1 | 架构师 | P2 | 命令数量不一致（标题 12 vs 实际 16） | 标题改为"16 个命令"，分类：6 I/O + 5 护栏 + 3 恢复 + 2 调试 | §3.1 |
| 2 | 架构师 | P2 | compact-history 实现机制未明确 | 明确为"纯提取 + 结构化 JSON"，不调用 LLM（Orchestrator 自身是 LLM） | §3.5 |
| 3 | 架构师 | P2 | Judge Worker 失败处理未定义 | 增加 Judge fail 分支：`conditional` → 修复后重 Judge；`fail` → 上报主 Agent | §5.1 Phase 4 |
| 4 | 架构师 | P2 | validate-quality 与 gate 函数关系需澄清 | 明确：gate 函数 = 硬约束（依赖无环、覆盖率），LLM 评估 = 软约束（内容质量），互补不冲突 | §3.2 |
| 5 | 架构师 | P2 | build-prompt --context-file 格式未定义 | 定义为 JSON：`{task, context, quality_criteria}`，Orchestrator 写临时文件 | §5.2 |
| 6 | 架构师 | P2 | 并行执行 sessions_yield 语义不明确 | 改为"默认串行；并行阶段数由 can-parallel 命令决定（不硬编码）；多个 spawn 后单次 yield 等待全部" | §5.1 并行规则 |
| 7 | 平台专家 | P2 | maxSpawnDepth 未显式确认 | start_ship_pro.py 启动前执行 `openclaw config get maxSpawnDepth`，≥ 2 才允许启动 | §8.2 入口守卫 |
| 8 | 平台专家 | P2 | cwd 硬编码为绝对路径 | 改用 `DEEPFLOW_HOME` 环境变量，`start_ship_pro.py` 中 `os.environ.get('DEEPFLOW_HOME', ...)` | §5.1 / §7 |
| 9 | 平台专家 | P2 | exec 环境约束仅在 prompt 中 | io_helper.py 文件头 shebang + 注释强化："⛔ 此文件禁止 from openclaw import" | §3.1 |
| 10 | 管线专家 | P2 | validate-quality 对自创阶段 gate_fn 映射 | 未知 stage 返回 `{pass: null, warning: "no gate_fn, fallback to format-only"}`，不报错 | §3.2 |
| 11 | 管线专家 | P2 | compact-history 信息丢失边界 | 改为"schema 字段列表 + 字段值完整列表"，io_helper 不截断，截断策略由 Orchestrator 控制 | §3.5 |
| 12 | 管线专家 | P2 | Judge Worker 失败降级路径 | Judge 失败 → Orchestrator 自评并标记 `verdict: "self-assessed"`（非独立评估） | §5.1 Phase 4 |
| 13 | 管线专家 | P3 | 并行阶段 blackboard 文件写入冲突 | 当前不修复（树状依赖图无风险），记录为 TODO：未来引入 `.lock` | §4.2 备注 |
| 14 | 可靠性专家 | P2 | compact-history 可能丢失失败细节 | 保留所有 gate_fail/gate_conditional 阶段完整记录（按状态筛选，不按位置） | §3.5 |
| 15 | 可靠性专家 | P2 | 并行阶段部分失败策略模糊 | 明确：已完成并行阶段结果保留，仅重做失败阶段；required=true 失败阻塞，否则标记 skipped | §5.1 并行规则 |
| 16 | 可靠性专家 | P2 | write-status 时序窗口 | resume-context 增加"文件扫描"：blackboard 有输出但状态未更新 → 自动修正状态 | §3.4 |
| 17 | 可靠性专家 | P2 | Judge Worker 评估可靠性 | Judge 评估结果与 Python gate 交叉验证：Judge pass 但 validate-quality fail → 以 quality 为准 | §5.1 Phase 4 |

---

## 修复策略

1. **保留 V2 原文件**：复制为 `SHIP_PRO_AI_NATIVE_PROPOSAL_V2.md`
2. **生成 V3**：在原文件上直接修改，顶部加版本标识
3. **变更追踪**：每处修改在对应章节加 `<!-- V3 FIX #N -->` 注释
4. **第三轮评审**：3 位新专家（非 V1/V2 评审者），视角如下：
   - **AI Native 工程师**（侧重 LLM 与代码的边界设计）
   - **分布式系统专家**（侧重并发、状态一致性、故障传播）
   - **开发者体验专家**（侧重 SKILL.md 可读性、Prompt 清晰度、调试体验）

---

## 第三轮评审专家（已规划）

| # | 专家 | 视角 | 第一轮参与 |
|---|------|------|----------|
| 1 | AI Native 工程师 | LLM/代码边界、Prompt 工程、Goal 声明式 | ❌ 新 |
| 2 | 分布式系统专家 | 并发安全、状态一致性、故障传播 | ❌ 新 |
| 3 | 开发者体验专家 | SKILL.md 可读性、调试体验、文档清晰度 | ❌ 新 |

---

*创建时间: 2026-06-25*
