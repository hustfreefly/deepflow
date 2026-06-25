# Ship Pro V4 - Agent 执行指南

> **版本**: V4.0 | **最后更新**: 2026-06-25  
> **架构**: Orchestrator 模式 + run_pipeline.py CLI + Cron Watcher  
> **核心理念**: 主 Agent 只负责启动，Orchestrator 编排 5 Worker，Watcher 通知进度  
> **CLI 引擎**: `run_pipeline.py`（prepare/task/gate/update-status/validate）

---

## 🏗️ 架构总览

```
主 Agent
  ├── exec: start_ship_pro.py → 准备管线 + 生成 spawn_params
  ├── sessions_spawn(orchestrator) → 启动编排器
  ├── cron_add(watcher) → 启动进度巡检
  └── sessions_yield() → 等待完成通知

orchestrator (sub-agent, depth=1)
  ├── run_pipeline.py prepare → 初始化 blackboard
  └── 对 5 个 agent 循环:
      ├── run_pipeline.py task → 构建 worker prompt
      ├── sessions_spawn(worker) → 启动 worker
      ├── sessions_yield() → 等待 worker 完成
      ├── run_pipeline.py gate → 质量门禁验证
      ├── run_pipeline.py update-status → 更新状态
      └── 继续下一个 agent
  └── 写 .completed → 完成

cron watcher (isolated, 每 3 分钟)
  └── pipeline_watcher.py → 检测新阶段 → 通知用户
  └── 检测 .completed → 最终报告 → cron 自删
```

### 与 Solution Pro 的一致性

| 设计要素 | Solution Pro | Ship Pro |
|---------|-------------|----------|
| 主 Agent 职责 | 启动 + yield | 启动 + yield |
| 编排层 | Orchestrator sub-agent | Orchestrator sub-agent |
| Worker 调度 | sessions_spawn + yield | sessions_spawn + yield |
| CLI 工具 | `run_solution_pro()` | `run_pipeline.py` |
| 进度通知 | Cron Watcher | Cron Watcher |
| 退出机制 | 三层（正常/超时/兜底） | 三层（正常/超时/兜底） |

---

## 🚀 主 Agent 执行步骤

### Step 1: 启动管线

```bash
cd ~/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 scripts/start_ship_pro.py \
  --input "<input_path>" \
  --output "<output_dir>"
```

**输入**: Solution Pro 的 `final_result.json` 路径（相对于 .deepflow）  
**输出**: JSON 包含 `spawn_params` + `watcher_cron_payload`

### Step 2: Spawn Orchestrator

```python
# 从 Step 1 的 JSON 输出中获取 spawn_params
sessions_spawn(**result["spawn_params"])
```

**关键**: `spawn_params` 已包含完整的 orchestrator prompt（路径已烘焙），直接传给 `sessions_spawn`。

### Step 3: 创建 Watcher Cron

```python
# 直接使用 start_ship_pro.py 输出的 watcher_cron_payload
cron_payload = result["watcher_cron_payload"]
cron_result = cron(action="add", job=cron_payload)

# 回填 cron_job_id（用于兜底清理）
cron_job_id = cron_result["id"]
```

### Step 4: 发送启动通知

```
✅ 已启动 DeepFlow Ship Pro 管线
📦 输入: {input_path}
📊 共 5 个阶段: Architect → Decomposer → Specifier → Reviewer → Packager
💬 期间你可以继续问我其他问题，完成后我会通知你
```

### Step 5: Yield 等待

```python
sessions_yield()
```

orchestrator 完成后会 announce 回来。

---

## 🔄 Orchestrator 行为（sub-agent depth=1）

Orchestrator 是 Ship Pro 的运行时调度器，由 `start_ship_pro.py` 生成的 prompt 驱动。

### 执行算法

```
for agent in [architect, decomposer, specifier, reviewer, packager]:
    1. exec: run_pipeline.py task <agent> <output_dir>  → 获取 task prompt
    2. sessions_spawn(worker, task=task_prompt)          → 启动 worker
    3. sessions_yield()                                  → 等待 worker 完成
    4. exec: run_pipeline.py gate <agent> <output_dir>   → 质量门禁
    5. 如果 gate FAIL → 重试（最多 max_retries 次，用 feedback 命令获取改进提示）
    6. exec: run_pipeline.py update-status <output_dir> <agent> PASS|CONDITIONAL|FAIL
    7. 继续下一个 agent

写 .completed 文件 → 完成
```

### CLI 命令参考

| 命令 | 用途 | 示例 |
|------|------|------|
| `prepare` | 初始化管线 | `run_pipeline.py prepare <input> <output_dir>` |
| `task` | 构建 worker prompt | `run_pipeline.py task architect <output_dir>` |
| `gate` | 质量门禁检查 | `run_pipeline.py gate architect <output_dir>` |
| `feedback` | 获取重试反馈 | `run_pipeline.py feedback architect <output_dir>` |
| `update-status` | 更新状态 | `run_pipeline.py update-status <output_dir> architect PASS` |
| `validate` | 最终验证 | `run_pipeline.py validate <output_dir>` |
| `status` | 查看状态 | `run_pipeline.py status <output_dir>` |

### Gate 重试机制

| Agent | max_retries | gate_fn |
|-------|-------------|---------|
| architect | 2 | gate_architect |
| decomposer | 2 | gate_decomposer |
| specifier | 2 | gate_specifier |
| reviewer | 5 | gate_reviewer |
| packager | 2 | gate_packager |

Gate FAIL 时：
1. `run_pipeline.py feedback <agent> <output_dir>` → 获取改进建议
2. 将 feedback 注入到新的 task prompt 中
3. 重新 spawn worker
4. 重新 gate

---

## 📡 Cron Watcher（进度巡检）

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

### 契约约束

- ✅ wrapper prompt 必须来自 `render_wrapper_prompt()`（start_ship_pro.py 已生成）
- ✅ delivery 通过 `DeliveryConfig` 验证
- ❌ 禁止主 Agent 手写 watcher prompt
- ❌ 禁止使用旧的 `cron_watcher.md` prompt

### 通知策略

- 有新阶段完成时才发消息（最多 5 条进度 + 1 条完成）
- 空检测 → NO_REPLY
- 完成 → 发最终报告 → `cron remove` 自杀
- 超时（30 分钟）→ 超时告警 → `cron remove` 自杀

---

## 🛡️ 三层退出机制

### 第一层：正常退出
orchestrator 写 `.completed` → cron 检测到 → 发最终报告 → `cron remove` 自杀

### 第二层：超时退出
cron 运行超过 15 次（30 分钟）→ 发超时告警 → `cron remove` 自杀

### 第三层：主 Agent 兜底
主 Agent 收到 orchestrator announce 后：
1. 检查 `.completed` 是否存在
2. 删除 cron job（如未自杀）
3. 清理状态文件
4. 向用户报告结果

---

## 📊 状态文件

| 文件 | 创建者 | 用途 |
|------|--------|------|
| `pipeline_state.json` | run_pipeline.py | 管线状态（CLI 管理） |
| `pipeline_config.json` | run_pipeline.py prepare | 管线配置 |
| `.completed` | orchestrator | 完成标记 |
| `.stage_progress.json` | orchestrator | 断点续接进度 |
| `.notified_stages.json` | cron | 已通知的阶段列表 |
| `.cron_run_count` | cron | 运行次数计数 |
| `.cron_job_id` | 主 Agent | cron job ID |

---

## ⛔ 禁止

- ❌ 主 Agent 直接 spawn Worker（必须通过 Orchestrator）
- ❌ 主 Agent 直接调用 `run_pipeline.py task/gate`（Orchestrator 的职责）
- ❌ Orchestrator 使用 `sessions_send`（sub-agent 没有此工具）
- ❌ 手写 watcher prompt（必须用 `start_ship_pro.py` 生成的 `watcher_cron_payload`）
- ❌ 直接写 `pipeline_state.json`（必须用 `update-status` CLI）
- ❌ 修改 Pydantic 模型不同步 Schema（必须跑 `generator --check`）

---

## 🎯 记忆锚点

> "主 Agent 启动 + yield，Orchestrator 编排 Worker，Watcher 通知进度"
> "CLI 是工具层，Orchestrator 是调度层，主 Agent 是入口层"
> "三层退出：正常自杀、超时自杀、主 Agent 兜底"
> "run_pipeline.py task → sessions_spawn → run_pipeline.py gate"

---

## 📖 历史版本

| 版本 | 日期 | 变更 |
|------|------|------|
| **V4.0** | **2026-06-25** | **恢复 Orchestrator 模式（与 Solution Pro 一致）** |
| V3.2 | 2026-06-23 | Pydantic 契约笼子 + CLI 引擎（扁平 spawn，已废弃） |
| V3.1 | 2026-06-22 | STAGE_PATH_REGISTRY 统一路径 |
| V3.0 | 2026-06-18 | 5 Agent LLM-native 管线 |
| V2.0 | 2026-06-15 | LLM 引导 + 确定性编译（已废弃） |

### V3.2 → V4.0 变更说明

V3.2 的 CLI 加固（`run_pipeline.py` 命令）保留，但上层调度从"主 Agent 扁平 spawn"恢复为"Orchestrator 编排"。

**保留的好东西**（CLI 加固成果）：
- `run_pipeline.py` CLI 命令（prepare/task/gate/update-status/validate）
- Pydantic 契约笼子（contracts/）
- `pipeline_state.json` 状态管理
- `STAGE_PATH_REGISTRY` 路径注册表

**修复的问题**：
- ~~主 Agent 被阻塞 30 分钟~~ → Orchestrator 接管，主 Agent yield
- ~~丢失并行能力~~ → Orchestrator 支持 `parallel_groups`（future）
- ~~违背核心设计原则~~ → 恢复"主 Agent 只负责启动"
