# Ship Compiler 代码质量审计报告

> **审计日期**: 2026-06-13
> **审计范围**: `domains/ship_pro/ship_compiler.py` + `tests/test_ship_compiler.py`
> **契约**: `cage/active/ship_pro_v0.1.yaml`
> **测试运行**: 19/19 passed ✅

---

## 总结

| 维度 | 状态 | 发现数 |
|------|------|--------|
| 1. 逻辑正确性 | 🟡 yellow | 4 |
| 2. 边界处理 | 🟡 yellow | 3 |
| 3. 错误处理 | 🔴 red | 4 |
| 4. 确定性 | 🟡 yellow | 2 |
| 5. 代码风格 | 🟡 yellow | 3 |
| 6. 测试覆盖 | 🔴 red | 6 |

**总计: 2 green, 3 yellow, 2 red** (无维度获 green，需关注)

---

## 1. 逻辑正确性 — 🟡 yellow

### 1.1 🔴 需求分配启发式过于粗糙，存在静默丢失风险

**位置**: `_decompose_work_packages()` L218-237

```python
if group in ("Core", "Functional") and wp_idx < len(packages) // 2 + 1:
    wp["requirements"].append(req_id)
    assigned = True
    break
elif group in ("NonFunctional",) and wp_idx >= len(packages) // 2:
    ...
```

**问题**:
- 需求只按 `group` 字符串匹配分配到"前半"或"后半" WP。如果 Core 需求在遍历到后半 WP 时才首次匹配（前半没有匹配到），会被 catch-all 塞进最后一个 WP，而非其逻辑相关的 WP。
- `group` 值不在 `("Core", "Functional", "NonFunctional")` 中的需求（如 `"Security"`, `"Performance"`）全部走 catch-all → 最后一个 WP。
- 没有基于 `req.related_modules` 或 `req.group` 与 WP 的 `related_modules` 做精确匹配。

**影响**: 需求可能被分配到不相关的 WP，导致验收契约错位。

**建议修复**: 优先按 `req.group` / `req.related_modules` 与 WP 的 `related_modules` 精确匹配；无匹配时再 fallback 到 position-based；最后才 catch-all。

---

### 1.2 🟡 依赖关系只连接相邻 phase，可能遗漏跨 phase 依赖

**位置**: `_decompose_work_packages()` L196-203

```python
if phase_num > 1:
    for prev_wp in packages:
        prev_phase_num = int(prev_wp["phase"].replace("phase_", "")) ...
        if prev_phase_num == phase_num - 1:
            dependencies.append(prev_wp["id"])
```

**问题**: 每个 WP 只依赖"前一个 phase"的 WP。如果存在 phase_1 → phase_3 的直接逻辑依赖（跳过 phase_2），编译器不会生成这条边。虽然拓扑排序仍能工作，但生成的 DAG 可能过于宽松。

**影响**: Harmony/Hermes 可能并行执行实际有依赖关系的 WP。

**建议修复**: 在 frozen_blueprint 的 `architecture.modules` 提供依赖信息时，优先使用模块级依赖；当前 heuristic 作为 fallback 可接受，但应在输出中标注 "heuristic dependencies"。

---

### 1.3 🟡 `_topo_sort` 静默忽略不在 id_set 中的依赖

**位置**: `_topo_sort()` L56

```python
adj = {p["id"]: [d for d in p.get("dependencies", []) if d in id_set] for p in packages}
```

**问题**: 如果 WP 依赖一个不存在的 WP-ID，该依赖被静默丢弃。契约要求 "work package 之间的依赖关系必须形成 DAG"，但悬空依赖不算违规也不算正确——它被忽略了。

**建议修复**: 对不在 `id_set` 中的依赖发出 warning（或记录到 risk_contract.known_gaps）。

---

### 1.4 🟡 `_generate_acceptance_contract` AC-REQ 匹配逻辑脆弱

**位置**: `_generate_acceptance_contract()` L268-272

```python
ac_id_str = ac.get("id", "")
...
if ac_id_str in wp.get("requirements", []):
```

**问题**: 将 `acceptance_criteria.id`（如 `"AC-001"` 或 `"REQ-001"`）与 WP 的 `requirements` 列表（包含 `"REQ-xxx"`）做交叉匹配。如果 AC 的 `id` 不以 `REQ-` 开头，永远不会匹配，所有 AC 都走 fallback（每个 WP 取第一个 AC 文本）。

**影响**: 验收标准可能与实际需求脱节。

**建议修复**: 匹配应基于 `ac.related_req_id` 或 `ac.req_id` 字段（如果存在），而非 `ac.id`。

---

## 2. 边界处理 — 🟡 yellow

### 2.1 🟡 `_safe_get` 将 `None` 值等同于缺失键

**位置**: `_safe_get()` L34-39

```python
current = current.get(key, default)
...
return current if current is not None else default
```

**问题**: 如果 JSON 中显式设置了 `"status": null`，`_safe_get` 返回 `default` 而非 `None`。这在 readiness 检查中可能导致意外行为（`null` status 被当作缺失而非显式空值）。

**建议修复**: 区分 `key not in dict` 和 `value is None`。

---

### 2.2 🟡 `_position_phase` 理论上的除零风险

**位置**: `_position_phase()` L176

```python
chunk = total / tier_count
```

**问题**: `total=0` 会导致除零。虽然当前调用方 `_compute_phase_map` 在 `not modules` 时提前返回，但函数本身缺乏防护。

**建议修复**: 添加 `if total <= 0: return "phase_1"` 防御。

---

### 2.3 🟡 重复 module ID 导致 phase_map 静默覆盖

**位置**: `_compute_phase_map()` L153-155

```python
tier_phases[mod_id] = ...
tier_phases[i] = ...
```

**问题**: 如果两个 module 有相同的 `id`，后者覆盖前者的 phase 映射。没有检测或报错。

**建议修复**: 检测重复 ID 并报错，或使用 `(mod_id, index)` 复合键。

---

## 3. 错误处理 — 🔴 red

### 3.1 🔴 JSON 解析无错误处理

**位置**: `_load_frozen_blueprint()` L72-73

```python
with path.open("r", encoding="utf-8") as f:
    bp = json.load(f)
```

**问题**: 如果文件内容不是合法 JSON，抛出 `json.JSONDecodeError` 无上下文信息（哪个文件、哪个位置出错）。

**建议修复**:
```python
try:
    bp = json.load(f)
except json.JSONDecodeError as e:
    raise ValueError(f"Invalid JSON in {path}: {e}") from e
```

---

### 3.2 🔴 输出文件写入无错误处理

**位置**: `compile_ship_package()` L350-356

```python
with json_path.open("w", encoding="utf-8") as f:
    json.dump(ship_package, f, ensure_ascii=False, indent=2)
md_content = _generate_markdown(ship_package)
with md_path.open("w", encoding="utf-8") as f:
    f.write(md_content)
```

**问题**: 磁盘满、权限不足等错误会抛出未捕获的异常。JSON 写入成功但 MD 写入失败时，会产生不一致状态（.json 已更新但 .md 是旧的）。

**建议修复**: 先写入临时文件，再原子 rename；或捕获异常并清理部分写入。

---

### 3.3 🔴 `_load_frozen_blueprint` 缺少 schema 级校验

**位置**: `_load_frozen_blueprint()` L66-80

**问题**: 只验证了 `contract_name`，未验证 frozen_blueprint 的必要字段（`readiness`, `architecture`, `requirements`, `risks`, `verification`）。如果输入是一个合法 JSON 但结构不完整的文件，后续步骤会以不可预测的方式失败（`_safe_get` 返回空默认值，静默生成空的 Ship Package）。

**契约违规**: `ship_pro_v0.1.yaml` Step 2 明确要求 "校验 frozen_blueprint schema"。

**建议修复**: 添加必要字段存在性检查，缺失时抛出明确错误。

---

### 3.4 🟡 CLI 入口使用 `raise SystemExit(2)` 而非 `sys.exit(2)`

**位置**: `__main__` L371

**问题**: 功能等价但不符合惯例。`raise SystemExit` 是 `sys.exit` 的底层实现，直接使用 `sys.exit` 更清晰。

**建议修复**: `sys.exit(2)`.

---

## 4. 确定性 — 🟡 yellow

### 4.1 🟡 `generated_at` 时间戳导致输出不可复现

**位置**: `compile_ship_package()` L311, L337

```python
"generated_at": datetime.now(timezone.utc).isoformat(),
```

**问题**: 契约红线 RED-SHIP-008 要求 "Ship Pro 编译器必须是确定性脚本"。时间戳使每次运行的 `meta.generated_at` 不同，导致 JSON 输出不同。

**建议修复**: 从 frozen_blueprint.meta 中提取 `frozen_at` 时间戳作为 `generated_at`，或接受 meta 字段为非确定性（仅影响元数据，不影响 work packages 内容）。后者需在契约中明确豁免。

---

### 4.2 🟡 `_generate_risk_contract` 修改传入的 `human_points` 列表

**位置**: `_generate_risk_contract()` L299

```python
for wp in work_packages:
    if wp.get("human_review_required"):
        human_points.append(...)
```

**问题**: `human_points` 是从 `_safe_get(bp, "risks", "human_confirmation_points", default=[])` 获取的引用。如果是列表，`.append()` 会修改原始 bp dict 中的数据。虽然后续有 `list(dict.fromkeys(human_points))` 做 dedup，但原始数据已被污染。

**建议修复**: 先 `human_points = list(human_points)` 复制后再 append。

---

## 5. 代码风格 — 🟡 yellow

### 5.1 🟡 `import re` 在函数内部循环中

**位置**: `_compute_phase_map()` L155

```python
import re
match = re.search(r'[Tt]?(\d+)', tier_str)
```

**问题**: `import re` 在 for 循环内部执行。虽然 Python 的 import 缓存使其不会重复加载，但将 import 放在函数/循环内部违反 PEP 8 和项目惯例。

**建议修复**: 移到文件顶部 import 区域。

---

### 5.2 🟡 `phase_num` 反复从字符串解析

**位置**: 多处

```python
phase_num = int(phase.replace("phase_", "")) if "phase_" in phase else 1
```

**问题**: 同一 phase 字符串被多次解析为 int（在 WP 创建时、在依赖计算时）。应存储为结构化数据（dict with `phase_num` int + `phase` string），或至少提取为 helper。

**建议修复**: 在 WP 结构中增加 `_phase_num` 内部字段（生成 JSON 时排除），或使用 helper `_phase_to_num(phase: str) -> int`。

---

### 5.3 🟡 `_decompose_work_packages` 函数过长（~80 行）

**位置**: L186-280

**问题**: 该函数承担了 phase 分配、依赖生成、deliverables 生成、需求分配、complexity 启发式等多项职责。违反单一职责原则。

**建议修复**: 拆分为 `_assign_requirements()`, `_compute_wp_dependencies()`, `_estimate_complexity()` 等子函数。

---

## 6. 测试覆盖 — 🔴 red

### 现有测试 (5 个，19 断言)

| 测试 | 覆盖内容 |
|------|----------|
| `test_cycle_detection` | 环依赖检测 ✅ |
| `test_empty_modules` | 空模块 catch-all ✅ |
| `test_blocked_readiness` | blocked 状态 ✅ |
| `test_all_same_tier` | tier fallback ✅ |
| `test_golden_sample` | 端到端 golden path ✅ |

### 缺失测试 (关键路径)

| # | 缺失场景 | 优先级 | 对应契约条目 |
|---|----------|--------|-------------|
| 1 | **forbidden_changes 完整传递** — 验证 `risk_contract.forbidden_actions` == `bp.risks.forbidden_changes` | P0 | RED-SHIP-007, L3 data |
| 2 | **not_verified → human_review_required** — coverage_status=not_verified 的 req 对应 WP 必须 `human_review_required=true` | P0 | RED-SHIP-006, L2 behavior |
| 3 | **P0 missing → blocking_before_start** — P0 需求 missing 时生成 blocking 风险 | P0 | L2 generate_risk_contract |
| 4 | **readiness 状态映射** — ready_with_conditions → conditional_ship, needs_clarification → conditional_ship | P1 | L3 data.readiness |
| 5 | **acceptance contract 生成** — 每个 WP 至少一条 AC，P0 req 的 AC 优先级为 P0 | P1 | L2 generate_acceptance_contract |
| 6 | **harmony_brief.package_order 与 WP 依赖一致** — 拓扑排序结果与 WP 依赖图匹配 | P1 | L2 generate_harmony_brief |

### 缺失测试 (边界条件)

| # | 缺失场景 | 优先级 |
|---|----------|--------|
| 7 | 文件不存在 → FileNotFoundError | P1 |
| 8 | 非法 JSON → 有意义的错误信息 | P1 |
| 9 | frozen_blueprint 缺少必要字段（如无 architecture）→ 行为 | P1 |
| 10 | 重复 module ID → 检测或合理处理 | P2 |
| 11 | 确定性验证 — 相同输入两次运行，work_packages 完全一致 | P1 (RED-SHIP-008) |

---

## 修复优先级建议

### P0 — 必须修复（契约红线相关）

1. **需求分配逻辑改进** (#1.1) — 当前启发式太粗糙，可能导致需求-WP 错位
2. **forbidden_changes 传递测试** (测试 #1) — 契约 RED-SHIP-007 明确要求
3. **not_verified → human_review 测试** (测试 #2) — 契约 RED-SHIP-006 明确要求
4. **schema 级校验** (#3.3) — 契约 Step 2 明确要求但编译器未实现

### P1 — 应修复

5. JSON 解析错误处理 (#3.1)
6. 输出写入原子性 (#3.2)
7. AC-REQ 匹配逻辑 (#1.4)
8. 确定性：时间戳处理 (#4.1)
9. 补充缺失测试 (#6)

### P2 — 建议改进

10. `import re` 位置 (#5.1)
11. phase_num 解析复用 (#5.2)
12. 函数拆分 (#5.3)
13. 悬空依赖 warning (#1.3)

---

*审计完成。2 green, 3 yellow, 2 red。主要风险在错误处理不足和测试覆盖缺失。*
