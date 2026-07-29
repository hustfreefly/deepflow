# Ship Pro Prompt 修复设计方案

> **版本**: V1.0  
> **日期**: 2026-07-29  
> **设计者**: Prompt 设计专家（Subagent）  
> **目标**: 将 consolidator.md 从 D 级提升到 B+ 级，将 orchestrator.md 从 B+ 级提升到 A- 级

---

## 目录

1. [问题分析](#1-问题分析)
2. [consolidator.md 修复方案（P0）](#2-consolidatormd-修复方案p0)
3. [orchestrator.md 修复方案（P1）](#3-orchestratormd-修复方案p1)
4. [与 Solution Pro 的对比](#4-与-solution-pro-的对比)
5. [实施建议](#5-实施建议)

---

## 1. 问题分析

### 1.1 consolidator.md 当前问题（D 级，6 个 P0）

| # | P0 问题 | 症状 | 根因 |
|---|---------|------|------|
| 1 | 无状态转移表 | 6 步法没有显式状态机，Agent 不知道"当前在哪一步、下一步去哪" | 只有步骤描述，没有状态流转定义 |
| 2 | 无完成条件 | 不知道"什么情况下算成功、什么情况下算失败" | 缺少成功条件 + 无法恢复条件的显式声明 |
| 3 | 无错误分类 | 所有错误一视同仁，要么全部 Fail Fast，要么全部忽略 | 没有区分瞬时故障/可恢复错误/不可恢复错误 |
| 4 | 无恢复机制 | 遇到问题直接失败，没有重试或降级 | Fail Fast 思维，没有 Recover Smart |
| 5 | 无中间产物持久化 | 6 步法的中间结果没有写入 blackboard | 没有定义每步的 checkpoint 文件 |
| 6 | 无契约笼子 | 没有输入契约、输出契约、错误处理契约 | 只有数据流描述，没有契约定义 |

### 1.2 orchestrator.md 当前问题（B+ 级，2 个 P1）

| # | P1 问题 | 症状 | 根因 |
|---|---------|------|------|
| 1 | 无智能重试 | Designer/Workers/Consolidator 失败后直接写 `.failed`，没有重试 | 没有参考 Solution Pro V4.1 的智能重试机制 |
| 2 | 无 Worker 执行契约注入 | Workers 的执行契约分散在各自的 prompt 中 | 没有参考 Solution Pro planning_module.md 的上级设定机制 |

---

## 2. consolidator.md 修复方案（P0）

### 2.1 状态转移表（修复 P0-1）

**设计思路**：将 6 步法映射为 8 个状态的状态机，每个状态有明确的出边和恢复策略。

```markdown
## 🔴 状态机（必须严格遵循）

### 状态全集（8 个状态）

#### 终态（2 个）

| 状态 | 含义 | 出边 |
|------|------|------|
| `CONSOLIDATOR_COMPLETED` | ✅ ShipPackage 生成并通过所有 Gate | 无 |
| `CONSOLIDATOR_FAILED` | ❌ 不可恢复失败 | 无 |

#### 执行状态（6 个）

| 状态 | 对应步骤 | 含义 |
|------|---------|------|
| `INIT` | - | Consolidator 刚启动 |
| `DOMAIN_ANALYSIS` | Step 0 | 领域判断，确定组装策略 |
| `COLLECTION` | Step 1 | 收集所有 Worker 的 WP |
| `SEMANTIC_INTEGRATION` | Step 2 | 语义整合（互补/冲突/重复） |
| `CONFLICT_DETECTION` | Step 3 | 冲突检测 |
| `DEPENDENCY_GRAPH` | Step 4 | 依赖图构建 |
| `ANCHOR_PASSTHROUGH` | Step 5 | Semantic Anchors 透传 |
| `ASSEMBLY` | Step 6 | 最终组装 |

### 状态转移图

```
INIT ──exec──▶ DOMAIN_ANALYSIS
                    │
             ┌──────┴──────┐
             │             │
       DOMAIN_OK      DOMAIN_MISSING
             │             │
             ▼             ▼
        COLLECTION    CONSOLIDATOR_FAILED
             │
      ┌──────┴──────┐
      │             │
COLLECTION_OK   COLLECTION_MISSING
      │             │
      ▼             ▼
SEMANTIC_INTEGRATION  CONSOLIDATOR_FAILED
      │
      ▼
CONFLICT_DETECTION
      │
      ▼
DEPENDENCY_GRAPH
      │
      ▼
ANCHOR_PASSTHROUGH
      │
 ┌────┴─────┐
 │          │
ANCHOR_OK  ANCHOR_MISSING
 │          │
 ▼          ▼
ASSEMBLY  CONSOLIDATOR_FAILED
 │
 ▼
CONSOLIDATOR_COMPLETED
```

### 转移表

| # | 当前状态 | 目标状态 | 触发条件 | 动作 | 恢复策略 |
|---|---------|---------|---------|------|---------|
| T1 | `INIT` | `DOMAIN_ANALYSIS` | 入口 | exec: 读取 pipeline_plan | - |
| T2 | `DOMAIN_ANALYSIS` | `COLLECTION` | `DOMAIN_OK` | exec: 读取 worker_file_paths | - |
| T3 | `DOMAIN_ANALYSIS` | `CONSOLIDATOR_FAILED` | `DOMAIN_MISSING` | 写 `.consolidator_failed` | 不可恢复 |
| T4 | `COLLECTION` | `SEMANTIC_INTEGRATION` | `COLLECTION_OK` | exec: 提取所有 WP | - |
| T5 | `COLLECTION` | `COLLECTION_RETRY` | `COLLECTION_MISSING` | 触发智能重试 | 等待 30s 后重试 |
| T6 | `SEMANTIC_INTEGRATION` | `CONFLICT_DETECTION` | `INTEGRATION_OK` | exec: 语义整合 | - |
| T7 | `CONFLICT_DETECTION` | `DEPENDENCY_GRAPH` | `CONFLICT_OK` | exec: 冲突检测 | - |
| T8 | `DEPENDENCY_GRAPH` | `ANCHOR_PASSTHROUGH` | `DEPENDENCY_OK` | exec: 构建依赖图 | - |
| T9 | `ANCHOR_PASSTHROUGH` | `ASSEMBLY` | `ANCHOR_OK` | exec: 透传 anchors | - |
| T10 | `ANCHOR_PASSTHROUGH` | `ANCHOR_RETRY` | `ANCHOR_MISSING` | 触发智能重试 | 等待 30s 后重试 |
| T11 | `ASSEMBLY` | `CONSOLIDATOR_COMPLETED` | `ASSEMBLY_OK` | 写 ShipPackage + `.consolidator_completed` | - |
| T12 | `ASSEMBLY` | `ASSEMBLY_RETRY` | `ASSEMBLY_MISSING` | 触发智能重试 | 等待 60s 后重试 |
```

### 2.2 契约笼子（修复 P0-6）

**设计思路**：参考 Solution Pro V4.1 的契约笼子模式，为 consolidator 设计输入/输出/错误处理三层契约。

```markdown
## 🔴 契约笼子（稳健性优先）

### 输入契约（模块输出必须满足）

**Worker 输出文件契约**（Pydantic 强制校验）：
- ✅ 文件必须存在且非空
- ✅ 文件大小必须 >= 2000 bytes（每个 Worker）
- ✅ 文件内容必须是有效 JSON
- ✅ 必须包含 `work_packages` 数组
- ❌ 如果不满足 → 触发智能重试（不是直接失败）

**Pipeline Plan 契约**：
- ✅ `pipeline_plan.json` 必须存在且非空
- ✅ 必须包含 `workers` 数组（用于确定 Worker 角色）
- ✅ 必须包含 `domain_analysis` 字段（用于确定组装策略）
- ❌ 如果不满足 → 尝试从 WP 的 deliverables 推断组装策略

**Solution Pro Input 契约**：
- ✅ `solution_pro_input.json` 必须存在（用于提取 semantic_anchors）
- ✅ 如果 `semantic_anchors` 不存在 → 设为 `[]` 且 `anchor_coverage` 设为 `{}`

### 输出契约（ShipPackage 必须满足）

**ShipPackage 输出契约**（Pydantic 强制校验）：
- ✅ 文件必须存在且非空
- ✅ 文件大小必须 >= 50000 bytes
- ✅ 文件内容必须是有效 JSON
- ✅ 必须包含以下必需字段：
  - `solution_name` (string)
  - `work_packages` (array, 非空)
  - `dependency_graph` (object)
  - `metadata` (object)
  - `semantic_anchors` (array, 可以为空但不能缺失)
  - `anchor_coverage` (object, 可以为空但不能缺失)
- ✅ `work_packages` 中的每个 WP 必须包含：
  - `wp_id`, `status`, `title`, `description`, `acceptance_criteria`, `deliverables`
  - `effort_hours`, `dependencies`, `covered_req_ids`, `anchored_to`, `source_worker`
- ✅ `status` 字段必须为 `"draft"`
- ❌ 如果不满足 → 触发智能重试（不是直接失败）

### 错误处理契约（智能重试，不降级）

**错误分类与恢复策略**：

| 错误类型 | 特征 | 恢复策略 |
|---------|------|---------|
| **瞬时故障** | 文件不存在、文件为空 | 等待 30 秒后重试（最多 2 次）|
| **可恢复错误** | 文件大小不足、JSON 格式错误、WP 缺失字段 | 从 checkpoint 恢复，重新执行对应步骤（最多 2 次）|
| **不可恢复错误** | pipeline_plan 损坏、所有 worker 文件缺失、solution_pro_input 损坏 | 报告详细失败原因（包含：哪个步骤、已尝试什么、建议什么）|

**智能重试流程**：
```
步骤输出 MISSING →
  1. 检查错误类型（瞬时故障？可恢复错误？）
  2. 检查重试次数（retry_count[step]）
  3. 如果 retry_count[step] < 2：
     - 重试 1：等待 30 秒 → 从 checkpoint 恢复 → 重新执行对应步骤
     - 重试 2：等待 60 秒 → 从 checkpoint 恢复 → 重新执行对应步骤
  4. 如果 2 次重试后仍 MISSING → 报告详细失败原因
```

**失败报告格式**（如果无法恢复）：
```json
{
  "status": "failed",
  "error_type": "unrecoverable",
  "failed_step": "collection / semantic_integration / assembly / ...",
  "error_message": "具体错误信息",
  "attempted_actions": [
    "重试 1: 等待 30 秒后从 checkpoint 恢复",
    "重试 2: 等待 60 秒后从 checkpoint 恢复"
  ],
  "suggestions": [
    "检查 worker_outputs 目录中的文件是否完整",
    "检查 pipeline_plan.json 是否正确",
    "检查 solution_pro_input.json 是否存在"
  ]
}
```
```

### 2.3 完成条件（修复 P0-2）

```markdown
## 🔴 完成条件

### 成功条件（必须全部满足）

1. **所有 WP 已合并**：
   - `work_packages` 数组包含所有 Worker 的所有 WP
   - 没有丢弃任何 Worker 的 WP
   - 没有遗漏任何本批次 Worker 的输出

2. **Semantic Anchors 已透传**：
   - `semantic_anchors` 字段存在且非空（如果上游有）
   - `anchor_coverage` 字段存在
   - `anchor_coverage._uncovered` 列出未被任何 WP 引用的 anchor

3. **依赖图已构建**：
   - `dependency_graph.edges` 包含所有跨 WP 的依赖关系
   - `dependency_graph.execution_layers` 包含所有 WP

4. **ShipPackage 已写入**：
   - 文件写入 `stages/ship_package.json`
   - 文件大小 >= 50000 bytes
   - 通过 Pydantic Schema 校验

5. **完成标记已写入**：
   - 写入 `.consolidator_completed`
   - 调用 `lifecycle.mark_completed('consolidator', run_id, output_files={...})`

### 无法恢复条件（任一满足即失败）

1. **所有 Worker 输出文件缺失**：
   - `stages/worker_outputs/` 目录为空
   - 重试 2 次后仍为空

2. **pipeline_plan.json 损坏**：
   - 文件不存在或 JSON 格式错误
   - 重试 2 次后仍损坏

3. **ShipPackage 无法生成**：
   - 重试 2 次后仍无法通过 Schema 校验
   - 文件大小始终 < 50000 bytes

4. **Semantic Anchors 透传失败**：
   - `solution_pro_input.json` 不存在或损坏
   - 重试 2 次后仍损坏
```

### 2.4 错误分类（修复 P0-3）

```markdown
## 🔴 错误分类

### 瞬时故障（自动重试）

| 错误 | 特征 | 恢复策略 |
|------|------|---------|
| 文件不存在 | `FileNotFoundError` | 等待 30 秒后重试 |
| 文件为空 | `file_size == 0` | 等待 30 秒后重试 |
| 读取超时 | `TimeoutError` | 等待 30 秒后重试 |

### 可恢复错误（修复后重试）

| 错误 | 特征 | 恢复策略 |
|------|------|---------|
| 文件大小不足 | `file_size < min_size` | 从 checkpoint 恢复，重新执行对应步骤 |
| JSON 格式错误 | `json.JSONDecodeError` | 尝试修复 JSON → 重新执行对应步骤 |
| WP 缺失字段 | Pydantic 校验失败 | 尝试从原始数据提取 → 重新执行对应步骤 |
| WP 语义重叠 | 多个 WP 覆盖相同功能 | 整合为更完整的 WP（不是删除） |
| WP 冲突 | 多个 WP 对同一功能有矛盾方案 | 在 `metadata.issues` 中标记，保留两个 WP |

### 不可恢复错误（报告失败）

| 错误 | 特征 | 恢复策略 |
|------|------|---------|
| pipeline_plan 损坏 | JSON 格式错误且无法修复 | 报告详细失败原因 |
| 所有 worker 文件缺失 | `worker_outputs/` 目录为空 | 报告详细失败原因 |
| solution_pro_input 损坏 | JSON 格式错误且无法修复 | 报告详细失败原因 |
| ShipPackage 无法生成 | 重试 2 次后仍无法通过 Schema 校验 | 报告详细失败原因 |
```

### 2.5 恢复机制（修复 P0-4）

```markdown
## 🔴 恢复机制

### 智能重试（参考 Solution Pro V4.1）

**重试策略**：
- ✅ 重试 2 次（等待 30 秒 + 60 秒）
- ✅ 从 checkpoint 恢复（不从头开始）
- ✅ 报告详细失败原因（包含已尝试什么、建议什么）
- ❌ 不降级（不跳过步骤，不用默认值）

**重试实现**：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
from core.process_manager import SingleSourceStateManager
import datetime, time

bb = BlackboardManager('{session_id}')
state_mgr = SingleSourceStateManager(str(bb.session_dir))
step = '{current_step}'  # 'collection' / 'semantic_integration' / 'assembly' / ...

# 检查重试次数
retry_key = f'consolidator_retry_count_{step}'
retry_count = bb.read_stage(retry_key, default=0)

if retry_count < 2:
    # 智能重试
    wait_time = 30 if retry_count == 0 else 60
    print(f'RETRY_{step.upper()}: attempt {retry_count + 1}, waiting {wait_time}s')
    time.sleep(wait_time)
    
    # 更新重试计数
    bb.write_stage(retry_key, retry_count + 1)
    
    # 从 checkpoint 恢复，重新执行对应步骤
    print(f'RETRY_STEP: {step}')
else:
    # 重试 2 次后仍失败，报告详细失败原因
    bb.write_stage('.consolidator_failed', {
        'session_id': '{session_id}',
        'failed_step': step,
        'failed_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'reason': 'MISSING_AFTER_2_RETRIES',
        'error_type': 'unrecoverable',
        'attempted_actions': [
            '重试 1: 等待 30 秒后从 checkpoint 恢复',
            '重试 2: 等待 60 秒后从 checkpoint 恢复'
        ],
        'suggestions': [
            f'检查 {step} 步骤的输入文件是否正确',
            f'检查 blackboard 目录是否可写',
            f'检查 {step} 步骤的逻辑是否正确'
        ],
        'architecture_version': 'v3.1',
    })
    print('CONSOLIDATOR_FAILED')
"
```

### 降级策略（仅在极端情况下使用）

**注意**：降级策略只在"无法恢复"且"用户明确要求继续"时使用。

| 场景 | 降级策略 |
|------|---------|
| 部分 Worker 文件缺失 | 在 `metadata.issues` 中标记，继续处理已有的 WP |
| semantic_anchors 缺失 | 设为 `[]` 且 `anchor_coverage` 设为 `{}` |
| domain_analysis 缺失 | 从 WP 的 deliverables 推断组装策略 |
```

### 2.6 中间产物持久化（修复 P0-5）

```markdown
## 🔴 中间产物持久化

### Checkpoint 文件清单

| 步骤 | Checkpoint 文件 | 内容 |
|------|----------------|------|
| Step 0 (Domain Analysis) | `.consolidator_checkpoint_domain.json` | `{"last_completed_step": 0, "domain": "软件开发", "assembly_strategy": "合并 WP 列表"}` |
| Step 1 (Collection) | `.consolidator_checkpoint_collection.json` | `{"last_completed_step": 1, "total_wps": 25, "worker_count": 5}` |
| Step 2 (Semantic Integration) | `.consolidator_checkpoint_integration.json` | `{"last_completed_step": 2, "merged_wps": 3, "conflict_wps": 2}` |
| Step 3 (Conflict Detection) | `.consolidator_checkpoint_conflict.json` | `{"last_completed_step": 3, "conflicts_found": 2}` |
| Step 4 (Dependency Graph) | `.consolidator_checkpoint_dependency.json` | `{"last_completed_step": 4, "dependency_edges": 15}` |
| Step 5 (Anchor Passthrough) | `.consolidator_checkpoint_anchor.json` | `{"last_completed_step": 5, "anchor_count": 10, "uncovered_count": 2}` |
| Step 6 (Assembly) | `.consolidator_completed` | `{"status": "completed", "ship_package_size": 52340}` |

### Checkpoint 写入时机

**每个步骤完成后立即写入 checkpoint**：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import datetime

bb = BlackboardManager('{session_id}')

# Step X 完成后
bb.write_stage('.consolidator_checkpoint_{step}', {
    'last_completed_step': {step_number},
    'step_name': 'step{step_number}_{step_name}',
    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    # 步骤特定的统计信息
    {step_specific_stats}
})

# 心跳调用
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager(str(bb.session_dir))
lifecycle.heartbeat('consolidator', '{run_id}')

print('CHECKPOINT_WRITTEN: step {step_number}')
"
```

### 断点恢复协议

**当 Consolidator crash 或重启时**：

1. **读取 checkpoint 文件** → 获取最后完成的步骤
2. **根据步骤决定恢复动作**：

| 最后完成步骤 | 恢复动作 |
|------------|---------|
| 0 (Domain Analysis) | 从 Step 1 (Collection) 开始 |
| 1 (Collection) | 从 Step 2 (Semantic Integration) 开始 |
| 2 (Semantic Integration) | 从 Step 3 (Conflict Detection) 开始 |
| 3 (Conflict Detection) | 从 Step 4 (Dependency Graph) 开始 |
| 4 (Dependency Graph) | 从 Step 5 (Anchor Passthrough) 开始 |
| 5 (Anchor Passthrough) | 从 Step 6 (Assembly) 开始 |
| 6 (Assembly) | 已完成，直接返回 `CONSOLIDATOR_COMPLETED` |

**恢复实现**：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager

bb = BlackboardManager('{session_id}')

# 检查断点
checkpoint = None
for step in [6, 5, 4, 3, 2, 1, 0]:
    checkpoint = bb.read_stage(f'.consolidator_checkpoint_{{\"domain\" if step == 0 else \"collection\" if step == 1 else \"integration\" if step == 2 else \"conflict\" if step == 3 else \"dependency\" if step == 4 else \"anchor\"}}', default=None)
    if checkpoint:
        break

if checkpoint:
    last_step = checkpoint.get('last_completed_step', -1)
    print(f'RESUMING: Last completed step = {last_step}, starting from step {last_step + 1}')
else:
    print('FRESH_START: No checkpoint found, starting from Step 0')
```
```

### 2.7 consolidator.md 修复后的完整结构

```markdown
# Ship Pro V3.1 — Consolidator (6-Step Assembly)

> **V3.1 核心变更**：
> 1. 添加显式状态机（8 个状态，12 条形式化转移）
> 2. 添加契约笼子（输入契约 + 输出契约 + 错误处理契约）
> 3. 添加完成条件（成功条件 + 无法恢复条件）
> 4. 添加错误分类（瞬时故障/可恢复错误/不可恢复错误）
> 5. 添加恢复机制（智能重试，参考 Solution Pro V4.1）
> 6. 添加中间产物持久化（checkpoint 文件）

## 🔴 状态机（必须严格遵循）
[见 2.1 节]

## 🔴 契约笼子（稳健性优先）
[见 2.2 节]

## 🔴 完成条件
[见 2.3 节]

## 🔴 错误分类
[见 2.4 节]

## 🔴 恢复机制
[见 2.5 节]

## 🔴 中间产物持久化
[见 2.6 节]

## 6 步法（必须按顺序执行）

### Step 0: 领域判断
[原有内容 + checkpoint 写入]

### Step 1: 收集
[原有内容 + checkpoint 写入]

### Step 2: 语义整合
[原有内容 + checkpoint 写入]

### Step 3: 冲突检测
[原有内容 + checkpoint 写入]

### Step 4: 依赖图
[原有内容 + checkpoint 写入]

### Step 5: Semantic Anchors 透传
[原有内容 + checkpoint 写入]

### Step 6: 组装
[原有内容 + 完成标记写入]
```

---

## 3. orchestrator.md 修复方案（P1）

### 3.1 智能重试（修复 P1-1）

**设计思路**：参考 Solution Pro V4.1 的智能重试机制，为 Designer/Workers/Consolidator 三个阶段增加重试逻辑。

```markdown
## 🔴 智能重试（V3.1 新增 — 稳健性优先）

### 错误分类与恢复策略

| 错误类型 | 特征 | 恢复策略 |
|---------|------|---------|
| **瞬时故障** | 文件不存在、文件为空 | 等待 30 秒后重试（最多 2 次）|
| **可恢复错误** | 文件大小不足、JSON 格式错误 | 从 checkpoint 恢复，重新执行模块（最多 2 次）|
| **不可恢复错误** | 模块 spawn 失败、checkpoint 损坏 | 报告详细失败原因（包含：哪个模块、已尝试什么、建议什么）|

### 智能重试流程

**模块输出 MISSING 时的处理**：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
from core.process_manager import SingleSourceStateManager
import datetime, time

bb = BlackboardManager('{session_id}')
state_mgr = SingleSourceStateManager(str(bb.session_dir))
module = '{current_module}'  # 'designer' / 'workers' / 'consolidator'

# 检查重试次数
retry_key = f'retry_count_{module}'
retry_count = bb.read_stage(retry_key, default=0)

if retry_count < 2:
    # 智能重试
    wait_time = 30 if retry_count == 0 else 60
    print(f'RETRY_{module.upper()}: attempt {retry_count + 1}, waiting {wait_time}s')
    time.sleep(wait_time)
    
    # 更新重试计数
    bb.write_stage(retry_key, retry_count + 1)
    
    # 从 checkpoint 恢复，重新 spawn 模块
    print(f'RETRY_SPAWN: {module}')
else:
    # 重试 2 次后仍失败，报告详细失败原因
    bb.write_stage('.failed', {
        'session_id': '{session_id}',
        'failed_module': module,
        'failed_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'reason': 'MISSING_AFTER_2_RETRIES',
        'error_type': 'unrecoverable',
        'attempted_actions': [
            '重试 1: 等待 30 秒后从 checkpoint 恢复',
            '重试 2: 等待 60 秒后从 checkpoint 恢复'
        ],
        'suggestions': [
            f'检查 {module} 模块 prompt 是否正确',
            f'检查 blackboard 目录是否可写',
            f'检查 {module} 模块的 Worker 是否正常执行'
        ],
        'architecture_version': 'v3.1',
    })
    print('PIPELINE_FAILED')
"
```

### 重试配置

| 模块 | 重试次数 | 等待时间 | 恢复策略 |
|------|---------|---------|---------|
| Designer | 2 次 | 30s + 60s | 从 checkpoint 恢复，重新 spawn Designer |
| Workers | 2 次 | 30s + 60s | 从 checkpoint 恢复，只重新 spawn 缺失的 Workers |
| Consolidator | 2 次 | 30s + 60s | 从 checkpoint 恢复，重新 spawn Consolidator |

### 状态转移表（更新）

**新增状态**：
- `RETRY_DESIGNER`: Designer 重试状态
- `RETRY_WORKERS`: Workers 重试状态
- `RETRY_CONSOLIDATOR`: Consolidator 重试状态

**新增转移**：
- `DESIGNER_VALIDATE` → `RETRY_DESIGNER`（如果 `DESIGNER_MISSING` 且 `retry_count < 2`）
- `RETRY_DESIGNER` → `DESIGNER_SPAWN`（从 checkpoint 恢复）
- `WORKERS_VALIDATE` → `RETRY_WORKERS`（如果 `WORKERS_MISSING` 且 `retry_count < 2`）
- `RETRY_WORKERS` → `WORKERS_SPAWN`（从 checkpoint 恢复，只重试缺失的 Workers）
- `CONSOLIDATOR_VALIDATE` → `RETRY_CONSOLIDATOR`（如果 `CONSOLIDATOR_MISSING` 且 `retry_count < 2`）
- `RETRY_CONSOLIDATOR` → `CONSOLIDATOR_SPAWN`（从 checkpoint 恢复）

### Workers 阶段的特殊处理

**Workers 阶段的重试需要特殊处理**：只重新 spawn 缺失的 Workers，而不是全部 Workers。

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json

bb = BlackboardManager('{session_id}')
plan = bb.read_json('stages/pipeline_plan.json')
roles = [w['role'] for w in plan.get('workers', [])]

# 检查哪些 Worker 已完成
missing_roles = []
for role in roles:
    normalized_role = role.replace(' ', '_')
    worker_file = f'stages/worker_outputs/worker_{normalized_role}.json'
    if not bb.exists(worker_file):
        missing_roles.append(role)

print(f'MISSING_WORKERS: {json.dumps(missing_roles)}')
print(f'MISSING_COUNT: {len(missing_roles)}')

# 如果所有 Worker 都缺失，重试全部
# 如果只有部分 Worker 缺失，只重试缺失的
if len(missing_roles) == len(roles):
    print('RETRY_ALL_WORKERS')
else:
    print(f'RETRY_MISSING_WORKERS: {missing_roles}')
"
```
```

### 3.2 Worker 执行契约注入（修复 P1-2）

**设计思路**：参考 Solution Pro planning_module.md 的上级设定机制，由 Orchestrator 在 spawn Workers 时统一注入执行契约。

```markdown
## 🔴 Worker 执行契约（V3.1 新增 — 由 Orchestrator 统一注入）

### 架构决策

**Worker 的执行契约由 Orchestrator 在 spawn task 中统一注入，而不是每个 Worker prompt 自己写。**

**为什么？**
- 单一信息源：Orchestrator 是编排者，它决定每个 Worker 的行为规范
- 减少重复：N 个 Worker 不需要各自维护同样的契约
- 更容易维护：改一个 Orchestrator 就能影响所有它管理的 Workers
- 符合架构原则：编排层负责编排逻辑，执行层专注执行

### 执行契约模板

```python
WORKER_CONTRACT = """
## 🔴 你的执行契约（由 Orchestrator 注入）

### 任务边界
- ✅ 你只负责：{worker_role}
- ❌ 你不负责：重试逻辑、错误恢复、降级输出

### 完成条件
- 输出写入 blackboard 且通过 Schema 校验
- 输出文件大小 >= {min_size} bytes
- 输出文件路径：stages/worker_outputs/worker_{normalized_role}.json

### 错误报告
如果无法完成，写入 stages/.worker_failed.json：
```json
{
  "worker_role": "{worker_role}",
  "error_type": "unrecoverable",
  "error_message": "具体错误信息",
  "suggestions": ["建议的后续动作"]
}
```

### 禁止行为
- ❌ 不要自行重试（Orchestrator 负责重试）
- ❌ 不要降级输出（不要写"默认值"或"占位符"）
- ❌ 不要跳过 Schema 校验
- ❌ 不要修改其他 Worker 的输出文件
"""
```

### Spawn Task 模板（更新）

**Step 2c 的 spawn 代码需要更新**：

```python
from core.blackboard.blackboard_manager import BlackboardManager
import json
bb = BlackboardManager('{session_id}')
run_id = '{run_id}'
plan = bb.read_json('stages/pipeline_plan.json')
roles = [w['role'] for w in plan.get('workers', [])]
_deepflow_root = str(bb.session_dir.parent.parent)
_failed_path = bb.resolve_path('stages/.failed')

# Worker 执行契约模板
WORKER_CONTRACT = """
## 🔴 你的执行契约（由 Orchestrator 注入）

### 任务边界
- ✅ 你只负责：{worker_role}
- ❌ 你不负责：重试逻辑、错误恢复、降级输出

### 完成条件
- 输出写入 blackboard 且通过 Schema 校验
- 输出文件大小 >= 2000 bytes
- 输出文件路径：stages/worker_outputs/worker_{normalized_role}.json

### 错误报告
如果无法完成，写入 stages/.worker_failed.json：
{{
  "worker_role": "{worker_role}",
  "error_type": "unrecoverable",
  "error_message": "具体错误信息",
  "suggestions": ["建议的后续动作"]
}}

### 禁止行为
- ❌ 不要自行重试（Orchestrator 负责重试）
- ❌ 不要降级输出（不要写"默认值"或"占位符"）
- ❌ 不要跳过 Schema 校验
- ❌ 不要修改其他 Worker 的输出文件
"""

for role in roles:
    normalized_role = role.replace(' ', '_')
    _prompt_path = bb.resolve_path(f'stages/worker_{normalized_role}_prompt.md')
    
    # 注入执行契约到 spawn task
    sessions_spawn(
        runtime="subagent",
        mode="run",
        label=f"ship_worker_{normalized_role}",
        task=f"""cd {_deepflow_root} && PYTHONPATH=.
你执行的所有 Python 命令必须以 `cd {_deepflow_root} && PYTHONPATH=.` 开头。

session_id: `{session_id}`
RUN_ID: `{run_id}`
worker_role: `{role}`
blackboard: `{str(bb.session_dir)}`

{WORKER_CONTRACT.format(worker_role=role, normalized_role=normalized_role)}

## 你的完整指令
用 read 工具读取: {_prompt_path}

读取后按指令执行。
如果文件不存在 → 写入 `{_failed_path}` 并立即结束。""",
        cwd=_deepflow_root,
        lightContext=True,
    )
```

### 同样的模式应用于 Designer 和 Consolidator

**Designer 执行契约**：

```python
DESIGNER_CONTRACT = """
## 🔴 你的执行契约（由 Orchestrator 注入）

### 任务边界
- ✅ 你只负责：分析 Frozen Spec，生成 Pipeline Plan（包括 Worker 角色定义）
- ❌ 你不负责：执行 Worker 任务、重试逻辑、错误恢复、降级输出

### 完成条件
- 输出写入 blackboard 的 stages/pipeline_plan.json
- 输出文件大小 >= 10000 bytes
- 必须包含 `workers` 数组（定义 Worker 角色）

### 错误报告
如果无法完成，写入 stages/.designer_failed.json：
{
  "module": "designer",
  "error_type": "unrecoverable",
  "error_message": "具体错误信息",
  "suggestions": ["建议的后续动作"]
}

### 禁止行为
- ❌ 不要自行重试（Orchestrator 负责重试）
- ❌ 不要降级输出（不要写"默认值"或"占位符"）
- ❌ 不要跳过 Schema 校验
"""
```

**Consolidator 执行契约**：

```python
CONSOLIDATOR_CONTRACT = """
## 🔴 你的执行契约（由 Orchestrator 注入）

### 任务边界
- ✅ 你只负责：合并所有 Worker 的 WP 为 ShipPackage
- ❌ 你不负责：执行 Worker 任务、重试逻辑、错误恢复、降级输出

### 完成条件
- 输出写入 blackboard 的 stages/ship_package.json
- 输出文件大小 >= 50000 bytes
- 必须包含 `semantic_anchors` 和 `anchor_coverage` 字段

### 错误报告
如果无法完成，写入 stages/.consolidator_failed.json：
{
  "module": "consolidator",
  "error_type": "unrecoverable",
  "error_message": "具体错误信息",
  "suggestions": ["建议的后续动作"]
}

### 禁止行为
- ❌ 不要自行重试（Orchestrator 负责重试）
- ❌ 不要降级输出（不要写"默认值"或"占位符"）
- ❌ 不要跳过 Schema 校验
- ❌ 不要丢弃任何 Worker 的 WP
"""
```
```

### 3.3 orchestrator.md 修复后的完整结构

```markdown
# Ship Pro V3.1 — Orchestrator (4-Phase Pipeline)

> **V3.1 核心变更**：
> 1. 添加智能重试（参考 Solution Pro V4.1）
> 2. 添加 Worker 执行契约注入（参考 Solution Pro planning_module.md）
> 3. 添加错误分类与恢复策略
> 4. 更新状态转移表（新增 RETRY_* 状态）

## 🔴 智能重试（V3.1 新增）
[见 3.1 节]

## 🔴 Worker 执行契约（V3.1 新增）
[见 3.2 节]

## 🔴 绝对禁止
[原有内容]

## 🔴 执行循环（最高优先级）
[原有内容 + 更新信号路由表]

## 🔴 状态机（必须严格遵循）
[原有内容 + 新增 RETRY_* 状态和转移]

## 🔴 Completion Event 处理规则
[原有内容]

## 🔴 状态管理（单一真相源）
[原有内容]

## 执行算法
[原有内容 + 更新 spawn 代码（注入执行契约）]
```

---

## 4. 与 Solution Pro 的对比

### 4.1 可以复用的部分

| 组件 | Solution Pro 版本 | Ship Pro 复用方式 |
|------|------------------|------------------|
| 智能重试框架 | V4.1 orchestrator.md | 直接复用重试逻辑（等待 30s + 60s，最多 2 次） |
| Worker 执行契约模板 | V3.3 planning_module.md | 直接复用契约模板结构（任务边界 + 完成条件 + 错误报告 + 禁止行为） |
| 契约笼子设计模式 | V4.1 orchestrator.md | 直接复用三层契约结构（输入契约 + 输出契约 + 错误处理契约） |
| 错误分类 | V4.1 orchestrator.md | 直接复用错误分类表（瞬时故障/可恢复错误/不可恢复错误） |
| Checkpoint 机制 | V3.3 planning_module.md | 直接复用 checkpoint 文件结构和断点恢复协议 |

### 4.2 需要定制的部分

| 组件 | Solution Pro 版本 | Ship Pro 定制原因 |
|------|------------------|------------------|
| Workers 阶段的重试 | 无（Solution Pro 的 Workers 在 Module Agent 内部） | Ship Pro 的 Workers 由 Orchestrator 直接管理，需要特殊处理"只重试缺失的 Workers" |
| Consolidator 状态机 | 无（Solution Pro 没有 Consolidator） | Ship Pro 需要为 Consolidator 的 6 步法设计专用状态机 |
| ShipPackage Schema | 无（Solution Pro 没有 ShipPackage） | Ship Pro 需要为 ShipPackage 设计专用的输出契约 |
| Semantic Anchors 透传 | 无（Solution Pro 没有这个概念） | Ship Pro 需要为 Semantic Anchors 设计专用的契约和验证逻辑 |
| 依赖图构建 | 无（Solution Pro 没有这个步骤） | Ship Pro 需要为依赖图构建设计专用的验证逻辑 |

### 4.3 对比表

| 特性 | Solution Pro V4.1 | Ship Pro V3.1（修复后） |
|------|------------------|------------------------|
| 智能重试 | ✅ 2 次（30s + 60s） | ✅ 2 次（30s + 60s） |
| Worker 执行契约注入 | ✅ Module Agent 注入 | ✅ Orchestrator 注入 |
| 契约笼子 | ✅ 三层契约 | ✅ 三层契约 |
| 错误分类 | ✅ 三类错误 | ✅ 三类错误 |
| Checkpoint 机制 | ✅ Step 级 checkpoint | ✅ Step 级 checkpoint |
| 状态机 | ✅ 简化 3 模块 | ✅ 14 + 3 = 17 个状态 |
| 完成条件 | ✅ 成功 + 无法恢复 | ✅ 成功 + 无法恢复 |
| 中间产物持久化 | ✅ 每个 Step 后写入 | ✅ 每个 Step 后写入 |

---

## 5. 实施建议

### 5.1 实施顺序

1. **Phase 1: consolidator.md 修复（P0）**
   - 添加状态机（2.1）
   - 添加契约笼子（2.2）
   - 添加完成条件（2.3）
   - 添加错误分类（2.4）
   - 添加恢复机制（2.5）
   - 添加中间产物持久化（2.6）

2. **Phase 2: orchestrator.md 修复（P1）**
   - 添加智能重试（3.1）
   - 添加 Worker 执行契约注入（3.2）
   - 更新状态转移表（新增 RETRY_* 状态）

3. **Phase 3: 测试验证**
   - 使用 AgentDryRun Skill 进行六维体检
   - 使用 DeepFlowDryRun Skill 进行动态诊断
   - 验证断点恢复、智能重试、错误处理是否正常工作

### 5.2 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 智能重试增加执行时间 | 中等 | 限制重试次数为 2 次，使用指数退避 |
| Checkpoint 文件过多 | 低 | 只保留关键步骤的 checkpoint |
| Worker 执行契约注入失败 | 高 | 在 spawn task 中显式包含契约，不依赖外部文件 |
| 状态机复杂度过高 | 中等 | 保持状态转移表清晰，避免过度设计 |

### 5.3 成功标准

- ✅ consolidator.md 评级从 D 提升到 B+ 或更高
- ✅ orchestrator.md 评级从 B+ 提升到 A- 或更高
- ✅ 通过 Prompt Doctor V2.1 检查清单（Layer 1 + Layer 3 必须通过）
- ✅ 通过 AgentDryRun Skill 六维体检
- ✅ 实际运行中能够成功恢复瞬时故障和可恢复错误

---

## 附录

### A. 参考文件

- Solution Pro V4.1 orchestrator: `/Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/orchestrator.md`
- Solution Pro V3.3 planning_module: `/Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/planning_module.md`
- Prompt Doctor V2.1: `/Users/allen/.openclaw/workspace/.deepflow/skills/prompt-doctor/SKILL.md`
- Ship Pro V3.0 orchestrator: `/Users/allen/.openclaw/workspace/.deepflow/domains/ship_pro/prompts/orchestrator.md`
- Ship Pro consolidator: `/Users/allen/.openclaw/workspace/.deepflow/domains/ship_pro/prompts/consolidator.md`

### B. 术语表

| 术语 | 定义 |
|------|------|
| 契约笼子 | 输入契约 + 输出契约 + 错误处理契约的三层结构 |
| 智能重试 | 根据错误类型决定恢复策略，而不是直接失败 |
| Checkpoint | 每个步骤完成后写入的中间产物文件，用于断点恢复 |
| Worker 执行契约 | 由 Orchestrator/Module Agent 在 spawn task 中注入的执行规范 |
| 瞬时故障 | 网络超时、临时不可用等可以自动恢复的错误 |
| 可恢复错误 | 输入格式错误、部分数据缺失等可以修复后重试的错误 |
| 不可恢复错误 | 关键输入缺失、核心功能失败等无法恢复的错误 |

### C. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-07-29 | 初始版本，包含 consolidator.md 和 orchestrator.md 的修复方案 |

---

*文档版本：V1.0*  
*创建时间：2026-07-29*  
*设计者：Prompt 设计专家（Subagent）*  
*基于：Solution Pro V4.1 + Prompt Doctor V2.1 + 实战经验*
