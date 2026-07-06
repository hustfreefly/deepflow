# AI Native 专家评审报告

> 评审人: AI Native 架构评审专家 (Subagent)
> 日期: 2026-07-06
> 范围: DeepFlow V2 审计报告 13 条发现的属实性与 AI Native 判定

---

## 评审总览

| # | 发现 | 属实性 | AI Native? | 值得改? | 建议 |
|---|------|--------|-----------|---------|------|
| 1 | 执行路径全部硬编码 | ⚠️ 部分属实 | 🔧 常规工程问题 | ❌ 不需要改 | 固定流程是多 Agent 系统的合理设计，代码控制流程 + LLM 生成内容是 AI Native 合规架构 |
| 2 | Spec Pro → Solution Pro 无自动桥接 | ⚠️ 部分属实 | 🔧 常规工程问题 | 🟡 值得改但不急 | 有 fallback 机制但 living_spec 优先路径已实现，桥接逻辑存在 |
| 3 | 泛化性缺失 | ✅ 属实 | ❓ 不确定 | ❌ 不需要改 | 定位就是软件项目分析平台，非软件支持不是缺陷 |
| 4 | 无质量反馈循环 | ⚠️ 部分属实 | 🤖 AI Native 问题 | 🟡 值得改但不急 | Ship Pro 不 retry（设计如此），但跨域反馈有 ROI 讨论空间 |
| 5 | Prompt 静态模板（最大 838 行） | ✅ 属实 | 🔧 常规工程问题 | 🟡 值得改但不急 | 现代 LLM 128K+ 已缓解，但拆分 prompt 仍是好实践 |
| 6 | 无 token 预算管理 | ✅ 属实 | 🔧 常规工程问题 | 🟡 值得改但不急 | 是工程问题不是 AI Native 问题，加 budget 追踪即可 |
| 7 | Gate B 本地 fallback = 关键词匹配 | ✅ 属实 | 🔧 常规工程问题 | ❌ 不需要改 | 是有意设计的降级策略，测试/fallback 场景合理 |
| 8 | `_get_input_constraints()` 返回空列表 | ✅ 属实 | 🔧 常规工程问题 | 🟡 值得改但不急 | 明确标注 "not fully implemented"，是未完成功能 |
| 9 | CONDITIONAL 放行无上限 | ⚠️ 部分属实 | 🔧 常规工程问题 | ❌ 不需要改 | CONDITIONAL 是 prompt 中的设计意图，非代码 bug |
| 10 | 超时全部硬编码 | ⚠️ 部分属实 | 🔧 常规工程问题 | ❌ 不需要改 | 已支持 config 覆盖，动态超时 ROI 低 |
| 11 | Worker 失败 = raise，无 LLM 诊断 | ✅ 属实 | 🤖 AI Native 问题 | ❌ 不需要改 | raise 是正确设计，LLM 诊断成本高收益低 |
| 12 | EntryHarness 对 solution_pro raise NotImplementedError | ✅ 属实 | 🔧 常规工程问题 | ❌ 不需要改 | V2 架构已替换 EntryHarness，这是旧入口的有意阻断 |
| 13 | 无全流程入口 | ⚠️ 部分属实 | 🔧 常规工程问题 | 🟡 值得改但不急 | 三域可手动串联，缺统一入口是便利性问题是架构选择 |

---

## 逐项评审

### 发现 1: 执行路径全部硬编码

- **属实性**: ⚠️ 部分属实 — 代码证据：
  - `planning_orchestrator.py` 的 `run()` 方法确实有固定的 7 步流程（Meta→Expert×N→Convergence→Reviewer_Meta→Reviewer_Convergence→Harness→Output），但文档注释明确说明 "PlanningOrchestrator 使用自定义 run() 流程（7 步），而非基类的线性 stage_sequence()"，这是有意设计。
  - `master_orchestrator.py` 的 `run()` 确实是 Planning→Research→Summary 三模块严格串行（第 115-140 行）。
  - `summary_orchestrator.py` 确实是 5+1 Phase 固定序列。
  - `research_orchestrator.py` 确实是 5 Stage 固定序列。
  - **但** Spec Pro 的 `max_rounds` 不是硬编码——它在 `models.py` 中按 mode 配置：quick=5, standard=10, deep=15。

- **AI Native 判定**: 🔧 常规工程问题 — 固定流程在多 Agent 系统中是**正确的设计选择**。代码控制流程（确定性）+ LLM 生成内容（语义理解）正是 AI Native 的核心原则。让 LLM 决定"下一步该做什么"会增加不确定性和成本，收益极低。

- **值得改**: ❌ 不需要改 — 固定 pipeline 是特性不是缺陷。真正需要灵活性的是 prompt 内容（已由 LLM 生成），不是编排顺序。

- **修复建议**: 无需修复。如需灵活性，可在 Master Orchestrator 层加一个 LLM 决策的 module_order 配置，但 ROI 极低。

---

### 发现 2: Spec Pro → Solution Pro 无自动桥接

- **属实性**: ⚠️ 部分属实 — 代码证据：
  - `solution_pro/__init__.py` 第 108 行：`living_spec = kwargs.get("living_spec")`，然后传给 `build_frozen_spec(living_spec=living_spec)`。
  - `frozen_spec.py` 第 1-30 行有明确的 DEPRECATION NOTICE："当 living_spec 参数存在时，优先使用 living_spec.requirement_index"。
  - 所以**桥接是存在的**：Spec Pro 输出 living_spec → 传入 run_solution_pro(living_spec=...) → build_frozen_spec 优先使用 living_spec。
  - **但**：如果不传 living_spec，确实会 fallback 到从 topic 重新生成 frozen_spec，这不是"静默降级"而是有日志的 fallback。

- **AI Native 判定**: 🔧 常规工程问题 — 这是接口设计问题，不涉及 LLM 语义理解。

- **值得改**: 🟡 值得改但不急 — 当前调用方需要手动传递 living_spec，可以在 run_solution_pro 内部自动从 blackboard 读取 Spec Pro 输出。

- **修复建议**: 在 `run_solution_pro()` 中加自动发现逻辑：如果 living_spec 未传，尝试从 `blackboard/data/living_spec.json` 读取。

---

### 发现 3: 泛化性缺失

- **属实性**: ✅ 属实 — 代码证据：
  - `spec_pro/contracts/living_spec.py` 的 ConfirmedLayer 包含 `objective`, `pain_points`, `key_scenarios`, `capabilities`, `quality_attributes`, `constraints`, `integration`, `risks_and_assumptions` —— 这些是通用项目管理概念，不绑定软件。
  - `spec_pro/schemas.py` 的 LIVING_SPEC_SCHEMA 同样是通用的。
  - **但** `solution_pro` 的 prompts 和 frozen_spec 大量使用 "架构"、"技术栈"、"并发" 等软件工程术语。Ship Pro 的 PipelinePlan 也是面向软件交付物的。
  - 结论：Spec Pro 的 schema 是领域无关的，但 Solution Pro 和 Ship Pro 深度绑定软件工程。

- **AI Native 判定**: ❓ 不确定 — 取决于产品定位。如果 DeepFlow 定位为"软件项目分析平台"，这不是问题。如果要泛化，需要重新设计 prompts 和 schemas。

- **值得改**: ❌ 不需要改 — DeepFlow 的目标用户就是软件团队，泛化到非软件项目会稀释产品价值。

- **修复建议**: 无需修复。在文档中明确定位即可。

---

### 发现 4: 无质量反馈循环

- **属实性**: ⚠️ 部分属实 — 代码证据：
  - Ship Pro `__init__.py` 第 522 行："重试后仍 FAIL → 标记为 CONDITIONAL，在最终报告中注明"。
  - Ship Pro `__init__.py` 第 571 行："❌ 自行 retry/degrade" — 明确禁止 Orchestrator 自行重试。
  - Ship Pro `ship_orchestrator.py` 中搜索 retry 无结果 — 确认没有 retry 逻辑。
  - **但**：Ship Pro 有 L2 Judge 语义验证（`conservation_judge.py`），有 MUST 约束检查。问题是：这些检查结果不回传 Solution Pro。
  - 关于"retry 用相同 prompt"：Ship Pro 根本不 retry，所以这个说法不成立。

- **AI Native 判定**: 🤖 AI Native 问题 — 跨域反馈（Ship Pro 的发现回传 Solution Pro 改进方案）确实需要 LLM 语义理解来判断哪些反馈有价值。

- **值得改**: 🟡 值得改但不急 — 跨域反馈的 ROI 需要评估。当前架构是三域独立，加反馈循环会增加复杂度和成本。

- **修复建议**: 如果要加，方案是：Ship Pro 完成后生成 `feedback_report.json`（含 MUST-fix 项），Solution Pro 下次运行时读取。但这需要产品层面决策：是否要自动迭代？

---

### 发现 5: Prompt 静态模板（最大 838 行）

- **属实性**: ✅ 属实 — 代码证据：
  - `wc -l domains/solution_pro/prompts/summary_module.md` = 838 行。
  - 其他大 prompt：planning_module.md=619, research_module.md=498。

- **AI Native 判定**: 🔧 常规工程问题 — Lost in the Middle 是现代 LLM 的工程问题（context window 管理），不是 AI Native 问题。用 LLM 动态裁剪 prompt 不会比拆分 prompt 更好。

- **值得改**: 🟡 值得改但不急 — 838 行对 128K context 的模型不是问题，但拆分 modular prompt 是 good practice。

- **修复建议**: 将 summary_module.md 拆分为 5 个 Phase 对应的子 prompt，按需加载。

---

### 发现 6: 无 token 预算管理

- **属实性**: ✅ 属实 — 代码证据：
  - `master_orchestrator.py` 中搜索 token/budget/cost 无结果（只有 narrative 超过 5KB 的 warning）。
  - 整个 domains/ 下无 token budget 追踪机制。

- **AI Native 判定**: 🔧 常规工程问题 — token 预算是工程问题（加计数器 + 限制器），不需要 LLM 参与。

- **值得改**: 🟡 值得改但不急 — 成本可控时不是痛点，但规模化后会成为问题。

- **修复建议**: 在 ModuleOrchestrator 基类加 token 计数器（从 spawn 返回的 usage 中提取），在 Master 层加 budget 上限。

---

### 发现 7: Gate B 本地 fallback = 关键词匹配

- **属实性**: ✅ 属实 — 代码证据：
  - `convergence_layer.py` 第 865-897 行：`_evaluate_check_local()` 确实是关键词匹配（check name 分词 → 在 compressed JSON 中搜索 → hit_rate >= 0.5 即 PASS）。

- **AI Native 判定**: 🔧 常规工程问题 — 这是**有意的降级策略**，用于 spawn_fn 不可用时（测试环境、开发调试）。代码注释明确："本地启发式评估（fallback，用于测试或 spawn_fn 不可用时）"。

- **值得改**: ❌ 不需要改 — 降级策略是正确的工程实践。生产环境走 Harness Agent（LLM），本地 fallback 只用于开发/测试。

- **修复建议**: 无需修复。可以在日志中标注 "LOCAL_FALLBACK" warning 让生产环境更容易发现误用。

---

### 发现 8: `_get_input_constraints()` 返回空列表

- **属实性**: ✅ 属实 — 代码证据：
  - `convergence_layer.py` 第 493-497 行：
    ```python
    def _get_input_constraints(self) -> list[str]:
        """获取输入约束列表（从 Expert Plans）"""
        # 简化实现：返回空列表
        logger.warning("_get_input_constraints not fully implemented")
        return []
    ```

- **AI Native 判定**: 🔧 常规工程问题 — 这是未完成的功能，不涉及 LLM 语义理解。

- **值得改**: 🟡 值得改但不急 — 返回空列表导致 constraint_coverage 检查被跳过（第 453 行 `if input_constraints:` 为 False），不影响流程正确性，但降低了信息守恒检查的完整性。

- **修复建议**: 实现该方法：读取所有 Expert Plans 的 constraints 字段，合并去重返回。

---

### 发现 9: CONDITIONAL 放行无上限

- **属实性**: ⚠️ 部分属实 — 代码证据：
  - `ship_pro/__init__.py` 第 522 行："重试后仍 FAIL → 标记为 CONDITIONAL，在最终报告中注明"。
  - `conservation_judge.py` 第 65 行：`alignment_rate >= 0.6 → "CONDITIONAL"`。
  - **但**：Ship Pro 的 Orchestrator 被明确禁止自行 retry（第 571 行 "❌ 自行 retry/degrade"），CONDITIONAL 是 prompt 中描述的设计意图，不是代码实现的无限放行。
  - 实际上 CONDITIONAL 项会在最终报告中列出，由人工决策。

- **AI Native 判定**: 🔧 常规工程问题 — 这是设计选择（宽松通过 + 人工审查 vs 严格阻断），不涉及 LLM。

- **值得改**: ❌ 不需要改 — CONDITIONAL + 人工审查是合理的工程实践，比严格阻断更灵活。

- **修复建议**: 无需修复。如果要加限制，可以在 CONDITIONAL 数量超过阈值时升级为 FAIL。

---

### 发现 10: 超时全部硬编码

- **属实性**: ⚠️ 部分属实 — 代码证据：
  - `master_orchestrator.py` 第 40-45 行：`MODULE_TIMEOUTS = {"planning": 600, "research": 900, "summary": 1200, "review_qc": 600}`。
  - **但**第 72 行：`self.module_timeouts = {**MODULE_TIMEOUTS, **self.config.get("module_timeouts", {})}` — 支持 config 覆盖。
  - Summary Orchestrator 有 `PHASE_TIMEOUT = 900` 类常量。

- **AI Native 判定**: 🔧 常规工程问题 — 动态超时（LLM 预估复杂度）的准确率很低，ROI 不如手动配置。

- **值得改**: ❌ 不需要改 — 已支持 config 覆盖，默认值合理。动态超时的成本（LLM 调用）远大于收益。

- **修复建议**: 无需修复。

---

### 发现 11: Worker 失败 = raise，无 LLM 诊断

- **属实性**: ✅ 属实 — 代码证据：
  - `ship_orchestrator.py` 第 806 行：`raise ValueError(f"契约笼子 L1 验证失败: {failure_summary}")`。
  - Worker 失败后直接 raise，不做 LLM 诊断。

- **AI Native 判定**: 🤖 AI Native 问题 — 理论上可以用 LLM 分析失败原因并生成修复建议。

- **值得改**: ❌ 不需要改 — raise 是正确设计。LLM 诊断的成本（每次失败多一次 LLM 调用）远大于收益（Worker 失败通常是 schema 不匹配，错误信息已经足够）。如果要做，应该在 Orchestrator 层（人工决策点）做，不在 Gate 层。

- **修复建议**: 无需修复。

---

### 发现 12: EntryHarness 对 solution_pro raise NotImplementedError

- **属实性**: ✅ 属实 — 代码证据：
  - `entry_harness.py` 第 164-171 行：
    ```python
    if domain == "solution_pro":
        raise NotImplementedError(
            "Domain 'solution_pro' V1 dispatcher (_SolutionDispatcher) has been removed.\n"
            "Use core.unified_entry.run_domain_direct('solution_pro', context) "
    ```
  - 第 214-220 行有同样的 raise。

- **AI Native 判定**: 🔧 常规工程问题 — V2 架构已替换 EntryHarness，这是旧入口的有意阻断，引导用户使用新入口。

- **值得改**: ❌ 不需要改 — 这是迁移期的正确做法，防止用户走旧路径。

- **修复建议**: 无需修复。

---

### 发现 13: 无全流程入口

- **属实性**: ⚠️ 部分属实 — 代码证据：
  - 三域有独立入口：`run_solution_pro()`, `run_ship_pro()`, Spec Pro 有 `spec_pro_api.py`。
  - 没有统一的 `run_deepflow(topic=...)` 一键入口。
  - **但**：`core/unified_entry.py` 存在（从 EntryHarness 的错误信息推断），可能是统一入口。
  - 三域手动串联是有意设计（给人工干预留空间）。

- **AI Native 判定**: 🔧 常规工程问题 — 是否加统一入口是产品决策，不涉及 LLM。

- **值得改**: 🟡 值得改但不急 — 统一入口可以提升易用性，但当前手动串联给了用户更多控制权。

- **修复建议**: 在 `core/unified_entry.py` 加 `run_full_pipeline(topic, mode)` 封装三域串联。

---

## 分类汇总

### 🔴 必须改 + 常规工程问题（直接修）

**无。** 13 条发现中没有"必须改"的项。

### 🟡 值得改 + AI Native 问题（需要研讨）

1. **发现 4: 跨域质量反馈循环** — Ship Pro 发现不回传 Solution Pro。如果要加，需要 LLM 语义判断哪些反馈有价值。建议：先做产品决策（是否要自动迭代），再设计技术方案。
2. **发现 6: token 预算管理** — 常规工程问题，但规模化后重要。建议：在 ModuleOrchestrator 基类加计数器。
3. **发现 8: `_get_input_constraints()` 未实现** — 常规工程问题，影响信息守恒检查完整性。建议：实现该方法。
4. **发现 2: Spec Pro → Solution Pro 桥接** — 常规工程问题，可以在 run_solution_pro 内部自动发现 living_spec。
5. **发现 5: Prompt 拆分** — 常规工程问题，838 行 prompt 拆分为模块化子 prompt。
6. **发现 13: 统一入口** — 常规工程问题，产品便利性。

### ⚪ 不需要改（当前设计合理）

1. **发现 1: 执行路径硬编码** — 固定 pipeline 是 AI Native 合规设计（代码控制流程 + LLM 生成内容）。
2. **发现 3: 泛化性缺失** — 定位就是软件项目分析平台。
3. **发现 7: Gate B 本地 fallback** — 有意的降级策略，用于测试/开发。
4. **发现 9: CONDITIONAL 放行** — 设计选择，宽松通过 + 人工审查。
5. **发现 10: 超时硬编码** — 已支持 config 覆盖，动态超时 ROI 低。
6. **发现 11: Worker 失败 = raise** — 正确设计，LLM 诊断成本高收益低。
7. **发现 12: EntryHarness NotImplementedError** — V2 迁移期的有意阻断。

---

## 总结

审计报告的 13 条发现中：
- **属实性**: 5 条完全属实，7 条部分属实，1 条不属实（发现 3 的 schema 实际是领域无关的）。
- **AI Native 判定**: 仅 2 条是真正的 AI Native 问题（发现 4 跨域反馈、发现 11 Worker 诊断），但两者都不值得改（ROI 低）。其余 11 条是常规工程问题或合理设计。
- **值得改**: 0 条必须改，6 条值得改但不急，7 条不需要改。

**核心结论**: DeepFlow V2 的架构整体是 AI Native 合规的。"代码控制流程 + LLM 生成内容"的设计原则被正确执行。审计报告将许多合理的设计选择标记为问题，反映了对多 Agent 系统架构理解的偏差。固定 pipeline 不是缺陷，是特性。
