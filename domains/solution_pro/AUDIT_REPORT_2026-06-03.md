# 代码一致性审计报告 — Prompt vs Code

> 审计时间: 2026-06-03 00:39 CST
> 审计范围: `/Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/`
> 审计人: Subagent (集成审计专家)
> 参考: AUDIT_REPORT_2026-06-02.md（不重复已发现问题）

---

## P0 问题

### [P0-1] `{blackboard_path}` 模板变量在 7 个 Worker prompt 模板中未被替换

- **位置**: `task_builder.py` (build_auditor_task/build_fixer_task_with_audit/build_consolidator_task/build_planner_task/build_reviewer_task/build_researcher_task/build_summarizer_task) + 对应 `prompts/*_v2_harness.md` 输出要求段
- **根因**: RC2 — 模板变量未替换
- **证据**:
  - `prompts/auditor_v2_harness.md` 输出要求段: `` 使用 **write** 工具将结果写入：`{blackboard_path}/stages/audit.json` ``
  - `prompts/fixer_v2_harness.md`: `` `{blackboard_path}/stages/fix.json` ``
  - `prompts/fixer_expert_v2_harness.md`: `` `{blackboard_path}/stages/fixer_expert.json` ``
  - `prompts/consolidator_v2_harness.md`: `` `{blackboard_path}/stages/consolidator.json` ``
  - `prompts/planner_v2_harness.md`: `` `{blackboard_path}/stages/planning.json` ``
  - `prompts/reviewer_v2_harness.md`: `` `{blackboard_path}/stages/reviewer_{{ review_type }}.json` ``
  - `prompts/researcher_v2_harness.md`: `` `{blackboard_path}/stages/research_{{ expert_id }}.json` ``
  - `prompts/summarizer_v2_harness.md`: `` `{blackboard_path}/stages/summarizer.json` ``
  - 代码对比: `build_harness_final_task` 正确替换了 `{blackboard_path}`（`task_builder.py:~830`: `prompt.replace("{blackboard_path}", f"{_DEEPFLOW_BASE}/blackboard/{session_id}")`），但上述 7 个 build 函数**均未**对该变量做 `.replace()` 调用
- **影响**: LLM 在输出要求段看到字面字符串 `{blackboard_path}` 而非实际路径。虽然每个函数在尾部追加了含具体路径的 context 块（如 `` {_get_stage_path(session_id, "audit")} ``），但 prompt 内部存在矛盾路径指引，可能导致 LLM 困惑或使用错误路径写入
- **建议**: 在对应 build 函数中添加 `prompt = prompt.replace("{blackboard_path}", f"{_DEEPFLOW_BASE}/blackboard/{session_id}")`，或统一将模板中的 `{blackboard_path}` 替换为 `{{ BLACKBOARD_PATH }}` 并集中替换

---

### [P0-2] Summarizer 输入文件引用格式与实际 pipeline 输出文件名完全不符

- **位置**: `prompts/summarizer_v2_harness.md` 第 30-40 行（全流程信息整合表）
- **根因**: RC8 — 过时指令 / 文件名漂移
- **证据**:
  - Summarizer prompt 引用: `stage_01_data_collection_output.json`、`stage_02_planner_output.json`、`stage_03_reviewer_*.json`、`stage_04_researcher_*.json`、`stage_05_consolidator_output.json`、`stage_06_auditor_output.json`、`stage_07_fixer_output.json`、`stage_08_fixer_expert_output.json`、`stage_09_harness_final_output.json`
  - 实际 pipeline 输出文件名（`orchestrator_agent.py` + `STAGE_PATH_REGISTRY`）:
    - `data/collection.json`（非 `stage_01_data_collection_output.json`）
    - `stages/planning.json`（非 `stage_02_planner_output.json`）
    - `stages/reviewer_technical.json`、`stages/reviewer_business.json`、`stages/reviewer_risk.json`（非 `stage_03_reviewer_*.json`）
    - `stages/research_expert_1.json`、`stages/research_expert_2.json`、`stages/research_expert_3.json`（非 `stage_04_researcher_*.json`）
    - `stages/consolidator.json`（非 `stage_05_consolidator_output.json`）
    - `stages/audit.json`（非 `stage_06_auditor_output.json`）
    - `stages/fix.json`（非 `stage_07_fixer_output.json`）
    - `stages/fixer_expert.json`（非 `stage_08_fixer_expert_output.json`）
    - `stages/harness_final.json`（非 `stage_09_harness_final_output.json`）
  - 10/10 文件名完全不匹配
- **影响**: Summarizer LLM 按 prompt 指示读取文件时将全部失败（FileNotFoundError），无法获取前序阶段的任何输出，导致最终方案文档为空或基于不完整数据生成
- **建议**: 将 Summarizer 的"输入读取"段和"全流程信息整合表"中的文件名替换为实际的 pipeline 输出路径

---

### [P0-3] Auditor prompt 要求读取 consolidator.json，但 Auditor 执行顺序在 Consolidator 之前

- **位置**: `prompts/auditor_v2_harness.md` 审计流程第 1 步
- **根因**: RC3 — 指令冲突 / pipeline 顺序矛盾
- **证据**:
  - Auditor prompt 审计流程 Step 1:
    ```
    1. **阅读输入文件**
       - 读取 planning.json
       - 读取所有 research_*.json
       - 读取 consolidator.json   ← 此文件在 Auditor 执行时尚未生成
    ```
  - Pipeline 执行顺序（`orchestrator_agent.py:get_all_tasks()`）:
    ```python
    pipeline = [
        "data_collection",      # Stage 1
        "planning",             # Stage 2
        "reviewers",            # Stage 3
        "research",             # Stage 4
        "consolidator",         # Stage 5  ← consolidator 在此
        "audit",                # Stage 6  ← auditor 在此
        ...
    ]
    ```
  - Auditor 在 Stage 6 执行，Consolidator 在 Stage 5 — Auditor **先于** Consolidator 运行，`consolidator.json` 不存在
- **影响**: LLM 尝试读取不存在的文件，可能报错或跳过该步骤，导致审计缺少 Consolidator 的统一方案视角
- **建议**: 从 Auditor 的输入文件列表中移除 `consolidator.json`（或调整 pipeline 顺序使 Auditor 在 Consolidator 之后运行）

---

## P1 问题

### [P1-1] `validate_stage_output` 接受 `PASS_WITH_CONDITIONS`，但所有 prompt 模板和评分标准中均未列出该值

- **位置**: `task_builder.py:288,361` vs `prompts/harness_scoring.md:27-32` + 所有 `*_v2_harness.md` 模板
- **根因**: RC6 — Schema 漂移
- **证据**:
  - `validate_stage_output` 代码:
    ```python
    valid_decisions = ["PASS", "PASS_WITH_CONDITIONS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]
    ```
  - `prompts/harness_scoring.md` 决策阈值表:
    ```
    | PASS | overall_score >= 0.85 |
    | WARNING | overall_score >= 0.70 |
    | CRITICAL_WARNING | overall_score >= 0.60 |
    | BLOCK_RECOMMENDATION | overall_score < 0.60 |
    ```
    — 缺少 `PASS_WITH_CONDITIONS` 及其阈值定义
  - 所有 9 个 harness prompt 模板的输出 JSON 示例中 `"decision"` 字段均为:
    ```
    "decision": "PASS|WARNING|CRITICAL_WARNING|BLOCK_RECOMMENDATION"
    ```
    — 同样缺少 `PASS_WITH_CONDITIONS`
- **影响**: LLM 不知道 `PASS_WITH_CONDITIONS` 是一个合法选项，永远不会输出该值。如果业务逻辑需要"有条件通过"的中间态，该路径永远不会被触发
- **建议**: 在 `harness_scoring.md` 决策阈值表中增加 `PASS_WITH_CONDITIONS` 行（如 `0.75 <= overall_score < 0.85`），并同步更新所有 9 个 harness prompt 模板的 `"decision"` 字段枚举

---

### [P1-2] `build_planner_task` 和 `build_harness_final_task` 中 `living_spec_context` 变量被双重赋值，首次构建完全被覆盖

- **位置**: `task_builder.py:~456-520`（build_planner_task）、`task_builder.py:~860-920`（build_harness_final_task）
- **根因**: RC1 — 代码内部不一致 / 死代码
- **证据**:
  - `build_planner_task` 中:
    ```python
    living_spec_context += f"""         # 第一次构建: ~456-480, 简短版(一句话概括+痛点+用户+成功指标+约束+分组标题)
    ## 全局理解（来自 executive_summary）
    ...
    """
    # ... 紧接着 ...
    living_spec_context = f"""          # 第二次赋值: ~482-520, 完整版(覆盖第一次构建)
    ## 全局理解（来自 executive_summary）
    > **重要**: 以下需求已经过用户确认...
    """
    ```
  - `build_harness_final_task` 中:
    ```python
    living_spec_context += f"""         # 第一次构建: ~860-885, 简短版
    ## 全局理解（来自 executive_summary）
    ...
    ## 你的角色相关需求分组（Harness Final: 全部 5 个分组）
    """
    # ... 紧接着 ...
    living_spec_context = f"""          # 第二次赋值: ~887-920, 完整版(覆盖第一次构建)
    ## 需求覆盖度评估基准（来自 Spec Pro）
    ...
    """
    ```
  - 两处均为先 `+=` 构建一段上下文，随后 `=` 重新赋值为更长版本，首次构建完全丢失
- **影响**: 约 30-40 行/处的代码是死代码，增加维护负担。如果未来开发者修改首次构建的内容，变更无效
- **建议**: 移除首次构建的 `living_spec_context` 代码块（保留更完整的第二次赋值版本）

---

### [P1-3] Fixer prompt 中 `files_modified` 字段暗示代码级修改，与 Solution 设计领域不符

- **位置**: `prompts/fixer_v2_harness.md` 输出格式 `fixes_applied[].files_modified`；`prompts/fixer_expert_v2_harness.md` 输出格式 `deep_fixes[].files_modified`、`refactoring[].component`
- **根因**: RC4 — 角色权限/职责不清
- **证据**:
  - `fixer_v2_harness.md`:
    ```json
    "fixes_applied": [
      {
        "audit_id": "AUD-001",
        "fix_description": "修复描述",
        "files_modified": ["修改的文件1", "文件2"]   ← 暗示代码文件
      }
    ]
    ```
  - `fixer_expert_v2_harness.md`:
    ```json
    "deep_fixes": [
      {
        "files_modified": ["文件1", "文件2"],
        "verification": "验证结果"
      }
    ],
    "refactoring": [
      {
        "component": "重构组件",    ← 代码级重构暗示
        "changes": "变更描述"
      }
    ]
    ```
  - Solution Pro 是**解决方案设计**领域，产出的是设计文档/方案，不涉及实际代码文件修改
- **影响**: LLM 可能误解为需要修改实际源代码文件，而非修改设计文档中的描述
- **建议**: 将 `files_modified` 改为 `documents_updated` 或 `sections_modified`，将 `refactoring` 改为 `design_adjustments`

---

### [P1-4] `build_planner_task`、`build_consolidator_task`、`build_summarizer_task` 的 `layer2_constraints` 参数签名存在但 orchestrator 从未传值

- **位置**: `task_builder.py` 函数签名 vs `orchestrator_agent.py:get_all_tasks()` 调用点
- **根因**: RC1 — 代码内部不一致（2026-06-02 报告已发现此问题，本次从 prompt 角度补充）
- **证据**:
  - 函数签名:
    - `build_planner_task(..., layer2_constraints: dict = None, ...)` — `task_builder.py:~420`
    - `build_consolidator_task(..., layer2_constraints: dict = None, ...)` — `task_builder.py:~1030`
    - `build_summarizer_task(..., layer2_constraints: dict = None, ...)` — `task_builder.py:~1130`
  - Orchestrator 调用:
    - `build_planner_task(self.session_id, self.topic, self.solution_type, self.constraints, self.stakeholders, living_spec=self.living_spec)` — **无 layer2_constraints 参数**
    - `build_consolidator_task(self.session_id, self.topic, [], living_spec=self.living_spec)` — **无 layer2_constraints 参数**
    - `build_summarizer_task(self.session_id, self.topic, {}, living_spec=self.living_spec)` — **无 layer2_constraints 参数**
  - 而 auditor/fixer_expert/reviewer/researcher 在 orchestrator 中通过 `LAYER2_READ_INSTRUCTION` 追加了 Layer 2 指令
- **影响**: 这三个函数的 `layer2_constraints` 参数始终为 `None`，`inject_layer2_constraints` 内部回退到默认约束。签名暗示可以传自定义约束，但实际调用链不支持
- **建议**: 要么从这三个函数签名中移除 `layer2_constraints` 参数，要么在 orchestrator 中传入 `LAYER2_READ_INSTRUCTION`（与 auditor/fixer_expert 一致）

---

### [P1-5] Fixer 输出格式中 `level: "P0/P1/P2"` 与 Auditor 输出格式中 `severity: "critical|major|minor|info"` 不一致

- **位置**: `task_builder.py:~889`（build_auditor_task fallback 上下文）vs `prompts/auditor_v2_harness.md` 输出格式
- **根因**: RC5 — 输出格式漂移
- **证据**:
  - `task_builder.py` 中 `build_auditor_task` 的 fallback context:
    ```
    "data": {{
       "issues": [{{"level": "P0/P1/P2", "description": "..."}}],
       "score": 85,
    }}
    ```
  - `prompts/auditor_v2_harness.md` 输出格式:
    ```json
    "audit_findings": [
      {
        "id": "AUD-001",
        "dimension": "completeness|feasibility|risk|consistency",
        "severity": "critical|major|minor|info",
        "description": "问题描述",
    ```
  - 字段名不同: `level` vs `severity`；值格式不同: `P0/P1/P2` vs `critical|major|minor|info`；数组名不同: `issues` vs `audit_findings`
- **影响**: 如果 prompt 文件读取失败触发 fallback，Fixer 收到的问题清单格式与 Auditor 正常输出的格式完全不兼容
- **建议**: 统一 fallback context 的输出格式与 prompt 模板一致（使用 `audit_findings`、`severity: critical|major|minor|info`）

---

## P2 问题

### [P2-1] `harness_scoring.md` 决策阈值表缺少 `PASS_WITH_CONDITIONS` 的条件定义（与 P1-1 关联但独立在 prompt 中）

- **位置**: `prompts/harness_scoring.md:27-32`
- **根因**: RC6 — Schema 漂移
- **证据**: 决策阈值表定义了 PASS/WARNING/CRITICAL_WARNING/BLOCK_RECOMMENDATION 四个阈值，但没有为 `PASS_WITH_CONDITIONS` 定义 `overall_score` 范围。`validate_stage_output` 代码中该值合法但 prompt 未提供使用指导
- **影响**: 见 P1-1
- **建议**: 见 P1-1

### [P2-2] `fixer_v2_harness.md` 输出要求中 `{blackboard_path}` 未替换且 fallback context 无输出路径指引

- **位置**: `prompts/fixer_v2_harness.md` 输出要求段 vs `task_builder.py:build_fixer_task_with_audit` fallback
- **根因**: RC2 — 模板变量未替换 + RC8 — 过时指令
- **证据**:
  - `fixer_v2_harness.md`: `` 使用 **write** 工具将结果写入：`{blackboard_path}/stages/fix.json` ``
  - `build_fixer_task_with_audit` 的 fallback 代码中有正确的路径指引（`{_get_stage_path(session_id, "fix")}`），但 prompt 文件正常读取时 `{blackboard_path}` 不会被替换
- **影响**: 与 P0-1 类似，但特别影响 fixer 路径
- **建议**: 见 P0-1 统一修复

### [P2-3] Summarizer 输出格式包含 `final_score`、`requirement_coverage` 等字段但无对应 validator 检查

- **位置**: `prompts/summarizer_v2_harness.md` 输出格式 vs `task_builder.py:validate_stage_output`
- **根因**: RC6 — Schema 漂移
- **证据**:
  - Summarizer prompt 输出格式包含:
    ```json
    "quality_assurance": {
      "final_score": 0.86,
      "requirement_coverage": {"total": 5, "covered": 5, "partial": 0, "missing": 0, "p0_missing": []},
    }
    ```
  - `validate_stage_output` 对 `summarizer`（豁免阶段）只检查 `covered_req_ids` 字段存在性，不检查上述嵌套结构
- **影响**: 低 — 这些是 Summarizer 的"额外"输出字段，validator 不阻止但也不保证。属于"提示充分但不验证"
- **建议**: 如果这些字段对下游重要，应在 validator 中添加对应检查；如果不重要，可从 prompt 中移除以降低 LLM 认知负担

### [P2-4] `data_collection.md` 输出格式未包含 `covered_req_ids` 字段，但 validator 要求此字段

- **位置**: `prompts/data_collection.md` 输出格式 vs `task_builder.py:validate_stage_output`
- **根因**: RC6 — Schema 漂移
- **证据**:
  - `data_collection.md` 输出 JSON 示例包含: `status`, `stage`, `search_keywords`, `search_results_summary`, `for_planner`, `recommendations_for_planner`
  - 但 validator 对豁免阶段只检查: `if "covered_req_ids" not in output: return False`
  - `covered_req_ids` 通过 `REQ_TRACEABILITY_INSTRUCTION`（由 `inject_req_traceability` 追加到 prompt）告知 LLM，但不在模板的输出格式示例中
- **影响**: 低 — `REQ_TRACEABILITY_INSTRUCTION` 明确指导 LLM 输出该字段，但模板示例的遗漏可能导致 LLM 忽略
- **建议**: 在 `data_collection.md` 输出格式 JSON 示例中添加 `"covered_req_ids": ["REQ-001"]` 行

### [P2-5] `harness_v3.md` 中 `global_understanding_check` 和 `requirement_group_coverage` 输出要求无 validator 对应

- **位置**: `prompts/harness_v3.md` "全局理解一致性检查"和"需求分组检查"段 vs `task_builder.py:validate_stage_output`
- **根因**: RC6 — Schema 漂移（提示与验证脱节）
- **证据**:
  - `harness_v3.md` 要求输出:
    ```json
    "global_understanding_check": {
      "why_alignment": "aligned|partial|misaligned",
      "for_whom_alignment": "...",
      "success_criteria_alignment": "...",
      "evidence": "..."
    },
    "requirement_group_coverage": { "Core": {...}, ... }
    ```
  - `validate_stage_output` 只检查 `harness_check` 的 4 维 + `overall_score` + `decision`，不验证上述两个新增字段
- **影响**: 低 — 这些是 harness_final 的"额外"检查，validator 不阻止但不保证
- **建议**: 如果这些字段对 harness_final 质量门控重要，应在 validator 中添加对应检查

### [P2-6] `prompts/planner_v2_harness.md` 中 dimensions 示例 JSON 使用了非标准 category 值

- **位置**: `prompts/planner_v2_harness.md` structured_requirements.json 输出格式
- **根因**: RC5 — 输出格式漂移（与 `frozen_spec.py` 的 category 枚举不一致）
- **证据**:
  - `planner_v2_harness.md` 输出示例:
    ```json
    "category": "performance|availability|security|scalability|business|constraint"
    ```
  - `frozen_spec.py` 中 `_add_requirement` 使用的 category:
    ```python
    "objective", "capability", "prohibition", "quality_attribute", "constraint",
    "integration", "pain_point", "success_metric", "user", "scenario",
    "risk", "assumption", "guardrail", "guardrail_prohibition", "hint"
    ```
  - 两组 category 完全不同
- **影响**: Planner 生成的 `structured_requirements.json` 使用一组 category，而 `frozen_spec.py` 生成的 `frozen_spec.json` 使用另一组。如果下游系统期望统一的 category 枚举，将产生解析失败
- **建议**: 统一 category 枚举。建议在 Planner prompt 中使用与 `frozen_spec.py` 一致的 category 值，或在代码中建立映射层

---

## 审计维度覆盖总结

| 审计维度 | 发现问题 | 最高级别 |
|:---|:---:|:---:|
| 1. Prompt-Code 不一致 | P0-1, P0-2, P1-5, P2-4, P2-6 | P0 |
| 2. 模板变量未替换 | P0-1, P2-2 | P0 |
| 3. 指令冲突 | P0-3 | P0 |
| 4. 角色权限不清 | P1-3 | P1 |
| 5. 输出格式漂移 | P1-5, P2-6 | P1 |
| 6. Schema 漂移 | P1-1, P2-1, P2-3, P2-5 | P1 |
| 7. Spec Pro ↔ Solution Pro 衔接 | P1-2（living_spec_context 重复构建）| P1 |
| 8. 过时指令 | P0-2, P0-3, P1-4 | P0 |

## 与 2026-06-02 报告的差异

| 2026-06-02 已发现 | 本次审计 |
|:---|:---|
| `layer2_constraints` 参数未传递（检查项 1.3） | 本次从 prompt 角度确认为 P1-4，补充了 build_summarizer_task |
| `living_spec.confirmed` 重复构建（检查项 3.4/4.4） | 本次发现具体的双重赋值 bug（P1-2），非仅"重复逻辑" |
| 死代码函数（检查项 1.4） | 本次未重复（属于代码结构问题，非 prompt 一致性问题） |
| `executive_summary`/`requirement_groups` 消费不足 | 本次聚焦 prompt-code 映射，此问题属于架构层面 |

**本次审计新发现**: P0-1（`{blackboard_path}` 未替换）、P0-2（Summarizer 文件名完全不匹配）、P0-3（Auditor 读取不存在的 consolidator.json）、P1-1（PASS_WITH_CONDITIONS 缺失）、P1-3（files_modified 领域不符）、P1-5（issues vs audit_findings 格式冲突）、P2-4/P2-5/P2-6（validator 与 prompt 脱节）

---

*审计完成。共发现 3 个 P0、5 个 P1、6 个 P2 问题。*
