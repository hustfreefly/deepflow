# ProcessManager 设计方案（评审稿）

> 评审任务：找出设计缺陷，给出具体修改建议，最后给 GO / CONDITIONAL / NO-GO 结论。

---

## 1. 问题背景（真实故障案例）

**DeepFlow Solution Pro V3.1 的实际故障（2026-07-25）**：

- Orchestrator Agent (depth-1) 按序 spawn 3 个 Module Agent：Planning → Research → Summary
- 每个模块用 `sessions_spawn` + `sessions_yield` 模式
- **实际结果**：Planning ✅ 完成（42KB）、Research ✅ 完成（52KB，21:13:53 写入完成标记）
- **但 Orchestrator 在 Research 完成后就死了，从未 spawn Summary**
- 证据：Research 完成后 blackboard 再无任何新文件；`summary_module_prompt.md` 不存在；无 `.completed` 无 `.failed`

**根因分析**：
- spawn-yield 模式 = Orchestrator 的 turn 结束后被动等待 wake 事件
- wake 事件不可靠（可能丢失/延迟/turn 异常结束）
- Module Agent 完成事件到达后，Orchestrator 没有正确继续执行
- **这是第二次同类事故**：Deliver Pro V2 的 yield 循环在 run-mode session「yield 时无 pending children = 自杀」语义下曾 5 连死

**用户的判断（决策者观点）**：
1. yield 是"有相当高失败概率的游戏"，多 Agent 场景必然出问题
2. 要恢复 V1.0（Python orchestrator 时代）的**过程管理能力**：主动轮询、状态感知、异常干预
3. 但不要 V1.0 的厚重（7760 行 Python orchestrator）
4. **不用 Cron**（实践证明 OpenClaw cron 有各种小问题，不稳健）
5. 做成 DeepFlow **通用基础模块**，所有域共享，不每个域单独适配
6. LLM 做语义调度，确定性代码做过程管理（能力正交）

---

## 2. V1.0 过程管理的精华（从 1843 行核心代码提炼）

| 机制 | V1.0 实现 | V3.1 现状 |
|:---|:---|:---|
| 主动轮询 | `_wait_for_output()` 每 5s 轮询 blackboard | ❌ yield 被动等待 |
| 断点续跑 | 双层 state 验证 + artifact hash | ❌ 状态不一致 |
| 超时保护 | 模块级差异化超时 | ❌ 无 |
| 失败重试 | retry_count + max_retries | ❌ 无 |
| 状态机 | state.json 持久化 | ⚠️ 有但不一致 |

V1.0 厚重的根因：把**调度逻辑**（模块序列、Gate check、降级策略）也写进了 Python。新方案只取**过程管理**（注册/扫描/检测/恢复），调度决策仍由 LLM Agent 做。

---

## 3. ProcessManager 设计

### 3.1 核心抽象：TrackableUnit

三域共性：都有"执行单元"需要追踪。

| 域 | 执行单元 | 并行模式 | 依赖关系 |
|:---|:---|:---|:---|
| Solution Pro | Module（3 个） | 模块内并行 workers | 严格顺序 P→R→S |
| Ship Pro | Worker（N 个） | 层内并行 | 分层（planner→workers→consolidator） |
| Deliver Pro | WP（N 个） | 层内并行 | 依赖图 execution_layers |

```python
@dataclass
class TrackableUnit:
    unit_id: str                    # "planning" / "worker_1" / "wp_core_001"
    output_check: dict              # 声明式输出验证契约
    timeout: int = 1800             # 超时预算（秒）
    depends_on: list[str] = []      # 依赖的 unit_id
    registered_at: float            # 注册时间戳
    status: str = "pending"         # pending/running/completed/failed/stalled
    retry_count: int = 0
```

### 3.2 模块结构（~340 行）

```
core/process_manager/
├── __init__.py      # 公开 API
├── manager.py       # ProcessManager 主类（~150 行）
├── unit.py          # TrackableUnit + 枚举（~60 行）
├── registry.py      # blackboard 持久化（~80 行）
└── poller.py        # 轮询辅助（~50 行）
```

### 3.3 核心 API

```python
pm = ProcessManager(session_id="...", domain="solution_pro")

# 1. 注册（spawn 前）
pm.register("planning",
    output_check={"type": "file_exists", "path": "stages/planning_convergence.json"},
    timeout=1800, depends_on=[])

# 2. 检查（轮询中）
pm.check("planning")
# → {"status": "running", "elapsed": 120, "action": "CONTINUE_POLL"}
# → {"status": "completed", "action": "ADVANCE"}
# → {"status": "stalled", "elapsed": 1900, "action": "RESPAWN"}

# 3. 全局扫描
pm.scan()
# → {"units": {...}, "next_ready": ["research"], "all_done": false}

# 4. 标记完成
pm.mark_completed("planning")
```

### 3.4 状态推导：文件系统是唯一真相（不维护内存状态）

```python
def check(self, unit_id):
    unit = registry.get(unit_id)
    # Layer 1: 完成标记存在？
    if completion_marker_exists(unit):
        # Layer 2: 输出文件有效？
        if verify_output(unit):
            return {"status": "completed", "action": "ADVANCE"}
        return {"status": "output_invalid", "action": "RESPAWN"}
    # Layer 3: 超时？
    if elapsed > unit.timeout:
        return {"status": "stalled", "action": "RESPAWN"}
    return {"status": "running", "action": "CONTINUE_POLL"}
```

### 3.5 声明式 output_check（可扩展）

```python
{"type": "file_exists", "path": "stages/planning_convergence.json"}
{"type": "json_schema", "path": "stages/research_digest.json", "schema": "ResearchDigest"}
{"type": "manifest", "path": "stages/worker_outputs/*/MANIFEST.json", "min_count": 3}
{"type": "custom", "validator": "domains.ship_pro...validate_ship_package"}
```

### 3.6 Orchestrator 轮询协议（替代 spawn-yield）

```
Orchestrator Agent 的一个 turn 内完成所有事：
对每个 unit：
  1. pm.register(unit)
  2. sessions_spawn(worker)   ← 不 yield！
  3. 轮询循环：
     - exec: pm.check(unit)
     - ADVANCE → 验证输出 → 下一个 unit
     - RESPAWN → 重新 spawn → 继续轮询
     - CONTINUE_POLL → exec: sleep 60 → 再 check
  4. pm.scan().all_done → 写 .completed → 结束 turn
```

**Token 估算**：每次轮询 ~150 tokens；2 小时任务 = 120 次 = ~18K tokens。

---

## 4. 关键设计决策（请重点评审）

**决策 1：轮询在 Agent turn 内（不用 cron、不用独立 Python 进程）**
- 理由：cron 不稳健（用户实践）；独立 Python 进程无法调 sessions_spawn（平台限制：spawn 是 Agent tool）
- 风险：Orchestrator session 若被平台杀死，轮询也死 → 靠 registry 持久化 + 重启恢复兜底

**决策 2：exec sleep 60 做轮询间隔**
- 每次 sleep 是 Agent 的一个 exec tool call
- 2 小时任务 = 120 个 exec 调用

**决策 3：状态推导全部 from 文件系统**
- 不维护内存状态，session 死了重启后 scan() 即可恢复

---

## 5. 需要评审回答的问题

1. Agent turn 内跑 2 小时轮询循环（120 次 exec + sleep 60），在 OpenClaw 平台上真的可行吗？turn 有没有隐藏的生命周期限制？
2. Orchestrator 轮询中自己挂了，重启恢复流程是否完整？有没有状态漏洞？
3. TrackableUnit 抽象对三域（Solution/Ship/Deliver）是否够用？有没有遗漏的维度？
4. 340 行自称"轻量"，有没有过度设计？能更简单吗？
5. stall 检测只有"超时"一个信号，够吗？（文件 mtime 不更新、子 agent 死但标记未写等场景）
