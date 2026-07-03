# Ship Pro — Agent 执行指南

> **架构**: AI Native（动态 Planner + Workers + Consolidator）  
> **对标**: Solution Pro V2 镜像架构  
> **状态**: 已实现，待 E2E 验证

---

## 🏗️ 架构总览

```
Phase 1: Planner (LLM 动态)
  └─ 分析 Solution Pro 输出 → 决定 Worker 数量/角色/依赖 → PlannerOutput
         ↓ PlannerGate 验证
Phase 2: Workers (LLM + 固定编排)
  └─ 拓扑排序 → 按层级 spawn Workers (同层并行) → WorkerGate 逐个验证
         ↓
Phase 3: Consolidator (LLM + 三层验证)
  └─ 汇总 Worker 输出 → G1:信息守恒 → G2:完整性 → G3:交付质量 → ShipPackage
```

### 核心原则

| 原则 | 说明 |
|------|------|
| **LLM 做决策** | Planner 动态决定 Worker 数量/角色/Prompt |
| **Python 做验证** | Orchestrator Gate 检查、状态管理、拓扑排序 |
| **契约笼子** | Pydantic Schema 约束每个阶段的输入输出 |
| **信息守恒** | Solution Pro 的需求不能丢失也不能新增 |

---

## 🚀 主 Agent 执行步骤

### Step 1: 加载 Orchestrator 并准备 spawn 参数

```bash
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 << 'EOF'
from domains.ship_pro.orchestrator import ShipOrchestrator
from pathlib import Path
import json

orchestrator = ShipOrchestrator(
    blackboard_path=Path('<blackboard_path>'),
    solution_pro_output_path=Path('<solution_pro_output_path>')
)

# Phase 1: Planner
spawn_params = orchestrator.prepare_planner_spawn()
print(json.dumps(spawn_params, indent=2, ensure_ascii=False))
EOF
```

### Step 2: Spawn Planner + Yield

```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="ship_planner",
    task=spawn_params['task'],
    cwd="/Users/allen/.openclaw/workspace/.deepflow",
    lightContext=True,
)
sessions_yield()
```

### Step 3: 验证 Planner 输出

```bash
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 << 'EOF'
from domains.ship_pro.orchestrator import ShipOrchestrator
from pathlib import Path

orchestrator = ShipOrchestrator(
    blackboard_path=Path('<blackboard_path>'),
    solution_pro_output_path=Path('<solution_pro_output_path>')
)
gate_result = orchestrator.verify_planner_output()
print(f"PlannerGate: {'PASS' if gate_result.passed else 'FAIL'}")
if not gate_result.passed:
    for issue in gate_result.issues:
        print(f"  - {issue}")
EOF
```

### Step 4: Spawn Workers（按层级并行）

```bash
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 << 'EOF'
from domains.ship_pro.orchestrator import ShipOrchestrator
from pathlib import Path
import json

orchestrator = ShipOrchestrator(
    blackboard_path=Path('<blackboard_path>'),
    solution_pro_output_path=Path('<solution_pro_output_path>')
)

# 获取所有 Worker 的 spawn 参数（按执行层级排序）
worker_spawns = orchestrator.prepare_worker_spawns()
for ws in worker_spawns:
    print(f"Layer {ws['layer']}: {ws['label']}")
print(json.dumps([{'label': w['label'], 'layer': w['layer']} for w in worker_spawns], indent=2))
EOF
```

然后按层级 spawn：
- 同层级的 Worker 可以并行 spawn
- 每个 Worker 完成后用 `orchestrator.verify_worker_output(label)` 验证
- 全部 Worker 完成后进入 Phase 3

### Step 5: Spawn Consolidator + 三层 Gate

```bash
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 << 'EOF'
from domains.ship_pro.orchestrator import ShipOrchestrator
from pathlib import Path

orchestrator = ShipOrchestrator(
    blackboard_path=Path('<blackboard_path>'),
    solution_pro_output_path=Path('<solution_pro_output_path>')
)

# Consolidator spawn 参数
spawn_params = orchestrator.prepare_consolidator_spawn()

# Consolidator 完成后验证（三层 Gate）
gate_results = orchestrator.verify_ship_package()
for gr in gate_results:
    status = "✅ PASS" if gr.passed else "❌ FAIL"
    print(f"{status}: {gr.gate_name}")
    if not gr.passed:
        for issue in gr.issues[:3]:
            print(f"  - {issue}")
EOF
```

---

## 📂 文件结构

```
domains/ship_pro/
├── contracts/              # 契约定义
│   ├── planner_output.py  # PlannerOutput + WorkerSpec
│   ├── worker_deliverable.py # WorkerDeliverable + WorkPackage
│   ├── ship_package.py    # ShipPackage + DependencyGraph
│   ├── gates.py           # PlannerGate + WorkerGate + 三层 Gate
│   └── schemas/           # JSON Schema (供 LLM 参考)
├── orchestrator/           # 编排器
│   ├── ship_orchestrator.py # 主编排器
│   └── state_manager.py   # 状态管理 (pipeline_state.json)
├── agent/                  # Agent 层
│   └── ship_agent.py      # spawn_fn/yield_fn 调度
├── prompts/                # Prompt 模板
│   ├── planner.md         # Planner 角色 + 约束笼子
│   ├── worker_base.md     # Worker 基础模板
│   ├── consolidator.md    # Consolidator 角色 + 三层验证
│   └── agent.md           # Agent 执行指南
├── tests/                  # 测试
│   ├── dry_run.py         # Dry Run 验证
│   └── test_ship_pro.py   # 单元测试
├── run_ship_pro.py        # 启动脚本
├── _archive/              # 旧版本归档 (V3/V4/V5)
└── SKILL.md               # 本文件
```

---

## 🔒 契约笼子

### 三层约束

| 层级 | 允许 | 禁止 |
|------|------|------|
| 任务边界 | 分析、规划、执行、汇总 | 修改 Solution Pro 输出、增删需求 |
| 角色边界 | 专注于自己的角色任务 | 执行其他角色的任务 |
| 输出边界 | 输出符合 Schema 的结构化数据 | 输出自由文本、解释决策 |

### Gate 验证链

```
PlannerGate: Worker 数量 2-8 + DAG 无环 + solution_pro_refs + must_constraints
WorkerGate: Schema 合规 + MUST 约束保留(LLM) + web_search 范围
G1 InformationConservation: 需求无丢失 + 无新增
G2 Completeness: REQ-ID 覆盖率 + 覆盖深度(LLM)
G3 Harness: 工作包数量 3-15 + DAG 合理 + AC 可操作(≥2/WP)
```

---

## 🔄 失败处理

每个阶段最多重试 2 次：
1. Gate 失败 → 生成 `fix_context`（含失败原因 + 修复建议）
2. 将 `fix_context` 注入下一轮 prompt
3. 超过重试次数 → 标记 `failed`，通知主 Agent

---

## 🧪 验证命令

```bash
# Dry Run
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 domains/ship_pro/tests/dry_run.py

# 单元测试
cd ~/.openclaw/workspace/.deepflow && python3 -m pytest domains/ship_pro/tests/test_ship_pro.py -v

# 生成 JSON Schemas
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from domains.ship_pro.contracts import get_planner_output_schema, get_worker_deliverable_schema, get_ship_package_schema
import json
from pathlib import Path
d = Path('domains/ship_pro/contracts/schemas')
d.mkdir(exist_ok=True)
for name, fn in [('planner_output.json', get_planner_output_schema), ('worker_deliverable.json', get_worker_deliverable_schema), ('ship_package.json', get_ship_package_schema)]:
    (d / name).write_text(json.dumps(fn(), indent=2, ensure_ascii=False))
    print(f'Generated: {d / name}')
"
```
