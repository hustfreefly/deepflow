## Prompt 体系 + 契约配置视角补充

> 评审日期: 2026-06-01
> 评审视角: Prompt 工程专家 + 契约架构专家
> 审查范围: domains/spec_pro/prompts/ (7), config/spec_pro.yaml, cage/active/spec_pro_v2.0.yaml, prompts/registry.yaml, coordinator.py, spec_pro_api.py, models.py, merge_spec.py

---

## Part A: Prompt 体系

### A1: 版本标识合规

| 文件 | Front Matter | version | id | updated | 合规 |
|------|-------------|---------|----|---------|------|
| orchestrator.md | ✅ | 2.1.0 | spec_pro/orchestrator | 2026-05-23 | ✅ |
| guide.md | ✅ | 2.1.0 | spec_pro/guide | 2026-05-23 | ✅ |
| parse.md | ✅ | 2.1.0 | spec_pro/parse | 2026-05-23 | ✅ |
| parse_response.md | ✅ | 2.1.0 | spec_pro/parse_response | 2026-05-23 | ✅ |
| assess.md | ✅ | 2.1.0 | spec_pro/assess | 2026-05-23 | ✅ |
| structure.md | ✅ | 2.1.0 | spec_pro/structure | 2026-05-23 | ✅ |
| harness.md | ✅ | 2.1.0 | spec_pro/harness | 2026-05-23 | ✅ |
| `_overview.md` | ❌ **缺失** | — | — | — | 🔴 |
| `IMPROVEMENTS.md` | ❌ **缺失** | — | — | — | 🔴 |
| `config/spec_pro.yaml` | N/A (Domain YAML 格式) | 2.3.0 | — | — | ✅ (符合 version_control.md §2.4) |
| `cage/active/spec_pro_v2.0.yaml` | N/A (Cage YAML 格式) | cage: 2.0.0 / spec: 2.1 | — | 2026-05-23 | ✅ |

**结论**: 7 个 prompt 文件的 Front Matter 全部合规。但 `_overview.md` 和 `IMPROVEMENTS.md` 缺失版本标识，违反 version_control.md §2.1 规范。

### A2: Prompt 质量

#### A2.1 苏格拉底六类问题完整性 ✅

`guide.md` 中完整定义了六类问题:
1. ✅ clarification — 追问模糊概念
2. ✅ probe_assumption — 暴露隐含假设
3. ✅ probe_evidence — 验证合理性
4. ✅ alternative_view — 引入其他视角
5. ✅ implication — 测试取舍
6. ✅ meta — 检验问题定义

且与 `models.py` 中 `QuestionType` Enum 完全对齐:
```python
class QuestionType(Enum):
    CLARIFICATION = "clarification"
    PROBE_ASSUMPTION = "probe_assumption"
    PROBE_EVIDENCE = "probe_evidence"
    ALTERNATIVE_VIEW = "alternative_view"
    IMPLICATION = "implication"
    META = "meta"
```

#### A2.2 assess.md 评估维度覆盖 ✅

assess.md 覆盖 7 维度，完整对应 Living Spec confirmed 层的所有字段:

| assess 维度 | 对应 Living Spec 字段 | 覆盖率 |
|------------|---------------------|--------|
| objective | objective + pain_points + success_metrics | ✅ |
| users | users + key_scenarios | ✅ |
| capabilities | capabilities (always/should/never) | ✅ |
| quality_attributes | quality_attributes | ✅ |
| constraints | constraints (全量遍历所有 key: budget/timeline/tech_stack/platform/input_format/output_format/usage_model/design_philosophy/language) | ✅ |
| integration | integration (existing_systems + requirements) | ✅ |
| risks | risks_and_assumptions (risks/assumptions/dependencies) | ✅ |

**但与 LivingSpec dataclass 存在 1 处不匹配**：
- LivingSpec dataclass 中没有 `user_directives` 字段（parse_response.md 输出中有，assess.md 规则中有 deliberately_omitted 处理，但 models.py 的 LivingSpec dataclass 没有对应字段）

#### A2.3 structure.md 输出 vs LivingSpec dataclass

| structure.md 输出字段 | LivingSpec dataclass 字段 | 匹配 |
|---------------------|------------------------|------|
| route_recommendation | route_recommendation | ✅ |
| solution_pro_hints | solution_pro_hints | ✅ |
| summary_text | (不存储, 仅展示) | ✅ |
| living_spec (action=done) | 完整结构 | ✅ |
| harness_report | (独立报告, 非 LivingSpec 字段) | ⚠️ |
| inferred_pending | inferred (subset) | ✅ |

**⚠️ action="proposal" 模式缺失**: orchestrator.md 和 coordinator.py 引入了 `action: "proposal"` (D5 停滞检测)，但:
1. `models.py` 的 `RoundAction` Enum **没有** `PROPOSAL` 值 — 只有 QUESTIONS/SUMMARY/DONE/ERROR/SAFETY_STOP
2. `structure.md` 的 "输出模式" 部分只定义了 `summary` 和 `done` 两种 action，**没有** `proposal`
3. `coordinator.py` 的 `_collecting_phase_instructions()` Step 6 分支 A 明确写了 `action: "proposal"` — 这是一个**三方不一致**

### A3: 跨 Prompt 依赖

#### A3.1 调用链完整性 ✅

```
Orchestrator (orchestrator.md)
  ├──→ ParseWorker (parse.md)        → stages/round_NN_parse.json + spec/living_spec.json
  ├──→ QuestionWorker (guide.md)     → stages/round_NN_questions.json
  │     输入: living_spec.json + quality_report.json
  ├──→ ResponseWorker (parse_response.md) → stages/round_NN_response.json
  │     输入: living_spec.json + user_response + round_NN_questions.json
  ├──→ AssessWorker (assess.md)      → spec/quality_report.json
  │     输入: living_spec.json
  ├──→ HarnessWorker (harness.md)    → spec/harness_report.json
  │     输入: living_spec.json + quality_report.json + conversation_log.json + quality_trajectory.json
  └──→ StructureWorker (structure.md) → spec/round_result.json
        输入: living_spec.json + quality_report.json [+ harness_report.json if done]
```

调用链完整，依赖方向正确。

#### A3.2 parse_response → assess 的消费关系 ✅

- parse_response.md 输出 `parsed_updates` → coordinator.py 通过 merge_spec.py 合并到 living_spec.json → assess.md 读取 living_spec.json 评分
- parse_response.md 输出 `inference_responses` → merge_spec.py 的 merge_inferred() 处理 → 推断状态更新
- parse_response.md 输出 `meta_signals` → 被 coordinator.py 读取用于判断 user_said_enough 等
- parse_response.md 输出 `new_inferences` → merge_spec.py 追加到 inferred 层

**链路完整**。但有一个隐性依赖：parse_response.md 新增的 `user_directives` 字段需要被 merge_spec.py 处理（见 Part B2）。

#### A3.3 harness → structure 的输入关系 ✅

- harness.md 读取 living_spec.json + quality_report.json + conversation_log.json + quality_trajectory.json
- harness.md 输出 spec/harness_report.json
- structure.md (action=done) 读取 harness_report.json（如果存在）并写入 round_result.json

**链路完整**。

### A4: Prompt 与 Python 代码的耦合

#### A4.1 coordinator.py 引用的 prompt vs 实际文件

| coordinator.py 引用 | 实际文件 | 匹配 |
|--------------------|---------|------|
| `read_prompt("spec_pro/orchestrator")` | orchestrator.md (id: spec_pro/orchestrator) | ✅ |
| `domains/spec_pro/prompts/parse.md` | parse.md | ✅ |
| `domains/spec_pro/prompts/guide.md` | guide.md | ✅ |
| `domains/spec_pro/prompts/parse_response.md` | parse_response.md | ✅ |
| `domains/spec_pro/prompts/assess.md` | assess.md | ✅ |
| `domains/spec_pro/prompts/structure.md` | structure.md | ✅ |
| `domains/spec_pro/prompts/harness.md` | harness.md | ✅ |

全部对应。coordinator.py 使用 `read_prompt()` 加载 orchestrator（自动剥离 Front Matter），其他 Worker prompt 通过字符串注入路径引用。

#### A4.2 spec_pro_api.py 的 prompt 加载方式

spec_pro_api.py 通过 SpecProCoordinator → `_build_orchestrator_task()` → `read_prompt("spec_pro/orchestrator")` 加载，符合 `version_control.md §4.1` 规定的自动剥离 Front Matter 行为。

**但注意**: coordinator.py 中 init/collecting/confirmation 三个 phase 的 instructions 里，对非 orchestrator Worker 的 prompt 是硬编码路径引用（如 `domains/spec_pro/prompts/parse.md`），**不经过 `read_prompt()`**。这意味着：
- 如果主 Agent 直接读取这些文件并喂给 LLM，**Front Matter 不会被剥离**，LLM 可能看到元数据
- orchestrator.md 本身经过 `read_prompt()`，Front Matter 被剥离 ✅

---

## Part B: 契约/配置一致性

### B1: Cage 描述 vs 实际代码

#### B1.1 Redline 检查结果

| Redline | 规则描述 | 实际检查 | 状态 |
|---------|---------|---------|------|
| RED-SP2-001 | Coordinator 禁止包含 LLM 推理逻辑 | grep 无匹配 | ✅ 通过 |
| RED-SP2-002 | Coordinator 禁止直接调用 sessions_spawn | coordinator.py 仅在 prompt 模板中出现（作为 Orchestrator Worker 的指令），Python 代码本身无 `sessions_spawn` 调用 | ✅ 通过 |
| RED-SP2-003 | Worker 禁止直接调用 openclaw SDK | Worker prompt 中不含 `import openclaw` 指令 | ✅ 通过 |
| RED-SP2-004 | 不得修改 Solution Pro 核心引擎行为 | Solution Pro 的 `living_spec` 参数为 `Optional[dict] = None`，向后兼容 | ✅ 通过 |
| RED-SP2-005 | 推断禁止未经确认就标记为 confirmed | parse.md 明确规定"推断放入 inferred 层，不放 confirmed"；merge_spec.py 的 merge_inferred() 正确处理 status | ✅ 通过 |
| RED-SP2-006 | Worker 间状态传递必须通过 Blackboard | 所有 Worker task prompt 中均包含 Blackboard 读写路径 | ✅ 通过 |
| RED-SP2-007 | 只有 Orchestrator 可写 living_spec.json | parse.md 写入 living_spec.json（仅 Round 1 创建），其余 Worker 只写增量文件。parse.md 是 ParseWorker 首次创建，符合 cage 中 writer_protocol 定义 | ✅ 通过 |

#### B1.2 Cage 接口描述 vs coordinator.py 方法签名

| Cage 方法 | Cage 签名 | coordinator.py 实现 | 匹配 |
|-----------|-----------|-------------------|------|
| `__init__` | `scenario: str, mode: str, session_prefix: str = None` | `scenario: str = "genesis", mode: str = "standard", session_prefix: Optional[str] = None` | ✅ |
| `init_session` | `user_input: str -> dict` | `user_input: str -> Dict[str, Any]` | ✅ |
| `build_next_round_task` | `user_response: str -> dict` | `user_response: str -> Dict[str, Any]` | ✅ |
| `read_round_output` | `() -> dict` | `() -> Dict[str, Any]` | ✅ |
| `build_confirmation_task` | `user_confirmation: dict -> str` | `user_confirmation: Dict[str, Any] -> str` | ✅ |
| `get_status` | `() -> dict` | `() -> Dict[str, Any]` | ✅ |
| `is_done` | `() -> bool` | `() -> bool` | ✅ |

全部匹配。

### B2: 配置一致性

#### B2.1 config/spec_pro.yaml 配置 vs Python 代码

**⚠️ 问题 1: `parse_response` Worker 在 config 中缺失**

`config/spec_pro.yaml` 的 `agents` 列表只有 5 个 Agent:
```yaml
agents:
  - role: orchestrator
  - role: questioner
  - role: parser          # ← parse.md
  - role: assessor
  - role: structurer
```

但系统实际有 **7 个 Worker**：parse、question(parse_response) → response_worker、assess、structure、harness。

**缺失项**：
- `response_worker`（parse_response.md）不在 config agents 列表中
- `harness_worker`（harness.md）不在 config agents 列表中

这导致 config/spec_pro.yaml 不能完整描述 Spec Pro 的全部 Worker。

**⚠️ 问题 2: config/spec_pro.yaml 的 timeout 值与代码不一致**

| Worker | config/spec_pro.yaml | cage/active/spec_pro_v2.0.yaml | coordinator.py | 不一致 |
|--------|---------------------|-------------------------------|----------------|--------|
| orchestrator | 180 | 600 | 600 | ❌ |
| questioner (guide) | 120 | 180 | 180 | ❌ |
| parser (parse) | 90 | 180 | 180 | ❌ |
| assessor | 90 | 180 | 180 | ❌ |
| structurer | 120 | 180 | 180 | ❌ |
| harness_worker | (缺失) | 240 | 240 | N/A |
| response_worker | (缺失) | 180 | 180 | N/A |

config/spec_pro.yaml 的 timeout 值全部过时（只有实际值的一半）。

**⚠️ 问题 3: `config/spec_pro.yaml` 的 timeout 在代码中未被使用**

coordinator.py 中 timeout 值硬编码在 `_init_phase_instructions()` 和 `_collecting_phase_instructions()` 的字符串模板中（`timeoutSeconds: 180` 等），**没有从 config/spec_pro.yaml 读取**。

同时 `models.py` 中有 `WORKER_TIMEOUT` 常量字典：
```python
WORKER_TIMEOUT: Dict[str, int] = {
    "parse_worker": 180,
    "question_worker": 180,
    ...
}
```

这个 `WORKER_TIMEOUT` 也**没有被 coordinator.py 引用**。

**结论**: 存在 **3 份 timeout 定义**（config/spec_pro.yaml、models.py WORKER_TIMEOUT、coordinator.py 硬编码字符串），且互不一致，也没有引用关系。config/spec_pro.yaml 的配置是**死配置**。

#### B2.2 代码中硬编码的配置值

| 硬编码位置 | 硬编码内容 | 应在配置中 |
|-----------|-----------|-----------|
| coordinator.py `_init_phase_instructions()` | `timeoutSeconds: 180` 等 | config/spec_pro.yaml 或 MODE_CONFIG |
| coordinator.py `_collecting_phase_instructions()` | `timeoutSeconds: 180/240` 等 | 同上 |
| models.py `MODE_CONFIG` | `max_rounds`, `threshold` | 已在 MODE_CONFIG（合理，是代码级配置） |
| models.py `DIMENSION_WEIGHTS` | 7 维权重 | 已在 models.py（合理） |
| models.py `HARNESS_DIMENSION_WEIGHTS` | Harness 5 维权重 | 已在 models.py（合理） |

### B3: 版本标识合规

#### B3.1 组件版本漂移

| 文件 | 版本号 | 应一致 |
|------|--------|--------|
| `config/spec_pro.yaml` component_version | **2.3.0** | — |
| `cage/active/spec_pro_v2.0.yaml` version | **2.1** | — |
| `cage/active/spec_pro_v2.0.yaml` cage_version | **2.0.0** | — |
| `models.py` LivingSpec meta.version | **"2.1"** | 硬编码 — 违反 version_control.md §4.4 |
| 所有 prompt 文件 Front Matter version | **2.1.0** | ✅ 一致 |
| `prompts/registry.yaml` spec_pro.version | **2.1.0** | ✅ |

**⚠️ 版本漂移分析**:
1. `config/spec_pro.yaml` 的 `component_version: "2.3.0"` 与 cage 的 `version: '2.1'` 不同 — 说明配置文件的版本号领先于契约文件
2. `cage/active/spec_pro_v2.0.yaml` 的 `cage_version: "2.0.0"` 与内部 `version: '2.1'` 不同 — 契约自身版本与它所约束的组件版本不同步
3. `models.py` 中 `"version": "2.1"` 是硬编码 — **违反 version_control.md §4.4** ("禁止在 Python 代码中硬编码版本号")
4. IMPROVEMENTS.md 描述 8 个问题都已修复（D1-D8），但 `config/spec_pro.yaml` 的 `component_version: "2.3.0"` 暗示修复已完成，而 cage 的 `version: '2.1'` 却没有更新

#### B3.2 缺失版本标识的文件

| 文件 | 应有标识 | 当前状态 |
|------|---------|---------|
| `_overview.md` | YAML Front Matter | 🔴 缺失 |
| `IMPROVEMENTS.md` | YAML Front Matter | 🔴 缺失 |
| `cage/spec_pro_direct_driver.yaml` | Cage YAML 格式 | 🔴 无 `cage_version` 字段 |
| `update_conversation_log.py` | Python 文件注释 | ⚠️ 未检查 |

### B4: 与 Solution Pro 的接口

#### B4.1 Living Spec 字段对齐

Solution Pro 的 `task_builder.py` 从 `living_spec["confirmed"]` 中读取以下字段:

| Solution Pro 读取的字段 | Living Spec 提供的字段 | 匹配 |
|----------------------|---------------------|------|
| `confirmed.objective` | ✅ | ✅ |
| `confirmed.pain_points` | ✅ | ✅ |
| `confirmed.success_metrics` | ✅ | ✅ |
| `confirmed.users` (role/count/key_needs) | ✅ | ✅ |
| `confirmed.key_scenarios` | ✅ | ✅ |
| `confirmed.capabilities.always_do/should_do/never_do` | ✅ | ✅ |
| `confirmed.quality_attributes` (category/spec/priority) | ✅ | ✅ |
| `confirmed.constraints` (全量遍历所有 key) | ✅ | ✅ |
| `confirmed.integration.existing_systems` (name/role) | ✅ | ✅ |
| `confirmed.risks_and_assumptions.risks` | ✅ | ✅ |
| `confirmed.risks_and_assumptions.assumptions` | ✅ | ✅ |

**字段名完全匹配，无字段名不匹配风险** ✅

#### B4.2 Spec Pro 独有字段 — Solution Pro 消费情况

| Spec Pro 产出 | Solution Pro 消费 | 说明 |
|-------------|-----------------|------|
| `inferred` 层 | ⚠️ 部分消费 | frozen_spec 2.0.0 已提取 inferred 为 REQ-ID（`inferred` category），但 task_builder.py 的 living_spec_context 不直接引用 |
| `guardrails` 层 | ✅ 已消费 | frozen_spec 2.0.0 透传 guardrails 到 frozen_spec.json，task_builder.py 注入到 Worker prompt |
| `route_recommendation` | ❌ 不消费 | Solution Pro 不读路由建议 |
| `solution_pro_hints` | ✅ 已消费 | frozen_spec 2.0.0 透传到 frozen_spec.json，spec_context.py 格式化注入到 Worker prompt |
| `meta` | ❌ 不消费 | 元数据，Solution Pro 不需要 |

> **已修复（2026-06-03）**: `solution_pro_hints` 原先产出但未被消费的问题，已通过 frozen_spec.py 2.0.0 透传 + spec_context.py `build_worker_context_section()` 注入解决。

SPEC_PRO 在 cage 中声明了 `solution_pro_hints` 的注入方式（cage §integration.solution_pro.injection_method），但实际代码中 Solution Pro 只消费了 `confirmed` 层，**没有消费 `solution_pro_hints`**。

#### B4.3 solution_pro_hints 结构对齐

| solution_pro_hints 字段 | Solution Pro 期望 | 实际 |
|----------------------|-----------------|------|
| `focus_areas` (area/weight/reason) | 未读取 | ⚠️ 产出但未被消费 |
| `layer2_hints` (researcher/auditor) | 未读取 | ⚠️ 产出但未被消费 |
| `anti_patterns` | 未读取 | ⚠️ 产出但未被消费 |

**结论（更新 2026-06-03）**: `solution_pro_hints` 已被 Solution Pro 消费。frozen_spec.py 2.0.0 透传该字段到 frozen_spec.json，spec_context.py 的 `format_solution_pro_hints_for_prompt()` 按 focus_areas/layer2_hints/anti_patterns 三段式注入到 Worker prompt。

#### B4.4 frozen_spec.py 2.0.0 更新记录（2026-06-03）

frozen_spec.py 的 `build_frozen_spec()` 已升级为 2.0.0，实现了 **living_spec → frozen_spec 全量提取**。

**提取覆盖的 REQ category（17 种）**：

| Category | 来源字段 | 示例 |
|----------|---------|------|
| objective | confirmed.objective | 核心目标 |
| capability | confirmed.capabilities.always_do + should_do | 功能需求 |
| prohibition | confirmed.capabilities.never_do | 禁止项 |
| quality_attribute | confirmed.quality_attributes | 质量标准 |
| constraint | confirmed.constraints（**全量遍历所有 key**） | 约束条件 |
| integration | confirmed.integration.requirements | 集成需求 |
| pain_point | confirmed.pain_points | 痛点 |
| success_metric | confirmed.success_metrics | 成功指标 |
| user | confirmed.users | 用户画像 |
| scenario | confirmed.key_scenarios | 关键场景 |
| risk | confirmed.risks_and_assumptions.risks | 风险 |
| assumption | confirmed.risks_and_assumptions.assumptions | 假设 |
| guardrail | living_spec.guardrails.always_do | 行为边界（必须做） |
| guardrail_prohibition | living_spec.guardrails.never_do | 行为边界（禁止做） |
| design_decision | living_spec.guardrails.resolved | 用户确认的设计决策 |
| hint | living_spec.solution_pro_hints | 给 Solution Pro 的提示 |
| inferred | living_spec.inferred | AI 推断需求 |

**关键修复**：
1. constraints 从硬编码 3 个 key（budget/timeline/tech_stack）→ 遍历所有 key（全量覆盖）
2. guardrails.resolved（设计决策）新增提取
3. living_spec.inferred（AI 推断）新增提取

信息保留率从 <5% 提升到 ~100%。

---

## Part C: 废弃文件清理建议

| 文件 | 状态 | 建议 |
|------|------|------|
| `cage/spec_pro_direct_driver.yaml` | 无 cage_version，内容描述的是 coordinator.py 的改进契约，已被 cage/active/spec_pro_v2.0.yaml 吸收 | 🗑️ **建议归档到 cage/archive/** 或删除 |
| `cage/archive/spec_pro_v1.0.yaml` | 已归档 | ✅ 合规 |
| `domains/spec_pro/__pycache__/` | 编译缓存 | 🧹 可清理 |
| `update_conversation_log.py` | 独立脚本，未被 coordinator.py 引用 | ⚠️ 检查是否仍有用途，若无则归档 |

---

## Part D: 问题汇总

### 🔴 严重 (必须修复)

| # | 问题 | 影响 | 修复建议 |
|---|------|------|---------|
| D1 | `RoundAction` Enum 缺少 `PROPOSAL` 值 | coordinator.py 和 structure.md 使用 action="proposal"，但 models.py 不支持 → 运行时 `RoundAction("proposal")` 抛 ValueError | 在 models.py 的 RoundAction 中增加 `PROPOSAL = "proposal"` |
| D2 | `models.py` 硬编码 `"version": "2.1"` | 违反 version_control.md §4.4 硬编码禁止 | 移除硬编码，从 config/spec_pro.yaml 动态读取 |
| D3 | `user_directives` 字段缺失 | parse_response.md 输出 user_directives，merge_spec.py 不处理，LivingSpec dataclass 无此字段 → 用户指令数据丢失 | 在 LivingSpec dataclass 增加 `user_directives` 字段，在 merge_spec.py 增加合并逻辑 |

### 🟡 重要 (应尽快修复)

| # | 问题 | 影响 | 修复建议 |
|---|------|------|---------|
| D4 | `config/spec_pro.yaml` 缺少 response_worker 和 harness_worker | 配置文件不完整，不能准确描述 Spec Pro 的全部 Worker | 补充 response_worker 和 harness_worker 到 config agents 列表 |
| D5 | `config/spec_pro.yaml` timeout 值过时且未被代码使用 | 配置是死的，实际 timeout 硬编码在 coordinator.py 和 models.py | 统一为单一来源（建议 models.py WORKER_TIMEOUT），或让 coordinator.py 从 config 读取 |
| D6 | ~~`solution_pro_hints` 未被 Solution Pro 消费~~ | ~~Spec Pro 产出的 hint 信息被浪费~~ | ✅ 已修复（2026-06-03）：frozen_spec.py 2.0.0 透传 + spec_context.py 注入 |

### 🟢 改进 (可选)

| # | 问题 | 建议 |
|---|------|------|
| D7 | `_overview.md` / `IMPROVEMENTS.md` 缺失 Front Matter | 补充 YAML Front Matter 以符合 version_control.md |
| D8 | `cage/spec_pro_direct_driver.yaml` 无 cage_version | 补充 cage_version 或归档 |
| D9 | 存在 3 份 timeout 定义互不一致 | 统一为单一来源 |

---

## 评审总结

Spec Pro 的 Prompt 体系总体设计良好：7 个 prompt 文件全部有合规的 Front Matter，苏格拉底六类问题完整定义，Worker 调用链完整。主要问题集中在：

1. **代码契约一致性**：`RoundAction` 缺 `PROPOSAL`、`user_directives` 字段在 dataclass/merge 中缺失
2. **配置死代码**：`config/spec_pro.yaml` 的 timeout 和 agent 列表与代码不同步
3. **接口利用不足**：`solution_pro_hints` 产出完整但未被 Solution Pro 消费
4. **版本硬编码**：models.py 违反 version_control.md 的硬编码禁止规则
