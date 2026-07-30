# Solution Pro V4.0 — 领域自适应方案设计引擎

> **版本**: V4.1.0 (2026-07-30)  
> **架构**: 纯 Agent Orchestrator（V4.0 简化版）  
> **测试**: 30 passed, 0 failures

---

## 架构概述

```
用户输入 + Living Spec
    ↓
DomainAnalysis（domain_analysis.py）
    ↓ DomainProfile（10 字段 Pydantic schema）
Orchestrator Agent（纯 LLM 调度器，depth-1）
    ↓ sessions_spawn
┌─────────────────────────────────────┐
│ Module 1: Planning（三层架构）       │
│   Layer 0: Meta-Planner → 选专家   │
│   Layer 1: Expert Planners ×N      │
│   Layer 2: Convergence Planner     │
│   → planning_convergence.json       │
│                                     │
│ Module 2: Research（多专家并行）     │
│   Stage 1: Knowledge Freshness     │
│   Stage 2: Expert Config（动态）   │
│   Stage 3: Research Experts ×M     │
│   Stage 4: Consolidation           │
│   Stage 5: Convergence             │
│   → research_convergence.json       │
│                                     │
│ Module 3: Summary（5+1 Phase）     │
│   Phase 1: Base Synthesis          │
│   Phase 2: Meta Summary Planner    │
│   Phase 3: Parallel Analysis ×N    │
│   Phase 4: Fix Judge → Fix Agent   │
│   Phase 5a: Document Generator     │
│   Phase 5b: JSON Extractor         │
│   → final_solution.md              │
└─────────────────────────────────────┘
    ↓
final_solution.md（MD source of truth）
    ↓ 自动生成
solution_track.json（Track 衍生）
    ↓
.completed 标记文件
```

### V4.0 简化变更

- ❌ 移除 Orchestrator 内置后置验证（L0 post_validator + L2 对抗审查 + L2 一致性检查）
- ✅ Orchestrator 简化为 3 步：初始化 → 模块执行 → 完成标记
- ✅ 状态机从 13 状态简化为 10 状态
- ✅ spawn 调用点从 5 个减少到 3 个
- ✅ 代码行数减少 23%（390→299 行）

> **Note**: V4.0 中 post_validator.py 和对抗 Agent 不再是 orchestrator 管线的内置步骤。
> 它们作为独立工具可供外部调用或按需手动触发。

### DAL（Domain Adaptation Layer）

- **domain_analysis.py**: LLM 分析输入 → DomainProfile（domain_id, complexity, risk_areas, scale 等 10 字段）
- **config/domain_loader.py**: YAML 配置降级为 few-shot 参考；仅 software 为 fallback，其他域走 YAML 或 LLM 自适应
- **三级 fallback**: 显式指定 → DomainAnalysis 推断 → software（默认）
- **支持领域**: 软件开发（默认）/ 投资分析 / 硬件设计 / 商业策略 / 任意新领域

---

## 文件索引

### 核心模块

| 文件 | 职责 |
|:---|:---|
| `__init__.py` | 公共 API `run_solution_pro()`（V4.0 入口） |
| `domain_analysis.py` | DAL 核心：DomainProfile + LLM prompt + parser |
| `blackboard.py` | Blackboard 状态持久化 |
| `pulse.py` | Pulse 脉冲调度（独立监控系统） |
| `post_validator.py` | L0 下限守卫（独立工具，非 orchestrator 内置） |

### Prompt 文件

| 文件 | 职责 |
|:---|:---|
| `prompts/orchestrator.md` | Orchestrator V4.0 调度器 prompt |
| `prompts/planning_module.md` | Planning Module Agent prompt |
| `prompts/research_module.md` | Research Module Agent prompt |
| `prompts/summary_module.md` | Summary Module Agent prompt |

### 辅助模块

| 文件 | 职责 |
|:---|:---|
| `harness_scorer.py` | Harness 评分（V4.0: 弱维度信号 + LLM 生成建议） |
| `information_conservation.py` | 信息守恒检查（V4.0: 参数化权重/阈值） |
| `task_builder.py` | Task 构建器（注入 domain_profile） |
| `control_contract.py` | 控制流契约 |
| `normalize.py` | 数据标准化 |
| `pipeline_watcher.py` | 管线监控 |
| `pipeline_exceptions.py` | 异常定义 |
| `llm_recorder.py` | LLM 调用记录 |

### 子目录

| 目录 | 内容 |
|:---|:---|
| `schemas/schemas.py` | Pydantic schema 定义 |
| `contracts/` | Stage/Pipeline 契约定义 |
| `config/domain_loader.py` | 域配置加载（V4.0: 仅 software fallback） |
| `prompts/` | 39 个 prompt 模板 |
| `tests/` | 30 tests |
| `scripts/` | 辅助脚本 |
| `eval/` | 评估工具 |

---

## 核心特性

### 断点续跑
- 双层 State 验证：`master_state.json` + `module_output.json`
- 模块级粒度，跳过已完成模块

### 超时降级

| 模块 | 默认超时 | 降级策略 |
|:---|:---|:---|
| Planning | 5 min | 使用 2 个通用 expert |
| Research | 15 min | 跳过，标记 degraded=true |
| Summary | 20 min | 降级为简化版合成 |

### 信息守恒
- 模块间通过 Blackboard 文件通信
- 所有 Stage 输出有 Pydantic Schema 验证
- REQ-ID 全链路追踪

---

## 快速开始

```python
from domains.solution_pro import run_solution_pro

# 运行 Solution Pro V4.0
result = run_solution_pro(
    user_input="需求描述",
    topic="主题",
    solution_type="team_design",
)

# 获取 spawn_params
spawn_params = result["spawn_params"]

# 使用 sessions_spawn 启动 Orchestrator
# sessions_spawn(**spawn_params)
```

---

## 版本历史

| 版本 | 日期 | 核心变更 |
|:---|:---|:---|
| **V4.1.0** | 2026-07-30 | ADR-009 MD-first：final_solution.md 为唯一真相源 + solution_track.json 衍生 |
| **V4.0.0** | 2026-07-27 | 移除 Step 4/5 后置验证，orchestrator 简化为 3 步 |
| **V3.1.0** | 2026-07-14 | 删除 Python orchestrator 层 + 新增对抗 Agent |
| **V2.1.1** | 2026-07-08 | AI Native 反模式修复：Cage F6/F7 结构化、harness 去硬编码 |
| **V2.1.0** | 2026-07-07 | DAL 领域自适应：DomainProfile 10 字段 + 4 YAML few-shot |
| **V2.0.0** | 2026-06-29 | 三层架构（Planning + Research + Summary）+ 断点续跑 |

### V4.1.0 变更详情（2026-07-30）— ADR-009 MD-first

- ✅ `final_solution.md` 成为唯一真相源（删除 `final_solution.json` fallback）
- ✅ `solution_track.json` 作为 Track 衍生（跨域元数据：semantic_anchors, req_ids）
- ✅ `living_spec.md` 为唯一输入源（删除 `frozen_spec.json` fallback）
- ✅ Ship Pro 已适配：读 `final_solution.md` + `solution_track.json`

### V4.0.0 变更详情（2026-07-27）

- ❌ 移除 Orchestrator 内置后置验证（L0 post_validator + L2 对抗审查 + L2 一致性检查）
- ❌ 移除 POST_VALIDATION 状态
- ✅ Orchestrator 简化为 3 步：初始化 → 模块执行 → 完成标记
- ✅ 状态机从 13 状态简化为 10 状态
- ✅ spawn 调用点从 5 个减少到 3 个
- ✅ 代码行数减少 23%（390→299 行）
- ✅ post_validator.py 和对抗 Agent 作为独立工具可供外部调用

### V3.1.0 变更详情（2026-07-14）

- ❌ 删除 Python orchestrator 层（MasterOrchestrator / PlanningOrchestrator / ResearchOrchestrator / SummaryOrchestrator）
- ❌ 删除 bridge 模式（FileBasedSpawnBridge）
- ❌ 删除 Gate A/B 数值评分（convergence_layer.py）
- ✅ Module Agent 直接通过 `sessions_spawn` 创建 Workers
- ✅ 新增对抗 Agent（语义质量审查 + 跨模块一致性检查）
- ✅ 保留 post_validator.py 作为 L0 下限守卫

---

## 禁止事项

- ❌ Python 代码中禁止直接 import OpenClaw SDK（使用 `sessions_spawn` 工具）
- ❌ Orchestrator 做语义判断（只做调度）
- ❌ 用正则/if-else 做语义分类或评分
- ❌ 手动拼接 stage 路径（使用 BlackboardManager API）

---

详细变更见 [CHANGELOG.md](../../CHANGELOG.md)
