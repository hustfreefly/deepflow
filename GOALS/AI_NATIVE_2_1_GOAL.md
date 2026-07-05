# DeepFlow 2.1.0 Goal — AI Native 多 Agent 协作平台

> **Goal 版本**: B — 三域联动版（Full-Cross-Domain）  
> **目标状态**: 把 DeepFlow 从"流程可以跑通"升级为"极高质量、可验证、可审计、可持续运转的多 Agent 协作平台"  
> **生效日期**: 2026-07-06  
> **Owner**: 姬忠礼 + Hermes (PM/Architect) + Codex CLI (Implementation)  
> **AI Native 原则**: LLM 做判断，代码做格式，人定方向。硬编码语义判断 = 不是 AI Native。

---

## 一、北极星指标（North Star）

| 维度 | 当前 | 2.1.0 目标 | 验证方式 |
|------|------|-----------|---------|
| 测试基线 | 455 passed / 21 failed / 5 errors / 46 skipped | 全绿（100% pass） | `pytest -q` |
| 单域测试覆盖 | spec_pro 无测试；solution_pro 11；ship_pro 1；research_pro 7；loop_engine 0 | spec_pro ≥ 20；solution_pro ≥ 20；ship_pro ≥ 10；research_pro ≥ 10；loop_engine ≥ 5 | 测试文件 + collect-only |
| AI Native 三层 Gate | 多数域只有 L1 代码检查 | 每个域都有 L1（代码）+ L2（LLM Judge）+ L3（合并决策） | 代码审查 + 测试 |
| 独立 Judge 多视角 | 单视角（Planner 自己评） | 判断类任务 ≥ 2 独立 Agent 视角 | prompt / spawn 记录 |
| 跨域契约一致性 | 无统一 schema | spec → solution → ship REQ-ID 全程可追溯 | 端到端测试 |
| 调度可持续性 | loop_engine 33 行空壳 | 可监控 blackboard、触发 Agent、处理超时/失败 | loop_engine 测试 + E2E |

---

## 二、成功标准（Success Criteria）

### SC-1: 测试基线 100% 通过
- 修复当前 `pytest` 中的 21 failed + 5 errors。
- 隔离或修复外部项目 `projects/resumefit/` 的测试失败。
- 修复 `tests/diagnostics/test_validation.py` 的 `ModuleNotFoundError`。
- 修复 `tests/unit/test_spec_pro_regressions.py` 的状态断言失败。

### SC-2: AI Native 三层 Gate 落地
- 每个 Domain 必须显式定义：
  - **L1 代码 Gate**: Schema 验证、文件存在、ID 引用、拓扑无环、TBD/FIXME 检测。
  - **L2 LLM-as-Judge Gate**: 独立 spawn 的 Agent 做语义判断（研究利用、Finding 决策、信息守恒、架构原则对齐）。
  - **L3 合并决策**: 综合 L1 + L2 输出 PASS / CONDITIONAL / FAIL，并附带证据。
- 禁止硬编码语义判断：
  - 禁止 `keyword in text` 判断研究是否被利用。
  - 禁止 `if source == "devil_advocate": decision = "adopted"` 这类代码赋值决策。
  - 禁止 if-else 状态机跳转替代 LLM 判断。

### SC-3: 跨域契约一致性
- `spec_pro` 输出 `LivingSpec` 必须包含 `requirement_index`（REQ-ID + 优先级 + 来源）。
- `solution_pro` 输入必须消费 `LivingSpec` 的 `requirement_index`。
- `solution_pro` 输出 `FinalSolution` 必须包含 `covered_req_ids` 和 `unverified_assumptions`。
- `ship_pro` 输入必须消费 `FinalSolution` 并生成 `WorkPackage` 级别的 `traced_req_ids`。
- 所有跨域数据传递必须通过 Blackboard 文件路径约定 + Pydantic schema 验证。

### SC-4: 独立 Judge 多视角
- 每个需要判断的环节（研究利用、Finding 决策、Worker 拆分、WP 可执行性、ShipPackage 一致性）必须至少 2 个独立 Agent 视角。
- Judge 与 Executor 不能同 prompt / 同 session / 同模型配置（理想情况下用不同模型）。
- Judge 输出必须有 `verdict` + `evidence` + `reasoning`。

### SC-5: Loop Engine 可运转
- `domains/loop_engine` 实现完整调度循环：
  - 监控 blackboard 状态（文件/事件驱动）。
  - 根据当前状态决定下一步 Agent。
  - 处理 Agent 超时、失败、重试。
  - 收敛到最终产物或报告失败。
- 有 5+ 个测试覆盖状态机、超时、失败恢复、正常收敛。

### SC-6: 可观测性
- 每次 Agent 调用记录：task 摘要、输入文件、输出文件、耗时、token、判定结果。
- 失败 session 能自动导出诊断包（日志 + 状态 + 输入 + 输出）。
- 提供 `scripts/audit/run_goal_health_check.py` 一键检查 Goal 达成度。

---

## 三、三域拆解（What & Why）

### 3.1 `spec_pro` — 需求澄清引擎

**现状问题**
- 状态机跳转（`asking` vs `confirming`）由硬编码规则驱动，回归测试失败。
- 没有独立 Judge 判断"本轮问题是否获得新信息""是否还有关键歧义"。
- LivingSpec 输出缺少置信度和未确认假设。

**2.1.0 目标**
- 每轮对话后 spawn **Clarification Judge**：判断本轮是否获得新信息、是否还有歧义。
- 状态机由 Judge 输出驱动，代码只做状态持久化。
- LivingSpec 输出增加：
  - `confidence: float` — 整体置信度。
  - `unverified_assumptions: list[str]` — 未确认假设。
  - `requirement_index: list[dict]` — REQ-ID、描述、优先级、来源 section。

**测试目标**: 新增 20+ tests，覆盖对话状态机、LivingSpec schema、Judge 输出格式。

---

### 3.2 `solution_pro` — 方案设计引擎

**现状问题**
- Fix 1（研究利用追踪）用 `keyword in text` 硬编码。
- Fix 4（Finding Ledger）decision 字段由代码赋值。
- Gate B 语义检查大量用代码实现，缺少独立 LLM Judge。
- Convergence Layer 同时做执行和评估，单视角盲区。

**2.1.0 目标**
- 引入 **三层 Gate 架构**（详见 `IMPROVEMENT_PLAN_V3_AI_NATIVE.md`）。
- 新增独立 Judge：
  - **Research Utilization Judge**: "Expert Finding 的核心洞察是否被方案实质性吸收？"
  - **Finding Decision Judge**: "Fix Plan 是否真正解决了 Finding 的根因？"
  - **Information Conservation Judge**: "从 frozen_spec 到 final_solution，信息是否语义丢失？"
- `ConvergenceLayer` 只做 L1 + L3，L2 全部独立 spawn。
- 输出 `FinalSolution` 必须包含：
  - `covered_req_ids`, `rejected_req_ids`, `unverified_assumptions`, `downstream_risks`。

**测试目标**: 新增 20+ tests，覆盖 Gate 判定、Judge prompt 输出、Convergence schema、跨域输入消费。

---

### 3.3 `ship_pro` — 交付包生成引擎

**现状问题**
- Worker 拆分由 LLM 设计，但拆分合理性没有独立 Judge。
- Work Package 之间依赖图由代码拓扑排序，没有 LLM 判断依赖是否合理。
- 缺少 Solution Pro → Ship Pro 的语义守恒验证。
- Consolidator 是单视角。

**2.1.0 目标**
- 新增三层 Judge：
  - **Plan Judge**: 判断 Worker 拆分是否覆盖所有方案模块、依赖是否合理。
  - **Worker Judge**: 判断每个 WP 是否包含足够上下文、是否可执行。
  - **Integration Judge**: 判断合并后的 ShipPackage 是否语义一致、无冲突。
- 新增 **Semantic Conservation Gate**: 对比 `FinalSolution` 和 `ShipPackage`，确保 REQ-ID 覆盖。
- 输出 `ShipPackage` 包含：
  - `dependency_graph`, `work_packages`, `traced_req_ids`, `risk_notes`。

**测试目标**: 新增 10+ tests，覆盖 Plan/Worker/Integration Judge、依赖图、语义守恒。

---

### 3.4 `research_pro` — 深度研究引擎

**现状问题**
- 来源是否真正回答研究问题没有独立 Judge。
- 引用是否支持主张只有可达性检查，没有语义判断。
- 输出缺少核心洞察提取和相关性评分。

**2.1.0 目标**
- 新增 **Research Judge**: 判断每个来源是否回答了研究问题。
- 新增 **Citation Judge**: 判断引用是否支持对应主张。
- 输出结构增加：
  - `key_insights: list[dict]` — insight + 来源 + 置信度。
  - `confidence: float` — 整体研究置信度。
  - `gaps: list[str]` — 未覆盖的研究问题。

**测试目标**: 新增 5+ tests，覆盖 Judge 输出、key_insights 提取、引用支持判断。

---

### 3.5 `loop_engine` — 调度循环

**现状问题**
- 仅 1 文件 33 行，几乎空壳。
- 没有状态机、没有超时处理、没有失败恢复。

**2.1.0 目标**
- 实现 `LoopEngine`：
  - 监听 blackboard 文件事件或轮询状态文件。
  - 根据状态决定下一步：spawn 哪个 Agent、传什么参数、超时多久。
  - 处理 Agent 失败：重试、降级、或暂停等待用户。
  - 最终状态：收敛完成 / 失败 / 需要用户输入。
- 提供配置文件：`loop_engine/config/default.yaml`。

**测试目标**: 新增 5+ tests，覆盖状态机、超时、失败恢复、正常收敛。

---

### 3.6 `core` — 跨域基础设施

**2.1.0 目标**
- 统一 Blackboard schema 和路径约定：`{blackboard_id}/data/`, `{blackboard_id}/logs/`, `{blackboard_id}/diagnostics/`。
- 契约笼子（`core/cage`）覆盖所有域入口：输入 schema、输出 schema、必需字段、失败降级。
- 跨域 REQ-ID 追踪：提供 `core/quality/traceability.py` 工具函数。
- 质量门可插拔：每个域的 L1/L2/L3 Gate 统一接口。

**测试目标**: 新增 10+ tests，覆盖 schema 验证、契约笼子、REQ-ID 追踪。

---

## 四、Non-Goals

- 不新增新 Domain（如 `eval_pro`、`doc_pro`）。
- 不替换底层模型（保持当前默认模型，但 Judge 可配置不同模型）。
- 不重构外部项目 `projects/resumefit/`（除非它污染测试基线，则隔离）。
- 不做 UI/CLI 大改动（仅增加诊断脚本和日志）。

---

## 五、关键风险与应对

| 风险 | 严重度 | 应对 |
|------|--------|------|
| LLM-as-Judge 增加 token 成本 | 🟡 | 对 L2 做抽样 + 缓存；只有 CONDITIONAL 才触全量 Judge；记录成本 per session。 |
| 硬编码路径多，重构引入回归 | 🔴 | 先修复测试基线；每改一个硬编码点，先写回归测试；用 Codex CLI 批量修改 + 验证。 |
| Judge prompt 反复调优 | 🟡 | 用 golden case 固化 Judge 期望输出；prompt 版本化。 |
| 跨域 schema 不一致 | 🔴 | 先定义契约 schema 再改代码；用 Pydantic 强制验证。 |
| 多 Agent 并行调试困难 | 🟡 | 增加可观测日志；每个 Agent 调用留痕。 |

---

## 六、里程碑 & 时间规划

| 周 | 主题 | 可交付验证 |
|----|------|-----------|
| **Week 1** | 测试基线 + 契约 schema | `pytest -q` 全绿；跨域 schema 文档化；新增契约笼子。 |
| **Week 2** | spec_pro + research_pro 的 LLM-as-Judge | 新增 spec_pro 20 tests、research_pro 5 tests；Judge 独立 spawn。 |
| **Week 3** | solution_pro 三层 Gate + ship_pro Judge | 替换 Fix 1/4 硬编码；Convergence 三层 Gate；新增 solution 20 tests、ship 10 tests。 |
| **Week 4** | loop_engine + 全链路 E2E + 可观测性 | loop_engine 5 tests；E2E 三域跑通；诊断脚本一键健康检查。 |

---

## 七、执行原则（来自 AGENTS.md & USER.md）

1. **Hermes = PM/Architect**，Codex CLI = 实现。重大问题 Hermes 决策，批量修改由 Codex 执行。
2. **只查原因，不修改文件**：Week 1 先做诊断报告，用户说 "stop checking" 或 "那你改吧" 才进入修复。
3. **Goal-Driven**：每个改动必须有可验证的测试或检查。
4. **系统修复 > 补丁**：先找已设计但未部署的方案，没有再补丁 + 记录根因。
5. **能 spawn 就 spawn**：判断类任务必须多 Agent 独立视角。

---

*这个 Goal 是 DeepFlow 2.1.0 的北极星。任何后续任务开始前，先读这个文件。*
