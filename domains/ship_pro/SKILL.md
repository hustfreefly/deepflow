---
name: ship-pro
description: "DeepFlow Ship Pro — 交付包生成引擎。触发：生成工作包、拆分任务、交付编译。"
version: "2.0.0"
---

# Ship Pro 2.0.0 — Agent 执行指南

> **架构**: AI Native（PipelineDesigner + Orchestrator + Workers + Consolidator）  
> **对标**: Solution Pro 2.0.0 镜像架构  
> **入口**: `run_ship_pro(project_name)` — Main Agent 唯一调用  
> **状态**: 2.0.0 架构定型，E2E 验证通过

---

## 🏗️ 架构总览

```
Main Agent (depth-0)
  └─ exec: run_ship_pro(project_name) → spawn_params
  └─ sessions_spawn(**spawn_params) → Orchestrator 子 Agent
  └─ 等待完成事件 → 拿到 ShipPackage

Orchestrator (depth-1, 全权调度)
  ├─ Phase 1: exec design_pipeline() → Designer prompt → spawn Designer LLM → PipelinePlan
  ├─ Phase 2: exec prepare_runner_spawn() → Worker prompts → spawn Workers (分层并行)
  │     └─ L1 确定性验证 (Schema + 内容深度)
  │     └─ L2 LLM Judge 语义验证（待实现）
  ├─ Phase 3: spawn Consolidator → ShipPackage
  │     └─ L1 + L2 + L3 三层验证
  └─ 输出最终报告
```

### 核心原则

| 原则 | 说明 |
|------|------|
| **Main Agent 只做一件事** | `run_ship_pro()` → spawn Orchestrator → 完事 |
| **Orchestrator 全权负责** | 设计 → 执行 → 验证 → 报告，不回调 Main Agent |
| **Python 做验证** | Gate 检查、状态管理、拓扑排序、JSON 提取 |
| **LLM 做决策** | Worker 拆分、WP 设计、语义整合 |
| **契约笼子** | Pydantic Schema + min_length 约束每个阶段的输入输出 |
| **信息守恒** | Solution Pro 的需求不能丢失也不能新增 |
| **cron wake 替代 sessions_yield** | 等待子 Agent 完成，避免空 turn |

### 统一 Blackboard

所有域的产出在同一个项目目录下：

```
.deepflow/blackboard/{project_name}/
├── data/living_spec.md             ← Solution Pro 产出（MD source of truth）
├── stages/solution_document.md     ← Solution Pro 产出（MD source of truth）
├── ship_pro/                       ← Ship Pro 写入
│   ├── solution_pro_input.json     ← 合并后的输入
│   ├── stages/
│   │   ├── pipeline_plan.json      ← Designer 输出
│   │   ├── context_*.json          ← Worker 上下文
│   │   ├── worker_*.json           ← Worker 输出
│   │   ├── ship_package.md         ← 最终交付包（唯一真相源）
│   │   └── ship_package.json       ← JSON 衍生（向后兼容）
│   └── ...
```

---

## 🚀 使用方式

### 标准流程（Main Agent 视角）

```python
# Step 1: 启动（唯一一步）
from domains.ship_pro import run_ship_pro
result = run_ship_pro("项目名称")

# Step 2: spawn Orchestrator
sessions_spawn(**result["spawn_params"])

# Step 3: 等待完成事件 → 读取 ShipPackage
# ship_package.md 在 result["ship_pro_dir"]/stages/ 下（JSON 衍生同步生成）
```

### run_ship_pro() 做什么

1. 定位统一 blackboard：`.deepflow/blackboard/{project_name}/`
2. 自动发现 Solution Pro 输出（`data/living_spec.md`，MD-first）
3. 合并输入（living_spec.md + 可选 supplemental）
4. 构建 Orchestrator prompt（含完整执行指令）
5. 返回 `spawn_params`

---

## 📐 管线阶段

### Phase 1: PipelineDesigner

**执行者**: Orchestrator 通过 `exec` 调 Python

```python
from domains.ship_pro import design_pipeline
result = design_pipeline("path/to/solution_pro_input.json", blackboard_base_dir="path/to/ship_pro/")
```

**产出**: `pipeline_plan.json`
- Workers 列表（role, covered_req_ids, interface_provides/requires）
- Execution order（分层拓扑）
- Rationale

**约束**:
- Worker 按**交付物模块**拆分（代码内聚性），4-6 个
- 每个 REQ-ID 只能分配给一个 Worker
- 每个 Worker 的 relevant_decisions ≤ 5, relevant_risks ≤ 3

### Phase 2: Workers

**执行者**: Orchestrator 通过 `sessions_spawn` 并行 spawn

**Worker prompt**（6 段式，~2.5KB）：
1. 角色 + 数据流（高注意力区）
2. 模块概述
3. 需求 + 架构约束 + 隐含约束
4. 接口契约（provides / requires / downstream）
5. 输出规范 + 紧凑示例
6. 反模式护栏（高注意力区）

**Worker 输出**: JSON 数组，每个 WP 包含：
- `id`: WP-ID（如 SM-001）
- `title`: 标题
- `description`: ≥ 100 字
- `acceptance_criteria`: ≥ 2 条
- `deliverables`: ≥ 1 项
- `effort_hours`: 整数（小时）。旧字段 `estimated_effort` (str "Nh") 会被自动转换
- `covered_req_ids`: ["REQ-xxx"]
- `dependencies`: ["WP-ID"]

**L1 验证**（Python 确定性）：
- Schema 合规（Pydantic）
- 内容深度（description ≥ 100 字, AC ≥ 2, deliverables ≥ 1）
- 字段映射兼容（wp_id→id, estimated_effort→effort_hours）

### Phase 3: Consolidator

**执行者**: Orchestrator 通过 `sessions_spawn` 启动

**5 步法**：
1. **收集** — 读取所有 worker_*.json，不丢弃任何 WP
2. **语义整合** — 互补型合并、冲突型保留+标记、完全重复取优
3. **冲突检测** — 约束矛盾、接口不兼容
4. **依赖图** — 跨模块 WP 依赖（基于接口契约）
5. **组装** — 生成 ShipPackage JSON

**ShipPackage 输出**（MD-first）：
- 主输出：`ship_package.md`（唯一真相源）
- 衍生输出：`ship_package.json`（向后兼容，自动生成）
- 格式：YAML frontmatter + Markdown sections（meta_info, work_packages, execution_order）

**L1 验证**: `validate_ship_package_v8()` — 检查 WP 完整性、非摘要化

---

## 🔒 契约笼子

### Schema 约束

| 模型 | 关键字段约束 |
|------|-------------|
| `WorkPackage` | description ≥ 100 字, AC ≥ 2, deliverables ≥ 1 |
| `PlannerOutput` | workers 2-8 个, 每个 covered_req_ids 非空 |
| `ShipPackage` | work_packages 非空, statistics 完整 |

### Gate 验证

| Gate | 层级 | 检查内容 |
|------|------|---------|
| PlannerGate | L1 确定性 | Schema 合规、REQ 全覆盖、无重叠分配 |
| WorkerGate | L1 + L2 | Schema + 内容深度 + LLM 语义审查 |
| InformationConservationGate | L1 + L2 | REQ 守恒率 ≥ 0.8 + LLM 语义漂移检测 |
| CompletenessGate | L1 + L2 | AC 覆盖率 + LLM 判断是否可交付 |
| HarnessV3 | L1 + L2 | 整体工程质量 1-10 评分 |

---

## 🛡️ 关键教训

| 教训 | 说明 |
|------|------|
| **sessions_yield 是陷阱** | 子 Agent yield 后无法被 child 完成事件唤醒。用 cron wake 替代 |
| **Worker prompt 不超载** | 2-3KB 最佳，REQ > 10 时只显示 ID，详情放 context.json |
| **不 read task 文件** | spawn params 已含完整 task，read 是浪费 token |
| **字段名必须一致** | Worker prompt 和 Schema 字段名对齐，L1 字段映射是 hack |
| **语义整合非去重** | 重叠 WP 合并为更完整的 WP，不删除 |
| **统一 blackboard** | 所有域共享项目目录，跨域信息流靠文件路径约定 |

---

## 📁 目录结构

```
domains/ship_pro/
├── __init__.py              # 2.0.0 入口 (run_ship_pro, design_pipeline, prepare_runner_spawn)
├── pipeline_designer.py     # PipelineDesigner + 上下文裁剪
├── contracts/               # Pydantic Schema
│   ├── gates.py             # Gate 验证逻辑
│   ├── planner_output.py    # PipelinePlan 模型
│   ├── ship_package.py      # ShipPackage 模型
│   └── worker_deliverable.py # WorkPackage 模型
├── orchestrator/            # 编排引擎
│   ├── ship_orchestrator.py # L1/L2/L3 验证
│   └── state_manager.py     # 状态管理（宽松模式）
├── prompts/
│   ├── consolidator.md      # Consolidator 模板
│   ├── designer_module.md   # Designer 模块模板
│   └── worker_module.md     # Worker 模块模板
├── tests/
│   ├── test_ship_pro.py     # 19 个单元测试
│   └── dry_run_v8.py        # 2.0.0 集成测试（已被 AgentDryRun Skill 替代）
├── docs/
│   └── V8_DECISIONS.md      # 架构决策文档
├── README.md                # 项目说明
└── SKILL.md                 # 本文件
```

---

## 🔄 2.0.0 兼容 API

以下旧 API 保留兼容，但推荐使用 `run_ship_pro()`：

- `design_pipeline(solution_pro_output_path)` — 只执行 Phase 1
- `prepare_runner_spawn(base_path, designer_output, solution_pro_input)` — 只准备 Worker params
- `extract_json_from_completion(text)` — 从 LLM 输出提取 JSON

---

*最后更新: 2026-07-30 2.0.0 (MD-first)*

---

## V2.0.0 (2026-07-08) — AI Native 反模式修复

### P0 修复（2 个）
| 问题 | 修复 |
|------|------|
| `_CODE_PATTERNS` 正则做代码检测 | → `_has_code_indicators()` 只检测 ``` + Layer 2 LLM Judge |
| `web_search_scope` 关键词匹配 | → 结构性检查（日志存在性）+ MUST Judge 语义判断 |

### P1 修复（2 个）
| 问题 | 修复 |
|------|------|
| WP 完成率 0.8/0.7 硬编码阈值 | → `WP_COMPLETION_THRESHOLD` + `CONSOLIDATOR_WP_RETENTION_THRESHOLD` 常量 |
| `VALID_TRANSITIONS` 硬编码状态机 | → `register_transition()` 运行时扩展机制 |

### 修复模式
代码做确定性粗筛（结构检查/常量阈值），语义判断交给 LLM Judge。

### 测试
- ship_pro: 19 passed
