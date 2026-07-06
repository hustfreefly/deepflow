# Phase 3 Round 1 增量重跑结果

> **重跑时间**: 2026-06-19 00:59 (GMT+8)
> **修复项**: F3 (风险传递) + F4 (context_files 约束) + F5 (quality_report 固定字段)
> **Prompt SHAs**:
> - specifier: `49c3dee8...`
> - reviewer: `f84983d8...`
> - packager: `8d881e21...`

---

## 总览

| 案例 | 验证结果 | F3 修复 | F4 修复 | F5 修复 |
|------|----------|---------|---------|---------|
| Case 1 (AI客服, Format B, 12模块) | ✅ 5/5 PASS | ✅ 8/8 risks | ✅ 0 phantoms | ✅ 9/9 fields |
| Case 2 (智能简历, Format A, 8模块) | ✅ 5/5 PASS | ✅ 5/5 risks | ✅ 0 phantoms | ✅ 9/9 fields |
| Case 3 (TODO, Format A, 1模块) | ✅ 5/5 PASS | ✅ 1/1 risks | ✅ 0 phantoms | ✅ 9/9 fields |

---

## Case 1 — 企业级AI智能客服系统 (Format B, 12 组件, 8 WP)

| 维度 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| **验证结果** | 5/5 PASS | 5/5 PASS | 维持 |
| **AC 评分** | 88 (L4:23, L3:18) | 85.1 (L4:31, L3:4, L2:5, L1:1) | eval 脚本重新评分，结构不变 |
| **risk mitigation** | ❌ 8/8 空字符串 `""` | ✅ 8/8 非空 (`[RISK_NO_MITIGATION]`) | **F3 修复成功** |
| **context_files** | ❌ 8 个 WP 引用 `docs/xxx.md` 幻影文件 | ✅ 仅引用 `blueprint.json` + 上游 WP outputs | **F4 修复成功** |
| **quality_report 字段** | ❌ 使用 `reviewer_verdict`/`review_rounds` 等非标准名 | ✅ 使用 `verdict`/`round`/`total_issues`/`critical_issues`/`high_issues`/`medium_issues`/`low_issues`/`ac_quality_summary`/`reviewer_model` | **F5 修复成功** |
| **quality_report 额外字段** | 有 `module_coverage_rate`/`requirements_coverage_rate`/`review_summary` 等多余字段 | 无多余字段 | 清理完成 |

### F3 修复详情

修复前所有 risk_register 条目的 mitigation 为空字符串：
```json
// 修复前
{"id": "RISK-001", "description": "EU AI Act合规截止日逼近", "severity": "high", "mitigation": ""}
```

修复后标注 `[RISK_NO_MITIGATION]`（因 blueprint 未提供 mitigation）：
```json
// 修复后
{"id": "RISK-001", "description": "EU AI Act合规截止日逼近", "severity": "high",
 "mitigation": "[RISK_NO_MITIGATION] blueprint 未提供 mitigation，需补充"}
```

### F4 修复详情

修复前各 WP 的 context_files 引用不存在的文档：
```json
// 修复前 WP-001
"context_files": ["blueprint.json", "docs/data_layer_architecture.md"]  // ❌ 幻影
// 修复前 WP-003
"context_files": ["blueprint.json", "docs/compliance_requirements.md", "docs/gdpr_checklist.md"]  // ❌ 幻影
```

修复后仅引用可追溯来源：
```json
// 修复后 WP-001 (无依赖)
"context_files": ["blueprint.json"]
// 修复后 WP-005 (依赖 WP-001/002/003)
"context_files": ["blueprint.json", "infra/milvus/setup.yaml", "infra/postgresql/setup.yaml", ...]
```

### F5 修复详情

```json
// 修复前
"quality_report": {
  "reviewer_verdict": "PASS",           // ❌ 非标准名
  "ac_verifiability_score": 88,         // ❌ 非标准名
  "module_coverage_rate": 1.0,          // ❌ 多余字段
  "requirements_coverage_rate": 1.0,    // ❌ 多余字段
  "review_rounds": 1,                   // ❌ 非标准名
  "review_summary": "..."               // ❌ 多余字段
}

// 修复后
"quality_report": {
  "verdict": "PASS",                    // ✅ 固定字段
  "round": 0,                           // ✅ 固定字段
  "total_issues": 0,                    // ✅ 固定字段
  "critical_issues": 0,                 // ✅ 固定字段
  "high_issues": 0,                     // ✅ 固定字段
  "medium_issues": 0,                   // ✅ 固定字段
  "low_issues": 0,                      // ✅ 固定字段
  "ac_quality_summary": {"score": 88},  // ✅ 固定字段
  "reviewer_model": "bailian/qwen3.7-plus" // ✅ 固定字段
}
```

---

## Case 2 — 智能简历生成系统 (Format A, 8 组件, 6 WP)

| 维度 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| **验证结果** | 5/5 PASS | 5/5 PASS | 维持 |
| **AC 评分** | 77.8 (L4:12, L3:24) | 100.0 (L4:36) | eval 脚本评分提升（AC 含具体命令） |
| **risk mitigation** | ✅ 5/5 已有 mitigation | ✅ 5/5 非空 | 维持（blueprint 本身无 mitigation） |
| **context_files** | ❌ WP-001 引用 `docs/input_format_spec.md` | ✅ 仅引用 `blueprint.json` + 上游 outputs | **F4 修复成功** |
| **quality_report 字段** | ❌ 使用 `reviewer_verdict`/`issues_by_severity`/`review_rounds` | ✅ 使用 9 个固定字段 | **F5 修复成功** |
| **quality_report 额外字段** | 有 `module_coverage`/`requirements_coverage`/`dependency_sanity`/`key_recommendations` 等多余字段 | 无多余字段 | 清理完成 |

### F4 修复详情

```json
// 修复前 WP-001
"context_files": ["blueprint.json", "docs/input_format_spec.md"]  // ❌ 幻影

// 修复后 WP-001 (无依赖)
"context_files": ["blueprint.json"]
```

### F5 修复详情

```json
// 修复前
"quality_report": {
  "reviewer_verdict": "PASS_WITH_CONDITIONS",  // ❌
  "ac_verifiability_score": 77.8,              // ❌
  "module_coverage": "8/8 (100%)",             // ❌ 多余
  "requirements_coverage": "6/6 (100%)",       // ❌ 多余
  "dependency_sanity": "ok",                    // ❌ 多余
  "total_issues": 6,                            // ✅ (保留)
  "issues_by_severity": {"high": 0, "medium": 3, "low": 3},  // ❌ 非标准
  "review_rounds": 1,                           // ❌
  "key_recommendations": [...]                  // ❌ 多余
}

// 修复后
"quality_report": {
  "verdict": "PASS_WITH_CONDITIONS",
  "round": 0,
  "total_issues": 3,
  "critical_issues": 0,
  "high_issues": 0,
  "medium_issues": 2,
  "low_issues": 1,
  "ac_quality_summary": {"score": 78, "distribution": {"L4": 12, "L3": 24}},
  "reviewer_model": "bailian/qwen3.7-plus"
}
```

---

## Case 3 — 单模块TODO应用 (Format A, 1 组件, 1 WP)

| 维度 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| **验证结果** | 5/5 PASS | 5/5 PASS | 维持 |
| **AC 评分** | 87 | 80.0 (L4:3, L3:3) | eval 脚本重新评分 |
| **risk mitigation** | ✅ 已有 mitigation | ✅ 非空 | 维持 |
| **context_files** | ✅ 空数组（无依赖） | ✅ 空数组 | 维持（边界案例，无问题） |
| **quality_report 字段** | ⚠️ 部分正确（有 `verdict`）但缺少 `total_issues`/`critical_issues` 等 | ✅ 9 个固定字段齐全 | **F5 修复成功** |
| **quality_report 额外字段** | 有 `coverage_rate`/`dependency_sanity`/`issues_count` 等多余字段 | 无多余字段 | 清理完成 |

### F5 修复详情

```json
// 修复前
"quality_report": {
  "verdict": "PASS",                      // ✅ 正确
  "ac_verifiability_score": 87,           // ❌ 非标准名
  "coverage_rate": 1.0,                   // ❌ 多余
  "dependency_sanity": "ok",              // ❌ 多余
  "review_rounds": 0,                     // ❌ 非标准名
  "issues_count": 0                       // ❌ 非标准名
}

// 修复后
"quality_report": {
  "verdict": "PASS",
  "round": 0,
  "total_issues": 0,
  "critical_issues": 0,
  "high_issues": 0,
  "medium_issues": 0,
  "low_issues": 0,
  "ac_quality_summary": {"score": 80},
  "reviewer_model": "bailian/qwen3.7-plus"
}
```

---

## 修复效果总结

### F3 (风险传递) — 修复效果

| 案例 | 修复前 | 修复后 |
|------|--------|--------|
| Case 1 | ❌ 8/8 mitigation 为空字符串 | ✅ 8/8 标注 `[RISK_NO_MITIGATION]` |
| Case 2 | ✅ 5/5 已有 mitigation 文本 | ✅ 5/5 维持（blueprint 本身无 mitigation 字段） |
| Case 3 | ✅ 1/1 已有 mitigation 文本 | ✅ 1/1 维持 |

**结论**: F3 修复生效。Case 1 从"空字符串"变为"显式标注缺失"。

### F4 (context_files 约束) — 修复效果

| 案例 | 修复前幻影引用数 | 修复后幻影引用数 |
|------|-----------------|-----------------|
| Case 1 | 10 个 (`docs/xxx.md` × 10) | 0 |
| Case 2 | 1 个 (`docs/input_format_spec.md`) | 0 |
| Case 3 | 0 (边界案例) | 0 |

**结论**: F4 修复生效。所有幻影引用已清除。

### F5 (quality_report 固定字段) — 修复效果

| 案例 | 修复前字段名 | 修复后字段名 | 多余字段 |
|------|-------------|-------------|---------|
| Case 1 | `reviewer_verdict`/`review_rounds` 等 6 个非标准名 | 9 个固定字段 | 已清理 |
| Case 2 | `reviewer_verdict`/`issues_by_severity` 等 7 个非标准名 | 9 个固定字段 | 已清理 |
| Case 3 | `ac_verifiability_score`/`issues_count` 等 4 个非标准名 | 9 个固定字段 | 已清理 |

**结论**: F5 修复生效。所有 3 个案例的 quality_report 均使用固定字段名，无多余字段。

---

## 验证脚本结果

所有 3 个案例均通过 `e2e_test.py validate` 的 5/5 Agent 验证：

```
Case 1: ✅ 5/5 agents passed (Architect/Decomposer/Specifier/Reviewer/Packager)
Case 2: ✅ 5/5 agents passed
Case 3: ✅ 5/5 agents passed
```

关键验证项：
- Schema compliance: 100% field completeness, 0 errors
- AC verifiability: Case1=85.1, Case2=100.0, Case3=80.0 (all ≥ 70 threshold)
- Dependency graph: No cycles, no orphans, no invalid refs
- Eval overall: pass 5/5 for all cases
