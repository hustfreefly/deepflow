# 第二轮评审报告：AI Native 架构师

> **评审人**: AI Native 架构师（LLM-native 系统设计方向）  
> **评审日期**: 2026-06-25  
> **评审对象**: `SHIP_PRO_AI_NATIVE_PROPOSAL.md` V2  
> **参考**: 第一轮评审报告 `review_ai_native_architect.md`

---

## V1 → V2 改进追踪

| # | V1 问题 | 严重度 | V2 修复状态 | 说明 |
|---|---------|--------|-----------|------|
| 1 | Orchestrator Prompt 缺少阶段依赖图 | P0 | ✅ 已修复 | §5.1 有 ASCII 依赖图 + `list-dependencies` 命令 + `can-parallel` 命令。依赖图标注为"参考，非硬约束"，允许 LLM 偏离但需记录原因——正确的平衡。 |
| 2 | Orchestrator Prompt 缺少质量评估维度 | P0 | ✅ 已修复 | §5.1 "质量评估 5 维度"：完整性、一致性、可行性、架构原则符合度、Schema 合规性。具体且可操作。 |
| 3 | io_helper.py 缺少 `read-dependencies` 命令 | P0 | ✅ 已修复 | §3.1 `list-dependencies` 命令（名称微调，功能等价）。输出阶段依赖图 JSON。 |
| 4 | io_helper.py 缺少 `log-decision` 命令 | P0 | ✅ 已修复 | §3.1 `log-decision` 命令，结构化写入 decisions.jsonl（timestamp, type, stage, reason, outcome）。Prompt 中要求"每次决策后调用"。 |
| 5 | 缺少 Goal Judge 设计 | P1 | ✅ 已修复 | §5.1 Phase 4 独立 Judge Worker，与 Orchestrator 分离。评估维度明确，输出格式 `{verdict, score, issues}`。 |
| 6 | 缺少 Context Compaction 设计 | P1 | ✅ 已修复 | §3.5 `compact-history` 命令 + Prompt 中"每完成 2 个阶段调用一次"的强制要求。输出结构化摘要 JSON。 |
| 7 | 缺少错误恢复策略指导 | P1 | ✅ 已修复 | §5.1 "错误恢复策略菜单"：7 种错误类型 → 7 种恢复策略，表格形式，清晰可操作。 |
| 8 | 缺少断点续接设计 | P1 | ✅ 已修复 | §3.4 `resume-context` 命令 + `.heartbeat` 文件。输出已完成/失败/待执行阶段 + retry_count + 上下文文件列表。Prompt 中"启动时必须先调用"。 |
| 9 | `build-prompt --context <json>` 有长度限制 | P1 | ✅ 已修复 | §5.2 改为 `--context-file <path>`，从文件读取上下文。 |
| 10 | Worker Prompt 模板仍有硬编码骨架 | P1 | ✅ 已修复 | §5.2 模板完全通用化：`{stage_name}`、`{auto_injected_dependencies}`、`{orchestrator_context}` 等占位符，由 io_helper 基于 stage-dependencies.json 动态注入。明确说明"Orchestrator 可以自创阶段名"。 |

**修复率：10/10（100%）**

---

## 新评分

- **总评分**: 8.7/10（V1: 7.2/10，+1.5）
- **核心判断**: V1 的 10 个 P0/P1 问题全部修复，V2 在护栏层设计、断点续接、上下文管理、错误恢复等方面达到了可实施的设计深度。剩余问题均为 P2 级细节，不阻塞实施。

### 分项评分

| 维度 | V1 | V2 | 变化 | 说明 |
|------|----|----|------|------|
| AI Native 纯度 | 7.0 | 8.5 | +1.5 | Worker Prompt 完全通用化 + Goal Judge 独立 + 阶段名可自创 |
| 架构一致性 | 7.0 | 9.0 | +2.0 | 与研讨会共识全面对齐：Goal Judge、Compaction、decisions.jsonl 消费方明确 |
| Orchestrator Prompt | 6.0 | 9.0 | +3.0 | 依赖图 + 5 维质量 + 恢复菜单 + 断点检查 + 并行规则，从"粗放"到"精细" |
| io_helper.py 接口 | 7.0 | 8.5 | +1.5 | 从 7 命令扩展到 16 命令，覆盖 I/O + 护栏 + 恢复 + 调试全链路 |
| 迁移可行性 | 8.0 | 8.5 | +0.5 | 断点续接 + 回滚 SOP + 渐进验证计划（6 步），更完整 |

---

## V2 新发现的问题

### P2（建议改进，不阻塞实施）

| # | 严重度 | 问题 | 建议 |
|---|--------|------|------|
| 11 | P2 | **命令数量不一致**：§3.1 标题写"12 个命令"，但表格列出了 16 个（6 I/O + 5 护栏 + 2 恢复 + 1 调试，实际还多 2 个）。数字应修正。 | 更新标题为"16 个命令"或重新分类。 |
| 12 | P2 | **`compact-history` 的实现机制未明确**：是 LLM 摘要还是纯文本提取？如果是 LLM 调用，Orchestrator 上下文中需要有一个 LLM 可用；如果是纯提取，摘要质量可能不够。 | 明确实现方式。建议：纯提取 + 结构化 JSON 输出（不需要 LLM），因为 Orchestrator 自身就是 LLM，可以直接阅读结构化摘要。 |
| 13 | P2 | **Judge Worker 的失败处理未定义**：Phase 4 说 Judge 输出 `{verdict: "fail", ...}`，但 Orchestrator 收到 fail 后怎么办？回退到哪个阶段？重新执行还是上报？ | 增加 Judge fail 的处理分支：conditional → 修复 issues 后重新 Judge；fail → 上报主 Agent。 |
| 14 | P2 | **`validate-quality` 与 gate 函数的关系需澄清**：gate 函数（如 `gate_decomposer`）包含业务逻辑（module coverage check），在 AI Native 架构下这些 gate 函数是保留还是废弃？V2 说"保留 Python gate 函数"，但没有说明 gate 函数的维护策略。 | 明确：gate 函数保留作为"硬约束"（依赖无环、覆盖率下限），LLM 评估作为"软约束"（内容质量、合理性）。两者互补，不冲突。 |
| 15 | P2 | **`build-prompt` 的 `--context-file` 格式未定义**：文件是 JSON？YAML？纯文本？Orchestrator 如何构造这个文件？ | 建议定义为 JSON，包含 `{task, context, quality_criteria}` 三个字段，由 Orchestrator 写入临时文件后传给 build-prompt。 |
| 16 | P2 | **并行执行的技术细节不足**：Prompt 说"并行 spawn 多个 Worker 后，多次 `sessions_yield()` 等待全部完成"，但 OpenClaw 的 sessions_yield 是"结束当前 turn 等待 auto-announce"，多次 yield 的语义不明确。 | 建议明确：多个 sessions_spawn 后，一次 sessions_yield 即可等待全部完成（auto-announce 机制会逐个通知）。或者改为"默认串行，并行作为高级优化后续引入"。 |

### 观察（非问题）

- **stage-dependencies.json 的 `required` 字段与 `validate-plan --required` 的关系**：两者存在冗余。stage-dependencies.json 中 `required: true` 的阶段应该自动成为 `validate-plan` 的默认 required 集合，不需要 Prompt 中再手动指定 `--required architect,reviewer,packager`。这是小问题，实现时自然解决。
- **.heartbeat 与 pipeline_state.json 的关系**：两者都记录阶段状态，但 .heartbeat 是时间戳序列（用于 Watcher 探活），pipeline_state.json 是当前状态快照。职责不同但容易混淆，建议在实现时明确文档。

---

## V2 亮点（相比 V1 新增）

1. **护栏层设计成熟**：`check-retry-limit` + `check-budget` + `validate-plan` + `can-parallel` 四个护栏命令形成了完整的安全网，"LLM 做决策、代码做护栏"的原则落地扎实。
2. **错误恢复策略菜单**：7 种错误类型 → 7 种恢复策略的表格设计非常实用，直接可放入 Prompt。这是 V1 最大的缺失之一。
3. **断点续接完整方案**：`resume-context` + `.heartbeat` + checkpoint 的组合设计，覆盖了崩溃恢复、超时恢复、手动中断恢复三种场景。
4. **双重验证机制**：`validate-format`（Pydantic 格式）+ `validate-quality`（Python gate 语义）+ LLM 自主评估的三层验证，比 V1 的单层验证强很多。
5. **上下文管理策略**：`compact-history` + "每 2 阶段压缩一次"的频率设计，直接解决了 V1 中"上下文膨胀导致注意力崩溃"的问题。

---

## 是否可以进入实施阶段？

- [x] **是**
- [ ] 需要第三轮

**理由**：
1. V1 的 10 个 P0/P1 问题全部修复，无遗留高优先级问题。
2. V2 新发现的 6 个问题均为 P2 级（数字不一致、实现细节澄清），不阻塞实施，可在编码阶段自然解决。
3. 架构方向、护栏设计、迁移策略、回滚方案均已到位。
4. 评分从 7.2 → 8.7，达到了"可实施"阈值（8.0+）。

**实施建议**：
- 按 §8.1 迁移步骤 1-6 顺序执行
- 优先完成 io_helper.py（步骤 2），这是其他所有组件的基础
- §8.3 验证计划的 6 步渐进验证是正确的策略，严格执行
- P2 问题在实施过程中顺手解决，不需要单独迭代

---

*评审完成 | AI Native 架构师 | 2026-06-25*
