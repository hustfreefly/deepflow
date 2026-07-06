# 编排代码层泛化性审计报告

> Agent C | 模型: qwen3.7-max | 耗时: 2m50s

## 汇总评分

| 文件 | 评分 | 严重问题数 | 核心判断 |
|------|:---:|:---------:|---------|
| module_orchestrator_base.py | 8/10 | 0C/1m | 最泛化的编排基础设施 |
| master_orchestrator.py | 7/10 | 0C/2M | 调度流程基本通用，stage名硬编码 |
| convergence_layer.py | 7/10 | 0C/2M | 收敛机制通用，评分维度偏软 |
| planning_orchestrator.py | 6/10 | 0C/1M/2m | 三层架构通用，专家类型偏软 |
| research_orchestrator.py | 5/10 | 1C/2M | Generalist Expert 硬编码 "General Software Architecture" |
| summary_orchestrator.py | 5/10 | 1C/1M | Summarizer 输出模板硬编码软件方案结构 |
| task_builder.py | 3/10 | 3C/3M | **最严重** — 大量软件硬编码 |
| harness_scorer.py | 6/10 | 0C/1M/2m | 四维度通用，检查项偏软 |

**综合泛化性评分：5.9/10**

## CRITICAL 发现

### 1. task_builder.py（3/10）— 3 个 CRITICAL
- Designer Task 输出结构：architecture/components/interfaces/data_model — 全软件
- 种子 URL：技术文档站（阿里云开发者/AWS架构/Martin Fowler）
- Reviewer Technical 检查项：架构设计/技术选型/性能指标/扩展性/技术债务

### 2. research_orchestrator.py（5/10）— 1 个 CRITICAL
```python
"domain": "General Software Architecture"  # ← 硬编码
```
- fallback 搜索查询："software architecture best practices 2025"
- ultimate fallback 风险领域默认 "architecture"

### 3. summary_orchestrator.py（5/10）— 1 个 CRITICAL
```python
"- 方案概述\n- 架构设计\n- 技术选型（含对比）\n- 实施计划\n- 风险缓解\n- 约束覆盖追溯"
```
- 默认 Analyzer fallback: "architecture_reviewer"

## MAJOR 发现

### 4. master_orchestrator.py — STAGE_SEQUENCE 固定
```python
STAGE_SEQUENCE = [
    {"stage": "spec_pro", ...},
    {"stage": "planning", ...},
    {"stage": "research", ...},
    {"stage": "summary", ...},
]
```
- solution_type 硬编码 "software_architecture"

### 5. research_orchestrator.py — fallback 全软件
- `"software architecture best practices 2025"`
- `"{topic} architecture patterns"`
- `"{topic} known pitfalls and anti-patterns"`

### 6. task_builder.py — Harness Final 检查项全软件
- "容错机制"、"数据流"、"测试策略"、"监控运维"、"CAPEX/OPEX"
- Worker 角色预设全软件（reviewer_technical, researcher_expert_1）

## 泛化性良好的部分
- ✅ module_orchestrator_base.py（8/10）— BlackboardManager API + checkpoint + timeout 完全通用
- ✅ convergence_layer.py（7/10）— Gate 评估 + 收敛逻辑通用
- ✅ harness_scorer.py 四维度（6/10）— completeness/necessity/alignment/global_impact 通用

## 修复优先级

| # | 文件 | 修复内容 | 预估工时 |
|---|------|---------|---------|
| 1 | task_builder.py | Designer/Reviewer/种子URL 全部参数化 | 2-3天 |
| 2 | research_orchestrator.py | Generalist domain 动态化 + fallback 查询模板化 | 1天 |
| 3 | summary_orchestrator.py | Summarizer 输出模板从 frozen_spec 动态获取 | 1天 |
| 4 | master_orchestrator.py | STAGE_SEQUENCE 配置化 + solution_type 参数化 | 0.5天 |
