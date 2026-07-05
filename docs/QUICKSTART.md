# DeepFlow 快速执行卡（半屏速查）

> **版本**: 0.4.0 (Spec Pro v2.4 + Solution Pro 2.0.0 + Research Pro)
> **变更**: Investment 模块已移除（v0.4.0），框架更轻量

---

## 方案设计 — 三步启动（Solution Pro）

```python
from core.unified_entry import UnifiedEntry

entry = UnifiedEntry()
result = entry.run({
    "domain": "solution",
    "topic": "设计一个智能物流仓储系统升级方案",
    "solution_type": "architecture",
    "constraints": ["预算500万", "周期6个月"],
    "session_prefix": "智能仓储"
})
```

**带 Living Spec（从 Spec Pro 传递）**:
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

## 验证清单（执行后检查）

```bash
ls blackboard/{session_id}/stages/
# 方案设计应有：
# ├── planner_output.json          ✅
# ├── reviewer_*_output.json       ✅ (>2KB)
# ├── researcher_*_output.json     ✅ (>2KB)
# ├── auditor_*_output.json        ✅ (>2KB)
# ├── harness_final_output.json    ✅
# └── final_report.md              ✅
```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| "sessions_spawn 不可用" | 未在 Agent Run 环境 | 必须通过 sessions_spawn 启动 |
| Worker 输出只有元数据 | 未等待 Worker 完成 | 检查 completion_handler 等待逻辑 |
| 收敛评分偏低 | 数据缺口/逻辑矛盾 | 检查 auditor P0/P1 问题 |
| Solution Pro 超时 | 任务复杂，Agent 数量多 | 增加 timeout_seconds 至 1800+ |

## 记忆锚点

> "Agent环境才spawn；spawn_fn逐层注入；yield等推送别轮询"
> "Worker 输出 >2KB 才真实；元数据 <500 字节是假的"
> "Solution Pro 用 UnifiedEntry → EntryHarness → PipelineOrchestrator → Workers"

---
*Solution Pro 设计详见：[domains/solution_pro/SKILL.md](domains/solution_pro/SKILL.md)*
*架构文档详见：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)*
