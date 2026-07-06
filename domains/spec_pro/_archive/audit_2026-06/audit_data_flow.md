# Spec Pro 数据流完整性审计报告

**审计角色**: Orchestrator Worker 数据流完整性审计员
**审计范围**: coordinator.py → Worker 执行链 → 文件传递 → 脚本 CLI 参数
**审计方法**: 逐轮模拟完整执行链，检查输入/输出衔接、格式一致性、CLI 参数匹配
**审计日期**: 2026-06-02

---

## P0 — 数据流断裂（会导致流程无法继续）

---

### [P0-01] [P0] [coordinator.py:_init_phase_instructions L484-531]

**问题描述**: Round 1 (init 阶段) 的 **Step 4/5/6/7 描述了 round_result.json 和 conversation_log.json 的写入，但没有给 Orchestrator Worker 下达任何 exec 命令或 write 指令来实际写这些文件**。

init 阶段指令中：
- Step 4 展示了 round_result.json 的 JSON 格式，但只说"读取以下文件...写入 round_result.json"，没有 `python3` 命令或 `write` 操作。
- Step 5 展示了 append_trajectory 的 exec 命令 ✅ (有)
- Step 6 展示了 conversation_log.json 的格式，但没有调用 `update_conversation_log.py` 的命令。
- Step 7 **不存在**于 init 阶段（collecting 阶段有 Step 7）。

**影响**: 
- `spec/round_result.json` 不会被创建 → `coordinator.read_round_output()` 返回 "round_result.json not found" → `is_done()` 永远返回 False → Round 2 无法正确判断上一轮状态。
- `spec/conversation_log.json` 只有空数组（init_session 初始化的），Round 1 的对话记录不会被追加 → Round 2+ 的"已问去重规则"无法工作（需要读取历史 meta_directives）。

**建议修复**: 
在 init 阶段指令末尾增加显式指令：
```
## Step 4-Write: 写入 round_result.json
使用 write 工具将 Step 4 汇总的 JSON 写入 {Blackboard}/spec/round_result.json

## Step 7: 更新 conversation_log.json
执行命令:
python3 .deepflow/domains/spec_pro/update_conversation_log.py {Blackboard} 1 init \
  --questions_file {Blackboard}/stages/round_01_questions.json \
  --user_response_file {Blackboard}/spec/input.md \
  --parsed_summary "[ParseWorker 解析摘要]" \
  --quality_after [quality_report.json overall_score] \
  --inferences_created [living_spec.json inferred 层数量]
```

---

### [P0-02] [P0] [coordinator.py:_collecting_phase_instructions L540-740]

**问题描述**: collecting 阶段的 **Step 6 (branching) 和 Step 7 同样缺少 round_result.json 和 conversation_log.json 的显式写入指令**。

collecting 阶段有三个分支：
- 分支 A (停滞检测): 描述了 StructureWorker 写 round_result.json ✅ (由 StructureWorker 写)
- 分支 B (质量达标): HarnessWorker 写 harness_report.json，然后 StructureWorker 写 round_result.json ✅
- 分支 C (未达标): QuestionWorker 写 questions.json 到 stages/，然后"汇总到 round_result.json"但**没有写指令** ❌

此外，Step 7 描述了 conversation_log.json 的格式，但**没有调用 update_conversation_log.py 的 exec 命令**。

**影响**:
- 分支 C 的 round_result.json 不会被写入 → coordinator.read_round_output() 失败 → 流程卡死。
- conversation_log.json 在所有 collecting 轮次都不会更新 → 已问去重规则在 Round 2+ 同样失效。

**建议修复**:
在分支 C 末尾添加：
```
汇总完成后，使用 write 工具将 round_result.json 写入 {Blackboard}/spec/round_result.json
```

在 Step 7 末尾添加：
```
执行命令更新对话日志:
python3 .deepflow/domains/spec_pro/update_conversation_log.py {Blackboard} {round_num} collecting \
  --questions_file {Blackboard}/stages/round_{pp}_questions.json \
  --user_response_file {Blackboard}/spec/user_response_round_{round_num}.md \
  --parsed_summary "[ResponseWorker 解析摘要]" \
  --quality_before [上轮分数] \
  --quality_after [本轮分数] \
  --inferences_created [新增推断数] \
  --inferences_confirmed [确认数] \
  --inferences_rejected [拒绝数]
```

---

### [P0-03] [P0] [coordinator.py:_confirmation_phase_instructions L272-276]

**问题描述**: confirmation 阶段的 revise 分支中，merge_spec.py 的 `--revisions` 命令**可能缺少第 3 个参数**。

coordinator.py 中的指令：
```
python3 .deepflow/domains/spec_pro/merge_spec.py --revisions {Blackboard}/spec/user_confirmation.md {Blackboard}/spec/living_spec.json
```

merge_spec.py 的 `main()` 中：
```python
if sys.argv[1] == "--revisions":
    confirmation_path = sys.argv[2]  # user_confirmation.md
    living_spec_path = sys.argv[3]   # living_spec.json
```

这里看起来 CLI 参数数量匹配（`--revisions` 后跟 2 个路径 = sys.argv 长度 4）。但存在**语义问题**：

`user_confirmation.md` 的扩展名是 `.md`，但 `apply_revisions()` 用 `json.load()` 读取它。coordinator.py 的 `build_confirmation_task()` 中写入的代码是：
```python
json.dump(user_confirmation, f, ...)  # 实际写入的是 JSON
```

虽然实际内容确实是 JSON，但 `.md` 扩展名会误导后续维护者。

**影响**: 当前不会崩溃（因为写入的是 JSON 内容），但扩展名与内容格式不一致，维护风险高。

**建议修复**: 将 `user_confirmation.md` 改为 `user_confirmation.json`，同步更新 coordinator.py 中所有引用该文件名的地方。

---

## P1 — 数据流不一致（可能导致意外行为或质量下降）

---

### [P1-01] [P1] [coordinator.py:_init_phase_instructions L520-524]

**问题描述**: Round 1 的 Step 3 (QuestionWorker) 指令中要求读取 `{Blackboard}/stages/round_01_questions.json` 用于"已问去重规则"的自检，但该文件**正是 QuestionWorker 本轮要输出的文件**。这是一个自引用循环。

```
- 读取: {Blackboard}/stages/round_01_questions.json (本轮已生成问题,用于自检去重)
- 写入: {Blackboard}/stages/round_01_questions.json
```

**影响**: 
- Round 1 时该文件不存在 → read 操作失败或返回空 → 去重逻辑无数据可用（无害但不必要）。
- 对 Orchestrator Worker 造成认知混乱：先读后写同一个文件，语义上不合理。
- collecting 阶段的 Step 6C 正确使用了上轮文件 (`round_{pp}_questions.json`)，init 阶段应保持一致。

**建议修复**: 
在 Round 1 的 QuestionWorker 输入列表中**删除** `stages/round_01_questions.json` 的读取指令，或标注为"如果存在则读取，首次运行时可能不存在"。

---

### [P1-02] [P1] [coordinator.py:_collecting_phase_instructions L680-689]

**问题描述**: Process Guard 输出如何注入到 QuestionWorker 的机制**不完整**。

Step 3 的 exec 命令：
```
python3 .deepflow/domains/spec_pro/process_guard.py {Blackboard} {round_num}
```
该命令输出 JSON 到 stdout。指令说"**保存 Process Guard 输出**，后续注入到 QuestionWorker"，但：
1. 没有说明如何"保存"（写入文件？内存变量？）。
2. Step 6C 的 QuestionWorker prompt 中用 `[Step 3 的输出]` 作为占位符，但没有指定 Orchestrator 如何提取 process_guard.py 输出的 `adjustment_instruction` 字段。
3. process_guard.py 输出完整 JSON (`{"anomalies": [...], "adjustment_instruction": "..."}`)，但注入到 QuestionWorker 的应该是 `adjustment_instruction` 的文本值，不是完整 JSON。

**影响**:
- 如果 Orchestrator 直接把整个 JSON 字符串注入到 prompt，QuestionWorker 会收到大量 JSON 噪音，而不是人类可读的调整指令。
- 如果 Orchestrator 不知道要提取 `adjustment_instruction` 字段，D4 (Process Guard 有力修复) 机制完全失效。

**建议修复**:
1. Step 3 指令改为：
```
## Step 3: Process Guard 检查
执行命令并捕获输出:
python3 .deepflow/domains/spec_pro/process_guard.py {Blackboard} {round_num}

将输出保存为 {Blackboard}/spec/process_guard_result.json
读取 adjustment_instruction 字段，如果非空则保存为 {Blackboard}/spec/process_guard_adjustment.md
```

2. Step 6C 的 QuestionWorker prompt 中改为：
```
Process Guard 调整指令: 读取 {Blackboard}/spec/process_guard_adjustment.md 的内容
```

---

### [P1-03] [P1] [coordinator.py L548-570 & merge_spec.py L280-290]

**问题描述**: collecting 阶段 Step 2 的 merge_spec.py 命令与 Step 1.5 的 fallback 命令之间存在**数据格式假设不一致**的风险。

Step 1.5 fallback:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py response {Blackboard}/stages/round_{nn}_response.json
```

worker_fallback.py 的 response fallback 输出：
```python
"response": {
    "input_guard": {"valid": False},
    "parsed_updates": {},
    "meta_signals": {},
}
```

merge_spec.py 的 `merge_spec()` 函数期望 `response` 中包含 `parsed_updates`（可以为空字典 ✅），`inference_responses`（可以为空列表 ✅），`new_inferences`（可以为空列表 ✅）。

问题在于：fallback 输出**没有** `new_inferences` 和 `inference_responses` 字段（只有 `parsed_updates` 和 `meta_signals` 和 `input_guard`）。merge_spec.py 中：
- `merge_inferred()` 调用 `response.get("inference_responses", [])` → 安全 ✅
- `merge_inferred()` 调用 `response.get("new_inferences", [])` → 安全 ✅
- `merge_guardrails()` 调用 `response.get("guardrails", {})` → 安全 ✅

所以这里实际上是安全的，但 **fallback 输出缺少 `guardrails` 字段**，如果 future 的 merge_spec 增加了非 `.get()` 的安全访问，就会崩溃。

**影响**: 当前代码安全，但 fallback 数据结构与 merge_spec 的期望字段不完全对齐，future 维护风险。

**建议修复**: 在 worker_fallback.py 的 response fallback 中增加缺失字段：
```python
"response": {
    "input_guard": {"valid": False},
    "parsed_updates": {},
    "meta_signals": {},
    "guardrails": {},
    "inference_responses": [],
    "new_inferences": [],
    "user_directives": [],
}
```

---

### [P1-04] [P1] [coordinator.py L694-700 & process_guard.py L94-99]

**问题描述**: process_guard.py 的 `check_progress_rate()` 和 utils.py 的 `check_process_guard()` 使用**不同的进度检查逻辑**，存在两套实现。

process_guard.py：
```python
if delta < min_d - 2:  # 有 ±2 容差
```

utils.py：
```python
if delta < expected_range[0] and trajectory[i]["overall_score"] < 75:  # 额外检查 overall_score
```

coordinator.py 的 exec 命令调用的是 `process_guard.py`，但 orchestrator.md 中的文档描述的预期范围与 process_guard.py 一致。utils.py 的版本永远不会被 coordinator 调用（没有 exec 命令引用它）。

**影响**: 
- 代码冗余，维护两套逻辑容易 divergence。
- 如果未来有人误改为调用 utils.py 的 process_guard 命令，检查行为会不同。

**建议修复**: 删除 utils.py 中的 `check_process_guard()` 函数，或让 process_guard.py import 并复用 utils.py 的实现。在文档中明确唯一的入口是 `process_guard.py`。

---

### [P1-05] [P1] [coordinator.py L536-539]

**问题描述**: Round 1 的 Step 5 (append_trajectory) 命令**缺少 `inferences_validated` 参数**，而 collecting 阶段的 Step 5 包含该参数。

Round 1:
```
python3 ...worker_fallback.py append_trajectory {Blackboard} 1 [score] [level] [questions_count]
```

collecting:
```
python3 ...worker_fallback.py append_trajectory {Blackboard} {round_num} [score] [level] [questions_count] [inferences_validated]
```

worker_fallback.py 中 `inferences_validated` 有默认值 0，所以不会崩溃。但 Round 1 确实创建了推断（ParseWorker 的 inferred 层），应该记录实际的 inferences_validated=0（因为是首轮，没有推断被确认）。

**影响**: 轻微。轨迹条目中 `inferences_validated` 字段在 Round 1 正确为 0（默认值），但命令参数不一致可能导致维护者困惑。

**建议修复**: 在 Round 1 的 append_trajectory 命令中显式添加第 7 个参数 `0`，保持与 collecting 阶段格式一致。

---

## P2 — 风格/维护性问题（不影响当前运行，但建议改进）

---

### [P2-01] [P2] [coordinator.py:_init_phase_instructions]

**问题描述**: init 阶段的 Step 6 要求 "截断500字"，但 Orchestrator Worker 没有被告知如何截断。`update_conversation_log.py` 的 CLI 接口接受 `--user_response` 或 `--user_response_file`，但没有截断参数。

**影响**: 如果用户初始输入超过 500 字，conversation_log.json 中会存储完整内容，与规范描述不一致。

**建议修复**: 在指令中增加截断说明，或让 update_conversation_log.py 内置截断逻辑。

---

### [P2-02] [P2] [coordinator.py:build_annotation_task]

**问题描述**: `build_annotation_task()` 构建的 RequirementStructuringWorker prompt 引用了 `annotate_requirements(confirmed)` 函数调用，但该函数在 `requirement_structuring.py` 中的签名是 `annotate_requirements(living_spec, llm_call_fn)`，需要两个参数。

prompt 中说：
```
2. 调用 annotate_requirements(confirmed) 进行 LLM 标注
```

实际函数签名：
```python
def annotate_requirements(living_spec: Dict[str, Any], llm_call_fn: Callable) -> Optional[List]
```

**影响**: 这个 prompt 是给 RequirementStructuringWorker（LLM Agent）看的，不是给代码执行的。但 LLM 可能会困惑于如何调用这个函数，因为它没有 `llm_call_fn`。

**建议修复**: 重写 prompt 中的执行步骤描述，明确 RequirementStructuringWorker 的执行方式（直接执行标注逻辑，而不是调用 Python 函数）。

---

### [P2-03] [P2] [coordinator.py L460-462]

**问题描述**: `_build_orchestrator_task()` 中对 `{Blackboard}` 占位符的替换是**单次字符串替换** (`str.replace`)，如果 prompt 中其他位置出现了字面量 `{Blackboard}`（不是作为路径的一部分），也会被意外替换。

```python
task = task.replace("{Blackboard}", self.base_path)
```

当前代码中所有 `{Blackboard}` 都是路径占位符，没有冲突。但如果未来有人向 prompt 中添加包含 `{Blackboard}` 的示例代码块，就会被误替换。

**影响**: 当前无问题，但缺乏防护。

**建议修复**: 使用更唯一的占位符如 `__BLACKBOARD_PATH__` 或在替换后验证结果。

---

### [P2-04] [P2] [worker_fallback.py L19-55]

**问题描述**: worker_fallback.py 的 `FALLBACKS` 字典中，各 worker 类型的 fallback 数据结构**与对应 Worker prompt 中的输出格式不完全一致**。

例如 parse fallback:
```python
"parse": {"status": "timeout", "parsed": {}, "inferred": [], "confidence": 0}
```

但 parse.md 的输出格式要求 `stages/round_01_parse.json` 包含：
```json
{"status": "completed", "parsed": {...}, "inferred": [...], "confidence_note": "..."}
```

fallback 缺少 `confidence_note`，使用 `status: "timeout"` 而非 `"completed"`。merge_spec.py 不消费 parse 的输出（只消费 response.json），所以当前不影响。但如果未来有代码读取 parse 输出，可能因字段差异而失败。

**影响**: 当前不影响数据流，但 fallback 输出格式与 Worker 输出格式不完全兼容。

**建议修复**: 在 FALLBACKS 中补充各 Worker 输出的所有必需字段，或使用默认值填充。

---

### [P2-05] [P2] [merge_spec.py L139-143]

**问题描述**: `merge_inferred()` 中将 confirmed 的推断移入 confirmed 层时，使用 `dim == "risks"` 映射到 `risks_and_assumptions.risks`，但 `merge_confirmed()` 中 risks 字段的合并路径是 `risks_and_assumptions`。两条路径的命名不一致（一个用 "risks"，一个用 "risks_and_assumptions"）。

```python
# merge_inferred 中:
elif dim == "risks":
    ra = c.setdefault("risks_and_assumptions", ...)
    append_unique(ra.setdefault("risks", []), [content])

# merge_confirmed 中:
new_risks = updates.get("risks_and_assumptions", {})
```

**影响**: 推断确认和常规确认使用不同的键名访问同一数据，增加了维护负担。

**建议修复**: 统一使用 `risks_and_assumptions` 作为维度名，或在 `merge_inferred` 中添加 `"risks_and_assumptions"` 的 elif 分支。

---

## 数据流总览图

```
Round 1 (init):
  input.md ──ParseWorker──→ round_01_parse.json + living_spec.json
  living_spec.json ──AssessWorker──→ quality_report.json
  living_spec.json + quality_report.json ──QuestionWorker──→ round_01_questions.json
  round_01_questions.json + quality_report.json ──[P0-01: 缺写指令]──→ round_result.json ⚠️
  quality_report.json ──append_trajectory──→ quality_trajectory.json ✅
  [P0-01: 缺写指令] ──→ conversation_log.json ⚠️

Round N (collecting):
  user_response_round_NN.md + living_spec.json + round_NN-1_questions.json
    ──ResponseWorker──→ round_NN_response.json
  round_NN_response.json + living_spec.json ──merge_spec.py──→ living_spec.json ✅
  quality_trajectory.json ──process_guard.py──→ stdout → [P1-02: 注入机制不完整] ⚠️
  living_spec.json ──AssessWorker──→ quality_report.json ✅
  quality_report.json ──append_trajectory──→ quality_trajectory.json ✅
  ┌─ 分支 A (停滞): living_spec.json + quality_report.json ──StructureWorker──→ round_result.json ✅
  ├─ 分支 B (达标): living_spec.json ──HarnessWorker──→ harness_report.json
  │                 living_spec.json + harness_report.json ──StructureWorker──→ round_result.json ✅
  └─ 分支 C (未达标): living_spec.json + quality_report.json ──QuestionWorker──→ round_NN_questions.json
                      round_NN_questions.json + quality_report.json ──[P0-02: 缺写指令]──→ round_result.json ⚠️
  [P0-02: 缺写指令] ──→ conversation_log.json ⚠️

Confirmation:
  user_confirmation.json ──confirm分支──→ living_spec.json + quality_report.json
    ──StructureWorker──→ round_result.json ✅
  user_confirmation.json ──revise分支──→ merge_spec.py --revisions ──→ living_spec.json ✅
    living_spec.json ──AssessWorker──→ quality_report.json ✅
    达标 → HarnessWorker → StructureWorker → round_result.json ✅
    未达标 → QuestionWorker → round_result.json
```

## 审计结论

| 严重性 | 数量 | 关键问题 |
|--------|------|---------|
| P0 | 3 | round_result.json 缺写指令 (init + collecting 分支 C)，conversation_log.json 缺更新命令 |
| P1 | 5 | Process Guard 注入机制不完整、Round 1 自引用文件、fallback 数据结构不完整、双份 process_guard 实现、参数不一致 |
| P2 | 5 | 截断逻辑缺失、函数签名引用错误、占位符替换防护不足、fallback 格式差异、键名不一致 |

**最关键修复优先级**: P0-01 → P0-02 → P0-03 → P1-02 → P1-01

---

*审计完成。共检查 7 个 Python 源文件 + 6 个 prompt 模板 + 2 个配置/模型文件。*
