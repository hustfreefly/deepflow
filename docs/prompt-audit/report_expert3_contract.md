# Expert 3: Prompt 契约与可观测性审计报告

> **审计日期**: 2026-07-29  
> **审计范围**: Solution Pro 的 30 个活跃 prompt 文件 + registry.yaml + 历史 memory 记录  
> **审计方法**: 全量读取 + 交叉引用 + 静态分析 + 历史失败模式提取

---

## 1. 契约笼子分析

### 1.1 约束分类统计

| 类别 | 数量 | 说明 |
|------|------|------|
| **代码强约束** | 12 | Pydantic Schema / raise ValueError / ProcessManager / ModuleLifecycleManager / SingleSourceStateManager |
| **Prompt 建议约束** | 47 | 文本 "MUST" / "🔴" / "禁止" / "必须" 但无代码保障 |
| **伪契约** | 18 | Prompt 中说"必须"但在代码中观察不到任何强制措施 |

### 1.2 代码强约束清单（12 项）

| # | 约束 | 实施位置 | 强制方式 |
|---|------|---------|---------|
| 1 | `write_stage` 接收 dict 不接收 str | `_shared_subagent_rules.md` → `BlackboardManager` | `write_stage` 内部类型检查 |
| 2 | `render_prompt` 模板变量替换 | `core/prompt_utils.py` | `render_prompt()` 函数 |
| 3 | Module 生命周期管理 | `core/process_manager.py` | `ModuleLifecycleManager` 类 |
| 4 | `try_acquire_run` 防重复启动 | `core/process_manager.py` | `try_acquire_run()` 返回 `already_running` |
| 5 | `wait_for` / `wait_for_all` 文件轮询 | `core/process_manager.py` | `ProcessManager` 类 |
| 6 | `SingleSourceStateManager.is_module_completed()` | `core/process_manager.py` | 读取 `.runs/{module}.run.json` |
| 7 | `BlackboardManager.resolve_path()` 路径验证 | `core/blackboard/` | `PathManager` 安全验证 |
| 8 | `mark_completed` 通知上游 | `core/process_manager.py` | `ModuleLifecycleManager.mark_completed()` |
| 9 | `heartbeat` 存活信号 | `core/process_manager.py` | `ModuleLifecycleManager.heartbeat()` |
| 10 | 模块配置 (files/sizes/timeout) | orchestrator.md 内嵌 Python 代码 | `MODULE_CONFIG` dict + `wait_for` 参数化 |
| 11 | Schema 验证（planning_convergence/research_digest） | `core/schemas.py` | Pydantic 模型 |
| 12 | 信息守恒检查 | `core/information_conservation.py` | 确定性代码验证 |

### 1.3 伪契约清单（18 项 — Prompt 声称"必须"但无代码保障）

| # | 伪契约内容 | 位置 | 风险 |
|---|-----------|------|------|
| 1 | "🔴 禁止在步骤之间生成文字" | orchestrator.md:38 | 🔴 LLM 本能会生成文字 |
| 2 | "🔴 禁止在步骤之间 yield" | orchestrator.md:39 | 🔴 历史事故已证明不可靠 |
| 3 | "🔴 禁止等待 completion event" | orchestrator.md:40 | 🔴 LLM 本能会等待 |
| 4 | "next exec must happen immediately" | orchestrator.md:46-48 | 🔴 无代码级状态机锁 |
| 5 | "Completion event 是系统通知，不是控制信号" | orchestrator.md:54 | 🟡 依赖 LLM 理解 |
| 6 | "🔴 生存铁律：收到任何完成事件 → 第一个 action 必须是 exec 验证" | planning_module.md:14 | 🔴 历史事故证明不可靠 |
| 7 | "MUST 约束不可妥协" | _shared_subagent_rules.md:3 | 🟡 无代码级 MUST 约束提取器 |
| 8 | "semantic tasks use LLM, deterministic enumeration uses Python" | _shared_subagent_rules.md:4 | 🟡 无合规检查 |
| 9 | "不修改上游输出" | _shared_subagent_rules.md:5 | 🟡 无写入保护 |
| 10 | "不能 web_search" | _shared_subagent_rules.md:7 | 🟡 无工具调用审计 |
| 11 | "声称 ≠ 完成，证据 = 完成" | _shared_subagent_rules.md:1 | 🔴 纯文本约定 |
| 12 | "只写指定 stage" | _shared_subagent_rules.md:2 | 🟡 无写入范围限制 |
| 13 | "edit 前必须 read" | _shared_subagent_rules.md:87 | 🟡 无强制 |
| 14 | "中文路径必须用引号包裹" | _shared_subagent_rules.md:93 | 🟡 无预处理检查 |
| 15 | "Research coverage_map 必须包含所有 45 条约束" | research_module.md:601 | 🔴 无代码验证 |
| 16 | "Summary coverage_map 每个 UC-xxx 必须有对应章节" | summary_module.md:601 | 🔴 无代码验证 |
| 17 | "Harness FAIL 信号显式传递给域级 adversarial reviewer" | summary_module.md:385 | 🟡 依赖文件写入，无确认机制 |
| 18 | "pulse agent 绝不 wait/yield" | solution_pulse.md:84 | 🔴 与 orchestrator 同类型风险 |

### 1.4 建议：应从 Prompt 升级到代码的约束（P0）

| 优先级 | 约束 | 升级方案 |
|--------|------|---------|
| **P0** | 禁止在步骤间生成文字/yield | 在 Orchestrator 的 exec 脚本中嵌入状态机锁，`_OK` 信号后自动触发下一个 exec，不依赖 LLM 判断 |
| **P0** | 收到 completion event 后的行为 | 在 `ModuleLifecycleManager` 中内置 "dedup by run_id" 逻辑，LLM 只需调用 `lifecycle.handle_completion_event()` |
| **P0** | 信息守恒：coverage_map 完整性 | 在 `post_validator.py` 中添加 `verify_coverage_completeness()` 函数，确定性检查 |
| **P0** | 禁止重复 spawn | 在 `try_acquire_run` 中加强防重复逻辑，返回 `already_running` 时禁止 spawn |
| **P1** | MUST 约束不可妥协 | 实现 `MustConstraintEnforcer` 类，从 planning_convergence 提取 MUST 约束并逐条验证 |
| **P1** | 不修改上游输出 | 在 `BlackboardManager` 中实现阶段级写入权限白名单 |

---

## 2. 版本管理审计

### 2.1 版本不一致清单

| 文件 | Frontmatter 版本 | Registry 版本 | 差距 | 严重度 |
|------|-----------------|--------------|------|--------|
| `orchestrator.md` | **4.0.0** | 2.0.0 | **2 个 major 版本** | 🔴 |
| `planning_module.md` | **3.3.0** | 2.0.0 | **1 个 major 版本** | 🔴 |
| `research_module.md` | **3.3.0** | 2.0.0 | **1 个 major 版本** | 🔴 |
| `summary_module.md` | **3.3.0** | 2.0.0 | **1 个 major 版本** | 🔴 |
| `ai_native_cognitive_base.md` | **无 version 字段** | 2.0.0 | 缺失 | 🟡 |
| `compliance_checker_base.md` | **无 version 字段** | 2.0.0 | 缺失 | 🟡 |
| `_shared_subagent_rules.md` | **无 version 字段** | **不在 registry 中** | 完全缺失 | 🟡 |
| `solution_pulse.md` | **无 version 字段** | **不在 registry 中** | 完全缺失 | 🟡 |
| `cross_module_consistency_checker.md` | **1.0.0** | **不在 registry 中** | 未注册 | 🟡 |
| `adversarial_quality_reviewer.md` | 未检查 | **不在 registry 中** | 未注册 | 🟡 |

### 2.2 版本号与变更幅度分析

| 文件 | 版本 | 实际变更 | 评估 |
|------|------|---------|------|
| `orchestrator.md` | 3.1.0 → 4.0.0 | 移除 Step 4/5，13→10 状态，390→299 行 | ✅ Major 合理 |
| `planning_module.md` | 3.0.0 → 3.3.0 | 新增生存铁律、Wake Response Protocol、checkpoint resume、心跳协议 | ⚠️ 应为 Minor 但实际变更量大 |
| `research_module.md` | 3.0.0 → 3.3.0 | 新增生存铁律、信息守恒约束、format 验证 | ⚠️ 同上 |
| `summary_module.md` | 3.1.0 → 3.3.0 | 新增 Fix Judge + Harness Check + 9-step 流程 | ⚠️ 同上 |

**发现**: 三个 module prompt 都标注为 3.3.0，但实际的变更量大到可以认为是 minor（3.0 → 3.3），版本号跳跃合理。但 `orchestrator.md` 的 4.0.0 与 registry 的 2.0.0 差距最大，说明 registry 自 2026-07-05 后从未更新过。

### 2.3 共享版本号问题

`planning_module.md`、`research_module.md`、`summary_module.md` 共享版本号 3.3.0，但：
- `summary_module.md` 的 updated 日期为 2026-07-26（早于其他两个的 2026-07-27）
- 三个文件的内容结构完全不同，不是"同步"而是"独立演进"
- 共享版本号容易造成"它们一起变更"的错觉，实际是分别演进

**建议**: 三个模块各自独立维护版本号，或用 `planning/3.3.0`、`research/3.3.0`、`summary/3.3.0` 的命名空间前缀。

---

## 3. 废弃标记审计

### 3.1 _archive 目录内容

| 文件 | 类型 | 状态 |
|------|------|------|
| `devil_advocate.md` | V2.0.0 旧版 Research Agent | 已归档 |
| `gap_analyst.md` | V2.0.0 旧版 Research Agent | 已归档 |
| `reviewqc_module.md` | V2.0.0 旧版审查模块 | 已归档 |
| `harness_legacy/` (10 个文件) | V2.0.0 Harness 体系 | 已归档 |

### 3.2 误用风险评估

**✅ 安全**: `_archive` 中的文件**没有被任何活跃代码引用**（grep 确认）。Orchestrator V4.0 已移除 Step 4 后置验证，不再需要这些 agent。

**🔴 风险**: Registry 中仍有 13 个指向 `_archive` 文件的条目，且**未标记为 deprecated**：

| Registry Key | 指向文件 | 实际状态 |
|-------------|---------|---------|
| `devil_advocate` | `devil_advocate.md` | 在 `_archive/` 中 |
| `gap_analyst` | `gap_analyst.md` | 在 `_archive/` 中 |
| `reviewqc_module` | `reviewqc_module.md` | 在 `_archive/` 中 |
| `auditor_harness` | `auditor_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `consolidator_harness` | `consolidator_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `fixer_harness` | `fixer_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `fixer_expert_harness` | `fixer_expert_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `planner_harness` | `planner_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `researcher_harness` | `researcher_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `reviewer_harness` | `reviewer_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `summarizer_harness` | `summarizer_harness.md` | 在 `_archive/harness_legacy/` 中 |
| `harness_agent` | `harness_agent.md` | 文件不存在 |
| `summary_fix_agent` | `summary_fix_agent.md` | 文件不存在 |

**如果代码通过 registry 查找 prompt 文件，这 13 个条目可能导致 FileNotFoundError。**

### 3.3 幽灵 Prompt（存在但未被任何代码引用）

| 文件 | 状态 | 风险 |
|------|------|------|
| `adversarial_quality_reviewer.md` | 存在但不在 registry 中 | 🟡 被 `pulse.py` 和 `_overview.md` 引用，但 registry 不知情 |
| `cross_module_consistency_checker.md` | 存在但不在 registry 中 | 🟡 被 `pulse.py` 引用，但 registry 不知情 |
| `solution_pulse.md` | 存在但不在 registry 中 | 🟡 被 cron job 直接使用，跳过 registry |
| `_shared_subagent_rules.md` | 存在但不在 registry 中 | 🟡 被所有 module prompt 引用，但 registry 不知情 |
| `ai_native_cognitive_base.md` | 存在，registry 中但 role=unknown | 🟡 角色标记错误 |

### 3.4 幽灵 Registry 条目（Registry 有但文件不存在）

13 个条目（见 3.2 表格中的 `auditor_harness` 到 `summary_fix_agent`），这些文件的物理位置在 `_archive/` 子目录中，但 registry 的 `filename` 字段指向顶层目录。

---

## 4. 可观测性评估

### 4.1 当前状态

| 维度 | 状态 | 详细 |
|------|------|------|
| **Prompt 输入/输出日志** | ❌ 缺失 | 无结构化记录 prompt 的输入参数和输出结果 |
| **版本变更追溯** | ⚠️ 部分 | registry.yaml 有 changelog 但自 2026-07-05 后未更新 |
| **错误追踪到具体 prompt** | ⚠️ 间接 | 通过 blackboard 中的 `.failed` 文件可追踪到模块，但无法追踪到具体 Worker prompt |
| **Prompt 执行耗时** | ⚠️ 部分 | `ProcessManager.wait_for` 记录 `elapsed` 但无中央收集 |
| **Prompt 成功率** | ❌ 缺失 | 无跨 session 的 prompt 成功率统计 |
| **Lifecycle 心跳** | ✅ 存在 | `ModuleLifecycleManager.heartbeat()` 和 `pulse_cli` 提供存活检测 |

### 4.2 改进建议

| 优先级 | 改进项 | 方案 |
|--------|--------|------|
| **P0** | Prompt 输入/输出日志 | 在 `render_prompt` 中记录 `{prompt_id, session_id, variables, timestamp}`；Worker 完成后记录 `{output_size, elapsed, status}` |
| **P0** | 版本变更自动同步 | CI hook：每次 frontmatter version 变更时自动更新 registry.yaml |
| **P1** | 跨 session 成功率面板 | 在 `pulse_cli` 中添加 `prompt_health` 命令，统计每个 prompt 的 success/fail/timeout 比率 |
| **P1** | 错误溯源增强 | `.failed` 文件增加 `worker_prompt` 字段，记录失败时正在执行的 prompt ID |
| **P2** | 分布式追踪 | 为每个 `sessions_spawn` 添加 trace_id，关联父子 prompt 执行链 |

---

## 5. 历史失败案例提取

### 5.1 失败模式汇总

| # | 日期 | 失败模式 | 根因 | 涉及 Prompt | 是否重复出现 |
|---|------|---------|------|------------|------------|
| 1 | 2026-07-26 | **task 参数截断** | orchestrator prompt (28KB) 塞进 `sessions_spawn task` → 静默截断 | orchestrator.md | ✅ 是（V34/V35/V36 三次） |
| 2 | 2026-07-26 | **planning_convergence MISSING** | Planning Module Agent 重复启动 | planning_module.md | ✅ 是（07-19 也出现过） |
| 3 | 2026-07-26 | **prompt 建议性约束不可靠** | "禁止 yield" 是纯 prompt 文本，LLM 本能会 yield | orchestrator.md | ✅ 是（多次） |
| 4 | 2026-07-26 | **FixFlow 修过头** | 为解决 context 爆炸连改 4 个 prompt + state_manager + post_validator | orchestrator/planning/research/summary | ❌ 新问题 |
| 5 | 2026-07-19 | **E2E 全链路中断** | Planning Module Agent 重复启动 + taskName 唯一性不足 | planning_module.md | ✅ 是（07-26 重复） |
| 6 | 2026-07-12 | **信息降级** | `build_frozen_spec()` 没读 `narrative` 和 `semantic_anchors` | frozen_spec.py (已废弃) | ❌ 已修复 |
| 7 | 2026-07-08 | **P0: 5 幽灵字段** | Pydantic 静默丢弃未知字段 | schemas.py | ❌ 已修复 |
| 8 | 2026-07-05 | **21/42 prompt 是死代码** | prompt 文件存在但未被 Python 代码引用 | 多个 | ❌ 已修复（V4.0 清理） |

### 5.2 重复出现的失败模式

| 模式 | 出现次数 | 涉及 Prompt | 修复状态 |
|------|---------|------------|---------|
| **task 参数截断** | 3 次 | orchestrator.md | ✅ 已修复（最小引用模式） |
| **Planning Module Agent 重复启动** | 2 次 | planning_module.md | ⚠️ 部分修复（R9 checkpoint） |
| **Prompt 建议性约束不可靠** | 多次 | orchestrator.md 为主 | ❌ 未根本解决 |
| **planning_convergence 生成失败** | 2 次 | convergence_planner.md | ⚠️ 部分修复 |

### 5.3 失败模式根因分析

**最危险的模式**: "Prompt 建议性约束不可靠"。这是所有失败中最底层的根因——
- LLM 对 "禁止 yield"、"禁止 poll"、"禁止等待" 等约束的遵循是概率性的
- 当 exec 长时间运行时，LLM 本能会去 poll 状态
- 这些约束在 prompt 中重复强调（🔴 标记），但历史证明它们仍然会被违反

**第二危险的模式**: "task 参数截断"——虽然已通过最小引用模式修复，但它揭示了一个系统性问题：prompt 内容不应通过 `sessions_spawn task` 参数传递，而应通过文件系统。

---

## 6. Prompt Doctor Skill 六维框架设计

### 6.1 框架总览

```
Prompt Doctor 六维检查框架
├── D1: 契约笼子检查 (Contract Cage)
├── D2: 版本管理检查 (Version Management)
├── D3: 废弃标记检查 (Deprecation Audit)
├── D4: 可观测性检查 (Observability)
├── D5: 历史失败关联 (Failure Pattern Match)
└── D6: 结构完整性检查 (Structural Integrity)
```

### 6.2 各维度详细设计

#### D1: 契约笼子检查 (Contract Cage)

**目标**: 区分代码强约束 vs 建议约束，识别伪契约

| 检查项 | 方法 | 自动化 |
|--------|------|--------|
| D1.1 统计 "MUST"/"禁止"/"必须" 出现次数 | 正则扫描 prompt 文本 | ✅ 全自动 |
| D1.2 对每个 MUST 约束，检查是否有对应代码实现 | 代码符号搜索 + 人工判断 | ⚠️ 半自动（AI 辅助判断） |
| D1.3 识别"伪契约"（prompt MUST 但代码无对应） | 交叉引用 prompt constraint ↔ code symbol | ⚠️ 半自动 |
| D1.4 检查约束是否可被静默绕过 | 检查异常处理路径（try/except/pass） | ⚠️ 半自动 |
| D1.5 建议升级清单（P0/P1/P2） | 基于影响分析自动生成 | ✅ 全自动 |

**评分标准**:
- **PASS**: 伪契约 < 5 个，所有 P0 约束有代码保障
- **CONDITIONAL**: 伪契约 5-15 个，部分 P0 约束缺失
- **FAIL**: 伪契约 > 15 个，多个 P0 约束缺失

#### D2: 版本管理检查 (Version Management)

**目标**: 确保版本号一致性、变更幅度合理

| 检查项 | 方法 | 自动化 |
|--------|------|--------|
| D2.1 Frontmatter version vs Registry version 一致性 | 解析 YAML frontmatter + registry.yaml 对比 | ✅ 全自动 |
| D2.2 版本号是否反映变更幅度 | Git diff 分析 + semver 判断 | ⚠️ 半自动 |
| D2.3 是否存在无 version 字段的文件 | 扫描 frontmatter | ✅ 全自动 |
| D2.4 共享版本号是否实际同步 | 比较同一版本号文件的 updated 日期 | ✅ 全自动 |
| D2.5 Registry 最后更新日期 | 检查 registry.yaml 的 `last_updated` | ✅ 全自动 |

**评分标准**:
- **PASS**: 所有文件 frontmatter 与 registry 一致，无缺失 version
- **CONDITIONAL**: 1-3 个不一致，或 registry 超过 14 天未更新
- **FAIL**: > 3 个不一致，或 major 版本差距（如 v2.0.0 vs v4.0.0）

#### D3: 废弃标记检查 (Deprecation Audit)

**目标**: 确保 `_archive` 文件不会被误用，幽灵 prompt 被识别

| 检查项 | 方法 | 自动化 |
|--------|------|--------|
| D3.1 _archive 中文件是否被活跃代码引用 | grep 全项目引用 | ✅ 全自动 |
| D3.2 Registry 中是否有已废弃但未标记为 deprecated 的条目 | 比较 registry 与文件系统位置 | ✅ 全自动 |
| D3.3 幽灵 prompt：文件存在但从未被任何代码引用 | 符号引用分析 | ✅ 全自动 |
| D3.4 幽灵 registry：registry 有但文件不存在 | 文件系统检查 | ✅ 全自动 |
| D3.5 _archive 中文件是否缺少废弃声明 | 扫描 frontmatter status 字段 | ✅ 全自动 |

**评分标准**:
- **PASS**: 0 个幽灵 prompt，0 个未标记废弃条目，0 个误用风险
- **CONDITIONAL**: 1-5 个幽灵/未标记条目
- **FAIL**: > 5 个幽灵/未标记条目，或存在误用风险

#### D4: 可观测性检查 (Observability)

**目标**: 确保 prompt 执行有追踪、有日志、有追溯

| 检查项 | 方法 | 自动化 |
|--------|------|--------|
| D4.1 是否有 prompt I/O 日志记录 | 检查 `render_prompt` 调用点是否有日志 | ⚠️ 半自动 |
| D4.2 错误是否可以追溯到具体 prompt | 检查 `.failed` 文件内容字段 | ⚠️ 半自动 |
| D4.3 是否有 prompt 成功率统计 | 检查是否有指标收集代码 | ⚠️ 半自动 |
| D4.4 版本变更是否有追溯 | 检查 registry changelog 完整性 | ✅ 全自动 |
| D4.5 是否有 prompt 执行耗时记录 | 检查 `ProcessManager.wait_for` 的 elapsed 是否被持久化 | ⚠️ 半自动 |

**评分标准**:
- **PASS**: 4/5 检查项通过
- **CONDITIONAL**: 2-3/5 检查项通过
- **FAIL**: 0-1/5 检查项通过

#### D5: 历史失败关联 (Failure Pattern Match)

**目标**: 检查当前 prompt 是否包含已知失败模式

| 检查项 | 方法 | 自动化 |
|--------|------|--------|
| D5.1 检查 prompt 是否包含 "大文本灌入 task 参数" 模式 | 扫描 `sessions_spawn` 调用中的 task 参数长度 | ✅ 全自动 |
| D5.2 检查是否有 "禁止 yield" 但无代码保障的模式 | 扫描 prompt 中的 "禁止 yield" + 交叉引用代码 | ⚠️ 半自动 |
| D5.3 检查是否缺少 checkpoint/resume 机制 | 扫描 prompt 中是否有 checkpoint 逻辑 | ✅ 全自动 |
| D5.4 检查是否有重复 spawn 风险 | 检查 `try_acquire_run` 调用完整性 | ⚠️ 半自动 |
| D5.5 检查已知失败模式的修复是否已应用到当前版本 | pattern matching 历史修复 ↔ 当前代码 | ⚠️ 半自动 |

**评分标准**:
- **PASS**: 0 个已知失败模式匹配
- **CONDITIONAL**: 1-2 个已知失败模式匹配（低风险）
- **FAIL**: > 2 个已知失败模式匹配，或包含 🔴 级别模式

#### D6: 结构完整性检查 (Structural Integrity)

**目标**: 检查 prompt 文件本身的格式和质量

| 检查项 | 方法 | 自动化 |
|--------|------|--------|
| D6.1 是否有 frontmatter（id/version/component/updated） | YAML 解析 | ✅ 全自动 |
| D6.2 是否有明确的角色定义 | 扫描 `#` 标题 + "你是" 模式 | ✅ 全自动 |
| D6.3 是否有输入/输出 Schema 定义 | 扫描 JSON Schema 或表格 | ⚠️ 半自动 |
| D6.4 是否有执行流程（步骤编号） | 扫描 "Step"/"Phase" 模式 | ✅ 全自动 |
| D6.5 是否有 Fail Fast 机制 | 扫描 "MISSING"/"FAILED" 处理 | ✅ 全自动 |
| D6.6 Prompt 长度是否过大（> 500 行） | 行数统计 | ✅ 全自动 |
| D6.7 是否有 Python 代码注入（exec 代码块） | 扫描 ```python 代码块 | ✅ 全自动 |
| D6.8 变量模板是否完整（`{var}` 是否有对应注入） | 正则提取 `{var}` + 交叉引用 render_prompt 调用 | ⚠️ 半自动 |

**评分标准**:
- **PASS**: 6/8 检查项通过
- **CONDITIONAL**: 4-5/8 检查项通过
- **FAIL**: < 4/8 检查项通过

### 6.3 整体评分标准

| 等级 | 条件 |
|------|------|
| **A** | 全部 6 维度 PASS |
| **B** | 5 维度 PASS，1 维度 CONDITIONAL |
| **C** | 3-4 维度 PASS，其余 CONDITIONAL |
| **D** | 1-2 维度 PASS，或任意维度 FAIL |
| **F** | 全部 FAIL，或存在 🔴 级别安全隐患 |

### 6.4 与 AgentDryRun 的关系

**可以直接扩展**。AgentDryRun 的六维检查（结构/流/边界/契约/数据/信号）与 Prompt Doctor 的六维框架高度互补：

| AgentDryRun 维度 | Prompt Doctor 对应维度 | 关系 |
|-----------------|----------------------|------|
| 结构扫描 | D6 结构完整性 | 直接继承 |
| 流分析 | D1 契约笼子（部分） | 互补 |
| 边界测试 | D6 结构完整性（部分） | 互补 |
| 契约验证 | **D1 契约笼子（核心）** | 深度扩展 |
| 数据流 | D4 可观测性（部分） | 互补 |
| 信号检测 | D5 历史失败关联 | 互补 |

**扩展方式**: 在 AgentDryRun 的 `prompt_audit` 模块中增加一个 `PromptDoctorCheck` 类，调用上述六维检查，输出结构化报告。AgentDryRun 负责"这个 prompt 会不会跑崩"，Prompt Doctor 负责"这个 prompt 的契约和元数据是否健康"。两者可以合并为一个统一报告。

---

## 7. 核心发现 + 改进建议

### P0（立即修复，可能导致系统故障）

| # | 发现 | 建议 |
|---|------|------|
| 1 | **Registry 与 Frontmatter 版本严重不一致**：orchestrator.md frontmatter v4.0.0 vs registry v2.0.0 | 立即更新 registry.yaml 中所有 solution_pro 条目的 version 字段，或实现自动同步脚本 |
| 2 | **13 个 Registry 条目指向已归档文件**：如果代码通过 registry 查找 prompt 文件会导致 FileNotFoundError | 将这些条目标记为 `status: deprecated` 并将 `filename` 指向正确的 `_archive/` 路径 |
| 3 | **"禁止 yield/禁止生成文字" 是伪契约**：历史事故已证明这些 prompt 约束不可靠 | 在 Orchestrator exec 脚本中嵌入状态机，`_OK` 信号后自动触发下一步，不依赖 LLM 判断 |
| 4 | **信息守恒约束（coverage_map 45 条约束）无代码验证** | 实现 `verify_coverage_completeness()` 确定性检查函数 |

### P1（本周修复，提升可靠性）

| # | 发现 | 建议 |
|---|------|------|
| 5 | **5 个 prompt 文件不在 registry 中**：`_shared_subagent_rules.md`、`solution_pulse.md`、`cross_module_consistency_checker.md`、`adversarial_quality_reviewer.md`、`README.md` | 在 registry.yaml 中注册这些文件 |
| 6 | **3 个 prompt 文件缺少 version 字段**：`ai_native_cognitive_base.md`、`compliance_checker_base.md`、`_shared_subagent_rules.md` | 在 frontmatter 中添加 version 字段 |
| 7 | **Prompt I/O 日志缺失** | 在 `render_prompt` 中增加日志记录，写 `stages/.prompt_log.jsonl` |
| 8 | **Registry 自 2026-07-05 后未更新**（24 天） | 建立 CI hook：frontmatter 变更时自动更新 registry |
| 9 | **三个模块共享版本号 3.3.0 但独立演进** | 每个模块独立维护版本号，或使用命名空间前缀 |

### P2（本月修复，提升长期可维护性）

| # | 发现 | 建议 |
|---|------|------|
| 10 | **无 cross-session prompt 成功率统计** | 在 `pulse_cli` 中添加 `prompt_health` 子命令 |
| 11 | **错误溯源不精确**：`.failed` 文件缺少 `worker_prompt` 字段 | 在失败标记中增加触发失败的 prompt ID |
| 12 | **`summary_module.md` 为 838 行**（最大 prompt） | 考虑拆分为独立 Worker prompt 文件，类似 Summary 已做的 9 步拆分 |
| 13 | **`_archive` 中文件缺少显式废弃声明** | 在 `_archive/` 中加 `README.md` 说明废弃原因和替代方案 |
| 14 | **Prompt Doctor Skill 应作为 AgentDryRun 的扩展模块** | 在 AgentDryRun 中增加 `prompt_doctor` 检查维度 |

---

## 8. 整体评分

### 评分: **D (68/100)**

| 维度 | 评分 | 理由 |
|------|------|------|
| 契约笼子 | **D** | 47 个建议约束 vs 12 个代码强约束（4:1 比例），18 个伪契约，多个 P0 约束无代码保障 |
| 版本管理 | **F** | Registry 与 Frontmatter 严重不一致（v2.0.0 vs v4.0.0），registry 24 天未更新，3 个文件缺失 version |
| 废弃标记 | **D** | 13 个 registry 条目指向已归档文件且未标记 deprecated，5 个幽灵 prompt |
| 可观测性 | **D** | 无 prompt I/O 日志，无成功率统计，错误无法精确追溯到具体 prompt |
| 历史失败 | **C** | 已知失败模式已部分修复，但根因（伪契约）未解决，task 截断模式已修复 |
| 结构完整性 | **B** | 大部分 prompt 有完整的 frontmatter 和流程定义，少数文件缺失 version 字段 |

**核心问题**: Solution Pro 的 Prompt 系统在契约层存在严重的"信任落差"——**prompt 文本声称了 47 条"必须"约束，但只有 12 条有代码级保障**。在 07-26 的三次事故中，正是这种落差导致了系统故障（"禁止 yield" 被 LLM 本能地违反）。同时，registry.yaml 的版本管理严重滞后，已成为"僵尸数据"。

**最大风险**: 如果未来有新开发者或新 Agent 通过 registry.yaml 查找 prompt 文件，13 个指向已归档文件的条目将导致 FileNotFoundError，且无任何告警机制。

**改进路径**: P0 → P1 → P2 三步走，预计 2 周完成全部 P0/P1 修复，1 个月完成 Prompt Doctor Skill 集成。

---

*报告生成: 2026-07-29 03:50 GMT+8 | 审计工具: Expert 3 Contract Auditor | 范围: 30 prompts + registry.yaml + 8 memory files*