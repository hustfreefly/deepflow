# Solution Pro V2 — 系统级解决方案设计引擎

> 通过三层模块化架构自动化生成高质量技术解决方案

## 当前版本

- **版本**: V2.0 (三层架构)
- **架构**: MasterOrchestrator → Planning（三层）+ Research（多专家并行）+ ReviewQC（Fix Loop + 收敛）
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

参见 [SKILL.md](SKILL.md) 中的 V2 执行指南。

### 3. 验证结果

```bash
# V2 集成测试
python3 tests/test_v2_integration.py

# V2 Schema 验证
python3 tests/test_v2_schemas.py

# Golden Case 验证
python3 tests/test_golden_case_001.py
```

## V2 架构概述

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

### Module 3: ReviewQC（质量保障 + 最终收敛）

```
Stage 1: Fix Loop → 检测并修复问题（最多 3 轮）
Stage 2: Harness Check → 对抗性检查
Stage 3: Final Review → 最终评审
Stage 4: Convergence → final_convergence.json
```

**输出**: `final_convergence.json`

## 核心特性

### 断点续跑
- 双层 State 验证：`master_state.json` + `module_output.json`
- 模块级粒度，跳过已完成模块

### 超时降级
| 模块 | 默认超时 | 降级策略 |
|------|---------|---------|
| Planning | 5 min | 使用 2 个通用 expert |
| Research | 15 min | 跳过，标记 degraded=true |
| ReviewQC | 10 min | 使用降级收敛 Schema |

### 信息守恒
- 模块间通过 Blackboard 文件通信
- 所有 Stage 输出有 Pydantic Schema 验证
- REQ-ID 全链路追踪

## 文档导航

| 文档 | 用途 | 受众 |
|------|------|------|
| [SKILL.md](SKILL.md) | Agent 执行步骤（V5.0） | AI Agent |
| [_overview.md](_overview.md) | V2 代码文件索引 | 开发者 |
| `schemas/v2_schemas.py` | V2 Schema 契约 | 开发者 |
| `prompts/` | V2 Prompt 模板 | 运行时 |
| `tests/` | V2 测试套件 | 测试工程师 |

## V1 兼容

V1 架构（固定多阶段管线）仍可用于已有 session 续跑：
- V1 入口：`from domains.solution import run_solution_pro`
- V1 文档：`prompts/pipeline_orchestrator.md`
- V1 Stage 路径：`STAGE_PATH_REGISTRY_V1`（在 `blackboard.py`）

**判断方法**：检查 `blackboard/<session_id>/v2/master_state.json` 是否存在。存在 = V2 session。

## 禁止事项

- ❌ Python 代码中禁止直接 import OpenClaw SDK（使用 `sessions_spawn` 工具）
- ❌ V2 session 使用 V1 入口
- ❌ 手动拼接 stage 路径（使用 BlackboardManager V6 API: `read_stage`/`write_stage`）
- ❌ MasterOrchestrator 做语义判断（只做调度）

## 版本历史

- **V2.0** (2026-06-29): 三层架构（Planning + Research + ReviewQC）+ 断点续跑 + 超时降级
- **V4.4** (2026-06-03): V1 最终版本（固定多阶段管线）

详细变更见 [CHANGELOG.md](../../CHANGELOG.md)
