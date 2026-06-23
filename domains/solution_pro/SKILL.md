# Solution Pro - Agent 执行指南

> **版本**: V4.4 | **最后更新**: 2026-06-03  
> **架构**: 固定 10 阶段 B 方案 + LLM Orchestrator + Cron 巡检通知 + REQ-ID 追踪质量门 + 状态持久化断点续接

---

## 🚀 主 Agent 执行步骤

### Step 0: 轻量 Spec Agent（场景B入口）

**触发条件**：用户没有先跑 Spec Pro，直接从对话启动 Solution Pro

**执行逻辑**：
```python
# 主 Agent 层面（可访问 LLM）
import json
from domains.solution.lightweight_spec_agent import infer_living_spec

topic = "{TOPIC}"
constraints = {CONSTRAINTS}  # 从用户输入提取

# 调用 LLM 推断 living_spec
def llm_call(prompt):
    # 主 Agent 的 LLM 调用逻辑
    return sessions_send(
        session_key="llm_worker",
        message=prompt,
        timeout=30
    )

living_spec = infer_living_spec(topic, constraints, llm_call)

# 保存为 JSON 文件（可选，便于调试）
import os
base_path = f"~/.openclaw/workspace/.deepflow/blackboard/sol_{int(time.time())}"
os.makedirs(base_path, exist_ok=True)
with open(f"{base_path}/inferred_living_spec.json", "w") as f:
    json.dump(living_spec, f, ensure_ascii=False, indent=2)
```

**注意事项**：
- 如果 LLM 调用失败，`infer_living_spec()` 会返回最小化的 living_spec（只有 objective）
- 轻量 Spec Agent 的输出质量不如完整 Spec Pro，但比纯 topic + constraints 好得多
- 后续可以优化为：先跑轻量 Spec Agent，再让用户确认/补充

### Step 1: 生成执行计划

```bash
cd ~/.openclaw/workspace/.deepflow && python3 -c "
import json
from domains.solution import run_solution_pro
result = run_solution_pro(
    topic='{TOPIC}',
    solution_type='{SOLUTION_TYPE}',
    constraints={CONSTRAINTS},
    stakeholders={STAKEHOLDERS},
    living_spec={LIVING_SPEC},  # 如果 Spec Pro 已产出，传入完整 living_spec
)
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

**living_spec 传递规则**：
- ✅ **有 Spec Pro 产出** → 传入完整 living_spec（包含 confirmed、inferred、guardrails 等）
- ✅ **普通对话入口** → 传入轻量 Spec Agent 生成的 living_spec（基于 topic + constraints 推断）
- ❌ **不传 living_spec** → frozen_spec 退化为 topic + constraints，REQ-ID 严重不足

`run_solution_pro()` 现在会自动完成：
- 生成 `tasks.json`、`execution_plan.json` 和 `data/frozen_spec.json`
- 清理旧的 `.completed`、`.cron_run_count`、`.notified_stages.json` 状态文件
- 初始化新的 cron 状态文件
- 读取并替换 orchestrator prompt 中的变量
- 返回 `spawn_params`（可直接传给 `sessions_spawn`）

### Step 2: 启动管线

```python
# 从 Step 1 的返回值中获取 spawn_params
sessions_spawn(**result["spawn_params"])
```

**关键**：`spawn_params` 已经包含了完整的 orchestrator prompt（变量已替换），直接传给 `sessions_spawn` 即可启动管线。

### Step 3: 向用户发送启动通知

```
✅ 已启动 DeepFlow Solution Pro 管线
📋 主题: {TOPIC}
📊 共 10 个阶段，预计 30-60 分钟
💬 期间你可以继续问我其他问题，完成后我会通知你
```

### Step 4: 创建 Cron 巡检 Agent

```python
from datetime import datetime

# 生成运行启动时间（用于时间戳校验）
run_start_at = datetime.now().isoformat()

# 创建 cron job
cron_result = cron(
    action="add",
    job={
        "name": f"deepflow_progress_{session_id[:8]}",
        "schedule": {"kind": "every", "everyMs": 180000},
        "sessionTarget": "isolated",
        "payload": {
            "kind": "agentTurn",
            "message": "<cron_watcher_prompt，替换 {base_path}, {session_id}, {cron_job_id}, {run_start_at}>",
            "timeoutSeconds": 120,
            "lightContext": True
        },
        "delivery": {"mode": "announce", "channel": "feishu", "to": "{FEISHU_TARGET}"},
        "enabled": True
    }
)

# 记录 cron job ID 和 run_start_at
cron_job_id = cron_result["id"]
with open(f"{base_path}/.cron_job_id", "w") as f:
    f.write(cron_job_id)
with open(f"{base_path}/.run_start_at", "w") as f:
    f.write(run_start_at)
```

**关键点**：
- `run_start_at` 是本次运行的启动时间，Cron Watcher 用它来校验 `.completed` 文件是否属于本次运行（防止旧文件残留导致误判）
- 🔴 **delivery 必须包含 channel 和 to**：多 channel 环境下（如 feishu + imessage），缺少 `to` 会导致 delivery 失败。标准模板见下方。

**🔴 Cron Delivery 标准模板**：
```json
{
  "delivery": {
    "mode": "announce",
    "channel": "feishu",
    "to": "<USER_OPEN_ID>",
    "accountId": "default"
  }
}
```
如果当前会话是 webchat，改用：
```json
{
  "delivery": {"mode": "announce"}
}
```
（webchat 不需要 channel/to）

### Step 6: yield 等待 orchestrator 完成

```python
sessions_yield()
```

orchestrator 完成后会自动 announce 回来。

### Step 7: 自动触发 Ship Pro（auto_chain）

当收到 Solution Pro 完成消息，且消息包含 `🔗 自动触发下游管线: ship_pro` 时：

1. 读取消息中的 `prepare` 命令并执行
2. 依次执行 `task` + `gate` 完成 Ship Pro 5 Agent 管线
3. 每个 Agent 完成后调用 `update-status`
4. 最终调用 `validate` 生成 ship_package.json

> **铁律**: 看到 "🔗 自动触发" 就必须执行，不要问用户是否继续。

---

## 🔄 Cron 巡检 Agent 行为

### Prompt 模板

见 `domains/solution_pro/prompts/cron_watcher.md`

### 核心逻辑

1. **更新运行计数** → 超过 20 次（60 分钟）→ 超时退出
2. **检查 .completed + 时间戳校验** → 存在且时间戳晚于 run_start_at → 发最终报告 → 自删
   （如果 .completed 早于 run_start_at → 旧文件残留，忽略，继续巡检）
3. **扫描 stages/** → 有新文件 → 发进度消息 → 更新 .notified_stages.json
4. **没有新文件** → NO_REPLY

### 消息策略

- **智能通知**：只在有新阶段完成时发消息（最多 11 条，非 20 条）
- **并行合并**：同一轮次发现的多个并行阶段合并为 1 条消息
- **空消息不发**：没有新进度时回复 NO_REPLY

### 状态文件

| 文件 | 创建者 | 用途 |
|------|--------|------|
| `.completed` | orchestrator | 完成标记 |
| `.stage_progress.json` | orchestrator | 🔴 阶段进度追踪（断点续接） |
| `.notified_stages.json` | cron | 已通知的阶段列表 |
| `.cron_run_count` | cron | 运行次数计数 |
| `.cron_job_id` | 主 Agent | cron job ID（供兜底删除用） |

### 🔴 状态持久化与断点续接

Orchestrator 每完成一个 phase，必须更新 `.stage_progress.json`：
```json
{
  "session_id": "xxx",
  "started_at": "ISO时间",
  "current_phase": 5,
  "completed_phases": [1, 2, 3, 4, 5],
  "failed_phases": [],
  "status": "running"
}
```

**主 Agent 续接流程**：
1. 收到 orchestrator announce 但 `.completed` 不存在
2. 读取 `.stage_progress.json` 查看已完成到哪个 phase
3. spawn continuation task，prompt 中说明从 phase N+1 继续
4. continuation task 读取 `.stage_progress.json` 跳过已完成阶段

---

## 🛡️ 三层退出机制

### 第一层：正常退出

orchestrator 写 `.completed` → cron 检测到 → 发最终报告 → `cron remove` 自杀

### 第二层：超时退出

cron 运行超过 20 次（60 分钟）→ 发超时告警 → `cron remove` 自杀

### 第三层：主 Agent 兜底

主 Agent 收到 orchestrator announce 后：
```python
# 读取 cron job ID
with open(f"{base_path}/.cron_job_id") as f:
    cron_job_id = f.read().strip()

# 尝试删除（如果 cron 已自杀，会返回 not found，忽略即可）
try:
    cron(action="remove", jobId=cron_job_id)
except:
    pass  # cron 已经自杀了

# 清理状态文件
import os
for f in [".cron_job_id", ".cron_run_count", ".notified_stages.json", ".run_start_at"]:
    path = f"{base_path}/{f}"
    if os.path.exists(path):
        os.remove(path)
```

### 退出流程总结

```
正常完成: orchestrator → .completed → cron 发报告 → cron 自删 → 主 Agent announce → 兜底清理
超时:     cron 计数 > 20 → cron 发超时告警 → cron 自删
兜底:     主 Agent announce → 主 Agent 主动删 cron → 清理状态文件
```

---

## 📊 主 Agent 收到 orchestrator announce 后

1. 解析完成状态
2. 执行兜底清理（删除 cron + 清理状态文件）
3. 执行 `python3 domains/solution_pro/completion_handler.py <session_id>` 验证
4. 更新 tasks 数据库为 `completed`
5. 向用户报告最终结果

---

## 🏗️ 架构总览

```
主 Agent
  ├── exec: run_solution_pro() → 生成计划
  ├── 初始化状态文件
  ├── sessions_spawn(orchestrator) → 启动管线
  ├── cron_add(watcher, every=3min) → 启动巡检
  ├── 记录 cron_job_id
  └── sessions_yield() → 等待

orchestrator (sub-agent, depth=1)
  └── 按 execution_plan.json 执行固定 10 阶段
  └── Stage 2 后运行 control_contract.py 刷新控制面
  └── 按 expected_output_path 检查 stages/*.json / data/*.json
  └── 最后写 .completed
  └── announce 回主 Agent

cron watcher (isolated, 每 3 分钟)
  └── 扫描 stages/ → 有新文件 → message 通知用户
  └── 检测 .completed → 最终报告 → cron remove 自杀

主 Agent 收到 announce
  └── 兜底清理 cron + 状态文件
  └── 更新 tasks DB
  └── 向用户报告
```

---

## ⛔ 禁止

```python
# ❌ orchestrator 使用 sessions_send（sub-agent 没有此工具）
# ❌ 主 Agent exec 阻塞轮询
# ❌ cron job 忘记自杀（必须有三层退出保障）
# ❌ 先发 cron remove 再发 message（顺序不能反）
```

---

## 🎯 记忆锚点

> "orchestrator 写文件，cron 读文件通知，主 Agent 兜底清理"
> "三层退出：正常自杀、超时自杀、主 Agent 兜底"
> "智能通知：有新阶段才发，最多 11 条"
> "状态靠文件，不靠内存"
> "expected_output_path 是完成判定契约"
> "frozen_spec.json 是 REQ-ID 权威需求源"

---



---

## 📖 参考文档

- **API 详情**: 见 [README.md](README.md)
- **Schema 契约**: 见 [docs/contracts/solution_pro_schema.md](../../docs/contracts/solution_pro_schema.md)
- **文件索引**: 见 [_overview.md](_overview.md)

*V4.4 | 2026-06-03 | 固定 10 阶段契约 + Schema 分层验证 + REQ-ID 需求追踪 + 状态持久化断点续接 + Cron delivery 模板化*
