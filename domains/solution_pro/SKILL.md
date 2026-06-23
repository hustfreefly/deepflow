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

### Step 4: 创建 Cron 巡检 Agent（V2 契约笼子）

使用 `pipeline_watcher.py` 确定性脚本 + 薄 wrapper prompt，禁止 LLM 自行判断。

```python
from datetime import datetime
from contracts.shared.watcher_config import render_wrapper_prompt, DeliveryConfig

# 1. 生成运行启动时间
run_start_at = datetime.now().isoformat()

# 2. 渲染 wrapper prompt（~10行，禁止 LLM 自行判断）
wrapper_prompt = render_wrapper_prompt(
    config_path=f"{deepflow_root}/domains/solution_pro/config/watcher_config.json",
    base_path=base_path,
    run_start_at=run_start_at,
    cron_job_id="{cron_job_id}",  # 创建后回填
    deepflow_root=deepflow_root,
)

# 3. 构建 delivery 配置（通过契约验证，不硬编码 open_id）
delivery = DeliveryConfig(mode="announce")  # 不指定 channel/to → 使用当前会话 channel
delivery_dict = delivery.to_cron_dict()

# 4. 创建 cron job
cron_result = cron(
    action="add",
    job={
        "name": f"deepflow_watcher_{session_id[:8]}",
        "schedule": {"kind": "every", "everyMs": 180000},
        "sessionTarget": "isolated",
        "payload": {
            "kind": "agentTurn",
            "message": wrapper_prompt,
            "timeoutSeconds": 60,
            "lightContext": True
        },
        "delivery": delivery_dict,
        "enabled": True
    }
)

# 5. 回填 cron_job_id + 记录
cron_job_id = cron_result["id"]
# 回填 wrapper prompt 中的 {cron_job_id} 占位符
wrapper_prompt = wrapper_prompt.replace("{cron_job_id}", cron_job_id)
cron(action="update", jobId=cron_job_id, patch={"payload": {"message": wrapper_prompt}})

# 写入状态文件
Path(f"{base_path}/.cron_job_id").write_text(cron_job_id)
Path(f"{base_path}/.run_start_at").write_text(run_start_at)
```

**🔴 契约约束**（违反即 FAIL）：
- ✅ wrapper prompt 必须来自 `render_wrapper_prompt()`，禁止自行编写
- ✅ delivery 必须通过 `DeliveryConfig` 验证，禁止硬编码 open_id
- ✅ 不指定 channel/to → OpenClaw 自动路由到发起会话的 channel
- ❌ 禁止在 prompt 中让 LLM 调用 `message` tool
- ❌ 禁止使用旧的 `cron_watcher.md` prompt（已 deprecated）

### Step 6: yield 等待 orchestrator 完成

```python
sessions_yield()
```

orchestrator 完成后会自动 announce 回来。

### Step 7: 自动触发 Ship Pro（auto_chain）

当收到 Solution Pro 完成消息，且消息包含 `🔗 自动触发下游管线: ship_pro` 时：

#### 7a. 启动 Ship Pro 管线

```python
# 运行启动脚本
result = exec("python3 scripts/start_ship_pro.py --input blackboard/<session>/stages/final_result.json --output blackboard/<session>/ship_output --print-watcher-prompt")

# 解析 JSON 输出
spawn_params = result["spawn_params"]
```

#### 7b. Spawn Ship Pro Orchestrator

```python
sessions_spawn(**spawn_params)
```

#### 7c. 🔴 创建 Watcher Cron（必须！）

```python
from contracts.shared.watcher_config import render_wrapper_prompt, DeliveryConfig

# 渲染 wrapper prompt
wrapper_prompt = render_wrapper_prompt(
    config_path=f"{deepflow_root}/domains/ship_pro/config/watcher_config.json",
    base_path=result["output_path"],
    run_start_at=result["run_start_at"],
    cron_job_id="{cron_job_id}",  # 创建后回填
    deepflow_root=deepflow_root,
)

# 创建 cron job
cron_result = cron(action="add", job={
    "name": f"deepflow_ship_watcher_{session_id[:8]}",
    "schedule": {"kind": "every", "everyMs": 120000},
    "sessionTarget": "isolated",
    "payload": {"kind": "agentTurn", "message": wrapper_prompt, "timeoutSeconds": 60, "lightContext": True},
    "delivery": DeliveryConfig(mode="announce").to_cron_dict(),
    "enabled": True
})

# 回填 cron_job_id
cron_job_id = cron_result["id"]
wrapper_prompt = wrapper_prompt.replace("{cron_job_id}", cron_job_id)
cron(action="update", jobId=cron_job_id, patch={"payload": {"message": wrapper_prompt}})
```

#### 7d. Yield 等待完成

```python
sessions_yield()
```

> **🔴 铁律**:
> - 看到 "🔗 自动触发" 就必须执行，不要问用户是否继续
> - **必须创建 Watcher Cron**，否则用户无法收到进度通知
> - 不创建 Watcher = 违规，等同于静默失败

---

## 🔄 Cron 巡检 Agent 行为（V2 契约笼子）

### 架构

```
Cron (isolated, 每 3 分钟)
  ↓ exec
pipeline_watcher.py (确定性 Python, <1s)
  ↓ stdout JSON
薄 wrapper prompt (10行)
  ↓ delivery announce
用户收到通知
```

**关键**: 所有逻辑在 `pipeline_watcher.py` 中，LLM 只负责调 exec + 转发。禁止 LLM 自行判断。

### 契约约束

| 约束 | 验证 |
|------|------|
| watcher_config.json 格式 | `WatcherConfig` Pydantic 模型 |
| delivery 配置 | `DeliveryConfig` Pydantic 模型 |
| wrapper prompt 内容 | 必须来自 `render_wrapper_prompt()` |

### 核心逻辑（在 pipeline_watcher.py 中实现）

1. **更新运行计数** → 超过 20 次（60 分钟）→ timeout 输出
2. **检查 .completed + 时间戳校验** → 存在且时间戳晚于 run_start_at → completed 输出 + should_remove_cron=true
3. **扫描 stages/** → 有新文件 → progress 输出
4. **没有新文件** → noop 输出 → LLM 回复 NO_REPLY
5. **连续无输出** → circuit_break 输出

### 消息策略

- **智能通知**：只在有新阶段完成时发消息（最多 11 条，非 20 条）
- **并行合并**：同一轮次发现的多个并行阶段合并为 1 条消息
- **空消息不发**：action=noop → NO_REPLY

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
