# 评审报告：AI Native 架构师

> **评审人**: AI Native 架构师（LLM-native 系统设计方向）  
> **评审日期**: 2026-06-25  
> **评审对象**: `SHIP_PRO_AI_NATIVE_PROPOSAL.md`  
> **参考材料**: `run_pipeline.py`（1053行当前实现）、`SKILL.md` V4.0、`AI_NATIVE_LOOP_DESIGN.md`

---

## 总评

- **总评分**: 7.2/10
- **核心判断**: 方案方向正确，核心思路"LLM 控制流 + Python I/O"与研讨会共识高度一致；但 Orchestrator Prompt 设计过于粗放，io_helper.py 接口遗漏关键能力，迁移路径缺少断点续接设计，整体处于"架构正确、细节不足"的状态。

---

## 逐维度评审

### 1. AI Native 纯度 (7/10)

**优点**：
- 核心改造目标明确：将 `AGENT_ORDER`、`GATE_CONFIG`、`AGENT_MODELS` 三组硬编码控制流全部移交给 LLM，这是正确的。
- `io_helper.py` 定位清晰：纯 I/O（文件读写 + Pydantic 格式校验），不包含任何控制逻辑。
- 保留了 Pydantic 做"格式校验"而非"质量判断"，这个边界划得好——格式是确定性的，质量是语义的。

**问题**：
- **P0 — Worker Prompt 模板仍有硬编码骨架**：方案中 Worker Prompt 模板（§3.5）预设了 5 个固定阶段名（`{stage_name}`），虽然内容动态填充，但阶段本身仍是预定义的。真正的 AI Native 应该是 LLM 连阶段名都可以自创（比如发现需要 "security_reviewer" 阶段）。
- **P1 — decisions.jsonl 是追加写入，不是 LLM 决策的**：方案说"所有决策写入 decisions.jsonl"，但写入动作本身是 `exec echo >>`，这意味着 LLM 必须自己记得写。如果忘了写或格式不对，就没有审计轨迹。应该由 io_helper.py 提供 `log-decision` 命令，确保结构化写入。
- **P2 — validate-format 的边界模糊**：方案说 Pydantic 只做格式校验，但 `check_gate()` 当前实现的 gate 函数里包含业务逻辑（如 `gate_decomposer` 需要 blueprint 做 module coverage check）。这些 gate 函数在 AI Native 架构下应该被 LLM 评估取代，还是保留为"格式校验"？方案没有明确。

**建议**：
1. Worker Prompt 模板应该完全由 LLM 生成，io_helper.py 只负责注入 schema 和 output_path。
2. 增加 `io_helper.py log-decision` 命令，结构化记录决策。
3. 明确 gate 函数的去留：建议保留 Pydantic 格式校验，废弃业务逻辑 gate（由 LLM 评估取代）。

---

### 2. 架构一致性 (7/10)

**与 AI Native Loop 研讨会 8 项共识的对齐**：

| 共识 | 对齐度 | 说明 |
|------|--------|------|
| LLM 做所有决策 | ✅ 高 | Orchestrator 自主规划、评估、恢复 |
| Python 只做 I/O | ✅ 高 | io_helper.py 定位正确 |
| 分形 Goal 嵌套 | ⚠️ 中 | 方案提到"Orchestrator Goal → 各阶段 Sub-Goal"，但没有具体设计 Goal 声明和验证机制 |
| Error Analyzer | ⚠️ 中 | Orchestrator 内置错误分析，但没有独立的 Error Analyzer 角色/阶段 |
| Dream Loop | ✅ N/A | 明确不在范围，decisions.jsonl 为未来数据源 |
| Memory 是灵魂 | ⚠️ 中 | decisions.jsonl 写了，但没有说如何跨 session 复用 |
| 间歇式心跳 | ✅ N/A | Watcher 已是 V3 AI Native |
| 一步到位做全 AI Native | ⚠️ 中 | 方案说"一步到位"，但迁移策略又是"不删旧的，新建并行"——这是渐进式 |

**问题**：
- **P1 — 缺少 Goal Judge 设计**：研讨会的核心共识是"声明式目标 + LLM Judge 验证"，但方案中 Orchestrator 的"最终评估"阶段没有具体设计：用什么标准判断？是 Orchestrator 自己判断还是需要独立 Judge？
- **P1 — 缺少 Compaction 设计**：`AI_NATIVE_LOOP_DESIGN.md` 强调 Context Compaction 是关键层（80K tokens 塞满上下文导致注意力崩溃），但方案完全没有提及 Orchestrator 的上下文管理策略。5 个阶段串行下来，Orchestrator 的上下文会膨胀到什么程度？
- **P2 — Memory 复用路径不清晰**：decisions.jsonl 写了之后呢？谁来读？什么时候读？如何影响下一次执行？

**建议**：
1. 增加 Goal Judge 设计：最终评估阶段应该是独立的 LLM 调用（可以用不同模型），不是 Orchestrator 自己评自己。
2. 增加 Compaction 策略：每完成一个阶段，Orchestrator 应该压缩历史（或 io_helper.py 提供 `compact-history` 命令）。
3. 明确 decisions.jsonl 的消费方：是 Dream Loop？是 Orchestrator 自己的反思阶段？还是调试工具？

---

### 3. Orchestrator Prompt 设计 (6/10)

**优点**：
- 工具列表清晰（exec, sessions_spawn, sessions_yield, read）。
- 5 个 Phase 的结构合理（理解→规划→执行→评估→完成）。
- 约束部分好："你自主决定执行计划，不要问主 Agent"——这是 AI Native 的核心。

**问题**：
- **P0 — Prompt 过于粗放，缺少具体约束**：
  - "分析需要哪些阶段（不一定要全部 5 个）"——但没有告诉 LLM 什么情况下可以跳过阶段。如果 LLM 决定跳过 reviewer，谁来保证质量？
  - "决定哪些阶段可以并行"——但没有给出依赖关系的参考。LLM 需要知道 decomposer 依赖 architect 输出，specifier 依赖前两者。这些信息应该由 io_helper.py 提供（如 `read-dependencies` 命令），而不是 LLM 凭空猜测。
  - "如果不够好：带 feedback 重试，或换方案"——但没有告诉 LLM 什么是"不够好"的标准。需要具体的质量维度（完整性、一致性、可行性、架构原则符合度）。

- **P0 — 缺少阶段依赖图**：当前 `run_pipeline.py` 有 `AGENT_DEPENDENCIES` 定义依赖关系，这是有价值的领域知识。AI Native 架构下，这个知识应该注入到 Orchestrator 的 prompt 中（作为参考，不是硬约束），而不是完全丢弃。

- **P1 — 缺少错误恢复策略指导**：方案说"遇到问题自己尝试解决（最多 3 次）"，但没有告诉 LLM 常见的错误类型和对应的恢复策略。比如：
  - Worker 输出格式错误 → 带 schema 反馈重试
  - Worker 输出内容质量差 → 提供更具体的上下文重试
  - Worker 超时 → 降级到更简单的任务或跳过
  - 连续 3 次失败 → 上报主 Agent

- **P1 — 缺少并行执行的具体指导**：方案说"决定哪些阶段可以并行"，但没有告诉 LLM 如何 spawn 多个 worker 并等待它们全部完成。OpenClaw 的 sessions_spawn + sessions_yield 模式是单 worker 的，多 worker 并行需要不同的模式。

- **P2 — Worker Prompt 模板缺少质量维度**：`{orchestrator_provided_quality_criteria}` 是空的占位符，没有给 LLM 提供质量维度的参考列表。

**建议**：
1. 在 prompt 中注入阶段依赖图（作为参考，标注"你可以偏离但需要理由"）。
2. 增加具体的质量评估维度（完整性、一致性、可行性、架构原则符合度、Schema 合规性）。
3. 增加错误恢复策略菜单（格式错误→重试，质量差→换上下文，超时→降级，连续失败→上报）。
4. 明确并行执行的技术方案（多个 sessions_spawn + 多个 sessions_yield？还是顺序执行？）。

---

### 4. io_helper.py 接口设计 (7/10)

**优点**：
- 命令设计简洁：7 个命令覆盖了核心 I/O 需求。
- 职责边界清晰：只做文件读写和格式校验，不包含控制逻辑。
- `build-prompt` 命令设计巧妙：LLM 提供内容，Python 填充模板——这是正确的混合架构。

**问题**：
- **P0 — 缺少 `read-dependencies` 命令**：Orchestrator 需要知道阶段依赖关系才能做规划。当前 `AGENT_DEPENDENCIES` 定义在 `run_pipeline.py` 中，io_helper.py 没有暴露这个信息。
- **P0 — 缺少 `log-decision` 命令**：方案要求"所有决策写入 decisions.jsonl"，但 io_helper.py 没有提供结构化写入的命令。`exec echo >>` 不可靠（LLM 可能忘记写、格式错误）。
- **P1 — `build-prompt` 的 `--context <json>` 参数设计有问题**：JSON 作为命令行参数有长度限制（macOS ARG_MAX ~262KB），如果上下文很大（如完整的 Living Spec），会超出限制。应该改为从文件读取（`--context-file <path>`）。
- **P1 — 缺少 `compact-history` 命令**：Orchestrator 执行 5 个阶段后，上下文会膨胀。io_helper.py 应该提供历史压缩功能（读取历史决策和输出，生成结构化摘要）。
- **P2 — `validate-format` 的输出格式未定义**：应该明确返回什么（pass/fail + 错误列表 + 建议修复？）。
- **P2 — `scan-progress` 与 Watcher 的 `pipeline_watcher.py` 功能重叠**：应该明确两者的关系（是替代还是共存？）。

**建议**：
1. 增加 `read-dependencies` 命令，返回阶段依赖图（JSON）。
2. 增加 `log-decision <output_dir> <decision_type> <content>` 命令，结构化写入 decisions.jsonl。
3. `build-prompt` 改为 `--context-file <path>`，避免命令行参数过长。
4. 增加 `compact-history <output_dir>` 命令，生成上下文摘要。
5. 明确 `validate-format` 的输出格式（建议：`{pass: bool, errors: [...], suggestions: [...]}`）。

---

### 5. 迁移可行性 (8/10)

**优点**：
- 迁移策略务实："不删旧的，新建并行"——这是正确的工程实践。
- 回滚方案清晰：保留旧 `run_pipeline.py`，随时可以切回。
- 验证方式具体：用 mock 输入或上次成功的 Living Spec 跑通。

**问题**：
- **P1 — 缺少断点续接设计**：当前 V4.0 有 `.stage_progress.json` 做断点续接，但 AI Native 方案没有提及。如果 Orchestrator 在执行第 3 个阶段时崩溃（上下文溢出、网络错误），如何恢复？需要重新从头开始吗？
- **P1 — 缺少 Orchestrator 上下文溢出的应对方案**：`memory/2026-06-25.md` 记录了"Orchestrator 上下文溢出（语义检查消耗太多上下文，后续阶段提前退出）"是现有问题。AI Native 架构下，Orchestrator 的上下文消耗会更大（需要记住所有阶段的输入输出、决策历史）。方案没有提及如何应对。
- **P2 — 缺少性能基准对比**：V4.0 的执行时间、token 消耗、成功率是多少？AI Native 方案的预期是多少？没有基准就无法评估改造效果。
- **P2 — 缺少渐进式验证计划**：方案说"用一个 mock 输入跑通"，但没有说如何逐步验证每个阶段。建议：先验证 io_helper.py 的每个命令 → 再验证 Orchestrator 的单阶段执行 → 再验证多阶段串行 → 再验证并行。

**建议**：
1. 增加断点续接设计：Orchestrator 每完成一个阶段，写入 checkpoint；崩溃后从 checkpoint 恢复。
2. 增加上下文管理策略：每完成一个阶段，压缩历史（或 io_helper.py 提供 `compact-history`）。
3. 建立性能基准：记录 V4.0 的执行时间、token 消耗、成功率，作为对比基线。
4. 制定渐进式验证计划：分 4 步验证（io_helper 命令 → 单阶段 → 多阶段串行 → 并行）。

---

## 必须修改的问题（P0/P1）

| # | 严重度 | 问题 | 建议 |
|---|--------|------|------|
| 1 | P0 | Orchestrator Prompt 缺少阶段依赖图 | 注入依赖关系作为参考（不是硬约束） |
| 2 | P0 | Orchestrator Prompt 缺少质量评估维度 | 增加具体维度：完整性、一致性、可行性、架构原则符合度、Schema 合规性 |
| 3 | P0 | io_helper.py 缺少 `read-dependencies` 命令 | 增加命令，返回阶段依赖图（JSON） |
| 4 | P0 | io_helper.py 缺少 `log-decision` 命令 | 增加命令，结构化写入 decisions.jsonl |
| 5 | P1 | 缺少 Goal Judge 设计 | 最终评估应该是独立的 LLM 调用，不是 Orchestrator 自己评自己 |
| 6 | P1 | 缺少 Context Compaction 设计 | 增加上下文压缩策略（io_helper.py `compact-history` 或 Orchestrator 内置） |
| 7 | P1 | 缺少错误恢复策略指导 | 在 prompt 中增加错误恢复策略菜单 |
| 8 | P1 | 缺少断点续接设计 | 增加 checkpoint 机制，支持崩溃恢复 |
| 9 | P1 | `build-prompt --context <json>` 有长度限制 | 改为 `--context-file <path>` |
| 10 | P1 | Worker Prompt 模板仍有硬编码骨架 | 阶段名应该由 LLM 自创，不是从预定义列表选择 |

---

## 建议改进（P2）

1. **明确 gate 函数的去留**：建议保留 Pydantic 格式校验，废弃业务逻辑 gate（由 LLM 评估取代）。在方案中明确说明。
2. **Memory 复用路径**：明确 decisions.jsonl 的消费方（Dream Loop？Orchestrator 反思？调试工具？）。
3. **并行执行的技术方案**：明确多 worker 并行的技术实现（多个 sessions_spawn + 多个 sessions_yield？）。
4. **`validate-format` 输出格式**：明确返回结构（`{pass: bool, errors: [...], suggestions: [...]}`）。
5. **`scan-progress` 与 Watcher 的关系**：明确是替代还是共存。
6. **性能基准对比**：建立 V4.0 vs AI Native 的执行时间、token 消耗、成功率基线。
7. **渐进式验证计划**：分 4 步验证（io_helper 命令 → 单阶段 → 多阶段串行 → 并行）。

---

## 亮点

1. **核心架构方向正确**："LLM 控制流 + Python I/O"的分离是 AI Native 的核心，方案把握住了。
2. **io_helper.py 职责边界清晰**：只做文件读写和格式校验，不包含控制逻辑——这是正确的。
3. **迁移策略务实**："不删旧的，新建并行" + 回滚方案——工程实践成熟。
4. **保留 Pydantic 做格式校验**：区分"格式"（确定性）和"质量"（语义）——这是 AI Native 的关键边界。
5. **decisions.jsonl 的设计**：为未来 Dream Loop 和 Meta-Loop 提供数据基础——有前瞻性。
6. **与 Solution Pro 的一致性**：方案考虑了跨域一致性，不是孤立设计。

---

## 总结

方案的核心架构方向是正确的，但在 Orchestrator Prompt 设计、io_helper.py 接口完整性、上下文管理、断点续接等方面存在明显不足。建议优先解决 P0 问题（依赖图注入、质量维度定义、io_helper 命令补全），然后解决 P1 问题（Goal Judge、Compaction、错误恢复、断点续接），最后完善 P2 细节。

**改造建议**：在当前方案基础上，增加约 30% 的设计细节（主要是 Prompt 约束和 io_helper 命令），即可进入实施阶段。

---

*评审完成 | AI Native 架构师 | 2026-06-25*
