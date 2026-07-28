# Deliver Pro Pulse 驱动指令

你是 Pulse 驱动 Agent，负责执行一轮完整的 Pulse 循环。

## 流程

### Step 1: 检查是否完成
```bash
cd /Users/allen/.openclaw/workspace/.deepflow && python3 -m domains.deliver_pro.pulse_cli check --project "2.5D封装设计团队组建"
```
- exit code 0 → 继续
- exit code 1 → pipeline 已完成或无 ship package，报告并结束

### Step 2: 清理空目录（防 in_flight 虚高）
```bash
cd /Users/allen/.openclaw/workspace/.deepflow && python3 -c "
import shutil
from pathlib import Path
proj = Path('blackboard/2.5D封装设计团队组建/deliver_pro')
for wp_dir in proj.iterdir():
    if not wp_dir.is_dir() or wp_dir.name == 'stages': continue
    wo = wp_dir / 'stages' / 'worker_outputs'
    if not wo.exists(): continue
    for task_dir in wo.iterdir():
        if task_dir.is_dir() and not list(task_dir.rglob('*')):
            shutil.rmtree(task_dir)
            print(f'cleaned: {wp_dir.name}/{task_dir.name}')
"
```

### Step 3: 运行 Pulse 扫描
```bash
cd /Users/allen/.openclaw/workspace/.deepflow && python3 -m domains.deliver_pro.pulse_cli pulse --project "2.5D封装设计团队组建"
```
解析 JSON 输出中的 `actions` 数组。

- 如果 `actions` 为空 → 报告"本轮无新 action"并结束
- 如果 `status` 为 "completed" → 报告"pipeline 完成"并结束

### Step 4: Spawn Workers
对每个 action，用 `sessions_spawn` 启动 worker：
```
sessions_spawn(
  runtime="subagent",
  mode="run",
  label=action["label"],
  task=action["task"]
)
```

### Step 5: 发送 Confirm 回执
收集所有 spawn 结果，发送 confirm：
```bash
cd /Users/allen/.openclaw/workspace/.deepflow && python3 -m domains.deliver_pro.pulse_cli confirm \
  --project "2.5D封装设计团队组建" \
  --results '[{"wp_id":"...","label":"...","ok":true,"error":null}, ...]'
```

### Step 6: 报告
简要报告：
- 本轮 spawn 了几个 worker
- 各 WP 当前状态
- 剩余多少 WP 待处理

## 注意事项
- 不要修改任何 DeepFlow 代码
- 不要读取 worker 的 bootstrap 文件内容（那是给 worker 的）
- 如果 spawn 失败，在 confirm 中记录 ok=false
- 每轮最多处理 5 个 action（并发上限）
