# Spec Pro — Prompt 契约一致性审计报告

> **审计员**: Prompt Contract Auditor (subagent)  
> **审计日期**: 2026-06-02  
> **审计范围**: 7 个 Worker Prompt 之间的数据格式契约对齐  
> **审查文件**:  
> - `domains/spec_pro/prompts/parse.md` (v2.1.0)  
> - `domains/spec_pro/prompts/parse_response.md` (v2.1.0)  
> - `domains/spec_pro/prompts/assess.md` (v2.1.0)  
> - `domains/spec_pro/prompts/guide.md` (v2.1.0)  
> - `domains/spec_pro/prompts/structure.md` (v2.1.0)  
> - `domains/spec_pro/prompts/harness.md` (v2.1.0)  
> - `domains/spec_pro/coordinator.py`  
> - `domains/spec_pro/merge_spec.py`  
> - `domains/spec_pro/models.py`  

---

## 审计矩阵总览

| # | 生产者 | 输出文件 | 消费者 | 状态 |
|---|--------|---------|--------|------|
| 1 | ParseWorker | round_01_parse.json | (内部用，无下游消费者) | ✅ |
| 2 | ParseWorker | living_spec.json | AssessWorker / merge_spec.py | ⚠️ P2 |
| 3 | ResponseWorker | round_NN_response.json | merge_spec.py | 🔴 P0 + P1 |
| 4 | AssessWorker | quality_report.json | QuestionWorker / coordinator | ✅ |
| 5 | QuestionWorker | round_NN_questions.json | coordinator Step 4 / conversation_log | ✅ |
| 6 | StructureWorker | round_result.json | coordinator.read_round_output() | ⚠️ P1 |
| 7 | HarnessWorker | harness_report.json | StructureWorker / coordinator | ✅ |

---

## 详细问题列表

---

### [P0-1] 严重性: P0 (断裂性) — 4 个 confirmed 维度字段无写入路径

**生产者**: parse_response.md  
**文件**: `prompts/parse_response.md` — "有效需求声明识别" 表格

**消费者**: merge_spec.py → `merge_confirmed()` / `merge_user_directives()` + structure.md 摘要模板

**不匹配描述**:

parse_response.md 的"有效需求声明识别"表格定义了 4 个用户指令类型及其到 `confirmed` 层的映射：

| 用户表达 | 类型 | parse_response.md 声称写入的 confirmed 字段 |
|---------|------|-------------|
| "参考业界规范/对标 XXX" | `benchmark_reference` | `confirmed.benchmark_references` |
| "你们来设计/这是设计层面的事" | `design_delegation` | `confirmed.design_delegations` |
| "自适应/智能调整" | `adaptive_expectation` | `confirmed.adaptive_requirements` |
| "高质量优先/不妥协" | `quality_priority` | `confirmed.quality_priorities` |
| "参考业界最佳实践" | `industry_reference` | `confirmed.industry_references` |

但是：

1. **parse.md** 定义的 `living_spec.json` confirmed 层 schema 中**不存在**这些字段。confirmed 只包含：`objective`, `pain_points`, `success_metrics`, `users`, `key_scenarios`, `capabilities`, `quality_attributes`, `constraints`, `integration`, `risks_and_assumptions`。
2. **merge_spec.py** 的 `merge_confirmed()` 函数**不处理**这些字段（只处理 10 个已知维度 + `user_directives`）。
3. **models.py** `LivingSpec` dataclass 的 `confirmed` 默认值中也**没有**这些字段。
4. **structure.md** 的摘要模板引用了 `[benchmark_references]`, `[design_delegations]`, `[adaptive_requirements]`, `[quality_priorities]`，但这些字段永远不会被填充 → 摘要中这些行将始终为空。

**断裂路径**:
```
parse_response.md 声称写入 confirmed.benchmark_references
    → merge_spec.py 不处理此字段 → 不写入 living_spec.json
    → structure.md 摘要模板引用 [benchmark_references] → 始终为空
```

**建议修复**:

方案 A（推荐）: 删除 parse_response.md 中"提取到 Living Spec"列里的独立 confirmed 字段映射，统一改为写入 `confirmed.user_directives` 数组（已在 models.py 和 merge_spec.py 中有完整支持）。修改 parse_response.md 表格：

```markdown
| 用户表达 | 类型 | 提取到 Living Spec |
|---------|------|-------------------|
| "参考业界规范/对标 XXX" | benchmark_reference | `confirmed.user_directives` 数组中新增一条 |
| ... | ... | 同上 |
```

同时修改 structure.md 摘要模板，从 `user_directives` 中读取并分类展示，而非从独立的 confirmed 字段读取。

方案 B: 在 parse.md living_spec schema + models.py + merge_spec.py 中新增这 5 个 confirmed 字段。工作量更大但语义更清晰。

---

### [P0-2] 严重性: P0 (断裂性) — meta_signals 字段名不一致

**生产者**: parse_response.md  
**文件**: `prompts/parse_response.md` — 输出 schema 中 `meta_signals` 定义

**消费者**: coordinator.py — `_collecting_phase_instructions()` Step 7 的"已问去重规则"

**不匹配描述**:

parse_response.md 定义的 `meta_signals` 结构：
```json
"meta_signals": {
  "user_said_enough": false,
  "user_wants_pivot": false,
  "new_topic_detected": false
}
```

但 coordinator.py `_collecting_phase_instructions()` 分支 C 的 QuestionWorker 注入指令中引用了：
```
3. 读取上轮 response.json 的 meta_signals
   - 如果 directive_stop_asking = true, 遵守 stop_asking_dimensions
   - 如果 user_said_enough = true, 减少问题数量到 1-2 个
```

`directive_stop_asking` 和 `stop_asking_dimensions` **不存在于** parse_response.md 的 `meta_signals` schema 中。

**断裂路径**:
```
coordinator.py 引用 response.meta_signals.directive_stop_asking
    → parse_response.md 未定义此字段
    → QuestionWorker 找不到 directive_stop_asking → 规则 #3 永远不生效
```

**建议修复**:

在 parse_response.md 的 `meta_signals` 输出 schema 中新增两个字段：
```json
"meta_signals": {
  "user_said_enough": false,
  "user_wants_pivot": false,
  "new_topic_detected": false,
  "directive_stop_asking": false,
  "stop_asking_dimensions": []
}
```

同时在 parse_response.md 的"元信号检测"规则表中补充：
- "不要再问 X" / "X 不需要考虑" → `directive_stop_asking: true`, `stop_asking_dimensions: ["X的维度"]`

---

### [P0-3] 严重性: P0 (格式不一致) — proposal vs summary 的 quality 对象结构不同

**生产者**: structure.md  
**文件**: `prompts/structure.md` — 三种 action 模式的输出 schema

**消费者**: coordinator.py — `read_round_output()` + 前端展示逻辑

**不匹配描述**:

structure.md 定义了三种 action 模式的 `round_result.json` 格式：

**模式 "proposal"** 的 quality 对象（完整）:
```json
"quality": {
  "overall_score": 62,
  "level": "B",
  "dimension_scores": {"objective": {"score":..., "delta":..., "change":...}, ...7个维度...},
  "top_improvements": [...],
  "top_missing": [...]
}
```

**模式 "summary"** 的 quality 对象（精简）:
```json
"quality": {
  "overall_score": 82,
  "level": "A"
}
```

**模式 "done"** 的 quality 对象（同 summary，精简）:
```json
"quality": {
  "overall_score": 82,
  "level": "A"
}
```

问题：
1. consumer 代码（coordinator.py `read_round_output()`）只读取 `action` 字段做状态转换，不读 quality → **目前不破裂**。
2. 但前端展示代码（未在本次审计范围内）如果假设 quality 始终有 `dimension_scores`，会在 summary/done 模式下崩溃。
3. coordinator.py 的 init 和 collecting 阶段指令中构造的 round_result 模板都包含 `dimension_scores`，与 structure.md 的 summary 模式不一致。

**建议修复**:

统一所有 5 种 action（questions / proposal / summary / done / safety_stop）的 quality 对象为完整格式。summary 和 done 模式也应包含 `dimension_scores`、`top_improvements`、`top_missing`，因为 quality_report.json 中已有这些数据，无需额外成本。

修改 structure.md 的 summary 和 done 模式：
```json
"quality": {
  "overall_score": 82,
  "level": "A",
  "dimension_scores": { ... },
  "top_improvements": [ ... ],
  "top_missing": [ ... ]
}
```

---

### [P1-1] 严重性: P1 — user_directives 嵌套层级不一致

**生产者**: parse_response.md  
**文件**: `prompts/parse_response.md` — 输出 schema

**消费者**: merge_spec.py — `merge_user_directives()` + assess.md

**不匹配描述**:

parse_response.md 的输出 schema 中，`user_directives` 放在 `parsed_updates` 下：
```json
"parsed_updates": {
  ...
  "user_directives": [
    {"directive": "...", "content": "...", "dimension": "...", "reason": "...", "status": "confirmed"}
  ]
}
```

但 merge_spec.py 的 `merge_user_directives()` 函数有两处回退读取路径：
```python
user_directives = parsed_updates.get("user_directives") or response.get("user_directives", [])
```

这意味着它也接受 `response.user_directives`（顶层），但 parse_response.md 的 schema 中 `user_directives` 只在 `parsed_updates` 下，不在顶层。

此外，assess.md 的 deliberately_omitted 规则说"检查 `confirmed.user_directives` 数组"，这是正确的——因为 merge_spec.py 会将其合并到 `confirmed.user_directives`。但 parse.md 的初始 living_spec.json schema 中 confirmed 层**没有** user_directives 字段。

**断裂风险**: Round 1 的 AssessWorker 读取 living_spec.json 时，`confirmed.user_directives` 不存在（因为 Round 1 没有 ResponseWorker 产出）→ assess.md 的"先检查 confirmed.user_directives"步骤会落空。

**建议修复**:

1. 在 merge_spec.py 中统一为只读取 `parsed_updates.user_directives`，删除 `or response.get("user_directives", [])` 回退路径，或反之在 parse_response.md schema 中同时在顶层添加 `user_directives`。
2. 在 assess.md 中添加说明："Round 1 时 confirmed.user_directives 不存在，跳过此检查"。

---

### [P1-2] 严重性: P1 — coordinator.py init 阶段 dimension_scores 与 assess.md output schema 类型不匹配

**生产者**: assess.md  
**文件**: `prompts/assess.md` — 输出 schema

**消费者**: coordinator.py — `_init_phase_instructions()` Step 4 汇总模板

**不匹配描述**:

assess.md 输出 quality_report.json 的 dimensions 数组格式：
```json
"dimensions": [
  {
    "dimension": "objective",
    "name": "目标与痛点",
    "weight": 0.20,
    "score": 85,
    "reasoning": "...",
    "missing_items": []
  }
]
```

这是一个**数组**，按 dimension 字段查找需要遍历。

但 coordinator.py init 阶段 Step 4 的模板假设可以直接用维度名取分数：
```json
"dimension_scores": {
  "objective": {"score": [分数], "delta": 0, "change": "new"},
  ...
}
```

coordinator 没有提供从 dimensions 数组中提取各维度分数的代码逻辑——这依赖 Orchestrator Worker 或 worker_fallback.py 来完成。查看 worker_fallback.py（如果存在）或依赖 LLM 正确解析 dimensions 数组。

**风险**: 如果 fallback 脚本不存在或 LLM 错误解析 dimensions 数组，round_result.json 的 dimension_scores 将为空或错误。

**建议修复**:

在 coordinator.py 或 worker_fallback.py 中添加明确的 dimensions 数组解析逻辑：
```python
# 从 dimensions 数组构建 dimension_scores 字典
dim_scores = {}
for d in quality_report.get("dimensions", []):
    dim_scores[d["dimension"]] = {
        "score": d["score"],
        "delta": 0,
        "change": "new"
    }
```

---

### [P2-1] 严重性: P2 — parse.md confirmed 层缺少 user_directives 字段

**生产者**: parse.md  
**文件**: `prompts/parse.md` — 文件 2 living_spec.json schema

**消费者**: assess.md + merge_spec.py

**不匹配描述**:

parse.md 定义的 confirmed 层 schema 不包含 `user_directives` 字段：
```json
"confirmed": {
  "objective", "pain_points", "success_metrics", "users", "key_scenarios",
  "capabilities", "quality_attributes", "constraints", "integration",
  "risks_and_assumptions"
}
```

但：
- merge_spec.py `merge_user_directives()` 使用 `confirmed.setdefault("user_directives", [])` 动态创建
- assess.md 引用 `confirmed.user_directives`
- models.py `LivingSpec` dataclass 顶层有 `user_directives` 字段（在 confirmed 外）

**问题**: `user_directives` 在 models.py 中是 LivingSpec 顶层字段，但在 merge_spec.py 中写入 `confirmed.user_directives`。位置不一致。

**建议修复**:

统一位置。推荐方案：在 parse.md 的 living_spec.json confirmed 层中添加 `"user_directives": []`，保持与 merge_spec.py 写入位置一致。同时检查 models.py — 如果顶层 `user_directives` 和 `confirmed.user_directives` 同时存在会造成混淆。

---

### [P2-2] 严重性: P2 — success_metrics 格式不一致

**生产者**: parse.md  
**文件**: `prompts/parse.md` — Step 1 提取表 vs 输出 schema

**消费者**: merge_spec.py — `merge_confirmed()`

**不匹配描述**:

parse.md Step 1 提取表中 success_metrics 定义为对象数组：
```
success_metrics: [{"metric": "GPU利用率", "target": "≥70%"}]
```

但 parse.md 的 `parsed` 输出中没有独立的 success_metrics 字段（只有 `parsed.quality_hints` 列表，是字符串）。

parse.md 的 `confirmed` 层输出 schema 中 success_metrics 是空数组 `[]`，没有指定元素格式。

merge_spec.py 的 `merge_confirmed()` 对 success_metrics 使用 `append_unique()` 字符串级去重：
```python
for field in ["pain_points", "success_metrics", "key_scenarios"]:
    new_items = updates.get(field, [])
    if isinstance(new_items, list):
        append_unique(confirmed.setdefault(field, []), new_items)
```

如果 ResponseWorker 输出 `success_metrics` 为 `[{"metric": "...", "target": "..."}]`（对象），`append_unique()` 会用整个对象做相等比较去重，这是正确的。但如果某些轮次输出为字符串格式 `["GPU利用率≥70%"]`，去重会失效。

**建议修复**:

在 parse.md 和 parse_response.md 中统一 success_metrics 的元素格式为对象 `{"metric": "...", "target": "..."}`，并在 merge_spec.py 中添加基于 `metric` 键的去重逻辑。

---

### [P2-3] 严重性: P2 — guide.md 问题数量规则自相矛盾

**文件**: `prompts/guide.md`

**不匹配描述**:

guide.md 中两处对问题数量的约束不一致：

1. "问题生成规则"第1条: "每轮 3-5 个问题，**不超过 5 个**（硬性限制，超过必须删除优先级最低的）"
2. 同节"问题优先级"标题下: "当可选问题 > 3 个时" — 暗示默认只选 3 个

coordinator.py 中无问题数量验证逻辑。

**风险**: 虽然不导致数据格式断裂，但 LLM 可能在不同轮次输出不同数量的问题（有时 3 个，有时 5 个），导致用户体验不一致。

**建议修复**:

统一为"每轮 **3-5** 个问题，优先 3 个，最多不超过 5 个"。删除"硬性限制"措辞，改为"建议限制"。

---

### [P2-4] 严重性: P2 — harness_report 在 structure.md done 模式中是条件字段

**生产者**: structure.md  
**文件**: `prompts/structure.md` — 模式 B (done) 输出 schema

**消费者**: 下游（Solution Pro 或前端展示）

**不匹配描述**:

structure.md done 模式中：
```json
"harness_report": {如有 harness_report.json 则读取并写入，否则 null}
```

这是一个条件可为 null 的字段，但未在 schema 中标注 `nullable` 或说明哪些情况下为 null。

coordinator.py confirmation 阶段指令中：
```
读取: {Blackboard}/spec/harness_report.json(如果存在)
```

当 overall_score < threshold 且未进入 HarnessWorker 分支时（直接走 QuestionWorker 分支），harness_report.json 不会被生成 → structure.md done 模式中的 harness_report 为 null。

**建议修复**:

在 structure.md 的 done 模式 schema 中明确标注：
```json
"harness_report": null,  // 仅在 HarnessWorker 执行后非 null；质量未达标进入分支 C 时为 null
```

---

## 审计总结

| 严重性 | 数量 | 关键问题 |
|--------|------|---------|
| **P0** | 3 | 4 个 confirmed 维度字段无写入路径（断裂）；meta_signals 字段名不匹配（功能失效）；quality 对象结构不一致 |
| **P1** | 2 | user_directives 嵌套层级不一致 + Round 1 缺失；dimensions 数组 vs 字典类型转换无代码保障 |
| **P2** | 4 | confirmed 层缺少 user_directives 字段定义；success_metrics 格式不统一；问题数量规则自相矛盾；harness_report 条件字段未标注 |

### 修复优先级建议

1. **立即修复 (P0)**: P0-1（4 个 confirmed 字段断裂）→ 这是最高优先级，用户指令声明功能形同虚设
2. **立即修复 (P0)**: P0-2（meta_signals 字段缺失）→ QuestionWorker 去重规则 #3 永远不生效
3. **尽快修复 (P0)**: P0-3（quality 对象统一）→ 防止前端崩溃
4. **本轮迭代修复 (P1)**: P1-1 + P1-2
5. **后续优化 (P2)**: P2-1 至 P2-4

---

*审计完成。共审查 7 对生产者-消费者关系，发现 9 个不一致项（3×P0, 2×P1, 4×P2）。*
