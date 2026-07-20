---
domain: spec_pro
version: "{version}"
created: "{timestamp}"
session: "{session_id}"
---

# Spec Requirements: {project_name}

## 元信息

> **角色**: 权威数据

| 字段 | 值 |
|------|-----|
| spec_version | {version} |
| quality_score | {score} |
| quality_level | {level} |
| conversation_rounds | {rounds} |
| domain_id | {domain_id} |
| domain_label | {domain_label} |

## 需求概述

> **角色**: 上下文参考

{objective}

## 确认需求

> **角色**: 权威数据

### REQ-ID 追溯表

| REQ-ID | 维度 | 需求描述 | 优先级 | 来源轮次 | 状态 |
|--------|------|----------|--------|----------|------|
| REQ-001 | {dimension} | {description} | P0 | Round 1 | confirmed |

### 用户角色

| 角色 | 关键需求 |
|------|----------|
| {role} | {key_needs} |

### 能力边界

| 分类 | 内容 |
|------|------|
| Always Do | {always_do} |
| Should Do | {should_do} |
| Never Do | {never_do} |

## 推断需求（待确认）

> **角色**: 上下文参考

| 假设 | 置信度 | 状态 |
|------|--------|------|
| {hypothesis} | {confidence} | pending |

## 质量属性

> **角色**: 权威数据

| 类别 | 规格 | 优先级 |
|------|------|--------|
| {category} | {spec} | P0 |

## 对话摘要

> **角色**: 上下文参考

**总结**: {summary}

**关键摘录**:
- Round 1: {excerpt_1}
- Round 2: {excerpt_2}

## Gate 决策

> **角色**: 决策记录
> **Gate 结果语义**: PASS=进入交接阶段 | CONDITIONAL=下游需额外验证以下条件 | FAIL=阻塞，需上游重新输出

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | {l1_result} | {l1_reason} |
| L2 (LLM Judge) | {l2_result} ({l2_score}/100) | {l2_reason} |
| L3 (合并) | {l3_result} | {l3_reason} |
