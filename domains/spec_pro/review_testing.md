# Spec Pro 系统性修复计划 — 测试评审意见

> 评审对象: `REMEDIATION_PLAN.md` 第五章"验证标准"
> 评审人: 测试工程评审专家
> 日期: 2026-06-02

---

## 评审结论摘要

| 评审维度 | 评级 | 说明 |
|----------|------|------|
| 验证标准覆盖率 | ⚠️ 不足 | "运行测试+3轮对话+无回归"仅覆盖 40-50% 的问题，缺 Schema 契约校验、异常注入、下游集成等关键测试 |
| 自动化可行性 | ✅ 80% | 30 个问题中约 24 个可自动化，6 个需手动/半自动 |
| 遗漏的测试类型 | 🔴 严重 | 缺少: (1) Schema 校验器单元测试 (2) 异常注入测试 (3) Spec→Solution 集成测试 (4) Prompt-Code 一致性校验 |

---

## 一、对当前验证标准的评估

### 1.1 "运行现有测试 + 新增对应测试"

**问题**: 当前无任何测试文件（`find` 无匹配）。"运行现有测试"为空操作。

**改进**: 必须先建立测试基础设施，再谈"运行"。建议按 Phase 逐步创建 `test_schemas.py`、`test_merge_spec.py`、`test_coordinator.py`、`test_frozen_spec.py` 等。

### 1.2 "模拟完整 3 轮对话流程验证端到端"

**问题**: 仅验证 happy path。P0-8（损坏字段类型崩溃）、P1-18/19（API JSON 损坏）、P2-29（NaN 序列化）等问题需要**异常注入**，正常对话不会触发。

**改进**: 3 轮对话作为 E2E 基准，但必须额外增加 **异常场景注入**（损坏 JSON、NaN 值、空 dict、负 delta 等）。

### 1.3 "检查无回归"

**问题**: "无回归"不可操作。没有回归标准、没有基线、没有自动化断言。

**改进**: 定义回归检查清单（见下方 Phase 专项测试）。

---

## 二、分 Phase 测试清单

### Phase 1: S1 Schema 契约层（解决 P0-1, P0-2, P0-3, P1-20, P1-21, P2-22/23/24/25）

#### 核心风险
S1 引入 `schemas.py` 是整个修复的基石。Schema 本身如果定义错误或校验逻辑有漏洞，后续所有 Phase 都建立在错误基础上。

#### 测试清单

| 编号 | 测试名 | 输入 | 期望输出 | 自动化 | 覆盖问题 |
|------|--------|------|----------|--------|----------|
| S1-1 | `test_schema_validate_living_spec_complete` | 包含全部 10 个 confirmed 维度 + user_directives 的完整 living_spec dict | `validate_living_spec()` 返回 `valid=True` | ✅ | P0-1 |
| S1-2 | `test_schema_validate_living_spec_missing_fields` | 缺少 `user_directives` 字段的 living_spec dict | `validate_living_spec()` 返回 `valid=False`，错误信息包含缺失字段名 | ✅ | P0-1 |
| S1-3 | `test_schema_meta_signals_directive_stop_asking` | 构造含 `meta_signals.directive_stop_asking` 的 response dict | 校验通过，该字段被 schema 接受 | ✅ | P0-2 |
| S1-4 | `test_schema_round_result_quality_structure` | 构造 quality 对象（统一格式：含 category/score/reasoning/missing_items） | 校验通过 | ✅ | P0-3 |
| S1-5 | `test_schema_quality_structure_rejects_legacy_format` | 构造旧版 quality 对象（仅 score 字段，无 category） | 校验失败，明确指出缺少的必填字段 | ✅ | P0-3 |
| S1-6 | `test_schema_dimensions_is_array_not_dict` | dimensions 字段为 `{"clarity": 80, "completeness": 70}`（字典格式） | 校验失败，提示应为 array | ✅ | P1-20 |
| S1-7 | `test_schema_dimensions_is_array` | dimensions 字段为 `[{"dimension": "clarity", "score": 80, ...}]` | 校验通过 | ✅ | P1-20 |
| S1-8 | `test_schema_user_directives_nesting` | user_directives 为嵌套的 `{"pain_points": {"directive": "..."}}` | 校验失败，应为扁平数组 | ✅ | P1-21 |
| S1-9 | `test_schema_user_directives_flat_array` | user_directives 为 `[{"dimension": "pain_points", "directive": "...", "content": "..."}]` | 校验通过 | ✅ | P1-21 |
| S1-10 | `test_schema_parse_response_missing_fields` | parse_response 输出缺少 success_metrics/pain_points 等字段 | 校验失败，列出缺失字段 | ✅ | P2-22 |
| S1-11 | `test_schema_success_metrics_format` | success_metrics 为非数组格式（如字符串） | 校验失败 | ✅ | P2-23 |
| S1-12 | `test_schema_harness_nullable_fields` | harness 输出中 final_decision 为 null | 校验失败（不可为 null） | ✅ | P2-25 |
| S1-13 | `test_schema_validate_round_result_quality_all_actions` | 分别构造 questions/summary/proposal/done 四种 action 的 round_result，均用统一 quality schema | 全部校验通过 | ✅ | P0-3 |
| S1-14 | `test_schema_merge_validates_before_merge` | 传入不合规的 response → `merge_spec()` | 在 merge 前被 schema 校验拦截，返回 error 状态 | ✅ | RC2 |
| S1-15 | `test_schema_prompt_code_consistency` | 加载 `schemas.py` + 7 个 prompt 文件，对比 schema 字段与 prompt 中定义的字段 | 无差异，或输出差异报告 | ⚠️ 半自动 | P0-1, P2-22 |

#### S1 关键评审点

**Q: Schema 校验能否防止 LLM 输出不符合 Schema？**

**A: 不能单方面防止，但能检测和修复。** LLM 输出发生在 Prompt 侧，Schema 校验发生在代码侧。正确的设计是：

1. **预防层**: Prompt 中嵌入 Schema 示例（S1 行动 3），让 LLM 按 Schema 输出
2. **检测层**: `merge_spec.py` 入口处 `validate_response(response)` 校验
3. **修复层**: 校验失败时，不是直接报错，而是尝试 auto-fix（如补默认值、展平嵌套）再校验

**建议新增**: `schemas.py` 中增加 `auto_fix_response()` 函数，处理常见的 LLM 格式偏离（嵌套→扁平、字符串→数组等），然后重新校验。

#### Prompt-Code 契约对齐验证（S1-15 补充）

手动验证步骤：
```
1. 从 schemas.py 提取所有 schema 字段集合 S_code
2. 从 7 个 prompt 文件提取所有 JSON 示例中的字段集合 S_prompt
3. 计算 S_code - S_prompt（代码有但 prompt 没有的字段）
4. 计算 S_prompt - S_code（prompt 有但代码没有的字段 → P0-1 类问题）
5. 差异应为空
```

建议写一个脚本 `scripts/audit_prompt_code_alignment.py` 自动执行此检查，CI 中运行。

---

### Phase 2: S2 Prompt 写入协议（解决 P0-4, P0-5）

#### 测试清单

| 编号 | 测试名 | 输入 | 期望输出 | 自动化 | 覆盖问题 |
|------|--------|------|----------|--------|----------|
| S2-1 | `test_init_prompt_contains_round_result_write` | 读取 coordinator.py `init_session()` 生成的 orchestrator_task 文本 | 文本中包含 `write` 或 `exec` 命令，明确指示写入 `round_result.json` | ✅ | P0-4 |
| S2-2 | `test_init_prompt_contains_conversation_log_update` | 同上 | 文本中包含 conversation_log.json 更新指令 | ✅ | P0-5b |
| S2-3 | `test_collecting_branch_C_prompt_contains_round_result_write` | 构造 collecting 分支 C 场景的 orchestrator_task | 文本中包含 round_result.json 写指令 | ✅ | P0-5 |
| S2-4 | `test_collecting_step7_prompt_contains_conversation_log_update` | 同上 | 文本中包含 conversation_log 更新指令 | ✅ | P0-5b |
| S2-5 | `test_all_phase_prompts_contain_write_instructions` | 遍历所有 phase（init/collecting/question/assess/structure）的 prompt | 每个需要输出的 phase 都有对应的 write 指令 | ✅ | P0-4, P0-5 |
| S2-6 | `test_init_session_e2e_creates_expected_files` | 调用 `coordinator.init_session("test input")`，模拟 Orchestrator 执行 write | Blackboard 目录下存在 `spec/round_result.json`、`spec/living_spec.json`、`spec/conversation_log.json` | ⚠️ 半自动（需 mock LLM） | P0-4 |

---

### Phase 3: S3 防御性编程（解决 P0-6, P0-7, P0-8, P1-14, P1-15, P1-17, P1-18/19, P2-29, P2-30）

#### 测试清单

| 编号 | 测试名 | 输入 | 期望输出 | 自动化 | 覆盖问题 |
|------|--------|------|----------|--------|----------|
| S3-1 | `test_session_id_no_collision` | 循环调用 `_generate_session_id()` 1000 次 | 所有 ID 唯一（使用 uuid4，碰撞概率≈0） | ✅ | P0-6 |
| S3-2 | `test_session_id_format` | 调用 `_generate_session_id()` | 返回格式为 `{prefix}_spec_{16-char-hex}`，长度≤50 | ✅ | P0-6 |
| S3-3 | `test_session_id_prefix_cap` | prefix 传入 100 字符字符串 | 生成的 ID 不超过 50 字符 | ✅ | P0-6 |
| S3-4 | `test_parse_worker_fallback_creates_living_spec` | 调用 `worker_fallback.py parse /tmp/test_output.json`，检查是否创建最小 living_spec | 输出文件存在且包含 `{"confirmed": {"objective": "", ...}}` 最小结构 | ✅ | P0-7 |
| S3-5 | `test_merge_confirmed_isinstance_check` | 传入 `confirmed.pain_points = "not_a_list"` 的 spec | `merge_confirmed()` 不崩溃，跳过或修复该字段 | ✅ | P0-8 |
| S3-6 | `test_merge_confirmed_nan_value` | 传入含 `float('nan')` 的 confirmed 字段 | 不崩溃（NaN 被转为字符串或 null） | ✅ | P2-29 |
| S3-7 | `test_merge_confirmed_empty_dict` | 传入 `confirmed = {}`（空 dict） | 不崩溃，返回 error 或填充默认值 | ✅ | P2-30 |
| S3-8 | `test_safety_stop_prevents_next_round` | 构造 `state = KILLED` 的 coordinator，调用 `build_next_round_task()` | 立即返回 `{"action": "safety_stop"}`，不执行后续逻辑 | ✅ | P1-14 |
| S3-9 | `test_process_guard_negative_delta` | 构造 trajectory 中 delta=-5 的数据，调用 `process_guard.py` | 不崩溃，正确识别负 delta 为异常 | ✅ | P1-15 |
| S3-10 | `test_process_guard_delta_zero` | 构造 delta=0 的 trajectory | 不崩溃，输出合理的进度过慢警告 | ✅ | P1-15 |
| S3-11 | `test_api_json_decode_error` | 传入损坏的 JSON 文件给 `spec_pro_api.py` 的 load 路径 | 捕获 JSONDecodeError，返回 `{"success": False, "error": "..."}` | ✅ | P1-18, P1-19 |
| S3-12 | `test_api_invalid_json_input` | 传入空文件/非 JSON 文本 | 同上，不崩溃 | ✅ | P1-18 |
| S3-13 | `test_fallback_data_structure_complete` | 遍历 FALLBACKS dict 中每种 worker_type，检查是否包含 merge 所需的最小字段 | 每种 fallback 都能被 `merge_confirmed()` / `merge_inferred()` 安全消费 | ✅ | P1-17 |
| S3-14 | `test_merge_spec_file_not_found` | 传入不存在的路径给 `merge_spec()` | 返回 `{"status": "error", "message": "..."}`，不崩溃 | ✅ | RC3 |
| S3-15 | `test_apply_revisions_invalid_json` | 传入损坏的 confirmation JSON | 捕获异常，返回 error | ✅ | P1-19 |

#### 防御性编程回归清单

| 回归检查 | 方法 |
|----------|------|
| merge_confirmed 对已有字段的处理逻辑不变 | S1-1 用例在修改前后各跑一次，对比结果 |
| merge_inferred 的 dimension→confirmed 映射不变 | 构造标准 inference_response，对比迁移前后的 confirmed 层 |
| check_contradictions 逻辑不变 | 用已有的 guardrail conflict 用例验证 |

---

### Phase 4: S4 下游消费 Adapter（解决 P0-9, P0-10, P0-11, P1-5a, P1-6a, P1-12, P1-13, P2-8, P2-9）

#### ⚠️ 此 Phase 最需要集成测试

| 编号 | 测试名 | 输入 | 期望输出 | 自动化 | 覆盖问题 |
|------|--------|------|----------|--------|----------|
| S4-1 | `test_build_living_spec_context_route_recommendation` | 含 `route_recommendation` 的 living_spec | `build_living_spec_context()` 返回的 context 包含 `route_recommendation` 的提取结果 | ✅ | P0-9 |
| S4-2 | `test_build_living_spec_context_user_directives` | 含 `user_directives: [{dimension, directive, content}]` 的 living_spec | context 中 `deliberately_omitted_dimensions` 或等价字段包含 user_directives 内容 | ✅ | P0-10 |
| S4-3 | `test_build_living_spec_context_inferred_pending` | 含 `inferred: [{status: "pending", ...}]` 的 living_spec | context 中 `pending_inferences` 包含待确认推断 | ✅ | P0-11 |
| S4-4 | `test_build_living_spec_context_layer2_hints` | 含 `layer2_hints` 的 living_spec | context 中 `layer2_hints` 保持原结构（不展平为字符串） | ✅ | P1-5a |
| S4-5 | `test_build_living_spec_context_anti_patterns` | 含 `anti_patterns` 的 living_spec | context 中 `anti_patterns` 被提取 | ✅ | P1-6a |
| S4-6 | `test_build_living_spec_context_requirement_annotations` | 含 `requirement_annotations` 的 living_spec | context 中包含标注信息 | ✅ | P1-12 |
| S4-7 | `test_hints_not_flattened_to_string` | 含结构化 hints dict 的 living_spec | 传递给 Solution Pro 的 hints 仍为 dict，不是 `str(hints)` | ✅ | P2-8 |
| S4-8 | `test_executive_summary_task_builder_consistency` | 对比 frozen_spec.py 的 executive_summary 与 task_builder.py 中注入的上下文 | 两者包含的字段一致，无矛盾 | ✅ | P2-9 |
| S4-9 | `test_frozen_spec_guardrails_passthrough` | 含完整 guardrails（always_do/ask_first/never_do）的 living_spec | frozen_spec.json 中 guardrails 完整保留 | ✅ | P1-13 |
| S4-10 | `test_frozen_spec_with_null_living_spec` | `living_spec=None` 调用 `build_frozen_spec()` | 返回最小 valid frozen_spec，不崩溃 | ✅ | RC4 |

#### S4 必须新增：Spec Pro → Solution Pro 集成测试

**测试名**: `test_spec_pro_to_solution_pro_integration`

```python
def test_spec_pro_to_solution_pro_integration():
    """
    集成测试：验证 Spec Pro 全部产出能正确传递到 Solution Pro
    
    步骤：
    1. 构造一个包含所有元数据层的完整 living_spec（模拟 Round 3 完成态）
       - confirmed: 10 维度全量
       - user_directives: 多条
       - route_recommendation: {suggested_engine, suggested_mode, ...}
       - inferred: 含 pending/confirmed/rejected 各一条
       - guardrails: always_do/ask_first/never_do 各 2 条
       - solution_pro_hints: {focus_areas: [...]}
       - layer2_hints: {场景A: [...], 场景B: [...]}
       - anti_patterns: [{pattern, risk, alternative}]
       - requirement_annotations: [...]
    
    2. 调用 build_frozen_spec(living_spec=...)
    
    3. 验证 frozen_spec.json 包含：
       - ✅ route_recommendation → top_level 或等效位置
       - ✅ user_directives → deliberately_omitted_dimensions
       - ✅ inferred_pending → pending_inferences
       - ✅ guardrails 完整（3 个子数组均非空）
       - ✅ solution_pro_hints 完整
       - ✅ requirement_annotations 合并到 REQ 中
    
    4. 调用 task_builder.build_planner_task(living_spec=frozen_spec)
    
    5. 验证生成的 prompt 中：
       - ✅ 包含 user_directives 的内容
       - ✅ 包含 route_recommendation 的建议
       - ✅ 包含 guardrails 的边界
       - ✅ 不含展平的 hints 字符串
    """
    pass
```

**此集成测试的重要性**: P0-9/10/11 三个 P0 问题的根因是"元数据层传递完全断裂"。仅靠单元测试无法验证传递链是否完整。必须有一个端到端的集成测试。

---

### Phase 5: S5 代码清理（解决 P1-16, P2-26, P2-27）

| 编号 | 测试名 | 输入 | 期望输出 | 自动化 | 覆盖问题 |
|------|--------|------|----------|--------|----------|
| S5-1 | `test_no_duplicate_process_guard` | grep 代码库中 `check_process_guard` 引用 | 仅在 `process_guard.py` 中定义，无其他定义 | ✅ | P1-16 |
| S5-2 | `test_process_guard_single_entry` | 所有对 process_guard 的调用 | 均通过 `process_guard.py`，不通过 `utils.py` | ✅ | P1-16 |
| S5-3 | `test_user_confirmation_is_json` | 检查 coordinator.py 中 user_confirmation 文件路径 | 使用 `.json` 扩展名 | ✅ | P2-26 |
| S5-4 | `test_round1_no_self_reference` | 读取 Round 1 QuestionWorker prompt | 不包含"读取之前的 round_result"之类的自引用 | ✅ | P2-27 |

---

## 三、无法自动化测试的修复项及手动验证方案

| 编号 | 修复项 | 为什么无法自动化 | 手动验证方法 |
|------|--------|------------------|--------------|
| S2-6 | init 阶段 round_result.json 实际写入 | 需要真实 LLM 执行 Orchestrator Worker 的 write 指令 | 启动一次完整 Spec Pro session（genesis + standard），检查 Blackboard 目录是否生成 round_result.json |
| S2-3/4 | collecting 分支 C 的 round_result.json 写入 | 需要触发 collecting 分支 C 的特定对话路径 | 手动运行到 collecting 阶段，触发分支 C 场景（LLM 判定为 collecting），检查文件 |
| S1-15 | Prompt-Code Schema 一致性 | Prompt 是文本，Schema 是代码，语义一致性需要人工审查 | 运行 `audit_prompt_code_alignment.py` 生成差异报告 → 人工逐字段确认 |
| S4-10 | Spec Pro → Solution Pro 集成（LLM 消费端） | LLM 对 prompt 的理解无法用代码断言 | 启动完整 Spec Pro session → 拿到 frozen_spec → 启动 Solution Pro session → 人工检查 Planner prompt 中是否包含 user_directives/route_recommendation 等信息 |
| P0-4/5 | 端到端 3 轮对话流程 | 需要 LLM 交互 | 手动跑一次完整的 3 轮对话，每轮后检查 Blackboard 文件完整性 |

### 手动验证 Checklist

```
□ 手动跑 1 次 genesis + standard 模式的完整 Spec Pro 对话（≥3 轮）
□ 检查每轮 Blackboard 目录下：
  □ spec/living_spec.json（存在且格式正确）
  □ spec/round_result.json（存在且含 quality 对象）
  □ spec/conversation_log.json（存在且逐轮追加）
  □ spec/quality_report.json（存在且 dimensions 为数组）
  □ spec/quality_trajectory.json（存在且 delta 非异常值）
  □ stages/harness.json（存在且 final_decision 非 null）
□ 将 living_spec.json 传递给 Solution Pro
□ 检查 Solution Pro 的 frozen_spec.json 是否包含：
  □ user_directives 信息
  □ route_recommendation 信息
  □ 完整 guardrails
□ 检查 Planner Worker prompt 文本中是否包含上述信息
```

---

## 四、测试基础设施建议

当前零测试，建议先搭建：

### 4.1 目录结构
```
domains/spec_pro/tests/
├── __init__.py
├── conftest.py              # pytest fixtures
├── test_schemas.py          # Phase 1
├── test_merge_spec.py       # Phase 1 + 3
├── test_coordinator.py      # Phase 2 + 3
├── test_worker_fallback.py  # Phase 3
├── test_process_guard.py    # Phase 3
├── test_frozen_spec.py      # Phase 4
├── test_task_builder.py     # Phase 4
├── test_spec_pro_api.py     # Phase 3
├── test_cleanliness.py      # Phase 5
├── integration/
│   ├── __init__.py
│   └── test_spec_to_solution.py  # S4 集成测试
└── fixtures/
    ├── valid_living_spec.json
    ├── invalid_living_spec.json
    ├── valid_response.json
    ├── malformed_json.txt
    └── nan_containing.json
```

### 4.2 conftest.py 核心 fixture
```python
@pytest.fixture
def valid_living_spec():
    """包含全部 10 个 confirmed 维度的标准 living_spec"""
    return {...}

@pytest.fixture
def living_spec_with_metadata():
    """含所有元数据层（route_recommendation, user_directives, hints...）"""
    return {...}

@pytest.fixture
def malformed_json_file(tmp_path):
    """包含损坏 JSON 的临时文件"""
    p = tmp_path / "bad.json"
    p.write_text("{broken json")
    return str(p)
```

### 4.3 CI 集成（建议）
```bash
# 单元测试
pytest domains/spec_pro/tests/ -v --tb=short

# Prompt-Code 一致性审计
python scripts/audit_prompt_code_alignment.py

# 集成测试
pytest domains/spec_pro/tests/integration/ -v
```

---

## 五、回归标准定义

"无回归"应具体化为以下检查：

| 回归检查项 | 验证方法 |
|------------|----------|
| merge_confirmed 对 10 个标准维度的处理逻辑不变 | 用标准 input→output 对比，diff 为 0 |
| merge_inferred 的 10 个 dimension→confirmed 映射不变 | 同上 |
| check_contradictions 检测逻辑不变 | 用已知 contradiction input 验证输出一致 |
| MODE_CONFIG（quick/standard/deep 的 max_rounds/threshold）不变 | 断言 MODE_CONFIG 值 |
| DIMENSION_WEIGHTS 不变 | 断言权重和为 1.0 且各值不变 |
| HARNESS_DIMENSION_WEIGHTS 不变 | 同上 |
| DialogState 枚举值不变 | 断言枚举成员 |
| RoundAction 枚举值不变 | 断言枚举成员 |
| QuestionType 枚举值不变 | 断言枚举成员 |
| QualityLevel 枚举值不变 | 断言枚举成员 |

---

## 六、评审建议优先级

| 优先级 | 建议 | 理由 |
|--------|------|------|
| 🔴 P0 | Phase 1 先写 Schema 单元测试 | Schema 是其他 Phase 的基石，必须先行 |
| 🔴 P0 | Phase 4 必须写集成测试 | P0-9/10/11 是 P0 级问题，单元测试不足以验证 |
| 🟡 P1 | 建立测试 fixture 目录 | 后续 Phase 复用 |
| 🟡 P1 | 写 Prompt-Code 一致性审计脚本 | 防止 S1 修复后再次漂移 |
| 🟢 P2 | 定义回归断言清单 | 防止"无回归"成为空话 |
| 🟢 P2 | 补充异常注入 fixture | P1-18/19/P2-29 等需要 |

---

*评审完成。建议按 Phase 顺序推进，每个 Phase 先写测试再改代码（TDD 模式），确保修复可验证。*
