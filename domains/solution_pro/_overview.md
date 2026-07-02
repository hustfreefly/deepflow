# Solution Pro V2 — 代码文件索引

> 版本: 2.0 | 更新: 2026-06-29

## V2 架构概述

Solution Pro V2 采用三层模块化架构，由 MasterOrchestrator 调度三个独立模块串联执行：

```
MasterOrchestrator（极简调度器）
  ├── PlanningOrchestrator（三层：Meta → Expert ×N → Convergence）
  ├── ResearchOrchestrator（多专家并行 + Knowledge Freshness）
  └── ReviewQCOrchestrator（Fix Loop + Harness + Final Review + Convergence）
```

**设计原则**：
- Code controls flow（确定性逻辑），LLM generates content（语义理解）
- 模块间通过 Blackboard 文件通信
- 每模块有独立超时 + 降级策略
- 双层 State 验证支持断点续跑

---

## V2 核心代码文件索引

| 文件 | 职责 | 版本 |
|------|------|------|
| `master_orchestrator.py` | V2 Master 调度器：Planning → Research → ReviewQC 串联 | V2.0 |
| `planning_orchestrator.py` | Planning 模块：三层架构（Meta → Expert ×N → Convergence） | V1.0 |
| `research_orchestrator.py` | Research 模块：Knowledge Freshness + 多专家并行 + 收敛 | V2.1 |
| `review_qc_orchestrator.py` | ReviewQC 模块：Fix Loop + Harness + Final Review + Convergence | V2.0 |
| `module_orchestrator_base.py` | 模块基类：公共 run/stage_sequence/spawn 逻辑 | V2.0 |
| `convergence_layer.py` | 收敛层：Gate 评估 + 收敛逻辑（Planning/Research/ReviewQC 共享） | V2.0 |
| `blackboard.py` | Blackboard 管理：SolutionRegistry + V1/V2 路径注册 | V3.2 |
| `pipeline_exceptions.py` | Pipeline 异常定义：PipelineError, ModuleFailureError, ModuleTimeoutError | V2.0 |
| `task_builder.py` | Worker Task 构建 + Meta-Planner/Reviewer 任务生成 | V2.0 |
| `harness_scorer.py` | Harness 评分：Gate A Layer2 校准 + Gate B 关键评估 | V2.0 |
| `information_conservation.py` | 信息守恒契约验证 | V1.0 |

## V1 兼容代码（保留用于已有 session 续跑）

| 文件 | 职责 |
|------|------|
| `orchestrator_agent.py` | V1 主编排器 `_SolutionDispatcher` |
| `__init__.py` | 公共 API `run_solution_pro()`（V1 入口） |
| `planner.py` | V1 规划器辅助 |
| `completion_handler.py` | V1 完成检查 + Schema 运行时验证 |
| `frozen_spec.py` | V1 REQ-ID 冻结规格生成 |
| `control_contract.py` | V1 Planning 后确定性刷新 control_contract.json |
| `security_validator.py` | 输入清理 + 路径遍历检测 |
| `harness_validator.py` | V1 Harness 验证 |
| `harness_check_expert.py` | V1 Harness 专家 |
| `harness_scoring.py` | V1 Harness 评分辅助 |
| `progress_tracker.py` | V1 进度追踪 |
| `check_contract.py` | V1 契约检查 |
| `prefix_extractor.py` | Session ID 前缀提取 |
| `config.py` | 配置 |
| `pipeline_watcher.py` | Cron 巡检脚本（V1/V2 共用） |
| `normalize.py` | 数据规范化 |
| `llm_recorder.py` | LLM 调用记录 |
| `spec_context.py` | Spec 上下文管理 |
| `lightweight_spec_agent.py` | 轻量 Spec Agent（无 Spec Pro 时的 fallback） |
| `ai_native_auditor.py` | AI Native 审计 |
| `golden_case_runner.py` | Golden Case 运行器 |
| `fix_loop_state_machine.py` | Fix Loop 状态机 |

---

## V2 Prompt 清单

### Planning 模块

| Prompt | 用途 |
|--------|------|
| `meta_planner.md` | Layer 0: 分析任务 → 选择专家 → 配置 Gate |
| `expert_planner_base.md` | Layer 1: Expert Planner 基础模板 |
| `convergence_planner.md` | Layer 2: 合并约束 + 验证清单 + P0 追溯 |
| `reviewer_meta.md` | 验证 Meta-Planner 输出 |
| `reviewer_convergence.md` | 验证 Convergence 输出 |
| `harness_agent.md` | Gate A + Gate B 评估 |
| `planner_harness.md` | Planner Harness 验证 |

### Research 模块

| Prompt | 用途 |
|--------|------|
| `research_expert_base.md` | Research Expert 基础模板 |
| `consolidator.md` | 研究成果整合 |
| `researcher_harness.md` | Researcher Harness 验证 |
| `consolidator_harness.md` | Consolidator Harness 验证 |

### ReviewQC 模块

| Prompt | 用途 |
|--------|------|
| `fixer_expert_harness.md` | Fix Loop 修复 |
| `harness_v3.md` | Harness 对抗性检查 |
| `reviewer_harness.md` | 最终评审 |
| `summarizer_harness.md` | Summarizer Harness 验证 |
| `fixer_harness.md` | Fixer Harness 验证 |

### 通用

| Prompt | 用途 |
|--------|------|
| `orchestrator_completion.md` | 完成处理 |
| `summarizer.md` | 最终总结 |
| `ai_native_cognitive_base.md` | AI Native 认知基础 |
| `harness_scoring.md` | Harness 评分逻辑 |
| `auditor_harness.md` | Auditor Harness 验证 |

---

## V2 Schema 清单

所有 V2 Schema 定义在 `schemas/schemas.py`：

| Schema | 用途 |
|--------|------|
| `V2BaseSchema` | 基类（schema_version + timestamp） |
| `ExpertManifestSchema` | Meta-Planner 专家清单 |
| `ExpertPlanSchema` | Expert Planner 输出 |
| `UnifiedConstraintsSchema` | 统一约束集 |
| `VerificationChecklistSchema` | 验证清单 |
| `PlanningConvergenceSchema` | Planning 收敛点 |
| `ResearchExpertSchema` | Research Expert 输出 |
| `ResearchConsolidatorSchema` | Research 整合结果 |
| `ResearchConvergenceSchema` | Research 收敛点 |
| `DegradedFinalConvergenceSchema` | 降级最终收敛 |

---

## V2 测试清单

| 测试文件 | 覆盖范围 |
|----------|---------|
| `tests/test_schemas.py` | V2 Schema 定义验证 |
| `tests/test_base_classes.py` | V2 基类（ModuleOrchestrator）验证 |
| `tests/test_planning_orchestrator.py` | Planning 模块单元测试 |
| `tests/test_integration.py` | V2 端到端集成测试 |
| `tests/test_convergence_migration.py` | 收敛层迁移测试 |
| `tests/test_phase1_acceptance.py` | Phase 1 验收测试 |
| `tests/test_phase2_acceptance.py` | Phase 2 验收测试 |
| `tests/test_phase3_acceptance.py` | Phase 3 验收测试 |
| `tests/test_golden_case_001.py` | Golden Case 001 |
| `tests/test_golden_case_007.py` | Golden Case 007 |
| `tests/golden/` | Golden Case E2E 测试框架 |

---

## 配置

| 文件 | 用途 |
|------|------|
| `config/solution.yaml` | 域配置 |
| `config/watcher_config.json` | Cron 巡检配置 |

---

*V2.0 | 2026-06-29 | V2 三层架构代码索引*
