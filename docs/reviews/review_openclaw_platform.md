# 评审报告：OpenClaw 平台专家

> **评审日期**: 2026-06-25  
> **评审对象**: Ship Pro AI Native 改造方案  
> **评审人**: OpenClaw 平台专家（Sub-agent）

---

## 总评

- **总评分**: 6.5/10
- **核心判断**: 方案方向正确（LLM 控制流 + Python I/O），但对 OpenClaw 平台能力的理解存在关键遗漏，尤其是 `cwd`/`PYTHONPATH` 这个已知踩坑点**在方案中完全没有体现**，有重蹈覆辙的风险。

---

## 逐维度评审

### 1. sessions_spawn 使用正确性 (5/10)

**发现的问题**：

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ❌ `spawn_params` 缺少 `cwd` | **P0** | `start_ship_pro.py` 第 166-172 行的 `spawn_params` 没有 `cwd` 参数。这是 **已知踩坑 #4**（2026-06-25 教训记录），11 个子 Agent 全部因此报 `ModuleNotFoundError`。 |
| ⚠️ Worker spawn 参数未定义 | **P1** | 方案 3.4 节只描述了 Orchestrator 的 prompt，没有明确 Worker 的 `sessions_spawn` 参数（cwd、PYTHONPATH、label 等）。 |
| ✅ Orchestrator 有 sessions_spawn | OK | Sub-agent 确实有 `sessions_spawn` 工具，方案假设正确。 |
| ✅ runtime/mode 参数正确 | OK | `runtime="subagent"`, `mode="run"` 使用正确。 |

**具体证据**：

```python
# start_ship_pro.py 第 166-172 行（当前实现）
spawn_params = {
    "runtime": "subagent",
    "mode": "run",
    "label": "ship-pro-orchestrator",
    "task": task,
    "runTimeoutSeconds": 1800
    # ❌ 缺少 "cwd": DEEPFLOW_HOME
}
```

**修复建议**：

```python
spawn_params = {
    "runtime": "subagent",
    "mode": "run",
    "label": "ship-pro-orchestrator",
    "task": task,
    "cwd": DEEPFLOW_HOME,  # ✅ 必须传 cwd
    "runTimeoutSeconds": 1800
}
```

**Worker spawn 也需要在 prompt 中明确**：

```python
# Orchestrator prompt 中应该要求：
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="ship-<agent_name>",
    task=<worker_task>,
    cwd="/Users/allen/.openclaw/workspace/.deepflow"  # ✅ 必须
)
```

---

### 2. sessions_yield 使用正确性 (7/10)

**发现的问题**：

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ✅ Orchestrator 可以 yield | OK | Sub-agent 有 `sessions_yield` 工具。 |
| ⚠️ Yield 后消息流未说明 | **P2** | 方案没有解释 Worker 完成后消息如何回来（auto-announce 机制）。 |
| ⚠️ 多层 yield 嵌套未验证 | **P2** | Main → Orchestrator → Worker 是 2 层嵌套 yield，需要确认 `maxSpawnDepth` 配置。 |

**消息流说明（方案应补充）**：

```
Main Agent
  ├── sessions_spawn(Orchestrator)
  └── sessions_yield() ← 等待 Orchestrator announce
        │
        Orchestrator (depth=1)
          ├── sessions_spawn(Worker)
          └── sessions_yield() ← 等待 Worker announce
                │
                Worker (depth=2)
                  └── 完成 → auto-announce → Orchestrator 收到
```

**建议**：在方案中补充一段说明 yield 的 push-based 机制，避免实现时误解。

---

### 3. cron 集成 (8/10)

**发现的问题**：

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ✅ Watcher 保持不变 | OK | 方案明确说 Watcher 不改，规避了风险。 |
| ✅ sessionTarget 使用 current | OK | `build_v3_cron_payload()` 已经正确处理。 |
| ⚠️ Cron 自杀机制依赖 .completed | **P2** | 如果 Orchestrator 崩溃没写 .completed，Watcher 会等到超时（30 分钟）。 |

**当前 Watcher 实现已验证**：
- `sessionTarget: "current"` ✅（不能用 "isolated"）
- `cron remove` 自杀 ✅
- 超时机制（max_runs=15）✅

**建议**：方案可以补充一个"兜底心跳"机制，比如 Orchestrator 每完成一个阶段写一个 `.heartbeat` 文件，Watcher 可以更早发现活跃状态。

---

### 4. exec 工具使用 (7/10)

**发现的问题**：

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ✅ Sub-agent 有 exec 工具 | OK | Orchestrator 和 Worker 都有 exec。 |
| ⚠️ io_helper.py 不存在 | **P1** | 方案提出创建 `io_helper.py`，但当前只有 `run_pipeline.py`。需要明确迁移计划。 |
| ✅ 路径解析正确 | OK | exec 命令中使用 `cd {DEEPFLOW_HOME} && PYTHONPATH=...` 是正确的。 |
| ⚠️ exec 环境无 openclaw 模块 | **P2** | 方案没有提醒：exec 中不能 `from openclaw import ...`，只能用 CLI。 |

**io_helper.py 迁移状态**：

| 当前 | 方案目标 | 状态 |
|------|---------|------|
| `run_pipeline.py` (1053 行) | 拆分为 `io_helper.py` (~200 行) | ❌ 未开始 |

**建议**：
1. 明确 `io_helper.py` 的创建是本次改造的前置任务
2. 在方案中补充：exec 环境中禁止 `from openclaw import ...`

---

### 5. 历史踩坑规避 (5/10)

**对照已知 5 个系统性问题**：

| # | 已知问题 | 方案是否规避 | 说明 |
|---|---------|-------------|------|
| 1 | ModuleNotFoundError | ❌ **未规避** | `spawn_params` 仍缺少 `cwd`，Worker spawn 也未要求 `cwd`。 |
| 2 | prompt 中想象 API | ⚠️ **部分规避** | 方案提出 `io_helper.py` 命令，但没有列出完整 API 清单，存在想象风险。 |
| 3 | list vs dict | ✅ **已规避** | 方案没有涉及 constraints 格式问题（由 Solution Pro 处理）。 |
| 4 | 缺 cwd | ❌ **未规避** | 同 #1，`spawn_params` 缺少 `cwd`。 |
| 5 | SKILL.md 入口守卫 | ⚠️ **未提及** | 方案提到更新 SKILL.md V5.0，但没有说明入口守卫如何设计。 |

**详细分析**：

**问题 #1 & #4（cwd 缺失）**：

这是 2026-06-25 刚修复的问题，教训已写入 MEMORY.md：
> "sessions_spawn 必须传 cwd,子 Agent 必须加 PYTHONPATH"

但方案的 `start_ship_pro.py` 代码中**仍然没有 cwd**！这说明方案是在修复之前写的，或者修复时没有同步更新方案。

**问题 #2（想象 API）**：

方案 3.3 节列出了 `io_helper.py` 的 7 个命令，但没有详细说明每个命令的参数和返回值。如果实现时 LLM 凭"理解"去调用，可能想象出不存在的参数。

**建议**：
1. 立即修复 `spawn_params` 添加 `cwd`
2. 为 `io_helper.py` 编写完整的 CLI 文档（argparse help）
3. SKILL.md V5.0 必须包含入口守卫（Step 0）

---

## 必须修改的问题（P0/P1）

| # | 严重度 | 问题 | 建议 |
|---|--------|------|------|
| 1 | **P0** | `spawn_params` 缺少 `cwd` | 在 `start_ship_pro.py` 第 166-172 行添加 `"cwd": DEEPFLOW_HOME` |
| 2 | **P0** | Worker spawn 未要求 `cwd` | 在 Orchestrator prompt 中明确要求 Worker spawn 必须传 `cwd` |
| 3 | **P1** | `io_helper.py` 不存在 | 明确创建计划，或先用 `run_pipeline.py` 代替 |
| 4 | **P1** | `io_helper.py` API 未完整定义 | 编写完整的 CLI 文档（每个命令的参数、返回值、示例） |
| 5 | **P1** | SKILL.md V5.0 缺少入口守卫设计 | 补充 Step 0（防偏检查）的具体内容 |

---

## 建议改进（P2）

1. **补充 yield 机制说明**：在方案中解释 push-based auto-announce 机制，避免实现时误解。

2. **补充 exec 环境约束**：明确说明 exec 中不能 `from openclaw import ...`，只能用 CLI。

3. **补充 maxSpawnDepth 检查**：Main → Orchestrator → Worker 是 2 层嵌套，确认配置足够。

4. **补充 Orchestrator 崩溃兜底**：如果 Orchestrator 中途崩溃，Watcher 如何更早发现？可以考虑 `.heartbeat` 文件。

5. **补充回滚验证**：方案提到"保留旧 run_pipeline.py"，但没有说明如何验证回滚是否成功。

---

## 亮点

1. **架构方向正确**：LLM 控制流 + Python I/O 的分层清晰，符合 AI Native 原则。

2. **迁移策略稳健**：不删旧的、新建并行的策略降低了风险。

3. **Watcher 保持不变**：明确说 Watcher 不改，避免了不必要的改动。

4. **decisions.jsonl 设计**：全量记录 LLM 决策，为未来 Dream Loop 提供数据，是好的前瞻性设计。

5. **与 Solution Pro 一致性表**：方案明确对比了两个域的设计要素一致性，便于维护。

---

## 总结

方案的核心思路（LLM 控制流 + Python I/O）是正确的，但在 **平台能力细节** 上存在明显疏漏，尤其是 `cwd`/`PYTHONPATH` 这个**已知踩坑点**没有规避。

**建议优先级**：
1. 🔴 **立即修复** P0 问题（cwd 缺失）— 这是 100% 会触发的崩溃
2. 🟡 **实现前完成** P1 问题（io_helper.py 定义、SKILL.md 入口守卫）
3. 🟢 **实现中补充** P2 问题（文档、兜底机制）

**评审结论**：方案需要修订后再进入实现阶段。建议修复 P0/P1 问题后，再进行下一轮评审。

---

*评审完成 | 2026-06-25 20:46*
