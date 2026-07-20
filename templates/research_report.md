---
domain: research_pro
version: "{version}"
created: "{timestamp}"
session: "{session_id}"
trigger: "{trigger_type}"
---

# Research Report: {research_topic}

## 元信息

> **角色**: 权威数据

| 字段 | 值 |
|------|-----|
| research_topic | {topic} |
| sources_count | {source_count} |
| confidence_level | {confidence} |

## 研究问题

> **角色**: 上下文参考

1. {question_1}
2. {question_2}

## 研究发现

> **角色**: 权威数据

### 发现 1: {finding_title}

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| {option} | {pros} | {cons} | {rating} |

**来源**: {source}

## 建议

> **角色**: 决策记录

1. {recommendation_1}
2. {recommendation_2}
3. {recommendation_3}

## 引用

> **角色**: 权威数据

| # | 来源 | URL | 访问日期 |
|---|------|-----|----------|
| 1 | {source} | {url} | {date} |

## Gate 决策

> **角色**: 决策记录
> **Gate 结果语义**: PASS=研究可用 | CONDITIONAL=需补充验证 | FAIL=研究不可用

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 (Schema) | {l1_result} | {l1_reason} |
| L2 (LLM Judge) | {l2_result} ({l2_score}/100) | {l2_reason} |
| L3 (合并) | {l3_result} | {l3_reason} |
