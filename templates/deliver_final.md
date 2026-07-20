---
domain: deliver_pro
version: "{version}"
created: "{timestamp}"
session: "{session_id}"
upstream: "{upstream_session}"
---

# Deliver Final: {project_name}

## 元信息

> **角色**: 权威数据

| 字段 | 值 |
|------|-----|
| deliverable_version | {version} |
| total_files | {file_count} |
| total_size_kb | {size_kb} |
| format | {format} |

## 交付物清单

> **角色**: 权威数据

| 交付物 | 类型 | 来源 WP | 路径 |
|--------|------|---------|------|
| {name} | {type} | WP-{id} | {path} |

## 执行指南

> **角色**: 上下文参考

1. **环境准备**: {env_prep}
2. **部署顺序**: {deploy_order}
3. **验证步骤**: {verify_steps}

## 验收标准汇总

> **角色**: 权威数据

| REQ-ID | 验收标准 | 验证方法 |
|--------|----------|----------|
| REQ-001 | {criteria} | {method} |

## Gate 决策

> **角色**: 决策记录
> **Gate 结果语义**: PASS=交付完成 | CONDITIONAL=交付但需人工复核 | FAIL=阻塞，需上游重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (完整性) | {l1_result} | {l1_reason} |
| L2 (LLM Judge) | {l2_result} ({l2_score}/100) | {l2_reason} |
| L3 (合并) | {l3_result} | {l3_reason} |
