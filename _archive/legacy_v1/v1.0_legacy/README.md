# V1.0 Legacy - DeepFlow Orchestrator

## 概述

此目录包含 DeepFlow V1.0 版本的 orchestrator 实现，作为历史参考和 fallback 方案保留。

## 文件说明

| 文件 | 说明 |
|------|------|
| `orchestrator_agent.py` | V1.0 的 orchestrator 实现，基于硬编码的阶段执行逻辑 |
| `pipeline_engine_orchestrator.md` | V1.0 的 pipeline engine 设计文档 |

## V1.0 的功能和限制

### 功能
- 基本的流水线执行能力
- 顺序执行各阶段（data_collection → research → audit → fix → verify → summarize）
- 简单的错误处理

### 限制
1. **无契约验证**：输入输出没有 YAML 契约验证，容易出错
2. **硬编码逻辑**：阶段执行逻辑硬编码在 Python 代码中，难以扩展
3. **无多轮迭代**：不支持收敛检测和自动迭代
4. **无 Blackboard**：阶段间数据传递通过返回值，缺乏持久化
5. **无并行执行**：所有阶段串行执行，效率低
6. **无 Worker 抽象**：没有 researcher/auditor/fixer 等角色抽象

## 何时使用 V1.0（Fallback）

以下情况可以考虑使用 V1.0：

1. **V2.0 出现严重 bug**：当 V2.0 的契约系统或 Blackboard 出现无法快速修复的问题时
2. **简单任务不需要复杂功能**：对于只需要单次执行的简单分析任务
3. **调试对比**：用于对比 V1.0 和 V2.0 的行为差异，定位问题

## 如何切换回 V1.0

```python
# 使用 V1.0 orchestrator
from .deepflow.ARCHIVED.v1.0_legacy.orchestrator_agent import OrchestratorAgent

orchestrator = OrchestratorAgent(domain="investment")
result = orchestrator.run({"code": "300604.SZ", "name": "长川科技"})
```

## 迁移到 V2.0

请参考 `../MIGRATION_GUIDE.md` 了解如何从 V1.0 迁移到 V2.0。

---

*最后更新: 2026-04-20*
