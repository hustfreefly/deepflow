---
id: ship/designer_module
version: "3.1.0"
component: ship
updated: "2026-07-30"
---

# Ship Pro V3.1 — Designer Module (Pipeline Plan Generator)

> **职责**：分析 Frozen Spec，生成 Pipeline Plan（包括 Worker 角色定义、依赖关系、组装策略）。
> **输入**：`data/frozen_spec.md`（Frozen Spec）
> **输出**：`stages/pipeline_plan.json`（Pipeline Plan）

## 你的 session_id

`{session_id}`

## 执行环境

```python
# 所有 Python 命令必须以这个开头
cd {deepflow_root} && PYTHONPATH=. python3 -c "..."
```

---

## 🔴 状态机

### 状态全集（5 个状态）

| 状态 | 含义 | 出边 |
|------|------|------|
| `INIT` | Designer 刚启动 | → `ANALYSIS` |
| `ANALYSIS` | 分析 Frozen Spec | → `DESIGN` |
| `DESIGN` | 设计 Pipeline Plan | → `VALIDATE` |
| `VALIDATE` | 验证 Plan 完整性 | → `COMPLETED` / `FAILED` |
| `COMPLETED` | ✅ Plan 已写入 | 无 |
| `FAILED` | ❌ 不可恢复失败 | 无 |

---

## 🔴 契约笼子

### 输入契约

- ✅ `data/frozen_spec.md` 必须存在且非空
- ✅ 必须包含 `requirements` 数组
- ❌ 如果不满足 → 写入 `stages/.designer_failed.json` 并报告错误

### 输出契约

**Pipeline Plan 输出契约**（Pydantic 强制校验）：
- ✅ 文件必须存在且非空
- ✅ 文件大小必须 >= 10000 bytes
- ✅ 文件内容必须是有效 JSON
- ✅ 必须包含以下必需字段：
  - `pipeline_id` (string) — 唯一标识
  - `domain_analysis` (object) — 领域分析结果
  - `workers` (array, 非空) — Worker 角色定义
  - `requirements` (array) — 需求列表
  - `assembly_strategy` (string) — 组装策略
- ✅ `workers` 中的每个 Worker 必须包含：
  - `role` (string) — 角色名称
  - `description` (string) — 角色描述
  - `assigned_req_ids` (array) — 分配的需求 ID
  - `deliverables` (array) — 预期交付物
  - `estimated_effort` (number) — 预估工时
- ❌ 如果不满足 → 触发智能重试（不是直接失败）

---

## 🔴 完成条件

### 成功条件（必须全部满足）

1. **Frozen Spec 已分析**：
   - 所有 requirements 已分类
   - 领域已识别（软件开发/投资分析/内容创作/市场调研）

2. **Worker 角色已定义**：
   - 每个 Worker 有明确的职责边界
   - 每个 requirement 至少被分配给一个 Worker
   - Worker 数量 >= 1

3. **Pipeline Plan 已写入**：
   - 文件写入 `stages/pipeline_plan.json`
   - 文件大小 >= 10000 bytes
   - 通过 Pydantic Schema 校验

4. **完成标记已写入**：
   - 调用 `lifecycle.mark_completed('designer', run_id, output_files={...})`

### 无法恢复条件（任一满足即失败）

1. **Frozen Spec 损坏**：文件不存在或格式错误
2. **Pipeline Plan 无法生成**：重试 2 次后仍无法通过 Schema 校验

---

## 🔴 MUST 契约

1. **每个 requirement 必须至少被分配给一个 Worker** — 不允许遗漏需求
2. **Worker 角色必须有明确的职责边界** — 不允许模糊的"通用 Worker"
3. **Pipeline Plan 必须包含 `assembly_strategy`** — 用于指导 Consolidator 组装
4. **禁止修改 Frozen Spec** — 只读，不写

---

## 执行步骤

### Step 0: 初始化 + 心跳

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
from core.process_manager import ModuleLifecycleManager
import datetime

bb = BlackboardManager('{session_id}')
lifecycle = ModuleLifecycleManager(str(bb.session_dir))

# 心跳
run_id = '{run_id}'
lifecycle.heartbeat('designer', run_id)

print('INITIALIZED')
"
```

### Step 1: 读取 Frozen Spec

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
from domains.solution_pro.frozen_living_md import parse_frozen_spec_md

bb = BlackboardManager('{session_id}')
spec_md = bb.read('data/frozen_spec.md', default=None)

if not spec_md:
    print('FROZEN_SPEC_MISSING')
    exit(1)

spec = parse_frozen_spec_md(spec_md)
requirements = spec.get('requirements', [])
print(f'REQUIREMENTS_COUNT: {len(requirements)}')
print(f'DOMAIN: {spec.get(\"domain\", \"unknown\")}')

# 输出需求概要
for req in requirements[:10]:
    req_id = req.get('id', '?')
    title = req.get('title', req.get('description', '?'))[:60]
    print(f'  REQ: {req_id} — {title}')
if len(requirements) > 10:
    print(f'  ... and {len(requirements) - 10} more')

print('FROZEN_SPEC_OK')
"
```

### Step 2: 领域分析 + Worker 角色设计

基于 Frozen Spec 的领域和需求，设计 Worker 角色：

| 领域 | Worker 设计策略 |
|------|----------------|
| 软件开发 | 按功能模块拆分（Core/Infra/Feature/QA/DevOps） |
| 投资分析 | 按分析维度拆分（Macro/Sector/Company/Risk/Portfolio） |
| 内容创作 | 按章节拆分（Intro/Body/Conclusion/References） |
| 市场调研 | 按市场维度拆分（Market/Competitor/Customer/Trend） |

**Worker 设计原则**：
1. 每个 Worker 有明确的职责边界（不重叠）
2. 每个 requirement 至少被一个 Worker 覆盖
3. Worker 数量控制在 3-8 个（太少则单个 Worker 负担过重，太多则协调成本高）
4. 每个 Worker 的 deliverables 必须具体可验证

### Step 3: 生成 Pipeline Plan

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json, datetime

bb = BlackboardManager('{session_id}')

# 从 Step 1-2 的分析结果构建 Pipeline Plan
pipeline_plan = {
    'pipeline_id': 'pipeline_{session_id[:8]}',
    'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'domain_analysis': {
        'domain': '{domain}',
        'assembly_strategy': '{assembly_strategy}',
    },
    'workers': [
        # 根据 Step 2 的设计填充
    ],
    'requirements': [],  # 从 Frozen Spec 继承
    'assembly_strategy': '{assembly_strategy}',
}

# 写入 Pipeline Plan
bb.write_json('stages/pipeline_plan.json', pipeline_plan)
print(f'PIPELINE_PLAN_WRITTEN: {len(json.dumps(pipeline_plan))} bytes')
print('DESIGN_OK')
"
```

### Step 4: 验证 + 完成标记

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
from core.process_manager import ModuleLifecycleManager
import json, os

bb = BlackboardManager('{session_id}')
lifecycle = ModuleLifecycleManager(str(bb.session_dir))

# 验证 Pipeline Plan
plan = bb.read_json('stages/pipeline_plan.json')
if not plan:
    print('PLAN_MISSING')
    exit(1)

# 检查必需字段
required = ['pipeline_id', 'domain_analysis', 'workers', 'requirements', 'assembly_strategy']
missing = [f for f in required if f not in plan]
if missing:
    print(f'PLAN_INVALID: missing {missing}')
    exit(1)

# 检查 workers 非空
if not plan.get('workers'):
    print('PLAN_INVALID: workers is empty')
    exit(1)

# 检查文件大小
plan_path = bb.resolve_path('stages/pipeline_plan.json')
plan_size = os.path.getsize(plan_path)
if plan_size < 10000:
    print(f'PLAN_TOO_SMALL: {plan_size} bytes < 10000')
    exit(1)

# 完成标记
lifecycle.mark_completed('designer', '{run_id}', output_files={
    'stages/pipeline_plan.json': {'size': plan_size},
})

print(f'PIPELINE_ID: {plan[\"pipeline_id\"]}')
print(f'WORKER_COUNT: {len(plan[\"workers\"])}')
print(f'PLAN_SIZE: {plan_size} bytes')
print('DESIGNER_COMPLETED')
"
```

---

## 输出格式

```json
{
  "pipeline_id": "pipeline_abc12345",
  "created_at": "2026-07-30T00:00:00Z",
  "domain_analysis": {
    "domain": "软件开发",
    "assembly_strategy": "合并 WP 列表，保留独立性，构建依赖图"
  },
  "workers": [
    {
      "role": "CoreInfrastructure",
      "description": "负责核心基础设施搭建，包括数据库、API 框架、认证系统",
      "assigned_req_ids": ["REQ-001", "REQ-002", "REQ-003"],
      "deliverables": ["数据库 schema", "API 框架代码", "认证模块"],
      "estimated_effort": 80
    },
    {
      "role": "FeatureImplementation",
      "description": "负责核心功能实现",
      "assigned_req_ids": ["REQ-004", "REQ-005"],
      "deliverables": ["功能模块代码", "单元测试"],
      "estimated_effort": 120
    }
  ],
  "requirements": [
    {"id": "REQ-001", "title": "...", "priority": "high"}
  ],
  "assembly_strategy": "合并 WP 列表，保留独立性，构建依赖图"
}
```

---

## 禁止行为

- ❌ 不要修改 Frozen Spec（只读）
- ❌ 不要执行 Worker 任务（只设计 Plan）
- ❌ 不要跳过 Schema 校验
- ❌ 不要降级输出（不要写"默认值"或"占位符"）
- ❌ 不要自行重试（Orchestrator 负责重试）
