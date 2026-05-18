# DeepFlow 完整架构流程（2026-05-16 重构版）

> **目标**：一个文档说清楚所有关键设计，不再丢失上下文。

---

## 一、整体架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户交互层                                  │
│  浏览器 (localhost:17788) ←→ React 前端                           │
│  提交任务：domain / topic / solution_type / constraints           │
└──────────────────────┬───────────────────────────────────────────┘
                       │ POST /api/v2/tasks
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI 后端 (17789)                       │
│  routers/tasks_v2.py: 创建任务 → SQLite (pending)                │
│  → 后台发送 Webhook → Gateway /hooks/wake (fire-and-forget)     │
│  routers/consumer.py: 线程轮询 pending（冗余兜底）                 │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway (18789)                       │
│  Webhook 触发 → Main Agent session (systemEvent)                  │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Cron Job (每 2 分钟)                            │
│  session: main, systemEvent → Main Agent                         │
│  Step 1: nc 检查后端存活                                          │
│  Step 2: 读 SQLite pending                                        │
│  Step 3: sessions_spawn → DeepFlow Orchestrator                  │
│  Step 4: 更新 SQLite → running/completed                         │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    DeepFlow 管线层                                 │
│                                                                  │
│  Solution Pro:                                                   │
│    SolutionOrchestratorV21.run(topic, spawn_fn=sessions_spawn)   │
│    → EntryHarness → PipelineOrchestrator → Workers               │
│    → 结果写入 blackboard/{session_id}/                            │
│                                                                  │
│  Investment:                                                     │
│    InvestmentOrchestrator(spawn_fn=sessions_spawn).run(context)  │
│    → DataManager → Planner → Researchers → Auditors → ...        │
│    → 结果写入 blackboard/{session_id}/                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、三层架构（OpenClaw 平台层）

```
depth-0: Main Agent（有 sessions_spawn 工具）
  ↓ sessions_spawn
depth-1: Orchestrator Agent（在 Agent Run 环境，继承 sessions_spawn）
  ↓ sessions_spawn（注入的 spawn_fn）
depth-2: Workers（Planner/Researcher/Auditor/...）
```

**关键规则**：
- ✅ 每一层必须有 `spawn_fn` 注入（`__init__(self, spawn_fn=None)`）
- ❌ 禁止 `from openclaw import sessions_spawn`（在 exec 环境永远失败）
- ✅ 子 Agent 在 Agent Run 环境里 `from openclaw import sessions_spawn` 可用

---

## 三、标准执行路径

### 3.1 Solution Pro（已验证）

**入口**：`domains/solution/orchestrator_agent.py` → `SolutionOrchestratorV21.run()`

```python
# 主 Agent 调用方式：
import asyncio
from domains.solution.orchestrator_agent import SolutionOrchestratorV21

result = asyncio.run(SolutionOrchestratorV21.run(
    topic='设计智能仓库升级方案',
    solution_type='architecture',
    constraints=['预算 500 万', '6 个月完成'],
    stakeholders=['技术团队', 'CFO'],
    spawn_fn=sessions_spawn,  # ← 注入！
    session_prefix='smart-warehouse'
))
```

**内部流程**：
```
SolutionOrchestratorV21.run()
  → EntryHarness.validate_and_start(domain='solution', context, spawn_fn)
    → PipelineOrchestrator.run_pipeline()
      → Stage 1: Data Collection (spawn)
      → Stage 2: Planning (spawn)
      → Stage 3: Reviewers ×3 (并行 spawn)
      → Stage 4: Researchers ×N (并行 spawn)
      → Stage 5: Consolidator (spawn)
      → Stage 6: Auditors ×3 (并行 spawn)
      → Stage 7: Fixer (spawn)
      → Stage 8: Harness Final (spawn)
      → Stage 9: Summarizer (spawn)
  → 结果写入 blackboard/{session_id}/
```

### 3.2 Investment Analysis（已验证）

**入口**：`domains/investment/__init__.py` → `InvestmentOrchestrator.run()`

```python
from domains.investment import InvestmentOrchestrator

orch = InvestmentOrchestrator(spawn_fn=sessions_spawn)  # ← 注入！
result = orch.run({
    'code': '688652.SH',
    'name': '京仪装备',
    'analysis_type': 'value'
})
```

### 3.3 Unified Entry（统一入口）

**入口**：`core/unified_entry.py` → `run(domain, spawn_fn, **context)`

```python
from core.unified_entry import run

# Solution
result = run('solution', spawn_fn=sessions_spawn,
             topic='设计智能仓库', solution_type='architecture')

# Investment
result = run('investment', spawn_fn=sessions_spawn,
             code='688652.SH', name='京仪装备')
```

---

## 四、任务队列与自动触发

### 4.1 任务生命周期

```
前端提交 → SQLite (status=pending)
           ↓
     Webhook → Gateway /hooks/wake (fire-and-forget)
           ↓
     Cron Job (每 2 分钟，main session)
           ↓
     读 SQLite → 有 pending → sessions_spawn → DeepFlow
           ↓
     更新 SQLite → running → completed/failed
           ↓
     Blackboard 更新 → 前端 ProgressPage 轮询显示
```

### 4.2 Cron Job 设计

| 属性 | 值 |
|:---|:---|
| 名称 | DeepFlow Task Processor |
| 频率 | 每 2 分钟 |
| Session | main |
| 触发方式 | systemEvent |
| 端口检查 | nc -z -w 1 127.0.0.1 17789 |
| 前端关闭时 | nc 失败 → NO_REPLY（0 token） |

### 4.3 Cron 执行步骤

```
Step 1: nc -z -w 1 127.0.0.1 17789 → 失败则 NO_REPLY
Step 2: 读 SQLite pending → 无则 NO_REPLY
Step 3: 对每个 pending，sessions_spawn → DeepFlow Orchestrator
        - solution: SolutionOrchestratorV21.run(topic, spawn_fn=sessions_spawn)
        - investment: InvestmentOrchestrator(spawn_fn=sessions_spawn).run(context)
Step 4: 更新 SQLite 状态
Step 5: 报告结果（有任务时才回复）
```

**红线**：
- ❌ 禁止 `from openclaw import`（在 exec 环境）
- ❌ 禁止调用 `webhook_task_processor.py`（exec 环境会 fallback 到 CLI）
- ❌ 禁止在 exec 中 import openclaw

### 4.4 webhook_task_processor.py 的角色

**当前状态**：代码存在但**不被 Cron 使用**。

**原始设计**：Main Agent 收到 Webhook 后调用 `process_pending_tasks()`。
**实际问题**：在 exec 环境中 `_resolve_spawn_fn()` 会 fallback 到 CLI 模式（`openclaw agent --agent main`），这会导致无限递归。

**当前方案**：Cron 直接让 Main Agent 用 `sessions_spawn` 工具 spawn Orchestrator，不经过 `webhook_task_processor.py`。

---

## 五、配置化

### 5.1 config.json

```json
{
  "backend": { "host": "127.0.0.1", "port": 17789 },
  "frontend": { "host": "127.0.0.1", "port": 17788 },
  "cron": { "interval": "2m", "timeout_seconds": 1800 },
  "paths": {
    "blackboard": "blackboard",
    "database": "frontend/backend/data/tasks.db",
    "task_queue": "frontend/task_queue"
  },
  "webhook": {
    "url": "http://127.0.0.1:18789/hooks/wake",
    "env_file": "~/.openclaw/.webhook_env"
  }
}
```

### 5.2 配置加载

- 后端：`core/app_config.py` → `load_config()`, `resolve_path()`
- 前端：`vite.config.ts` 端口从 3000 → 17788
- 前端 API：`api/client.ts` 从 8000 → 17789
- **所有模块零硬编码端口**

### 5.3 跨平台支持

| 方案 | macOS | Linux | Windows |
|:---|:---|:---|:---|
| 端口探测 (socket) | ✅ | ✅ | ✅ |
| 系统 crontab | ✅ | ✅ | ❌ |
| OpenClaw Cron Job | ✅ | ✅ | ✅ |

**选择 OpenClaw Cron Job** = 跨平台 + 端口探测 = 前端关闭时 0 token。

---

## 六、已验证案例

| 日期 | 领域 | 案例 | 状态 |
|:---|:---|:---|:---|
| 2026-04-21 | investment | 京仪装备 688652.SH | ✅ 完整管线执行通过 |
| 2026-04-12 | solution | 代码质量审查 | ✅ 2 轮迭代 78→93 分 |
| 2026-05-15 | webhook | 前端提交 → SQLite | ✅ 任务入队 |
| 2026-05-15 | webhook | SQLite → Gateway 200 | ✅ Webhook 成功 |

**未验证**：Cron → sessions_spawn → DeepFlow 执行 → Blackboard 回写 → 前端展示

---

## 七、历史教训索引

| 教训 | 记忆锚点 | 详见 |
|:---|:---|:---|
| exec 无 openclaw | exec 无 openclaw，有 import 就失败 | AGENTS.md / SOUL.md |
| spawn_fn 注入是正道 | 主Agent用工具，Orchestrator收注入 | AGENTS.md |
| V2.5 是菜谱我是厨师 | 主Agent spawn才有SDK，子Agent跑代码=mock | MEMORY.md |
| 修复必验证 | 声称≠完成 | AGENTS.md |
| yield等推送别轮询 | sessions_yield() 静默等待 | AGENTS.md |
| 架构设计是宪法 | bug是违宪，修复是修宪，绕过是政变 | AGENTS.md |

---

## 八、下一步

1. **启动前端**（17788 + 17789）
2. **提交测试任务**
3. **验证 Cron 自动处理**
4. **验证 Blackboard 回写 → 前端展示**
