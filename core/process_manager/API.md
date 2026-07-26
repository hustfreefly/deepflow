# ProcessManager API 手册

> DeepFlow 通用过程管理器 — 极端稳健性设计

## 概述

ProcessManager 负责 DeepFlow 所有模块的过程管理，提供：
- **阻塞式文件等待**（替代 spawn-yield 被动等待）
- **模块生命周期管理**（心跳、完成标记、stall 检测）
- **单源状态管理**（消除双写不一致）
- **独立 watchdog**（主动告警守护进程）
- **超时/stall webhook 告警**

**设计原则**：
- 代码做控制流（Python while 循环，100% 确定）
- LLM 只做语义判断
- 零内存状态（全部从文件系统推导）
- 契约笼方法（Pydantic models → JSON Schema → 代码实现）

---

## 核心 API

### 1. ProcessManager（最小原语）

阻塞式等待文件出现，返回原始状态。

```python
from core.process_manager import ProcessManager

pm = ProcessManager(
    session_dir: str | Path,        # blackboard session 目录
    webhook_url: str | None = None  # 超时告警 webhook（可选）
)
```

#### `wait_for(path, timeout, poll_interval, min_size, validate_json)`

阻塞式等待文件出现。

```python
result = pm.wait_for(
    path="stages/planning_convergence.json",  # 相对 session_dir 的路径
    timeout=1800,          # 超时秒数（默认 30 分钟）
    poll_interval=15,      # 轮询间隔（默认 15s，防 stuck abort）
    min_size=0,            # 最小文件大小（字节）
    validate_json=False,   # 是否验证 JSON 可解析
)

# result.found=True → 文件出现
# result.found=False → 超时（自动发送 webhook 告警）
```

**返回值 `WaitResult`**：
```python
{
    "found": True,                    # 文件是否找到
    "path": "stages/xxx.json",        # 文件路径
    "elapsed": 120.5,                 # 等待时间（秒）
    "timeout": 1800,                  # 超时时间（秒）
    "file_size": 80593,               # 文件大小（字节）
    "file_mtime": 1785081345.0,       # 文件修改时间
    "exists_but_empty": False,        # 文件存在但为空
    "exists_but_invalid_json": False, # 文件存在但 JSON 无效
}
```

#### `check(path, min_size, validate_json)`

立即检查文件（非阻塞）。

```python
result = pm.check("stages/planning_convergence.json")
```

#### `wait_for_any(paths, timeout, poll_interval)`

等待任一文件出现（用于并行 worker 场景）。

```python
result = pm.wait_for_any([
    "stages/worker_1_output.json",
    "stages/worker_2_output.json",
    "stages/worker_3_output.json",
], timeout=1800)
```

#### `wait_for_all(paths, timeout, poll_interval)`

等待所有文件出现，返回每个文件的状态。

```python
results = pm.wait_for_all([
    "stages/worker_1_output.json",
    "stages/worker_2_output.json",
], timeout=1800)

# results = {
#     "stages/worker_1_output.json": WaitResult(...),
#     "stages/worker_2_output.json": WaitResult(...),
# }
```

---

### 2. ModuleLifecycleManager（模块生命周期管理）

管理模块的 spawn、心跳、完成标记、stall 检测。

```python
from core.process_manager import ModuleLifecycleManager

lifecycle = ModuleLifecycleManager(
    session_dir: str | Path  # blackboard session 目录
)
```

#### `try_acquire_run(module, stall_threshold_sec)`

spawn 前去重，获取运行权。

```python
run = lifecycle.try_acquire_run(
    module="planning",           # 模块名
    stall_threshold_sec=1800,    # 心跳超时阈值（默认 30 分钟）
)

# run.run_id = "planning_1785081345_a1b2c3d4"
# run.attempt = 1
# run.already_running = False  # True 表示已有活跃运行，不应重复 spawn
```

#### `heartbeat(module, run_id)`

Module Agent 定期调用更新心跳。

```python
# Module Agent 每 60 秒调用一次
success = lifecycle.heartbeat("planning", run.run_id)
# success=True → 仍是活跃运行
# success=False → 已被替代（不应继续执行）
```

#### `mark_completed(module, run_id, output_files)`

Module Agent 完成时调用（可选，ProcessManager 会自动检测输出文件）。

```python
success = lifecycle.mark_completed(
    module="planning",
    run_id=run.run_id,
    output_files={
        "stages/planning_convergence.json": {
            "size": 80593,
            "mtime": 1785081345.0,
        }
    }
)
```

#### `wait_for_module(module, expected_files, timeout, ...)`

Orchestrator 调用，等待模块完成。

**增强版完成判定**：
1. 输出文件存在且有效（**必要条件**）
2. run record status == "completed" OR 完成标记存在（辅助信号）

```python
result = lifecycle.wait_for_module(
    module="planning",
    expected_files=["stages/planning_convergence.json"],
    timeout=3600,                  # 超时秒数
    poll_interval=15,              # 轮询间隔
    min_file_sizes={               # 最小文件大小
        "stages/planning_convergence.json": 10000
    },
    heartbeat_threshold=1800,      # 心跳超时阈值（秒）
    file_mtime_threshold=900,      # 文件 mtime 超时阈值（秒）
)

# result.found=True → 模块完成
# result.found=False, result.reason="stall" → 模块 stall（心跳超时）
# result.found=False, result.reason="timeout" → 模块超时
```

**返回值 `ModuleWaitResult`**：
```python
{
    "found": True,                  # 模块是否完成
    "run_id": "planning_1785081345_a1b2c3d4",
    "attempt": 1,                   # 尝试次数
    "elapsed": 120.5,               # 等待时间（秒）
    "reason": "",                   # 失败原因："" | "timeout" | "stall"
    "files": {                      # 文件详情
        "stages/planning_convergence.json": {
            "size": 80593,
            "mtime": 1785081345.0,
            "valid": True,
        }
    }
}
```

#### `atomic_write_file(target_path, content, encoding)`

通用原子写操作（Module Agent 写输出文件时必须调用）。

```python
lifecycle.atomic_write_file(
    target_path="stages/planning_convergence.json",
    content=json.dumps(data),
    encoding="utf-8",
)
# 内部使用 .tmp + rename 模式，防止写入中断导致文件损坏
```

---

### 3. SingleSourceStateManager（单源状态管理）

从 `.runs/*.run.json` 派生状态，消除双写不一致。

```python
from core.process_manager import SingleSourceStateManager

state_mgr = SingleSourceStateManager(
    session_dir: str | Path  # blackboard session 目录
)
```

#### `get_module_status(module)`

获取模块状态（从 .run.json 派生）。

```python
status = state_mgr.get_module_status("planning")
# {
#     "status": "running",        # running | completed | failed | stalled
#     "run_id": "planning_...",
#     "attempt": 1,
#     "started_at": 1785081345.0,
#     "completed_at": None,
#     "last_heartbeat": 1785081405.0,
# }
```

#### `get_all_modules_status()`

获取所有模块状态。

```python
all_status = state_mgr.get_all_modules_status()
# {
#     "planning": {...},
#     "research": {...},
#     "summary": {...},
# }
```

#### `is_module_completed(module)`

检查模块是否完成。

```python
if state_mgr.is_module_completed("planning"):
    print("Planning 完成")
```

#### `is_module_stalled(module, threshold)`

检查模块是否 stall。

```python
if state_mgr.is_module_stalled("planning", threshold=1800):
    print("Planning stall 了")
```

#### `get_pipeline_status()`

获取整个 pipeline 状态（从各模块状态派生）。

```python
pipeline = state_mgr.get_pipeline_status()
# {
#     "status": "running",           # running | completed | failed | stalled
#     "completed_modules": ["planning"],
#     "failed_modules": [],
#     "stalled_modules": [],
# }
```

---

### 4. Watchdog（独立 watchdog 进程）

定期扫描心跳过期，检测 stall 并发送告警。

```python
from core.process_manager import Watchdog

watchdog = Watchdog(
    session_dir: str | Path,          # blackboard session 目录
    webhook_url: str | None = None,   # webhook URL
    heartbeat_threshold: int = 1800,  # 心跳超时阈值（秒）
)
```

#### `scan_and_alert()`

扫描所有模块，检测 stall 并发送告警。

```python
alerts = watchdog.scan_and_alert()
# [
#     {
#         "alert_type": "stall",
#         "session_id": "2.5D封装_V40_20260726",
#         "module": "planning",
#         "run_id": "planning_1785081345_a1b2c3d4",
#         "message": "Module planning stalled: heartbeat age 2000s > 1800s",
#         "timestamp": 1785083345.0,
#         "details": {...},
#     }
# ]
```

#### `get_recent_alerts(minutes)`

获取最近的告警。

```python
recent = watchdog.get_recent_alerts(minutes=60)
```

#### `run_watchdog_once(session_dir, webhook_url)`

运行一次 watchdog 扫描（供 cron 调用）。

```bash
# cron 每分钟运行一次
* * * * * cd /path/to/deepflow && python3 -m core.process_manager.watchdog /path/to/session https://webhook.url
```

---

## 使用示例

### 场景 1：Orchestrator spawn Module Agent

```python
from core.process_manager import ModuleLifecycleManager

lifecycle = ModuleLifecycleManager(session_dir)

# 1. spawn 前去重
run = lifecycle.try_acquire_run("planning")
if run.already_running:
    print("已有活跃运行，不重复 spawn")
else:
    # 2. spawn Module Agent
    sessions_spawn(
        task=f"""
        RUN_ID: {run.run_id}
        执行 Planning 模块...
        """,
        cwd=deepflow_root,
    )

# 3. 等待完成
result = lifecycle.wait_for_module(
    module="planning",
    expected_files=["stages/planning_convergence.json"],
    min_file_sizes={"stages/planning_convergence.json": 10000},
)

if result.found:
    print("Planning 完成")
elif result.reason == "stall":
    print("Planning stall，需要 respawn")
elif result.reason == "timeout":
    print("Planning 超时")
```

### 场景 2：Module Agent 执行工作

```python
from core.process_manager import ModuleLifecycleManager

lifecycle = ModuleLifecycleManager(session_dir)
run_id = "planning_1785081345_a1b2c3d4"  # 从 task 中获取

import time

while True:
    # 1. 定期心跳（每 60 秒）
    if not lifecycle.heartbeat("planning", run_id):
        print("已被替代，停止执行")
        break
    
    # 2. 执行工作
    # ...
    
    # 3. 写输出文件（必须用原子写）
    lifecycle.atomic_write_file(
        target_path="stages/planning_convergence.json",
        content=json.dumps(data),
    )
    
    # 4. 完成时标记（可选，ProcessManager 会自动检测）
    lifecycle.mark_completed("planning", run_id, output_files={
        "stages/planning_convergence.json": {
            "size": len(content),
            "mtime": time.time(),
        }
    })
    break
```

### 场景 3：配置 watchdog cron

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每分钟扫描一次）
* * * * * cd /Users/allen/.openclaw/workspace/.deepflow && python3 -m core.process_manager.watchdog /Users/allen/.openclaw/workspace/.deepflow/blackboard/2.5D封装_V40_20260726 https://hooks.slack.com/xxx
```

---

## 契约定义（Pydantic Models）

所有数据结构通过 Pydantic 契约验证，确保稳健性。

```python
from core.process_manager.contracts import (
    WaitResultContract,          # wait_for 返回结果
    ModuleWaitResultContract,    # wait_for_module 返回结果
    RunRecordContract,           # 运行记录（单源状态）
    AtomicWriteContract,         # 原子写操作
    WatchdogAlertContract,       # Watchdog 告警
    FileValidationContract,      # 文件验证
    StallDetectionContract,      # Stall 检测
    TimeoutAlertContract,        # 超时告警
)
```

---

## 解决的故障（V37-V40）

| 问题 | 根因 | 解决方案 |
|------|------|---------|
| **mark_completed 没调用** | Agent 可能不调用 mark_completed | 输出文件验证（必要条件），不依赖 mark_completed |
| **JSON 损坏** | 写入中断导致文件损坏 | 强制原子写（.tmp + rename）|
| **状态不一致** | pipeline_state.json 和 .run.json 双写 | 单源状态管理（从 .run.json 派生）|
| **卡死 75 分钟无人知** | 无主动告警守护进程 | 独立 watchdog（cron 1min）+ webhook 告警 |
| **超时事件无法捕获** | wait_for 超时仅 print | 超时 webhook 告警（写入告警文件 + 调用 webhook）|
| **stall 检测缺失** | 只检查心跳，不检查文件 mtime | 多信号 stall 检测（心跳超时 + 文件 mtime 超时）|

---

## 测试

```bash
# 运行 ProcessManager 测试
python3 -m pytest core/process_manager/tests/ -v

# 运行 Solution Pro 测试（验证无回归）
python3 -m pytest domains/solution_pro/tests/ -v
```

---

## 版本历史

- **v1.0** (2026-07-25): 初始版本，最小原语（wait_for）
- **v2.0** (2026-07-27): 增强版，契约笼方法
  - 输出文件验证（不依赖 mark_completed）
  - 多信号 stall 检测（心跳 + 文件 mtime）
  - 强制原子写（.tmp + rename）
  - 单源状态管理（消除双写）
  - 独立 watchdog（cron 1min）
  - 超时 webhook 告警
