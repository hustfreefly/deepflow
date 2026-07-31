# INVESTIGATION-001: 主微信消息队列被 Deliver Pro 阻塞

> 调查时间：2026-07-31 19:00
> 报告人：用户反馈 + 代码调查
> 状态：根因已确认，待修复

---

## 问题描述

**用户反馈**：
> "Deliver Pro 在工作的时候，主微信的消息队列就被占用了，我很难给你发信息。我给你发了信息，你也不能及时回。"

**症状**：
- Deliver Pro 执行期间，主 agent 无法及时响应用户消息
- 消息延迟或完全无响应
- 用户体验极差

---

## 根因分析

### 1. 直接原因：Pulse 同步阻塞主 agent

```
主 Agent（处理用户消息）
  ↓ exec(pulse_cli.py pulse --project X)
  ↓ [阻塞 30-60 秒]
  ↓ 扫描 28 个 WP
  ↓ 推导进度（文件系统 I/O）
  ↓ Spawn 5 个 agents
  ↓ 返回 report
  ↓ [恢复响应]
```

**关键代码**：
- `pulse_cli.py:cmd_pulse()` → `orch.pulse()` → 同步执行 30-60 秒
- 主 agent 直接调用 `exec`，被阻塞直到完成

### 2. 设计意图 vs 实际执行

**设计意图**（来自 `pulse-v1-implementation.md`）：
> "cron 每 5 分钟点火一个全新 isolated session → exec 跑 `DeliverOrchestrator.pulse()` → 动作落盘 `_pulse_actions.json` → pulse agent 逐条 spawn + confirm 回执 → session 结束。"

**实际执行**：
- ❌ 没有 cron 定时任务（`crontab` 为空）
- ❌ 没有 isolated session（直接在主 agent 执行）
- ❌ 主 agent 同步调用 `pulse()`，阻塞 30-60 秒

### 3. 为什么设计没有落地？

**根因**：
1. **cron 配置缺失**：没有设置 launchd/crontab 定时任务
2. **主 agent 越权**：主 agent 直接调用 pulse，而不是让 cron 触发 isolated session
3. **缺少护栏**：没有代码阻止主 agent 同步调用 pulse

### 4. 影响范围

| 影响 | 严重度 | 说明 |
|------|:------:|------|
| 用户消息延迟 | 🔴 高 | 30-60 秒无响应 |
| 用户体验差 | 🔴 高 | "很难给你发信息" |
| 主 agent 被占用 | 🟡 中 | 无法处理其他任务 |
| Pulse 执行不完整 | 🟡 中 | 主 agent 可能中断 pulse |

---

## 与复盘问题的关联

这个问题与复盘报告中的多个问题相互关联：

### 问题网络

```
┌─────────────────────────────────────────────────────────────┐
│                    根因：Pulse 没有独立调度                    │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ 消息队列阻塞  │   │ 告警静默失效  │   │ 调度空窗      │
│ (本调查)      │   │ (复盘 P0-2)   │   │ (复盘 P0-3)   │
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ↓
                    ┌───────────────┐
                    │ 4 个 WP 卡死  │
                    │ 6+ 小时无告警 │
                    └───────────────┘
```

**关键洞察**：
- **消息队列阻塞** 和 **告警静默失效** 是同一个根因的两个表现
- 如果 Pulse 独立调度（cron + isolated session），这两个问题同时解决
- 这是 **最高杠杆的修复点**

---

## 解决方案

### 方案概述

**核心思路**：Pulse 必须独立于主 agent 运行

```
┌─────────────────────────────────────────────────────────────┐
│                    目标架构                                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  cron/launchd (每 5 分钟)                                    │
│       ↓                                                      │
│  isolated session (独立进程)                                 │
│       ↓                                                      │
│  exec(pulse_cli.py pulse --project X)                        │
│       ↓                                                      │
│  落盘 _pulse_actions.json                                    │
│       ↓                                                      │
│  pulse agent 逐条 spawn                                      │
│       ↓                                                      │
│  session 结束                                                │
│                                                              │
│  主 Agent（独立运行，不被阻塞）                               │
│    - 处理用户消息                                            │
│    - 需要时调用 check 命令（<1 秒）                          │
│    - 不直接调用 pulse                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 实施步骤

#### Phase 1: 立即止血（P0，1 小时）

**目标**：阻止主 agent 同步调用 pulse

1. **代码护栏**：在 `pulse_cli.py` 添加检测
   ```python
   def cmd_pulse(args) -> int:
       # 检测是否在主 agent 中运行
       if os.environ.get("OPENCLAW_SESSION") == "main":
           print("ERROR: pulse 不应在主 agent 中同步执行", file=sys.stderr)
           print("请使用 cron + isolated session 模式", file=sys.stderr)
           return 10  # 特殊退出码
       
       # 原有逻辑
       orch = _load_orchestrator(args.project)
       report = orch.pulse()
       ...
   ```

2. **主 agent 行为修正**：
   - 禁止主 agent 直接调用 `pulse_cli.py pulse`
   - 只允许调用 `check` 命令（轻量检查）
   - 写入 AGENTS.md / SKILL.md

3. **临时方案**：如果必须手动触发 pulse，使用 `--async` 模式（方案 2）

#### Phase 2: 独立调度（P0，2 小时）

**目标**：实现 cron + isolated session 模式

1. **macOS launchd 配置**：
   ```xml
   <!-- ~/Library/LaunchAgents/ai.openclaw.deliver-pro-pulse.plist -->
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>ai.openclaw.deliver-pro-pulse</string>
       <key>ProgramArguments</key>
       <array>
           <string>/usr/local/bin/python3</string>
           <string>-m</string>
           <string>domains.deliver_pro.pulse_cli</string>
           <string>pulse</string>
           <string>--project</string>
           <string>2.5D封装设计团队_MD_V2</string>
       </array>
       <key>WorkingDirectory</key>
       <string>/Users/allen/.openclaw/workspace/.deepflow</string>
       <key>StartInterval</key>
       <integer>300</integer> <!-- 5 分钟 -->
       <key>StandardOutPath</key>
       <string>/tmp/deliver-pro-pulse.log</string>
       <key>StandardErrorPath</key>
       <string>/tmp/deliver-pro-pulse.err</string>
   </dict>
   </plist>
   ```

2. **加载 launchd 任务**：
   ```bash
   launchctl load ~/Library/LaunchAgents/ai.openclaw.deliver-pro-pulse.plist
   ```

3. **验证**：
   ```bash
   # 检查任务是否运行
   launchctl list | grep deliver-pro-pulse
   
   # 查看日志
   tail -f /tmp/deliver-pro-pulse.log
   ```

#### Phase 3: 异步模式（P1，2 小时）

**目标**：实现 `--async` 模式作为备用方案

1. **修改 `pulse_cli.py`**：
   ```python
   def cmd_pulse(args) -> int:
       if args.async_mode:
           import subprocess
           import os
           
           # 后台执行
           log_file = f"/tmp/pulse-{args.project}-{int(time.time())}.log"
           with open(log_file, "w") as f:
               proc = subprocess.Popen([
                   sys.executable, "-m", "domains.deliver_pro.pulse_cli",
                   "pulse", "--project", args.project
               ], stdout=f, stderr=f)
           
           print(json.dumps({
               "status": "async_started",
               "pid": proc.pid,
               "log_file": log_file
           }))
           return 0
       
       # 原有同步逻辑
       ...
   ```

2. **主 agent 调用模式**：
   ```python
   # 启动异步 pulse
   exec("python3 -m domains.deliver_pro.pulse_cli pulse --project X --async")
   # → 立即返回，不阻塞
   
   # 需要检查进度时
   exec("python3 -m domains.deliver_pro.pulse_cli check --project X")
   # → 轻量检查，<1 秒
   ```

#### Phase 4: 心跳告警（P0，1 小时）

**目标**：监控 Pulse 是否正常运行

1. **Pulse 写心跳**：
   ```python
   # pulse_cli.py
   def cmd_pulse(args) -> int:
       # 写心跳
       heartbeat_path = BLACKBOARD_ROOT / args.project / "_pulse_heartbeat.json"
       atomic_write_json(heartbeat_path, {
           "timestamp": time.time(),
           "pid": os.getpid()
       })
       
       # 原有逻辑
       ...
   ```

2. **独立 watchdog**：
   ```python
   # watchdog.py (另一个 launchd 任务，每 10 分钟检查)
   heartbeat = json.loads(heartbeat_path.read_text())
   age = time.time() - heartbeat["timestamp"]
   if age > 600:  # 10 分钟无心跳
       # 发送飞书告警
       send_feishu_alert("Pulse 心跳超时，可能已停止运行")
   ```

---

## 验收标准

| 验收项 | 标准 | 验证方法 |
|--------|------|----------|
| 主 agent 不被阻塞 | 用户消息 <5 秒响应 | 手动测试 |
| Pulse 独立运行 | cron 每 5 分钟触发 | 查看日志 |
| 心跳告警 | 超时 10 分钟发告警 | 模拟故障 |
| 代码护栏 | 主 agent 调用 pulse 返回错误 | 单元测试 |

---

## 与复盘改进建议的整合

本调查的解决方案与复盘报告中的 P0 改进建议高度重合：

| 复盘建议 | 本调查方案 | 关系 |
|----------|-----------|------|
| 调度与监控独立于主 agent | Phase 2: launchd 配置 | ✅ 完全一致 |
| 心跳告警 | Phase 4: 心跳 + watchdog | ✅ 完全一致 |
| Pulse 异步化 | Phase 3: --async 模式 | ✅ 完全一致 |

**结论**：本调查的解决方案就是复盘 P0 改进的具体实施计划。

---

## 下一步行动

### 立即执行（今天）

1. **Phase 1: 代码护栏**（1h）
   - 修改 `pulse_cli.py`，检测并阻止主 agent 同步调用
   - 更新 AGENTS.md，明确禁止主 agent 调用 pulse

2. **Phase 2: launchd 配置**（2h）
   - 创建 plist 文件
   - 加载并验证
   - 观察 1-2 个周期

### 短期执行（本周）

3. **Phase 3: --async 模式**（2h）
   - 实现异步模式
   - 测试验证

4. **Phase 4: 心跳告警**（1h）
   - 实现心跳写入
   - 配置 watchdog

### 验证与监控

5. **观察 1 周**
   - 确认消息队列不再阻塞
   - 确认 Pulse 正常运行
   - 确认告警机制有效

---

## 总结

**根因**：Pulse 没有独立调度，直接在主 agent 同步执行，阻塞 30-60 秒

**影响**：
- 用户消息延迟（本调查）
- 告警静默失效（复盘 P0-2）
- 调度空窗（复盘 P0-3）

**解决方案**：Pulse 独立调度（cron + isolated session）

**最高杠杆**：这一个修复同时解决 3 个 P0 问题

**实施计划**：4 个 Phase，总计 6 小时，今天可以完成 Phase 1-2

---

> 调查完成时间：2026-07-31 19:30
> 调查方法：代码审查 + 文档分析 + 根因追溯
> 下一步：等待用户确认，开始实施 Phase 1-2
