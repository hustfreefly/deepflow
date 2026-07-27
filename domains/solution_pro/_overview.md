# Solution Pro V4.0 — 代码文件索引

> 版本: 4.0 | 更新: 2026-07-27

## V4.0 架构概述

Solution Pro V4.0 采用纯 Agent Orchestrator 架构，由 Orchestrator Agent（LLM 调度器）驱动三个独立模块串联执行：

```
Orchestrator Agent（纯 LLM 调度器，depth-1）
  ├── Planning Module Agent（depth-2）
  │   └── sessions_spawn → Worker Agents（depth-3）
  ├── Research Module Agent（depth-2）
  │   └── sessions_spawn → Worker Agents（depth-3）
  └── Summary Module Agent（depth-2）
      └── sessions_spawn → Worker Agents（depth-3）
```

**设计原则**：
- Code controls flow（确定性逻辑），LLM generates content（语义理解）
- 模块间通过 Blackboard 文件通信
- 每模块有独立超时 + 降级策略
- 双层 State 验证支持断点续跑

**V4.0 简化变更**：
- ❌ 移除 Orchestrator 内置后置验证（L0 post_validator + L2 对抗审查 + L2 一致性检查）
- ✅ Orchestrator 简化为 3 步：初始化 → 模块执行 → 完成标记
- ✅ 状态机从 13 状态简化为 10 状态
- ✅ spawn 调用点从 5 个减少到 3 个

---

## V4.0 核心代码文件索引

| 文件 | 职责 | 版本 |
|------|------|------|
| `__init__.py` | 公共 API `run_solution_pro()`（V4.0 入口） | 4.0.0 |
| `domain_analysis.py` | DAL 核心：DomainProfile + LLM prompt + parser | 4.0.0 |
| `blackboard.py` | Blackboard 管理：SolutionRegistry + 路径注册 | 4.0.0 |
| `pulse.py` | Pulse 脉冲调度（独立监控系统） | 4.0.0 |
| `post_validator.py` | L0 下限守卫（独立工具，非 orchestrator 内置） | 4.0.0 |
| `pipeline_exceptions.py` | Pipeline 异常定义 | 4.0.0 |
| `task_builder.py` | Worker Task 构建 + Meta-Planner 任务生成 | 4.0.0 |
| `harness_scorer.py` | Harness 评分：弱维度信号 + LLM 生成建议 | 4.0.0 |
| `information_conservation.py` | 信息守恒契约验证（参数化权重/阈值） | 4.0.0 |

---

## V4.0 Prompt 清单

### Orchestrator

| Prompt | 用途 |
|--------|------|
| `orchestrator.md` | V4.0 Orchestrator 调度器（3 步简化版） |

### Planning 模块

| Prompt | 用途 |
|--------|------|
| `planning_module.md` | Planning Module Agent prompt |
| `meta_planner.md` | Layer 0: 分析任务 → 选择专家 → 配置 Gate |
| `expert_planner_base.md` | Layer 1: Expert Planner 基础模板 |
| `convergence_planner.md` | Layer 2: 合并约束 + 验证清单 + P0 追溯 |
| `reviewer_meta.md` | 验证 Meta-Planner 输出 |
| `reviewer_convergence.md` | 验证 Convergence 输出 |

### Research 模块

| Prompt | 用途 |
|--------|------|
| `research_module.md` | Research Module Agent prompt |
| `research_expert_base.md` | Research Expert 基础模板 |
| `consolidator.md` | 研究成果整合 |

### Summary 模块

| Prompt | 用途 |
|--------|------|
| `summary_module.md` | Summary Module Agent prompt |
| `summary_base_synthesizer.md` | Phase 1: 基础方案合成 |
| `summary_meta_planner.md` | Phase 2: 审查规划 |
| `summary_analyzer_base.md` | Phase 3: 并行分析（含 Review Layer B） |
| `summary_fix_judge.md` | Phase 4: Fix Judge（质量判断） |
| `summary_fix_agent.md` | Phase 4: Fix Agent（问题修复） |
| `summary_harness_check.md` | Phase 4: Harness 对抗性检查 |
| `summary_refiner.md` | Phase 4: 方案精炼 |
| `summary_json_extractor.md` | Phase 5b: JSON 提取 → final_solution |

### 独立工具（非 orchestrator 内置）

| Prompt | 用途 |
|--------|------|
| `adversarial_quality_reviewer.md` | L2 对抗审查（独立调用） |
| `cross_module_consistency_checker.md` | L2 一致性检查（独立调用） |

### 通用

| Prompt | 用途 |
|--------|------|
| `ai_native_cognitive_base.md` | AI Native 认知基础 |
| `harness_scoring.md` | Harness 评分逻辑 |

---

## V4.0 Schema 清单

所有 V4.0 Schema 定义在 `schemas/schemas.py`：

| Schema | 用途 |
|--------|------|
| `ExpertManifestSchema` | Meta-Planner 专家清单 |
| `ExpertPlanSchema` | Expert Planner 输出 |
| `UnifiedConstraintsSchema` | 统一约束集 |
| `VerificationChecklistSchema` | 验证清单 |
| `PlanningConvergenceSchema` | Planning 收敛点 |
| `ResearchExpertSchema` | Research Expert 输出 |
| `ResearchConsolidatorSchema` | Research 整合结果 |
| `ResearchConvergenceSchema` | Research 收敛点 |

---

## V4.0 测试清单

| 测试文件 | 覆盖范围 |
|----------|---------|
| `tests/test_pulse.py` | Pulse 脉冲调度测试（30 tests） |
| `tests/test_schemas.py` | Schema 定义验证 |
| `tests/test_base_classes.py` | 基类验证 |

---

## 配置

| 文件 | 用途 |
|------|------|
| `config/solution.yaml` | 域配置 |
| `config/watcher_config.json` | Cron 巡检配置 |

---

*V4.0 | 2026-07-27 | V4.0 简化版代码索引*
