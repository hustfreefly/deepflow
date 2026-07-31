# Deliver Pro 异步 Pulse 方案（解决主 agent 消息队列占用）

> 问题：Pulse 同步执行阻塞主 agent，导致用户消息响应延迟
> 日期：2026-07-31

---

## 问题根因

```
主 Agent
  ↓ exec(pulse_cli.py pulse --project X)
  ↓ [阻塞 30-60 秒]
  ↓ 扫描 26 个 WP
  ↓ 推导进度（文件系统 I/O）
  ↓ Spawn 5 个 agents
  ↓ 返回 report
  ↓ [恢复响应]
```

**瓶颈**：`orch.pulse()` 是同步调用，主 agent 被阻塞直到完成。

---

## 方案 1：异步 Pulse（推荐）

### 核心思路
Pulse 放到后台执行，主 agent 立即返回，通过文件状态查询结果。

### 实现

```python
# pulse_cli.py 新增 --async 模式
def cmd_pulse(args) -> int:
    if args.async_mode:
        # 后台执行，立即返回
        import subprocess
        subprocess.Popen([
            sys.executable, "-m", "domains.deliver_pro.pulse_cli",
            "pulse", "--project", args.project
        ])
        print(json.dumps({"status": "async_started", "pid": ...}))
        return 0
    
    # 同步执行（原有逻辑）
    orch = _load_orchestrator(args.project)
    report = orch.pulse()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0
```

### 主 agent 调用模式

```python
# 1. 启动异步 pulse
exec("python3 -m domains.deliver_pro.pulse_cli pulse --project X --async")
# → 立即返回，不阻塞

# 2. 用户发消息时，主 agent 可以立即响应
# 3. 需要检查进度时，用 check 命令
exec("python3 -m domains.deliver_pro.pulse_cli check --project X")
# → 轻量检查，<1 秒
```

### 优点
- 主 agent 不被阻塞
- 用户消息可以立即响应
- 实现简单，改动小

### 缺点
- 需要额外的状态查询机制
- 后台进程管理复杂

---

## 方案 2：增量 Pulse

### 核心思路
每次 pulse 只处理少量 WP（如 3-5 个），分多次执行。

### 实现

```python
# orchestrator.py
def pulse(self, max_wps_per_pulse: int = 3) -> dict:
    # 只处理前 N 个活跃 WP
    active_wps = self._get_active_wps()[:max_wps_per_pulse]
    for wp_id in active_wps:
        self._process_wp(wp_id)
    ...
```

### 主 agent 调用模式

```python
# 多次调用，每次处理少量 WP
for i in range(0, total_wps, 3):
    exec(f"python3 -m domains.deliver_pro.pulse_cli pulse --project X --max-wps 3 --offset {i}")
    # 每次处理 3 个 WP，约 10 秒
    # 中间可以响应用户消息
```

### 优点
- 单次 pulse 时间短（10 秒 vs 60 秒）
- 实现简单
- 可以中途响应用户

### 缺点
- 需要多次调用
- 总时间可能更长

---

## 方案 3：独立调度进程

### 核心思路
用 cron 或独立进程执行 pulse，完全不占用主 agent。

### 实现

```bash
# crontab
*/2 * * * * python3 -m domains.deliver_pro.pulse_cli pulse --project X >> /tmp/pulse.log 2>&1
```

### 主 agent 角色
- 只负责启动/停止 cron
- 查询进度（`check` 命令）
- 不执行 pulse

### 优点
- 主 agent 完全不被阻塞
- 调度与响应解耦

### 缺点
- 需要 cron 管理
- 调试复杂
- 与 OpenClaw 架构不一致

---

## 方案 4：优先级中断

### 核心思路
Pulse 执行中检测到用户消息，暂停 pulse 优先响应。

### 实现
需要 OpenClaw 平台支持：
- 消息队列优先级
- 可中断的 exec 调用
- 状态恢复机制

### 优点
- 用户体验最好
- 资源利用率高

### 缺点
- 需要平台支持
- 实现复杂
- 状态恢复困难

---

## 推荐方案：异步 Pulse + 增量处理

结合方案 1 和方案 2：

```python
# 主 agent 调用
exec("python3 -m domains.deliver_pro.pulse_cli pulse --project X --async --max-wps 5")
# → 后台启动，每次处理 5 个 WP
# → 主 agent 立即返回

# 用户发消息
# → 主 agent 立即响应

# 需要检查进度
exec("python3 -m domains.deliver_pro.pulse_cli check --project X")
# → 轻量检查，<1 秒
```

### 实现优先级

| 阶段 | 内容 | 工作量 |
|------|------|--------|
| **Phase 1** | 增量 Pulse（`--max-wps` 参数） | 2h |
| **Phase 2** | 异步 Pulse（`--async` 参数） | 4h |
| **Phase 3** | 状态查询优化（`check` 命令增强） | 2h |

---

## 临时解决方案（立即可用）

在实现异步 Pulse 之前，可以：

1. **减少单次 Pulse 处理的 WP 数量**
   ```python
   # orchestrator.py
   MAX_WPS_PER_PULSE = 5  # 从 26 降到 5
   ```

2. **优化 Pulse 内部逻辑**
   - 减少文件系统 I/O（缓存 MANIFEST）
   - 并行推导进度（多线程）
   - 减少 spawn 等待时间

3. **主 agent 分层响应**
   - 用户消息优先处理
   - Pulse 在空闲时执行
   - 长时间 Pulse 拆分成多次

---

## 总结

| 问题 | 根因 | 解决方案 |
|------|------|----------|
| 主 agent 消息队列被占用 | `pulse()` 同步阻塞 | 异步 Pulse + 增量处理 |
| 单次 Pulse 耗时过长 | 处理 26 个 WP | `--max-wps` 限制 |
| 无法中途响应用户 | exec 阻塞 | `--async` 后台执行 |

**推荐实施顺序**：
1. 立即：减少 `MAX_WPS_PER_PULSE`（临时缓解）
2. 短期：实现增量 Pulse（`--max-wps`）
3. 中期：实现异步 Pulse（`--async`）
4. 长期：平台级消息优先级支持
