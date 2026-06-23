# Solution Pro 架构说明

> **版本**: V4.1  
> **最后更新**: 2026-06-01  
> **状态**: 生产就绪

---

## 1. 整体架构

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  主 Agent (Main)                                             │
│  - 启动 Orchestrator                                         │
│  - 创建 Cron Watcher                                         │
│  - 兜底清理                                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator (Sub-Agent, depth=1)                          │
│  - 读取 execution_plan.json                                  │
│  - 按顺序 spawn workers (depth=2)                            │
│  - 写入 stages/*.json                                        │
│  - 写入 .completed                                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Workers (Sub-Sub-Agents, depth=2)                          │
│  - 执行具体阶段任务                                          │
│  - 写入输出文件                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Cron Watcher (Isolated Cron, 独立 Session)                 │
│  - 每 3 分钟巡检                                             │
│  - 扫描 stages/*.json                                        │
│  - 有新阶段 → message 通知用户                               │
│  - 检测 .completed → 发最终报告 → 自杀                       │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

| 原则 | 说明 | 实现方式 |
|------|------|----------|
| **文件即状态** | 所有状态通过文件系统传递 | `stages/*.json`、`.completed`、`.cron_run_count` |
| **职责分离** | Orchestrator 专注执行，Cron 专注通知 | 两个独立 Agent，互不干扰 |
| **三层退出** | 确保 Cron 一定会退出 | 正常退出 + 超时退出 + 兜底清理 |
| **主 Agent 不阻塞** | 主 Agent yield 后可处理其他请求 | Orchestrator 异步运行 |

---

## 2. 10 阶段管线

| 阶段 | 类型 | Worker | 输出文件 |
|------|------|--------|----------|
| 1 | 串行 | data_collection | `data/collection.json` |
| 2 | 串行 | planning | `stages/planning.json` |
| 3 | 并行×3 | reviewer_technical<br>reviewer_business<br>reviewer_risk | `stages/reviewer_*.json` |
| 4 | 并行×3 | research_expert_1<br>research_expert_2<br>research_expert_3 | `stages/research_expert_*.json` |
| 5 | 串行 | consolidator | `stages/consolidator.json` |
| 6 | 串行 | audit | `stages/audit.json` |
| 7 | 串行 | fix | `stages/fix.json` |
| 8 | 串行 | fixer_expert | `stages/fixer_expert.json` |
| 9 | 串行 | harness_final | `stages/harness_final.json` |
| 10 | 串行 | summarizer | `stages/final_solution.md` |

---

## 3. Cron 巡检机制

### 3.1 工作流程

```
主 Agent
  │
  ├─ 1. 清理旧状态文件（.completed, .cron_job_id 等）
  ├─ 2. 生成 execution_plan.json + tasks.json
  ├─ 3. spawn orchestrator（异步，不等待）
  ├─ 4. 创建 Cron Watcher（每 3 分钟）
  ├─ 5. 记录 cron_job_id 到 .cron_job_id
  └─ 6. yield（等待 orchestrator announce）

Orchestrator
  │
  ├─ 读取 tasks.json
  ├─ 按顺序执行 10 阶段
  │   ├─ spawn workers
  │   ├─ 等待 workers 完成
  │   └─ workers 写入 stages/*.json
  ├─ 写入 .completed（status=completed/partial/failed）
  └─ announce 回主 Agent

Cron Watcher（每 3 分钟触发）
  │
  ├─ Step 1: 更新 .cron_run_count（count++）
  │   └─ 如果 count > 20 → 超时退出 → 自杀
  │
  ├─ Step 2: 检查 .completed 是否存在
  │   └─ 如果存在 → 发最终报告 → 自杀
  │
  ├─ Step 3: 扫描 stages/*.json
  │   ├─ 对比 .notified_stages.json
  │   ├─ 找出新文件
  │   ├─ 如果有新文件 → 发进度通知
  │   └─ 更新 .notified_stages.json
  │
  └─ Step 4: 没有新文件 → NO_REPLY（不发通知）

主 Agent（收到 orchestrator announce）
  │
  ├─ 读取 .cron_job_id
  ├─ cron remove（兜底清理）
  ├─ 清理状态文件（.cron_job_id, .cron_run_count, .notified_stages.json）
  ├─ 更新 tasks 数据库（status=completed）
  └─ 向用户报告最终结果
```

### 3.2 三层退出机制

| 层级 | 触发条件 | 行为 | 负责方 |
|------|----------|------|--------|
| **第一层：正常退出** | Cron 检测到 `.completed` | 发最终报告 → `cron remove` 自杀 | Cron Watcher |
| **第二层：超时退出** | Cron 运行次数 > 20（60 分钟） | 发超时告警 → `cron remove` 自杀 | Cron Watcher |
| **第三层：兜底清理** | 主 Agent 收到 orchestrator announce | `cron remove` + 清理状态文件 | 主 Agent |

**为什么需要三层？**

- **第一层**：Cron 自己检测到完成，最理想的情况
- **第二层**：Orchestrator 崩溃了，`.completed` 永远不会出现，Cron 不能无限运行
- **第三层**：前两层都失败了（比如 Cron 自杀失败），主 Agent 兜底清理

### 3.3 消息策略

| 场景 | 消息内容 | 频率 |
|------|----------|------|
| **进度通知** | "📊 方案设计进度 (3/10)\n✅ Data Collection\n✅ Planning\n✅ Reviewers\n⏳ Research 运行中..." | 有新阶段时才发（最多 10 条） |
| **完成通知** | "✅ 方案设计完成！\n📊 共 10/10 阶段完成\n📄 final_solution.md 已生成" | 只发 1 次 |
| **超时告警** | "⚠️ DeepFlow 管线运行超时（已运行 60 分钟）\norchestrator 可能已崩溃" | 只发 1 次 |
| **NO_REPLY** | （不发任何消息） | 没有新阶段时 |

**关键**: 不是每 3 分钟都发消息，而是**只在有新阶段完成时**才发。

### 3.4 状态文件

| 文件 | 创建者 | 用途 | 清理时机 |
|------|--------|------|----------|
| `.completed` | Orchestrator | 标记任务完成 | 新运行开始前清理 |
| `.cron_job_id` | 主 Agent | 记录 Cron Job ID | 主 Agent 兜底清理时删除 |
| `.cron_run_count` | Cron | 记录运行次数（超时保护） | 新运行开始前清理 |
| `.notified_stages.json` | Cron | 记录已通知的阶段（去重用） | 新运行开始前清理 |
| `.send_failures.json` | Cron | 记录消息发送失败（可选） | 新运行开始前清理 |
| `stages/*.json` | Workers | 各阶段输出文件 | 保留（用户需要查看） |

---

## 4. 文件目录结构

```
blackboard/{session_id}/
├── execution_plan.json          # 执行计划（Orchestrator 读取）
├── tasks.json                   # 任务配置（Orchestrator 读取）
│
├── data/
│   └── collection.json          # 阶段 1 输出
│
├── stages/
│   ├── planning.json            # 阶段 2 输出
│   ├── reviewer_technical.json  # 阶段 3 输出
│   ├── reviewer_business.json   # 阶段 3 输出
│   ├── reviewer_risk.json       # 阶段 3 输出
│   ├── research_expert_1.json   # 阶段 4 输出
│   ├── research_expert_2.json   # 阶段 4 输出
│   ├── research_expert_3.json   # 阶段 4 输出
│   ├── consolidator.json        # 阶段 5 输出
│   ├── audit.json               # 阶段 6 输出
│   ├── fix.json                 # 阶段 7 输出
│   ├── fixer_expert.json        # 阶段 8 输出
│   ├── harness_final.json       # 阶段 9 输出
│   └── final_solution.md        # 阶段 10 输出（最终方案）
│
├── .completed                   # Orchestrator 写入（完成标记）
├── .cron_job_id                 # 主 Agent 写入（Cron Job ID）
├── .cron_run_count              # Cron 写入（运行次数）
├── .notified_stages.json        # Cron 写入（已通知阶段）
└── .send_failures.json          # Cron 写入（可选，发送失败记录）
```

---

## 5. 错误处理

### 5.1 Orchestrator 崩溃

**现象**: Orchestrator 运行中崩溃，`.completed` 永远不会出现。

**处理流程**:
1. Cron 继续每 3 分钟巡检
2. 运行次数递增（`.cron_run_count`）
3. 当 count > 20（60 分钟）→ 触发第二层退出
4. Cron 发送超时告警 → 自杀
5. 用户收到告警，知道任务可能失败了
6. 用户可查看 `stages/` 目录，了解已完成的阶段

### 5.2 Cron 消息发送失败

**现象**: Cron 尝试发 message 但失败（网络问题、API 限流等）。

**处理流程**:
1. Cron 记录失败到 `.send_failures.json`
2. 下次运行时重试
3. 如果连续失败 5 次 → 发告警 → 自杀
4. 用户收到告警，知道通知机制失败了

### 5.3 用户中途取消

**现象**: 用户主动取消任务，Orchestrator 被杀死。

**处理流程**:
1. 主 Agent 收到用户取消指令
2. 读取 `.cron_job_id`
3. `cron remove` 删除 Cron Job
4. 清理状态文件
5. 通知用户"任务已取消"

---

## 6. 性能优化

### 6.1 并行阶段

**阶段 3（Reviewers）和阶段 4（Researchers）是并行的**：

```
Orchestrator
  │
  ├─ spawn reviewer_technical
  ├─ spawn reviewer_business
  ├─ spawn reviewer_risk
  │  （3 个 workers 并行运行）
  │
  └─ yield 等待全部完成
```

**优势**: 3 个 reviewers 同时运行，总时间 = max(3 个 worker 时间) 而非 sum。

### 6.2 智能通知

**Cron 不是每 3 分钟都发通知**：

```
Cron 触发
  │
  ├─ 扫描 stages/*.json
  ├─ 对比 .notified_stages.json
  ├─ 找出新文件
  │
  ├─ 如果有新文件 → 发通知（有新阶段完成）
  └─ 如果没有新文件 → NO_REPLY（不打扰用户）
```

**优势**: 避免消息轰炸，用户只在有新进展时收到通知。

---

## 7. 已知限制

### 7.1 Sub-Agent 工具限制

**问题**: Orchestrator（depth=1）没有 `sessions_send` 和 `message` 工具，无法主动通知主 Agent。

**解决方案**: 使用 Cron Watcher 作为独立的观察者，定期扫描文件系统。

### 7.2 文件系统依赖

**问题**: 所有状态通过文件系统传递，如果文件损坏或丢失会导致状态不一致。

**缓解措施**:
- Cron 增加时间戳校验（待实施）
- 使用 run_id 区分不同运行（待实施）

### 7.3 长时间任务

**问题**: 10 阶段管线可能需要 30-60 分钟，用户等待时间长。

**缓解措施**:
- Cron 每 3 分钟发送进度通知
- 超时保护（60 分钟后自动告警）

---

## 8. 相关文档

- `domains/solution_pro/SKILL.md` - 主 Agent 执行指南
- `domains/solution_pro/prompts/pipeline_orchestrator_v4.md` - Orchestrator Prompt
- `domains/solution_pro/prompts/cron_watcher.md` - Cron Watcher Prompt
- `core/orchestrator/completion_handler.py` - 完成处理脚本
- `docs/CRON_EARLY_EXIT_POSTMORTEM.md` - Cron 提前退出问题复盘
- `docs/CRON_DESIGN.md` - Cron 设计文档（专家评审报告）

---

**文档版本**: V4.1  
**作者**: 小满 🦞  
**审核**: 忠礼  
**最后更新**: 2026-06-01
