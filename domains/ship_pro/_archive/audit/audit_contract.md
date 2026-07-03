# Ship Pro 契约合规审计报告

> **审计时间**: 2026-06-12
> **审计对象**: 智能简历生成系统 Ship Package
> **场景契约**: ship_pro_v0.1.yaml
> **编译器**: ship_compiler.py (v0.1.0)
> **产出**: ship_package.json + ship_package.md

---

## 一、红线检查（8 条）

### RED-SHIP-001: Ship Pro 只消费 frozen_blueprint.json，禁止读取 Solution Pro 内部文件

- **状态**: 🟢 green
- **证据**: `grep -rnE 'final_result|frozen_spec|harness_final|control_contract|stages/' ship_compiler.py` → exit code 1，无匹配
- **说明**: 编译器仅通过 `_load_frozen_blueprint()` 读取 frozen_blueprint.json，未引用任何 Solution Pro 内部文件

---

### RED-SHIP-002: readiness.status 为 blocked 时，禁止生成 Ship Package

- **状态**: 🟢 green
- **证据**:
  - 编译器 `_check_readiness()` (L98-115) 检查 `fb_status == "blocked"` 时直接返回 blocked 状态
  - `compile_ship_package()` (L282-298) 在 readiness=="blocked" 时写入空 Ship Package 并提前 return，不执行拆解
  - 实际产出 `readiness.status = "ready_to_ship"`（frozen blueprint 为 ready_for_ship），非 blocked
- **说明**: 编译器有 blocked 守卫逻辑，且本次执行路径正确

---

### RED-SHIP-003: Ship Package 必须通过 JSON Schema 校验才能标记为 valid

- **状态**: 🟢 green
- **证据**: `python3 -m jsonschema` 验证结果 → **"VALID: Schema validation passed"**
- **说明**: ship_package.json 完全符合 ship_package.schema.json 定义，包括所有 required 字段、类型约束、enum 值和 pattern 匹配

---

### RED-SHIP-004: Ship Pro 禁止重新定义需求或重新做架构设计

- **状态**: 🟢 green
- **证据**: `grep -rnE 'redefine.*req|redesign.*arch|create.*architecture' ship_compiler.py` → exit code 1，无匹配
- **说明**: 编译器仅做工程拆解（`_decompose_work_packages` 按 architecture.modules 1:1 生成 WP），不包含任何需求/架构重设计逻辑

---

### RED-SHIP-005: Ship Pro 禁止直接调用 Codex 或生成 Codex 会话命令

- **状态**: 🟢 green
- **证据**: `grep -rnE 'codex|sessions_spawn.*codex|agent_task' ship_compiler.py` → exit code 1，无匹配
- **说明**: 编译器是纯数据转换脚本，无任何 Codex/Agent 调度逻辑

---

### RED-SHIP-006: not_verified 需求不能标记为 ready_to_ship

- **状态**: 🟢 green
- **证据**:
  - Frozen blueprint 中 6 个需求全部为 `coverage_status: "covered"`，无 not_verified 需求
  - 编译器 (L213-217) 对 `coverage == "not_verified"` 的需求自动设置 `human_review_required = True`
  - 实际产出中所有 WP 的 `human_review_required = false`，与输入数据一致
- **说明**: 本次无 not_verified 需求，规则不适用但编译器已内置守卫逻辑

---

### RED-SHIP-007: forbidden_changes 必须完整传递到 risk_contract 和 harmony_brief

- **状态**: 🟢 green
- **证据**:
  - Frozen blueprint `risks.forbidden_changes = []`（0 条）
  - Ship package `risk_contract.forbidden_actions = []`
  - Ship package `harmony_brief.forbidden_actions = []`
  - 编译器 (L253) `[str(f) for f in forbidden]` 直接透传
- **说明**: 上游无 forbidden_changes，下游正确传递为空数组。∅ ⊆ ∅ 成立

---

### RED-SHIP-008: Ship Pro 编译器必须是确定性脚本，禁止 LLM 推理

- **状态**: 🟢 green
- **证据**: `grep -rnE 'openai|anthropic|llm|chat_completion|sessions_spawn' ship_compiler.py` → exit code 1，无匹配
- **说明**: 编译器仅使用 `json`, `sys`, `datetime`, `pathlib`, `typing`, `re` 标准库，纯确定性逻辑

---

## 二、P0 质量门禁（6 条）

### P0-1: ship_package.json 必须通过 ship_package.schema.json 校验

- **状态**: 🟢 green
- **证据**: jsonschema.validate() → "VALID: Schema validation passed"

---

### P0-2: readiness.status 为 blocked 时禁止生成 Ship Package

- **状态**: 🟢 green
- **证据**: 同 RED-SHIP-002，readiness = "ready_to_ship"，编译器有 blocked 守卫

---

### P0-3: 每个 P0 requirement 必须被至少一个 work package 覆盖

- **状态**: 🟢 green
- **证据**:
  - P0 需求: REQ-001（priority=P0）
  - REQ-001 被分配到 WP-001（requirements: ["REQ-001"]）
  - 覆盖率: 1/1 = 100%

---

### P0-4: forbidden_changes 必须完整传递到 risk_contract.forbidden_actions

- **状态**: 🟢 green
- **证据**: 同 RED-SHIP-007，∅ → ∅ 完整传递

---

### P0-5: not_verified requirement 对应的 WP 必须标记 human_review_required=true

- **状态**: 🟢 green
- **证据**: 无 not_verified 需求，规则 vacuously true。编译器有守卫逻辑 (L213-217)

---

### P0-6: work package 依赖关系必须形成 DAG（无环）

- **状态**: 🟢 green
- **证据**:
  - Kahn 算法验证: 8 节点全部进入拓扑序，`len(order) == len(wps)` → True
  - 依赖结构: phase_1 (WP-001/002/003) → phase_2 (WP-004/005/006) → phase_3 (WP-007/008)
  - 无环，DAG 成立

---

## 三、P1 质量门禁（4 条）

### P1-1: ship_package.md 必须与 .json 同步生成

- **状态**: 🟢 green
- **证据**: `ship_package.md` 文件存在，由 `_generate_markdown()` (L299-355) 在同一 `compile_ship_package()` 调用中生成

---

### P1-2: 每个 work package 必须有至少一条 acceptance criteria

- **状态**: 🟢 green
- **证据**:
  - WP-001: 1 AC | WP-002: 1 AC | WP-003: 1 AC | WP-004: 1 AC
  - WP-005: 5 ACs | WP-006: 1 AC | WP-007: 1 AC | WP-008: 1 AC
  - 所有 8 个 WP 均 ≥ 1 条 AC

---

### P1-3: acceptance_contract 中 P0 条目必须有 verification_method

- **状态**: 🟢 green
- **证据**: AC-001 (priority=P0) → verification_method = "automated_test" ✓

---

### P1-4: harmony_brief.package_order 必须与 work_packages 依赖关系一致

- **状态**: 🟢 green
- **证据**:
  - package_order = [WP-001, WP-002, WP-003, WP-004, WP-005, WP-006, WP-007, WP-008]
  - 与 `_topo_sort()` 输出完全一致
  - WP 集合与 package_order 集合完全匹配
- **备注**: 拓扑序在同 phase 内不唯一（WP-001/002/003 可互换），当前顺序为 DFS 自然序，合规但不影响正确性

---

## 四、附加发现（非红线/非门禁，数据质量观察）

| # | 严重度 | 问题 | 说明 |
|---|--------|------|------|
| 1 | ⚠️ 低 | `meta.source_blueprint = "None vNone"` | frozen_blueprint 的 meta 字段可能缺少 contract_name/contract_version，编译器 `_safe_get` 返回 None 后拼接为字符串 "None vNone"。不影响 schema 校验但降低可追溯性 |
| 2 | ⚠️ 低 | 所有 WP 的 `constraints = []` | frozen_blueprint 的 `architecture.module_boundaries = []`，导致无约束传递。可能是上游 blueprint 未填充此字段 |
| 3 | ⚠️ 低 | 所有 WP 的 `acceptance_criteria` 文本相同 | 编译器将全部 verification.acceptance_criteria 复制到每个 WP，未按需求-WP 关联过滤 |
| 4 | ⚠️ 低 | 需求分配不均 | WP-005 获得 5 个需求，WP-002/003/004/006/007/008 获得 0 个。分配启发式过于粗糙 |

---

## 五、审计总结

| 类别 | 🟢 green | 🟡 yellow | 🔴 red |
|------|----------|-----------|--------|
| 红线 (8条) | **8** | 0 | 0 |
| P0 门禁 (6条) | **6** | 0 | 0 |
| P1 门禁 (4条) | **4** | 0 | 0 |
| **合计 (18条)** | **18** | **0** | **0** |

### 结论: ✅ 全部通过

Ship Pro 编译器和本次产出 **完全符合** ship_pro_v0.1.yaml 场景契约的全部 8 条红线和 10 条质量门禁。

4 项附加数据质量观察（非违规）建议后续优化，不影响合规判定。

---

*审计员: Ship Pro Contract Auditor*
*审计方法: 静态代码分析 + grep 规则验证 + JSON Schema 校验 + 数据流追溯*
