# Solution Pro V2.1.1 — 领域自适应方案设计引擎

> **版本**: V2.1.1 (2026-07-08)
> **架构**: DAL 领域自适应 + MasterOrchestrator → Planning（三层）+ Research（多专家并行）+ Summary（5+1 Phase 收敛）
> **测试**: 127 passed, 10 skipped, 0 failures

---

## 架构概述

```
用户输入 + Living Spec
    ↓
DomainAnalysis（domain_analysis.py）
    ↓ DomainProfile（10 字段 Pydantic schema）
MasterOrchestrator（master_orchestrator.py, 29 def）
    ↓ set_domain_profile() + 三级 fallback
┌─────────────────────────────────────────────┐
│ Module 1: Planning（三层架构）               │
│   Layer 0: Meta-Planner → 选专家 + 配 Gate  │
│   Layer 1: Expert Planners ×N（并行）       │
│   Layer 2: Convergence Planner → 合并验证   │
│   → planning_convergence.json               │
│                                             │
│ Module 2: Research（多专家并行研究）          │
│   Stage 1: Knowledge Freshness + web_search │
│   Stage 2: Expert Config（动态）            │
│   Stage 3: Research Experts ×M（并行）      │
│   Stage 4: Consolidation（去重+冲突检测）    │
│   Stage 5: Convergence                      │
│   → research_convergence.json               │
│                                             │
│ Module 3: Summary（5+1 Phase 收敛）         │
│   Phase 1: Base Synthesis                   │
│   Phase 2: Meta Summary Planner             │
│   Phase 3: Parallel Analysis ×N             │
│   Phase 4: Fix Judge → Fix Agent            │
│   Phase 5a: Document Generator              │
│   Phase 5b: JSON Extractor                  │
│   → final_solution.json + solution_document │
└─────────────────────────────────────────────┘
```

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
| `master_orchestrator.py` | 主编排器（29 def），统一入口 + DAL 注入 |
| `planning_orchestrator.py` | Planning 三层架构编排 |
| `research_orchestrator.py` | Research 多专家并行编排 |
| `summary_orchestrator.py` | Summary 5+1 Phase 收敛编排 |
| `module_orchestrator_base.py` | 模块编排器基类 |
| `domain_analysis.py` | DAL 核心：DomainProfile + LLM prompt + parser |
| `convergence_layer.py` | 收敛层：Gate A/B 重构（V2.1.1 P0 修复） |

### 辅助模块

| 文件 | 职责 |
|:---|:---|
| `blackboard.py` | Blackboard 状态持久化 |
| `state_manager.py` | 断点续跑状态管理 |
| `harness_scorer.py` | Harness 评分（V2.1.1: 弱维度信号 + LLM 生成建议） |
| `information_conservation.py` | 信息守恒检查（V2.1.1: 参数化权重/阈值） |
| `task_builder.py` | Task 构建器（注入 domain_profile） |
| `control_contract.py` | 控制流契约 |
| `normalize.py` | 数据标准化 |
| `pipeline_watcher.py` | 管线监控 |
| `pipeline_exceptions.py` | 异常定义 |
| `llm_recorder.py` | LLM 调用记录 |

### 子目录

| 目录 | 内容 |
|:---|:---|
| `schemas/schemas.py` | Pydantic schema 定义（Cage F6/F7 结构化字段） |
| `contracts/` | Stage/Pipeline 契约定义 |
| `config/domain_loader.py` | 域配置加载（V2.1.1: 仅 software fallback） |
| `prompts/` | 39 个 prompt 模板 |
| `tests/` | 137 tests |
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
from domains.solution_pro.master_orchestrator import MasterOrchestrator
from domains.solution_pro.blackboard import BlackboardManager

# 创建 Blackboard
session_id = "sol_{timestamp}"
bb = BlackboardManager(session_id)

# 保存 frozen_spec
bb.write("data/frozen_spec.json", frozen_spec)

# 创建并运行 MasterOrchestrator
master = MasterOrchestrator(blackboard=bb, spawn_fn=spawn_fn)
result = master.run(user_input="需求描述", config={"topic": "主题"})
```

---

## 版本历史

| 版本 | 日期 | 核心变更 |
|:---|:---|:---|
| **V2.1.1** | 2026-07-08 | AI Native 反模式修复：Cage F6/F7 结构化、harness 去硬编码、DAL 完善 |
| **V2.1.0** | 2026-07-07 | DAL 领域自适应：DomainProfile 10 字段 + 4 YAML few-shot + 16+ Prompt 泛化 |
| **V2.0.0** | 2026-06-29 | 三层架构（Planning + Research + Summary）+ 断点续跑 + 超时降级 |

### V2.1.1 修复详情（2026-07-08）

9 个反模式修复（3 P0 + 6 P1），清除代码中"用代码做语义判断"的反模式：

| 优先级 | 问题 | 修复 |
|:---|:---|:---|
| P0 | Gate B 关键词命中率判定 | → SKIPPED（不伪造语义判断） |
| P0 | 前 20 字符子串匹配研究利用率 | → [REF-xxx] 引用标记（确定性） |
| P0 | 硬编码四维度语义分 | → raw_metrics + Layer 2 LLM |
| P1 | Cage F6 关键词触发器 | → 结构化 control_flow_type 枚举 |
| P1 | Cage F7 正则提取阈值 | → 结构化 threshold_value 字段 |
| P1 | VERDICT_SCORE_MAP 硬编码映射 | → Fallback + 优先读 LLM 数值分 |
| P1 | harness 硬编码改进建议 | → 弱维度信号 + LLM 生成建议 |
| P1 | conservation 权重/阈值硬编码 | → DEFAULT_WEIGHTS + 参数化 |
| P1 | domain_loader 4 域硬编码 | → 仅 software fallback + YAML |

### V2.1.0 变更详情（2026-07-07）

- **DAL 引入**: domain_analysis.py (DomainProfile 10 字段) + domain_loader.py (4 YAML few-shot)
- **三级 fallback**: 显式指定 → DomainAnalysis 推断 → software 默认
- **术语统一**: "技术选型"→"关键选型"、"架构设计"→"方案设计"
- **Schema 开放**: DOMAIN_CATEGORIES Literal→str + SemanticAnchor.category 开放
- **Pipeline 修复**: ResearchOrchestrator 未传递 domain_profile 给 Worker

---

## 禁止事项

- ❌ Python 代码中禁止直接 import OpenClaw SDK（使用 `sessions_spawn` 工具）
- ❌ MasterOrchestrator 做语义判断（只做调度）
- ❌ 用正则/if-else 做语义分类或评分
- ❌ 手动拼接 stage 路径（使用 BlackboardManager API）

---

详细变更见 [CHANGELOG.md](../../CHANGELOG.md)
