# Solution Pro 2.0.0 — 代码文件索引

> 版本: 2.0 | 更新: 2026-06-29

## 2.0.0 架构概述

Solution Pro 2.0.0 采用三层模块化架构，由 MasterOrchestrator 调度三个独立模块串联执行：

```
MasterOrchestrator（极简调度器）
  ├── PlanningOrchestrator（三层：Meta → Expert ×N → Convergence）
  ├── ResearchOrchestrator（多专家并行 + Knowledge Freshness）
  └── SummaryOrchestrator（5+1 Phase 收敛模块，吸收了 ReviewQC 的质量保障功能）
```

**设计原则**：
- Code controls flow（确定性逻辑），LLM generates content（语义理解）
- 模块间通过 Blackboard 文件通信
- 每模块有独立超时 + 降级策略
- 双层 State 验证支持断点续跑

---

## 2.0.0 核心代码文件索引

| 文件 | 职责 | 版本 |
|------|------|------|
| `master_orchestrator.py` | 2.0.0 Master 调度器：Planning → Research → Summary 串联 | 2.0.0 |
| `planning_orchestrator.py` | Planning 模块：三层架构（Meta → Expert ×N → Convergence） | 2.0.0 |
| `research_orchestrator.py` | Research 模块：Knowledge Freshness + 多专家并行 + 收敛 | 2.0.0 |
| `summary_orchestrator.py` | Summary 模块：5+1 Phase 收敛（吸收了 ReviewQC 功能） | 2.0.0 |
| `module_orchestrator_base.py` | 模块基类：公共 run/stage_sequence/spawn 逻辑 | 2.0.0 |
| `convergence_layer.py` | 收敛层：Gate 评估 + 收敛逻辑（Planning/Research/Summary 共享） | 2.0.0 |
| `blackboard.py` | Blackboard 管理：SolutionRegistry + 2.0.0/2.0.0 路径注册 | 2.0.0 |
| `pipeline_exceptions.py` | Pipeline 异常定义：PipelineError, ModuleFailureError, ModuleTimeoutError | 2.0.0 |
| `task_builder.py` | Worker Task 构建 + Meta-Planner/Reviewer 任务生成 | 2.0.0 |
| `harness_scorer.py` | Harness 评分：Gate A Layer2 校准 + Gate B 关键评估 | 2.0.0 |
| `information_conservation.py` | 信息守恒契约验证 | 2.0.0 |

## 2.0.0 兼容代码（保留用于已有 session 续跑）

| 文件 | 职责 |
|------|------|
| `orchestrator_agent.py` | 2.0.0 主编排器 `_SolutionDispatcher` |
| `__init__.py` | 公共 API `run_solution_pro()`（2.0.0 入口） |
| `planner.py` | 2.0.0 规划器辅助 |
| `completion_handler.py` | 2.0.0 完成检查 + Schema 运行时验证 |
| `frozen_spec.py` | 2.0.0 REQ-ID 冻结规格生成 |
| `control_contract.py` | 2.0.0 Planning 后确定性刷新 control_contract.json |
| `security_validator.py` | 输入清理 + 路径遍历检测 |
| `harness_validator.py` | 2.0.0 Harness 验证 |
| `harness_check_expert.py` | 2.0.0 Harness 专家 |
| `harness_scoring.py` | 2.0.0 Harness 评分辅助 |
| `progress_tracker.py` | 2.0.0 进度追踪 |
| `check_contract.py` | 2.0.0 契约检查 |
| `prefix_extractor.py` | Session ID 前缀提取 |
| `config.py` | 配置 |
| `pipeline_watcher.py` | Cron 巡检脚本（2.0.0/2.0.0 共用） |
| `normalize.py` | 数据规范化 |
| `llm_recorder.py` | LLM 调用记录 |
| `spec_context.py` | Spec 上下文管理 |
| `lightweight_spec_agent.py` | 轻量 Spec Agent（无 Spec Pro 时的 fallback） |
| `ai_native_auditor.py` | AI Native 审计 |
| `golden_case_runner.py` | Golden Case 运行器 |
| `fix_loop_state_machine.py` | Fix Loop 状态机 |

---

## 2.0.0 Prompt 清单

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

### Summary 模块（吸收了 ReviewQC 功能）

| Prompt | 用途 |
|--------|------|
| `summary_base_synthesizer.md` | Phase 1: 基础方案合成 |
| `summary_meta_planner.md` | Phase 2: 审查规划 |
| `summary_analyzer_base.md` | Phase 3: 并行分析（含 Review Layer B） |
| `summary_fix_judge.md` | Phase 4: Fix Judge（质量判断） |
| `summary_fix_agent.md` | Phase 4: Fix Agent（问题修复） |
| `summary_harness_check.md` | Phase 4: Harness 对抗性检查 |
| `summary_refiner.md` | Phase 4: 方案精炼 |
| `summary_json_extractor.md` | Phase 5b: JSON 提取 → final_solution |

### 通用

| Prompt | 用途 |
|--------|------|
| `orchestrator_completion.md` | 完成处理 |
| `summarizer.md` | 最终总结 |
| `ai_native_cognitive_base.md` | AI Native 认知基础 |
| `harness_scoring.md` | Harness 评分逻辑 |
| `auditor_harness.md` | Auditor Harness 验证 |

---

## 2.0.0 Schema 清单

所有 2.0.0 Schema 定义在 `schemas/schemas.py`：

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

## 2.0.0 测试清单

| 测试文件 | 覆盖范围 |
|----------|---------|
| `tests/test_schemas.py` | 2.0.0 Schema 定义验证 |
| `tests/test_base_classes.py` | 2.0.0 基类（ModuleOrchestrator）验证 |
| `tests/test_planning_orchestrator.py` | Planning 模块单元测试 |
| `tests/test_integration.py` | 2.0.0 端到端集成测试 |
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

*2.0.0 | 2026-06-29 | 2.0.0 三层架构代码索引*
