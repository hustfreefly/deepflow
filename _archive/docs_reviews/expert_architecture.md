# 架构专家评审：Sub-Agent 中间通知方案

> **日期**: 2026-06-01
> **评审对象**: DeepFlow Solution Pro 10 阶段管线进度通知
> **评审深度**: 结合 OpenClaw 实际限制 + 现有代码架构

---

## 方案评估

| 方案 | 可行性 | 实时性 | 复杂度 | 推荐度 |
|------|--------|--------|--------|--------|
| A: orchestrator 用 sessions_send | ❌ 不可行 | N/A | N/A | ⭐ 0/5 |
| B: 主 Agent 定时轮询 blackboard | ⚠️ 有限可行 | 低（2min延迟） | 高 | ⭐ 1/5 |
| C: 主 Agent 不 yield，exec 轮询 | ⚠️ 有限可行 | 中 | 极高 | ⭐ 1/5 |
| D: 利用 announce 机制（串行化） | ✅ 可行 | 低（阶段串行） | 低 | ⭐ 2/5 |
| E: 中间层 watcher agent | ❌ 不可行 | 低 | 高 | ⭐ 0/5 |
| **F: Python 确定性编排（现有架构）** | ✅ 可行 | **高** | **低** | ⭐⭐⭐ **5/5** |
| **G: 增强型 LLM orchestrator（文件信号）** | ✅ 可行 | 中 | 中 | ⭐⭐⭐⭐ 4/5 |

---

## 核心发现：现有架构已解决此问题

评审代码后发现，**当前代码库中存在两套并行的执行路径**，其中一套天然具备进度可见性：

### 路径 1：Python 确定性编排（`domains/solution_pro/__init__.py` → `run_solution_pro()`）

```
主 Agent exec
  └── run_solution_pro(topic, spawn_fn=sessions_spawn)
        └── _SolutionDispatcher.run_harness_v2(spawn_fn)
              └── PipelineOrchestrator.run_pipeline()   ← Python 同步执行
                    → _execute_serial() / _execute_parallel()
                    → _wait_for_worker()（文件轮询）
                    → spawn workers (depth-2)
                    → print() 实时输出到 exec stdout
```

**关键特征**：
- `PipelineOrchestrator` 在主 Agent 的 **exec 进程**中同步运行
- `sessions_yield` 不存在于 exec 环境中 — 不需要 yield
- 每个阶段完成后 `print()` 输出进度到 stdout，主 Agent 可以实时读取
- Worker 使用 `spawn_fn` 注入机制 spawn，不依赖子 Agent 的消息能力
- **天然具备进度可见性**，无需额外设计

### 路径 2：LLM 子 Agent 编排（`SKILL.md` Step 2）

```
主 Agent
  └── sessions_spawn(orchestrator) → sessions_yield()  ← 阻塞等待全部完成
        └── orchestrator sub-agent
              └── sessions_spawn(worker) → sessions_yield()
```

**关键特征**：
- orchestrator 是 depth-1 子 Agent，**没有** `sessions_send` / `message` 工具
- 主 Agent 调用 `sessions_yield()` 后完全阻塞，直到 orchestrator 完成
- **进度不可见** — 这正是本文要解决的问题

### 问题根源

SKILL.md 中 Step 2（LLM 子 Agent 编排）是**路径 1 的退化版本**，引入了子 Agent 的工具限制却不带来任何收益。真正需要子 Agent 编排的场景是当编排逻辑本身需要 LLM 决策（如动态调整阶段顺序），但 Solution Pro 的阶段顺序是 `execution_plan.json` 确定的，不需要 LLM 决策。

---

## 推荐方案：F — 强化现有 Python 确定性编排

### 详细说明

**不使用 LLM orchestrator 子 Agent，直接在主 Agent exec 中运行 `run_solution_pro()`**。

这是现有代码已经支持的路径（`domains/solution_pro/__init__.py` 中的 `run_solution_pro()` 函数），只需在调用方式上做两处增强：

#### 1. 调用方式（主 Agent）

```python
import sys, json
sys.path.insert(0, "/Users/allen/.openclaw/workspace/.deepflow")
from domains.solution import run_solution_pro

result = run_solution_pro(
    topic="{TOPIC}",
    solution_type="{SOLUTION_TYPE}", 
    constraints={CONSTRAINTS},
    stakeholders={STAKEHOLDERS},
    spawn_fn=sessions_spawn,  # ← 关键：在 exec 中通过注入传递
)
print(json.dumps(result, ensure_ascii=False))
```

**注意**：`sessions_spawn` 在主 Agent 的 exec 环境中是**可用的**（通过 OpenClaw 的 exec 工具注入机制）。这与 LLM sub-agent 不同 — exec 环境是主 Agent 进程的延伸。

#### 2. 进度输出增强（PipelineOrchestrator 修改）

在 `pipeline_orchestrator.py` 的 `run_pipeline()` 方法中，每完成一个阶段输出结构化进度：

```python
# 在 for phase 循环的末尾（phase 完成后）
progress_msg = {
    "type": "stage_progress",
    "session_id": self.session_id,
    "stage_completed": phase_num,
    "stages_total": len(phases),
    "stage_name": stage_name,
    "status": "completed" if status == "completed" else "partial",
    "workers_completed": self.progress["workers_completed"],
    "workers_failed": self.progress["workers_failed"],
    "elapsed_phases": self.progress["phases_completed"],
}
print(f"[DEEPFLOW_PROGRESS] {json.dumps(progress_msg, ensure_ascii=False)}")
```

主 Agent 的 exec 输出会包含这些 `[DEEPFLOW_PROGRESS]` 标记行，可以被主 Agent 解析后推送给用户。

#### 3. 用户端进度展示格式

```
📊 方案设计进度 [session_id]
━━━━━━━━━━━━━━━━━━━━
✅ Data Collection          (1/10)  00:45
✅ Planning                 (2/10)  01:20
⏳ Reviewers (3并行)         (3/10)  运行中...
⬜ Research
⬜ Consolidator
⬜ Audit
⬜ Fix
⬜ Fixer Expert
⬜ Harness Final
⬜ Summarizer

已耗时: 03:15 | 预计剩余: 25:00
```

### 实现修改清单

| 文件 | 修改内容 | 复杂度 |
|------|---------|--------|
| `core/orchestrator/pipeline_orchestrator.py` | `run_pipeline()` 中每阶段完成后输出 `[DEEPFLOW_PROGRESS]` 行 | 低（~10行） |
| `domains/solution_pro/SKILL.md` | 将 Step 1（Python 方式）标注为**推荐路径**，Step 2 标注为**备选** | 低（文档） |
| `domains/solution_pro/progress_tracker.py` | 已有模块，与 pipeline_orchestrator 集成输出 | 低（已有代码） |

---

## 为什么选方案 F

### 1. 零架构变更

方案 F **不是新方案**，是现有代码已经支持的路径。`run_solution_pro(spawn_fn=sessions_spawn)` 已完整实现了 Python 确定性编排，只是 SKILL.md 中把它放在了 Step 1，Step 2 的 LLM orchestrator 方式反而成了更受关注的路径。

### 2. 规避所有 sub-agent 工具限制

```
Python 编排 (exec)          LLM orchestrator (sub-agent)
────────────────────────    ────────────────────────────────
sessions_spawn ✅            sessions_spawn ✅
sessions_yield ❌ (不需要)   sessions_yield ✅ (必须用)
sessions_send ✅ (主Agent)   sessions_send ❌ (不可用)
message 工具 ❌ (不需要)     message 工具 ❌ (不可用)
print() 进度输出 ✅          无中间通知机制 ❌
同步执行，自然等待 ✅        yield 阻塞，完全盲等 ❌
```

### 3. 保持并行能力

`PipelineOrchestrator._execute_parallel()` 已实现并行 spawn 多 worker + 统一等待（文件轮询），并行阶段（Reviewers ×3, Research ×3, Audit ×3）不受影响。

### 4. 实现复杂度极低

只需在 `pipeline_orchestrator.py` 的 `run_pipeline()` 循环中添加 `print()` 输出，约 10 行代码。

---

## 备选方案：G — 增强型 LLM orchestrator（文件信号）

**适用场景**：如果确实需要 LLM orchestrator（例如编排逻辑需要动态决策阶段顺序）。

### 设计

```
主 Agent
  ├── sessions_spawn(orchestrator)
  └── exec 循环轮询 blackboard/progress.json
        └── 发现更新 → 解析 → 推送用户

orchestrator sub-agent
  ├── 每阶段完成后 exec 写 progress.json
  ├── sessions_spawn(worker)
  └── sessions_yield() 等待完成
```

### 关键设计点

1. **orchestrator 写进度文件**（不用 sessions_send）：
   ```python
   # orchestrator 在每个阶段完成后执行：
   import json, time
   progress = {"stage": 3, "stage_name": "Reviewers", "status": "completed", "ts": "..."}
   with open(".../progress.json", "w") as f:
       json.dump(progress, f)
   ```

2. **主 Agent 轮询 + 推送**：
   ```python
   # 主 Agent spawn orchestrator 后：
   last_stage = 0
   while True:
       # 读 progress.json，对比 last_stage
       # 有更新 → 推送用户
       # 检测到 done marker → break
       time.sleep(15)  # 15秒轮询间隔
   ```

3. **问题**：主 Agent 在 exec 循环中仍然阻塞，无法同时处理用户其他请求。但至少有进度输出。

### 为什么不如方案 F

- 需要 LLM orchestrator 在每个阶段后正确写文件（可靠性低于 Python 的 `print()`）
- 主 Agent 需要额外轮询逻辑
- 增加了一层不确定性（LLM 可能忘记写进度文件）
- 延迟更高（轮询间隔 vs 即时 print）

---

## 各候选方案详细分析

### 方案 A：orchestrator 用 sessions_send — ❌ 不可行

- OpenClaw 文档明确 "sub-agents do not get session tools by default"
- 即使通过 `toolsAllow` 配置开放，也违背了 OpenClaw 的安全设计
- 子 Agent 向父 Agent 发任意消息可能引入循环调用风险
- **结论：此路不通，不需要进一步讨论**

### 方案 B：主 Agent 定时轮询 — ⚠️ 理论上可行，实际不推荐

**问题**：
- cron job 生命周期管理复杂（创建、监控、停止、清理）
- 如果 orchestrator 提前完成但 cron 还在跑 → 浪费资源
- 如果 orchestrator 失败但 cron 没检测到 → 用户永远等不到结果
- 延迟最多 2 分钟（轮询间隔）

### 方案 C：主 Agent 不 yield，exec 轮询 — ⚠️ 可行但糟糕

**问题**：
- 主 Agent 被绑定在轮询循环中，无法处理用户其他请求
- 本质上是把 LLM orchestrator 的 yield 阻塞换成了 exec 轮询阻塞
- 没有获得任何实质收益

### 方案 D：利用 announce 机制 — ✅ 可行但有代价

**分析**：
- announce 只在 sub-agent **完成时**触发，不是阶段性的
- 如果要让每个阶段都 announce，orchestrator 必须在每个阶段完成后 terminate 并重新 spawn
- 这完全破坏了管线连续性，实现复杂度远超收益
- **变种**：每个阶段一个独立的 sub-agent，主 Agent 按顺序 spawn → yield → spawn → yield
  - 可行，但失去并行能力（因为主 Agent 必须串行等待）
  - 总时间翻倍（并行阶段变串行）

### 方案 E：中间层 watcher agent — ❌ 不可行

**问题**：
- watcher 也是 sub-agent，同样没有 `sessions_send` 工具
- watcher 发现新文件后无法通知主 Agent
- 除非 watcher 也写文件，那主 Agent 为什么不直接轮询文件？
- **增加了一层没有解决任何问题的抽象**

---

## 风险

### 方案 F 的风险

| 风险 | 严重程度 | 缓解措施 |
|------|---------|---------|
| `sessions_spawn` 在 exec 中不可用 | 中 | 已验证：`domains/solution_pro/orchestrator_agent.py` 中的 `_resolve_spawn_fn()` 就是为此设计的 |
| 长时间 exec 运行超时 | 低 | 设置合理的 exec timeout（3600s），PipelineOrchestrator 本身有 per-worker 超时 |
| exec 输出被截断，进度行丢失 | 低 | 使用 `[DEEPFLOW_PROGRESS]` 标记，主 Agent 解析 stdout 时过滤 |
| 并行阶段的进度报告顺序不确定 | 低 | 只报告阶段完成（不是 worker 粒度），阶段完成是串行的 |

### 通用风险

| 风险 | 说明 |
|------|------|
| OpenClaw 版本升级改变 sub-agent 工具策略 | 方案 F 不依赖 sub-agent 工具，不受影响 |
| `progress_tracker.py` 与 `pipeline_orchestrator.py` 集成冲突 | 两者已存在，只需在 orchestrator 中调用 progress_tracker.update() |

---

## 总结

| 维度 | 方案 F（Python编排） | 方案 G（LLM+文件信号） |
|------|---------------------|----------------------|
| 可行性 | ✅ 已存在 | ⚠️ 需新建 |
| 实时性 | 即时（print） | 延迟（轮询15-30s） |
| 并行能力 | 完整保留 | 完整保留 |
| 实现复杂度 | ~10行 | ~50行 + 文档 |
| 可靠性 | 高（Python确定性） | 中（LLM可能遗漏写文件） |
| 主Agent阻塞 | 是（exec阻塞） | 是（exec轮询阻塞） |
| 可维护性 | 高 | 中 |

**最终推荐：方案 F** — 它不是新方案，而是**让现有架构发挥它本应有的能力**。SKILL.md 需要更新以明确 Step 1（Python 方式）为推荐路径，并在 `pipeline_orchestrator.py` 中添加结构化进度输出。
