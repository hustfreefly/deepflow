# 第二轮评审报告：管线工程专家

> **评审人**: 管线工程专家  
> **评审日期**: 2026-06-25  
> **评审对象**: `SHIP_PRO_AI_NATIVE_PROPOSAL.md` V2  
> **评审范围**: 管线工程质量（阶段完整性、质量门控、数据流、并行安全、可观测性）

---

## V1 → V2 改进追踪

| # | V1 严重度 | V1 问题 | V2 修复状态 | 说明 |
|---|----------|---------|-----------|------|
| 1 | P0 | LLM 可能跳过关键阶段 | ✅ 已修复 | `validate-plan --required architect,reviewer,packager` 代码级强制校验（§3.2）；`stage-dependencies.json` 显式标记 `required: true`（§4.1）；Orchestrator prompt Phase 2 强制调用 validate-plan（§5.1）。LLM 可以偏离执行图，但无法绕过 Python 侧的 required 校验。 |
| 2 | P0 | 质量门控退化为"橡皮图章" | ✅ 已修复 | `validate-quality` 命令调用保留的 Python gate 函数（gate_architect 等）做语义校验（§3.2）；Orchestrator prompt 要求"双重验证"：validate-format（Pydantic）+ validate-quality（Python gate）+ LLM 自评 三层（§5.1 Phase 3 Step 4）；`stage-dependencies.json` 每个阶段声明 `gate_fn` 字段（§4.1）。 |
| 3 | P0 | 阶段间数据依赖不透明 | ✅ 已修复 | `stage-dependencies.json` 显式声明每个阶段的 inputs/outputs/depends_on（§4.1）；`build-prompt` 自动注入前置阶段输出（§5.2 Worker Prompt 模板 `{auto_injected_dependencies}`）；`list-dependencies` 命令供调试（§3.1）。数据依赖从 LLM 隐式记忆变为代码显式声明。 |
| 4 | P0 | 并行安全性无保障 | ✅ 基本修复 | `can-parallel` 命令基于 stage-dependencies.json 的 depends_on 判断（§3.2）；Orchestrator prompt 明确"默认串行，返回 can_parallel: true 才允许并行"（§5.1）；原子写入保护 write-status（§3.3）。**残留小问题**：blackboard 文件级写入锁未显式设计，但 can-parallel 已阻止有数据冲突的阶段并行，实际风险低。 |
| 5 | P1 | retry 上限由 prompt 约束 | ✅ 已修复 | `check-retry-limit` 命令代码级强制（§3.2, §6.2）；Orchestrator prompt 明确"重试前必须调用"，返回 `allowed: false` 时禁止重试、必须上报（§5.1）；`stage-dependencies.json` 每阶段声明 `max_retries`（§4.1）。从 prompt 建议升级为代码护栏。 |
| 6 | P1 | `.stage_progress.json` 未提及 | ✅ 已修复 | §9 明确声明"保留，确保 Watcher 兼容"；新增 `.heartbeat` 文件设计（§3.4），Watcher 可用 heartbeat 判断 Orchestrator 存活状态，比纯文件变化检测更可靠。 |

**修复率**: 6/6（100%），其中 4 个 P0 全部修复，2 个 P1 全部修复。

---

## 新评分

### 分维度评分

| 维度 | V1 评分 | V2 评分 | 变化 | 说明 |
|------|--------|--------|------|------|
| 阶段完整性保证 | 4/10 | 8/10 | +4 | validate-plan 代码级强制 required 阶段不能跳过；LLM 可偏离但受约束 |
| 质量门控有效性 | 5/10 | 8/10 | +3 | 三层验证（Pydantic + Python gate + LLM 评估）；gate 函数保留为代码护栏 |
| 阶段间数据流 | 6/10 | 8.5/10 | +2.5 | 显式依赖声明 + 自动注入，不再依赖 LLM 手动传递 |
| 并行安全性 | 3/10 | 7.5/10 | +4.5 | can-parallel 代码级判断；默认串行策略；原子写入保护状态文件 |
| 可观测性 | 7/10 | 8.5/10 | +1.5 | .stage_progress.json 保留 + .heartbeat 新增 + decisions.jsonl 结构化 + compact-history 防膨胀 |

### 总评分

- **总评分**: **8.0/10**（V1: 5.5/10，提升 +2.5）
- **核心判断**: V2 将第一轮的 6 个 P0/P1 问题全部通过代码级护栏修复，"LLM 做决策、代码做护栏"的设计原则落地扎实，管线工程从"LLM 即兴发挥"回归到"有工程保障的 AI Native 管线"。

---

## V2 新发现的问题

### 1. [P2] validate-quality 对自创阶段的 gate_fn 映射

**问题**：Orchestrator 被允许自创阶段名（§5.2 "不再预定义为 5 个固定阶段"），但 `validate-quality <stage>` 依赖 `stage-dependencies.json` 中的 `gate_fn` 字段。如果 Orchestrator 创建了一个不在 stage-dependencies.json 中的阶段，validate-quality 会找不到对应的 gate 函数。

**风险**：低。Orchestrator 自创阶段本身是边缘场景，且 validate-plan 会校验 required 阶段存在。

**建议**：validate-quality 对未知 stage 返回 `{"pass": null, "warning": "no gate_fn defined, falling back to format-only validation"}`，而非报错。

### 2. [P2] compact-history 的信息丢失边界

**问题**：compact-history 取"前 500 字符 + schema 字段列表"作为摘要，但某些阶段输出（如 architect 的架构原则）可能在 500 字符后被截断关键内容。

**风险**：低。compact-history 只在第 3+ 阶段后调用，此时前置阶段输出已写入 blackboard 文件，Worker 可通过 build-prompt 读取完整内容。

**建议**：摘要策略改为"schema 字段列表 + 每字段 top-3 值"而非"前 500 字符"，确保关键字段不丢失。

### 3. [P2] Judge Worker 失败的降级路径

**问题**：§5.1 Phase 4 设计了独立 Judge Worker，但未说明 Judge Worker 自身失败（超时/输出不合规）时的降级策略。

**风险**：低。Judge Worker 是最终评估，失败后可由 Orchestrator 自己做最终评估作为 fallback。

**建议**：增加降级策略："Judge Worker 失败 → Orchestrator 自行评估并标记 verdict 为 self-assessed（非独立评估）"。

### 4. [P3] 并行阶段的 blackboard 文件写入冲突

**问题**：can-parallel 基于 depends_on 判断，理论上不会有两个并行阶段写同一文件。但如果未来依赖图变复杂（如两个并行阶段都写同一个共享配置文件），缺少文件级锁。

**风险**：极低。当前依赖图是树状结构，不存在此问题。

**建议**：当前不需要修复。如未来依赖图复杂化，可引入 blackboard 文件级 `.lock`。

---

## V2 设计亮点（管线工程视角）

1. **validate-plan + can-parallel + check-retry-limit 三件套**：将关键控制流从 prompt 约束升级为代码护栏，这是 V2 最大的改进。LLM 有决策自由，但自由在代码划定的边界内。

2. **stage-dependencies.json 作为单一事实来源**：一个文件同时服务于 validate-plan（阶段完整性）、can-parallel（并行安全）、build-prompt（数据注入）、validate-quality（gate 映射），设计简洁且一致。

3. **双重验证 → 三层验证**：validate-format（Pydantic 格式）+ validate-quality（Python gate 语义）+ LLM 自评，层次清晰，每层职责明确。

4. **断点恢复设计完备**：resume-context + .heartbeat + pipeline_state.json 三者配合，Watcher 和 Orchestrator 都能准确判断管线状态。

5. **compact-history 防上下文膨胀**：这是 V1 完全缺失的，V2 补上了，且设计合理（每 2 阶段压缩一次）。

---

## 是否可以进入实施阶段？

- [x] **是**
- [ ] 需要第三轮

**理由**：

1. 第一轮 6 个 P0/P1 问题全部修复，且修复方式符合"代码护栏"原则，不是简单的 prompt 加强。
2. V2 新发现的问题均为 P2/P3 级别，不影响管线核心工程质量，可在实施过程中逐步完善。
3. 迁移策略稳健（保留旧 run_pipeline.py、入口守卫、回滚 SOP），风险可控。
4. 验证计划覆盖关键场景（单阶段、多阶段串行、断点恢复、超时保护、回滚），可执行。

**实施建议**：

1. **优先实现 io_helper.py 的 4 个护栏命令**（validate-plan, check-retry-limit, can-parallel, validate-quality），这是管线安全的基石。
2. **stage-dependencies.json 先行**：在实现 io_helper.py 之前先定义好，因为多个命令依赖它。
3. **第一轮验证只跑串行**：先验证 5 阶段串行全流程通过，再测试并行场景。
4. **compact-history 可延后**：前几次运行上下文不太可能膨胀到需要压缩，等实际遇到问题再启用。

---

*评审完成。V2 方案从 5.5/10 提升至 8.0/10，建议进入实施阶段。*
