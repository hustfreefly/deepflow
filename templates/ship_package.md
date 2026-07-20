---
domain: ship_pro
version: "{version}"
created: "{timestamp}"
session: "{session_id}"
upstream: "{upstream_session}"
---

# Ship Package: {project_name}

## 元信息

> **角色**: 权威数据

| 字段 | 值 |
|------|-----|
| package_version | {version} |
| total_wp | {wp_count} |
| total_estimated_hours | {total_hours} |
| critical_path | {critical_path} |

## Work Package 清单

> **角色**: 权威数据

| WP-ID | 名称 | 优先级 | 依赖 | 预估工时 | 交付物 | 验收标准 |
|-------|------|--------|------|----------|--------|----------|
| WP-001 | {name} | P0 | - | {hours}h | {deliverable} | {acceptance_criteria} |

## 执行顺序

> **角色**: 权威数据

{execution_order_diagram}

## REQ-ID 追溯

> **角色**: 权威数据

| REQ-ID | 覆盖 WP | 验收标准关联 |
|--------|---------|--------------|
| REQ-001 | WP-{ids} | {acceptance_criteria} |

## Gate 决策

> **角色**: 决策记录
> **Gate 结果语义**: PASS=进入 Deliver Pro | CONDITIONAL=Deliver Pro 需额外验证 | FAIL=阻塞，需 Solution Pro 重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | {l1_result} | {l1_reason} |
| L2 (LLM Judge) | {l2_result} ({l2_score}/100) | {l2_reason} |
| L3 (合并) | {l3_result} | {l3_reason} |
