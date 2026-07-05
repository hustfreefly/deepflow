# DeepFlow 完整架构流程（2026-06-05 更新版）

> **目标**：一个文档说清楚所有关键设计，不再丢失上下文。
> **变更**: Investment 模块已移除（v0.4.0），框架更轻量

---

## 一、整体架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户交互层                                  │
│  OpenClaw 会话                                                     │
│  提交任务：domain / topic / solution_type / constraints           │
└──────────────────────┬───────────────────────────────────────────┘
                       │ sessions_spawn
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    DeepFlow 管线层                                 │
│                                                                  │
│  Solution Pro:                                                   │
│    UnifiedEntry.run(domain='solution', topic='...', spawn_fn)   │
│    → EntryHarness → PipelineOrchestrator → Workers               │
│    → 结果写入 blackboard/{session_id}/                            │
│                                                                  │
│  Research Pro:                                                   │
│    多源搜索 → 分层研究 → 引用验证 → 研究报告                      │
│                                                                  │
│  Spec Pro:                                                       │
│    苏格拉底式对话 → Living Spec                                   │
│    → SpecProCoordinator → 多轮对话                                │
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

**入口**：`core/unified_entry.py` → `UnifiedEntry.run(domain='solution', ...)`

```python
from core.unified_entry import UnifiedEntry

entry = UnifiedEntry()
result = entry.run({
    "domain": "solution",
    "topic": "设计智能仓库升级方案",
    "solution_type": "architecture",
    "constraints": ["预算 500 万", "6 个月完成"],
    "session_prefix": "smart-warehouse"
})
```

**内部流程**：
```
UnifiedEntry.run(domain='solution')
  → EntryHarness.validate_and_start(domain='solution', context, spawn_fn)
    → PipelineOrchestrator.run_pipeline()
      → Stage 1: Planner (create research plan)
      → Stage 2: Reviewers ×3 (并行 spawn)
      → Stage 3: Researchers ×N (并行 spawn)
      → Stage 4: Consolidator (integrate results)
      → Stage 5: Auditors ×3 (并行 spawn)
      → Stage 6: Fixer (fix issues)
      → Stage 7: Fixer Expert (expert-level fix)
      → Stage 8: Harness Final (final quality gate)
      → Stage 9: Summarizer (generate report)
  → 结果写入 blackboard/{session_id}/
```

### 3.2 Spec Pro → Solution Pro 桥接

```python
import json
from core.unified_entry import UnifiedEntry

with open("blackboard/spec_xxx/spec/living_spec.json") as f:
    living_spec = json.load(f)

entry = UnifiedEntry()
result = entry.run({
    "domain": "solution",
    "topic": living_spec["confirmed"]["objective"],
    "living_spec": living_spec,
    "session_prefix": "solution"
})
```

### 3.3 Unified Entry（统一入口）

**入口**：`core/unified_entry.py` → `run(domain, spawn_fn, **context)`

```python
from core.unified_entry import run

# Solution
result = run('solution', spawn_fn=sessions_spawn,
             topic='设计智能仓库', solution_type='architecture')
```

---

## 四、已验证案例

| 日期 | 领域 | 案例 | 状态 |
|:---|:---|:---|:---|
| 2026-04-12 | solution | 代码质量审查 | ✅ 2 轮迭代 78→93 分 |
| 2026-05-05 | solution | 智能物流仓储方案 | ✅ 10 阶段完整执行 |
| 2026-06-03 | solution | Spec Pro → Solution Pro 桥接 | ✅ Living Spec 传递成功 |

---

## 五、历史教训索引

| 教训 | 记忆锚点 | 详见 |
|:---|:---|:---|
| exec 无 openclaw | exec 无 openclaw，有 import 就失败 | AGENTS.md / SOUL.md |
| spawn_fn 注入是正道 | 主Agent用工具，Orchestrator收注入 | AGENTS.md |
| 2.0.0 是菜谱我是厨师 | 主Agent spawn才有SDK，子Agent跑代码=mock | MEMORY.md |
| 修复必验证 | 声称≠完成 | AGENTS.md |
| yield等推送别轮询 | sessions_yield() 静默等待 | AGENTS.md |
| 架构设计是宪法 | bug是违宪，修复是修宪，绕过是政变 | AGENTS.md |
