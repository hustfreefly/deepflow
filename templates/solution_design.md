---
domain: solution_pro
version: "{version}"
created: "{timestamp}"
session: "{session_id}"
upstream: "{upstream_session}"
---

# Solution Design: {project_name}

## 元信息

> **角色**: 权威数据

| 字段 | 值 |
|------|-----|
| solution_version | {version} |
| domain_id | {domain_id} |
| covered_req_count | {req_count} |
| architecture_layers | {layers} |
| total_components | {components} |

## 需求覆盖矩阵

> **角色**: 权威数据

| REQ-ID | 覆盖状态 | 对应组件 | 设计决策 |
|--------|----------|----------|----------|
| REQ-001 | ✅ covered | {component} | {decision} |

## 方案结构

> **角色**: 权威数据

### 分层架构

| 层 | 组件 | 职责 |
|----|------|------|
| {layer_name} | {component} | {responsibility} |

### 数据流

{dataflow_diagram}

## 执行计划

> **角色**: 上下文参考

| 阶段 | 内容 | 预估工时 | 风险 |
|------|------|----------|------|
| Phase 1 | {content} | {hours}h | {risk} |

## 质量属性实现

> **角色**: 权威数据

| REQ-ID | 质量属性 | 实现策略 |
|--------|----------|----------|
| REQ-{id} | {attribute} | {strategy} |

## Gate 决策

> **角色**: 决策记录
> **Gate 结果语义**: PASS=进入 Ship Pro | CONDITIONAL=Ship Pro 需额外验证 | FAIL=阻塞，需 Spec Pro 重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | {l1_result} | {l1_reason} |
| L2 (LLM Judge) | {l2_result} ({l2_score}/100) | {l2_reason} |
| L3 (合并) | {l3_result} | {l3_reason} |
