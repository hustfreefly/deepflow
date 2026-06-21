# Prompt TODO/PLACEHOLDER 审计报告

> **审计日期**: 2026-06-22
> **审计范围**: 9 个 prompt 文件（据恢复验证报告标记的 TODO/PLACEHOLDER）
> **审计结论**: ✅ **所有 9 个文件中均无实际 TODO/PLACEHOLDER 标记**

---

## 审计结果摘要

| 文件 | 报告中的 TODO 数 | 实际 TODO 数 | 状态 |
|------|:---:|:---:|:---:|
| ship_pro/prompts/architect.md | 2 | 0 | ✅ 无需处理 |
| ship_pro/prompts/decomposer.md | 1 | 0 | ✅ 无需处理 |
| ship_pro/prompts/ship_orchestrator.md | 2 | 0 | ✅ 无需处理 |
| solution/prompts/pipeline_orchestrator.md | 1 | 0 | ✅ 无需处理 |
| solution/prompts/pipeline_orchestrator_v4.md | 1 | 0 | ✅ 无需处理 |
| spec_pro/prompts/assess.md | 4 | 0 | ✅ 无需处理 |
| spec_pro/prompts/assess_guide.md | 1 | 0 | ✅ 无需处理 |
| spec_pro/prompts/guide.md | 1 | 0 | ✅ 无需处理 |
| spec_pro/prompts/parse_response.md | 2 | 0 | ✅ 无需处理 |
| **合计** | **15** | **0** | ✅ |

---

## 详细分析：恢复验证报告中的误判项

恢复验证报告标记的 15 个 "TODO" 实际均为以下三类**非 TODO 内容**：

### 类型 1：JSON 模板中的示例占位符（COMP-XXX / WP-XXX）

这些是 prompt 中 JSON 示例的**教学性占位符**，用于向 LLM 展示"此处应填入实际值"。

| 文件 | 行号 | 内容 | 性质 |
|------|------|------|------|
| architect.md | 74 | `"id": "COMP-XXX"` | JSON 模板示例，表示"从输入继承或自动生成" |
| architect.md | 97 | `"from": "COMP-XXX", "to": "COMP-YYY"` | 依赖关系示例模板 |
| decomposer.md | 146 | `"wp_id": "WP-XXX"` | risk_flags 示例模板 |

**判定**：✅ 合理的教学设计，不是 TODO。这些占位符是 prompt 的一部分，指导 LLM 如何填充实际值。

### 类型 2：反面示例中的 xxx（禁止行为演示）

这些是告诉 LLM **不要做什么** 的示例文本。

| 文件 | 行号 | 内容 | 性质 |
|------|------|------|------|
| ship_orchestrator.md | 21 | `❌ 说"waiting for xxx"然后不再继续` | 禁止行为示例 |
| ship_orchestrator.md | 166 | `❌ 禁止编造路径（如 /tmp/xxx.json）` | 禁止行为示例 |
| pipeline_orchestrator.md | 21 | `❌ 说"waiting for xxx"然后不再继续` | 禁止行为示例 |
| pipeline_orchestrator_v4.md | 21 | `❌ 说"waiting for xxx"然后不再继续` | 禁止行为示例 |

**判定**：✅ 反面示例，不是 TODO。

### 类型 3：评分规则中的示例模式（对标 XXX）

这些是评分指导中展示"用户可能怎么说"的示例文本。

| 文件 | 行号 | 内容 | 性质 |
|------|------|------|------|
| assess.md | 144 | `"参考业界规范/对标 XXX"` | 评分规则示例 |
| assess.md | 165 | `"参考业界最优实践" / "对标 XXX"` | 意图判断表示例 |
| assess.md | 197 | `"对标 XXX"等表述应记录` | 注意事项示例 |
| assess_guide.md | 114 | `"参考业界规范/对标 XXX"` | 评分哲学示例 |
| guide.md | 120 | `"对标XXX"/"你们来决定"` | 问题生成规则示例 |
| parse_response.md | 32 | `"对标 XXX"` → benchmark_reference | 解析规则示例 |
| parse_response.md | 58 | `"对标 XXX"` → benchmark_reference | 映射表示例 |

**判定**：✅ 评分/解析规则的示例文本，不是 TODO。

### 其他发现（非 TODO 的正常内容）

| 文件 | 行号 | 内容 | 性质 |
|------|------|------|------|
| ship_orchestrator.md | 142 | `sessions_yield()  # 等待完成事件` | 正常代码注释 |
| pipeline_orchestrator.md | 50-51, 102 | `sessions_yield()` 相关 | 正常代码注释 |
| pipeline_orchestrator_v4.md | 50-51, 102 | `sessions_yield()` 相关 | 正常代码注释 |

---

## 修复操作

- **A 类（补全内容）**: 0 项 — 无实际 TODO 需要补全
- **B 类（添加注释）**: 0 项 — 无需要标注的待定项
- **C 类（保留标记）**: 0 项 — 无合理的未来工作标记

**修改的文件**: 0 个

---

## 结论

恢复验证报告中提到的 15 个 TODO/PLACEHOLDER 标记**均为误判**。所有被标记的内容都是 prompt 文件中合理的设计元素：

1. **JSON 模板占位符**（COMP-XXX, WP-XXX）— 教学性示例，指导 LLM 输出格式
2. **反面示例**（waiting for xxx, /tmp/xxx.json）— 告诉 LLM 不要做什么
3. **评分规则示例**（对标 XXX）— 展示用户可能的表述模式

**无需任何修复操作。** 恢复验证报告的 TODO 计数可能来自早期版本的 prompt 文件，在后续的 v2.2/v3.0 重写中已被清除，但报告未同步更新。

---

## 建议

1. 更新恢复验证报告，将 TODO 计数归零
2. 如需在 prompt 中使用真正的 TODO 标记，建议采用统一格式：`<!-- TODO: 描述 -->` 以便于自动化扫描
