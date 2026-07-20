# Spec Requirements V2 — MD Schema 设计

## 设计原则
1. **AI Native**: LLM 是消费者，不需要程序化字段路径
2. **Walk-based**: 覆盖所有 JSON 字段，按实际存在渲染
3. **Frontmatter 最小化**: 只保留 3-5 个元字段
4. **Section 角色标注**: 每个 section 标注 `authority`（权威数据）或 `context`（参考上下文）

## YAML Frontmatter（3 字段）
```yaml
---
domain: spec_pro
version: "{spec_version}"
session: "{session_id}"
---
```

## MD Body Sections（完整覆盖）

### 必需 Sections（authority）

| # | Section | 对应 JSON 字段 | 角色 |
|:-:|:-------:|:-------------:|:----:|
| 1 | 元信息 | meta.* | authority |
| 2 | 需求概述 | confirmed.objective / narrative / core_summary | authority |
| 3 | 确认需求 | confirmed.* (所有子字段) | authority |
| 4 | 能力边界 | confirmed.capabilities | authority |
| 5 | 约束条件 | confirmed.constraints | authority |
| 6 | Gate 决策 | gate_summary | authority |

### 可选 Sections（context / authority）

| # | Section | 对应 JSON 字段 | 角色 | 何时渲染 |
|:-:|:-------:|:-------------:|:----:|:--------:|
| 7 | 推断需求 | inferred[] | context | inferred 非空 |
| 8 | 质量属性 | confirmed.quality_attributes | authority | quality_attributes 非空 |
| 9 | 用户显式指令 | confirmed.user_directives | authority | user_directives 非空 |
| 10 | 开放问题 | open_questions[] | context | open_questions 非空 |
| 11 | 护栏规则 | guardrails | authority | guardrails 非空 |
| 12 | 溯源信息 | traceability | context | traceability 非空 |
| 13 | 下游提示 | solution_pro_hints | context | solution_pro_hints 非空 |
| 14 | 路由建议 | route_recommendation | context | route_recommendation 非空 |
| 15 | 语义锚点 | semantic_anchors | authority | semantic_anchors 非空 |
| 16 | 对话摘要 | conversation_digest | context | conversation_digest 非空 |

## 各 Section 详细格式

### S1: 元信息
```markdown
## meta_info

| field | value |
|-------|-------|
| spec_version | {spec_version} |
| domain_type | {domain_type} |
| conversation_rounds | {rounds} |
```
> 动态行：只渲染 meta 中实际存在的字段

### S2: 需求概述
```markdown
## overview

{objective 或 narrative 或 core_summary 的文本}
```

### S3: 确认需求
```markdown
## confirmed_reqs

### REQ-ID Table

| REQ-ID | dimension | description | priority | status |
|--------|-----------|-------------|----------|--------|
| REQ-001 | {dimension} | {description} | P0 | confirmed |

### User Roles

| role | key_needs |
|------|-----------|
| {role} | {key_needs} |

### Pain Points
- {pain_point_1}
- {pain_point_2}

### Key Scenarios
- {scenario_1}
- {scenario_2}

### Success Metrics

| metric | target | priority |
|--------|--------|----------|
| {metric} | {target} | {priority} |

### Terms
- {term_1}
- {term_2}
```
> REQ-ID Table: 从 requirement_index 提取；若空则从 confirmed 子字段反向推导
> 其他子 section: 只渲染非空字段

### S4: 能力边界
```markdown
## capability_boundary

| category | content |
|----------|---------|
| always_do | {items} |
| should_do | {items} |
| never_do | {items} |
```

### S5: 约束条件
```markdown
## constraints

| key | value |
|-----|-------|
| {key} | {value} |
```
> 如果 constraints 是 list → 渲染为无序列表
> 如果 constraints 是 dict → 渲染为表格

### S6: Gate 决策
```markdown
## gate_decisions

| check_layer | result | reason |
|-------------|--------|--------|
| L1 (Schema) | PASS | ... |
| L3 (merge) | PASS | ... |
```

### S7: 推断需求（可选）
```markdown
## inferred

| hypothesis | confidence | status | source |
|------------|------------|--------|--------|
| {description} | {confidence} | {status} | {source} |
```

### S8: 质量属性（可选）
```markdown
## quality_attrs

| category | spec | priority |
|----------|------|----------|
| {category} | {spec} | {priority} |
```

### S9: 用户显式指令（可选）
```markdown
## user_directives

| dimension | directive | reason |
|-----------|-----------|--------|
| {dimension} | {directive} | {reason} |
```

### S10: 开放问题（可选）
```markdown
## open_questions

| id | question | context | blocking |
|----|----------|---------|----------|
| {id} | {question} | {context} | {blocking} |
```

### S11: 护栏规则（可选）
```markdown
## guardrails

### Zone 0: Immutable
- {rule_1}
- {rule_2}

### Zone 1: Verified Change
- {rule_1}

### Zone 2: Free Change
- {rule_1}
```
> 如果 guardrails 是 list-based → 渲染为普通列表
> 如果 guardrails 是 zone-based → 渲染为分 zone 列表

### S12: 溯源信息（可选）
```markdown
## traceability

### Input Sources
- {source_1}
- {source_2}

### Decision Provenance
| decision | source |
|----------|--------|
| {key} | {value} |
```

### S13: 下游提示（可选）
```markdown
## solution_pro_hints

### Focus Areas
- {area_1}
- {area_2}

### Anti-patterns
- {pattern_1}

### Layer2 Hints
- {hint_1}
```

### S14: 路由建议（可选）
```markdown
## route_recommendation

| field | value |
|-------|-------|
| suggested_engine | {engine} |
| suggested_mode | {mode} |
| complexity_score | {score} |
| confidence | {confidence} |
```

### S15: 语义锚点（可选）
```markdown
## semantic_anchors

| name | category | constraint | priority |
|------|----------|------------|----------|
| {name} | {category} | {constraint} | {priority} |
```

### S16: 对话摘要（可选）
```markdown
## conversation_summary

**summary**: {summary_text}

### Key Excerpts
- Round {n}: {excerpt}
```

## 覆盖率验证

### 投资域样本（11 confirmed keys）
- ✅ meta (5 keys) → S1
- ✅ confirmed.objective → S2
- ✅ confirmed.pain_points → S3
- ✅ confirmed.terms → S3
- ✅ confirmed.success_metrics → S3
- ✅ confirmed.users → S3
- ✅ confirmed.key_scenarios → S3
- ✅ confirmed.capabilities → S4
- ✅ confirmed.quality_attributes → S8
- ✅ confirmed.constraints (dict) → S5
- ✅ confirmed.integration → S3 (walk-based fallback)
- ✅ confirmed.risks → S3 (walk-based fallback)
- ✅ inferred (7 items) → S7
- ✅ guardrails (empty) → 不渲染
- **覆盖率: 100%**

### AI Loop 域样本（24 confirmed keys）
- ✅ meta (9 keys) → S1
- ✅ narrative / core_summary → S2
- ✅ confirmed.description → S2
- ✅ confirmed.core_decisions → S3 (walk-based)
- ✅ confirmed.architecture → walk-based 渲染
- ✅ confirmed.primitives → walk-based 渲染
- ✅ confirmed.tools → walk-based 渲染
- ✅ confirmed.innovation_mechanisms → walk-based 渲染
- ✅ confirmed.quality_attributes → S8
- ✅ confirmed.constraints (list) → S5
- ✅ confirmed.users → S3
- ✅ confirmed.key_scenarios → S3
- ✅ confirmed.success_metrics → S3
- ✅ confirmed.risks_and_assumptions → walk-based 渲染
- ✅ confirmed.capabilities → S4
- ✅ confirmed.user_directives → S9
- ✅ confirmed.direction_guard → walk-based 渲染
- ✅ confirmed.tools_policy → walk-based 渲染
- ✅ confirmed.budget_policy → walk-based 渲染
- ✅ confirmed.circuit_breaker → walk-based 渲染
- ✅ confirmed.concurrency → walk-based 渲染
- ✅ confirmed.core_insight → walk-based 渲染
- ✅ confirmed.entry_point → walk-based 渲染
- ✅ confirmed.exit_point → walk-based 渲染
- ✅ confirmed.first_use_case → walk-based 渲染
- ✅ guardrails (zone-based) → S11
- ✅ open_questions (4 items) → S10
- ✅ traceability → S12
- ✅ requirement_index (80 items) → S3 REQ-ID Table
- **覆盖率: 100%**

## 对比 V1

| 维度 | V1 (当前) | V2 (本方案) |
|:----:|:---------:|:----------:|
| Sections | 8 个固定 | 6 必需 + 10 可选 |
| Frontmatter | 3 字段 | 3 字段（不变） |
| 投资域覆盖率 | ~60% | 100% |
| AI Loop 域覆盖率 | ~30% | 100% |
| Walk-based fallback | 无 | 有（未知 key 自动渲染） |
| Section 角色标注 | 无 | authority / context |
