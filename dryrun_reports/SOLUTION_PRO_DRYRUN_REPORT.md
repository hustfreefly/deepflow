# Agent DryRun 报告 — Solution Pro 2.0.0

> **执行日期**: 2026-07-06
> **检查范围**: DeepFlow Solution Pro 2.0.0（三模块架构：Planning → Research → ReviewQC）
> **检查方法**: Agent DryRun V3.2 六维体检框架
> **执行耗时**: ~30 分钟（4 个并行子 Agent）

---

## 综合判定: 🔴 NO_GO

**系统存在结构性问题，不建议在没有修复的情况下继续运行 E2E。**

| 维度 | 状态 | 严重程度 | 核心问题 |
|------|------|----------|----------|
| 🔑 Prompt 主线 | 🔴 FAIL | HIGH | 71% 约束仅靠 Prompt 声明；V1/V2 两套 Pipeline 并存 |
| 🔴 人 (Agent 行为) | 🟡 SKIP | — | 未执行 Agent 行为测试（需完整 E2E 验证） |
| 🟡 料 (输入质量) | 🟡 OK | LOW | Prompt 信噪比总体可接受，但 V1 遗留 prompt 拉低质量 |
| 🔵 法 (编排 + 数据流) | 🔴 FAIL | CRITICAL | 2 个 CRITICAL 发现；14 跳中 3 跳断裂 |
| 🟣 环 (外部依赖) | 🟡 OK | LOW | 依赖平台正常，但 knowledge_freshness 有静默降级 |
| ⚫ 系统级 | 🔴 FAIL | HIGH | 契约笼子薄弱；fallback bypass 绕过验证；自评不可信 |

---

## 架构主线（Step 0 输出）

```
Pipeline: Planning → Research → ReviewQC (3 模块，顺序串行)

Planning (Module 1, 600s):
  meta_planner → reviewer_meta(gate) → expert_planners(xN) → 
  convergence_planner → reviewer_convergence(gate) → harness → 
  planning_convergence

Research (Module 2, 900s):
  knowledge_freshness → expert_config → research_experts(xM) → 
  consolidation → digest → research_convergence

ReviewQC (Module 3, 600s):
  fix_loop → harness_check → final_review → review_qc_convergence
  [ABORT → DegradedFinalConvergenceSchema]

关键路径断裂点:
  1. reviewer_meta FAIL → raise ValueError (无降级)
  2. reviewer_convergence FAIL → raise ValueError (无降级)
  3. experts < min_viable → RuntimeError (无降级)
  4. fix_loop ABORT → 降级产出 (唯一降级路径)
```

---

## 🔑 维度 1: Prompt 主线 — 详细发现

### 统计概览

| 指标 | 数值 |
|------|------|
| Prompt 文件总数 | 41 个 |
| 总行数 | 9,547 行 |
| 约束总数 | 85 条（47 MUST + 38 MUST NOT/NEVER/禁止） |
| **代码强制** | 25 条（29%） |
| **Prompt 仅** | 60 条（71%） |
| Pydantic Schema | 28 个模型 |
| raise ValueError/RuntimeError | 32 处 |

### 🔴 HIGH 发现

#### F-001: V1 和 V2 Pipeline Prompt 并存导致架构混乱

**问题**: 目录中同时存在两套完全不兼容的 Pipeline：
- **V1 Pipeline**（8 个 `*_harness.md` 文件）：使用 `{{ template }}` 变量，输出到 `stages/*.json`
- **V2 Pipeline**（8+ 个模块 prompt）：使用 BlackboardManager，输出到 `blackboard/<session>/`

两套 Pipeline 的输出文件名、字段结构、数据流协议完全不同。Agent 可能混淆应该遵循哪套协议。

**影响**: Agent 在 V2 pipeline 中误用 V1 prompt，导致输出格式错误、验证失败。

**建议**: 将 V1 prompts 移至 `_archive/` 或添加 `DEPRECATED` 标记。

#### F-002: 71% 的约束仅靠 Prompt 声明，无代码强制

**关键 prompt-only 约束（无代码验证）**：
- "每个 Finding ≥ 200 字"（research_expert_base）
- "必须执行至少 15 次 web_search"（research_expert_base）
- "reasoning 必须引用具体 ID"（reviewer_*）
- "P0 REQ 100% 追溯"（meta_planner, convergence_planner）
- "merge_ratio 0.5-0.8"（convergence_planner）
- "禁止浅层结论"（research_expert_base）
- "禁止所有维度都给 STRONG"（planner_harness）

**影响**: LLM Agent 可能忽略这些约束而不被检测到。例如 "15 次 web_search" 实际执行 3 次也不会触发任何错误。

**建议**: 为关键约束添加代码级验证：
1. web_search 调用计数器
2. Finding 长度检查
3. reasoning 中 ID 引用正则检查
4. merge_ratio 数值范围检查

### 🟡 MEDIUM 发现

#### F-003: Convergence 输出到 Research 输入之间存在命名断裂

convergence_planner 输出 3 个独立文件（`unified_constraints.json`, `verification_checklist.json`, `requirement_traceability.json`），但 `research_expert_base` 读取单一的 `planning_convergence` stage。

**建议**: 在 `planning_module.md` 中明确声明聚合逻辑。

#### F-004: harness_agent.md 在 V2 pipeline 中无调用入口

harness_agent.md 定义了完整的 Gate A/B 评估逻辑，但 `orchestrator.md` 的验证脚本不引用 `harness_report.json`。

**建议**: 确认是否仍在使用，如不则标记为 DEPRECATED。

#### F-005: V1 Summarizer 和 V2 Orchestrator 输出不兼容

summarizer_harness.md 写入 `final_result.json`（含 `final_solution` + `markdown_document`），但 orchestrator.md 验证 `solution_document` + `final_solution`（两个独立 stage）。

**建议**: 统一输出格式或标记 V1 为 DEPRECATED。

### 跨 Agent Prompt 契约对齐

| 状态 | 对数 | 说明 |
|------|------|------|
| ✅ 对齐 | 5 | meta→expert, expert→convergence, convergence→reviewer, meta→reviewer_meta, research→summary |
| ❌ 未对齐 | 6 | 主要源于 V1/V2 架构并存 |

### Prompt 质量排名

**Top 3（高质量）**：
1. `orchestrator.md` (0.92) — 6 段式完整，Wake Protocol 明确，Fail Fast 清晰
2. `meta_planner.md` (0.90) — 完整 Schema，3 场景示例，P0 三维度
3. `ai_native_cognitive_base.md` (0.88) — 极简 320 字认知基底

**Bottom 3（低质量）**：
1. `fixer_expert_harness.md` (0.50) — 与 fixer_harness 高度重复，结构混乱
2. `consolidator_harness.md` (0.55) — V1 遗留，与 V2 不兼容
3. `fixer_harness.md` (0.55) — V1 遗留，harness_check 重复

---

## 🔵 维度 4: 法（编排 + 数据流）— 详细发现

### 统计概览

| 指标 | 数值 |
|------|------|
| 信息守恒逐跳检查 | 14 hops |
| 完好 | 10 hops |
| 断裂 | 3 hops |
| 风险 | 4 hops |
| Prompt-Runner 一致性 | 8 agents 检查 |
| 一致 | 5 agents |
| 不匹配 | 3 agents |

### 🔴 CRITICAL 发现

#### D4-001: ReviewQCOrchestrator 无调用方

**问题**: 架构地图声明 Module 3 = `ReviewQCOrchestrator`（含 Fix Loop + Harness + Final Review），但 `MasterOrchestrator.run()` 实际调用的是 `SummaryOrchestrator`。

ReviewQCOrchestrator 有完整实现但**无调用方** — 代码存在但从未执行。

**影响**: 所有 ReviewQC 功能（Fix Loop、Harness Check、Final Review）实际上都没有运行。系统直接跳过了质量门控。

**建议**: 检查 `MasterOrchestrator.run()` 的模块调用逻辑，确认是调用 SummaryOrchestrator 还是 ReviewQCOrchestrator。

#### D4-002: Research 模块无质量门禁

**问题**: `_generate_research_convergence()` 的 `gate_a_scores` 和 `gate_b_results` 全部硬编码为默认 `PASS` / `score=0.0`。

```python
# 伪代码示意
gate_a_scores = {"completeness": {"score": 0.0, "verdict": "PASS"}, ...}
gate_b_results = {"critical_items": [], "verdict": "PASS"}
```

研究质量无任何语义评估，低质量研究可无条件流入 Summary。

**影响**: Research 模块的产出质量完全依赖 LLM 自我约束，没有独立质量验证。

**建议**: 实现真正的 Research Harness Check，或者从 Planning Convergence 的质量标准推导 Research 的 Gate 评分。

### 🟡 WARNING 发现

#### D4-003: 平台能力跨域断裂

Meta Planner 识别 platform P0 约束（如 `platform_capabilities`），但 Ship Pro 无法获取，无跨域传递机制。

**建议**: 在 `planning_convergence.json` 中显式包含 `platform_capabilities` 字段，Ship Pro 读取时提取。

#### D4-004: Prompt-Runner 数据契约漂移

Expert Planner / Research Expert / Meta Planner 的 Prompt 声明输入与 Runner 实际注入存在差异。Runner 注入了 Prompt 未声明的字段：`p0_constraints`、`soft_constraints`、`semantic_anchors`。

**建议**: 更新 Prompt 以匹配 Runner 实际注入的数据，或在 Runner 中移除未声明的注入。

### 信息降级风险

| 检查项 | 状态 | 说明 |
|--------|------|------|
| build_frozen_spec() 读取 narrative | ✅ 通过 | 已读取 |
| build_frozen_spec() 读取 semantic_anchors | ⚠️ 部分 | 字段存在但类型处理有 warning |
| conversation_digest 传递 | ❌ 失败 | V2 路径中不传递 |
| platform_capabilities 跨域传递 | ❌ 失败 | 无跨域机制 |

---

## ⚫ 维度 6: 系统级 — 详细发现

### 统计概览

| 指标 | 数值 |
|------|------|
| Pydantic Schema | 46 个 |
| 有 validators | 3 个 |
| 仅靠字段约束 | 43 个 |
| 运行时 raise | 44 处 |
| Fallback bypass | 5 个 |
| 并发写入点 | 8 个 |
| 降级路径 | 4 active + 2 deprecated |

### 🔴 HIGH 发现

#### S-001: 46 个 Schema 仅 3 个有真正验证器

**问题**: 绝大多数 Pydantic Schema 只有字段定义（`str`, `int`, `list`），没有自定义验证器。这等于"有笼子但无锁"。

**真正有效的验证器**（仅 3 个）：
1. `GateAWeights` — 检查权重和 = 1.0
2. `UnifiedConstraintsSchema` — F6（LLM 控制域）+ F7（阈值一致性）
3. `HarnessCheck` — H1-H8（8 个质量笼子）

**仅有字段约束的 Schema**（43 个，示例）：
- `ExpertManifestSchema` — 只有 `min_length=1, max_length=5`，不验证内容
- `ExpertPlanSchema` — 只有 `min_length=1`，不验证约束质量
- `PlanningConvergenceSchema` — 只有 `max_length=500`，不验证内容
- `ResearchConvergenceSchema` — 只有 `max_length=1000`

**影响**: 字段存在且类型正确 ≠ 内容质量合格。例如 `ExpertPlanSchema` 验证"有至少 1 条约束"但不验证"约束是否有 rationale"。

**建议**: 为关键 Schema 添加内容质量验证器（如检查 rationale 非空、ID 格式正确、引用存在等）。

#### S-002: 5 个 Fallback Bypass 静默绕过验证

| 位置 | 降级行为 | 风险 |
|------|----------|------|
| `control_contract.py` | `STAGE_PATH_REGISTRY.get(stage_name, fallback)` | 静默回退到默认路径 |
| `control_contract.py` | planning.json 无效时使用 fallback control contract | 使用错误配置继续运行 |
| `research_orchestrator.py` | LLM query 失败 → keyword queries | 语义质量下降不报错 |
| `research_orchestrator.py` | LLM 不可用 → keyword overlap 去重 | 精度下降不报错 |
| `master_orchestrator.py` | living_spec 构建失败 → 硬编码 dict | 丢失原始需求 |

**影响**: 这些 fallback 都是"静默失败" — 系统继续运行但质量已降级，没有任何告警。

**建议**: 将所有 fallback 改为显式警告或 raise。降级必须被检测到。

### 并发安全评估

| 资源 | 保护机制 | 风险 |
|------|----------|------|
| `expert_plans/*.json` | tempfile+fsync+rename | ✅ 安全 |
| `research_experts/*.json` | 原子写入 | ✅ 安全 |
| `master_state.json` | threading.Lock | ✅ 安全 |
| `SourceRegistry` | threading.Lock | ✅ 安全 |
| `errors.jsonl` | append-only | ⚠️ 低（大量并发可能截断） |
| `pipeline_metrics.json` | 单线程 | ✅ 安全 |

**总体评估**: 并发安全良好，原子写入和锁使用正确。

### 降级路径评估

| 路径 | 状态 | 兼容性 | 问题 |
|------|------|--------|------|
| ReviewQC ABORT → Degraded | ✅ Active | ✅ 兼容 | 产出包含 `degradation_reason` + `partial_results` |
| Expert planner graceful | ✅ Active | ✅ 兼容 | min_viable 阈值 + checkpoint resume |
| Research expert graceful | ✅ Active | ✅ 兼容 | min_viable + format_check |
| Consolidation fallback | ✅ Active | ⚠️ 降级 | keyword overlap 去重精度低 |
| Planning default_expert | ❌ Deprecated | — | 已改为 raise，但 dict 仍保留 |
| Research skip_degraded | ❌ Deprecated | — | 同上 |

### 故障级联分析

| 故障场景 | 影响 | 恢复 | 严重度 |
|----------|------|------|--------|
| Planning 失败 | Pipeline 终止 | Checkpoint resume | HIGH |
| Research 失败 | Pipeline 终止 | Checkpoint resume | HIGH |
| ReviewQC ABORT | 降级产出 | 降级 Schema | MEDIUM |
| SourceRegistry 崩溃 | 仅影响 Research 去重 | 重新初始化 | LOW |
| Blackboard 磁盘满 | 全 Pipeline 失败 | 无 | HIGH |
| spawn_fn 不可用 | 全 Pipeline 失败 | 无 | HIGH |

**单点故障**: MasterOrchestrator.run()、Blackboard 文件系统、spawn_fn、living_spec 准备

### 角色边界正交性

| 检查项 | 结果 | 说明 |
|--------|------|------|
| Orchestrator 只做调度 | ✅ 通过 | 无语义判断，仅流程控制 |
| LLM 只做内容生成 | ✅ 通过 | 无流程控制 |
| 代码判断全是确定性 | ✅ 通过 | 计数、阈值、枚举 |

**评估**: 角色边界正交性良好。Code controls flow, LLM generates content 原则得到遵守。

### 自评可信度评估

| 指标 | 数值 |
|------|------|
| 管线自评 | 0.92 |
| 独立评分 | 6.1 |
| 偏差 | 38% |
| 审计误判率 | 25% |

**根因分析**:
1. 同一模型既生成又评估（确认偏差）
2. Harness Layer2 是 LLM-as-Judge majority vote，但 voter 和 executor 使用相似模型
3. 单层 LLM 评审不可靠（25% 误判率）

**设计含义**:
- Harness 双层设计（Layer1 规则 + Layer2 LLM）是正确方向，但 Layer2 本身也有偏差
- Cage H5（反自满）和 H6（反思不能敷衍）基于关键词匹配，LLM 可以绕过
- 需要 2+ 独立视角交叉验证

---

## 问题清单（按优先级排序）

### 🔴 P0 — 必须修复（阻塞级）

| # | 问题 | 维度 | 根因 | 修复方向 |
|---|------|------|------|----------|
| 1 | **ReviewQCOrchestrator 无调用方** — 完整实现但从未执行 | 🔵 | MasterOrchestrator 调用的是 SummaryOrchestrator | 检查 MasterOrchestrator.run() 的模块调用逻辑 |
| 2 | **Research 无质量门禁** — gate scores 硬编码 PASS | 🔵 | _generate_research_convergence() 未实现真实评分 | 实现 Research Harness 或从 Planning 推导 Gate 标准 |
| 3 | **V1/V2 Prompt 并存** — 8 个 V1 + 8 个 V2 共存 | 🔑 | 迁移未清理 | 将 V1 移至 _archive/ 或标记 DEPRECATED |

### 🟡 P1 — 高优先级

| # | 问题 | 维度 | 根因 | 修复方向 |
|---|------|------|------|----------|
| 4 | **71% 约束无代码强制** — 60 条仅靠 Prompt | 🔑 | 未实现代码验证 | 为关键约束添加计数器/长度检查/正则验证 |
| 5 | **46 Schemas 仅 3 有 validators** — 43 个只有字段定义 | ⚫ | 过度依赖 Pydantic 字段约束 | 为关键 Schema 添加内容质量验证器 |
| 6 | **5 个 fallback bypass** — 静默降级无告警 | ⚫ | 降级路径设计为静默 | 改为显式警告或 raise |
| 7 | **platform_capabilities 跨域断裂** — Ship Pro 无法获取 | 🔵 | 无跨域传递机制 | 在 planning_convergence.json 中显式包含 |

### 🟢 P2 — 中优先级

| # | 问题 | 维度 | 根因 | 修复方向 |
|---|------|------|------|----------|
| 8 | **Convergence→Research 命名断裂** — 3 文件 vs 1 stage | 🔑 | 中间聚合未声明 | 在 planning_module.md 中明确聚合逻辑 |
| 9 | **harness_agent.md 无调用入口** — orphaned prompt | 🔑 | V2 迁移遗留 | 确认使用状态，标记 DEPRECATED |
| 10 | **Summarizer 输出与 Orchestrator 验证不兼容** | 🔑 | V1/V2 格式不匹配 | 统一输出格式 |
| 11 | **conversation_digest 不传递** | 🔵 | V2 路径中移除 | 评估是否需要恢复 |
| 12 | **Prompt-Runner 数据契约漂移** | 🔵 | Runner 注入 Prompt 未声明的字段 | 同步 Prompt 和 Runner 的数据契约 |
| 13 | **Harness 自检标准 8 个 prompt 重复** | 🔑 | 未提取共享部分 | 提取为 _shared_harness_layer1.md |
| 14 | **双重评级系统混乱** — green/yellow/red + PASS/FAIL | 🔑 | 两套评级并存 | 明确关系或删除一套 |
| 15 | **Orchestrator Step 0 冗余 fallback** | 🔑 | 代码重复 | 删除第一次读取 |

---

## 修复建议汇总

### 短期（1-2 天）

1. **确认 ReviewQCOrchestrator 调用问题**: 检查 MasterOrchestrator 是否应调用 ReviewQCOrchestrator 而非 SummaryOrchestrator。这是设计意图还是实现错误？
2. **实现 Research 质量门禁**: 为 Research 模块添加真实的 Harness Check，或者从 Planning Convergence 的质量标准推导 Gate 评分。
3. **清理 V1 Prompt**: 将 8 个 V1 `*_harness.md` 文件移至 `prompts/_archive/v1/`。

### 中期（1 周）

4. **为关键约束添加代码验证**:
   - web_search 调用计数器（Research Expert）
   - Finding 长度检查（Research Expert）
   - reasoning 中 ID 引用正则检查（Reviewer）
   - P0 REQ 覆盖率检查（Convergence）
5. **强化 Schema 验证器**: 为 ExpertPlanSchema、ResearchExpertSchema 等添加内容质量验证（非空、格式正确、引用存在）。
6. **消除 fallback bypass**: 将所有静默降级改为显式警告 + 日志记录。
7. **修复跨域信息传递**: 在 planning_convergence.json 中显式输出 platform_capabilities 和 architecture_principles。

### 长期（1 个月）

8. **统一 Prompt 架构**: 消除 V1/V2 两套 pipeline，统一使用 BlackboardManager。
9. **改进自评可信度**: 引入 2+ 独立 Judge Agent（不同模型），降低确认偏差。
10. **建立 Prompt 版本管理**: 每次修改后运行 DryRun，防止回归。

---

## 结论

Solution Pro 2.0.0 的架构设计是合理的（三模块顺序 + 双层状态 + 原子写入），但实现层面存在结构性问题：

1. **ReviewQC 模块实际上未运行**（无调用方）
2. **Research 模块无质量验证**（硬编码 PASS）
3. **71% 的约束仅靠 Prompt 声明**（无代码强制）
4. **V1/V2 两套 Pipeline 并存**（架构混乱）
5. **大量 fallback 静默降级**（质量下降无感知）

**这些问题不是微调能解决的，需要结构性修复。**

建议修复 P0 问题后再运行 E2E 验证。

---

*报告生成: 2026-07-06 | Agent DryRun V3.2 | 检查文件: 41 prompts + 8 代码文件 + 12 schemas*
