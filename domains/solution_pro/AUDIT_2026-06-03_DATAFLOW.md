# Solution Pro 数据流转完整性审计报告

> **审计日期**: 2026-06-03 01:39  
> **审计范围**: `domains/solution_pro/` 核心 6 模块 + `pipeline_orchestrator.py`  
> **审计方法**: 代码证据驱动，逐阶段追踪输入→输出→消费链路  
> **参考**: AUDIT_REPORT_2026-06-03_CONSOLIDATED.md（不重复已报告问题）

---

## 管线全景（10 阶段）

```
Stage 1: data_collection  → data/collection.json
Stage 2: planning         → stages/planning.json
Stage 3: reviewers (×3)   → stages/reviewer_{technical|business|risk}.json
Stage 4: research (×3)    → stages/research_expert_{1|2|3}.json
Stage 5: consolidator     → stages/consolidator.json
Stage 6: audit            → stages/audit.json
Stage 7: fix              → stages/fix.json
Stage 8: fixer_expert     → stages/fixer_expert.json
Stage 9: harness_final    → stages/harness_final.json
Stage 10: summarizer      → stages/summarizer.json + final_result.json + final_solution.md
```

---

## P0 问题（Critical — 运行时断链）

### [P0-D1] `structured_requirements.json` 在 STAGE_PATH_REGISTRY 中注册但**无人产生**

- **审计维度**: 输入断链 + 输出不一致
- **位置**: `blackboard.py:24` 注册了 `"structured_requirements": "data/structured_requirements.json"`
- **根因**: 
  - `orchestrator_agent.py` 文档声称 data_collection "输出 collection.json + structured_requirements.json"（L14）
  - 但 `build_data_collection_task()` 的 prompt 只要求写入 `data/collection.json`
  - `structured_requirements.json` 仅在 `prompts_archive/_deprecated_v3.py`（已废弃文件）中有生成逻辑
  - **实际管线中没有任何 worker 产生这个文件**
- **证据**:
  - `grep -rn "structured_requirements" task_builder.py` → 0 结果
  - `grep -rn "structured_requirements" orchestrator_agent.py` → 仅注释行（L14, L15, L18, L32）
  - `STAGE_PATH_REGISTRY` 有注册但无生产者
- **影响**: 
  - 注册表中存在一个"幽灵文件"——永远不会被创建
  - 任何 worker 或脚本依赖此文件将读取到空/旧数据
  - 文档声明与实际行为不一致，属于**静默数据丢失**
- **建议**: 
  - 要么从 STAGE_PATH_REGISTRY 移除该条目，要么在 data_collection task 中显式输出该文件
  - 更新 orchestrator 文档删除已废弃的声明

---

### [P0-D2] `control_contract.json` 生命周期断裂——**产生方与消费方脱节**

- **审计维度**: 谁产生？谁消费？谁更新？
- **位置**: `control_contract.py:198` (build_control_contract) + `control_contract.py:225` (rewrite_after_planning)
- **根因**:
  - **产生**: `control_contract.py` 的 `rewrite_after_planning()` 生成 `control_contract.json`
  - **消费**: 
    - `orchestrator_agent.py:367` 注释声称 "Planning 完成后 control_contract.py 会把 Planner 生成的专家映射进 expert_1/expert_2/expert_3 的 prompt"
    - `execution_plan.json` 引用了 `control_contract_path: "control_contract.json"`（L534）
  - **谁调用 rewrite_after_planning()？**
    - 仅在 `scripts/golden_solution_pro_dry_run.py` 中被调用
    - **主执行路径 `run_harness_v2()` 从未调用 `rewrite_after_planning()` 或 `build_control_contract()`**
  - 这意味着 `control_contract.json` 在正常 Harness 2.0.0 执行中**永远不会被生成**
  - `research_workers` 专家映射、`layer2_constraints` 动态化等机制全部失效
- **证据**:
  - `grep -rn "rewrite_after_planning\|build_control_contract" orchestrator_agent.py` → 0 结果（仅 L367 注释引用）
  - `pipeline_orchestrator.py` 也不调用此模块
  - `execution_plan.json` 记录路径但无人写文件
- **影响**:
  - Planner 动态生成的专家（`required_experts`）**不会**映射到 research workers
  - `layer2_constraints` 全部回退到 `DEFAULT_LAYER2_CONSTRAINTS`（硬编码默认值）
  - `control_contract.json` 在 execution_plan 中有引用但实际不存在
  - **Planner 的动态决策对下游 Worker 完全失效**
- **建议**:
  - 在 `run_harness_v2()` 中，planning stage 完成后立即调用 `rewrite_after_planning()` 刷新 research/audit/fix 的 task
  - 或将 `rewrite_after_planning` 集成到 `PipelineOrchestrator` 的 phase 后处理中

---

### [P0-D3] `PARALLEL_OUTPUT_PATHS` vs `STAGE_PATH_REGISTRY` vs `execution_plan.json` 三轨不一致

- **审计维度**: 输出不一致 + 路径注册表覆盖度
- **位置**: `orchestrator_agent.py:75-94` + `blackboard.py:22-41` + `save_execution_plan()` L508-526
- **根因**: 三套路径来源并行存在：

| 来源 | reviewers 路径 | research 路径 | 同步机制 |
|------|---------------|---------------|---------|
| `STAGE_PATH_REGISTRY` | `reviewer_technical` / `reviewer_business` / `reviewer_risk` | `research_expert_1/2/3` | 唯一事实源（声称） |
| `PARALLEL_OUTPUT_PATHS` | `"technical"` / `"business"` / `"risk"` (键名不同!) | `"expert_1"` / `"expert_2"` / `"expert_3"` (无 `research_` 前缀!) | 硬编码，无同步 |
| `save_execution_plan()` | `PARALLEL_OUTPUT_PATHS.get("reviewers", {}).get(worker_id)` | 同上 | 依赖 PARALLEL_OUTPUT_PATHS |

  - **关键断裂**: `save_execution_plan()` 中 `PARALLEL_OUTPUT_PATHS["research"]` 的值为 `"stages/research_expert_1.json"` 等（直接写死字符串），但键名是 `"expert_1"` 而非 `"research_expert_1"`
  - 而 `_get_stage_path()` 生成的文件名是 `stages/research_{expert_id}.json`（`task_builder.py` 的 researcher task 输出路径）
  - `STAGE_PATH_REGISTRY` 中的键是 `research_expert_1`，但 `PARALLEL_OUTPUT_PATHS["research"]` 的键是 `expert_1`
- **证据**:
  - `orchestrator_agent.py:89-93`: `"expert_1": "stages/research_expert_1.json"` — 键值对，键是 `"expert_1"` 但值是 `"stages/research_expert_1.json"`
  - `save_execution_plan()` L521: `PARALLEL_OUTPUT_PATHS.get(stage_name, {}).get(worker_id, f"stages/{stage_name}_{worker_id}.json")` — 如果 key 不匹配，回退到 `f"stages/{stage_name}_{worker_id}.json"` 即 `stages/research_expert_1.json` ✓（碰巧一致但路径是硬编码的 fallback 兜住的）
  - `pipeline_orchestrator.py` 的 `WORKER_OUTPUT_PATH_MAP` 又有第四套映射
- **影响**: 
  - 目前碰巧由 fallback 兜住不会实际出错，但**路径一致性依赖隐式回退逻辑而非显式注册**
  - 任何一处的修改（如更名 `research_expert_1` → `research_tech`）将导致预期输出路径与实际路径断裂
  - `completion_handler.py` 使用 `_expected_outputs_from_plan()` 验证文件存在性，验证的也是 `expected_output_path` 字段，如果此字段与实际写入路径不一致则**误判为缺失**
- **建议**: 
  - 删除 `PARALLEL_OUTPUT_PATHS`，改为从 `STAGE_PATH_REGISTRY` 动态构建：
    ```python
    PARALLEL_OUTPUT_PATHS = {
        "reviewers": {k.split("_", 1)[1]: v for k, v in STAGE_PATH_REGISTRY.items() if k.startswith("reviewer_")},
        "research": {k: v for k, v in STAGE_PATH_REGISTRY.items() if k.startswith("research_")},
    }
    ```

---

### [P0-D4] `requirements_traceability_matrix.json` 只注册不产生不消费

- **审计维度**: 路径注册表覆盖度 + 输出不一致
- **位置**: `blackboard.py:26` + `control_contract.py:219` + `frozen_spec.py:187`
- **根因**:
  - **注册**: `STAGE_PATH_REGISTRY["requirements_traceability_matrix"] = "requirements_traceability_matrix.json"`
  - **引用**: 
    - `control_contract.py` 的 `build_control_contract()` 输出 `"traceability_matrix_path": "requirements_traceability_matrix.json"`
    - `frozen_spec.py` 的 `coverage_policy` 输出 `"matrix_path": "requirements_traceability_matrix.json"`
  - **谁产生？** 没有任何 worker 或脚本生成此文件
  - **谁消费？** 没有任何 worker 读取此文件
- **证据**:
  - `grep -rn "traceability_matrix" --include="*.py"` → 仅定义和引用，无写入/读取逻辑
  - 无对应的 `build_*_task` 函数生成 traceability matrix
  - `validate_stage_output()` 不检查此文件
- **影响**: 
  - 注册了一个永远不存在的文件
  - frozen_spec 的 `coverage_policy.matrix_path` 指向空文件，REQ-ID 追踪无法落地
  - `completion_handler` 不会检查此文件，所以运行时不会报错但功能失效
- **建议**: 
  - 要么在 consolidator 或 harness_final 阶段生成此文件，要么从注册表移除

---

## P1 问题（High — 功能缺陷）

### [P1-D1] Consolidator 的 `research_outputs` 输入为空列表 — **数据断链**

- **审计维度**: 输入断链
- **位置**: `orchestrator_agent.py:374` + `task_builder.py:build_consolidator_task()`
- **根因**:
  - `orchestrator_agent.py:374`: `build_consolidator_task(self.session_id, self.topic, [], ...)` — 传入空列表 `[]`
  - 注释明确说 `# 实际应从blackboard读取researcher outputs`
  - `build_consolidator_task()` 接收到空列表后，将 `outputs_json = "[]"` 注入 prompt
  - Consolidator 被要求整合三个 researcher 的输出，但实际上拿不到任何输出数据
- **证据**:
  - `orchestrator_agent.py:374-376`: 明确传入 `[]` 且注释承认
  - `build_consolidator_task()` 的 `research_outputs` 参数直接转为 JSON 注入 prompt
- **影响**: 
  - Consolidator 输出的 `consolidator.json` 基于**零研究输入**生成
  - 后续所有依赖 consolidator 输出的阶段（audit, fix, harness_final, summarizer）都建立在空数据基础上
  - 这是**整条管线的核心数据断链**——Stage 4→Stage 5 完全断裂
- **建议**:
  - Consolidator task 的 prompt 应该包含 researcher 输出文件的路径，让 Consolidator worker 运行时从 Blackboard 读取
  - 类似 `LAYER2_READ_INSTRUCTION` 模式，注入读取指令

---

### [P1-D2] Fixer 的 `audit_path` 在 get_all_tasks() 阶段指向**尚未存在的文件**

- **审计维度**: 输入断链
- **位置**: `orchestrator_agent.py:383` + `task_builder.py:build_fixer_task_with_audit()`
- **根因**:
  - `get_all_tasks()` 在**所有 task 同时构建时**就计算了 `audit_path = str(self.blackboard.get_stage_path("audit"))`
  - 此时 `audit.json` 尚未生成（fix 在 audit 之后执行）
  - 路径字符串本身是正确的（指向 `blackboard/{session}/stages/audit.json`），但 fixer prompt 中的 `{{AUDIT_PATH}}` 指向一个运行时才存在的文件
  - 这是**正确的设计模式**（运行时读取），但 fallback 机制中如果 audit.json 不存在，fixer 会静默使用默认修复
- **证据**:
  - `build_fixer_task_with_audit()` 的 fallback 提示: "如果 audit.json 不存在,使用以下默认修复"
  - 这意味着 fixer 在正常执行时能读到 audit.json（因为按阶段顺序执行）
  - 但 `execution_plan.json` 的 timeout 设置（300s）如果不够用，PipelineOrchestrator 继续下一阶段时 fixer 可能读到不完整数据
- **影响**: 低风险（正常流程下不会断裂），但超时场景下 fixer 会静默降级
- **建议**: 在 fixer prompt 中明确标注"如果读取失败则 BLOCK"而非 fallback

---

### [P1-D3] `execution_plan.json` 的 `expected_output_path` 与 `STAGE_PATH_REGISTRY` 存在多处潜在不一致

- **审计维度**: 输出不一致 + execution_plan.json expected_output_path
- **位置**: `orchestrator_agent.py:save_execution_plan()` L508-542
- **根因**: `save_execution_plan()` 中：
  - 串行阶段: `STAGE_OUTPUT_PATHS.get(stage_name, f"stages/{stage_name}.json")`
    - `STAGE_OUTPUT_PATHS` 是 `orchestrator_agent.py:62-72` 从 `STAGE_PATH_REGISTRY` 的子集构建
    - **缺失**: `reviewers`, `research` 不在 `STAGE_OUTPUT_PATHS` 中（它们是并行阶段）
    - 回退路径 `f"stages/{stage_name}.json"` 对大多数阶段碰巧正确，但对 `"reviewers"` / `"research"` 会产生错误路径（因为它们是并行阶段，不走这个分支）
  - 并行阶段: `PARALLEL_OUTPUT_PATHS.get(stage_name, {}).get(worker_id, f"stages/{stage_name}_{worker_id}.json")`
    - 如 P0-D3 所述，键名不一致
- **证据**:
  - `STAGE_OUTPUT_PATHS` 包含: data_collection, planning, consolidator, audit, fix, fixer_expert, harness_final, summarizer（8个）
  - 串行 pipeline 有 10 个阶段，其中 2 个（reviewers, research）是并行阶段，走另一个分支
  - 对于 reviewers: `save_execution_plan()` 的并行分支会为 worker_id="technical" 查找 `PARALLEL_OUTPUT_PATHS["reviewers"]["technical"]` = `STAGE_PATH_REGISTRY["reviewer_technical"]` = `"stages/reviewer_technical.json"` ✓
- **影响**: 实际运行时由于 fallback 机制碰巧正确，但**路径一致性缺乏显式验证**
- **建议**: 添加一个 `_verify_path_consistency()` 函数在 `save_execution_plan()` 末尾验证所有路径

---

### [P1-D4] PipelineOrchestrator 的 `WORKER_OUTPUT_PATH_MAP` 是**第四套路径来源**

- **审计维度**: 路径注册表覆盖度
- **位置**: `core/orchestrator/pipeline_orchestrator.py:38-68`
- **根因**:
  - `STAGE_PATH_REGISTRY` 是黑板的"唯一事实源"
  - `PARALLEL_OUTPUT_PATHS` 是 orchestrator 的第二套
  - `STAGE_OUTPUT_PATHS` 是第三套
  - `WORKER_OUTPUT_PATH_MAP` 是 pipeline_orchestrator 的第四套
  - 四套路径各自维护，无自动同步机制
- **证据**:
  - `pipeline_orchestrator.py:38-68`: `WORKER_OUTPUT_PATH_MAP` 包含 18 个条目
  - 其中部分条目如 `"expert_1": "stages/research_expert_1.json"` 与 `STAGE_PATH_REGISTRY` 的 `research_expert_1` 重复但键名不同
  - 注释承认 "此字典仅补充 STAGE_PATH_REGISTRY 中没有的别名映射" 但实际包含了所有映射
- **影响**: 
  - 维护成本高，任何路径变更需要同步更新 4 个地方
  - `resolve_worker_output_path()` 的优先级机制可能在不同情况下返回不同路径
- **建议**: 统一到 `STAGE_PATH_REGISTRY`，删除 `WORKER_OUTPUT_PATH_MAP`，在 `resolve_worker_output_path()` 中只使用 `STAGE_PATH_REGISTRY` + 简单的 key 转换逻辑

---

### [P1-D5] `completion_handler.py` 的 fallback 阶段定义与 `execution_plan` 冲突

- **审计维度**: 输出不一致
- **位置**: `completion_handler.py:76-98`
- **根因**:
  - `completion_handler.py:64-74`: 优先使用 `_expected_outputs_from_plan(plan)` 从 `execution_plan.json` 读取预期输出
  - 但如果 plan 解析失败，回退到 `STAGE_PATH_REGISTRY` 动态构建 `stage_definitions`
  - **问题**: `STAGE_PATH_REGISTRY` 包含 20+ 个条目（包括 data_collection, structured_requirements, frozen_spec, requirements_traceability_matrix 等），而实际 pipeline 只有 10 个阶段（含并行子阶段共 16 个输出文件）
  - 回退路径会检查所有 20+ 个注册表条目，其中 4+ 个永远不会存在，导致 **completion_rate 永远不是 1.0**
- **证据**:
  - `STAGE_PATH_REGISTRY` 有 20 个条目
  - 10 阶段管线实际产生的文件约 13 个（data/collection.json + stages/*.json × 10 + final_result.json + progress.json）
  - `structured_requirements.json`, `requirements_traceability_matrix.json`, `design.json`, `fix.json`（已废弃？）等可能永远不会产生
- **影响**: fallback 模式下 completion_handler 永远返回 `status: "partial"` 即使实际执行正常
- **建议**: 回退路径应基于 `SolutionConfig.stages` 的实际阶段列表构建预期，而非整个 `STAGE_PATH_REGISTRY`

---

## P2 问题（Medium — 维护性）

### [P2-D1] `frozen_spec.json` 的数据桥接完整但单向

- **审计维度**: frozen_spec.py + spec_context.py 数据桥接
- **位置**: `frozen_spec.py` + `spec_context.py`
- **证据**:
  - `frozen_spec.py` 从 `living_spec` 生成 `frozen_spec.json`，包含 requirements, requirement_groups, executive_summary, coverage_policy
  - `spec_context.py` 从 `living_spec` 提取 user_directives, inferred_pending, solution_pro_hints 注入到 worker prompt
  - 但 `spec_context.py` **不读取 `frozen_spec.json`**，而是直接读取 `living_spec`
  - 这意味着 `frozen_spec.json` 中的 REQ-ID 映射和分组信息**不被 worker 消费**
  - 只有 `inject_req_traceability()` 要求 worker 读取 `frozen_spec.json` 并使用 REQ-ID
- **影响**: 
  - `frozen_spec.json` 的 `requirement_groups` 和 `executive_summary` 字段虽然生成，但实际消费方有限
  - worker 通过 `REQ_TRACEABILITY_INSTRUCTION` 读取 `frozen_spec.json` 获取 REQ-ID 列表，这是**唯一的消费路径**
- **建议**: 确认 `executive_summary` 的指针模式（REQ-ID 引用）是否被 worker 正确使用

---

### [P2-D2] `progress.json` 硬编码 `total_stages: 10` 与实际阶段数可能不一致

- **审计维度**: 输出不一致
- **位置**: `blackboard.py:159`: `"total_stages": 10,  # P1-2 修复: 10 阶段管线`
- **根因**: 硬编码为 10，但实际执行阶段数为 10 个逻辑阶段、16 个 worker、5 个 phase（含并行合并）
- **影响**: 进度百分比在不同上下文中含义不同
- **建议**: 动态计算 `total_stages` 为实际 worker 数量

---

### [P2-D3] `data/collection.json` 是 data_collection 的唯一输出，但后续阶段不消费它

- **审计维度**: 输入断链
- **位置**: `build_planner_task()` + 后续 worker prompt
- **根因**:
  - Stage 1 输出 `data/collection.json`
  - Stage 2 (Planner) 的 prompt **不要求**读取 `data/collection.json`
  - Planner 的输入完全来自 `living_spec` + topic + constraints
  - 这意味着 data_collection 阶段的输出**不被任何后续阶段消费**
  - 整个 pipeline 的数据来源是 `living_spec` 和 topic，而非 collection.json
- **证据**:
  - `build_planner_task()` 中无引用 `collection.json` 的路径
  - `build_reviewer_task()` 也不引用
  - 只有 `build_designer_task()`（死代码，不在 pipeline 中）引用了 `data_collection` 输出
- **影响**: 
  - `data_collection` 阶段的存在价值存疑——它产生数据但无人消费
  - 如果 `living_spec` 不存在（无 Spec Pro），data_collection 收集的信息也无法传递给 Planner
- **建议**: 
  - 要么让 Planner 读取 collection.json，要么移除 data_collection 阶段
  - 或者明确 data_collection 的职责为"信息预加载"而非"数据传递"

---

## 审计维度覆盖总结

| 审计维度 | 状态 | 问题数 | 最高级别 |
|:---|:---:|:---:|:---:|
| 输入断链 | 🔴 | 4 | P0-D1, P0-D2, P1-D1, P2-D3 |
| 输出不一致 | 🔴 | 3 | P0-D3, P1-D3, P1-D5 |
| 路径注册表覆盖度 | 🔴 | 3 | P0-D1, P0-D4, P1-D4 |
| execution_plan expected_output_path | 🟡 | 1 | P1-D3 |
| PARALLEL_OUTPUT_PATHS 路径映射 | 🟡 | 1 | P0-D3 |
| control_contract.json 生命周期 | 🔴 | 1 | P0-D2 |
| requirements_traceability_matrix.json | 🔴 | 1 | P0-D4 |

**总计**: 4 P0 + 5 P1 + 3 P2 = **12 个问题**

---

## 根因归纳

| ID | 根因 | 触发问题 |
|----|------|---------|
| RC-D1 | **声明-执行脱节**：文档声明某文件被产生/消费，但实际代码无此逻辑 | P0-D1, P2-D3 |
| RC-D2 | **模块调用断裂**：模块存在且功能完整，但主执行路径不调用它 | P0-D2 |
| RC-D3 | **路径多轨制**：同一概念在 4 个不同位置各有一套映射 | P0-D3, P1-D4 |
| RC-D4 | **注册表过度注册**：STAGE_PATH_REGISTRY 注册了实际不会产生的文件 | P0-D4, P1-D5 |
| RC-D5 | **跨阶段数据不传递**：并行阶段输出未被后续阶段消费 | P1-D1 |

---

## 修复优先级

### 第一轮（P0 × 4）— 数据流转断裂

| # | 问题 | 修复策略 | 预计工作量 |
|---|------|---------|-----------|
| 1 | P0-D2 control_contract.json 生命周期断裂 | 在 planning 完成后调用 rewrite_after_planning() | 30 min |
| 2 | P0-D1 structured_requirements.json 幽灵文件 | 从注册表移除或实际生成 | 15 min |
| 3 | P0-D3 PARALLEL_OUTPUT_PATHS 三轨不一致 | 动态构建从 STAGE_PATH_REGISTRY | 20 min |
| 4 | P0-D4 requirements_traceability_matrix.json 死注册 | 从注册表移除或在合适阶段生成 | 10 min |

### 第二轮（P1 × 5）— 功能缺陷

| # | 问题 | 修复策略 | 预计工作量 |
|---|------|---------|-----------|
| 1 | P1-D1 Consolidator 输入为空 | 注入 researcher 输出路径让 worker 读取 | 20 min |
| 2 | P1-D4 WORKER_OUTPUT_PATH_MAP 第四轨 | 统一到 STAGE_PATH_REGISTRY | 30 min |
| 3 | P1-D3 execution_plan expected_output_path | 添加路径一致性验证 | 15 min |
| 4 | P1-D5 completion_handler fallback 过度检查 | 基于实际阶段构建预期 | 15 min |
| 5 | P1-D2 Fixer audit_path 时序 | 明确 BLOCK 而非 fallback | 10 min |

### 第三轮（P2 × 3）— 维护性

| # | 问题 | 修复策略 | 预计工作量 |
|---|------|---------|-----------|
| 1 | P2-D1 frozen_spec.json 消费有限 | 确认并补充消费方 | 20 min |
| 2 | P2-D2 progress.json 硬编码 | 动态计算 | 10 min |
| 3 | P2-D3 collection.json 无人消费 | 明确职责或移除阶段 | 30 min |

---

*审计完成时间: 2026-06-03 01:45 CST*
*基于代码证据，逐文件逐函数审计*
