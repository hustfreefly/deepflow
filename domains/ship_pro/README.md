# Ship Pro 2.0.0 — AI Native 交付包生成

> **版本**: 2.0.0 | **日期**: 2026-07-04 | **状态**: 架构定型，E2E 验证通过

## 🎯 核心理念

**Ship Pro = Solution Pro 的下游管线**

读取 Solution Pro 的方案输出 → 拆分为可执行的 Work Packages → 合并为 ShipPackage。

| 原则 | 说明 |
|------|------|
| **Main Agent 只做一件事** | `run_ship_pro()` → spawn Orchestrator → 完事 |
| **Orchestrator 全权负责** | 设计 → 执行 → 验证 → 报告，不回调 Main Agent |
| **Python 做验证** | Gate 检查、状态管理、拓扑排序、JSON 提取 |
| **LLM 做决策** | Worker 拆分、WP 设计、语义整合 |
| **统一 blackboard** | 所有域共享项目目录，跨域信息流靠文件路径约定 |

---

## 🏗️ 架构（2.0.0）

```
Main Agent (depth-0)
  └─ exec: run_ship_pro(project_name) → spawn_params
  └─ sessions_spawn(**spawn_params) → Orchestrator (depth-1)

Orchestrator (depth-1, 全权调度)
  ├─ Phase 1: PipelineDesigner
  │   └─ exec design_pipeline() → 分析需求 → PipelinePlan (Worker 拆分 + 依赖 + 上下文裁剪)
  │
  ├─ Phase 2: Workers (4-6 个, 并行)
  │   └─ exec prepare_runner_spawn() → Worker prompts
  │   └─ spawn Workers (分层并行, cron wake 等待)
  │   └─ L1 确定性验证 (Schema + 内容深度)
  │
  ├─ Phase 3: Consolidator
  │   └─ spawn Consolidator (cron wake 等待)
  │   └─ 5 步法：收集 → 语义整合 → 冲突检测 → 依赖图 → 组装
  │   └─ L1 + L2 + L3 三层验证
  │
  └─ 输出: ShipPackage (ship_package.md + JSON 衍生)
```

### 统一 Blackboard

```
.deepflow/blackboard/{project_name}/
├── data/frozen_spec.md             ← Solution Pro 产出
├── stages/solution_document.json   ← Solution Pro 产出（markdown）
├── ship_pro/                       ← Ship Pro 写入
│   ├── solution_pro_input.json     ← 合并后的输入
│   └── stages/
│       ├── pipeline_plan.json
│       ├── context_*.json
│       ├── worker_*.json
│       ├── ship_package.md         ← 最终交付包（唯一真相源）
│       └── ship_package.json       ← JSON 衍生（向后兼容）
```

---

## 🚀 快速开始

```python
# Main Agent 只需做这一件事
from domains.ship_pro import run_ship_pro

result = run_ship_pro("OpenClaw AI Native Loop Engineering Framework")
sessions_spawn(**result["spawn_params"])
# 等待完成事件 → ShipPackage 在 result["ship_pro_dir"]/stages/ship_package.md
```

### 前置条件

- Solution Pro 已完成，输出在 `.deepflow/blackboard/{project_name}/data/frozen_spec.md`
- 项目目录存在于 `.deepflow/blackboard/` 下

---

## 📐 管线阶段

### Phase 1: PipelineDesigner

**执行方式**: Orchestrator 通过 `exec` 调 Python

- 分析 Solution Pro 输出（requirements, decisions, risks）
- 按**交付物模块**（代码内聚性）拆分 4-6 个 Workers
- 为每个 Worker 裁剪上下文（~2KB context.json）
- 输出 `pipeline_plan.json`

### Phase 2: Workers

**执行方式**: Orchestrator 通过 `sessions_spawn` 并行 spawn

每个 Worker 收到 6 段式 prompt（~2.5KB）：
1. 角色 + 数据流声明
2. 模块概述
3. 需求 + 约束
4. 接口契约
5. 输出规范 + 示例
6. 反模式护栏

**Worker 输出**: JSON 数组，每个 WP 包含 id, title, description(≥100字), acceptance_criteria(≥2条), deliverables(≥1项), effort_hours, covered_req_ids, anchored_to, dependencies

**L1 验证**: Schema 合规 + 内容深度 + 字段映射兼容

### Phase 3: Consolidator

**执行方式**: Orchestrator 通过 `sessions_spawn` 启动

5 步法：
1. **收集** — 读取所有 worker_*.json
2. **语义整合** — 互补型合并、冲突型保留+标记、完全重复取优
3. **冲突检测** — 约束矛盾、接口不兼容
4. **依赖图** — 跨模块 WP 依赖
5. **组装** — ShipPackage JSON + 统计信息

---

## 🔒 契约笼子

### 三层验证架构

| 层 | 性质 | 做什么 |
|----|------|--------|
| L1 | Python 确定性 | Schema 合规、字段验证、内容深度、AC 数量 |
| L2 | LLM Judge 语义 | MUST 约束保留、信息守恒、工程品质 |
| L3 | Python 综合 | 合并 L1+L2 → PASS / CONDITIONAL / FAIL |

### Gate 清单

| Gate | L1 | L2 |
|------|----|----|
| PlannerGate | Schema + REQ 全覆盖 + 无重叠 | — |
| WorkerGate | Schema + 内容深度 | MUST 约束语义检查 |
| InformationConservationGate | REQ 守恒率 ≥ 0.8 | 语义漂移检测 |
| CompletenessGate | AC 覆盖率 | 可交付性判断 |
| HarnessV3 | 整体统计 | 工程质量 1-10 评分 |

---

## 📁 文件结构

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
│   └── dry_run_v8.py        # 2.0.0 集成测试
├── docs/
│   └── V8_DECISIONS.md      # 架构决策文档（2.0.0 → 2.0.0 → 2.0.0）
├── _archive/                # 归档（2.0.0/2.0.0 遗留文件）
├── README.md                # 本文件
└── SKILL.md                 # Agent 执行指南
```

---

## 🧪 测试

```bash
cd .deepflow

# 单元测试
python3 -m pytest domains/ship_pro/tests/test_ship_pro.py -v

# 2.0.0 集成测试
python3 -m pytest domains/ship_pro/tests/dry_run_v8.py -v
```

---

## 📊 E2E 性能

| 指标 | 2.0.0 | 2.0.0 |
|------|-----|-----|
| Work Packages | 35 | **39** |
| ShipPackage 大小 | 1.1KB (摘要) | **103KB** (完整) |
| 执行时间 | 51 min | **12 min** |
| REQ 覆盖率 | 91.3% | **91%** |
| 依赖边 | 0 | **56** |

---

## 🎓 关键教训

| 教训 | 说明 |
|------|------|
| sessions_yield 是陷阱 | 子 Agent yield 后无法被 child 完成事件唤醒 → 用 cron wake |
| Main Agent 不编排 | spawn-and-forget，不是 spawn-and-micromanage |
| 统一 blackboard | 跨域信息流靠文件路径约定，不靠手动搬运 |
| Worker prompt 不超载 | 2-3KB 最佳，REQ > 10 时只显示 ID |
| 语义整合非去重 | 重叠 WP 合并为更完整的 WP，不删除 |
| 字段名必须一致 | Worker prompt 和 Schema 对齐，L1 映射是 hack |

---

## 📚 相关文档

- [2.0.0 架构决策](docs/V8_DECISIONS.md) — 完整设计决策记录
- [SKILL.md](SKILL.md) — Agent 执行指南
- [AgentDryRun Skill](../../../skills/AgentDryRun/SKILL.md) — 六维体检框架

---

*2.0.0 架构定型：Orchestrator 单入口 + 统一 blackboard + cron wake*
