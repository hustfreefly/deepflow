---
id: ship/worker_module
version: "3.1.0"
component: ship
updated: "2026-07-30"
---

# Ship Pro V3.1 — Worker Module (WP Executor)

> **职责**：根据 Pipeline Plan 中分配的角色和需求，执行具体工作并输出 Work Packages。
> **输入**：`stages/pipeline_plan.json`（Pipeline Plan）+ 你的角色定义
> **输出**：`stages/worker_outputs/worker_{normalized_role}.json`（Worker Deliverable）

## 你的 session_id

`{session_id}`

## 你的角色

`{worker_role}`

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
| `INIT` | Worker 刚启动 | → `READ_PLAN` |
| `READ_PLAN` | 读取 Pipeline Plan，提取角色信息 | → `EXECUTE` |
| `EXECUTE` | 执行工作，生成 Work Packages | → `VALIDATE` |
| `VALIDATE` | 验证输出完整性 | → `COMPLETED` / `FAILED` |
| `COMPLETED` | ✅ Worker 输出已写入 | 无 |
| `FAILED` | ❌ 不可恢复失败 | 无 |

---

## 🔴 契约笼子

### 输入契约

- ✅ `stages/pipeline_plan.json` 必须存在且非空
- ✅ 必须包含 `workers` 数组
- ✅ `workers` 中必须存在 `role == "{worker_role}"` 的条目
- ❌ 如果不满足 → 写入 `stages/.worker_failed.json` 并报告错误

### 输出契约

**Worker Deliverable 输出契约**（Pydantic 强制校验）：
- ✅ 文件必须存在且非空
- ✅ 文件大小必须 >= 2000 bytes
- ✅ 文件内容必须是有效 JSON
- ✅ 必须包含以下必需字段：
  - `worker_role` (string) — 你的角色名称
  - `work_packages` (array, 非空) — 你产出的 WP 列表
  - `metadata` (object) — 元信息
- ✅ `work_packages` 中的每个 WP 必须包含：
  - `wp_id` (string) — 唯一标识（格式：`{ROLE_PREFIX}-NNN`）
  - `status` (string) — 固定为 `"draft"`
  - `title` (string) — WP 标题
  - `description` (string, ≥100 字) — 详细描述
  - `acceptance_criteria` (array, 非空) — 验收标准
  - `deliverables` (array, 非空) — 交付物列表
  - `effort_hours` (number) — 预估工时
  - `dependencies` (array) — 依赖的其他 WP-ID
  - `covered_req_ids` (array) — 覆盖的需求 ID
  - `anchored_to` (array) — 关联的 Semantic Anchors
  - `source_worker` (string) — 你的角色名称
- ❌ 如果不满足 → 触发智能重试（不是直接失败）

---

## 🔴 完成条件

### 成功条件（必须全部满足）

1. **Pipeline Plan 已读取**：
   - 你的角色定义已提取
   - 分配给你的 requirements 已识别

2. **Work Packages 已生成**：
   - 每个 assigned requirement 至少对应一个 WP
   - 每个 WP 包含完整的 description + acceptance_criteria + deliverables
   - WP 内容具体、可执行、不模糊

3. **Worker 输出已写入**：
   - 文件写入 `stages/worker_outputs/worker_{normalized_role}.json`
   - 文件大小 >= 2000 bytes
   - 通过 Pydantic Schema 校验

4. **完成标记已写入**：
   - 调用 `lifecycle.mark_completed('workers', run_id, output_files={...})`

### 无法恢复条件（任一满足即失败）

1. **Pipeline Plan 损坏**：文件不存在或格式错误
2. **角色定义缺失**：Pipeline Plan 中没有你的角色
3. **Worker 输出无法生成**：重试 2 次后仍无法通过 Schema 校验

---

## 🔴 MUST 契约

1. **每个 assigned requirement 必须至少产出一个 WP** — 不允许遗漏需求
2. **WP description 必须 ≥100 字** — 不允许模糊的"实现 XXX 功能"
3. **acceptance_criteria 必须具体可验证** — 不允许"功能正常"这种模糊标准
4. **deliverables 必须具体到文件名或模块名** — 不允许"相关代码"这种模糊描述
5. **禁止修改其他 Worker 的输出文件** — 只写自己的文件
6. **禁止修改 Pipeline Plan** — 只读，不写

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
lifecycle.heartbeat('workers', run_id)

print('INITIALIZED')
print(f'WORKER_ROLE: {worker_role}')
"
```

### Step 1: 读取 Pipeline Plan，提取角色信息

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json

bb = BlackboardManager('{session_id}')
plan = bb.read_json('stages/pipeline_plan.json')

if not plan:
    print('PIPELINE_PLAN_MISSING')
    exit(1)

workers = plan.get('workers', [])
my_worker = None
for w in workers:
    if w.get('role') == '{worker_role}':
        my_worker = w
        break

if not my_worker:
    print(f'WORKER_ROLE_NOT_FOUND: {worker_role}')
    exit(1)

assigned_reqs = my_worker.get('assigned_req_ids', [])
deliverables = my_worker.get('deliverables', [])
description = my_worker.get('description', '')

print(f'ROLE: {my_worker[\"role\"]}')
print(f'DESCRIPTION: {description}')
print(f'ASSIGNED_REQS: {json.dumps(assigned_reqs)}')
print(f'EXPECTED_DELIVERABLES: {json.dumps(deliverables)}')
print(f'EFFORT: {my_worker.get(\"estimated_effort\", \"?\")} hours')
print('PLAN_READ_OK')
"
```

### Step 2: 执行工作，生成 Work Packages

根据你的角色和分配的需求，生成具体的 Work Packages：

**WP 设计原则**：
1. 每个 WP 对应一个独立的功能单元
2. description 必须详细（≥100 字），包含：
   - 做什么（What）
   - 为什么做（Why — 对应哪个需求）
   - 怎么做（How — 技术方案概要）
3. acceptance_criteria 必须具体可验证：
   - ✅ "API 响应时间 < 200ms（P95）"
   - ❌ "功能正常"
4. deliverables 必须具体到文件名或模块名：
   - ✅ "src/api/auth.py"
   - ❌ "相关代码"
5. dependencies 列出本 Worker 内其他 WP 的依赖（跨 Worker 依赖由 Consolidator 处理）
6. covered_req_ids 必须覆盖所有 assigned_req_ids

### Step 3: 写入 Worker 输出

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json, os

bb = BlackboardManager('{session_id}')

# 构建 Worker Deliverable
worker_deliverable = {
    'worker_role': '{worker_role}',
    'work_packages': [
        # 从 Step 2 的设计填充
    ],
    'metadata': {
        'total_wps': 0,
        'total_effort_hours': 0,
        'covered_req_ids': [],
    }
}

# 更新 metadata
wps = worker_deliverable['work_packages']
worker_deliverable['metadata']['total_wps'] = len(wps)
worker_deliverable['metadata']['total_effort_hours'] = sum(wp.get('effort_hours', 0) for wp in wps)
worker_deliverable['metadata']['covered_req_ids'] = list(set(
    req_id for wp in wps for req_id in wp.get('covered_req_ids', [])
))

# 写入输出文件
normalized_role = '{worker_role}'.replace(' ', '_')
output_path = f'stages/worker_outputs/worker_{normalized_role}.json'
bb.write_json(output_path, worker_deliverable)

output_size = os.path.getsize(bb.resolve_path(output_path))
print(f'OUTPUT_WRITTEN: {output_path} ({output_size} bytes)')
print(f'WP_COUNT: {len(wps)}')
print(f'COVERED_REQS: {json.dumps(worker_deliverable[\"metadata\"][\"covered_req_ids\"])}')
print('WORKER_OUTPUT_OK')
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

# 验证输出
normalized_role = '{worker_role}'.replace(' ', '_')
output_path = f'stages/worker_outputs/worker_{normalized_role}.json'
deliverable = bb.read_json(output_path)

if not deliverable:
    print('OUTPUT_MISSING')
    exit(1)

# 检查必需字段
required = ['worker_role', 'work_packages', 'metadata']
missing = [f for f in required if f not in deliverable]
if missing:
    print(f'OUTPUT_INVALID: missing {missing}')
    exit(1)

# 检查 work_packages 非空
wps = deliverable.get('work_packages', [])
if not wps:
    print('OUTPUT_INVALID: work_packages is empty')
    exit(1)

# 检查每个 WP 的必需字段
wp_required = ['wp_id', 'status', 'title', 'description', 'acceptance_criteria', 'deliverables', 'effort_hours', 'dependencies', 'covered_req_ids', 'anchored_to', 'source_worker']
for wp in wps:
    wp_missing = [f for f in wp_required if f not in wp]
    if wp_missing:
        print(f'WP_INVALID: {wp.get(\"wp_id\", \"?\")} missing {wp_missing}')
        exit(1)

# 检查文件大小
full_path = bb.resolve_path(output_path)
file_size = os.path.getsize(full_path)
if file_size < 2000:
    print(f'OUTPUT_TOO_SMALL: {file_size} bytes < 2000')
    exit(1)

# 完成标记
lifecycle.mark_completed('workers', '{run_id}', output_files={
    output_path: {'size': file_size},
})

print(f'WORKER_ROLE: {deliverable[\"worker_role\"]}')
print(f'WP_COUNT: {len(wps)}')
print(f'FILE_SIZE: {file_size} bytes')
print('WORKER_COMPLETED')
"
```

---

## 输出格式

```json
{
  "worker_role": "{worker_role}",
  "work_packages": [
    {
      "wp_id": "CORE-001",
      "status": "draft",
      "title": "搭建核心 API 框架",
      "description": "基于 FastAPI 搭建核心 API 框架，包括路由注册、中间件配置、错误处理、日志系统。采用分层架构（Router → Service → Repository），支持依赖注入和单元测试。",
      "acceptance_criteria": [
        "AC1: API 框架能正常启动并响应请求",
        "AC2: 所有中间件按顺序执行",
        "AC3: 错误响应格式统一为 JSON"
      ],
      "deliverables": [
        "src/api/framework.py",
        "src/api/middleware.py",
        "tests/test_framework.py"
      ],
      "effort_hours": 24,
      "dependencies": [],
      "covered_req_ids": ["REQ-001"],
      "anchored_to": ["fastapi", "uvicorn"],
      "source_worker": "{worker_role}"
    }
  ],
  "metadata": {
    "total_wps": 3,
    "total_effort_hours": 72,
    "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003"]
  }
}
```

---

## 禁止行为

- ❌ 不要修改 Pipeline Plan（只读）
- ❌ 不要修改其他 Worker 的输出文件（只写自己的）
- ❌ 不要跳过 Schema 校验
- ❌ 不要降级输出（不要写"默认值"或"占位符"）
- ❌ 不要自行重试（Orchestrator 负责重试）
- ❌ 不要产出模糊的 WP（description < 100 字、acceptance_criteria 不可验证）
