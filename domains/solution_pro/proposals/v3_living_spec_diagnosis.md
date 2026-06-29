# V3 Solution Pro × Living Spec 对接诊断报告

> **日期**: 2026-06-29
> **诊断范围**: V1 (`run_solution_pro`) vs V3 (`run_solution_pro_v2`) 的 Living Spec 接口一致性
> **目标**: V3 的接口与 V1 保持一致 — 改了内在流程，但接口不变

---

## 1. V1 Solution Pro 完整接口

### 1.1 入口签名

```python
def run_solution_pro(topic: str, **kwargs):
    """
    Args:
        topic: 设计主题（必需，>=5字符）
        **kwargs: solution_type, mode, constraints, stakeholders,
                  living_spec（Spec Pro 桥接，dict 类型）
    Returns:
        {
            "session_id": str,
            "base_path": str,
            "plan_path": str,
            "spawn_params": dict,  # 直接传给 sessions_spawn
            "run_start_at": str,
            "watcher_config": str,
            ...
        }
    """
```

### 1.2 Living Spec 接收方式

```
run_solution_pro(**kwargs)
  → _SolutionDispatcher.__init__(living_spec=kwargs.get('living_spec'))
    → self.living_spec = living_spec  # Optional[dict]
```

### 1.3 Living Spec 传递链路（完整无断点）

```
self.living_spec
  ├─→ write_frozen_spec(base_path, topic, constraints, self.living_spec)
  │     └─→ frozen_spec.py:build_frozen_spec()
  │           ├─ 从 confirmed 提取所有字段 → 生成 REQ-IDs
  │           ├─ 构建 executive_summary（指针+上下文模式）
  │           ├─ 构建 requirement_groups（5 组分类）
  │           ├─ 透传 guardrails
  │           └─ 透传 solution_pro_hints
  │
  └─→ 每个 build_*_task(living_spec=self.living_spec)
        ├─ build_data_collection_task()   → 注入 confirmed.objective/pain_points/capabilities
        ├─ build_planner_task()           → 注入 confirmed 全部字段（全局理解上下文）
        ├─ build_researcher_task()        → 注入 solution_pro_hints.focus_areas + guardrails
        ├─ build_reviewer_task()          → 注入 objective/capabilities/quality_attributes/constraints
        ├─ build_consolidator_task()      → 注入 living_spec 上下文
        ├─ build_auditor_task()           → 注入 living_spec 上下文
        ├─ build_fixer_task()             → 注入 living_spec 上下文
        ├─ build_harness_final_task()     → 注入 capabilities/quality_attributes/constraints
        └─ build_summarizer_task()        → 注入 capabilities/quality_attributes/constraints + user_directives
```

### 1.4 V1 输出格式

| 文件 | 路径 | 内容 |
|------|------|------|
| frozen_spec.json | `data/frozen_spec.json` | 含 REQ-IDs、executive_summary、requirement_groups、guardrails、solution_pro_hints |
| execution_plan.json | `{session_dir}/execution_plan.json` | 10 阶段固定计划 |
| tasks.json | `{session_dir}/tasks.json` | 11 个 worker task prompts |
| control_contract.json | Blackboard stage `control_contract` | Planning 后刷新的控制契约 |
| requirements_traceability_matrix | Blackboard stage | 需求覆盖矩阵 |
| .completed | Blackboard stage | 完成标记 |

---

## 2. V3 Solution Pro 当前接口

### 2.1 入口签名

```python
def run_solution_pro_v2(user_input: str, **kwargs):
    """
    Args:
        user_input: 用户输入（需求描述）
        **kwargs: topic, solution_type, mode, domain, constraints, stakeholders,
                  living_spec（Spec Pro 桥接）
    Returns:
        {
            "session_id": str,
            "base_path": str,
            "spawn_params": dict,
        }
    """
```

### 2.2 Living Spec 接收方式

```python
living_spec = kwargs.get("living_spec")
if living_spec:
    frozen_spec["living_spec"] = living_spec  # 仅作为 raw dict 存入 frozen_spec
```

### 2.3 Living Spec 传递链路（⚠️ 严重断裂）

```
living_spec = kwargs.get("living_spec")
  │
  ├─→ frozen_spec["living_spec"] = living_spec  ✅ 存入 frozen_spec.json
  │     （但 frozen_spec 是极简版，不含 REQ-IDs/executive_summary/requirement_groups）
  │
  └─→ ❌ 断裂！
        ├─ master_orchestrator._build_frozen_spec() 不使用 frozen_spec.py
        ├─ V2/V3 module prompts 不引用 living_spec
        ├─ V2/V3 worker prompts 不注入 living_spec 上下文
        └─ 无 REQ-ID 生成、无 executive_summary、无 requirement_groups
```

### 2.4 V3 输出格式

| 文件 | 路径 | 内容 |
|------|------|------|
| frozen_spec.json | `data/frozen_spec.json` | 极简版：topic/solution_type/mode/domain/constraints/user_input + raw living_spec |
| master_state.json | `master_state.json` | 模块级状态 |
| planning_convergence | Blackboard stage | Planning 模块输出 |
| research_convergence | Blackboard stage | Research 模块输出 |
| review_qc_convergence | Blackboard stage | ReviewQC 模块输出 |
| .completed | Blackboard | 完成标记 |

---

## 3. V1 vs V3 接口差异表

| 维度 | V1 (`run_solution_pro`) | V3 (`run_solution_pro_v2`) | 差异严重度 |
|------|------------------------|---------------------------|-----------|
| **入口参数** | `topic` + `**kwargs` | `user_input` + `**kwargs` | 🟡 低（兼容） |
| **living_spec 接收** | `kwargs.get('living_spec')` | `kwargs.get('living_spec')` | ✅ 一致 |
| **frozen_spec 生成** | `frozen_spec.py:build_frozen_spec()` — 完整 REQ-ID + executive_summary + groups | `master_orchestrator._build_frozen_spec()` — 极简 6 字段 | 🔴 **严重** |
| **REQ-ID 系统** | ✅ 从 living_spec.confirmed 生成完整 REQ-ID 列表 | ❌ 无 REQ-ID 生成 | 🔴 **严重** |
| **executive_summary** | ✅ 指针+上下文模式 | ❌ 不存在 | 🔴 **严重** |
| **requirement_groups** | ✅ 5 组分类（Core/Functional/NonFunctional/Boundaries/Context） | ❌ 不存在 | 🔴 **严重** |
| **Worker prompt 注入** | ✅ 每个 worker 通过 `build_*_task(living_spec=...)` 注入上下文 | ❌ V3 module prompts 无 living_spec 注入 | 🔴 **严重** |
| **guardrails 传递** | ✅ 注入到 research/review/harness workers | ❌ 不传递 | 🟠 高 |
| **solution_pro_hints** | ✅ 注入到 researcher/summarizer | ❌ 不传递 | 🟠 高 |
| **需求覆盖追踪** | ✅ covered_req_ids + traceability_matrix | ❌ 无覆盖追踪 | 🔴 **严重** |
| **coverage_policy** | ✅ 在 frozen_spec 中定义覆盖策略 | ❌ 不存在 | 🟠 高 |
| **Blackboard 路径** | `blackboard/{session_id}/` | `solution_pro/blackboard_sessions/{topic}/` | 🟡 低（架构差异） |
| **输出结构** | 10 阶段 pipeline | 3 模块（Planning→Research→ReviewQC） | 🟡 低（架构差异） |
| **control_contract** | ✅ 有 | ❌ 无 | 🟠 高 |
| **向后兼容** | `living_spec=None` 完全回退 | `living_spec=None` 也工作（但有的话也不用） | ✅ 一致 |

---

## 4. Living Spec 数据模型

> 来源: `domains/spec_pro/contracts/living_spec.py`

### 4.1 顶层结构

```
LivingSpec
├── meta                    # 必填：引擎元数据
├── confirmed               # 必填：权威需求层
├── inferred                # 可选：AI 推断需求（含置信度）
├── guardrails              # 必填：行为边界
├── solution_pro_hints      # 可选：下游提示
└── route_recommendation    # 可选：路由建议
```

### 4.2 meta 字段

| 字段 | 类型 | 含义 |
|------|------|------|
| engine | str | 固定 "spec_pro" |
| version | str | 契约版本 "2.1" |
| spec_version | int | Living Spec 版本号 |
| scenario | str | genesis/supplement/refine/pivot |
| mode | str | standard/quick/deep |
| created_at | str | ISO 8601 |
| updated_at | str | ISO 8601 |
| conversation_rounds | int | 对话轮次 |
| quality_score | float | 0-100 |
| quality_level | str | S/A/B/C |

### 4.3 confirmed 字段（权威需求层）

| 字段 | 类型 | 含义 |
|------|------|------|
| objective | str | 核心目标 |
| pain_points | list[str] | 关键痛点 |
| success_metrics | list[SuccessMetric] | 成功指标（metric/target） |
| users | list[User] | 用户角色（role/count/key_needs） |
| key_scenarios | list[str] | 关键使用场景 |
| capabilities | Capabilities | 能力分层（always_do/should_do/never_do） |
| quality_attributes | list[QualityAttribute] | 质量属性（category/spec/priority） |
| constraints | dict | 约束条件 |
| integration | dict | 集成需求（existing_systems/requirements） |
| risks_and_assumptions | RisksAndAssumptions | 风险/假设/依赖 |
| terms | list[Term] | 术语定义 |
| user_directives | list[dict] | 用户指令 |

### 4.4 guardrails 字段

| 字段 | 类型 | 含义 |
|------|------|------|
| always_do | list[str] | 必须做的边界 |
| never_do | list[str] | 禁止做的边界 |
| ask_first | list[str] | 需确认后才能做 |

### 4.5 solution_pro_hints 字段

| 字段 | 类型 | 含义 |
|------|------|------|
| focus_areas | list[str] | 重点关注领域 |
| complexity_notes | list[str] | 复杂度说明 |
| priority_dimensions | list[str] | 优先级维度 |

---

## 5. V3 缺失的 Living Spec 对接点

### 5.1 🔴 P0：frozen_spec 生成未使用 frozen_spec.py

**位置**: `master_orchestrator.py:_build_frozen_spec()`

**现状**:
```python
def _build_frozen_spec(self, user_input: str, config: dict) -> dict:
    return {
        "topic": config.get("topic", user_input),
        "solution_type": config.get("solution_type", "architecture"),
        "mode": config.get("mode", "standard"),
        "domain": config.get("domain", "backend_api"),
        "constraints": config.get("constraints", []),
    }
```

**问题**: 完全忽略了 living_spec。V1 使用 `frozen_spec.py:build_frozen_spec()` 从 living_spec.confirmed 提取所有字段生成 REQ-IDs、executive_summary、requirement_groups。

**影响**: V3 的 frozen_spec 不含任何需求结构，下游模块无法进行需求覆盖追踪。

### 5.2 🔴 P0：V3 Module Prompts 无 Living Spec 引用

**位置**:
- `prompts/v2_planning_module.md` — 只嵌入 `frozen_spec JSON`（极简版）
- `prompts/v2_research_module.md` — 只引用 frozen_spec
- `prompts/v2_reviewqc_module.md` — 不引用 frozen_spec 或 living_spec

**问题**: V1 的每个 worker prompt 都通过 `build_worker_context_section(living_spec, worker_name)` 注入"全局理解"上下文（objective、pain points、users、capabilities、constraints、quality attributes、guardrails、solution_pro_hints）。V3 的 module prompts 完全没有这个机制。

**影响**: V3 的 workers 在没有任何需求上下文的情况下工作，只能看到 topic 和 constraints。

### 5.3 🔴 P0：无 REQ-ID 系统

**位置**: V3 整个 pipeline

**现状**: V1 从 living_spec 生成完整的 REQ-ID 列表（REQ-001, REQ-002, ...），每个 worker 输出 `covered_req_ids`，最终生成 `requirements_traceability_matrix`。V3 完全没有 REQ-ID 概念。

**影响**: 无法追踪方案是否覆盖了所有需求，Harness 检查无法进行覆盖度评估。

### 5.4 🟠 P1：无 guardrails 传递

**位置**: V3 Research/ReviewQC modules

**现状**: V1 将 `guardrails.always_do` 和 `guardrails.never_do` 注入到 researcher 和 reviewer prompts。V3 不传递。

**影响**: V3 的方案可能违反用户设定的行为边界。

### 5.5 🟠 P1：无 solution_pro_hints 传递

**位置**: V3 Research module

**现状**: V1 将 `solution_pro_hints.focus_areas` 注入到 researcher prompts，指导研究方向。V3 不传递。

**影响**: V3 的研究方向可能偏离 Spec Pro 的建议重点。

### 5.6 🟠 P1：E2E 测试无 Living Spec 输入

**位置**: `e2e_test_runner.py`

**现状**: `_load_or_create_frozen_spec()` 创建极简 frozen_spec，不含 living_spec 字段。测试用例完全在无 Living Spec 环境下运行。

**影响**: 无法验证 Spec Pro → Solution Pro 的端到端集成。

### 5.7 🟡 P2：Blackboard 路径不一致

**位置**: V1 vs V3 BlackboardManager 初始化

| | V1 | V3 |
|---|---|---|
| base_dir | `blackboard/{session_id}/` | `solution_pro/blackboard_sessions/{topic}/` |

**影响**: 跨模块工具（如 watcher、auto-chain）需要适配不同路径。

---

## 6. 修复建议

### 6.1 修复 P0-1：让 V3 使用 frozen_spec.py

**文件**: `master_orchestrator.py`

**改动**:

```python
# 修改 _build_frozen_spec() 方法
def _build_frozen_spec(self, user_input: str, config: dict) -> dict:
    """构建 Frozen Spec — 使用 frozen_spec.py 的完整生成逻辑"""
    from domains.solution_pro.frozen_spec import build_frozen_spec as build_full_frozen_spec
    
    living_spec = config.get("living_spec")
    constraints = config.get("constraints", [])
    topic = config.get("topic", user_input)
    
    # 使用完整的 frozen_spec 生成（含 REQ-IDs、executive_summary、requirement_groups）
    return build_full_frozen_spec(
        topic=topic,
        constraints=constraints,
        living_spec=living_spec,
    )
```

**同步修改**: `run_solution_pro_v2()` 中也需要确保 living_spec 被传递到 config：

```python
# 在 run_solution_pro_v2() 中
config = {
    "topic": topic,
    "solution_type": kwargs.get("solution_type", "architecture"),
    "mode": kwargs.get("mode", "standard"),
    "domain": kwargs.get("domain", "backend_api"),
    "constraints": kwargs.get("constraints", []),
    "living_spec": kwargs.get("living_spec"),  # ← 确保传入 config
}
```

### 6.2 修复 P0-2：V3 Module Prompts 注入 Living Spec 上下文

**方案 A（推荐）：在 frozen_spec 中引用**

由于 P0-1 修复后 frozen_spec.json 已包含完整的 executive_summary、requirement_groups、guardrails、solution_pro_hints，V3 module prompts 只需读取 frozen_spec.json 即可获得所有 living_spec 信息。

**改动**: 在 `v2_planning_module.md`、`v2_research_module.md`、`v2_reviewqc_module.md` 的执行流程中，第一步读取 frozen_spec：

```markdown
### Layer 0: 读取 Frozen Spec（含 Living Spec 上下文）

用 exec 读取 frozen_spec：
```bash
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import json
spec = bb.read_stage('data/frozen_spec', default={})
print(json.dumps(spec, ensure_ascii=False, indent=2))
"
```

frozen_spec 包含以下关键信息（来自 Living Spec）：
- `executive_summary`: 一句话目标 + 关键场景 REQ-IDs + 成功标准 + 约束
- `requirements`: 完整 REQ-ID 列表（每个 REQ 有 id/category/description/priority/source）
- `requirement_groups`: 5 组分类（Core/Functional/NonFunctional/Boundaries/Context）
- `guardrails`: 行为边界（always_do / never_do）
- `solution_pro_hints`: 重点关注领域

你的所有分析和输出必须基于这些信息。
```

**方案 B（补充）：在 Master Orchestrator prompt 模板中注入**

在 `v2_orchestrator.md` 的 Step 0 初始化中，将 frozen_spec 的生成改为调用 `frozen_spec.py`：

```python
# Step 0 中的 frozen_spec 写入改为：
from domains.solution_pro.frozen_spec import build_frozen_spec
frozen = build_frozen_spec(
    topic='{topic}',
    constraints={constraints},
    living_spec={living_spec_json},
)
bb.write('data/frozen_spec.json', frozen)
```

### 6.3 修复 P0-3：V3 需要 REQ-ID 覆盖追踪

**改动**: 在 `v2_planning_module.md` 的 Convergence Planner (Layer 2) 输出格式中，添加 `covered_req_ids`：

```markdown
## 输出格式（JSON）
{
  "unified_constraints": { ... },
  "covered_req_ids": ["REQ-001", "REQ-002", ...],  // ← 新增
  "requirement_evidence": {                          // ← 新增
    "REQ-001": "在 xxx 约束中覆盖",
    "REQ-002": "在 yyy 验收标准中覆盖"
  }
}
```

**改动**: 在 `v2_reviewqc_module.md` 的 Harness Check (Stage 2) 中，添加覆盖度检查：

```markdown
### Stage 2: Harness Check

检查项：
1. 需求覆盖度：所有 P0 REQ-IDs 是否在 planning_convergence.covered_req_ids 中？
2. 架构一致性：方案是否符合 frozen_spec.executive_summary 中的目标？
3. 信息守恒：frozen_spec 中的所有需求是否在最终方案中有对应？
4. Guardrails 遵守：方案是否违反 guardrails.never_do？
```

### 6.4 修复 P1-1：Guardrails 传递

修复 P0-1 后，guardrails 已包含在 frozen_spec.json 中。只需确保 V3 module prompts 明确引用 guardrails 字段。

**改动**: 在 `v2_research_module.md` 的 Stage 3 (Research Experts) task 描述中添加：

```markdown
## 边界约束（来自 guardrails）
- 必须做: {frozen_spec.guardrails.always_do}
- 禁止做: {frozen_spec.guardrails.never_do}
```

### 6.5 修复 P1-2：solution_pro_hints 传递

修复 P0-1 后，solution_pro_hints 已包含在 frozen_spec.json 中。

**改动**: 在 `v2_research_module.md` 的 Stage 1 (Knowledge Freshness) 和 Stage 3 (Research Experts) 中添加：

```markdown
## 重点关注（来自 solution_pro_hints）
- focus_areas: {frozen_spec.solution_pro_hints.focus_areas}
- complexity_notes: {frozen_spec.solution_pro_hints.complexity_notes}
```

### 6.6 修复 P1-3：E2E 测试添加 Living Spec 输入

**改动**: 在 `e2e_test_runner.py` 中：

```python
def _load_or_create_frozen_spec(topic: str) -> dict:
    """加载或创建 frozen_spec（含 Living Spec）"""
    # 尝试从已有 Spec Pro session 加载 living_spec
    from domains.solution_pro.frozen_spec import build_frozen_spec
    
    living_spec = _load_living_spec_from_spec_pro()
    
    return build_frozen_spec(
        topic=topic,
        constraints=["全LLM控制", "8+小时运行"],
        living_spec=living_spec,
    )

def _load_living_spec_from_spec_pro() -> dict | None:
    """从 Spec Pro blackboard 加载 living_spec.json"""
    spec_dir = Path(DEEPFLOW) / "blackboard"
    if spec_dir.exists():
        for session_dir in spec_dir.iterdir():
            living_spec_path = session_dir / "spec" / "living_spec.json"
            if living_spec_path.exists():
                with open(living_spec_path) as f:
                    return json.load(f)
    return None
```

---

## 7. 修复优先级总结

| 优先级 | 修复项 | 文件 | 工作量 |
|--------|--------|------|--------|
| 🔴 P0-1 | `_build_frozen_spec()` 使用 `frozen_spec.py` | `master_orchestrator.py` | 小 |
| 🔴 P0-2 | V3 module prompts 注入 Living Spec 上下文 | `v2_planning_module.md`, `v2_research_module.md`, `v2_reviewqc_module.md` | 中 |
| 🔴 P0-3 | V3 添加 REQ-ID 覆盖追踪 | `v2_planning_module.md`, `v2_reviewqc_module.md` | 中 |
| 🟠 P1-1 | Guardrails 传递 | 由 P0-1 解决（frozen_spec 已含 guardrails） | 极小 |
| 🟠 P1-2 | solution_pro_hints 传递 | 由 P0-1 解决（frozen_spec 已含 hints） | 极小 |
| 🟠 P1-3 | E2E 测试添加 Living Spec | `e2e_test_runner.py` | 小 |
| 🟡 P2 | Blackboard 路径统一 | 架构层面，暂不修复 | 大 |

---

## 8. 核心结论

**V3 的 Living Spec 对接存在 3 个 P0 级断裂**：

1. **frozen_spec 生成不使用 frozen_spec.py** → 导致 REQ-IDs、executive_summary、requirement_groups 全部缺失
2. **V3 module prompts 不引用 living_spec** → workers 在没有需求上下文的环境下工作
3. **无 REQ-ID 覆盖追踪** → 无法验证方案是否覆盖了所有需求

**修复策略**：

- **P0-1 是根因修复**：让 `_build_frozen_spec()` 调用 `frozen_spec.py:build_frozen_spec()`，一次性解决 REQ-IDs、executive_summary、requirement_groups、guardrails、solution_pro_hints 的缺失问题。
- **P0-2 是消费端修复**：V3 module prompts 需要读取 frozen_spec.json 并基于其丰富内容工作。
- **P0-3 是追踪修复**：V3 的 planning 和 reviewqc 模块需要输出 covered_req_ids。

**修复后目标**：V3 的接口（接什么、输出什么）与 V1 保持一致。内在流程（3 模块 vs 10 阶段）可以不同，但 Living Spec 的接收、传递、消费链路必须完整。
