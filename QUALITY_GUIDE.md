# DeepFlow 全链路质量评估方法论

> **版本**: V1.0.0 | **创建日期**: 2026-06-20  
> **适用范围**: Spec Pro → Solution Pro → Ship Pro 端到端质量追溯  
> **首次验证案例**: Serenity Skills A股适配

---

## 一、概述

DeepFlow 的全链路质量评估采用**双维度模型**：

1. **模块内质量（Intra-Module Quality）** — 各域独立评估输出质量
2. **跨模块对齐（Cross-Module Alignment）** — 验证模块间的信息传递和一致性

### 质量评估架构

```
用户输入 (Living Spec)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Spec Pro                                                │
│  ├─ HarnessWorker: 5维度 Output Guard                   │
│  │   (清晰度/完整度/可执行度/一致度/下游适配度)          │
│  └─ 输出: living_spec.json + quality_report.json        │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Solution Pro                                            │
│  ├─ HarnessScorer: 4维度评分                            │
│  │   (完整性30%/必要性20%/目标一致性30%/全局影响20%)     │
│  ├─ Multi-Reviewer: 3路并行评审                         │
│  └─ 输出: final_result.json + requirements_traceability │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Ship Pro                                                │
│  ├─ Quality Gate V2: Compiler → Reviewer → Fixer        │
│  │   (AC质量验证 + 依赖合理性验证)                      │
│  └─ 输出: ship_package.json + ship_review_result.json   │
└─────────────────────────────────────────────────────────┘
```

---

## 二、维度一：模块内质量（Intra-Module Quality）

### 2.1 Spec Pro 质量门禁

**评估框架**: 5维度 Output Guard（详见 `domains/spec_pro/prompts/harness.md`）

| 维度 | 权重 | 评估内容 |
|------|------|---------|
| 清晰度 (Clarity) | 25% | 需求表述是否无歧义，下游能否准确理解 |
| 完整度 (Completeness) | 25% | 关键需求维度是否都有覆盖 |
| 可执行度 (Executability) | 20% | 下游引擎能否直接消费这份 Spec |
| 一致度 (Consistency) | 15% | 需求之间是否有矛盾 |
| 下游适配度 (Downstream Fitness) | 15% | 结构是否完整，是否适合下游消费 |

**决策阈值**:
- PASS: ≥ 75 分
- WARN: 60-74 分
- SOFT_BLOCK: 45-59 分
- HARD_BLOCK: < 45 分

### 2.2 Solution Pro 质量门禁

**评估框架**: 4维度 Harness Scorer（详见 `domains/solution/harness_scorer.py`）

| 维度 | 权重 | 评估内容 |
|------|------|---------|
| 完整性 (Completeness) | 30% | 方案覆盖范围，关键设计点无遗漏 |
| 必要性 (Necessity) | 20% | 方案适度，无过度设计 |
| 目标一致性 (Alignment) | 30% | 方案与原始目标的一致性 |
| 全局影响 (Global Impact) | 20% | 成本、风险、集成、运维、长期演进 |

**决策阈值**:
- PASS: ≥ 0.85
- WARNING: 0.70-0.84
- CRITICAL_WARNING: 0.60-0.69
- BLOCK_RECOMMENDATION: < 0.60

**特殊规则**: 目标一致性 < 0.6 → 至少 CRITICAL_WARNING

### 2.3 Ship Pro 质量门禁

**评估框架**: Quality Gate V2（详见 `domains/ship_pro/docs/quality_gate_design.md`）

**检查项**:
1. **AC 质量验证** — 逐条检查 acceptance_criteria 是否包含空泛表述
2. **依赖合理性验证** — 检查循环依赖、孤立模块、基础设施隔离

**修复流程**: Compiler(确定性) → Reviewer(LLM) → Fixer(LLM) → Harness(LLM)，最多 2 轮修复循环

---

## 三、维度二：跨模块对齐（Cross-Module Alignment）

### 3.1 对齐检查 2A: 用户意图 → Solution Pro

**目标**: 验证 Solution Pro 的设计是否覆盖用户原始需求

**方法**: 逐条对照 Living Spec 中的 `confirmed` 层，检查 Solution Pro 的 `final_result.json` 是否覆盖。

| 检查项 | 数据来源 | 验证方法 |
|--------|---------|---------|
| 核心目标覆盖 | `living_spec.confirmed.objective` | `final_result.json` 的执行摘要 |
| 每个痛点有对策 | `living_spec.confirmed.pain_points` | `final_result.json` 的问题拆解表 |
| 成功指标覆盖 | `living_spec.confirmed.success_metrics` | `final_result.json` 的成功指标章节 |
| 护栏遵守 | `living_spec` guardrails (always_do/never_do) | `final_result.json` 各章节 + 合规护栏 |
| 推断项处理 | `living_spec.inferred`（含 pending） | `final_result.json` 中是否被处理 |

**过度工程检测**: 列出 Solution Pro 中用户原始需求未提及的功能/设计，对比 `input.md` vs `final_result.json`

### 3.2 对齐检查 2B: Solution Pro → Ship Pro

**目标**: 验证 Ship Pro 的执行计划是否准确反映 Solution Pro 的设计

| 检查项 | 数据来源 | 验证方法 |
|--------|---------|---------|
| ADR 传播 | `final_result.json` 中的 architecture_decisions | `ship_package.json` 中的 work_packages 是否体现 |
| 组件映射 | `final_result.json` 中的 components | `ship_package.json` 中的 work_packages 是否一一对应 |
| 文件映射 | `final_result.json` 中的 deliverables | `ship_package.json` 中的 file_paths 是否完整 |

### 3.3 对齐检查 2C: 端到端（用户意图 → Ship Package）

**目标**: 验证从用户原始需求到最终执行计划的完整追溯链

**追溯链**:
```
Living Spec (confirmed.objective)
    ↓
Solution Pro (final_result.json)
    ↓
Ship Pro (ship_package.json)
```

**完整性检查**:
- 每个 `confirmed.objective` 是否在 `final_result.json` 中有对应设计
- 每个设计是否在 `ship_package.json` 中有对应 work_package
- 每个 work_package 是否有明确的 acceptance_criteria

---

## 四、数据采集清单

### 4.1 Spec Pro 采集项

| 数据项 | 来源文件 | 关键指标 |
|--------|---------|---------|
| 质量评分 | `spec/quality_report.json` | 7维度加权平均 |
| Harness 决策 | `spec/harness_report.json` | PASS/WARN/SOFT_BLOCK/HARD_BLOCK |
| 推断审计 | `spec/harness_report.json` | pending 推断数量 |
| 对话轮次 | `spec/conversation_log.json` | 3-6 轮（standard） |

### 4.2 Solution Pro 采集项

| 数据项 | 来源文件 | 关键指标 |
|--------|---------|---------|
| Harness 评分 | `stages/harness_final.json` | 4维度加权总分 |
| 需求覆盖 | `requirements_traceability_matrix.json` | covered_req_ids 覆盖率 |
| REQ 传播 | `final_result.json` | requirement_evidence 完整性 |
| 评审结果 | `stages/reviewer_*.json` | 3路评审一致性 |

### 4.3 Ship Pro 采集项

| 数据项 | 来源文件 | 关键指标 |
|--------|---------|---------|
| AC 质量 | `ship_review_result.json` | vague_ac 数量 |
| 依赖合理性 | `ship_review_result.json` | cycle/orphan 数量 |
| Harness 判定 | `ship_harness_result.json` | passed/failed/passed_with_conditions |
| 修复轮次 | `ship_harness_result.json` | fix_round 数（0-2） |

---

## 五、质量报告模板

### 5.1 全链路质量报告结构

```markdown
# DeepFlow 全链路质量报告

## 项目信息
- 项目名称: {project_name}
- Living Spec: {living_spec_path}
- 评估时间: {timestamp}

## 模块内质量

### Spec Pro
- Harness 决策: {decision}
- 总分: {score}/100
- 关键问题: {issues}

### Solution Pro
- Harness 决策: {decision}
- 总分: {score}/1.0
- 需求覆盖率: {coverage}%

### Ship Pro
- Quality Gate: {decision}
- AC 质量: {vague_ac_count} 个问题
- 修复轮次: {fix_round}

## 跨模块对齐

### 2A: 用户意图 → Solution Pro
- 覆盖度: {coverage}%
- 过度工程: {over_engineering_items}

### 2B: Solution Pro → Ship Pro
- ADR 传播: {adr_propagation}%
- 组件映射: {component_mapping}%

### 2C: 端到端追溯
- 追溯链完整性: {traceability}%

## 综合评估
- 整体质量等级: {grade}
- 关键风险: {risks}
- 改进建议: {recommendations}
```

---

## 六、附录

### 6.1 相关文档

- Spec Pro Harness: `domains/spec_pro/prompts/harness.md`
- Solution Pro Harness: `domains/solution/harness_scorer.py`
- Ship Pro Quality Gate: `domains/ship_pro/docs/quality_gate_design.md`

### 6.2 验证脚本

- Golden Case 验证: `tests/golden/verify_golden_case.py`
- 需求去重验证: `domains/solution/scripts/validate_req_dedup.py`
- V6 改进测试: `domains/solution/eval/test_v6_improvements.py`

### 6.3 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V1.0.0 | 2026-06-20 | 初始版本，覆盖全链路质量评估方法论 |
