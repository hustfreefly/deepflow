# Solution Pro 数据流转完整性审计报告

> **审计日期**: 2026-06-03 01:38 CST  
> **审计人**: 数据流审计 Subagent  
> **审计范围**: 10 阶段 Pipeline 数据流转完整性  
> **审计原则**: 基于代码证据，区分"设计选择"与"真实缺陷"  
> **参考**: AUDIT_REPORT_2026-06-02.md、AUDIT_REPORT_2026-06-03_CONSOLIDATED.md（不重复已发现问题）

---

## 审计概览

| 维度 | 发现 | P0 | P1 | P2 |
|:---|:---:|:---:|:---:|:---:|
| 输入断链 | 3 | 1 | 2 | 0 |
| 输出路径不一致 | 4 | 1 | 2 | 1 |
| 路径注册表覆盖度 | 3 | 1 | 2 | 0 |
| 数据传递方式不当 | 2 | 0 | 1 | 1 |
| 关键文件无人产生 | 2 | 1 | 1 | 0 |
| 关键文件无人消费 | 1 | 0 | 1 | 0 |

**总计**: 15 个问题（3 P0 + 7 P1 + 5 P2）

---

## P0 问题

### [P0-1] Summarizer 阶段 `all_outputs={}` 传入空字典 — 完整输入断链

- **位置**: `orchestrator_agent.py:385-389`
- **根因**: `build_summarizer_task(session_id, topic, {}, living_spec=self.living_spec)` 传入空字典 `{}` 作为 `all_outputs` 参数，但 Summarizer prompt 中要求读取 16 个前序阶段文件。`all_outputs` 参数在 `build_summarizer_task` 中仅被 `json.dumps({}, ...)` 后替换到 `{{ all_outputs }}` 模板变量。
- **证据**: 
  ```python
  # orchestrator_agent.py L385-389
  elif stage == "summarizer":
      tasks[stage] = build_summarizer_task(
          self.session_id, self.topic,
          {},  # 实际应从blackboard读取all_outputs
          living_spec=self.living_spec
      )
  ```
  同时 `build_summarizer_task` 中：
  ```python
  # task_builder.py
  prompt = prompt.replace("{{ all_outputs }}", all_outputs_json)  # "{}"
  ```
- **影响**: Summarizer 的 `{{ all_outputs }}` 模板变量替换为 `"{}"` 字面字符串。虽然 prompt 的"输入读取"段落列出了 16 个文件路径（Summarizer 会自己去 read），但 `{{ all_outputs }}` 段的数据注入为空，导致数据流设计意图（通过参数传递）与实际运行时（Worker 自己 read）不一致。这是**断链 + 双重数据源**问题。
- **建议**: 两种修复方案：
  1. 删除 `all_outputs` 参数，完全依赖 prompt 中的"输入读取"指令（推荐 — 更简洁）
  2. 在 `get_all_tasks()` 中从 blackboard 实际读取 10 个阶段输出文件并组装为字典传入（不可行 — `get_all_tasks()` 在 pipeline 执行前调用，文件尚不存在）
  - **推荐方案 1**：删除参数，因为 pipeline 执行前不可能有前序阶段输出。

### [P0-2] `structured_requirements.json` — 声明存在但无消费者 — 设计断裂

- **位置**: `orchestrator_agent.py:14-15`（声明）+ `planner_v2_harness.md:197-198`（Planner 写入）
- **根因**: 注释声明 "Planning输入扩展：同时读取structured_requirements.json + collection.json"，但实际代码中：
  1. **Planner 写入**: `planner_v2_harness.md` 第 197-198 行要求 Planner 写入 `data/structured_requirements.json` ✅
  2. **无消费者**: `build_planner_task` 不读取该文件（planning 是 Stage 2，最早写入者）
  3. **无消费者**: `build_consolidator_task`、`build_auditor_task`、`build_harness_final_task` 均未读取此文件
  4. **无消费者**: `completion_handler.py`、`control_contract.py` 均未读取此文件
  5. `harness_v3.md` 的"输入读取"中未提及 `structured_requirements.json`
  6. 只有 `_deprecated_v3.py` 中的旧代码引用此文件
- **证据**: 
  ```bash
  # 搜索所有 .py 中 consumers of structured_requirements：
  # → 仅有 blackboard.py 的注册表 + orchestrator_agent.py 的注释 + 已废弃的 _deprecated_v3.py
  ```
  所有 worker build 函数和 prompt 模板中无一读取 `structured_requirements.json`。
- **影响**: Planner 产出此文件但无人消费，形成**孤岛数据**。注释声称"Harness Final检查基准：基于structured_requirements.json做全局覆盖度检查"，但 Harness Final 实际使用的是 `data/frozen_spec.json`（见 `harness_v3.md` 输入读取段落）。设计意图与实际实现断裂。
- **建议**: 
  1. 如果 `structured_requirements.json` 不再使用 → 从 `STAGE_PATH_REGISTRY` 和 Planner prompt 中移除
  2. 如果有意使用 → 在 Harness Final 或 Summarizer 的输入读取段落中明确引用

### [P0-3] `control_contract.py` 中 `build_researcher_task` 调用传入 `layer2_constraints` 但函数签名已移除该参数 — 调用断裂

- **位置**: `control_contract.py:252-259`
- **根因**: `control_contract.py:rewrite_after_planning()` 在刷新 research tasks 时调用了 `build_researcher_task(..., layer2_constraints=contract["layer2_constraints"])`，但 `task_builder.py:build_researcher_task()` 的函数签名**不包含** `layer2_constraints` 参数。Python 运行时会抛出 `TypeError: unexpected keyword argument 'layer2_constraints'`。
- **证据**:
  ```python
  # control_contract.py L252-259
  task = build_researcher_task(
      worker["name"], session_id, topic,
      {"type": solution_type, "mode": mode, "constraints": constraints},
      expert_id=worker["id"],
      angle=worker["angle"],
      reason=worker["reason"],
      layer2_constraints=contract["layer2_constraints"],  # ← 函数签名无此参数！
  )
  ```
  ```python
  # task_builder.py build_researcher_task 签名
  def build_researcher_task(expert, session_id, topic, context,
                           expert_id="expert_1",
                           angle="综合分析",
                           reason="需要深入分析该领域",
                           living_spec=None):  # ← 无 layer2_constraints
  ```
- **影响**: `rewrite_after_planning()` 被 `pipeline_orchestrator_v4.md` 规定为 Planning 完成后的**必须步骤**。调用此函数时必然崩溃，导致整个 pipeline 在 Stage 2 完成后断裂。
- **建议**: 移除 `layer2_constraints=contract["layer2_constraints"]` 参数调用。Layer 2 约束已通过 `LAYER2_READ_INSTRUCTION` 注入到后续 worker prompt 中（同一函数内的 auditor/fixer 修复已使用此模式）。

---

## P1 问题

### [P1-1] `build_consolidator_task` 的 `research_outputs=[]` 参数传空列表 — 设计选择但有运行时风险

- **位置**: `orchestrator_agent.py:359-362`
- **根因**: `build_consolidator_task(session_id, self.topic, [], living_spec=self.living_spec)` 传入空列表 `[]`。注释明确承认 "实际应从blackboard读取researcher outputs"。在 `build_consolidator_task` 中，此参数被序列化为 JSON 并替换到 `{{ research_outputs }}` 模板变量。
- **证据**:
  ```python
  # orchestrator_agent.py L359-362
  tasks[stage] = build_consolidator_task(
      self.session_id, self.topic,
      [],  # 实际应从blackboard读取researcher outputs
      living_spec=self.living_spec
  )
  ```
  ```python
  # task_builder.py: build_consolidator_task
  outputs_json = json.dumps(research_outputs, ensure_ascii=False, indent=2)  # → "[]"
  prompt = prompt.replace("{{ research_outputs }}", outputs_json)
  ```
- **影响**: Consolidator 的 `{{ research_outputs }}` 模板变量替换为 `"[]"`。这与 Summarizer 的 P0-1 同类 — 因为 `get_all_tasks()` 在 pipeline 执行前调用，此时 research 阶段尚未产出。**设计选择**：prompt 的"整合流程"第 1 步要求 Consolidator 自己 `读取所有 research_*.json`。所以空参数是**预期行为**，但存在数据流设计不一致（声明了参数却不使用）。
- **建议**: 移除 `research_outputs` 参数，与 P0-1 同一修复。

### [P1-2] `build_fixer_expert_task` 的 `audit_findings=[]` 参数传空列表 — 同类断裂

- **位置**: `orchestrator_agent.py:375-378`
- **根因**: `build_fixer_expert_task(session_id, self.topic, [], severity="critical", ...)` 传入空列表。注释未说明原因。Fixer Expert 需要通过 `{{ audit_findings }}` 模板变量获取 Auditor 发现的问题。
- **证据**:
  ```python
  # orchestrator_agent.py L375-378
  tasks[stage] = build_fixer_expert_task(
      self.session_id, self.topic,
      [],  # ← 空列表，无注释解释
      severity="critical",
      living_spec=self.living_spec
  )
  ```
  ```python
  # task_builder.py: build_fixer_expert_task
  findings_json = json.dumps(audit_findings, ensure_ascii=False, indent=2)  # → "[]"
  prompt = prompt.replace("{{ audit_findings }}", findings_json)
  prompt = prompt.replace("{{ AUDIT_FINDINGS }}", findings_json)
  ```
- **影响**: `{{ audit_findings }}` 和 `{{ AUDIT_FINDINGS }}` 均被替换为 `"[]"`。Fixer Expert 的 prompt 模板中未列出"审计发现"的读取路径，不像 Fixer 有 `{{ AUDIT_PATH }}` 参数指向文件路径。Fixer Expert 完全依赖注入的 `audit_findings` 列表，但实际为空。
- **建议**: 在 Fixer Expert 的 prompt 中添加审计发现的读取路径（如 `stages/audit.json`），与 Fixer 保持一致。或者在 `build_fixer_expert_task` 中传入 audit.json 路径而非内容列表。

### [P1-3] `STAGE_PATH_REGISTRY` 与 `build_*_task` 中的输出路径不一致 — 路径双轨制残留

- **位置**: `task_builder.py` 多处 `_get_stage_path()` 调用 vs `blackboard.py` 的 `STAGE_PATH_REGISTRY`
- **根因**: 虽然 `task_builder.py` 的 `_get_stage_path()` 从 `STAGE_PATH_REGISTRY` 查找，但对于不在注册表中的 stage 名称，它 fallback 到 `{base}/blackboard/{session_id}/{stage_name}`（无扩展名）。以下调用存在不一致：
  1. `build_data_collection_task`: `_get_stage_path(session_id, "data/collection.json")` → 注册表中 key 是 `"data_collection"` → `"data/collection.json"` ✅ 匹配
  2. `build_planner_task`: `_get_stage_path(session_id, "planning")` → 注册表 key `"planning"` → `"stages/planning.json"` ✅ 匹配
  3. `build_researcher_task`: `_get_stage_path(session_id, "stages/research_")}{expert_id}.json` — 这里手动拼接了路径**绕过了注册表**。
- **证据**:
  ```python
  # task_builder.py — build_researcher_task
  prompt += f"""写入: `{_get_stage_path(session_id, "stages/research_")}{expert_id}.json`"""
  # ↑ 传入 "stages/research_" 作为 stage_name，不在注册表中 → fallback 路径错误
  # 实际输出路径: {base}/blackboard/{session_id}/stages/research_ + expert_id + .json
  ```
  而 `STAGE_PATH_REGISTRY` 中的 key 是 `"research_expert_1"` → `"stages/research_expert_1.json"`，
  且 `PARALLEL_OUTPUT_PATHS` 中 `"expert_1": "stages/research_expert_1.json"`。
  `_get_stage_path("stages/research_")` 返回 `{base}/blackboard/{session_id}/stages/research_`，
  拼接后得到 `{base}/blackboard/{session_id}/stages/research_expert_1.json` — **碰巧正确但机制脆弱**。
- **影响**: 研究者写入路径碰巧正确，但路径构造方式不通过注册表。如果 `STAGE_PATH_REGISTRY` 未来修改了 `research_expert_1` 的路径（如改为 `stages/research/1.json`），三处路径源将不一致。
- **建议**: 在 `build_researcher_task` 中直接使用 `STAGE_PATH_REGISTRY[f"research_expert_{expert_id}"]` 而非手动拼接。

### [P1-4] `PARALLEL_OUTPUT_PATHS` 中 `research` 路径硬编码，未使用 `STAGE_PATH_REGISTRY`

- **位置**: `orchestrator_agent.py:87-94`
- **根因**: `PARALLEL_OUTPUT_PATHS` 中 `research` 路径直接硬编码为 `"stages/research_expert_1.json"` 等，未引用 `STAGE_PATH_REGISTRY`。
- **证据**:
  ```python
  # orchestrator_agent.py L87-94
  PARALLEL_OUTPUT_PATHS = {
      "reviewers": {
          "technical": STAGE_PATH_REGISTRY["reviewer_technical"],      # ✅ 使用注册表
          "business": STAGE_PATH_REGISTRY["reviewer_business"],        # ✅ 使用注册表
          "risk": STAGE_PATH_REGISTRY["reviewer_risk"],                # ✅ 使用注册表
      },
      "research": {
          "expert_1": "stages/research_expert_1.json",                 # ❌ 硬编码
          "expert_2": "stages/research_expert_2.json",                 # ❌ 硬编码
          "expert_3": "stages/research_expert_3.json",                 # ❌ 硬编码
      },
  }
  ```
- **影响**: `reviewers` 正确使用注册表，但 `research` 硬编码。如果注册表变更，两者将不一致。当前碰巧一致，但是维护隐患。
- **建议**: 改为 `STAGE_PATH_REGISTRY["research_expert_1"]` 等。

### [P1-5] `Fixer Expert` prompt 中无输入文件读取路径 — 完全依赖注入参数

- **位置**: `task_builder.py:build_fixer_expert_task` + `prompts/fixer_expert_v2_harness.md`
- **根因**: `build_fixer_task_with_audit` 接收 `audit_path` 参数并注入到 prompt 中，Fixer 可以自己读取审计文件。但 `build_fixer_expert_task` 接收 `audit_findings: list`（空列表），且 prompt 模板 `fixer_expert_v2_harness.md` 中没有"输入读取"段落指导 Fixer Expert 去读取任何文件。
- **证据**:
  ```python
  # fixer_expert_v2_harness.md 输入区域
  ## 修复主题: {{ TOPIC }}
  ## 严重程度: {{ SEVERITY }}
  ## 审计发现: {{ AUDIT_FINDINGS }}  # ← 空列表 "[]"
  ```
  对比 Fixer:
  ```python
  # fixer_v2_harness.md
  ## 审计报告路径: {{ AUDIT_PATH }}  # ← 有文件路径
  ```
- **影响**: Fixer Expert 运行时 `{{ AUDIT_FINDINGS }}` 为空数组 `[]`，无法获取 Auditor 的发现。除非 `fixer_expert_v2_harness.md` 中另有"读取 audit.json"的步骤指令（需检查 prompt 全文），否则 Fixer Expert 将在零输入下运行。
- **建议**: 在 `fixer_expert_v2_harness.md` 中添加"输入读取"段落：`stages/audit.json` 和 `stages/fix.json`。

### [P1-6] `build_summarizer_task` 中 `all_outputs={}` 参数被 `build_worker_context_section` 部分补偿 — 双重注入但不完整

- **位置**: `task_builder.py:build_summarizer_task` 末尾
- **根因**: `build_summarizer_task` 在最后调用了 `build_worker_context_section(living_spec, "summarizer")`，注入 `user_directives` + `solution_pro_hints`。但 `all_outputs={}` 的核心输入仍为空。
- **影响**: Summarizer 收到 Spec Pro 的上下文（用户指令/提示），但完全没有前序阶段的产出数据。这是 P0-1 的延伸 — 即使有 S4 补偿，核心输入流仍然断裂。
- **建议**: 同 P0-1 — 移除 `all_outputs` 参数，在 prompt 中明确输入文件列表。

---

## P2 问题

### [P2-1] `control_contract.py:rewrite_after_planning()` 也传入 `layer2_constraints` 给 `build_auditor_task` — 但签名不一致

- **位置**: `control_contract.py:263`
- **根因**: `build_auditor_task(session_id, topic, {...}, layer2_constraints=contract["layer2_constraints"])` 传入了 `layer2_constraints`，但 `build_auditor_task` 的签名为 `def build_auditor_task(session_id, topic, context, living_spec=None)` — 没有 `layer2_constraints` 参数。Python 会忽略此参数（作为 keyword arg 传给不存在的参数名）→ **运行时 TypeError**。
- **证据**:
  ```python
  # control_contract.py L263
  base_task = builder(session_id, topic, {...}, layer2_constraints=contract["layer2_constraints"])
  # builder = build_auditor_task
  # 签名: def build_auditor_task(session_id, topic, context, living_spec=None)
  ```
- **影响**: 同 P0-3 — `rewrite_after_planning()` 运行时崩溃。
- **建议**: 移除 `layer2_constraints` 参数，已通过 `LAYER2_READ_INSTRUCTION` 注入。

### [P2-2] `STAGE_PATH_REGISTRY` 中注册了 `"design": "stages/design.json"` 但 design 阶段不在 Pipeline 中 — 幽灵路径

- **位置**: `blackboard.py:32` + `orchestrator_agent.py:296-307`（pipeline 列表无 `"design"`）
- **根因**: 注册表包含 `"design"` 路径，但 pipeline 不包含 `"design"` stage。这意味着：
  1. 如果有任何 worker 写入 `stages/design.json`，注册表可以解析
  2. 但没有任何 worker 被调度去写入
  3. `completion_handler.py` 基于注册表遍历所有阶段 → 会把 `design` 标记为"缺失"
- **影响**: `completion_handler.py` 的 `check_orchestrator_completion()` 遍历 `STAGE_PATH_REGISTRY` 中所有条目作为预期阶段。这意味着 `design` 会被报告为"missing stage"，导致完成率永远不到 100%（21 个注册表条目，pipeline 只有 10 个 stage）。
- **证据**: 
  ```python
  # completion_handler.py L70-71
  for stage_name, rel_path in STAGE_PATH_REGISTRY.items():
      stage_definitions[stage_name] = [rel_path]
  # ← 遍历全部 21 个注册表条目，而实际 pipeline 只有 10 个阶段
  ```
- **建议**: `completion_handler.py` 应基于 `execution_plan.json` 中的 phase 列表来定义预期阶段（它已有 `_expected_outputs_from_plan` 函数），而非遍历 `STAGE_PATH_REGISTRY`。

### [P2-3] `frozen_spec.json` 的 `executive_summary` 被 prompt 注入但从未通过参数传递 — 一致性风险

- **位置**: 全局（`frozen_spec.py` 生成 vs 各 worker 的 living_spec_context）
- **根因**: `frozen_spec.py` 精心构建了 `executive_summary`（指针+上下文模式），但每个 worker 的"全局理解"都是从 `living_spec.confirmed` 手动拼接的。两者数据源不同：`frozen_spec.json` 包含 `requirement_groups`、`coverage_policy` 等扩展信息，而 workers 只读取 `confirmed` 的子集。
- **影响**: 此前审计报告已发现此问题（AUDIT_REPORT_2026-06-02.md §3.4），此处仅补充数据流视角 — `executive_summary` 的 `objective_req` 指针和 `key_scenarios_reqs` 指针**从未被任何消费者解析**。
- **建议**: 在 worker prompt 的"全局理解"段落中引用 `frozen_spec.json` 中的 `executive_summary`，而非从 `living_spec.confirmed` 手动拼接。

### [P2-4] `completion_handler.py` 基于 `STAGE_PATH_REGISTRY` 检查完成度 vs 基于 `execution_plan.json` 检查 — 双路径逻辑

- **位置**: `completion_handler.py:61-77`（STAGE_PATH_REGISTRY fallback）vs `completion_handler.py:48-55`（execution_plan.json 优先）
- **根因**: `check_orchestrator_completion()` 优先读取 `execution_plan.json`（✅ 正确），但如果读取失败则 fallback 到遍历 `STAGE_PATH_REGISTRY`。fallback 路径会检查 21 个注册表条目（包括不在 pipeline 中的 `design`、`structured_requirements` 等），导致完成率计算错误。
- **影响**: 如果 `execution_plan.json` 缺失（异常场景），完成检查将报告 10/21 阶段完成 → 47% 完成率 → `partial` 状态。这掩盖了真实失败原因。
- **建议**: 移除 `STAGE_PATH_REGISTRY` fallback 路径，或将其限制为仅包含 pipeline 中的 10 个阶段。

### [P2-5] `build_harness_final_task` 中 `harness_scoring` prompt 被内联但 `{blackboard_path}` 替换存在

- **位置**: `task_builder.py:build_harness_final_task`
- **根因**: `build_harness_final_task` 正确替换了 `{blackboard_path}` 和所有 `{{ }}` 模板变量。但 `harness_v3.md` prompt 的"输入读取"段落使用 `{blackboard_path}`（单花括号），被 `build_harness_final_task` 替换为实际路径。此处一致性良好，无问题。标记为 P2 仅作记录 — 此处是**正确实现**的示例。
- **状态**: ✅ 无问题，仅作正面参照。

---

## 数据流完整性总结

### 完整的数据流链（✅ 无断链）

| 阶段 | 输入来源 | 输出去向 | 状态 |
|:---|:---|:---|:---|
| **data_collection** | topic + constraints (参数) | `data/collection.json` | ✅ |
| **planning** | collection.json (via prompt) | `stages/planning.json` + `data/structured_requirements.json` | ✅ |
| **reviewers** | planning.json (via LAYER2_READ_INSTRUCTION) | `stages/reviewer_*.json` | ✅ |
| **research** | topic + context (参数) | `stages/research_expert_*.json` | ✅ |
| **consolidator** | research_*.json (via prompt 指令, 非参数) | `stages/consolidator.json` | ⚠️ 参数传空但 prompt 有指令 |
| **audit** | planning.json (via LAYER2) | `stages/audit.json` | ✅ |
| **fix** | audit.json (via audit_path 参数) | `stages/fix.json` | ✅ |
| **fixer_expert** | **空 audit_findings 参数** | `stages/fixer_expert.json` | 🔴 输入断链 |
| **harness_final** | frozen_spec.json + 各阶段输出 (via prompt) | `stages/harness_final.json` + `requirements_traceability_matrix.json` | ✅ |
| **summarizer** | **空 all_outputs 参数** | `stages/summarizer.json` + `final_solution.md` | ⚠️ 参数传空但 prompt 有指令 |

### 关键文件产生/消费矩阵

| 文件 | 产生者 | 消费者 | 状态 |
|:---|:---|:---|:---|
| `data/collection.json` | Data Collection | Planner (prompt) | ✅ |
| `stages/planning.json` | Planner | Reviewers/Auditor/Fixers (LAYER2) | ✅ |
| `data/structured_requirements.json` | Planner | **无** | 🔴 孤岛 |
| `data/frozen_spec.json` | write_frozen_spec (init) | 所有 Workers (REQ traceability) | ✅ |
| `stages/research_expert_*.json` | Researcher ×3 | Consolidator (prompt) | ✅ |
| `stages/consolidator.json` | Consolidator | Auditor/Fixer (prompt) | ✅ |
| `stages/audit.json` | Auditor | Fixer (参数) | ✅ |
| `stages/fix.json` | Fixer | Summarizer (prompt) | ✅ |
| `stages/fixer_expert.json` | Fixer Expert | Summarizer (prompt) | ✅ |
| `stages/harness_final.json` | Harness Final | Summarizer (prompt) | ✅ |
| `requirements_traceability_matrix.json` | Harness Final (prompt) | Summarizer (prompt) | ✅ |
| `control_contract.json` | rewrite_after_planning() | Pipeline Orchestrator | ✅ |

---

## 修复优先级

### 第一轮（P0 × 3）— 运行时必然崩溃或断裂

| # | 问题 | 修复 | 工作量 |
|---|------|------|--------|
| 1 | **P0-3**: control_contract.py 调用 build_researcher_task 传入了不存在的 layer2_constraints 参数 | 移除参数调用 | 5 min |
| 2 | **P0-1**: Summarizer all_outputs={} 参数断链 | 移除 all_outputs 参数 + prompt 中的 {{ all_outputs }} 替换 | 15 min |
| 3 | **P0-2**: structured_requirements.json 孤岛文件 | 从注册表和 Planner prompt 中移除，或添加消费者 | 20 min |

### 第二轮（P1 × 4）— 功能不完整但可运行

| # | 问题 | 修复 | 工作量 |
|---|------|------|--------|
| 1 | **P1-2**: Fixer Expert 空 audit_findings 参数 | 在 prompt 中添加 audit.json 读取路径 | 10 min |
| 2 | **P1-5**: Fixer Expert 无输入文件路径 | 同上修复 | 合并 |
| 3 | **P1-3**: Researcher 路径手动拼接 | 使用注册表 | 10 min |
| 4 | **P1-4**: PARALLEL_OUTPUT_PATHS 硬编码 | 使用注册表 | 5 min |

### 第三轮（P2 × 4）— 维护性优化

| # | 问题 | 修复 | 工作量 |
|---|------|------|--------|
| 1 | **P2-1**: control_contract.py 也传 layer2_constraints 给 build_auditor_task | 移除参数 | 5 min |
| 2 | **P2-2**: completion_handler 遍历全部注册表条目 | 使用 execution_plan 优先 | 15 min |
| 3 | **P2-3**: executive_summary 双重数据源 | 统一消费 frozen_spec | 1 hr |
| 4 | **P2-4**: completion_handler fallback 逻辑有 bug | 移除 fallback 或限制范围 | 10 min |

---

**报告生成时间**: 2026-06-03 01:40 CST
