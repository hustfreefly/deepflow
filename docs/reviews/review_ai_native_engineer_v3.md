# 第三轮评审报告：AI Native 工程师

> **评审人**: AI Native 工程师（LLM/代码边界、Prompt 工程、Goal 声明式方向）  
> **评审对象**: `SHIP_PRO_AI_NATIVE_PROPOSAL.md` V3  
> **评审日期**: 2026-06-25  
> **评审轮次**: 第三轮（首次参与此方案）

---

## 总评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **总评分** | **6.5/10** | 有 AI Native 意识，但本质仍是"LLM 驱动的过程式管线" |
| **AI Native 纯度** | **5/10** | 忠礼决策"全 LLM 控制"未兑现，Prompt 是 5 阶段 waterfall |
| **Prompt 工程质量** | **6/10** | 结构清晰但过长，关键约束淹没，缺 few-shot |
| **LLM/代码边界** | **7/10** | 三层验证分工合理，但边界定义不够锐利 |
| **可实施性** | **8/10** | io_helper 设计扎实，迁移/回滚完善，可落地 |

**核心判断**: V3 是一个**工程扎实的"混合架构"**，但距离忠礼要求的"全 LLM 控制、不分阶段演进"的 AI Native 愿景有本质差距。方案用 LLM 包装了一个固定 5 阶段管线，Orchestrator 的"自主性"被限制在"可以偏离但必须记录原因"的框架内——这是**合规驱动，不是 AI Native**。

---

## 发现的问题

### P0（根本性问题，会导致方案偏离 AI Native 目标）

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P0-1 | **"全 LLM 控制"决策未兑现，本质仍是硬编码 5 阶段管线** | 忠礼决策原文："全 LLM 控制，Python 不做控制流"、"一步到位，不分阶段演进"。但 V3 方案中：① `stage-dependencies.json` 硬编码 5 个固定阶段 + 固定依赖关系；② Orchestrator Prompt 定义了 Phase 1→2→3→4→5 的固定流程；③ Orchestrator "可以偏离"依赖图，但偏离需要 `log-decision` 记录原因——这是"鼓励遵守，惩罚创新"。**这不是 AI Native，这是给 waterfall 管线加了个 LLM 调度器。** | **方案 A（推荐）**：将 `stage-dependencies.json` 改为"能力注册表"而非"阶段定义"。注册可用的 Worker 类型（architect/decomposer/reviewer/packager 等）及其输入输出 schema，但**不定义执行顺序**。Orchestrator 看到输入后自主决定调用哪些 Worker、什么顺序、是否并行。`validate-plan` 只校验"必要能力是否覆盖"，不校验"阶段是否齐全"。<br>**方案 B（折中）**：保留当前设计但明确标注"这是 V1 约束，后续迭代放开"，并在 Prompt 中给 Orchestrator 更大的自主权（如"你可以完全忽略依赖图，只要最终产出满足 Living Spec"）。 |
| P0-2 | **Orchestrator Prompt 是过程式（Phase 1→5），不是 Goal 声明式** | AI Native 的核心是：声明 Goal + Constraints，LLM 自主规划路径。当前 Prompt 是典型的 waterfall：Phase 1 理解输入 → Phase 2 规划 → Phase 3 执行 → Phase 4 评估 → Phase 5 完成。这是**人类写死的流程**，LLM 只是执行器。如果输入是一个简单的 Living Spec（如"给 order_service 加个字段"），Orchestrator 仍然要走完 5 个 Phase，这是浪费。 | **改为 Goal 声明式 Prompt**：<br>```markdown<br>## Goal<br>将 Living Spec 转化为满足以下约束的 Ship Package：<br>- 架构原则符合 Living Spec<br>- 所有模块覆盖率 ≥ 80%<br>- 通过 reviewer 独立评审<br>- 通过 packager 打包校验<br><br>## Constraints<br>- 重试上限：见 stage-dependencies.json<br>- 预算上限：30 分钟<br>- 必须调用 check-retry-limit / check-budget<br><br>## Available Workers<br>- architect: 输出架构设计<br>- decomposer: 输出工作包分解<br>- reviewer: 独立评审<br>- packager: 最终打包<br><br>## Your Autonomy<br>你自主决定执行路径。可以串行、并行、跳过非必要阶段。<br>每次决策后 log-decision。完成后 spawn Judge。<br>```<br>这样 Orchestrator 有真正的自主权，而不是被 Phase 1→5 绑死。 |
| P0-3 | **stage-dependencies.json 的 `required: true` 与"LLM 自主"矛盾** | `architect`、`reviewer`、`packager` 被标记为 `required: true`，`validate-plan` 会强制检查。这意味着 Orchestrator **不能跳过** 这三个阶段。但如果输入是一个极简单的需求（如"改个配置项"），architect 阶段可能是不必要的。LLM 的"自主性"被 `required` 字段架空了。 | **两种改法**：<br>1. 去掉 `required` 字段，改为 `validate-plan` 只输出 warning（"你跳过了 architect，确定吗？"），Orchestrator 确认后可继续。<br>2. 保留 `required`，但在 Prompt 中明确："required 是默认约束，如果你有充分理由跳过，log-decision 记录后可覆盖"。 |

### P1（严重影响实施质量）

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P1-1 | **Orchestrator Prompt 过长（~200 行），关键约束淹没** | Prompt 包含大量规则列表（工具表、依赖图、执行流程、错误恢复菜单、5 维度评估、并行规则、约束...）。LLM 对长 prompt 的遵循度随长度递减。关键约束（如"重试前必须 check-retry-limit"）被淹没在细节中，容易被忽略。 | **分层 Prompt 设计**：<br>1. **System Prompt**（< 50 行）：Goal + Constraints + 核心规则（重试必查、预算必查、spawn 必传 cwd）。<br>2. **Reference Doc**（可读取）：错误恢复菜单、5 维度评估细节、并行规则等。Orchestrator 需要时用 `read` 读取，而不是全部塞进 Prompt。<br>3. **Few-shot 示例**：给 1-2 个"好的执行计划"和"好的 Worker feedback"示例，比规则列表更有效。 |
| P1-2 | **LLM 评估 vs Python gate 的边界在 Prompt 中不够锐利** | §3.2 定义了三层验证（format → quality → LLM 评估），且说明"gate 是硬约束，LLM 是软约束"。但 §5.1 Phase 3 步骤 4 中，Orchestrator 的执行顺序是：validate-format → validate-quality → **你自己的质量评估**。问题是：如果 Python gate 说 pass，但 Orchestrator 自评说 fail，怎么办？Prompt 没说。反过来（§5.1 Phase 4，Judge pass 但 quality fail → 以 quality 为准）只解决了 Judge 场景，没解决 Orchestrator 自评场景。 | **在 Prompt 中明确优先级链**：<br>```<br>validate-format fail → 必须重试（不可覆盖）<br>validate-quality fail → 必须重试（不可覆盖，即使你认为内容合理）<br>validate-format + quality pass，但你自评 fail → 可带 feedback 重试，但受 check-retry-limit 约束<br>```<br>这样 Orchestrator 清楚知道：哪些是硬墙，哪些是软约束。 |
| P1-3 | **Judge Worker 与 Orchestrator 使用相同评估维度，可能产生相同偏差** | Judge 评估维度：完整性、一致性、可行性、架构原则符合度、Schema 合规性。Orchestrator 评估维度：完全相同。如果 Orchestrator 对某问题视而不见（如忽略了某个依赖矛盾），Judge 用相同维度评估，很可能也忽略。这不是"独立评估"，是"同一个 LLM 用同一个 prompt 评估两次"。 | **Judge 应有不同视角**：<br>- Orchestrator 关注"产出是否满足 Living Spec"<br>- Judge 关注"产出是否能被下游正确消费"（如：工作包是否能被开发者直接执行？架构设计是否有明显的单点故障？）<br>或者引入"对抗性 Judge"：Judge 的目标是**找出问题**，而不是"评估质量"。Prompt 改为："请找出这个 Ship Package 中的 3 个最大风险"。 |
| P1-4 | **compact-history "纯提取不调用 LLM"可能丢失关键语义** | §3.5 明确 compact-history 是"纯提取 + 结构化 JSON，不调用额外 LLM"。但结构化 JSON 摘要（schema 字段列表 + top-3 值）会丢失**决策原因**（如"为什么选择微服务而不是单体"）。Orchestrator 在后续阶段可能需要这些原因来做决策（如 reviewer 阶段需要知道架构原则来评审）。丢失原因 → Orchestrator 可能做出与前期决策矛盾的后续决策。 | **compact-history 增加"决策原因"字段**：<br>```json<br>"key_decisions": [<br>  {"stage": "architect", "decision": "use_microservices", <br>   "reason": "Living Spec 要求独立部署和团队自治",<br>   "alternatives_considered": ["monolith", "modular_monolith"]}<br>]<br>```<br>reason 和 alternatives 从 architect 输出的"决策记录"字段中提取（如果输出 schema 有该字段），或从 decisions.jsonl 中提取。 |

### P2（建议改进，不阻塞实施）

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| P2-1 | **Prompt 缺少 few-shot 示例** | 没有"好的执行计划长什么样"、"好的 Worker feedback 长什么样"的示例。LLM 对 few-shot 的遵循度远高于 zero-shot 规则描述。 | 在 Prompt 末尾或 Reference Doc 中增加 1-2 个示例：<br>- 示例执行计划：`{"stages": [...], "order": [...], "parallel": [...]}`<br>- 示例 feedback：`"上次 decomposer 输出中 wp-3 缺少依赖声明，本次请补充"` |
| P2-2 | **log-decision schema 过于宽松** | `{timestamp, type, stage, reason, outcome}` 中 `type` 和 `outcome` 是自由文本。decisions.jsonl 会变成垃圾场（"plan" / "planning" / "Plan" 三种写法）。 | 枚举合法值：<br>`type`: `plan` / `stage_start` / `stage_complete` / `retry` / `escalation` / `skip` / `parallel_decision`<br>`outcome`: `pass` / `fail` / `skip` / `escalate` / `retry` |
| P2-3 | **Worker Prompt 模板缺少"失败反馈"占位符** | 重试时 Orchestrator 需要告诉 Worker "上次哪里错了"。当前模板只有 `{orchestrator_context}`，Orchestrator 只能把 feedback 塞进去，语义不清晰。 | 增加 `{failure_feedback}` 占位符：<br>```markdown<br>## 上次执行反馈（仅重试时存在）<br>{failure_feedback}<br><br>请针对以上问题修正你的输出。<br>``` |
| P2-4 | **缺少 Prompt 版本管理** | Orchestrator Prompt 硬编码在 SKILL.md 中。修改 Prompt 需要改 SKILL.md → git checkout → 重新部署。不支持热更新，也不方便 A/B 测试不同 Prompt 版本。 | 将 Prompt 模板外置为 `prompts/orchestrator_v1.md`，SKILL.md 中引用路径。支持通过配置切换 Prompt 版本。 |
| P2-5 | **`validate-plan` 的 `--required` 参数硬编码在 Prompt 中** | Prompt 中写死了 `validate-plan <output_dir> --required architect,reviewer,packager`。如果未来需要增加/减少 required 阶段，需要改 Prompt。 | `--required` 列表从 `stage-dependencies.json` 中 `required: true` 的阶段自动推导，不需要在 Prompt 中硬编码。`validate-plan <output_dir>` 即可。 |
| P2-6 | **Orchestrator 自评与 Judge Worker 的分工不够清晰** | Phase 3 步骤 4 有 Orchestrator 自评，Phase 4 有 Judge Worker。两者都在评估质量，但评估时机、评估粒度、评估目的没有明确区分。 | 明确分工：<br>- Orchestrator 自评：**阶段级**，每个阶段完成后立即评估，目的是决定是否重试。<br>- Judge Worker：**管线级**，所有阶段完成后评估，目的是决定整体是否通过。<br>在 Prompt 中说明这个区别，避免 Orchestrator 困惑。 |

---

## V3 P2 修复评估

| 指标 | 评分 |
|------|------|
| 修复数量 | 17 P2 + 1 P3，全部标注 `<!-- V3 FIX #N -->` |
| 修复质量 | **7.5/10** |
| 是否到位 | **基本到位，但有 3 个修复引入了新问题** |

**修复到位的（14/17）**：
- ✅ FIX #1（命令数量统一为 16）
- ✅ FIX #2（compact-history 明确为纯提取）—— 但我认为"纯提取"本身是 P1 问题（见 P1-4）
- ✅ FIX #4（三层验证分工表）—— 清晰，但 Prompt 中优先级链未闭环（见 P1-2）
- ✅ FIX #5（context-file JSON schema）
- ✅ FIX #6（sessions_yield 语义明确）
- ✅ FIX #7（maxSpawnDepth 入口守卫）
- ✅ FIX #8（cwd 改用 DEEPFLOW_HOME）
- ✅ FIX #9（io_helper 文件头强化）
- ✅ FIX #10（自创阶段 fallback format-only）
- ✅ FIX #11（compact-history 字段级摘要）
- ✅ FIX #13（并行 blackboard 冲突 TODO）
- ✅ FIX #16（resume-context 文件扫描）

**修复引入新问题的（3/17）**：
- ⚠️ FIX #3/#12（Judge Worker 失败处理）—— 增加了 fail/conditional 分支和自评降级，但 Judge 与 Orchestrator 评估维度相同的问题未解决（见 P1-3）
- ⚠️ FIX #14（compact-history 保留失败细节）—— 保留了最近 2 阶段完整记录，但"纯提取"策略仍可能丢失决策原因（见 P1-4）
- ⚠️ FIX #17（Judge 与 Python gate 交叉验证）—— "以 validate-quality 为准"规则清晰，但只覆盖了 Judge 场景，没覆盖 Orchestrator 自评场景（见 P1-2）

---

## V3 亮点

1. **io_helper.py 设计扎实**：16 个命令分类清晰（I/O / 护栏 / 恢复 / 调试），每个命令有明确的输入输出 schema。原子写入、枚举校验、文件扫描自动修正状态等细节体现了工程素养。

2. **三层验证分工（format → quality → LLM）**：比 V2 的"双层"更清晰，gate 函数负责硬约束、LLM 负责软约束的分工合理。V3 新增的"未知 stage fallback format-only"容错处理也到位。

3. **断点恢复设计完善**：resume-context 不仅读 pipeline_state.json，还扫描 blackboard 实际文件，自动修正状态不一致。这解决了 write-status 时序窗口问题，是生产级设计。

4. **迁移/回滚策略零风险**：保留 run_pipeline.py 不删、入口守卫检查 maxSpawnDepth、回滚 SOP 清晰。对生产环境的尊重值得肯定。

5. **V2→V3 修复追踪透明**：17 个 P2 全部有 `<!-- V3 FIX #N -->` 标注，P2_FIXES_V3.md 追踪完整。这种工程纪律在 AI 方案中少见。

---

## 是否可以进入实施阶段？

- [ ] 是
- [x] 需要第四轮

**理由**：

3 个 P0 问题指向同一个根本矛盾：**方案声称"AI Native"，但实际设计是"LLM 驱动的硬编码管线"**。忠礼的决策是"全 LLM 控制，不分阶段演进"，V3 没有兑现。如果带着 P0 进入实施，会得到一个"看起来 AI Native 但行为上仍是 waterfall"的系统——这比直接做 waterfall 更糟，因为它增加了 LLM 的不确定性和 Prompt 维护成本，却没有获得 AI Native 的灵活性收益。

**第四轮评审建议聚焦**：
1. P0-1/P0-2/P0-3 是否解决？（stage-dependencies 从"阶段定义"改为"能力注册"？Prompt 改为 Goal 声明式？）
2. P1-2 优先级链是否闭环？（Orchestrator 自评 vs Python gate 冲突时怎么办？）
3. P1-3 Judge 独立性是否解决？（Judge 视角是否与 Orchestrator 差异化？）

**如果决策者接受"混合架构"定位**（即放弃"全 LLM 控制"的 AI Native 纯度要求），则 P0 可降级为 P1，方案可在修复 P1 后进入实施。但这需要忠礼明确确认。

---

*评审人：AI Native 工程师 | 2026-06-25*
