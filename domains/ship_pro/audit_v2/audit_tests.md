# Ship Pro 测试与自动化审计报告

> **审计版本**: v2.0
> **审计日期**: 2026-07-16
> **审计范围**: `test_ship_compiler.py` (14 tests, 47 assertions) vs `ship_compiler.py` (424 lines) + `ship_pro_v0.1.yaml` 契约
> **运行结果**: 47 passed, 0 failed ✅

---

## 一、测试覆盖率

**状态: 🟡 YELLOW**

### 1.1 契约红线 (RED-SHIP) 覆盖

| 红线 | 规则 | 测试覆盖 | 状态 |
|------|------|----------|------|
| RED-SHIP-001 | 只消费 frozen_blueprint.json | 间接覆盖 — 所有测试仅喂入 frozen_blueprint.json，但无负面测试（喂入非 frozen_blueprint 文件验证拒绝） | 🟡 |
| RED-SHIP-002 | blocked 时禁止生成 Ship Package | ✅ Test 3 (`test_blocked_readiness`) — 验证 status=blocked + work_packages 为空 | 🟢 |
| RED-SHIP-003 | Ship Package 必须通过 JSON Schema 校验 | ❌ **无测试** — `ship_package.schema.json` 存在但从未在测试中使用 | 🔴 |
| RED-SHIP-004 | 禁止重新定义需求/重做架构 | 静态保证（代码中无 redefine/redesign 逻辑），无运行时测试 | 🟡 |
| RED-SHIP-005 | 禁止调用 Codex | 静态保证（代码中无 codex/sessions_spawn），无运行时测试 | 🟡 |
| RED-SHIP-006 | not_verified 记录到 risk_register 不阻断 | ✅ Test 7 (`test_not_verified_to_risk_register`) | 🟢 |
| RED-SHIP-007 | forbidden_changes 完整传递 | ✅ Test 6 (`test_forbidden_changes_propagation`) — risk_contract + harmony_brief + WP constraints | 🟢 |
| RED-SHIP-008 | 确定性脚本，禁止 LLM | ✅ Test 13 (`test_determinism`) — 两次运行完全一致 | 🟢 |

**红线覆盖率**: 4/8 有运行时测试 (50%)，2/8 有静态保证 (75%)，2/8 完全未验证 (RED-SHIP-003 是最严重的缺口)

### 1.2 代码路径覆盖

| 代码路径 | 函数 | 测试覆盖 | 状态 |
|----------|------|----------|------|
| 环依赖检测 | `_topo_sort` | ✅ Test 1 | 🟢 |
| 空模块 fallback | `_decompose_work_packages` | ✅ Test 2 | 🟢 |
| blocked readiness | `_check_readiness` | ✅ Test 3 | 🟢 |
| 全同 tier fallback | `_compute_phase_map` | ✅ Test 4 | 🟢 |
| Golden sample 端到端 | `compile_ship_package` | ✅ Test 5 | 🟢 |
| forbidden_changes 传递 | `_decompose_work_packages` + `_generate_risk_contract` | ✅ Test 6 | 🟢 |
| not_verified → risk_register | `_generate_risk_contract` | ✅ Test 7 | 🟢 |
| source_blueprint 正确性 | `compile_ship_package` (meta) | ✅ Test 8 | 🟢 |
| 组件级 AC 生成 | `_generate_module_ac` | ✅ Test 9 | 🟢 |
| 需求均匀分配 | `_assign_requirements` | ✅ Test 10 | 🟢 |
| 全自动化验证 | 多处 | ✅ Test 11 | 🟢 |
| Schema 校验（输入） | `_load_frozen_blueprint` | ✅ Test 12 | 🟢 |
| 确定性 | `compile_ship_package` | ✅ Test 13 | 🟢 |
| 非法 JSON 处理 | `_load_frozen_blueprint` | ✅ Test 14 | 🟢 |
| **文件不存在** | `_load_frozen_blueprint` | ❌ 无测试 | 🔴 |
| **合约名不匹配** | `_load_frozen_blueprint` | ❌ 无测试 | 🔴 |
| **输出 JSON Schema 校验** | `compile_ship_package` 输出 | ❌ 无测试 (RED-SHIP-003) | 🔴 |
| **ready_with_conditions 状态映射** | `_check_readiness` | ❌ 无测试 | 🔴 |
| **needs_clarification 状态映射** | `_check_readiness` | ❌ 无测试 | 🔴 |
| **空需求列表** | `_assign_requirements` | ❌ 无测试 | 🟡 |
| **模块无 summary** | `_generate_module_ac` | ❌ 无测试 | 🟡 |
| **Markdown 输出正确性** | `_generate_markdown` | ❌ 无测试 | 🟡 |
| **原子写入** | `_write_json_atomic` / `_write_text_atomic` | ❌ 无测试 | 🟡 |
| **大规模模块 (10+)** | `_compute_phase_map` + `_decompose_work_packages` | ❌ 无测试 | 🟡 |
| **technology_choices 传递** | `_generate_harmony_brief` | ❌ 无测试 | 🟡 |
| **blocking_before_start (P0 missing)** | `_generate_risk_contract` | ❌ 无测试 | 🔴 |
| **known_gaps critical → blocking** | `_generate_risk_contract` | ❌ 无测试 | 🔴 |

### 1.3 发现项

| # | 严重度 | 发现 |
|---|--------|------|
| C-01 | **P0** | RED-SHIP-003 无运行时测试 — ship_package.schema.json 存在但从未用于校验输出 |
| C-02 | **P1** | 文件不存在路径未测试 — `_load_frozen_blueprint` 的 `FileNotFoundError` 分支无覆盖 |
| C-03 | **P1** | 合约名不匹配未测试 — `_load_frozen_blueprint` 的 contract_name 校验分支无覆盖 |
| C-04 | **P1** | `ready_with_conditions` / `needs_clarification` → `conditional_ship` 映射无测试 |
| C-05 | **P1** | `blocking_before_start` (P0 req missing / critical gap) 逻辑无测试 |
| C-06 | **P2** | `known_gaps` critical → blocking 逻辑无测试 |
| C-07 | **P2** | Markdown 输出正确性无测试 |
| C-08 | **P2** | 大规模模块 (10+) 的 phase 分配无测试 |

---

## 二、测试质量

**状态: 🟡 YELLOW**

### 2.1 断言充分性

| 方面 | 评价 | 状态 |
|------|------|------|
| 断言粒度 | 每条断言检查一个具体条件，消息清晰 | 🟢 |
| 断言覆盖 | 核心路径断言充分 | 🟢 |
| 负面断言 | 有（环依赖检测、非法 JSON、缺失 section） | 🟢 |
| 边界值断言 | 不足 — 缺少空输入、零模块、单模块等边界 | 🟡 |
| Schema 断言 | 缺失 — 未用 jsonschema 库做结构校验 | 🔴 |

### 2.2 测试独立性

| 方面 | 评价 | 状态 |
|------|------|------|
| 文件系统隔离 | ✅ 每个测试使用独立 `tempfile.mkdtemp` + `shutil.rmtree` | 🟢 |
| 全局状态 | ✅ 无全局状态污染（PASSED/FAILED 计数器除外） | 🟢 |
| 测试间依赖 | ✅ 无测试依赖另一个测试的结果 | 🟢 |
| Golden sample 依赖 | ⚠️ Test 5 依赖外部 blackboard 文件存在，文件不存在时静默跳过 | 🟡 |

### 2.3 测试数据有效性

| 方面 | 评价 | 状态 |
|------|------|------|
| `_make_base_bp` 工厂 | ✅ 生成合规的 frozen_blueprint 结构 | 🟢 |
| 数据多样性 | ⚠️ 多数测试使用 1-2 个模块的简单场景 | 🟡 |
| 真实场景 | ✅ Golden sample 使用真实项目数据 | 🟢 |
| 极端数据 | ❌ 缺少极端场景（100 模块、超长文本、特殊字符） | 🔴 |

### 2.4 发现项

| # | 严重度 | 发现 |
|---|--------|------|
| Q-01 | **P1** | 未使用 `jsonschema` 库做输出结构校验 — 测试手动检查 section 存在性，但不验证完整 schema 合规性 |
| Q-02 | **P1** | 使用自定义 `_assert` 而非 pytest — 无法利用 pytest 的 fixture、parametrize、详细报告、失败继续 |
| Q-03 | **P2** | Golden sample 测试 (Test 5) 是非确定性的 — 文件不存在时静默跳过，CI 环境可能永远不运行 |
| Q-04 | **P2** | 缺少 pytest 参数化 — 多个测试结构相似（创建 temp dir → 写 JSON → 编译 → 断言 → 清理），可参数化减少重复 |
| Q-05 | **P2** | PASSED/FAILED 全局变量 — 测试不可并行运行 |

---

## 三、自动化程度

**状态: 🟢 GREEN**

### 3.1 全自动化验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 测试是否纯自动化 | ✅ 100% | 运行 `python3 test_ship_compiler.py` 无任何人工交互 |
| `human_review_required` 是否完全移除 | ✅ 所有 WP 均为 `false` | Test 11 显式验证 |
| `human_review_points` 是否为空 | ✅ risk_contract + harmony_brief 均为 `[]` | Test 11 显式验证 |
| 编译器是否含 LLM 调用 | ✅ 无 | grep 确认无 openai/anthropic/llm/chat_completion |
| 编译器是否含 Codex 调用 | ✅ 无 | grep 确认无 codex/sessions_spawn/agent_task |
| 编译器是否读取上游内部文件 | ✅ 无 | grep 确认无 final_result/frozen_spec/harness_final/control_contract/stages/ |
| 测试是否可在 CI 中运行 | ✅ 可 | 仅依赖标准库 + 本地文件系统 |

### 3.2 发现项

| # | 严重度 | 发现 |
|---|--------|------|
| A-01 | **P2** | 无 CI 配置文件 — 测试可自动化但没有 CI pipeline 定义（GitHub Actions / GitLab CI 等） |
| A-02 | **P2** | 无测试运行 hook — 没有 pre-commit 或 Makefile 确保提交前运行测试 |

---

## 四、可维护性

**状态: 🟡 YELLOW**

### 4.1 测试代码清晰度

| 方面 | 评价 | 状态 |
|------|------|------|
| 命名 | ✅ 函数名清晰表达测试意图 | 🟢 |
| 注释 | ✅ 每个测试有 docstring 说明目的 | 🟢 |
| 结构 | ✅ 测试编号 + 分隔线 + 统一格式 | 🟢 |
| 辅助函数 | ✅ `_make_base_bp` + `_write_frozen` + `_assert` 封装合理 | 🟢 |

### 4.2 扩展性

| 方面 | 评价 | 状态 |
|------|------|------|
| 添加新测试 | 🟡 需要手动在 `main()` 中注册新测试函数 | 🟡 |
| 参数化 | 🔴 无参数化 — 相似测试场景需要复制粘贴 | 🔴 |
| Fixture 复用 | 🔴 无 fixture — temp dir 创建/清理在每个测试中重复 | 🔴 |
| 测试选择 | 🔴 无法运行单个测试（无 pytest mark 或 tag） | 🔴 |

### 4.3 运行时间

| 方面 | 评价 | 状态 |
|------|------|------|
| 总运行时间 | ✅ < 2 秒（14 个测试，47 个断言） | 🟢 |
| Golden sample 依赖 | ⚠️ 如果 blackboard 文件不存在则跳过，运行时间不稳定 | 🟡 |

### 4.4 发现项

| # | 严重度 | 发现 |
|---|--------|------|
| M-01 | **P1** | 未使用 pytest — 自定义测试框架限制了测试选择、参数化、fixture 复用、CI 集成 |
| M-02 | **P2** | temp dir 创建/清理代码重复 — 14 个测试中有 10 个重复 `mkdtemp` + `try/finally/rmtree` 模式 |
| M-03 | **P2** | 无 conftest.py — 缺少共享 fixture（如 `_make_base_bp`、temp dir、schema path） |
| M-04 | **P2** | 无测试运行入口（如 `Makefile` target 或 `pytest.ini`） |

---

## 总结

### 各维度状态

| 维度 | 状态 | 核心问题 |
|------|------|----------|
| 测试覆盖率 | 🟡 YELLOW | RED-SHIP-003 (Schema 校验) 无测试；多个代码路径未覆盖 |
| 测试质量 | 🟡 YELLOW | 未使用 jsonschema 验证输出；自定义 assert 而非 pytest |
| 自动化程度 | 🟢 GREEN | 100% 自动化，无 human_review 残留 |
| 可维护性 | 🟡 YELLOW | 自定义测试框架限制扩展性；缺少 pytest 生态 |

### 总评

**测试套件在核心功能覆盖上表现良好**（14 个测试，47 个断言，全部通过），特别是在关键契约红线（RED-SHIP-002/006/007/008）和核心代码路径（环检测、blocked 处理、forbidden 传递、确定性）上有充分验证。全自动化程度高，无 human_review 残留。

**主要缺口**：
1. **RED-SHIP-003 无运行时测试** — 这是 P0 级缺口。`ship_package.schema.json` 已存在，但没有测试验证输出合规性。这意味着编译器可能产出结构不合规的 Ship Package 而测试不会发现。
2. **自定义测试框架** — 使用 `_assert` 而非 pytest，限制了参数化、fixture、CI 集成和失败报告能力。
3. **多个代码路径未覆盖** — 特别是 `ready_with_conditions` 映射、`blocking_before_start` 逻辑、文件不存在/合约名不匹配等错误路径。

### 建议新增测试清单

| 优先级 | 测试名称 | 覆盖目标 | 对应发现项 |
|--------|----------|----------|------------|
| **P0** | `test_json_schema_validation` | 编译输出通过 `ship_package.schema.json` 校验 | C-01, Q-01 |
| **P1** | `test_file_not_found` | 文件不存在时抛出 `FileNotFoundError` | C-02 |
| **P1** | `test_contract_name_mismatch` | 合约名不匹配时抛出 `ValueError` | C-03 |
| **P1** | `test_conditional_readiness` | `ready_with_conditions` → `conditional_ship` 映射 | C-04 |
| **P1** | `test_blocking_p0_missing` | P0 需求 missing 时生成 `blocking_before_start` | C-05 |
| **P1** | `test_blocking_critical_gap` | critical gap 未解决时生成 `blocking_before_start` | C-06 |
| **P2** | `test_empty_requirements` | 零需求时 WP 的 requirements 为空列表 | — |
| **P2** | `test_module_no_summary` | 模块无 summary 时 AC fallback 到"单元测试全部通过" | — |
| **P2** | `test_markdown_output` | Markdown 输出包含所有必要 section | C-07 |
| **P2** | `test_large_module_count` | 10+ 模块的 phase 分配和需求分布 | C-08 |
| **P2** | `test_technology_choices` | technology_choices 传递到 harmony_brief.constraints | — |
| **P2** | `test_needs_clarification_readiness` | `needs_clarification` → `conditional_ship` 映射 | — |
| **P2** | `test_schema_invalid_output` | 构造不合规输出验证 schema 能检测（schema 本身的测试） | — |

### 建议改进方向

1. **迁移到 pytest** — 获得 fixture、parametrize、mark、详细报告能力
2. **添加 jsonschema 依赖** — 在测试中 `import jsonschema` 做输出校验
3. **创建 conftest.py** — 共享 `_make_base_bp`、temp dir fixture、schema path
4. **添加 CI pipeline** — 确保每次提交自动运行测试
5. **Golden sample 固化** — 将 golden sample 的 frozen_blueprint 复制到 tests/fixtures/ 避免外部依赖
