# Ship Pro AI Native 改造报告

> **日期**: 2026-06-25  
> **状态**: ✅ 完成  
> **原则**: LLM 做判断，代码做格式验证

---

## 核心问题

V1/V2/V3 的 Ship Pro 管线存在系统性偏差：
- 架构约束（如"全 LLM 控制"、"基于 OpenClaw 平台"）在传递过程中丢失
- 即使约束被传递到下游，Architect/Decomposer/Specifier 也没有据此改变输出
- Gate 检查只能验证"有没有"（字段存在），不能验证"对不对"（语义合理）

**根因**: 管线的 gate 函数是规则驱动的（硬编码检查逻辑），无法理解语义。

---

## AI Native 改造方案

### 核心原则

| 类型 | 判断方式 | 例子 |
|------|---------|------|
| **需要理解语义** | LLM 判断 | 架构是否合理、原则是否被违反、model 是否合适 |
| **纯格式验证** | 代码验证 | JSON schema、字段存在性、依赖无环 |

### 三层 Gate 架构

```
Layer 1: 确定性检查（代码）
  ↓ 快速过滤格式错误（字段存在、依赖无环、Pydantic 验证）
Layer 2: LLM 语义检查（Orchestrator）
  ↓ Orchestrator 用自己的 LLM 评估 Worker 输出
Layer 3: 综合决策
  ↓ 合并确定性 + 语义结果 → PASS / CONDITIONAL / FAIL
```

---

## 改动清单

### 1. 删除硬编码映射表

**文件**: `scripts/inject_principles.py`

**改动**:
- 删除 `CONSTRAINT_TO_PRINCIPLE` 字典（约 50 行）
- 删除 `CONSTRAINT_TO_PLATFORM` 字典（约 80 行）
- 删除 `match_constraint_to_rule` 函数
- 删除 `extract_principles` 函数
- 简化为：只复制 `planning.json` 的 `constraints` 字段到 `final_result.json`

**原因**: 让 Orchestrator 在 Phase -1 中用 LLM 提取原则，而不是用硬编码映射规则。

---

### 2. 增加 Phase -1 原则提取

**文件**: `scripts/start_ship_pro.py`

**改动**: 在 Orchestrator prompt 的 "Phase 0: 准备管线" 之前增加：

```
### Phase -1: 原则提取（AI Native）

读取输入文件中的 constraints 字段。

用你的 LLM 能力，从 constraints 中提取：
1. architecture_principles: 架构原则列表
2. platform_capabilities: 平台能力列表

判断标准（用你的理解判断，不是硬编码规则）：
- 如果 constraint 描述的是"必须怎么做"或"禁止怎么做" → architecture_principle
- 如果 constraint 描述的是"基于什么平台"或"用什么工具" → platform_capabilities
- 其他 → 忽略

severity 判断：
- 如果违反会导致系统无法运行或严重偏离设计意图 → BLOCKER
- 如果违反会影响质量但不阻塞 → WARNING

把提取结果写入输入文件（读取原文件，增加这两个字段，写回）。
```

**原因**: 让 Orchestrator 用 LLM 自动提取原则，不需要硬编码映射表。

---

### 3. 强化 Architect prompt

**文件**: `domains/ship_pro/prompts/architect.md`

**改动**: 在"提取规则"章节之前增加：

```
## 架构完整性判断（AI Native）

你必须判断这个架构是否完整。具体来说：

1. **编排层**：如果这是一个多组件系统，必须有编排层（负责串联所有组件形成完整执行路径）。
   用你的理解判断是否需要编排层，如果需要，生成对应的模块。

2. **全 LLM 控制**：如果架构原则要求"全 LLM 控制"，你需要判断每个模块的技术栈是否符合这个原则。
   如果你认为某个模块用确定性逻辑（如状态机、阈值、规则引擎）更合适，可以保留，
   但必须在 rationale 中解释为什么这个模块不适合用 LLM。

3. **需求覆盖**：检查 requirements 字段，确保所有 P0 需求都被映射到模块。
   如果有 P0 需求未被映射，生成对应的模块。

不要机械地套用规则，用你的理解判断什么是最合理的架构设计。
```

**原因**: 让 LLM 自己判断是否需要编排层、是否违反"全 LLM 控制"原则，而不是硬编码模块名或反模式列表。

---

### 4. 强化 Reviewer prompt

**文件**: `domains/ship_pro/prompts/reviewer.md`

**改动**: 在"审核维度"章节之前增加：

```
## Verdict 判断（AI Native）

你必须综合判断 verdict，不是机械地套用规则。具体来说：

1. **PASS**：如果架构设计合理，所有原则都被遵守，没有重大问题。

2. **PASS_WITH_CONDITIONS**：如果有中等严重度的问题（如某个协议缺失、某个 SLA 未传递），但不影响核心功能。

3. **FAIL**：如果有严重问题（如核心模块缺失、原则被严重违反）。

判断标准：
- 如果 issue 涉及原则违反（如"全 LLM 控制"被违反），即使 severity=medium，也应该考虑 FAIL 或 PASS_WITH_CONDITIONS。
- 如果 issue 涉及核心模块缺失（如编排层），应该 FAIL。
- 如果 issue 只是细节问题（如 model_tier 选择不合理），可以 PASS。

用你的理解判断，不要机械地套用"medium issue 不影响 verdict"的规则。
```

**原因**: 让 LLM 综合判断 verdict，而不是硬编码"medium issue → PASS"的规则。

---

### 5. 强化 Specifier prompt

**文件**: `domains/ship_pro/prompts/specifier.md`

**改动**: 在"原则验证 AC"章节之前增加：

```
## Model Tier 选择（AI Native）

你必须根据 WP 的特点判断合适的 model_tier，不是机械地套用规则。具体来说：

判断标准：
- 如果 WP 涉及复杂逻辑（如 DAG 分解、质量评估、错误分析） → claude-opus
- 如果 WP 涉及中等复杂度逻辑（如状态管理、上下文压缩） → claude-sonnet
- 如果 WP 涉及简单逻辑（如文件 I/O、配置读取） → claude-haiku

考虑因素：
- WP 的 complexity 字段
- WP 的 priority 字段
- WP 涉及的模块类型

用你的理解判断，不要机械地套用"所有 WP 都用 opus"或"low complexity 都用 haiku"的规则。
```

**原因**: 让 LLM 根据 WP 复杂度判断模型，而不是硬编码映射表。

---

### 6. 强化 Decomposer prompt

**文件**: `domains/ship_pro/prompts/decomposer.md`

**改动**: 在"拆分原则"章节之前增加：

```
## WP 分配判断（AI Native）

你必须判断是否需要为某些特殊需求创建独立的 WP，不是机械地套用规则。具体来说：

1. **对等协作协议**：如果 Architect 输出中包含 Hermes 或其他对等协作伙伴的描述，
   你需要判断是否需要创建独立的 WP 来实现通信协议。用你的理解判断，不要机械地忽略。

2. **SLA 约束传递**：如果 Architect 输出中包含 SLA 约束（如 HITL 超时、最大并发数），
   你需要判断是否需要将这些约束分配到具体的 WP。用你的理解判断哪些 WP 应该承接这些约束。

3. **WP 粒度**：你需要判断 WP 的粒度是否合理。如果一个 WP 的职责过多（如涉及多个不同领域），应该拆分。
   但如果职责紧密相关，不需要拆分。用你的理解判断，不要机械地套用"职责 > 3 必须拆分"的规则。
```

**原因**: 让 LLM 判断是否需要为 Hermes/HITL 创建独立 WP，而不是硬编码规则。

---

### 7. 简化 semantic-task prompts

**文件**: `domains/ship_pro/eval/llm_gate_checks.py`

**改动**:
- 简化 `_build_architect_prompt`：删除硬编码的检查规则（如"如果 tech stack 包含令牌桶限流→FAIL"），改为给出原则描述，让 Orchestrator 自己判断。
- 简化 `_build_decomposer_prompt`：同上。
- 简化 `_build_specifier_prompt`：同上。

**原因**: 让 Orchestrator 自己判断，不是硬编码检查规则。

---

### 8. 删除硬编码 gate 函数

**文件**: `domains/ship_pro/eval/gates.py`

**改动**:
- 删除 `gate_principle_alignment` 函数（约 60 行）
- 删除 `gate_platform_coverage` 函数（约 50 行）
- 修改 `gate_architect`：删除 Phase 2 的原则对齐检查（architecture_principles_present, platform_capabilities_present, principle_coverage_present, platform_reuse_map_present）
- 修改 `gate_reviewer`：删除 Phase 2 的原则审计检查（principle_audit_present, platform_audit_present, no_principle_failures, no_platform_failures）

**原因**: 语义检查应该由 Orchestrator 做（Layer 2），不是代码（Layer 1）。代码只做格式检查（LLM 不擅长的）。

---

## 验证结果

```
✅ inject_principles.py 硬编码映射表已删除
✅ gate_principle_alignment 已删除
✅ gate_platform_coverage 已删除
✅ architect.md AI Native 章节已添加
✅ reviewer.md AI Native 章节已添加
✅ specifier.md AI Native 章节已添加
✅ decomposer.md AI Native 章节已添加
✅ llm_gate_checks.py 硬编码检查规则已删除
✅ start_ship_pro.py Phase -1 已添加
```

---

## 下一步

重跑 Ship Pro V4，验证：

1. **Phase -1 原则提取**: Orchestrator 是否能用 LLM 自动提取原则
2. **Architect 编排层**: 是否能生成 MainLoopOrchestrator 等编排层模块
3. **Decomposer Hermes/HITL**: 是否能创建独立 WP
4. **Specifier model_tier**: 是否能根据复杂度选择合适模型
5. **Reviewer verdict**: 是否能综合判断（不是机械套用规则）
6. **语义检查覆盖**: 是否覆盖 architect/decomposer/specifier 三个阶段

---

## 核心改进

| 维度 | V3（规则驱动） | V4（AI Native） |
|------|-------------|----------------|
| 原则提取 | 硬编码映射表 | LLM 自动提取 |
| 架构完整性 | 硬编码模块名 | LLM 判断是否需要编排层 |
| 原则检查 | 硬编码关键词匹配 | LLM 语义判断 |
| verdict 决策 | 硬编码规则 | LLM 综合判断 |
| model 选择 | 硬编码映射表 | LLM 根据复杂度判断 |
| WP 分配 | 硬编码规则 | LLM 判断是否需要独立 WP |

**总结**: 所有需要理解/判断的都用 LLM，只有 LLM 不擅长的（格式验证）才用代码。

---

*AI Native 改造完成。核心理念：LLM 做判断，代码做格式验证。*
