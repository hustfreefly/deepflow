# Solution Pro 2.0.0 — 系统级解决方案设计引擎

> 通过三层模块化架构自动化生成高质量技术解决方案

## 当前版本

- **版本**: 2.0.0 (三层架构)
- **架构**: MasterOrchestrator → Planning（三层）+ Research（多专家并行）+ Summary（5+1 Phase 收敛）
- **模型**: 默认使用 Qwen 3.7 Plus

## 快速开始

### 1. 初始化 Blackboard + MasterOrchestrator

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
result = master.run(user_input="需求描述", config={"topic": "主题", ...})
```

### 2. 执行完整流程

参见 [SKILL.md](SKILL.md) 中的 2.0.0 执行指南。

### 3. 验证结果

```bash
# 2.0.0 集成测试
python3 tests/test_integration.py

# 2.0.0 Schema 验证
python3 tests/test_schemas.py

# Golden Case 验证
python3 tests/test_golden_case_001.py
```

## 2.0.0 架构概述

### Module 1: Planning（三层架构）

```
Layer 0: Meta-Planner → 分析任务 → 选择专家 → 配置 Gate
Layer 1: Expert Planners ×N（并行）→ 各自生成约束/风险/验收标准
Layer 2: Convergence Planner → 合并 + 验证 + P0 REQ 追溯
```

**输出**: `planning_convergence.json`

### Module 2: Research（多专家并行研究）

```
Stage 1: Knowledge Freshness → LLM 提取查询 → web_search → 压缩
Stage 2: Expert Config → 从 planning_output.risk_areas 动态确定
Stage 3: Research Experts ×M（并行 + 迭代）→ 各自研究成果
Stage 4: Consolidation → 批量去重 + 冲突检测 + 分层分类
Stage 5: Convergence → research_convergence.json
```

**输出**: `research_convergence.json`

### Module 3: Summary（5+1 Phase 收敛模块）

> 吸收了原 ReviewQC 模块的质量保障功能，并增加了方案收敛能力。

```
Phase 1: Base Synthesis（运动员）→ base_solution
Phase 2: Meta Summary Planner（裁判+导演）→ summary_plan
Phase 3: Parallel Analysis ×N（含 Review Layer B）→ analysis_[name]
Phase 4: Fix Judge → Fix Agent → Harness Check → refined_solution
Phase 5a: Document Generator → solution_document
Phase 5b: JSON Extractor → final_solution
```

**输出**: `final_solution.json` + `solution_document.md`

## 核心特性

### 断点续跑
- 双层 State 验证：`master_state.json` + `module_output.json`
- 模块级粒度，跳过已完成模块

### 超时降级
| 模块 | 默认超时 | 降级策略 |
|------|---------|---------|
| Planning | 5 min | 使用 2 个通用 expert |
| Research | 15 min | 跳过，标记 degraded=true |
| Summary | 20 min | 降级为简化版合成 |

### 信息守恒
- 模块间通过 Blackboard 文件通信
- 所有 Stage 输出有 Pydantic Schema 验证
- REQ-ID 全链路追踪

## 文档导航

| 文档 | 用途 | 受众 |
|------|------|------|
| [SKILL.md](SKILL.md) | Agent 执行步骤（2.0.0） | AI Agent |
| [_overview.md](_overview.md) | 2.0.0 代码文件索引 | 开发者 |
| `schemas/schemas.py` | 2.0.0 Schema 契约 | 开发者 |
| `prompts/` | 2.0.0 Prompt 模板 | 运行时 |
| `tests/` | 2.0.0 测试套件 | 测试工程师 |

## 2.0.0 兼容

2.0.0 架构（固定多阶段管线）仍可用于已有 session 续跑：
- 2.0.0 入口：`from domains.solution import run_solution_pro`
- 2.0.0 文档：`prompts/v1/pipeline_orchestrator.md`
- 2.0.0 Stage 路径：`STAGE_PATH_REGISTRY_V1`（在 `blackboard.py`）

**判断方法**：检查 `blackboard/<session_id>/v2/master_state.json` 是否存在。存在 = 2.0.0 session。

## 禁止事项

- ❌ Python 代码中禁止直接 import OpenClaw SDK（使用 `sessions_spawn` 工具）
- ❌ 2.0.0 session 使用 2.0.0 入口
- ❌ 手动拼接 stage 路径（使用 BlackboardManager 2.0.0 API: `read_stage`/`write_stage`）
- ❌ MasterOrchestrator 做语义判断（只做调度）

## 版本历史

- **2.0.0** (2026-06-29): 三层架构（Planning + Research + Summary）+ 断点续跑 + 超时降级
- **2.0.0** (2026-06-03): 2.0.0 最终版本（固定多阶段管线）

详细变更见 [CHANGELOG.md](../../CHANGELOG.md)
