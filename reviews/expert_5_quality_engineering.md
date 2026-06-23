# 软件质量工程专家评审报告

> **评审人**: 质量工程专家（Google/Meta 背景，测试策略与可靠性工程）
> **评审日期**: 2026-06-23
> **评审对象**: DeepFlow Contract Layer 提案
> **评审视角**: 测试策略、质量门禁设计、可靠性工程

---

## 📋 执行摘要

### 核心判断

**提案诊断准确，但根因不止"缺少合同层"。真正的根因是"测试策略与生产环境脱节"。**

128 个 Schema 错误未被发现，不是因为缺少合同，而是因为：
1. **测试用合成数据，不用生产数据** — fixtures 是手写的"完美数据"，不反映 LLM 真实输出
2. **测试的 Schema ≠ 生产的 Schema** — `eval_code_checks.py` 用硬编码 Python dict，生产用 `ship_package_v3.schema.json`，两者已分裂
3. **Gate 测试通过 ≠ Gate 有效** — `test_gates.py` 的 fixture 有 `project_type` 字段，但真实 architect 输出没有，测试在测"理想世界"
4. **没有端到端集成测试** — 没有测试跑完整条管线并验证最终产物符合生产 schema

Contract Layer 是**正确的解法**，但它解决的是"如何防止未来再犯"，不是"为什么现在没发现"。

---

## 一、128 个 Schema 错误为什么没被测试发现？

### 1.1 测试策略的 4 个致命缺陷

#### 缺陷 1：合成 Fixture 脱离生产现实

**现状**：
```python
# test_gates.py
@pytest.fixture
def good_package():
    return {
        "schema_version": "3.0.0",
        "meta": {...},  # 手写，符合 gate 期望
        "work_packages": [...]  # 手写，字段完整
    }
```

**问题**：这个 fixture 是**根据 gate 代码反推出来的"完美数据"**，不是 LLM 真实输出。

**真实情况**（6/23 端到端运行）：
- Packager 输出 `_meta` 在顶层（schema 不允许）
- `meta.input_format` 用 `"A"` 但 schema 期望 `"A_final_solution"`
- `work_packages` 有额外字段 `constraints`/`related_modules`/`requirements`
- `model_tier` 用 `"standard"` 但 schema 枚举是 `claude-opus/sonnet/gpt-4o` 等

**结论**：测试从未见过 LLM 的真实输出模式。

#### 缺陷 2：测试 Schema 与生产 Schema 分裂

**现状**：
```python
# eval_code_checks.py
SHIP_PACKAGE_SCHEMA = {
    "type": "object",
    "required": ["work_packages"],
    "properties": {
        "work_packages": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "objective", "budget", ...],
                ...
            }
        }
    }
}
```

**生产环境**：`schemas/ship_package_v3.schema.json`（16KB，独立的 JSON Schema 文件）

**问题**：这两个 schema **可能已经不一致**。测试通过只证明符合硬编码的简化版 schema，不证明符合生产 schema。

**证据**：
- 生产 schema 有 `meta.input_format` 的枚举约束（`"A_final_solution"`）
- 硬编码 schema 可能没有这个细节
- Packager prompt 的输出 schema 段落可能是从旧版 schema 复制的

#### 缺陷 3：Gate 测试不验证 Gate ↔ Prompt 一致性

**现状**：
```python
# test_gates.py
def test_good_blueprint_passes(self, good_blueprint):
    result = gate_architect(good_blueprint)
    assert result["decision"] == "PASS"
```

`good_blueprint` fixture 包含：
```python
{
    "project_type": "greenfield",  # ← Gate 检查这个
    "requirements": [
        {"mapped_components": ["COMP-001"]}  # ← Gate 检查这个
    ]
}
```

**真实情况**：
- `architect.md` prompt 的输出 schema **没有** `project_type` 字段
- `architect.md` prompt 的输出 schema **没有** `requirements[].mapped_components` 字段
- Gate 每次都触发 CONDITIONAL，但因为 `test_missing_project_type_conditional` 测试断言这是 PASS，所以测试通过

**结论**：测试验证了"Gate 代码逻辑正确"，但没验证"Gate 检查的字段在真实输出中存在"。这是**测试代码本身没有测试**的经典案例。

#### 缺陷 4：没有端到端集成测试

**现状**：
- `test_gates.py` 有 `TestFullPipeline`，但用的是 `real_case_crossborder/blackboard/` 的历史数据
- 没有测试**真正跑一次完整管线**并验证最终产物

**缺失的测试**：
```python
def test_end_to_end_pipeline():
    """Run full pipeline with real LLM calls and validate final output."""
    # 1. Run Solution Pro
    solution = run_solution_pro(test_requirements)
    
    # 2. Run Ship Pro
    package = run_ship_pro(solution)
    
    # 3. Validate against PRODUCTION schema
    import jsonschema
    with open("schemas/ship_package_v3.schema.json") as f:
        schema = json.load(f)
    jsonschema.validate(package, schema)  # ← 这个会立即暴露 128 个错误
```

### 1.2 为什么测试"通过"但系统"失败"

| 测试类型 | 测试了什么 | 没测试什么 | 结果 |
|:---|:---|:---|:---|
| **单元测试（gates）** | Gate 代码逻辑正确 | Gate 检查的字段在真实输出中存在 | ✅ 通过 |
| **单元测试（eval_checks）** | 硬编码 schema 校验逻辑正确 | 硬编码 schema = 生产 schema | ✅ 通过 |
| **集成测试（full pipeline）** | 历史数据能通过 gate | 新运行能产出符合 schema 的数据 | ✅ 通过（用旧数据） |
| **端到端测试** | ❌ 不存在 | — | ❌ 缺失 |
| **契约测试** | ❌ 不存在 | — | ❌ 缺失 |

---

## 二、契约测试（Contract Testing）在 DeepFlow 的应用

### 2.1 谁是 Consumer，谁是 Provider？

在微服务中，Consumer-Driven Contract Testing（如 Pact）的模式是：
- **Consumer**：调用方，定义"我期望收到什么"
- **Provider**：被调用方，承诺"我会输出什么"
- **Contract**：两者之间的正式协议

**DeepFlow 的映射**：

| 组件 | 角色 | 理由 |
|:---|:---|:---|
| **Architect Prompt** | Provider | 声明"我会输出这些字段" |
| **Architect Gate** | Consumer | 声明"我需要这些字段才能放行" |
| **JSON Schema** | Contract | 应该是两者的正式协议 |

**当前问题**：
- Provider（Prompt）说"我输出 `modules`, `dependencies`, `requirements`"
- Consumer（Gate）说"我需要 `project_type`, `requirements[].mapped_components`"
- Contract（Schema）说"我不管你们俩，我自己定义一套"
- **三者独立演化，无同步机制**

### 2.2 DeepFlow 应该写什么样的契约测试？

#### 契约 1：Prompt ↔ Schema

**测试目标**：Prompt 声明的输出字段必须在 Schema 中有定义。

**实现方式**：
```python
def test_architect_prompt_matches_schema():
    """Architect prompt's declared output fields must exist in schema."""
    # 1. Parse architect.md to extract output schema section
    prompt_schema = parse_prompt_output_schema("agents/architect/architect.md")
    
    # 2. Load production schema
    with open("schemas/architect_output.schema.json") as f:
        production_schema = json.load(f)
    
    # 3. Every field in prompt must be in schema
    for field in prompt_schema["required_fields"]:
        assert field in production_schema["properties"], \
            f"Prompt declares '{field}' but schema doesn't have it"
    
    # 4. Every required field in schema must be in prompt
    for field in production_schema["required"]:
        assert field in prompt_schema["required_fields"], \
            f"Schema requires '{field}' but prompt doesn't declare it"
```

**价值**：如果 architect.md 说"输出 `project_type`"，但 schema 没有这个字段，测试立即失败。

#### 契约 2：Gate ↔ Schema

**测试目标**：Gate 检查的字段必须在 Schema 中有定义。

**实现方式**：
```python
def test_gate_checks_only_schema_fields():
    """Gate must only check fields that exist in schema."""
    # 1. Inspect gate_architect() to find checked fields
    # (This requires static analysis or explicit field declarations)
    gate_fields = ["project_type", "requirements.mapped_components", ...]
    
    # 2. Load schema
    with open("schemas/architect_output.schema.json") as f:
        schema = json.load(f)
    
    # 3. Every gate field must be in schema
    for field in gate_fields:
        assert field_in_schema(field, schema), \
            f"Gate checks '{field}' but schema doesn't define it"
```

**价值**：防止 Gate 检查"幽灵字段"。

#### 契约 3：Cross-Domain Contract（Solution Pro ↔ Ship Pro）

**测试目标**：Solution Pro 的输出必须符合 Ship Pro 的输入期望。

**实现方式**：
```python
def test_solution_pro_output_matches_ship_pro_input():
    """Solution Pro's final artifacts must satisfy Ship Pro's input contract."""
    # 1. Define Ship Pro input contract
    ship_pro_input_contract = {
        "required_files": ["final_solution.md", "frozen_blueprint.json"],
        "schema": "schemas/solution_pro_output.schema.json"
    }
    
    # 2. Run Solution Pro (or load recent output)
    solution_output = load_solution_pro_output()
    
    # 3. Validate
    for file in ship_pro_input_contract["required_files"]:
        assert file in solution_output["artifacts"], \
            f"Ship Pro needs '{file}' but Solution Pro didn't produce it"
    
    jsonschema.validate(solution_output, ship_pro_input_contract["schema"])
```

**价值**：防止 6/23 的 `frozen_blueprint.json` 未生成问题。

### 2.3 契约测试的局限性

**LLM 输出的不确定性**：
- LLM 可能输出契约中未声明的额外字段（如 `constraints`, `related_modules`）
- LLM 可能用不同的字段名（如 `wp_id` vs `id`）
- LLM 可能输出枚举外的值（如 `"standard"` vs `"claude-sonnet"`）

**契约能约束的**：
- ✅ 必填字段必须存在
- ✅ 字段类型必须正确
- ✅ 枚举值必须在范围内
- ✅ 数组长度必须满足 minItems

**契约不能约束的**：
- ❌ LLM 是否会"创造性地"添加额外字段
- ❌ 字段值的语义正确性（如 `objective` 是否真的描述了任务目标）
- ❌ 字段之间的逻辑一致性（如 `dependencies` 引用的 WP 是否真的存在）

**结论**：契约测试是**必要条件但不是充分条件**。需要配合 schema 严格校验（拒绝额外字段）和语义 eval（L2 eval）。

---

## 三、Gate 的可靠性：测试代码本身没有测试

### 3.1 问题的本质

**Gate 代码 ↔ Prompt 描述不一致** 本质上是 **"测试代码本身没有测试"** 的变体。

在软件测试中，我们有一个递归问题：
- 测试代码验证生产代码
- 谁来验证测试代码？
- 如果测试代码有 bug，谁来发现？

**DeepFlow 的具体表现**：
- Gate 代码 = 测试代码（验证 LLM 输出）
- Prompt = 生产代码（指导 LLM 输出）
- Gate 检查 `project_type`，但 Prompt 不输出 `project_type`
- 测试用 fixture 有 `project_type`，所以测试通过
- **没有人验证"Gate 检查的字段在 Prompt 输出中真实存在"**

### 3.2 如何打破这个循环？

#### 方案 1：契约测试（推荐）

如前所述，写 Prompt ↔ Schema ↔ Gate 的三方契约测试。

#### 方案 2：Property-Based Testing

用 Hypothesis 生成随机但符合 schema 的数据，测试 Gate 的行为：

```python
from hypothesis import given, strategies as st

# Define a strategy that generates schema-compliant data
@given(st.fixed_dictionaries({
    "project_type": st.sampled_from(["greenfield", "migration", ...]),
    "modules": st.lists(module_strategy(), min_size=1),
    "requirements": st.lists(requirement_strategy(), min_size=1),
    ...
}))
def test_gate_always_passes_for_schema_compliant_data(blueprint):
    """If data matches schema, gate MUST pass."""
    result = gate_architect(blueprint)
    assert result["decision"] == "PASS", \
        f"Schema-compliant data should pass, got {result['decision']}"

@given(st.dictionaries(...))  # Generate data that violates schema
def test_gate_always_fails_for_schema_violations(blueprint):
    """If data violates schema, gate MUST fail."""
    # Inject a schema violation
    blueprint["modules"] = []  # Critical violation
    result = gate_architect(blueprint)
    assert result["decision"] == "FAIL"
```

**价值**：如果 Gate 检查了一个 schema 中没有的字段，property-based test 会生成不包含该字段的数据，暴露问题。

#### 方案 3：Mutation Testing

对 Gate 代码做变异测试，验证 Gate 能检测出各种变异：

```python
# Original gate code
def gate_architect(blueprint):
    critical["modules_non_empty"] = len(blueprint.get("modules", [])) > 0

# Mutant: invert the check
def gate_architect_mutant(blueprint):
    critical["modules_non_empty"] = len(blueprint.get("modules", [])) == 0  # ← mutated

# Test suite should FAIL the mutant
# If tests still pass, the gate is not effective
```

**价值**：验证 Gate 代码真的在"检查"，而不是"走过场"。

#### 方案 4：生产数据回放（最实用）

**收集真实的 LLM 输出**，建立回归测试集：

```python
def test_gate_against_real_llm_outputs():
    """Test gate against collected real LLM outputs."""
    # Load 50+ real architect outputs from production runs
    for run_id in get_real_run_ids("architect"):
        real_output = load_real_output(run_id)
        result = gate_architect(real_output)
        
        # Log the result for analysis
        log_gate_result(run_id, result)
        
        # If gate says CONDITIONAL, investigate why
        if result["decision"] == "CONDITIONAL":
            print(f"Run {run_id}: {result['feedback']}")
```

**价值**：立即暴露"Gate 总是触发 CONDITIONAL"的问题。

### 3.3 推荐组合

| 方案 | 实施成本 | 检测能力 | 推荐优先级 |
|:---|:---|:---|:---|
| 契约测试 | 中 | 高（防止 Prompt/Gate/Schema 分裂） | 🔴 P0 |
| 生产数据回放 | 低 | 高（暴露真实问题） | 🔴 P0 |
| Property-Based Testing | 中 | 中（覆盖边界情况） | 🟡 P1 |
| Mutation Testing | 高 | 中（验证 Gate 有效性） | 🟢 P2 |

---

## 四、LLM 输出的测试策略

### 4.1 传统单元测试够用吗？

**不够。**

传统单元测试假设：
- 输入确定 → 输出确定
- 可以用 assert 精确比较

LLM 输出的特点：
- 输入相同 → 输出可能不同（temperature > 0）
- 输出是半结构化 JSON（可能有额外字段、字段顺序不同）
- 语义正确性难以用 assert 判断（如 `objective` 描述是否准确）

### 4.2 推荐的 LLM 输出测试策略

#### 层次 1：Schema 严格校验（确定性）

**工具**：`jsonschema` 库

**测试内容**：
- 必填字段存在
- 字段类型正确
- 枚举值在范围内
- 数组长度满足约束
- **拒绝额外字段**（`additionalProperties: false`）

**示例**：
```python
import jsonschema

def test_llm_output_strict_schema():
    """LLM output must match schema exactly."""
    with open("schemas/ship_package_v3.schema.json") as f:
        schema = json.load(f)
    
    # Enable strict mode: reject additional properties
    schema["additionalProperties"] = False
    for prop in schema["properties"].values():
        if prop["type"] == "object":
            prop["additionalProperties"] = False
    
    # This will catch the 128 errors immediately
    jsonschema.validate(llm_output, schema)
```

**关键**：必须在生产代码中也启用 `additionalProperties: false`，否则 LLM 会添加额外字段。

#### 层次 2：Property-Based Testing（半确定性）

**工具**：`hypothesis` 库

**测试内容**：
- 生成符合 schema 的随机数据
- 验证 Gate/Eval 代码的行为一致性
- 发现边界情况

**示例**：
```python
from hypothesis import given, strategies as st
from hypothesis_jsonschema import from_schema

@given(from_schema(load_schema("ship_package_v3.schema.json")))
def test_gate_always_passes_for_valid_data(package):
    """Any schema-compliant data should pass the gate."""
    result = gate_packager(package)
    assert result["decision"] == "PASS"
```

#### 层次 3：Snapshot Testing（语义一致性）

**工具**：`syrupy` 或自定义 snapshot 工具

**测试内容**：
- 对同一输入，LLM 输出的"结构"应该稳定
- 字段值可以不同，但字段集合应该一致
- 用于检测"LLM 突然开始输出新字段"

**示例**：
```python
def test_architect_output_snapshot(snapshot):
    """Architect output structure should be stable."""
    output = run_architect(test_requirements)
    
    # Snapshot only the structure (field names), not values
    structure = extract_structure(output)
    assert structure == snapshot
```

#### 层次 4：Fuzz Testing（鲁棒性）

**工具**：自定义 fuzzer

**测试内容**：
- 向 Gate/Eval 代码注入畸形 JSON
- 验证不会 crash
- 验证能正确报告错误

**示例**：
```python
def test_gate_handles_malformed_json():
    """Gate should gracefully handle malformed input."""
    malformed_inputs = [
        {},  # Empty
        {"modules": None},  # Null field
        {"modules": "not a list"},  # Wrong type
        {"modules": [{"id": 123}]},  # Wrong field type
        ...
    ]
    
    for input_data in malformed_inputs:
        result = gate_architect(input_data)
        assert result["decision"] in ("FAIL", "CONDITIONAL")
        assert "feedback" in result  # Must explain why
```

#### 层次 5：语义 Eval（LLM 驱动）

**工具**：L2 Eval（如 `eval_ac_verifiability`）

**测试内容**：
- Acceptance Criteria 是否可执行
- Objective 是否清晰
- Dependencies 是否合理

**示例**：
```python
def test_acceptance_criteria_quality():
    """ACs should be executable, not vague."""
    package = run_packager(test_input)
    
    result = score_all_acs(package["work_packages"])
    assert result["mean_score"] >= 80, \
        f"AC quality too low: {result['mean_score']}"
    assert result["distribution"]["L1"] == 0, \
        f"No vague ACs allowed: {result['distribution']['L1']} found"
```

### 4.3 推荐测试金字塔

```
        /\
       /  \      语义 Eval（L2 Eval）
      / E  \     - AC 可执行性
     /______\    - 目标清晰度
    /        \
   / Property \   Property-Based Testing
  /   Based    \  - Schema 边界情况
 /______________\ - Gate 行为一致性
/                \
/   Snapshot &   \  Snapshot + Fuzz Testing
/     Fuzz        \ - 结构稳定性
/__________________\  - 畸形输入鲁棒性
/                    \
/   Schema Strict    \  Schema 严格校验
/   Validation        \ - 字段存在性
/______________________\  - 类型正确性
```

---

## 五、质量门禁的分级：PASS/CONDITIONAL/FAIL

### 5.1 当前设计分析

**当前逻辑**：
- Critical 失败 → FAIL
- Major 失败 > 50% → CONDITIONAL
- Minor 失败 → PASS（仅记录）

**问题**：
- CONDITIONAL 允许"带病继续"，导致下游收到不合格数据
- 6/23 案例：Architect Gate 触发 CONDITIONAL（缺 `project_type`），但继续运行 → Decomposer 收到不完整的 blueprint → 下游连锁失败

### 5.2 什么时候应该 Fail-Fast？

**Fail-Fast 的条件**：
1. **Schema 校验失败** → 立即 FAIL，不 CONDITIONAL
   - 理由：Schema 是合同，违反合同 = 无法继续
2. **Critical 字段缺失** → 立即 FAIL
   - 理由：下游依赖这些字段，缺失 = 下游必然失败
3. **状态机不一致** → 立即 FAIL
   - 理由：状态不一致 = 系统不可信

**CONDITIONAL 的条件**：
1. **Optional 字段缺失** → CONDITIONAL + 警告
2. **Minor 质量指标下降** → CONDITIONAL + 记录
3. **非阻塞性格式问题** → CONDITIONAL + 自动修复尝试

### 5.3 推荐的质量门禁分级

```python
class GateDecision(Enum):
    FAIL = "FAIL"              # 立即停止，人工介入
    FAIL_AUTO_RETRY = "FAIL_RETRY"  # 自动重试（最多 N 次）
    CONDITIONAL = "CONDITIONAL"     # 继续，但记录警告
    PASS = "PASS"              # 正常通过

def make_decision(critical_failures, major_failures, minor_failures):
    # 1. Schema 校验失败 → FAIL（不重试，因为是系统性问题）
    if any(f["type"] == "schema_violation" for f in critical_failures):
        return GateDecision.FAIL
    
    # 2. Critical 字段缺失 → FAIL_RETRY（可能是 LLM 随机性）
    if len(critical_failures) > 0:
        return GateDecision.FAIL_AUTO_RETRY
    
    # 3. Major 失败 > 50% → CONDITIONAL + 警告
    if len(major_failures) > len(major_checks) * 0.5:
        return GateDecision.CONDITIONAL
    
    # 4. Minor 失败 → PASS
    return GateDecision.PASS
```

### 5.4 CONDITIONAL 的安全使用

**如果允许 CONDITIONAL 继续**，必须：
1. **记录到状态文件**：`pipeline_status.json` 中标记 `warnings: [...]`
2. **下游 Gate 感知**：下游 Gate 检查上游的 warnings，决定是否累积失败
3. **最终汇总**：Packager Gate 检查所有上游 warnings，如果累积过多 → FAIL

**示例**：
```python
def gate_packager(package, upstream_warnings):
    """Packager gate considers upstream warnings."""
    if len(upstream_warnings) > 3:
        return {
            "decision": "FAIL",
            "feedback": f"Too many upstream warnings: {upstream_warnings}"
        }
    ...
```

---

## 六、最小质量保障方案（单人维护项目）

### 6.1 核心原则

**对于单人项目，质量保障必须：**
- ✅ 自动化（无人工审查时间）
- ✅ 快速（< 5 分钟跑完）
- ✅ 高信噪比（只报告真正的问题）
- ✅ 低维护成本（< 1 小时/周）

### 6.2 最小质量保障套件

#### 套件 1：契约测试（防分裂）

**文件**：`tests/contract/test_prompt_schema_alignment.py`

**内容**：
```python
def test_all_prompts_match_schemas():
    """Every agent's prompt output schema must match its JSON schema."""
    for agent in ["architect", "decomposer", "specifier", "packager"]:
        prompt_schema = parse_prompt_output_schema(f"agents/{agent}/{agent}.md")
        json_schema = load_json(f"schemas/{agent}_output.schema.json")
        assert schemas_compatible(prompt_schema, json_schema)

def test_all_gates_check_schema_fields():
    """Every gate must only check fields defined in schema."""
    for agent in ["architect", "decomposer", "specifier", "packager"]:
        gate_fields = extract_gate_fields(f"eval/gates.py::gate_{agent}")
        json_schema = load_json(f"schemas/{agent}_output.schema.json")
        for field in gate_fields:
            assert field_in_schema(field, json_schema)
```

**运行频率**：每次修改 prompt 或 schema 时

#### 套件 2：生产数据回归测试（暴露真实问题）

**文件**：`tests/regression/test_real_llm_outputs.py`

**内容**：
```python
def test_gates_against_collected_outputs():
    """Test gates against 50+ real LLM outputs."""
    for run_id in get_real_runs("architect", limit=50):
        output = load_real_output(run_id)
        result = gate_architect(output)
        
        # If gate says CONDITIONAL > 80% of the time, something is wrong
        conditional_rate = get_conditional_rate("architect")
        assert conditional_rate < 0.2, \
            f"Architect gate CONDITIONAL rate too high: {conditional_rate}"
```

**运行频率**：每周一次，或收集到 10+ 新运行时

#### 套件 3：端到端 Smoke Test（验证整体可用）

**文件**：`tests/e2e/test_smoke.py`

**内容**：
```python
def test_end_to_end_smoke():
    """Run full pipeline with minimal input and validate output."""
    # Use a simple test case (e.g., TODO app)
    requirements = load_test_requirements("tests/fixtures/todo_app.md")
    
    # Run pipeline (with timeout)
    package = run_ship_pro(requirements, timeout_minutes=10)
    
    # Validate against production schema
    jsonschema.validate(package, load_schema("ship_package_v3.schema.json"))
    
    # Validate AC quality
    ac_result = score_all_acs(package["work_packages"])
    assert ac_result["mean_score"] >= 70
```

**运行频率**：每次重大修改后，或每周一次

#### 套件 4：Schema 严格校验（生产代码）

**修改**：`run_pipeline.py`

**内容**：
```python
def validate_stage_output(stage_name, output):
    """Validate stage output against production schema with strict mode."""
    schema = load_schema(f"schemas/{stage_name}_output.schema.json")
    schema["additionalProperties"] = False  # Reject extra fields
    
    try:
        jsonschema.validate(output, schema)
    except jsonschema.ValidationError as e:
        log.error(f"Schema validation failed for {stage_name}: {e.message}")
        raise PipelineError(f"{stage_name} output does not match schema")
```

**关键点**：必须在生产代码中启用，不只是测试

#### 套件 5：状态一致性检查（防状态机分裂）

**文件**：`tests/integration/test_state_consistency.py`

**内容**：
```python
def test_pipeline_status_consistent():
    """All status files must agree on pipeline state."""
    pipeline_status = load_json("blackboard/pipeline_status.json")
    stage_progress = load_json("blackboard/.stage_progress.json")
    completed = load_json("blackboard/.completed.json")
    
    # If pipeline says "completed", all stages must be completed
    if pipeline_status["state"] == "completed":
        for stage in AGENT_ORDER:
            assert stage_progress[stage]["status"] == "completed"
        assert completed["status"] == "completed"
```

**运行频率**：每次运行后自动检查

### 6.3 实施优先级

| 套件 | 实施时间 | 维护成本 | 检测能力 | 优先级 |
|:---|:---|:---|:---|:---|
| Schema 严格校验 | 2 小时 | 0 | 高 | 🔴 P0 |
| 契约测试 | 4 小时 | 1 小时/周 | 高 | 🔴 P0 |
| 状态一致性检查 | 2 小时 | 0 | 中 | 🔴 P0 |
| 生产数据回归 | 4 小时 | 2 小时/周 | 高 | 🟡 P1 |
| 端到端 Smoke | 4 小时 | 1 小时/周 | 中 | 🟡 P1 |

**总计**：~16 小时实施，~4 小时/周维护

---

## 七、盲点与风险

### 7.1 Contract Layer 本身可能引入的问题

#### 风险 1：过度工程化

**问题**：Contract Layer 引入 `contract.yaml`，需要编写解析器、代码生成器、验证器。对于单人项目，这可能过于复杂。

**建议**：从**最小契约**开始 — 只要求 Prompt、Gate、Schema 三者的字段列表一致，不引入新的 DSL。

#### 风险 2：契约测试成为新的"测试代码没测试"

**问题**：契约测试本身可能有 bug，导致"契约测试通过但实际不一致"。

**建议**：契约测试用**最简单的代码**（字段名集合比较），不用复杂的解析逻辑。

#### 风险 3：Schema 严格校验降低 LLM 成功率

**问题**：LLM 可能因为 prompt 不精确而输出额外字段，严格校验会导致频繁失败。

**建议**：
- 开发阶段：宽松校验（允许额外字段）
- 生产阶段：严格校验（拒绝额外字段）
- 通过 A/B 测试找到平衡点

### 7.2 未被讨论的问题

#### 问题 1：Prompt 版本管理

**现状**：Prompt 是 Markdown 文件，没有版本号，没有变更日志。

**风险**：修改 prompt 后，无法知道"这个输出是哪个版本的 prompt 生成的"。

**建议**：
- Prompt 文件加版本头：`<!-- version: 3.1.3 -->`
- LLM 输出加 `prompt_version` 字段
- 测试时验证 `prompt_version` 与当前 prompt 匹配

#### 问题 2：Gate 的反馈不够 actionable

**现状**：Gate 失败时，反馈是 `{"project_type_exists": False}`，不告诉 LLM 如何修复。

**建议**：Gate 反馈应该包含修复指令：
```python
{
    "decision": "FAIL",
    "feedback": "Missing required field 'project_type'. Add it to your output with value from ['greenfield', 'migration', ...]",
    "retry_instructions": "Include 'project_type' field in your JSON output."
}
```

#### 问题 3：没有"质量趋势"监控

**现状**：每次运行独立，无法知道"系统质量在恶化还是改善"。

**建议**：
- 每次运行记录 Gate 结果到 `quality_metrics.jsonl`
- 每周生成趋势报告：CONDITIONAL 率、FAIL 率、AC 质量分数
- 设置告警：如果 CONDITIONAL 率 > 30%，立即调查

---

## 八、建议与优先级

### 8.1 立即行动（本周）

#### 行动 1：启用 Schema 严格校验

**修改文件**：`run_pipeline.py`

```python
def validate_stage_output(stage_name, output):
    schema = load_schema(f"schemas/{stage_name}_output.schema.json")
    schema["additionalProperties"] = False
    jsonschema.validate(output, schema)
```

**预期效果**：立即暴露所有 schema 不一致问题，强制修复。

#### 行动 2：对齐 Packager Prompt 与 Schema

**修改文件**：`agents/packager/packager.md`

- 更新输出 schema 段落，与 `ship_package_v3.schema.json` 一致
- 删除 `_meta` 字段（schema 不允许）
- 修正 `meta.input_format` 的枚举值
- 删除 `work_packages[].constraints`/`related_modules`/`requirements`（schema 没有）

**预期效果**：消除 128 个 schema 错误。

#### 行动 3：对齐 Architect Prompt 与 Gate

**选择 A**：修改 Prompt，添加 `project_type` 和 `requirements[].mapped_components`

**选择 B**：修改 Gate，删除对这两个字段的检查

**建议**：选择 A（添加字段），因为这些字段有实际价值。

### 8.2 短期行动（2 周内）

#### 行动 4：编写契约测试

**文件**：`tests/contract/test_prompt_schema_alignment.py`

**内容**：如前所述，验证 Prompt ↔ Schema ↔ Gate 一致性。

#### 行动 5：收集生产数据，建立回归测试集

**步骤**：
1. 修改 `run_pipeline.py`，每次运行保存 LLM 输出到 `data/real_outputs/`
2. 编写脚本，从收集的数据中筛选"有代表性的样本"
3. 编写回归测试，用这些样本测试 Gate

#### 行动 6：编写端到端 Smoke Test

**文件**：`tests/e2e/test_smoke.py`

**内容**：如前所述，跑完整条管线并验证最终产物。

### 8.3 中期行动（1 个月内）

#### 行动 7：实施 Contract Layer Phase 1

**参考提案**：`deepflow_contract_layer_review_20260623.md`

**关键**：从最简单的 `contract.yaml` 开始，只定义必填字段，不引入复杂 DSL。

#### 行动 8：实施状态一致性检查

**文件**：`tests/integration/test_state_consistency.py`

**内容**：验证 `pipeline_status.json`、`.stage_progress.json`、`.completed.json` 一致。

#### 行动 9：建立质量趋势监控

**文件**：`scripts/quality_metrics.py`

**内容**：每次运行记录 Gate 结果，每周生成趋势报告。

---

## 九、总结

### 核心判断

1. **诊断准确**：DeepFlow 确实缺少合同层，导致 Prompt/Gate/Schema 分裂
2. **但不止于此**：测试策略本身有缺陷（合成 fixture、测试 schema ≠ 生产 schema、无端到端测试）
3. **Contract Layer 是正确方向**：但需要从"最小契约"开始，避免过度工程化
4. **立即行动优先**：启用 Schema 严格校验、对齐 Prompt 与 Schema、收集生产数据

### 最小质量保障套件

| 套件 | 目的 | 实施时间 | 优先级 |
|:---|:---|:---|:---|
| Schema 严格校验 | 防止 128 个错误再次发生 | 2 小时 | 🔴 P0 |
| 契约测试 | 防止 Prompt/Gate/Schema 分裂 | 4 小时 | 🔴 P0 |
| 状态一致性检查 | 防止状态机分裂 | 2 小时 | 🔴 P0 |
| 生产数据回归 | 暴露真实 LLM 输出问题 | 4 小时 | 🟡 P1 |
| 端到端 Smoke | 验证整体可用性 | 4 小时 | 🟡 P1 |

### 最终建议

**不要等 Contract Layer 全部完成才开始测试。**

**今天就做**：
1. 在 `run_pipeline.py` 中加 10 行代码，启用 Schema 严格校验
2. 对齐 Packager Prompt 与 Schema（消除 128 个错误）
3. 对齐 Architect Prompt 与 Gate（消除 CONDITIONAL）

**本周做**：
4. 写契约测试（防止再次分裂）
5. 收集生产数据（建立回归测试集）

**下周做**：
6. 写端到端 Smoke Test
7. 建立质量趋势监控

**下个月做**：
8. 实施 Contract Layer Phase 1

---

*评审完成。报告路径：`/Users/allen/.openclaw/workspace/.deepflow/reviews/expert_5_quality_engineering.md`*
