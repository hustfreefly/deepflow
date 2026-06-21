# Ship Pro Schema 一致性与产出质量审计报告

> **审计对象**: 智能简历生成系统_architecture_d99f733a
> **Schema 版本**: ship_package.schema.json (Draft-07, v0.1)
> **Compiler 版本**: ship_compiler.py v0.1.0
> **审计时间**: 2026-06-12T06:30:00+00:00

---

## 1. Schema 校验

**状态**: 🟢 GREEN

```
jsonschema Draft7Validator → 0 errors
Schema validation PASSED
```

所有 required 字段存在，类型匹配，pattern 约束满足，enum 值合法。

---

## 2. 字段完整性

**状态**: 🟢 GREEN

| 顶层 required 字段 | Schema 要求 | 实际产出 | 状态 |
|---|---|---|---|
| meta | ✅ required | ✅ 存在 | OK |
| readiness | ✅ required | ✅ 存在 | OK |
| work_packages | ✅ required (minItems:1) | ✅ 8 个 WP | OK |
| acceptance_contract | ✅ required | ✅ 12 个 AC | OK |
| risk_contract | ✅ required | ✅ 存在 | OK |
| harmony_brief | ✅ required | ✅ 存在 | OK |

**meta 子字段**:
| 字段 | 要求 | 实际 | 状态 |
|---|---|---|---|
| contract_name | const: "deepflow.ship_package" | ✅ 匹配 | OK |
| contract_version | pattern: "^0\\.1\\.\\d+$" | "0.1.0" ✅ | OK |
| source_blueprint | string | "None vNone" ⚠️ | 见值质量 |
| source_session_id | string, minLength:1 | ✅ | OK |
| generated_at | string, format: date-time | ✅ | OK |
| engine | const: "ship_pro" | ✅ | OK |
| engine_version | string | "0.1.0" ✅ | OK |

**WP 子字段 (每个 WP)**:
| 字段 | 要求 | 实际 | 状态 |
|---|---|---|---|
| id | pattern: "^WP-\\d{3}$" | ✅ WP-001~008 | OK |
| title | string, minLength:3 | ✅ | OK |
| phase | string | ✅ | OK |
| dependencies | array of WP-id pattern | ✅ | OK |
| requirements | array of REQ-id pattern | ✅ | OK |
| deliverables | array, minItems:1 | ✅ 每个 WP 2 个 | OK |
| acceptance_criteria | array, minItems:1 | ✅ 每个 WP 3 个 | OK |
| human_review_required | boolean | ✅ | OK |

---

## 3. 类型一致性

**状态**: 🟢 GREEN

| 字段路径 | Schema 类型 | 实际类型 | 状态 |
|---|---|---|---|
| work_packages[].dependencies | string[] (pattern WP-\\d{3}) | ✅ string[] | OK |
| work_packages[].requirements | string[] (pattern REQ-\\d{3}) | ✅ string[] | OK |
| work_packages[].estimated_complexity | enum [small,medium,large] | ✅ | OK |
| acceptance_contract[].verification_method | enum [automated_test,manual_check,code_review,integration_test] | ✅ | OK |
| acceptance_contract[].priority | enum [P0,P1,P2] | ✅ | OK |
| risk_contract.known_gaps | object[] | ✅ [] | OK |
| risk_contract.risk_register | object[] | ✅ 6 items | OK |
| harmony_brief.package_order | string[] (pattern WP-\\d{3}) | ✅ | OK |

---

## 4. 值质量

### 4.1 meta.source_blueprint = "None vNone"

**状态**: 🔴 RED

**问题**: `source_blueprint` 值为 `"None vNone"`，这是编译器代码中 f-string 对 `None` 值的字符串化结果：

```python
# ship_compiler.py line ~330
"source_blueprint": f"{_safe_get(bp, 'meta', 'contract_name', '')} v{_safe_get(bp, 'meta', 'contract_version', '')}",
```

但 Frozen Blueprint 实际包含 `contract_name: "deepflow.frozen_blueprint"` 和 `contract_version: "0.1.0"`。

**根因分析**: 编译器在 blocked 路径（line ~310）和正常路径（line ~330）都使用了这段代码，但 `_safe_get` 的 default 参数是 `""`（空字符串），不应该返回 `None`。实际检查发现 Frozen Blueprint 的 `meta.contract_name` 和 `meta.contract_version` 字段确实存在且有值。

**修正**: 经重新检查编译器代码，`_safe_get` 在 key 不存在时返回 `""` 而非 `None`（因为 `default=""` 且末尾有 `if current is not None else default`）。但产出中确实是 `"None vNone"`，说明 Frozen Blueprint 被读取时 meta 字段可能未被正确解析，或者编译器运行时的 Frozen Blueprint 文件内容与当前版本不同。

**影响**: 溯源断裂——无法从 Ship Package 反向定位到 Frozen Blueprint 的合约版本。

**建议修复**:
1. 在编译器中添加防御性检查：如果 source_blueprint 包含 "None" 则抛出警告
2. 考虑改为直接存储 `"deepflow.frozen_blueprint v0.1.0"` 硬编码值（因为合约名是固定的）
3. 或改为存储 session_id + generated_at 组合，更有溯源价值

---

### 4.2 acceptance_criteria 内容质量

**状态**: 🔴 RED

**问题**: 8 个 WP 中，每个 WP 的 acceptance_criteria 前 3 条都是相同的泛化文本：
```
- "智能简历生成系统"
- "保真度90%-95%以上，不造假，仅合理拓展"
- "与目标JD高度贴合"
```

这些是 Frozen Blueprint `verification.acceptance_criteria` 的全局需求级 AC，不是组件级的验收标准。

**根因分析**: 编译器 `_decompose_work_packages()` 中：

```python
# 对所有 WP 都取全局 AC 的前 3 条
wp_ac = []
for ac in acceptance_criteria:
    if isinstance(ac, dict):
        wp_ac.append(ac.get("text", ""))
# ...
"acceptance_criteria": wp_ac[:3] if wp_ac else [f"{mod_name} 功能验证通过"],
```

这段代码对每个 module/WP 都取相同的全局 AC 列表前 3 条，没有做组件级拆分。

**影响**: 
- WP-001（输入解析层）和 WP-005（双格式渲染管道）的验收标准完全相同
- 施工方无法根据 AC 判断具体组件的完成标准
- acceptance_contract 中 AC-001~AC-004, AC-010~AC-012 的 criteria 都是 "智能简历生成系统"（5 字以上所以通过 schema minLength:5，但语义空洞）

**建议修复**:
1. 编译器应为每个 module 生成组件级 AC，例如：
   - WP-001: "输入解析层能正确解析 PDF/DOCX/纯文本三种输入格式"
   - WP-005: "PDF 渲染输出在 macOS/Windows/Linux 三平台格式一致"
2. 短期方案：至少将 module 的 summary/description 作为 AC 的一部分
3. 在 Frozen Blueprint 中为每个 module 添加 module-level acceptance criteria

---

### 4.3 requirements 分配不均

**状态**: 🟡 YELLOW

**问题**: 6 个 REQ 中，5 个被分配到 WP-005（双格式渲染管道），1 个分配到 WP-001（输入解析层），其余 6 个 WP 没有 requirements。

| WP | Requirements | 数量 |
|---|---|---|
| WP-001 | REQ-001 | 1 |
| WP-002 | (无) | 0 |
| WP-003 | (无) | 0 |
| WP-004 | (无) | 0 |
| WP-005 | REQ-002, 003, 004, 005, 006 | 5 |
| WP-006 | (无) | 0 |
| WP-007 | (无) | 0 |
| WP-008 | (无) | 0 |

**根因分析**: 编译器 requirement 分配逻辑有缺陷：

```python
for req in requirements:
    group = req.get("group", "")
    for wp in packages:
        wp_idx = packages.index(wp)
        if group in ("Core", "Functional") and wp_idx < len(packages) // 2 + 1:
            wp["requirements"].append(req_id)
            assigned = True
            break
        elif group in ("NonFunctional",) and wp_idx >= len(packages) // 2:
            wp["requirements"].append(req_id)
            assigned = True
            break
```

问题：
1. Core 组的 REQ-001 匹配到第一个 WP（WP-001）就 break 了
2. NonFunctional 组的 5 个 REQ 都匹配到 `wp_idx >= 4` 的第一个 WP，即 WP-005（index=4）
3. 每个 group 的所有 REQ 都堆积到同一个 WP

**影响**: 
- WP-005 承载了 83% 的需求，成为事实上的"全能组件"
- 其他 WP 没有需求追溯，RTM（需求追溯矩阵）断裂
- 施工方不知道 WP-002~004, 006~008 具体要满足什么需求

**建议修复**:
1. 在 Frozen Blueprint 中为每个 module 标注 `supported_requirements` 字段
2. 编译器改为轮询分配或基于 module 功能匹配分配
3. 短期方案：按 module 数量均分 requirements，每个 WP 至少关联 1 个

---

### 4.4 constraints 全部为空

**状态**: 🟡 YELLOW

**问题**: 所有 8 个 WP 的 constraints 字段都是空数组 `[]`。

**根因分析**: 编译器从 `architecture.module_boundaries` 读取约束，但 Frozen Blueprint 中 `module_boundaries` 为空数组 `[]`。同时 `risks.forbidden_changes` 也为空。

**评估**: Frozen Blueprint v0.1 的 `missing_sections` 中已标注 `"contracts (v0.1: best effort, typically empty)"`，这是已知的 v0.1 限制。

**建议**: 在 Solution Pro → Frozen Blueprint 阶段增加 module boundaries 生成逻辑，至少包含：
- 技术栈约束（如 "仅使用 Python 标准库 + reportlab + python-docx"）
- 性能约束（如 "基线模式响应时间 < 5 秒"）
- 接口约束（如 "中间表示层必须兼容 JSON Resume Schema"）

---

### 4.5 forbidden_actions 为空

**状态**: 🟢 GREEN（符合预期）

**分析**: 
- Frozen Blueprint `risks.forbidden_changes` = `[]`（空数组）
- 因此 Ship Package `risk_contract.forbidden_actions` = `[]` 是正确的
- harmony_brief.forbidden_actions 同样为空，与 risk_contract 一致

**评估**: 对于个人工具项目，没有显式禁止变更是合理的。Frozen Blueprint 的 quality_gate 评分 0.93，necessity=1.0，说明需求定义完整。

---

## 5. Markdown 同步

**状态**: 🟡 YELLOW

**对比结果**:

| 检查项 | 状态 | 详情 |
|---|---|---|
| WP 数量一致 | ✅ | JSON: 8, MD: 8 |
| WP ID 一致 | ✅ | WP-001~008 |
| WP title 一致 | ✅ | 完全匹配 |
| Phase 一致 | ✅ | 完全匹配 |
| Dependencies 一致 | ✅ | 完全匹配 |
| Requirements 一致 | ✅ | 完全匹配 |
| Deliverables 一致 | ✅ | 完全匹配 |
| Acceptance 一致 | ✅ | 完全匹配 |
| Readiness 一致 | ✅ | ready_to_ship |
| Harmony Brief 一致 | ✅ | objective 截断到 100 字符（设计如此） |
| **缺少 acceptance_contract 章节** | ⚠️ | MD 中没有独立的 acceptance_contract 表格 |
| **缺少 risk_contract 章节** | ⚠️ | MD 中没有 risk_register 详情（6 条改进建议未展示） |
| **缺少 non_goals** | ⚠️ | MD 中未展示 non_goals（JSON 中也为空） |

**根因**: 编译器 `_generate_markdown()` 函数没有输出 acceptance_contract 和 risk_contract.risk_register 的完整内容。只输出了 blocking（空）和 forbidden（空）条件。

**影响**: MD 作为人类可读文档，丢失了 12 条验收标准和 6 条改进建议的详细信息。

**建议修复**: 在 `_generate_markdown()` 中增加：
1. `## Acceptance Contract` 章节（AC 表格）
2. `## Risk Register` 章节（改进建议列表）

---

## 总结

| 维度 | 状态 | 严重度 |
|---|---|---|
| 1. Schema 校验 | 🟢 GREEN | — |
| 2. 字段完整性 | 🟢 GREEN | — |
| 3. 类型一致性 | 🟢 GREEN | — |
| 4.1 source_blueprint "None vNone" | 🔴 RED | High |
| 4.2 acceptance_criteria 泛化 | 🔴 RED | High |
| 4.3 requirements 分配不均 | 🟡 YELLOW | Medium |
| 4.4 constraints 全部为空 | 🟡 YELLOW | Low (v0.1 已知限制) |
| 4.5 forbidden_actions 为空 | 🟢 GREEN | — (符合预期) |
| 5. Markdown 同步 | 🟡 YELLOW | Medium |

### 统计: **5 Green, 3 Yellow, 2 Red**

---

## 优先级修复建议

### P0 (必须修复)

1. **source_blueprint "None vNone"** — 编译器 `_safe_get` 或 f-string 逻辑有 bug，需排查为何 Frozen Blueprint 有值但产出为 "None vNone"
2. **acceptance_criteria 泛化** — 编译器需为每个 module 生成组件级验收标准，而非复制全局 AC

### P1 (建议修复)

3. **requirements 分配逻辑** — 当前按 group 粗暴分配导致 WP-005 承载 83% 需求，需改为基于 module 功能匹配
4. **Markdown 缺失章节** — 补充 acceptance_contract 表格和 risk_register 详情

### P2 (可延后)

5. **constraints 生成** — 依赖 Frozen Blueprint 提供 module_boundaries，需在 Solution Pro 阶段增强
6. **risk_register 格式** — 6 条 IMPROVE-recommendations 的 description 是 Python dict 字符串而非结构化 JSON，应改为嵌套对象

---

*审计员: Ship Pro Schema Auditor v0.1*
*审计方法: jsonschema Draft7Validator + 人工代码审查 + 交叉比对*
