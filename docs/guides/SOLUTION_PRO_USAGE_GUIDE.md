# Solution Pro 使用指南

> **版本**: V4.1  
> **最后更新**: 2026-06-01

---

## 快速开始

### 1. 启动 Solution Pro

主 Agent 按以下步骤执行：

```python
# Step 1: 清理旧状态 + 初始化
import os, json

base_path = "/path/to/blackboard/{session_id}"
for old_file in [".completed", ".cron_job_id", ".cron_run_count", ".notified_stages.json"]:
    path = f"{base_path}/{old_file}"
    if os.path.exists(path):
        os.remove(path)

# Step 2: 生成执行计划
from domains.solution import run_solution_pro
plan = run_solution_pro(
    topic="设计一个智能客服系统",
    solution_type="architecture",
    constraints=["预算100万", "3个月交付"],
    stakeholders=["产品团队", "技术团队"]
)

# Step 3: Spawn Orchestrator
sessions_spawn(
    task=read("domains/solution_pro/prompts/pipeline_orchestrator_v4.md").format(**plan),
    mode="run",
    label=f"orchestrator_{plan['session_id'][:8]}"
)

# Step 4: 创建 Cron Watcher
cron_job_id = cron(action="add", job={
    "name": f"deepflow_progress_{plan['session_id'][:8]}",
    "schedule": {"kind": "every", "everyMs": 180000},
    "payload": {
        "kind": "agentTurn",
        "message": read("domains/solution_pro/prompts/cron_watcher.md").format(
            base_path=plan["base_path"],
            session_id=plan["session_id"]
        )
    },
    "sessionTarget": "isolated"
})

# Step 5: 记录 cron_job_id
write(f"{base_path}/.cron_job_id", cron_job_id)

# Step 6: Yield 等待
sessions_yield()
```

### 2. 预期行为

**主 Agent 启动后**:
- Orchestrator 开始异步执行 10 阶段管线
- Cron Watcher 每 3 分钟巡检一次
- 主 Agent yield，可处理其他请求

**用户会收到**:
- 每 3 分钟一次的进度通知（仅当有新阶段完成时）
- 完成时的最终报告
- 超时时的告警（60 分钟未完成）

**主 Agent 收到 orchestrator announce 后**:
- 兜底清理 Cron Job
- 清理状态文件
- 更新 tasks 数据库
- 向用户报告最终结果

---

## 参数说明

### run_solution_pro 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `topic` | string | ✅ | 设计主题，如"设计一个智能客服系统" |
| `solution_type` | string | ❌ | 方案类型：`architecture`（默认）、`business`、`technical` |
| `constraints` | list[string] | ❌ | 约束条件，如 `["预算100万", "3个月交付"]` |
| `stakeholders` | list[string] | ❌ | 利益相关者，如 `["产品团队", "技术团队"]` |

### Cron Watcher 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `interval` | 3 分钟 | 巡检频率 |
| `max_runs` | 20 | 最大运行次数（超时保护） |
| `timeout_minutes` | 60 | 超时阈值 |

---

## 查看结果

### 最终方案

```bash
cat {base_path}/stages/final_solution.md
```

### 各阶段输出

```bash
ls -lh {base_path}/stages/
cat {base_path}/stages/planning.json
cat {base_path}/stages/audit.json
```

### 执行计划

```bash
cat {base_path}/execution_plan.json
```

---

## 故障排查

### 问题 1: Cron 没有发送进度通知

**可能原因**:
1. Cron Job 创建失败
2. Cron Job 提前退出（旧 `.completed` 残留）
3. 消息发送失败

**排查步骤**:
```bash
# 检查 Cron Job 是否存在
cron action="list"

# 检查 .cron_job_id 文件
cat {base_path}/.cron_job_id

# 检查 .cron_run_count
cat {base_path}/.cron_run_count

# 检查 .notified_stages.json
cat {base_path}/.notified_stages.json
```

### 问题 2: Orchestrator 崩溃

**现象**: 60 分钟后收到超时告警

**排查步骤**:
```bash
# 查看已完成的阶段
ls -lh {base_path}/stages/

# 查看最后一个完成的阶段
cat {base_path}/stages/$(ls -t {base_path}/stages/ | head -1)

# 查看 Orchestrator 日志（如果有）
openclaw logs --filter orchestrator
```

**恢复方法**:
1. 分析崩溃原因
2. 清理旧状态文件
3. 重新启动 Solution Pro

### 问题 3: 主 Agent 没有收到 announce

**可能原因**:
1. Orchestrator 没有正常完成
2. OpenClaw 内部问题

**排查步骤**:
```bash
# 检查 .completed 是否存在
ls -lh {base_path}/.completed

# 检查 tasks 数据库
sqlite3 {db_path} "SELECT * FROM tasks WHERE session_id='{session_id}'"
```

**恢复方法**:
1. 手动执行兜底清理
2. 更新 tasks 数据库
3. 向用户报告结果

---

## 高级用法

### 自定义 Worker Prompt

修改 `domains/solution_pro/prompts/` 下的 prompt 文件：

```bash
# 修改 Planning Worker
vim domains/solution_pro/prompts/planning.md

# 修改 Reviewer Workers
vim domains/solution_pro/prompts/reviewer_*.md
```

### 调整 Cron 巡检频率

修改 SKILL.md 中的 Cron 创建参数：

```python
cron_job_id = cron(action="add", job={
    "schedule": {"kind": "every", "everyMs": 60000},  # 改为 1 分钟
    ...
})
```

### 禁用 Cron 通知

如果不需要进度通知，可以跳过 Cron 创建步骤：

```python
# 只执行 Step 1-3, 6（跳过 Step 4-5）
# 用户只在任务完成时收到通知
```

---

## 最佳实践

### 1. 启动前清理

**必须**在启动新运行前清理旧状态文件，避免 Cron 误判。

### 2. 监控长时间任务

如果任务预计超过 30 分钟，建议：
- 增加 Cron 巡检频率（每 2 分钟）
- 增加 `max_runs`（如 30 次）
- 向用户说明预计时间

### 3. 处理失败任务

如果任务失败：
1. 查看已完成的阶段输出
2. 分析失败原因
3. 清理旧状态
4. 重新启动

### 4. 查看中间结果

即使任务未完成，也可以查看已完成的阶段：

```bash
# 查看所有已完成的阶段
ls -lh {base_path}/stages/

# 查看 Planning 结果
cat {base_path}/stages/planning.json | jq .

# 查看 Audit 发现的问题
cat {base_path}/stages/audit.json | jq .issues
```

---

## 相关文档

- `docs/SOLUTION_PRO_ARCHITECTURE.md` - 架构说明
- `docs/CRON_EARLY_EXIT_POSTMORTEM.md` - Cron 提前退出问题复盘
- `domains/solution_pro/SKILL.md` - 主 Agent 执行指南
- `domains/solution_pro/prompts/pipeline_orchestrator_v4.md` - Orchestrator Prompt
- `domains/solution_pro/prompts/cron_watcher.md` - Cron Watcher Prompt

---

**文档版本**: V4.1  
**作者**: 小满 🦞  
**审核**: 忠礼  
**最后更新**: 2026-06-01
