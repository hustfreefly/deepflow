# 代码一致性审计报告

> 审计时间: 2026-06-02 21:36 CST
> 审计范围: `/Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/`
> 审计人: Subagent (代码一致性专家)

---

## 检查项 1: 函数签名一致性

- 状态: ⚠️ 警告

### 1.1 `living_spec` 参数传递 — ✅ 通过

所有 11 个 Pipeline Worker 都正确接收了 `living_spec=self.living_spec`:

| Stage | Builder Function | `living_spec` |
|---|---|---|
| data_collection | `build_data_collection_task` | ✅ 传递 |
| planning | `build_planner_task` | ✅ 传递 |
| reviewers | `build_reviewer_task` | ✅ 传递 |
| research | `build_researcher_task` | ✅ 传递 |
| consolidator | `build_consolidator_task` | ✅ 传递 |
| audit | `build_auditor_task` | ✅ 传递 |
| fix | `build_fixer_task_with_audit` | ✅ 传递 |
| fixer_expert | `build_fixer_expert_task` | ✅ 传递 |
| harness_final | `build_harness_final_task` | ✅ 传递 |
| summarizer | `build_summarizer_task` | ✅ 传递 |

**数据流追溯**: `run_solution_pro(**kwargs)` → `_SolutionDispatcher.__init__(living_spec=kwargs.get('living_spec'))` → `self.living_spec` → 每个 `build_*_task(living_spec=self.living_spec)`。完整无断点。

### 1.2 "全局理解"上下文注入 — ✅ 通过

所有带 `living_spec` 的 Worker 都一致注入了「全局理解」上下文，结构统一:
- 一句话概括 (objective ≤50字截断)
- 痛点 (pain_points[:3])
- 用户 (users[:3])
- 成功指标 (success_metrics[:5])
- 角色特定需求分组标注

每个 Worker 的 `## 全局理解（来自 executive_summary）` 和 `## 你的角色相关需求分组` 模板高度一致。

### 1.3 `layer2_constraints` 参数 — ⚠️ 不一致

以下 6 个函数签名包含 `layer2_constraints` 参数，但在 `orchestrator_agent.py` 的 `get_all_tasks()` 中**未被传递**:

| 函数 | 签名有参数 | 调用传参 |
|---|---|---|
| `build_planner_task` | ✅ 有 | ❌ 未传 (默认 None) |
| `build_reviewer_task` | ✅ 有 | ❌ 未传 (用 LAYER2_READ_INSTRUCTION 替代) |
| `build_consolidator_task` | ✅ 有 | ❌ 未传 (默认 None) |
| `build_auditor_task` | ✅ 有 | ❌ 未传 (用 LAYER2_READ_INSTRUCTION 替代) |
| `build_fixer_expert_task` | ✅ 有 | ❌ 未传 (用 LAYER2_READ_INSTRUCTION 替代) |
| `build_summarizer_task` | ✅ 有 | ❌ 未传 (默认 None) |

**分析**: 这不算错误 — `orchestrator_agent.py` 选择使用 `LAYER2_READ_INSTRUCTION`（运行时读取 planning.json）替代直接注入约束。这是一种设计选择。但 `build_planner_task`、`build_consolidator_task`、`build_summarizer_task` 三个函数的 `layer2_constraints` 参数完全未被使用，建议要么在 orchestrator 中传入，要么从函数签名中移除以消除歧义。

### 1.4 死代码函数 — ⚠️ 存在

以下函数在 `task_builder.py` 中定义，但在 10 阶段 Pipeline 中**未被任何调用方使用**:

| 函数 | 状态 |
|---|---|
| `build_fixer_task` | ⚠️ 定义但 pipeline 使用 `build_fixer_task_with_audit` |
| `build_designer_task` | ⚠️ 定义且被 orchestrator 导入，但 `design` stage 不在 pipeline 列表 |
| `build_deliver_task` | ⚠️ 定义但从未被导入或调用 |
| `build_harness_v2_task` | ⚠️ 定义但从未被导入或调用 |
| `build_harness_task` | ⚠️ 定义但从未被导入或调用 |

---

## 检查项 2: 导入一致性

- 状态: ⚠️ 警告

### 2.1 `orchestrator_agent.py` 从 `task_builder.py` 导入 — ✅ 通过

```python
from domains.solution.task_builder import (
    build_data_collection_task,    ✅ 存在
    build_planner_task,            ✅ 存在
    build_researcher_task,         ✅ 存在
    build_reviewer_task,           ✅ 存在
    build_auditor_task,            ✅ 存在
    build_fixer_task_with_audit,   ✅ 存在
    build_harness_final_task,      ✅ 存在
    build_consolidator_task,       ✅ 存在
    build_fixer_expert_task,       ✅ 存在
    build_summarizer_task,         ✅ 存在
    build_designer_task,           ✅ 存在
    inject_req_traceability,       ✅ 存在
    validate_stage_output,         ✅ 存在
    HARNESS_EXEMPT_STAGES,         ✅ 存在
    LAYER2_READ_INSTRUCTION,       ✅ 存在
)
```

所有 15 个导入目标均存在。

### 2.2 `__init__.py` 公共 API — ✅ 通过

```python
__all__ = ['run_solution_pro']
```

唯一公共入口 `run_solution_pro` 正确导出，通过 `_SolutionDispatcher` 代理所有操作。

### 2.3 `control_contract.py` 从 `task_builder.py` 导入 — ✅ 通过

导入 `build_researcher_task`, `build_auditor_task`, `build_fixer_task_with_audit`, `build_fixer_expert_task`, `inject_req_traceability`, `LAYER2_READ_INSTRUCTION` — 全部存在。

### 2.4 循环导入风险 — ✅ 无

依赖关系图:
```
__init__.py → orchestrator_agent.py → task_builder.py → blackboard.py
              orchestrator_agent.py → frozen_spec.py
control_contract.py → task_builder.py → blackboard.py
completion_handler.py → blackboard.py
completion_handler.py → task_builder.py
```

无循环: `blackboard.py` 不反向依赖任何 solution 模块，`task_builder.py` 只依赖 `blackboard.py` 和 `core.prompt_registry` / `core.config.path_config`。✅ 安全。

---

## 检查项 3: frozen_spec 2.0.0 消费方

- 状态: ⚠️ 警告

### 3.1 `_acceptance_from_frozen_spec` 处理 2.0.0 字段 — ✅ 通过

`control_contract.py:137-176`:
- ✅ 正确读取 `frozen_spec.json`
- ✅ 优先使用 `requirement_groups` 组织输出（2.0.0 新字段）
- ✅ 遍历每个 group 的 `req_ids`，从 `frozen["requirements"]` 查找对应 requirement
- ✅ 正确提取 2.0.0 字段: `id`, `description`, `priority`, `category`
- ✅ Fallback 到扁平列表（向后兼容 2.0.0）

**注意**: `_acceptance_from_frozen_spec` 为每个 group 添加了 `group` 和 `group_description` 字段，这些是 control_contract 的扩展字段，不属于 frozen_spec 结构本身。这是正确的处理方式。

### 3.2 STAGE_PATH_REGISTRY 包含 frozen_spec 路径 — ✅ 通过

```python
STAGE_PATH_REGISTRY = {
    ...
    "frozen_spec": "data/frozen_spec.json",              ✅
    "requirements_traceability_matrix": "...",           ✅
    ...
}
```

### 3.3 `inject_req_traceability` 引用 frozen_spec — ✅ 通过

`task_builder.py` 中的 `REQ_TRACEABILITY_INSTRUCTION` 模板正确指向 `{blackboard_path}/data/frozen_spec.json`，并定义了 `covered_req_ids` 和 `requirement_evidence` 输出契约。

`orchestrator_agent.py` 的 `_inject_req_traceability()` 将此指令注入到**每一个** Worker 任务中。

### 3.4 ⚠️ frozen_spec 2.0.0 字段未被充分利用

`frozen_spec.json` 2.0.0 新增的关键字段在下游消费情况:

| 2.0.0 字段 | 消费方 | 状态 |
|---|---|---|
| `version: "2.0"` | 无消费者检查此字段 | ⚠️ 未验证版本 |
| `executive_summary` | `task_builder.py` 各 Worker 手动从 `living_spec.confirmed` 提取 | ⚠️ 重复逻辑 |
| `requirement_groups` | `_acceptance_from_frozen_spec` ✅ | ✅ 已消费 |
| `coverage_policy` | 无消费者 | ⚠️ 未消费 |
| `guardrails` | frozen_spec 写入时透传，但 Worker 未主动读取 | ⚠️ 仅透传 |
| `solution_pro_hints` | `build_researcher_task` 读取 `focus_areas` | ✅ 部分消费 |

**核心问题**: 每个 Worker 的 "全局理解" 上下文都是从 `living_spec.confirmed` 手动拼接的（约 20-40 行/函数），而不是直接消费 `frozen_spec.json` 中已构建好的 `executive_summary`。这导致了:
1. **代码重复**: 相同逻辑在 10+ 个函数中复制
2. **一致性风险**: 如果 `executive_summary` 结构变化，需要同步修改 10+ 处
3. **数据不一致**: Worker 从 `living_spec` 读取，而 `_acceptance_from_frozen_spec` 从 `frozen_spec.json` 读取 — 两个来源可能不同步

---

## 检查项 4: 数据流完整性

- 状态: ⚠️ 警告

### 4.1 `run_solution_pro()` 完整数据流 — ✅ 通过

```
run_solution_pro(topic, **kwargs)
  └─ _SolutionDispatcher(topic, **kwargs, spawn_fn=None)
       ├─ __init__: self.living_spec = kwargs.get('living_spec')
       └─ init():
            ├─ BlackboardManager(session_id)
            └─ write_frozen_spec(base_path, topic, constraints, living_spec)
  └─ get_all_tasks()  → 10 阶段 tasks (均带 living_spec)
  └─ save_tasks()     → tasks.json
  └─ save_execution_plan() → execution_plan.json
  → return {session_id, base_path, plan_path}
```

### 4.2 living_spec 传递完整性 — ✅ 通过

`living_spec` 从 `run_solution_pro(**kwargs)` 透传到所有 11 个 Pipeline Worker，无断点。

### 4.3 frozen_spec 读取 — ✅ 通过

- `write_frozen_spec()` 在 `init()` 时写入 `data/frozen_spec.json` ✅
- `REQ_TRACEABILITY_INSTRUCTION` 引导每个 Worker 运行时读取 `frozen_spec.json` ✅
- `_acceptance_from_frozen_spec` 在 `build_control_contract()` 中读取 ✅

### 4.4 `executive_summary` 和 `requirement_groups` 使用 — ⚠️ 不一致

| 组件 | executive_summary | requirement_groups |
|---|---|---|
| `frozen_spec.py` 构建 | ✅ 生成 | ✅ 生成 |
| `control_contract.py` 消费 | ❌ 未消费 | ✅ 消费 (_acceptance_from_frozen_spec) |
| `task_builder.py` Workers | ⚠️ 从 living_spec.confirmed 手动构建 | ❌ 未消费 |
| `completion_handler.py` | ❌ 未消费 | ❌ 未消费 |

**问题**: `executive_summary` 被 `frozen_spec.py` 精心构建（指针+上下文模式），但下游 Worker 并没有消费它，而是各自从 `living_spec.confirmed` 重新拼接。这违背了 2.0.0 的"指针 + 上下文"设计意图。

### 4.5 `design` stage 不在 Pipeline — ⚠️ 悬空代码

`orchestrator_agent.py` 的 `get_all_tasks()` 中 `pipeline` 列表**不包含** `"design"` stage，但 `build_designer_task` 被导入且有一段 `elif stage == "design"` 代码永远不会执行。

---

## 总体评估

### 健康度: 7/10

### ✅ 做得好的地方
1. **living_spec 传递完整**: 从入口到所有 Worker 无断点
2. **导入一致性良好**: 所有导入目标均存在，无缺失
3. **无循环导入**: 依赖图是单向 DAG
4. **"全局理解"注入一致**: 所有 Worker 使用相同的模板结构
5. **frozen_spec 2.0.0 生成完整**: `executive_summary`, `requirement_groups`, `coverage_policy` 均正确构建

### 🔴 关键问题

| # | 问题 | 严重度 | 文件 |
|---|---|---|---|
| 1 | `build_planner_task`/`build_consolidator_task`/`build_summarizer_task` 的 `layer2_constraints` 参数从未被 orchestrator 传递 | 中 | orchestrator_agent.py |
| 2 | 每个 Worker 手动从 `living_spec.confirmed` 构建"全局理解"，未消费 `frozen_spec.json` 中的 `executive_summary` — 10+ 处重复 | 中 | task_builder.py |
| 3 | 5 个死代码函数 (`build_fixer_task`, `build_designer_task`, `build_deliver_task`, `build_harness_v2_task`, `build_harness_task`) 增加了维护负担 | 低 | task_builder.py |
| 4 | `design` stage 不在 Pipeline 但被导入和定义 | 低 | orchestrator_agent.py |
| 5 | `coverage_policy` 和 `executive_summary` 2.0.0 字段在下游几乎未被消费 | 中 | 全局 |

### 🔧 建议修复

1. **[P1] 统一"全局理解"消费**: 创建一个 `format_global_understanding(session_id, worker_role)` 辅助函数，从 `frozen_spec.json` 读取 `executive_summary` 并格式化为 Worker prompt 片段，替换 10+ 处重复代码。

2. **[P2] 清理或启用 `layer2_constraints` 参数**: 
   - 如果 `LAYER2_READ_INSTRUCTION` 是首选方案 → 从 `build_planner_task`, `build_consolidator_task`, `build_summarizer_task` 签名中移除 `layer2_constraints` 参数
   - 如果需要两种模式并存 → 在 orchestrator 中传入实际值

3. **[P2] 移除或标记死代码函数**: 
   - `build_deliver_task` — 从未被导入，建议移除
   - `build_harness_v2_task` / `build_harness_task` — 从未被调用，建议标记 `@deprecated` 或移除
   - `build_designer_task` — 被导入但 stage 不在 pipeline，要么加入 pipeline 要么移除

4. **[P3] 验证 frozen_spec 版本**: 在 `_acceptance_from_frozen_spec` 入口添加 `version` 检查，确保 2.0.0 结构假设有效。

5. **[P3] 消费 `coverage_policy`**: 在 `completion_handler.py` 或 `harness_final` 中使用 `coverage_policy.harness_final_must_check_all_p0` 做最终验证。
