# Cron 可靠性设计

> **日期**: 2026-06-01
> **评审对象**: DeepFlow Solution Pro 10 阶段管线进度通知的 isolated cron job
> **目标**: cron job 绝不变成幽灵进程，每条消息都有意义，所有失败路径都有容错

---

## 1. 三层退出机制

### 第一层：正常退出（.completed 信号）

**触发条件**: cron job 检测到 `{base_path}/.completed` 标记文件存在。

**执行流程**:
```
1. 读取 .completed JSON 文件，获取 status/final_output
2. 根据 status 判断成功/失败，格式化最终汇报
3. 用 message 工具发送最终汇报到用户
4. 用 exec 执行 `openclaw cron rm {cron_job_id}` 删除自己
5. 回复最终汇报文本（作为本次 cron 运行的结果）
```

**关键设计**:
- `.completed` 文件由 orchestrator 在所有阶段完成后写入
- `.completed` 文件也可能包含 `"status": "failed"`（orchestrator 异常退出时）
- cron job 必须在发送最终汇报**之后**才删除自己（防止汇报失败但 cron 已删除）

**实现代码**（cron prompt 中的伪指令）:
```
如果 {base_path}/.completed 存在：
  1. 读取内容：status = "completed" | "failed" | "cancelled"
  2. 根据 status 格式化最终汇报消息
  3. 用 message 工具发送最终汇报
  4. 用 exec 执行: openclaw cron rm {cron_job_id}
  5. 返回: "✅ 已发送最终汇报，cron job {cron_job_id} 已删除"
  6. 本次运行结束
```

### 第二层：超时退出（运行次数保护）

**核心问题**: isolated cron job 每次运行是全新 session，无法记住之前运行了多少次。

**解决方案**: 用 `{base_path}/.cron_run_count` 文件记录运行次数。

**文件内容**:
```json
{
  "count": 7,
  "first_run_at": "2026-06-01T00:30:00Z",
  "last_run_at": "2026-06-01T01:06:00Z",
  "max_runs": 20
}
```

**退出逻辑**:
```
每次运行时:
  1. 读取 .cron_run_count（不存在则创建，count=0）
  2. count += 1
  3. 写回 .cron_run_count
  4. 如果 count > max_runs（默认 20，即 60 分钟 @ 3 分钟间隔）:
     a. 发送超时告警消息给用户
     b. 用 exec 执行: openclaw cron rm {cron_job_id}
     c. 返回: "⚠️ 超时退出，已运行 {count} 次"
     d. 本次运行结束
```

**参数设计**:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_runs` | 20 | 20 × 3min = 60 分钟 |
| `interval_min` | 3 | 检查间隔（分钟） |
| `timeout_total_min` | 60 | 总超时上限 |

**为什么选 20 次（60 分钟）**:
- DeepFlow Solution Pro 10 阶段管线通常 30-60 分钟完成
- 60 分钟足够覆盖绝大多数正常场景
- 超过 60 分钟说明 orchestrator 可能卡死/崩溃了
- 告警消息可以提醒用户"任务可能已失败"

### 第三层：主 Agent 兜底（主动清理）

**核心问题**: 主 Agent yield 后如何知道 cron job 的 ID？

**解决方案**: 双通道记录 cron job ID。

**通道 1: 文件记录**
```
创建 cron 时，主 Agent 写入:
{base_path}/.cron_job_id = "a515ef86-ed56-4e9d-a0e3-xxx"
```

**通道 2: 传给 orchestrator**
```
在 orchestrator 的 prompt 中注入:
CRON_JOB_ID=a515ef86-ed56-4e9d-a0e3-xxx
```

**主 Agent 兜底触发条件**:
1. 用户主动取消任务
2. 主 Agent 从其他渠道得知 orchestrator 已终止
3. 兜底定时器（可选，如 90 分钟后自动检查）

**主 Agent 清理流程**:
```
1. 读取 {base_path}/.cron_job_id 获取 cron ID
2. 执行: openclaw cron rm {cron_id}
3. 清理状态文件: rm -f .cron_run_count .cron_job_id
4. 通知用户: "⚠️ 已手动清理 cron job，DeepFlow 管线已终止"
```

**三层退出的关系**:
```
正常情况 ──→ .completed ──→ 发送最终汇报 ──→ 自删
             ↑
             │ orchestrator 写
             
超时情况 ──→ .cron_run_count >= max_runs ──→ 发超时告警 ──→ 自删
             ↑
             │ cron 自己计数
             
兜底情况 ──→ 主 Agent 主动 rm ──→ 发清理通知
             ↑
             │ 用户取消 / 兜底定时器
```

---

## 2. 失败场景容错

| 场景 | 影响 | 容错策略 | 恢复机制 |
|------|------|---------|---------|
| **orchestrator 崩溃** | `.completed` 永远不会出现 | cron 超时退出（60min）+ 发超时告警 | 超时消息提醒用户任务可能失败，用户可决定是否重试 |
| **cron job 自身失败** | 无法通知用户 | OpenClaw 自动 retry（`consecutiveErrors` 计数）| cron 状态变为 error，主 Agent 可手动 `cron rm` + 重建 |
| **Gateway 重启** | cron job 和 orchestrator 可能都丢失 | cron 持久化在 jobs.json，重启后自动恢复；orchestrator 需要重新 spawn | Gateway 重启后 cron 自动恢复执行，orchestrator 丢失需主 Agent 处理 |
| **网络断开** | message 发送失败 | cron job 记录到 `{base_path}/.send_failures.json`，下次重试 | 网络恢复后，cron 检测到 `.send_failures.json` 并重发 |
| **用户中途取消** | orchestrator 被杀，cron 残留 | 主 Agent 通过 `.cron_job_id` 文件找到并删除 cron | 用户取消时触发清理流程 |
| **stages/ 目录被误删** | cron 扫描不到任何阶段文件 | cron 检测到 stages/ 目录不存在或为空，记录异常 | 连续 N 次扫描为空 → 发告警 + 超时退出 |
| **.completed 文件写入不完整** | cron 读取到无效 JSON | cron 捕获 JSON 解析错误，等待下次重试 | 连续 N 次解析失败 → 发告警（可能是 orchestrator 异常） |
| **cron job ID 文件丢失** | 主 Agent 无法通过 ID 删除 | 主 Agent 可通过 `openclaw cron list` 按名称搜索 | 名称规则: `deepflow_progress_{session_id[:8]}` |

### 失败计数器设计

```json
// {base_path}/.send_failures.json
{
  "failures": [
    {
      "attempt": 1,
      "timestamp": "2026-06-01T00:45:00Z",
      "error": "Network unreachable",
      "stage_file": "planning.json"
    }
  ],
  "max_retries": 5,
  "last_success_at": "2026-06-01T00:33:00Z"
}
```

### 连续失败退出

```
如果 .send_failures.json 中连续失败次数 >= 5:
  → 发送失败告警（含历史失败记录）
  → 删除 cron job
  → 通知用户：cron 因连续发送失败已退出，管线可能仍在运行
```

---

## 3. 消息策略

### 3.1 频率设计：智能通知，非固定频率

**问题**: 3 分钟间隔 × 最多 20 次 = 最多 20 条消息？太多。

**解决方案**: 只在有**新阶段完成**时发送通知，而非每次运行都发。

```
每次运行:
  扫描 stages/ 目录 → 得到当前阶段列表
  对比 .notified_stages.json → 得到已通知阶段列表
  
  如果有新阶段:
    → 发送进度消息（含所有阶段状态）
    → 更新 .notified_stages.json
  
  如果没有新阶段:
    → NO_REPLY（不发送任何消息）
    → 继续等待下次运行
```

**实际消息数**: 10 个阶段 = 最多 10 条进度消息 + 1 条完成消息 = 11 条（上限）

### 3.2 并行阶段合并

**问题**: 3 个 reviewer 并行完成 → 算 3 条还是 1 条消息？

**方案**: 同一轮次内并行阶段合并为 1 条消息。

```
当检测到多个新阶段时（如 reviewer_technical.json + reviewer_security.json）:
  → 合并为 1 条消息，标题为 "并行阶段完成（3/3）"
  → 消息体中列出各 reviewer 的状态
```

### 3.3 消息格式模板

**启动消息**（主 Agent 发送，非 cron 发送）:
```
✅ 已启动 DeepFlow Solution Pro 管线
📊 共 10 个阶段，预计 30-60 分钟
💬 期间你可以继续问我其他问题，完成后我会通知你
```

**进度消息**（cron 发送，仅当有新阶段时）:
```
📊 方案设计进度 [session_id]
━━━━━━━━━━━━━━━━━━━━
✅ Data Collection (1/10)
✅ Planning (2/10)
⏳ Reviewers (3-5/10) - 运行中...
⬜ Research
⬜ Consolidator
⬜ Audit
⬜ Fix
⬜ Fixer Expert
⬜ Harness Final
⬜ Summarizer

已耗时: 12:30
```

**完成消息**（cron 发送，检测到 .completed 时）:
```
✅ 方案设计完成！用时 45 分钟

快速摘要：
1. 架构：微服务 + Kubernetes
2. 数据库：PostgreSQL + Redis
3. 安全：OAuth 2.0 + JWT

完整方案已保存至 blackboard/xxx/final_solution.md
需要我解释某个部分，还是直接开始实施？
```

**失败消息**（cron 发送，检测到 .completed.status="failed" 时）:
```
⚠️ 方案设计在第 4 阶段失败

原因：外部 API 触发了限流（429 Too Many Requests）
影响：第 1-3 阶段结果已保存，第 4-10 阶段未执行

选项：
1. 5 分钟后重试（自动退避）
2. 跳过第 4 阶段，继续后续阶段
3. 手动提供第 4 阶段所需信息

你想怎么处理？
```

**超时消息**（cron 发送，超过 max_runs 时）:
```
⚠️ DeepFlow 管线运行超时

已运行 60 分钟（20 次巡检），仍未收到完成信号。
可能的原因：
- orchestrator 崩溃或卡死
- 某个阶段耗时过长

管线状态文件仍在 blackboard/{session_id}/ 中，你可检查已有阶段结果。
建议操作：
1. 查看 stages/ 目录了解已完成的阶段
2. 决定是否重新启动管线
```

---

## 4. 状态文件设计

### 4.1 文件目录结构

```
{base_path}/
├── .completed              # orchestrator 写入的完成标记（JSON）
├── .notified_stages.json   # cron 维护的已通知阶段列表
├── .cron_run_count         # cron 运行次数计数（JSON）
├── .cron_job_id            # cron job 的 ID（纯文本字符串）
├── .send_failures.json     # 消息发送失败记录（可选）
└── stages/
    ├── planning.json
    ├── reviewer_technical.json
    ├── reviewer_security.json
    ├── reviewer_usability.json
    ├── research.json
    ├── consolidator.json
    ├── audit.json
    ├── fix.json
    ├── fixer_expert.json
    ├── harness_final.json
    └── summarizer.json
```

### 4.2 各文件格式

**.completed**
```json
{
  "session_id": "xxx",
  "status": "completed",
  "completed_at": "2026-06-01T01:15:00Z",
  "final_output": "final_solution.md",
  "summary": "1. 架构... 2. 数据库... 3. 安全...",
  "error": null
}
```

**失败状态的 .completed**
```json
{
  "session_id": "xxx",
  "status": "failed",
  "completed_at": "2026-06-01T00:50:00Z",
  "final_output": null,
  "summary": null,
  "error": "Stage 4 (Research) failed: API rate limit exceeded",
  "completed_stages": ["data_collection", "planning", "reviewer_technical"]
}
```

**.notified_stages.json**
```json
{
  "notified": [
    {
      "stage": "data_collection",
      "notified_at": "2026-06-01T00:33:00Z",
      "message_index": 1
    },
    {
      "stage": "planning",
      "notified_at": "2026-06-01T00:39:00Z",
      "message_index": 2
    }
  ],
  "last_notify_at": "2026-06-01T00:39:00Z",
  "total_messages_sent": 2
}
```

**.cron_run_count**
```json
{
  "count": 7,
  "first_run_at": "2026-06-01T00:30:00Z",
  "last_run_at": "2026-06-01T01:06:00Z",
  "max_runs": 20
}
```

**.cron_job_id**
```
a515ef86-ed56-4e9d-a0e3-00392acad566
```
（纯文本，单行 UUID 字符串）

**.send_failures.json**（可选，仅在发送失败时创建）
```json
{
  "failures": [
    {
      "attempt": 1,
      "timestamp": "2026-06-01T00:45:00Z",
      "error": "Network unreachable",
      "stage_file": "planning.json"
    }
  ],
  "max_retries": 5,
  "last_success_at": "2026-06-01T00:33:00Z"
}
```

### 4.3 生命周期管理

| 文件 | 创建者 | 更新者 | 删除时机 |
|------|--------|--------|---------|
| `.completed` | orchestrator | — | 任务完成后保留（审计用） |
| `.notified_stages.json` | cron（首次运行时创建） | cron | 任务完成后保留 |
| `.cron_run_count` | cron（首次运行时创建） | cron | 任务完成后保留 |
| `.cron_job_id` | 主 Agent | — | 主 Agent 清理时删除 |
| `.send_failures.json` | cron（发送失败时创建） | cron | 发送成功后可删除 |

---

## 5. Cron Watcher Prompt

### 完整 Prompt

```
你是 DeepFlow 进度巡检员，运行在 isolated cron job 中。

## 输入变量
- base_path: "{base_path}"
- session_id: "{session_id}"
- cron_job_id: "{cron_job_id}"
- max_runs: {max_runs}（默认 20）
- interval_min: {interval_min}（默认 3）

## 你的职责
定期巡检 {base_path}/stages/ 目录，在有新阶段完成时通知用户。
检测完成或超时时发送最终报告并删除自己。

## 执行步骤

### Step 1: 读取运行计数
```
1. 读取 {base_path}/.cron_run_count
2. 如果文件不存在：
   count = 0
   first_run_at = 当前 ISO 时间
3. count = count + 1
4. 写回 {base_path}/.cron_run_count:
   {"count": count, "first_run_at": "...", "last_run_at": "当前时间", "max_runs": {max_runs}}
5. 如果 count > max_runs:
   → 进入 Step 6（超时退出）
   → 跳过 Step 2-5
```

### Step 2: 检查完成标记
```
1. 检查 {base_path}/.completed 是否存在
2. 如果存在:
   a. 读取 JSON 内容
   b. 根据 status 字段判断成功/失败
   c. 进入 Step 4（完成处理）
   d. 跳过 Step 3
```

### Step 3: 检查新阶段
```
1. 列出 {base_path}/stages/ 目录下所有 .json 文件
2. 读取 {base_path}/.notified_stages.json（不存在则创建，notified=[]）
3. 对比：找出 .json 文件名 - 已通知文件名 = 新阶段列表
4. 如果新阶段列表为空:
   → 回复 NO_REPLY（不发送任何消息）
   → 本次运行结束
5. 如果有新阶段:
   a. 计算当前总进度（已完成的阶段数 / 总阶段数）
   b. 判断是否有并行阶段（同一批发现的新阶段）
   c. 如果并行阶段 > 1:
      合并为 1 条消息，标题为"并行阶段完成（N/M）"
   d. 格式化进度消息（见下方消息格式）
   e. 用 message 工具发送进度消息
   f. 更新 .notified_stages.json，添加新通知记录
   g. 如果发送失败:
      记录到 .send_failures.json
      检查连续失败次数，如果 >= 5 → 进入 Step 5
```

### Step 4: 完成处理
```
1. 读取 .completed 内容
2. 如果 status == "completed":
   → 发送完成消息（见消息格式）
3. 如果 status == "failed":
   → 发送失败消息（见消息格式）
4. 用 exec 执行: openclaw cron rm {cron_job_id}
5. 返回: "✅ 已发送最终汇报，cron job {cron_job_id} 已删除"
6. 本次运行结束
```

### Step 5: 连续失败处理
```
1. 读取 .send_failures.json
2. 如果连续失败次数 >= 5:
   a. 发送告警消息:
      "⚠️ 进度通知因连续发送失败已停止（连续 {N} 次失败）
       管线可能仍在运行，但无法推送进度更新。
       建议手动检查 stages/ 目录了解进度。"
   b. 用 exec 执行: openclaw cron rm {cron_job_id}
   c. 返回: "⚠️ cron 因连续发送失败已退出"
   d. 本次运行结束
```

### Step 6: 超时退出
```
1. 发送超时告警消息（见消息格式）
2. 用 exec 执行: openclaw cron rm {cron_job_id}
3. 返回: "⚠️ 超时退出，已运行 {count} 次（{count * interval_min} 分钟）"
4. 本次运行结束
```

## 消息格式

### 进度消息（有新阶段时）
```
📊 DeepFlow 方案设计进度 [{session_id}]
━━━━━━━━━━━━━━━━━━━━
✅ Data Collection (1/10) - 完成于 HH:MM
✅ Planning (2/10) - 完成于 HH:MM
⏳ Reviewers (3-5/10) - 运行中...
⬜ Research (6/10)
⬜ Consolidator (7/10)
⬜ Audit (8/10)
⬜ Fix (9/10)
⬜ Summarizer (10/10)

已耗时: {elapsed_time}
```

### 完成消息
```
✅ 方案设计完成！用时 {elapsed_time}

快速摘要：
{completed.summary 前 200 字}

完整方案已保存至 blackboard/{session_id}/final_solution.md
需要我解释某个部分，还是直接开始实施？
```

### 失败消息
```
⚠️ 方案设计失败

阶段: {error 中的阶段信息}
原因: {error 详情}
已完成: {completed_stages 列表}

选项：
1. 5 分钟后重试
2. 跳过失败阶段继续
3. 手动提供缺失信息

你想怎么处理？
```

### 超时消息
```
⚠️ DeepFlow 管线运行超时

已运行 {elapsed_time}（{count} 次巡检），仍未收到完成信号。

可能原因：
- orchestrator 崩溃或卡死
- 某个阶段耗时过长

状态文件仍在 blackboard/{session_id}/ 中，建议：
1. 查看 stages/ 目录了解已完成的阶段
2. 决定是否重新启动管线
```

## 错误处理

1. **JSON 解析错误**（.completed 或 .notified_stages.json 损坏）:
   → 记录错误日志
   → 等待下次重试
   → 不发送消息

2. **stages/ 目录不存在**:
   → 回复 NO_REPLY
   → 等待下次重试

3. **message 工具调用失败**:
   → 记录到 .send_failures.json
   → 继续执行后续步骤

4. **openclaw cron rm 失败**:
   → 返回错误信息
   → 不阻塞本次运行结束

## 重要约束

- 不要在 NO_REPLY 之外发送任何消息，除非有新阶段或完成/超时
- 每次运行必须更新 .cron_run_count
- 必须在发送最终汇报后才删除 cron job
- 并行阶段的消息必须合并为 1 条
- 所有时间使用 ISO 8601 格式
```

---

## 6. 主 Agent 集成

### 6.1 创建 Cron Job

```bash
# Step 1: 创建 cron job
CRON_OUTPUT=$(openclaw cron add \
  --name "deepflow_progress_$(echo ${SESSION_ID} | cut -c1-8)" \
  --session isolated \
  --every 3m \
  --timeout-seconds 120 \
  --message "你是 DeepFlow 进度巡检员。
    base_path: {base_path}
    session_id: {session_id}
    cron_job_id: 稍后写入
    max_runs: 20
    interval_min: 3
    
    [完整 prompt 见第 5 节]" \
  --json)

# Step 2: 提取 cron job ID
CRON_ID=$(echo "$CRON_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Step 3: 写入 cron job ID 到文件
echo "$CRON_ID" > "{base_path}/.cron_job_id"

# Step 4: 初始化运行计数
echo '{"count":0,"first_run_at":"","last_run_at":"","max_runs":20}' \
  > "{base_path}/.cron_run_count"

# Step 5: 初始化已通知列表
echo '{"notified":[],"last_notify_at":"","total_messages_sent":0}' \
  > "{base_path}/.notified_stages.json"
```

### 6.2 主 Agent 兜底删除

```bash
# 场景 1: 用户取消任务
cron_id=$(cat "{base_path}/.cron_job_id")
openclaw cron rm "$cron_id"
rm -f "{base_path}/.cron_job_id" "{base_path}/.cron_run_count"
message "⚠️ 已清理 cron job $cron_id"

# 场景 2: 兜底检查（90 分钟后）
cron_id=$(cat "{base_path}/.cron_job_id")
openclaw cron get "$cron_id"
# 如果返回 404 → 已不存在（正常自删）
# 如果返回正常 → 仍在运行 → 手动 rm
```

### 6.3 名称约定

所有 DeepFlow 进度 cron job 使用统一命名前缀：

```
deepflow_progress_{session_id 前 8 位}
```

示例: `deepflow_progress_a515ef86`

这使得主 Agent 可以批量搜索和清理：

```bash
openclaw cron list --json | python3 -c "
import sys, json
jobs = json.load(sys.stdin)['jobs']
for job in jobs:
    if job['name'].startswith('deepflow_progress_'):
        print(f\"{job['id']} {job['name']} {job['status']}\")"
```

### 6.4 集成检查清单

主 Agent 在创建 cron 前必须验证：

- [ ] base_path 存在且可写
- [ ] stages/ 目录已创建
- [ ] session_id 已定义
- [ ] cron job 名称不冲突（搜索现有同名 cron）
- [ ] 状态文件已初始化（.cron_run_count, .notified_stages.json）
- [ ] .cron_job_id 已写入

---

## 附录：决策记录

### 为什么用文件信号而非内存信号？

isolated cron job 每次是全新 session，无法依赖内存中的变量。
文件系统是唯一可靠的跨 session 状态持久化方式。

### 为什么不用 OpenClaw 的 --delete-after-run 标志？

`--delete-after-run` 只在 job **成功**时删除。
如果 cron job 因异常失败（如 JSON 解析错误），job 不会被删除。
我们需要 cron job **主动**删除自己（通过 exec），确保所有退出路径都清理。

### 为什么消息策略是"有新阶段才通知"而非"每 3 分钟都通知"？

10 阶段管线，如果每 3 分钟通知一次：
- 60 分钟 = 20 条消息
- 大部分消息内容相同（无新进度）
- 用户体验极差

改为"有新阶段才通知"：
- 10 阶段 = 最多 10 条进度消息 + 1 条完成消息 = 11 条
- 每条消息都有新信息
- 用户体验良好

### 并行阶段合并的规则

同一轮次内（单次 cron 运行）发现的多个新阶段 → 合并为 1 条消息。
这避免了 reviewer_technical、reviewer_security、reviewer_usability 三个并行阶段
产生 3 条独立消息的问题。

---

*文档版本: 1.0 | 作者: Cron Reliability Expert Sub-Agent | 日期: 2026-06-01*