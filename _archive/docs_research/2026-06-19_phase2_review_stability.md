# Phase 2 评审：管线稳定性与鲁棒性

> 评审日期：2026-06-19  
> 评审范围：3 个 E2E 案例的 ship_package / review_report / wp_specs / eval_code_checks  
> 评审视角：管线稳定性与鲁棒性

---

## 评审结论：PASS_WITH_CONCERNS

管线在 3 个案例上均能跑通并产出结构化输出，eval_code_checks 全部 5/5 pass。但存在 3 个需关注的稳定性问题：quality_report schema 不一致（跨案例字段命名不同）、complexity_distribution 使用非法枚举值、缺失边界输入场景测试。

---

## 跨案例对比

| 维度 | Case 1（AI客服系统） | Case 2（智能简历系统） | Case 3（单模块TODO） | 一致性 |
|------|--------|--------|--------|--------|
| **输入格式** | Format B | Format A | Format A | ✅ 两种格式均覆盖 |
| **WP 数量** | 8 | 6 | 1 | ✅ 合理分布 |
| **模块数** | 12 | 8 | 1 | ✅ |
| **schema_version** | 3.0.0 | 3.0.0 | 3.0.0 | ✅ 一致 |
| **eval_code_checks** | 5/5 pass | 5/5 pass | 5/5 pass | ✅ 全部通过 |
| **AC 均分（eval 工具）** | 85.1 | 100.0 | 80.0 | ⚠️ 分布合理但 Case2 满分需关注 |
| **AC 分布（L4/L3/L2/L1）** | 31/4/5/1 | 36/0/0/0 | 3/3/0/0 | ⚠️ Case2 全 L4 可疑 |
| **Reviewer verdict** | PASS | PASS_WITH_CONDITIONS | PASS | ⚠️ 命名不一致（见下） |
| **quality_report 字段命名** | `reviewer_verdict` / `module_coverage_rate` | `reviewer_verdict` / `module_coverage` | `verdict` / `coverage_rate` | ❌ 不一致 |
| **complexity_distribution 枚举** | 含 `"critical": 4` | 含 `"complex": 3` | 含 `"medium": 1` | ❌ Case1 使用非法值 |
| **dependency_graph 结构** | edges + parallel_groups + critical_path | 含 reason 字段的 edges | 空 edges + 单节点 | ✅ 结构一致 |
| **risk_register** | 8 项（缺 mitigation） | 5 项（含 residual + covered_by_wp） | 1 项 | ⚠️ 字段完整度不同 |

---

## 边界案例分析

### Case 3：单模块场景

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 是否过度拆分 | ✅ 正确 | 1 模块 → 1 WP，未拆分 |
| dependency_graph 正确性 | ✅ 正确 | `edges: []`，`parallel_groups: [["WP-001"]]`，`critical_path: ["WP-001"]` |
| eval_code_checks 处理 | ✅ 正确 | orphan 检查仅在 `len(wp_ids) > 1` 时触发，单 WP 跳过 orphan 检测 |
| 拓扑排序 | ✅ 正确 | 输出 `["WP-001"]`，单节点无依赖 |
| AC 评分 | ✅ 合理 | 6 条 AC，3 条 L4（含 `npm run test`、`localStorage` 断言）+ 3 条 L3（含时间阈值），均分 80.0 刚好过阈值 |

**结论**：单模块场景处理健壮，无误拆分、无错误依赖推断。

### Case 2 AC 满分分析

Case 2 的 36 条 AC 全部被评为 L4（100 分），原因是所有 AC 均以 `运行 pytest`、`运行 python3`、`运行 python3 -c` 等可执行命令开头。这实际上是**高质量 AC 的正确反映**——Specifier 为每条 AC 都给出了具体测试命令。eval 工具的 EXECUTABLE_SIGNALS 正则匹配行为正确。

但需注意：Case 1 有 5 条 L2 和 1 条 L1 AC，说明 Case 1 的 Specifier 输出质量略低。这属于**模型输出随机性**而非管线问题。

---

## Schema 合规性

### eval_code_checks 的 schema 覆盖

eval_code_checks.py 中硬编码的 `SHIP_PACKAGE_SCHEMA` 检查了以下 required 字段：
- WP 级：`id`, `title`, `objective`, `budget`, `complexity`, `priority`, `outputs`, `acceptance_criteria`
- budget 级：`tokens`

3 个案例均通过。但 eval 工具的 schema 是**宽松的子集检查**，不验证 `schema_version`、`meta`、`project_context`、`dependency_graph`、`risk_register`、`summary`、`quality_report` 等顶层字段。

### quality_report 字段不一致（主要问题）

| 字段 | Case 1 | Case 2 | Case 3 | 问题 |
|------|--------|--------|--------|------|
| verdict 字段名 | `reviewer_verdict` | `reviewer_verdict` | `verdict` | ❌ Case3 不同 |
| AC 分数字段名 | `ac_verifiability_score` | `ac_verifiability_score` | `ac_verifiability_score` | ✅ |
| 模块覆盖字段名 | `module_coverage_rate` (float) | `module_coverage` (string "8/8 (100%)") | 缺失 | ❌ 类型和命名均不同 |
| 需求覆盖字段名 | `requirements_coverage_rate` (float) | `requirements_coverage` (string "6/6 (100%)") | 缺失 | ❌ 类型和命名均不同 |
| 依赖检查字段 | 缺失 | `dependency_sanity` | `dependency_sanity` | ⚠️ Case1 缺失 |
| issues 字段 | 缺失（summary 文本中提及） | `total_issues` + `issues_by_severity` | `issues_count` | ❌ 命名不同 |
| review summary | `review_summary` (string) | `key_recommendations` (array) | 缺失 | ❌ 结构不同 |

**影响**：下游消费者（如 Dashboard、自动化管线）无法用统一 schema 解析 quality_report，需要 case-by-case 适配。

### complexity_distribution 枚举违规

Case 1 的 `summary.complexity_distribution` 包含 `"critical": 4`，但 `complexity` 字段的 enum 定义为 `["simple", "medium", "complex"]`。`critical` 不是合法值。这说明 Specifier 在 summary 中使用了与 WP 级 complexity 不同的枚举体系，但未在 schema 中定义映射。

---

## Reviewer 行为一致性

| 维度 | Case 1 | Case 2 | Case 3 |
|------|--------|--------|--------|
| verdict | PASS | PASS_WITH_CONDITIONS | PASS |
| issues 数量 | 0 | 6（3 medium + 3 low） | 0 |
| review_rounds | 1 | 1 | 0 |
| issue 描述风格 | N/A | 结构化（target_agent + severity + description + suggestion + affected_wp） | N/A |
| summary 风格 | 叙述性段落 | 叙述性段落 + 量化指标 | 简短段落 |

**发现**：
1. Case 1 和 Case 3 的 reviewer 未提出任何 issue，直接 PASS。Case 2 提出了 6 个结构化 issue。Reviewer 行为存在**松紧度不一致**——可能是模型随机性，也可能是 Case 1/3 的 spec 质量确实更高。
2. Case 3 的 `review_rounds: 0` 与 Case 1/2 的 `review_rounds: 1` 不同。语义不明：是"未需要修订轮次"还是"未执行 review"？缺乏文档说明。
3. Case 2 的 issue 格式高度结构化（含 suggestion 和 affected_wp），但 Case 1/3 无 issue 可比较格式。无法确认 issue 格式在无 issue 时是否稳定。

---

## risk_register 字段不一致

| 字段 | Case 1 | Case 2 | Case 3 |
|------|--------|--------|--------|
| `id` | ✅ | ✅ | ✅ |
| `description` | ✅ | ✅ | ✅ |
| `severity` | ✅ | ✅ | ✅ |
| `mitigation` | 空字符串 "" | 有内容 | 有内容 |
| `residual` | 缺失 | ✅ | 缺失 |
| `covered_by_wp` | 缺失 | ✅ | 缺失 |

Case 1 的 mitigation 全为空字符串，且缺少 `residual` 和 `covered_by_wp` 字段。Case 2 的 risk_register 最完整。这反映了 Specifier 输出质量的波动。

---

## 缺失测试场景

| 场景 | 是否覆盖 | 风险等级 |
|------|---------|---------|
| Format A 输入（自然语言描述） | ✅ Case 2, Case 3 | — |
| Format B 输入（结构化需求） | ✅ Case 1 | — |
| Format C 输入（仅技术约束） | ❌ 未覆盖 | 中 |
| Format D 输入（极简/模糊输入） | ❌ 未覆盖 | 高 |
| 空输入 / 无效输入 | ❌ 未覆盖 | 高 |
| 单模块场景 | ✅ Case 3 | — |
| 多模块复杂场景（>10 WP） | ✅ Case 1（8 WP） | — |
| 超大规模场景（>20 WP） | ❌ 未覆盖 | 中 |
| 含循环依赖的 blueprint | ❌ 未覆盖（应由 eval 捕获） | 中 |
| 跨 WP AC 重复 | ❌ 未覆盖（eval 有 dedup 检查但未触发） | 低 |

**最关键缺失**：Format C/D 输入和空输入。这些边界场景可能导致管线崩溃或产出无意义结果。

---

## eval_code_checks 工具评估

### 优点
1. **确定性强**：纯正则匹配，无 LLM 依赖，<1s 执行
2. **覆盖全面**：schema 合规、AC 可验证性、依赖图、AC 去重、字段完整性 5 项检查
3. **单 WP 场景正确处理**：orphan 检测仅在 WP > 1 时触发
4. **CLI + JSON 双输出**：便于人类阅读和管线集成

### 不足
1. **schema 检查过于宽松**：不验证 `meta`、`project_context`、`dependency_graph`、`quality_report` 等顶层字段的存在性和类型
2. **complexity enum 检查仅限 WP 级**：`summary.complexity_distribution` 的 key 不受 enum 约束
3. **quality_report 无 schema 定义**：3 个案例产出了 3 种不同字段命名，eval 工具未捕获
4. **AC 评分对"运行 pytest"模板化 AC 全部给 L4**：Case 2 的 36 条 AC 几乎结构相同（"运行 pytest ..."），但全部获得 L4=100 分。评分器未考虑 AC 多样性

---

## 建议

### 高优先级

1. **统一 quality_report schema**  
   定义 `quality_report_v3.schema.json`，固定字段名和类型。建议：
   ```json
   {
     "verdict": "PASS | PASS_WITH_CONDITIONS | FAIL",
     "ac_verifiability_score": 88,
     "module_coverage_rate": 1.0,
     "requirements_coverage_rate": 1.0,
     "dependency_sanity": "ok",
     "review_rounds": 1,
     "issues": [...],
     "summary": "..."
   }
   ```
   在 Reviewer prompt 中强制要求输出符合此 schema。

2. **修复 complexity_distribution 枚举**  
   在 Specifier prompt 中明确：`summary.complexity_distribution` 的 key 必须与 WP 级 `complexity` enum 一致（`simple`/`medium`/`complex`），禁止使用 `critical`/`high` 等未定义值。

3. **补充 Format C/D 输入测试案例**  
   - Case 4：仅给出技术约束（如"用 React + SQLite 做个应用"），无功能描述
   - Case 5：极简/模糊输入（如"帮我做个东西"），测试管线的澄清/拒绝能力

### 中优先级

4. **加强 eval_code_checks 的 schema 验证**  
   扩展 `SHIP_PACKAGE_SCHEMA` 覆盖 `meta`、`project_context`、`dependency_graph`、`quality_report` 顶层字段。或引入 jsonschema 库做严格校验。

5. **risk_register 字段标准化**  
   在 Specifier prompt 中明确 risk 条目的必填字段：`id`、`description`、`severity`、`mitigation`（禁止空字符串）。`residual` 和 `covered_by_wp` 设为可选。

6. **AC 评分器增加多样性惩罚**  
   当同一 case 内大量 AC 结构高度相似时（如 Case 2 的 36 条"运行 pytest ..."），引入 Jaccard 相似度惩罚因子，避免"模板化 AC 刷分"。

### 低优先级

7. **review_rounds 语义文档化**  
   明确 `review_rounds: 0` 的含义（是"未执行 review"还是"首轮即通过无需修订"）。

8. **空输入防护**  
   在管线入口添加输入验证：空 blueprint → 拒绝并返回明确错误信息，而非让管线产出空 ship_package。

---

## 附录：eval_code_checks 原始数据

| Check | Case 1 | Case 2 | Case 3 |
|-------|--------|--------|--------|
| schema_compliance | ✅ pass | ✅ pass | ✅ pass |
| ac_verifiability | ✅ 85.1 | ✅ 100.0 | ✅ 80.0 |
| dependency_graph | ✅ no cycles | ✅ no cycles | ✅ no cycles |
| ac_dedup | ✅ 0 pairs | ✅ 0 pairs | ✅ 0 pairs |
| field_completeness | ✅ 8/8 | ✅ 6/6 | ✅ 1/1 |
| **Overall** | **5/5 pass** | **5/5 pass** | **5/5 pass** |
