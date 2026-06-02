# Spec Pro → Solution Pro 下游消费与集成审计报告

**审计日期**: 2026-06-02
**审计范围**: Spec Pro 产出(living_spec.json) → Solution Pro 消费(frozen_spec.py + task_builder.py)
**审计方法**: 代码级静态分析，逐字段追踪 生产→消费 路径

---

## 审计结论总览

| 编号 | 严重性 | 类型 | 字段/文件 | 简述 |
|:---:|:---:|:---:|---|---|
| [1] | P0 | 断裂 | route_recommendation | StructureWorker 产出完整路由建议，Solution Pro 零消费 |
| [2] | P0 | 断裂 | user_directives / deliberately_omitted | Spec Pro 写入，Solution Pro 不知情，会重复追问已拒绝的维度 |
| [3] | P0 | 断裂 | inferred_pending | StructureWorker 产出待确认推断，Solution Pro 完全忽略 |
| [4] | P1 | 冗余 | requirement_annotations | 标注管线存在但几乎无效——冻结后没有下游使用 context_note/dependencies/potential_conflicts |
| [5] | P1 | 断裂 | solution_pro_hints.layer2_hints | 生成的 per-worker 提示未被 task_builder 消费，Solution Pro 用 Planner 的 layer2_constraints 替代 |
| [6] | P1 | 断裂 | solution_pro_hints.anti_patterns | 生成的反模式列表写入 living_spec，但没有 Worker prompt 消费它 |
| [7] | P1 | 不一致 | frozen_spec executive_summary vs task_builder 上下文 | frozen_spec 构建了 executive_summary 但 task_builder 各函数直接从 confirmed 重建，完全不一致 |
| [8] | P2 | 冗余 | solution_pro_hints 被展平为 hint 类 REQ | 结构化 hints 被 _add_requirement 拍平为字符串，语义丢失 |
| [9] | P2 | 不一致 | user_directives 字段位置 | LivingSpec 模型定义顶层 user_directives，但 merge_spec.py 写入 confirmed.user_directives |

---

## 详细审计条目

---

### [1] [P0] [断裂] route_recommendation 从未被消费

**Spec Pro 产出**: `living_spec.route_recommendation`（由 StructureWorker 生成，见 structure.md Step 2）
```json
{
  "suggested_engine": "solution_pro",
  "suggested_mode": "standard",
  "reasoning": "...",
  "confidence": 0.85,
  "complexity_score": 68,
  "complexity_factors": [...]
}
```

**Solution Pro 消费**: **无**。

**证据**:
- `frozen_spec.py::build_frozen_spec()` — 不读取 `living_spec.get("route_recommendation")`
- `task_builder.py` — 所有 10 个 `build_*_task()` 函数都不读取 `route_recommendation`
- `domains/solution/` 下全文搜索 `route_recommendation` 结果为 **0**
- `route_recommendation` 仅在 `domains/spec_pro/models.py:190` 定义为 dataclass

**影响**: 这个字段做了完整的复杂度评估（8个因子、4个引擎档位），但下游引擎不知道"为什么选择了自己"、"复杂度多少"、"建议什么模式"。如果 Solution Pro 需要根据复杂度动态调整深度（例如 complexity_score > 80 时启用更多研究者），这个字段本应提供依据。

**建议修复**:
- **方案 A（推荐）**: 在 `frozen_spec.py` 中将 `route_recommendation` 透传到 `frozen_spec.json` 顶层（类似 `guardrails` 和 `solution_pro_hints` 的做法），让 Solution Pro 入口读取
- **方案 B**: 如果不需要动态调整，直接从 LivingSpec 模型和 StructureWorker 中移除该字段，减少维护负担

---

### [2] [P0] [断裂] user_directives / deliberately_omitted 未被 Solution Pro 消费

**Spec Pro 产出**: `living_spec.confirmed.user_directives`（由 merge_spec.py::merge_user_directives 写入）
```json
"user_directives": [
  {"dimension": "users", "directive": "deliberately_omitted", "reason": "用户原话: '不要再问用户相关的问题'"}
]
```

**Solution Pro 消费**: **无**。

**证据**:
- `frozen_spec.py::build_frozen_spec()` — 不读取 `confirmed.get("user_directives")`
- `task_builder.py` — 所有函数直接从 `confirmed` 提取字段拼接 context，不检查 `user_directives`
- `domains/solution/` 下全文搜索 `user_directives` / `deliberately_omitted` 结果为 **0**

**影响**: Spec Pro 的 AssessWorker 知道对 deliberately_omitted 维度给 50 分不扣分（coordinator.py 注释明确说明），但 Solution Pro 的所有 Worker（Planner、Researcher、Auditor、Reviewer 等）都不知道哪些维度被用户主动放弃了。如果 Spec Pro 因为用户说"不考虑安全"而没有追问安全需求，Solution Pro 的 Auditor 可能反过来审计"安全方案缺失"，产生无意义的负面反馈。

**建议修复**:
- 在 `frozen_spec.py::build_frozen_spec()` 中读取 `confirmed.get("user_directives", [])`，提取 deliberately_omitted 维度列表
- 透传到 `frozen_spec.json` 作为 `deliberately_omitted_dimensions` 字段
- 在 `task_builder.py` 的各 Worker context 中注入"以下维度已被用户明确放弃，不要审计或追问: [...]"

---

### [3] [P0] [断裂] inferred_pending 未被 Solution Pro 消费

**Spec Pro 产出**: `round_result.json` 中的 `inferred_pending` 数组（由 StructureWorker 在所有 action 模式下输出，见 structure.md）
```json
"inferred_pending": [
  {"id": "INF-003", "content": "...", "confidence": 0.6}
]
```

**Solution Pro 消费**: **无**。

**证据**:
- `frozen_spec.py` — 不读取 `inferred_pending`
- `task_builder.py` — 不读取 `inferred_pending`
- `domains/solution/` 下全文搜索 `inferred_pending` 结果为 **0**

**影响**: Spec Pro 收集到的待确认推断（如"推断用户可能还需要移动端支持，置信度 0.6"）在 Spec Pro 流程结束后完全丢失。Solution Pro 无法知道"有哪些推断需要验证"或"有哪些 AI 假设需要在方案中标注"。

**建议修复**:
- `route_recommendation` 和 `inferred_pending` 应该作为 `living_spec.json` 的顶层字段保留（而非只在 round_result.json 中），这样 `frozen_spec.py` 可以读取
- 在 `frozen_spec.json` 中新增 `pending_inferences` 字段，供 Solution Pro 的 Auditor 或 Harness Final 检查这些推断是否被方案覆盖

---

### [4] [P1] [冗余] requirement_annotations 标注管线几乎无效

**Spec Pro 产出**: `living_spec.confirmed.requirement_annotations`（由 coordinator.py::build_annotation_task() 触发 LLM 标注，apply_annotations() 写入）

**Solution Pro 消费**: `frozen_spec.py::_merge_annotations()` — **读取但下游不使用**。

**证据**:
- `frozen_spec.py:159` 确实读取了 `confirmed.get("requirement_annotations")`
- `_merge_annotations()` 将 `context_note`、`dependencies`、`potential_conflicts` 合并到每个 REQ 对象
- 但 `task_builder.py` 中没有任何 Worker prompt 引用 REQ 的 `context_note` / `dependencies` / `potential_conflicts`
- REQ 对象的这 3 个字段被写入 `frozen_spec.json` 但从未被下游 Worker 的 prompt 模板使用

**实际状态**: 标注管线完成了"生产→合并→写入"的完整链路，但在"消费"环节断裂。LLM 花 token 生成的上下文注释、依赖关系、潜在冲突，最终只是静默地躺在 frozen_spec.json 里。

**建议修复**:
- **方案 A**: 在 `task_builder.py` 的 `inject_req_traceability()` 或各 Worker context 中，注入 REQ 的 `context_note` / `dependencies` / `potential_conflicts`，让 Worker 知道需求间的关联
- **方案 B（更彻底）**: 移除整个标注管线（build_annotation_task、apply_annotations、_merge_annotations），减少 Spec Pro 的收尾开销。如果未来确实需要，可以按需重新启用

---

### [5] [P1] [断裂] solution_pro_hints.layer2_hints 未被消费

**Spec Pro 产出**: `living_spec.solution_pro_hints.layer2_hints`（由 StructureWorker 生成，见 structure.md Step 3）
```json
"layer2_hints": {
  "researcher": ["必须调研主流GPU调度方案..."],
  "auditor": ["审计是否考虑GPU碎片化..."]
}
```

**Solution Pro 消费**: **无**。

**证据**:
- `frozen_spec.py:142-148` 只将 hints 展平为 hint 类 REQ（`f"{key}: {value}"`），不分角色
- `task_builder.py` 的 `inject_layer2_constraints()` 使用的是 `layer2_constraints` 参数（来自 Planner 的输出或 DEFAULT_LAYER2_CONSTRAINTS fallback），**不是** `solution_pro_hints.layer2_hints`
- `build_researcher_task()` 读取了 `hints.get("focus_areas", [])` 和 `living_spec.get("guardrails")`，但不读取 `hints.get("layer2_hints", {})`

**影响**: StructureWorker 基于需求复杂度为每个 Worker 角色生成了定制化提示（researcher 要调研什么、auditor 要关注什么），但 Solution Pro 完全无视这些提示，用的是 Planner 生成的通用 layer2_constraints 或硬编码的 DEFAULT_LAYER2_CONSTRAINTS。Spec Pro 的专业化建议被通用 fallback 替代。

**建议修复**:
- 在 `task_builder.py` 各 `build_*_task()` 函数中，读取 `solution_pro_hints.layer2_hints[worker_role]`，将其注入到 Layer 2 约束中
- 优先级: Spec Pro 的 layer2_hints > Planner 的 layer2_constraints > DEFAULT_LAYER2_CONSTRAINTS

---

### [6] [P1] [断裂] solution_pro_hints.anti_patterns 未被消费

**Spec Pro 产出**: `living_spec.solution_pro_hints.anti_patterns`（由 StructureWorker 生成，见 structure.md Step 3）
```json
"anti_patterns": [
  "不要过度设计（先满足MVP）",
  "避免引入过多开源组件增加运维负担"
]
```

**Solution Pro 消费**: **无**。

**证据**:
- `frozen_spec.py:142-148` 将 hints 展平为 hint 类 REQ，anti_patterns 没有被单独提取
- `task_builder.py` 没有任何函数读取 `anti_patterns`
- `domains/solution/` 下全文搜索 `anti_pattern` 结果为 **0**

**影响**: 这些反模式是 Spec Pro 基于需求分析得出的具体"不要做什么"的警告（比 guardrails.never_do 更具体、更有上下文），Solution Pro 的 Worker 完全看不到。

**建议修复**:
- 在 `frozen_spec.py` 中单独提取 `anti_patterns` 数组，透传到 `frozen_spec.json`
- 在 `task_builder.py` 的各 Worker context 末尾追加反模式提醒（类似 guardrails.never_do 的处理方式）

---

### [7] [P1] [不一致] frozen_spec executive_summary vs task_builder 上下文不一致

**Spec Pro 产出**: `living_spec`（confirmed 层）

**Solution Pro 消费**: 两条独立的上下文构建路径

**证据**:

路径 A — `frozen_spec.py::_build_executive_summary()`:
```python
return {
    "one_liner": one_liner,
    "objective_req": objective_req,          # REQ-ID 引用
    "key_scenarios_reqs": key_scenarios_reqs, # REQ-ID 列表
    "why": why,                               # pain_points[:3]
    "for_whom": for_whom,                     # users[:3] 带 role/description
    "success_criteria": success_criteria,     # success_metrics[:5]
    "constraints": constraints_dict,          # budget/timeline/tech_stack
    "source": source,
}
```

路径 B — `task_builder.py` 各 `build_*_task()` 函数:
```python
# 每个函数直接从 confirmed 重建上下文，完全不使用 executive_summary
objective = confirmed.get("objective", topic)
one_liner = objective if len(objective) <= 50 else objective[:47] + "..."
pain_points = confirmed.get("pain_points", [])[:3]
# ... 完全重复的逻辑
```

**问题**:
1. `executive_summary` 在 `frozen_spec.json` 中构建并输出，但 `task_builder.py` 的所有函数**不使用它**，而是各自从 `living_spec["confirmed"]` 重新提取、拼接
2. 两者的提取逻辑不完全一致：
   - `executive_summary.for_whom` 提取 `role + description`
   - `task_builder.py::build_planner_task` 提取 `role + key_needs`（字段名不同！）
   - `task_builder.py::build_auditor_task` 也提取 `role + key_needs`
   - 如果 `users` 数据结构中 `key_needs` 和 `description` 不同，两者注入的信息不一致
3. 如果有新的 confirmed 字段加入，需要在 frozen_spec 和 8+ 个 task_builder 函数中分别更新，维护成本高

**建议修复**:
- `task_builder.py` 应直接使用 `frozen_spec.executive_summary` 作为全局理解上下文，而不是各自重建
- 统一 `for_whom` 的字段提取逻辑（确认 `key_needs` vs `description` 哪个是正确的）

---

### [8] [P2] [冗余] solution_pro_hints 被展平为字符串化 hint REQ

**Spec Pro 产出**: `living_spec.solution_pro_hints`（结构化的 JSON 对象）

**Solution Pro 消费**: `frozen_spec.py:142-148`
```python
hints = (living_spec or {}).get("solution_pro_hints", None)
if hints:
    if isinstance(hints, str):
        _add_requirement(requirements, "hint", hints, "P1", "living_spec.solution_pro_hints")
    elif isinstance(hints, dict):
        for key, value in hints.items():
            _add_requirement(requirements, "hint", f"{key}: {value}", "P1", ...)
```

**问题**: 结构化的 `focus_areas`（带 area/weight/reason）、`layer2_hints`（带角色分组）、`anti_patterns` 被拍平为 `"{key}: {value}"` 字符串。例如：
```
"focus_areas: [{'area': '调度算法', 'weight': 0.30, ...}]"
```
这种字符串化的 REQ 无法被下游 Worker 程序化使用——Worker 看到的是不可解析的字符串。

**建议修复**:
- `solution_pro_hints` 应该像 `guardrails` 一样在 `frozen_spec.json` 中保持原结构透传（frozen_spec.py:173 已经做了 `solution_pro_hints_raw` 的透传，这很好）
- 移除 142-148 行的 `_add_requirement` 展平逻辑（因为它既丢失结构又产生冗余）
- 确保 `task_builder.py` 使用结构化版本而非展平后的 hint REQ

---

### [9] [P2] [不一致] user_directives 字段位置不一致

**Spec Pro 模型定义**: `models.py:136` — `LivingSpec.user_directives` 是**顶层字段**
```python
user_directives: List[Dict[str, Any]] = field(default_factory=list)
```

**merge_spec.py 实际写入**: `merge_spec.py:230` — 写入 `confirmed.user_directives`
```python
confirmed = spec.setdefault("confirmed", {})
directives = confirmed.setdefault("user_directives", [])
```

**问题**: 模型定义在顶层，实际写入在 confirmed 层下游。`frozen_spec.py` 也不读取 `user_directives`（见 [2]），所以这个不一致目前没有直接 bug，但增加了理解成本。

**建议修复**:
- 确认 `user_directives` 应该在顶层还是 confirmed 层
- 如果在 confirmed 层（更符合"用户确认的指令"语义），更新 `LivingSpec` dataclass 定义
- 如果在顶层，修改 `merge_spec.py` 写入路径和 `coordinator.py` 中 AssessWorker 的读取路径

---

## 消费矩阵（完整性概览）

| Spec Pro 产出字段 | frozen_spec.py 消费 | task_builder.py 消费 | 实际被 Worker 使用 |
|---|:---:|:---:|:---:|
| `confirmed.objective` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.pain_points` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.success_metrics` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.users` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.key_scenarios` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.capabilities.*` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.quality_attributes` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.constraints.*` | ✅ REQ | ✅ 全局理解 | ✅ |
| `confirmed.integration.*` | ✅ REQ | 部分 | 部分 |
| `confirmed.risks_and_assumptions` | ✅ REQ | 部分 | 部分 |
| `guardrails.*` | ✅ REQ | ✅ 研究边界 | ✅ |
| `solution_pro_hints.focus_areas` | ✅ 展平为 REQ | ✅ 重点关注领域 | ✅ |
| `solution_pro_hints.layer2_hints` | ✅ 展平为 REQ | ❌ **未消费** | ❌ |
| `solution_pro_hints.anti_patterns` | ✅ 展平为 REQ | ❌ **未消费** | ❌ |
| `route_recommendation` | ❌ **未读取** | ❌ **未读取** | ❌ |
| `user_directives` | ❌ **未读取** | ❌ **未读取** | ❌ |
| `inferred_pending` | ❌ **未读取** | ❌ **未读取** | ❌ |
| `requirement_annotations` | ✅ _merge_annotations | ❌ context_note 未被 Worker 使用 | ❌ |
| `inferred`（顶层） | ❌ **未读取** | ❌ **未读取** | ❌ |

---

## 总结

**断裂类问题（3 个 P0 + 3 个 P1）**:
- `route_recommendation`、`user_directives/deliberately_omitted`、`inferred_pending` 是完整的 Spec Pro 产出，Solution Pro 完全零消费。它们各自都有明确的价值，但当前是"写了没人看"
- `layer2_hints` 和 `anti_patterns` 是 solution_pro_hints 的子字段，被 StructureWorker 精心生成但没有下游 Worker 使用
- `requirement_annotations` 的 context_note/dependencies/potential_conflicts 被合并到 REQ 但没有 Worker prompt 引用

**冗余/不一致问题（3 个 P1/P2）**:
- `executive_summary` 和 task_builder 各自重建上下文，逻辑重复且字段名不一致
- `solution_pro_hints` 被展平为字符串化 REQ 后语义丢失
- `user_directives` 的字段位置在模型定义和实际写入间不一致

**优先级建议**:
1. **P0-2 (user_directives)**: 最危险 — Solution Pro 可能追问已被用户明确拒绝的维度，直接破坏用户体验
2. **P0-1 (route_recommendation)**: 最有价值 — 复杂度评分和引擎推荐对 Solution Pro 的动态调整有意义
3. **P0-3 (inferred_pending)**: 信息丢失 — 待确认推断是 Spec Pro 的重要增值
4. **P1 组**: 结构性改进，建议在上述修复后统一处理
