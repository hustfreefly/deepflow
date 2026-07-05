---
name: solution-pro
description: "DeepFlow Solution Pro — 系统级解决方案设计引擎。触发：设计解决方案、架构设计、技术方案。"
version: "2.0.0"
---

# Solution Pro — Agent 执行指南

> **版本**: 2.0.0 | **架构**: Orchestrator → Planning + Research + Summary  
> **入口**: `domains/solution_pro/SKILL.md`  
> **单入口函数**: `run_solution_pro()`

## 快速入口

```python
from domains.solution_pro import run_solution_pro

result = run_solution_pro(
    user_input="你的需求描述",
    topic="项目名称",
)
# Main Agent spawn Orchestrator → 全权调度
```

## 详细执行指南

→ [domains/solution_pro/SKILL.md](../../domains/solution_pro/SKILL.md)

## 架构概览

```
Main Agent (depth-0)
  → exec: run_solution_pro(user_input, topic) → spawn params
  → sessions_spawn → Orchestrator (depth-1)

Orchestrator (depth-1): MasterOrchestrator
  → Phase 1: PlanningOrchestrator (规划)
  → Phase 2: ResearchOrchestrator (研究)
  → Phase 3: ReviewQCOrchestrator (审查 + 收敛)
  → ConvergenceLayer (收敛判定)
```

## Blackboard 路径

```
.deepflow/blackboard/{project}/
├── spec/living_spec.json         ← Spec Pro 产出
└── data/frozen_spec.json         ← Solution Pro 写入
```
