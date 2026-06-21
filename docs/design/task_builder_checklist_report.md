# Task Builder Checklist 核对报告

**日期**: 2026-06-21  
**核对人**: AI Assistant  
**基线版本**: 887c300 (2026-06-11)  
**当前版本**: 1904 行 (commit 5258074)

---

## 执行摘要

完成了 task_builder.py 的 9 项 checklist 核对，发现并修复了 2 个确定性 bug，确认 4 项已存在修复，2 项无需修复，1 项为功能增强暂不处理。

**最终通过率**: 7/9 (78%)

---

## 核对详情

### ✅ #1 STAGE_OUTPUT_SCHEMA 定义 requirement_evidence

**状态**: 已修复  
**问题**: schema 的 `required` 数组中缺少 `"requirement_evidence"` 字段  
**修复**: 
- 在 `required` 数组中添加了 `"requirement_evidence"`
- 添加了完整的字段定义：`type: array`, `items` 包含 `req_id`、`status`、`evidence`、`confidence` 等字段
- 验证通过：导入成功，schema 结构正确

### ✅ #2 validate_stage_output() decision 一致性

**状态**: 已修复  
**问题**: decision 枚举包含 `"PASS_WITH_CONDITIONS"`，但 harness_scorer.py 不产生该值  
**修复**:
- STAGE_OUTPUT_SCHEMA 中的 decision 枚举：删除 `"PASS_WITH_CONDITIONS"`
- validate_stage_output() 中的 valid_decisions 列表：删除 `"PASS_WITH_CONDITIONS"`
- 现在与 harness_scorer.py 的 DecisionType 定义完全一致：`["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]`
- 验证通过：导入成功，枚举值正确

### ⏸️ #3 HARNESS_EXEMPT_STAGES 豁免规则

**状态**: 不修复  
**说明**: 
- data_collection、planning、summarizer 被豁免，不检查 requirement_evidence（行 341）
- 这是设计决策，非 bug
- 改动风险高，需要评估对下游的影响
- 当前代码已经运行稳定，暂不修改

### ✅ #4 build_harness_final_task() 替换 layer2_constraints

**状态**: 无需修复  
**说明**:
- 检查 harness_v3.md 模板（199 行），未发现 `{layer2_constraints}` 变量
- 检查 build_harness_final_task() 函数（1353-1450 行），确认该函数没有替换 `{layer2_constraints}` 的逻辑
- 模板中使用的变量包括：`{{ stage_number }}`、`{{ check_type }}`、`{{ harness_scoring }}`、`{{ input_stage }}`、`{{ completeness_items }}` 等，但没有 `{layer2_constraints}`
- 结论：这不是 bug，无需修复

### ✅ #5 build_fixer_task_with_audit() 成功路径注入

**状态**: 已存在修复  
**说明**:
- 差异 #9 显示：`return final_prompt` → `return inject_req_traceability(final_prompt, session_id)`
- 检查当前代码（行 1014）：成功路径已经调用了 `inject_req_traceability()`
- 检查当前代码（行 1070）：失败路径也已经调用了 `inject_req_traceability()`
- 结论：修复已存在，无需再次修改

### ✅ #6 build_data_collection_task() 输出路径

**状态**: 已存在修复  
**说明**:
- 差异 #3 显示：`"data/"` → `"data_collection"`
- 检查当前代码（行 471）：已经使用 `_get_stage_path(session_id, "data_collection")`
- 结论：修复已存在，无需再次修改

### ✅ #7 build_designer_task() 输入路径

**状态**: 已存在修复  
**说明**:
- 差异 #7 显示：`"data/"` → `"data_collection"`
- 检查当前代码（行 790）：已经使用 `_get_stage_path(session_id, "data_collection")`
- 结论：修复已存在，无需再次修改

### ✅ #8 build_deliver_task() 读取 design

**状态**: 已存在修复  
**说明**:
- 差异 #11 显示：`"stages/design.md"` → `"design"`
- 检查当前代码（行 1122）：已经使用 `_get_stage_path(session_id, "design")`
- 结论：修复已存在，无需再次修改

### ⏸️ #9 build_researcher_task() max_iterations

**状态**: 不修复  
**说明**:
- 检查函数签名（行 651-660）：没有 `max_iterations` 参数
- 这是功能增强，非必要修复
- 当前 Researcher 只能进行单轮研究，如果未来需要多轮迭代功能再添加
- 结论：暂不修复

---

## 已确认实施的改动（来自 887c300 到当前的 14 处差异）

| # | 改动内容 | 行号 | 状态 |
|---|---------|------|------|
| 1 | 导入 normalize 模块 | 36 | ✅ 已存在 |
| 2 | REQ_TRACEABILITY_INSTRUCTION 文本微调 | 66 | ✅ 已存在 |
| 3 | data_collection 输出路径修复 | 471 | ✅ 已存在 |
| 4 | success_metrics 格式化逻辑改进 | 542-543 | ✅ 已存在 |
| 5 | existing_systems 格式化注释 | 553 | ✅ 已存在 |
| 6 | researcher_task 中 users 格式化改进 | 693, 704 | ✅ 已存在 |
| 7 | designer_task 中数据收集路径修复 | 790 | ✅ 已存在 |
| 8 | auditor_task 中 users 格式化改进 | 839, 850 | ✅ 已存在 |
| 9 | fixer_task 成功路径注入 REQ 追踪 | 1014 | ✅ 已存在 |
| 10 | fixer_task 失败路径注入 REQ 追踪 | 1070 | ✅ 已存在 |
| 11 | deliver_task 中设计方案路径修复 | 1122 | ✅ 已存在 |
| 12 | harness_final_task 中 users 格式化改进 | 1229 | ✅ 已存在 |

---

## 修复汇总

### 已修复（2 项）
1. STAGE_OUTPUT_SCHEMA 添加 requirement_evidence 字段定义
2. decision 枚举删除 PASS_WITH_CONDITIONS，与 harness_scorer.py 保持一致

### 已存在修复（4 项）
1. build_fixer_task_with_audit() 成功路径注入
2. build_data_collection_task() 输出路径
3. build_designer_task() 输入路径
4. build_deliver_task() 读取 design

### 无需修复（2 项）
1. HARNESS_EXEMPT_STAGES 豁免规则（设计决策）
2. build_harness_final_task() 替换 layer2_constraints（模板中无此变量）

### 暂不修复（1 项）
1. build_researcher_task() max_iterations（功能增强）

---

## 验证结果

```python
✅ 导入成功
✅ STAGE_OUTPUT_SCHEMA.required = ['status', 'stage', 'covered_req_ids', 'requirement_evidence']
✅ Decision enum = ['PASS', 'WARNING', 'CRITICAL_WARNING', 'BLOCK_RECOMMENDATION']
```

---

## 下一步

task_builder.py 的修复已完成，可以进入下一个待重建模块：
1. ✅ task_builder.py（已完成）
2. solution/QUALITY_GUIDE.md（待重建）
3. spec_pro/eval/harness.py（待重建）
4. spec_pro/QUALITY_GUIDE.md（待重建）
