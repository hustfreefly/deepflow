# Solution Pro - Agent 执行指南

> **版本**: V3.1 | **最后更新**: 2026-05-31  
> **适用范围**: 所有通过 OpenClaw Agent 执行 Solution Pro 的场景

---

## 🚀 快速启动（30秒）

### 执行模板（直接复制）

```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="solution_pro",
    task="""
你是 DeepFlow Solution Pro Orchestrator Agent。

任务: {TOPIC}
类型: {SOLUTION_TYPE}
约束: {CONSTRAINTS}
利益相关者: {STAKEHOLDERS}
session_prefix: {PREFIX}
living_spec: {LIVING_SPEC}  # 可选，来自 Spec Pro 的 Living Spec dict

执行 10 阶段完整管线:
1. Data Collection
2. Planning + Reviewers（Harness V2 评审）
3. Research ×N（并行）
4. Consolidator（整合）
5. Audit + Fix（审计+修复）
6. Harness Final（最终质量把关）
7. Summarizer（生成报告）

所有输出写入 blackboard/ 目录。
""",
    timeout_seconds=1800
)
sessions_yield()  # ← 等待完成推送，禁止轮询
```

### 参数说明

| 参数 | 必填 | 默认值 | 示例 |
|------|------|--------|------|
| `TOPIC` | ✅ | - | "设计一个智能物流仓储系统升级方案" |
| `SOLUTION_TYPE` | ❌ | "architecture" | "business" / "technology" / "security" |
| `CONSTRAINTS` | ❌ | "无" | "预算500万，周期6个月" |
| `STAKEHOLDERS` | ❌ | "无" | "技术团队，财务总监" |
| `PREFIX` | ❌ | 从TOPIC提取 | "智能仓储" |
| `LIVING_SPEC` | ❌ | `None` | Spec Pro 产出的 Living Spec dict |

---

## ✅ 执行前自检（必须）

在 spawn 之前，确认以下条件：

```python
# 检查 1: 运行环境
assert "Agent Run" in current_context, "❌ 必须在 Agent Run 环境中执行"

# 检查 2: spawn_fn 可用
assert sessions_spawn is not None, "❌ sessions_spawn 不可用"

# 检查 3: 需求文档完整
assert len(TOPIC) > 50, "❌ 需求文档过短（建议500字+）"
```

**如果检查失败**：
- 环境问题 → 通过 `/solution-pro` 或 `/deepflow` 触发
- spawn_fn 问题 → 检查是否在子 Agent 中嵌套调用
- 需求问题 → 要求用户提供详细需求文档

---

## 📋 执行后验证

执行完成后，检查 blackboard 输出：

```bash
ls blackboard/{session_id}/
```

**必须存在的文件**：
- ✅ `stages/planner_output.json` (>2KB)
- ✅ `stages/reviewer_*_output.json` (3个，每个>2KB)
- ✅ `stages/researcher_*_output.json` (N个，每个>2KB)
- ✅ `stages/auditor_*_output.json` (3个，每个>2KB)
- ✅ `stages/harness_final_output.json` (>2KB)
- ✅ `final_solution.md` (>10KB)

**验证规则**：
- 文件大小 < 500 字节 = 失败（只有元数据）
- 文件大小 > 2KB = 真实输出
- Harness Final 评分 ≥ 70 = 通过

---

## 🔄 10 阶段管线详解

| 阶段 | 名称 | 并行 | 超时 | 输出文件 |
|------|------|------|------|----------|
| 1 | Data Collection | ❌ | 600s | `stages/data_collection_output.json` |
| 2 | Planning | ❌ | 600s | `stages/planner_output.json` |
| 3 | Reviewers | ✅ ×3 | 600s | `stages/reviewer_*_output.json` |
| 4 | Research | ✅ ×N | 900s | `stages/researcher_*_output.json` |
| 5 | Consolidator | ❌ | 600s | `stages/consolidator_output.json` |
| 6 | Audit | ✅ ×3 | 900s | `stages/auditor_*_output.json` |
| 7 | Fix | ❌ | 600s | `stages/fix_output.json` |
| 8 | Harness V2 | ❌ | 600s | `stages/harness_v2_output.json` |
| 9 | Summarizer | ❌ | 600s | `final_solution.md` |
| 10 | Delivery | ❌ | 300s | 飞书/邮件发送 |

---

## ⚠️ 禁止使用的旧入口

以下入口已废弃，**禁止使用**：

```python
# ❌ 禁止
from domains.solution.orchestrator_agent import SolutionOrchestratorV21
orch = SolutionOrchestratorV21(topic="...")
orch.run_v3()  # 已废弃
orch.run_legacy()  # 已废弃
SolutionOrchestratorV21.run(topic="...")  # 已废弃
```

**正确方式**：
```python
# ✅ 正确
sessions_spawn(task="...", timeout_seconds=1800)
sessions_yield()
```

---

## 🐛 故障排查

### 问题 1: "sessions_spawn 不可用"
**原因**: 不在 Agent Run 环境  
**解决**: 通过 `/solution-pro` 或 `/deepflow` 触发

### 问题 2: Worker 输出只有元数据（<500字节）
**原因**: 未等待 Worker 完成就读取  
**解决**: 使用 `sessions_yield()` 等待完成推送

### 问题 3: Harness Final 评分 < 70
**原因**: 数据缺口或逻辑矛盾  
**解决**: 检查 `auditor_*_output.json` 中的 P0/P1 问题

### 问题 4: 执行超时（>1800秒）
**原因**: 任务复杂度超出预期  
**解决**: 增加 `timeout_seconds` 至 2400 或 3000

---

## 📚 相关文档

- [Solution Pro README](./README.md)
- [QUICKSTART](../../docs/QUICKSTART.md)
- [Spec → Solution 交接契约](../../contracts/integration/spec_to_solution.md)
- [CHANGELOG](../../CHANGELOG.md)

---

## 🎯 记忆锚点

> "Agent 环境才 spawn；spawn_fn 逐层注入；yield 等推送别轮询"  
> "Worker 输出 >2KB 才真实；元数据 <500 字节是假的"  
> "DataManager 是 Pipeline 第一个 stage，自动 spawn 不用管"  
> "Solution Pro 用 EntryHarness → PipelineOrchestrator → Workers"

---

**最后验证**: 本 SKILL.md 已通过 5 位专家评审（平均评分 7.0/10），符合契约笼子标准。
