# Cron 架构专家评审：Solution Pro 巡检员

> **日期**: 2026-06-01
> **评审对象**: 基于 isolated cron job 的 Solution Pro 进度通知方案
> **评审者**: expert_cron_architecture sub-agent

---

## 一、方案评估总览

| 维度 | 评分 | 说明 |
|------|------|------|
| 可行性 | ⭐⭐⭐⭐ 4/5 | isolated cron 有完整工具集，技术上可行 |
| 可靠性 | ⭐⭐ 2/5 | 无状态 + 多次独立运行 = 状态泄漏点密集 |
| 可维护性 | ⭐⭐ 2/5 | 分布式状态机需要精确对齐多个退出路径 |
| 推荐度 | ⭐⭐ 2/5 | 能工作但需要大量防御性设计 |

---

## 二、退出机制设计

### 2.1 正常退出（Happy Path）

```
cron 第 N 次运行
  ├── 扫描 stages/ 目录
  ├── 发现 .completed 文件
  ├── 读取 .completed 获取最终状态
  ├── message 发送最终报告
  ├── cron remove 自杀
  └── exit 0
```

**脚本逻辑**：

```bash
#!/usr/bin/env bash
# cron-watcher.sh — 每次 cron 触发的入口

STAGES_DIR="/Users/allen/.openclaw/workspace/.deepflow/blackboard/<session_id>/stages"
HEARTBEAT_FILE="/Users/allen/.openclaw/workspace/.deepflow/blackboard/<session_id>/.heartbeat"

# --- 1. 检查 .completed ---
if [ -f "${STAGES_DIR}/.completed" ]; then
  # 最终报告
  RESULT=$(cat "${STAGES_DIR}/.completed" 2>/dev/null || echo "完成但无法读取结果")
  message --text "✅ Solution Pro 已完成\n\n${RESULT}"
  cron remove --label "${CRON_LABEL}"
  exit 0
fi

# --- 2. 检查心跳超时（orchestrator 可能已崩溃）---
if [ -f "${HEARTBEAT_FILE}" ]; then
  LAST_HEARTBEAT=$(stat -f %m "${HEARTBEAT_FILE}" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  ELAPSED=$(( NOW - LAST_HEARTBEAT ))
  HEARTBEAT_TIMEOUT=600  # 10 分钟无心跳 = orchestrator 挂掉
  if [ "${ELAPSED}" -gt "${HEARTBEAT_TIMEOUT}" ]; then
    message --text "⚠️ Solution Pro 已超时（${ELAPSED}s 无心跳）\n\nOrchestrator 可能已崩溃，cron 将停止巡检。"
    cron remove --label "${CRON_LABEL}"
    exit 0
  fi
fi

# --- 3. 检查最大运行次数 ---
# 通过 cron 的 label 或外部计数器追踪
RUN_COUNT_FILE="/tmp/cron-watcher-${CRON_LABEL}-count"
COUNT=$(cat "${RUN_COUNT_FILE}" 2>/dev/null || echo 0)
COUNT=$(( COUNT + 1 ))
echo "${COUNT}" > "${RUN_COUNT_FILE}"

MAX_RUNS=20  # 3分钟 × 20 = 60分钟 = orchestrator 最大超时
if [ "${COUNT}" -gt "${MAX_RUNS}" ]; then
  message --text "🛑 巡检员达到最大运行次数（${MAX_RUNS}）\n\nOrchestrator 运行超过 ${MAX_RUNS}×3=60 分钟，可能卡死。"
  cron remove --label "${CRON_LABEL}"
  exit 0
fi

# --- 4. 扫描进度 ---
STAGE_COUNT=$(find "${STAGES_DIR}" -name "*.json" -not -name ".completed" 2>/dev/null | wc -l | tr -d ' ')
if [ "${STAGE_COUNT}" -gt 0 ]; then
  STAGE_FILES=$(find "${STAGES_DIR}" -name "*.json" -not -name ".completed" 2>/dev/null | sort)
  LAST_STAGE=$(echo "${STAGE_FILES}" | tail -1)
  LAST_STAGE_NAME=$(basename "${LAST_STAGE}" .json)
  message --text "📊 Solution Pro 进度：${STAGE_COUNT} 个阶段已完成\n\n最新阶段：${LAST_STAGE_NAME}"
fi
```

### 2.2 超时退出（Orchestrator 崩溃）

**三层超时检测**：

| 层级 | 机制 | 超时值 | 触发条件 |
|------|------|--------|---------|
| L1 | 心跳文件 | 10 分钟无写入 | orchestrator 进程挂掉 |
| L2 | 最大运行次数 | 20 次 (60 分钟) | cron 计数器 |
| L3 | orchestrator runTimeoutSeconds | 3600 秒 | OpenClaw 子 Agent 超时 |

**心跳机制设计**：

Orchestrator 在完成每个阶段时，除了写 `stages/N.json`，还必须写：

```bash
date +%s > /path/to/blackboard/<session_id>/.heartbeat
```

Cron watcher 检查 `.heartbeat` 文件的 mtime，如果超过 10 分钟没更新，判定 orchestrator 已崩溃。

### 2.3 最大运行次数

```
MAX_RUNS = ceil(orchestrator_timeout_seconds / cron_interval_seconds)
         = ceil(3600 / 180)
         = 20

实际建议 = 20 + 2 = 22（留 6 分钟缓冲）
```

**实现方式**：使用 `/tmp/` 文件计数（isolated cron 每次新 session，无法内存计数）。

### 2.4 主 Agent 兜底

```
主 Agent 流程：
  1. spawn orchestrator（带 label）
  2. cron_add watcher（带 label）
  3. yield

主 Agent 收到 orchestrator announce 后：
  ├── 展示最终结果给用户
  ├── exec: cron remove --label "solution-watcher-<session_id>"
  └── exec: rm -f /tmp/cron-watcher-<session_id>-count
```

**这是最可靠的退出路径**，因为主 Agent 是唯一知道 orchestrator 已完成的实体。

**问题**：主 Agent yield 后处于休眠状态，只有在收到 announce 时才会醒来。如果 orchestrator 崩溃不 announce，主 Agent 不会醒来 → 依赖 L1/L2 超时退出。

---

## 三、生命周期状态机

### 3.1 状态转换图

```
                    ┌──────────────────────────────────────────┐
                    │                                          │
                    ▼                                          │
    ┌─────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐  │
    │ IDLE │───▶│ SCANNING │───▶│ REPORTING │───▶│ CONTINUE  │──┘
    └─────┘    └──────────┘    └──────────┘    └───────────┘
                                    │
                  ┌─────────────────┼──────────────────┐
                  ▼                 ▼                  ▼
            ┌──────────┐   ┌──────────────┐   ┌──────────────┐
            │ COMPLETED│   │ TIMEOUT_L1   │   │ TIMEOUT_L2   │
            │ + suicide│   │ + suicide    │   │ + suicide    │
            └──────────┘   └──────────────┘   └──────────────┘
```

### 3.2 详细状态定义

| 状态 | 触发 | 动作 | 下一状态 |
|------|------|------|----------|
| **CREATED** | 主 Agent `cron_add` | cron 任务已注册，等待首次触发 | → IDLE |
| **IDLE** | cron interval 到期 | 新 session 启动，加载计数 | → SCANNING |
| **SCANNING** | 进入运行时 | 读取 .completed、.heartbeat、计数器 | → 根据结果分流 |
| **REPORTING** | 发现阶段进展 | `message` 发送进度 | → CONTINUE |
| **CONTINUE** | 报告完毕 | 更新计数器，正常退出，等待下次 cron 触发 | → IDLE |
| **COMPLETED** | 发现 .completed | 发送最终报告 → `cron remove` → 清理临时文件 | → TERMINATED |
| **TIMEOUT_L1** | 心跳超时 | 发送告警 → `cron remove` → 清理 | → TERMINATED |
| **TIMEOUT_L2** | 运行次数超限 | 发送告警 → `cron remove` → 清理 | → TERMINATED |
| **TIMEOUT_L3** | orchestrator 超时被杀 | 心跳超时 + 无 .completed → 同上 | → TERMINATED |
| **TERMINATED** | 终态 | cron 已删除，无后续触发 | — |

### 3.3 创建时机

```
主 Agent 伪代码：

SESSION_ID=$(date +%s)_$RANDOM

# 1. 创建 stages 目录
mkdir -p /path/to/blackboard/${SESSION_ID}/stages

# 2. 初始化计数器
echo "0" > /tmp/cron-watcher-${SESSION_ID}-count

# 3. 注册 cron watcher
cron_add --label "solution-watcher-${SESSION_ID}" \
         --interval 180 \
         --command "bash /path/to/cron-watcher.sh ${SESSION_ID}"

# 4. Spawn orchestrator
sessions_spawn(
  task="执行 Solution Pro 管线，每完成一个阶段写 stages/N.json 并更新 .heartbeat",
  runTimeoutSeconds=3600
)

# 5. Yield
sessions_yield()
```

### 3.4 清理策略

| 资源 | 清理时机 | 清理者 |
|------|----------|--------|
| cron job | .completed / 超时 / 主 Agent 兜底 | cron watcher 或主 Agent |
| 计数器文件 | cron 自杀时 | cron watcher |
| .heartbeat | 任务结束时 | orchestrator 或 cron watcher |
| stages/*.json | 保留（作为审计记录） | — |
| .completed | 保留（作为完成标志） | — |

---

## 四、失败场景分析

### 4.1 失败场景矩阵

| # | 场景 | 概率 | 影响 | 检测方式 | 恢复策略 | 责任人 |
|---|------|------|------|----------|---------|--------|
| 1 | orchestrator 超时（3600s） | 中 | 高 | L1 心跳超时 → L2 计数超限 | cron 自杀 + 告警 | cron watcher |
| 2 | orchestrator 崩溃（OOM/异常） | 低 | 高 | L1 心跳停止更新 | cron L1 超时自杀 + 告警 | cron watcher |
| 3 | cron job 自身失败 | 中 | 中 | 连续 2 次无消息 | 无自动恢复 → 用户感知 | 用户/主 Agent |
| 4 | Gateway 重启 | 低 | 高 | cron 任务丢失 | 主 Agent 重启后需手动重注册 | 主 Agent |
| 5 | 网络断开 | 低 | 中 | `message` 失败 | cron 继续运行，消息丢弃，网络恢复后重新发送 | cron watcher |
| 6 | stages/ 目录不存在 | 低 | 中 | 文件检查失败 | cron 判定为异常 → 自杀 | cron watcher |
| 7 | .completed 写失败 | 极低 | 高 | orchestrator 报错 | orchestrator 重试或崩溃 → 退到 L1 超时 | orchestrator |
| 8 | 计数器文件丢失 | 中 | 低 | `cat` 返回空 | 从 0 重新计数（安全降级） | cron watcher |
| 9 | 主 Agent 崩溃 | 低 | 高 | 无兜底 | cron 继续运行直到超时自杀 | cron watcher |
| 10 | 消息去重（重复通知） | 高 | 低 | 连续相同状态 | cron 跳过相同状态的通知 | cron watcher |

### 4.2 各场景详细分析

#### 场景 1：orchestrator 超时（3600s）

```
时间线：
  T+0s    → 主 Agent spawn orchestrator + cron watcher
  T+180s  → cron 第 1 次运行，发现 0 阶段，报告 "等待中"
  T+360s  → cron 第 2 次运行，发现 1 阶段，报告 "阶段 1 完成"
  ...
  T+3600s → OpenClaw 杀掉 orchestrator（runTimeoutSeconds 到期）
  T+3600s → orchestrator 崩溃，不写 .completed，心跳停止
  T+3780s → cron 第 21 次运行，心跳超时 → 告警 → 自杀
```

**应对**：L1 心跳超时在 orchestrator 被杀后 ~10 分钟检测，L2 计数器在 66 分钟检测。**推荐 L1 先触发**。

#### 场景 2：orchestrator 崩溃

```
可能原因：
  - OOM（LLM 响应过大，内存溢出）
  - 未处理的异常（API 错误、文件系统错误）
  - 内部 panic

行为：
  - 不写 .completed
  - 心跳停止更新
  - 不 announce（主 Agent 收不到信号）

检测：
  - L1 心跳超时（推荐 10 分钟）
  - cron 检查 .heartbeat 的 mtime

恢复：
  - cron 发送告警消息
  - cron 自杀
  - 用户手动重新启动（或主 Agent 收到告警后处理）
```

#### 场景 3：cron job 自身失败

```
可能原因：
  - bash 脚本语法错误
  - 权限问题
  - OpenClaw cron 调度器 bug

行为：
  - cron 不触发或触发后立即退出
  - 用户收不到任何进度消息

检测：
  - 无法自动检测（cron 是静默失败）
  - 用户在 6+ 分钟后没收到任何消息 → 感知到问题

缓解：
  - 主 Agent 在 spawn orchestrator 之前先运行一次 cron 脚本验证
  - cron 脚本加 set -e 和错误日志
  - 考虑备用方案：主 Agent yield 前 exec 运行一次验证
```

#### 场景 4：Gateway 重启

```
场景：
  - 用户执行 openclaw gateway restart
  - launchctl kickstart Gateway
  - 系统重启

影响：
  - cron 任务全部丢失（不持久化）
  - orchestrator 子 Agent 也被杀死
  - 没有任何实体在运行

恢复：
  - Gateway 重启后，主 Agent 需要重新注册 cron
  - 但主 Agent 可能不知道之前有一个活跃的管线
  - **需要持久化任务状态**

持久化设计：
  在 blackboard/<session_id>/ 下写 .task_state.json：
  {
    "status": "running",
    "cron_label": "solution-watcher-123456",
    "created_at": "2026-06-01T00:00:00Z",
    "orchestrator_session_id": "abc-123"
  }

  Gateway 重启后，主 Agent 启动时检查：
  - 存在 .task_state.json 且 status = "running" → 恢复 cron + 通知用户
```

#### 场景 5：网络断开

```
场景：
  - WiFi 断开
  - DNS 故障
  - OpenAI API 不可达

行为：
  - orchestrator 可能因 API 调用失败而挂起
  - cron watcher 的 message 调用失败

检测：
  - cron 检查 message 返回值
  - 心跳可能仍在更新（orchestrator 在本地重试）

应对：
  - cron 的 message 失败时不应阻止后续运行
  - 使用 try-catch 包裹 message 调用
  - 网络恢复后，下一条消息正常发送
```

---

## 五、增强设计：消息去重

**问题**：如果 orchestrator 在两个 cron 周期之间没有新阶段完成，cron 会发送完全相同的消息。

**解决方案**：记录上次报告的阶段数，只在变化时发送。

```bash
# 消息去重
LAST_REPORTED_FILE="/tmp/cron-watcher-${SESSION_ID}-last-reported"
LAST_REPORTED=$(cat "${LAST_REPORTED_FILE}" 2>/dev/null || echo "-1")

STAGE_COUNT=$(find "${STAGES_DIR}" -name "*.json" -not -name ".completed" 2>/dev/null | wc -l | tr -d ' ')

if [ "${STAGE_COUNT}" != "${LAST_REPORTED}" ]; then
  message --text "📊 Solution Pro 进度：${STAGE_COUNT}/10 个阶段已完成"
  echo "${STAGE_COUNT}" > "${LAST_REPORTED_FILE}"
else
  echo "阶段数未变化 (${STAGE_COUNT})，跳过通知"
fi
```

---

## 六、完整脚本实现

```bash
#!/usr/bin/env bash
# cron-watcher.sh — Solution Pro 进度巡检员
# 每次 cron 触发时运行（isolated session，无状态）
# 参数 1: SESSION_ID

set -euo pipefail

SESSION_ID="${1:?SESSION_ID required}"
BLACKBOARD_BASE="/Users/allen/.openclaw/workspace/.deepflow/blackboard"
STAGES_DIR="${BLACKBOARD_BASE}/${SESSION_ID}/stages"
HEARTBEAT_FILE="${BLACKBOARD_BASE}/${SESSION_ID}/.heartbeat"
CRON_LABEL="solution-watcher-${SESSION_ID}"

# 临时文件
TMP_DIR="/tmp"
COUNT_FILE="${TMP_DIR}/cron-watcher-${SESSION_ID}-count"
LAST_REPORTED_FILE="${TMP_DIR}/cron-watcher-${SESSION_ID}-last-reported"

# ===== 配置 =====
CRON_INTERVAL=180        # cron 触发间隔（秒）
ORCHESTRATOR_TIMEOUT=3600 # orchestrator 最大运行时间（秒）
HEARTBEAT_TIMEOUT=600    # 心跳超时（秒）= orchestrator 挂掉检测窗口
MAX_RUNS=$(( (ORCHESTRATOR_TIMEOUT / CRON_INTERVAL) + 2 ))  # = 22

# ===== 辅助函数 =====
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2; }

safe_message() {
  local text="$1"
  message --text "${text}" 2>/dev/null || log "WARN: message failed (network?)"
}

cleanup() {
  rm -f "${COUNT_FILE}" "${LAST_REPORTED_FILE}"
}

# ===== 主逻辑 =====
log "Cron watcher started for session ${SESSION_ID}"

# --- 1. 检查 .completed ---
if [ -f "${STAGES_DIR}/.completed" ]; then
  log "Found .completed — sending final report"
  RESULT=$(cat "${STAGES_DIR}/.completed" 2>/dev/null || echo "完成但无法读取结果文件")
  safe_message "✅ **Solution Pro 已完成**\n\n${RESULT}"
  cron remove --label "${CRON_LABEL}" 2>/dev/null || true
  cleanup
  exit 0
fi

# --- 2. 检查目录存在性 ---
if [ ! -d "${STAGES_DIR}" ]; then
  log "ERROR: stages directory not found — ${STAGES_DIR}"
  safe_message "❌ 巡检员错误：stages 目录不存在 (${SESSION_ID})\n\nOrchestrator 可能未正确初始化。"
  cron remove --label "${CRON_LABEL}" 2>/dev/null || true
  cleanup
  exit 1
fi

# --- 3. 检查心跳超时 ---
if [ -f "${HEARTBEAT_FILE}" ]; then
  LAST_HEARTBEAT=$(stat -f %m "${HEARTBEAT_FILE}" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  ELAPSED=$(( NOW - LAST_HEARTBEAT ))
  if [ "${ELAPSED}" -gt "${HEARTBEAT_TIMEOUT}" ]; then
    log "Heartbeat timeout: ${ELAPSED}s > ${HEARTBEAT_TIMEOUT}s"
    safe_message "⚠️ **Solution Pro 心跳超时**\n\nOrchestrator 已 ${ELAPSED}s 无响应，可能已崩溃。\n\n请检查或重新启动任务。"
    cron remove --label "${CRON_LABEL}" 2>/dev/null || true
    cleanup
    exit 0
  fi
else
  log "No heartbeat file yet — orchestrator may still be initializing"
fi

# --- 4. 检查最大运行次数 ---
COUNT=$(cat "${COUNT_FILE}" 2>/dev/null || echo 0)
COUNT=$(( COUNT + 1 ))
echo "${COUNT}" > "${COUNT_FILE}"
log "Run count: ${COUNT}/${MAX_RUNS}"

if [ "${COUNT}" -gt "${MAX_RUNS}" ]; then
  log "Max runs exceeded: ${COUNT} > ${MAX_RUNS}"
  safe_message "🛑 **巡检员达到最大运行次数**\n\nOrchestrator 运行超过 $(( MAX_RUNS * CRON_INTERVAL / 60 )) 分钟。\n\n请检查任务状态或重新启动。"
  cron remove --label "${CRON_LABEL}" 2>/dev/null || true
  cleanup
  exit 0
fi

# --- 5. 扫描进度（含去重）---
STAGE_COUNT=$(find "${STAGES_DIR}" -name "*.json" -not -name ".completed" 2>/dev/null | wc -l | tr -d ' ')
LAST_REPORTED=$(cat "${LAST_REPORTED_FILE}" 2>/dev/null || echo "-1")

if [ "${STAGE_COUNT}" != "${LAST_REPORTED}" ]; then
  log "Stage count changed: ${LAST_REPORTED} → ${STAGE_COUNT}"
  
  # 获取最新阶段名
  LAST_STAGE=""
  if [ "${STAGE_COUNT}" -gt 0 ]; then
    LAST_STAGE=$(find "${STAGES_DIR}" -name "*.json" -not -name ".completed" 2>/dev/null | sort | tail -1 | xargs basename | sed 's/\.json$//')
  fi
  
  if [ "${STAGE_COUNT}" -eq 0 ]; then
    safe_message "⏳ **Solution Pro 等待中**\n\nOrchestrator 已启动，正在初始化第一阶段…"
  else
    safe_message "📊 **Solution Pro 进度更新**\n\n已完成阶段：${STAGE_COUNT}/10\n最新阶段：${LAST_STAGE}"
  fi
  
  echo "${STAGE_COUNT}" > "${LAST_REPORTED_FILE}"
else
  log "Stage count unchanged (${STAGE_COUNT}), skipping notification"
fi

log "Cron watcher completed (run ${COUNT}/${MAX_RUNS})"
exit 0
```

---

## 七、主 Agent 集成伪代码

```python
# 主 Agent 中调用
import json, os, time

SESSION_ID = f"{int(time.time())}"
STAGES_DIR = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{SESSION_ID}/stages"
CRON_LABEL = f"solution-watcher-{SESSION_ID}"

# 1. 创建目录结构
os.makedirs(STAGES_DIR, exist_ok=True)

# 2. 注册 cron watcher
exec(f"cron_add --label '{CRON_LABEL}' --interval 180 "
     f"--command 'bash /path/to/cron-watcher.sh {SESSION_ID}'")

# 3. 注册兜底清理（收到 orchestrator announce 后执行）
#    这需要主 Agent 在 announce handler 中做：
#    exec(f"cron remove --label '{CRON_LABEL}'")
#    exec(f"rm -f /tmp/cron-watcher-{SESSION_ID}-*")

# 4. Spawn orchestrator
sessions_spawn(
    task=(
        f"执行 Solution Pro 管线。\n"
        f"每完成一个阶段，写入 {STAGES_DIR}/N.json。\n"
        f"每写完一个阶段，更新 {STAGES_DIR[:-8]}/.heartbeat 文件（写入当前时间戳）。\n"
        f"全部完成后，写入 {STAGES_DIR}/.completed 文件。\n"
        f"SESSION_ID: {SESSION_ID}"
    ),
    runTimeoutSeconds=3600,
)

# 5. Yield
sessions_yield()
```

**兜底清理**（主 Agent 收到 announce 后）：

```python
# announce handler 中：
exec(f"cron remove --label '{CRON_LABEL}' 2>/dev/null || true")
exec(f"rm -f /tmp/cron-watcher-{SESSION_ID}-*")
```

---

## 八、风险总结与建议

### 8.1 高风险项

| # | 风险 | 严重度 | 建议 |
|---|------|--------|------|
| R1 | 心跳机制依赖 orchestrator 配合 | 高 | 必须在 orchestrator prompt 中强调 .heartbeat 写入 |
| R2 | Gateway 重启后 cron 丢失 | 高 | 需要 .task_state.json 持久化 + 恢复逻辑 |
| R3 | orchestrator 崩溃无 announce | 高 | 依赖心跳超时检测（600s 延迟） |
| R4 | 主 Agent 兜底清理失败 | 中 | cron 自杀机制作为兜底 |

### 8.2 低风险评估

| # | 风险 | 严重度 | 说明 |
|---|------|--------|------|
| R5 | 计数器文件竞争 | 低 | cron 串行触发，无竞争 |
| R6 | 消息重复 | 低 | 去重机制已解决 |
| R7 | cron 脚本语法错误 | 低 | 首次运行前验证 |

### 8.3 最终建议

**方案可行，但建议优先考虑方案 F（Python 确定性编排）**，原因：

1. **现有代码已有进度可见性**：`PipelineOrchestrator` 在 exec 中同步运行，`print()` 输出实时进度到 stdout
2. **无需分布式状态管理**：cron watcher 本质是一个分布式状态机，需要在 cron session、orchestrator session、主 Agent 之间精确对齐
3. **Gateway 重启场景**：cron 任务不持久化，需要额外设计恢复逻辑
4. **Orchestrator 崩溃检测延迟**：600 秒的心跳超时意味着用户要等 10 分钟才知道出了问题

**如果必须用 cron watcher 方案**（例如 orchestrator 必须是 LLM 子 Agent），本文档提供了完整的退出机制、状态机和失败场景应对。核心要点：

1. ✅ **心跳文件** — 最关键的检测机制
2. ✅ **最大运行次数** — 防止无限运行
3. ✅ **消息去重** — 避免骚扰用户
4. ✅ **主 Agent 兜底清理** — 最可靠的退出路径
5. ⚠️ **Gateway 重启恢复** — 需要额外设计

---

## 九、附录：决策树

```
cron 触发
  │
  ├─ .completed 存在？
  │   ├─ 是 → 最终报告 → cron remove → ✅ 正常退出
  │   └─ 否 ↓
  │
  ├─ stages/ 存在？
  │   ├─ 否 → 错误告警 → cron remove → ❌ 异常退出
  │   └─ 是 ↓
  │
  ├─ .heartbeat 存在？
  │   ├─ 否 → 跳过心跳检查（首次运行）↓
  │   └─ 是 → 检查 mtime
  │       ├─ 超时？→ 告警 → cron remove → ❌ 超时退出
  │       └─ 未超时 ↓
  │
  ├─ 运行次数 > MAX_RUNS？
  │   ├─ 是 → 告警 → cron remove → ❌ 超限退出
  │   └─ 否 ↓
  │
  └─ 扫描阶段数
      ├─ 变化？→ message 报告进度 → ✅ 继续
      └─ 未变？→ 跳过 → ✅ 继续
```

---

*评审完成 | 2026-06-01*
