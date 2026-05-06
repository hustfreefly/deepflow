# Solution Pro Orchestrator

> DeepFlow Solution Domain - 系统级方案设计引擎
> 当前版本: V3.1

## 版本历史

| 版本 | 日期 | 核心改进 |
|------|------|---------|
| V1.0 | 2026-04-28 | 架构重构，按Investment V4.0模式实现 |
| V2.0 | 2026-04-29 | 六阶段管线（Data Collection + Planning + Review + Research + Consolidator + Audit） |
| V3.0 | 2026-05-04 | 九阶段管线增加Fix + Harness Final + Summarizer，structured_requirements.json |
| **V3.1** | **2026-05-05** | **Planning Agent语义理解+自我验证+结构化理由** |

## V3.1 特性

### Planning Agent增强
- **语义理解**：不做关键词匹配，完整阅读REQ描述理解技术领域
- **术语澄清**：对易混淆术语明确含义（如"隔离"=硬件资源隔离）
- **自我验证**：6个问题确保分配合理性
- **结构化理由**：技术领域判定 + 专长匹配逻辑 + 产出能力评估 + 反例说明
- **置信度评分**：1-10分，≤6分重新考虑
- **allocation_rationale**：每个分配都有明确理由

### 验证效果
- Planning Harness: 81 → 91 (+10)
- 覆盖率: 75% → 87.5% (+12.5%)
- REQ-ID错配率: 24.2% → 0%

## 使用方式

```python
from domains.solution.orchestrator_agent import SolutionOrchestratorV21

orch = SolutionOrchestratorV21(
    topic='设计一个AI算力调度平台',
    solution_type='architecture',
    mode='rigorous',  # rigorous | standard
    constraints=['10000+并发', '延迟<5秒'],
    stakeholders=['平台方', '供给方', '需求方'],
    spawn_fn=sessions_spawn
)

orch.init()
result = orch.run_v3()
```

## 10阶段管线

1. Data Collection - 需求收集
2. Planning - 规划方案（含自我验证）
3. Reviewers（3并行）- 技术/商业/风险评审
4. Researchers（3并行）- 深度研究
5. Consolidator - 方案整合
6. Audit - 质量审计
7. Fix - 修复
8. Fixer Expert - 专家修复
9. Harness Final - 最终质量门禁
10. Summarizer - 最终文档

## 产出文件

| 文件 | 说明 |
|------|------|
| `stages/planning.json` | 规划方案（含allocation_rationale） |
| `stages/consolidator.json` | 整合方案 |
| `stages/audit.json` | 审计报告 |
| `stages/harness_final.json` | 最终质量门禁 |
| `final_solution.md` | 最终文档 |

## 相关文档

- [CHANGELOG](../CHANGELOG.md)
- [REFACTORING_SUMMARY](REFACTORING_SUMMARY.md)
- [契约文件](../cage/solution_orchestrator_v3_1.yaml)
