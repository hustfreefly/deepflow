# Ship Compiler v0.1.1 代码质量审计报告

> **审计对象**: `domains/ship_pro/ship_compiler.py` (v0.1.1)
> **测试文件**: `domains/ship_pro/tests/test_ship_compiler.py`
> **审计日期**: 2026-07-19
> **测试结果**: 47/47 passed ✅

---

## 1. 逻辑正确性 🟡 Yellow

### 发现项

| # | 严重度 | 位置 | 问题描述 | 影响 | 修复建议 |
|---|--------|------|----------|------|----------|
| L-1 | **P1** | `_assign_requirements` L213-226 | **需求匹配阈值硬编码为 2**：`best_score >= 2` 要求至少 2 个关键词重叠。当 WP title 为单字词（如 "引擎"）时，几乎不可能匹配到任何需求，导致所有需求走 round-robin 分配，功能匹配形同虚设。 | 需求分配质量下降，单字模块名的 WP 永远得不到精准匹配 | 阈值改为 `max(1, min(len(mod_name.split()) // 2, 2))` 或按 WP 关键词数动态调整 |
| L-2 | **P1** | `_decompose_work_packages` L261-264 | **forbidden_changes 无条件复制到所有 WP**：每个 WP 的 constraints 都包含全部 forbidden_changes，不论该 WP 是否涉及相关模块。10 条 forbidden × 20 个 WP = 每个 WP 携带 10 条无关约束。 | WP constraints 信噪比极低，下游执行者无法区分真正相关的约束 | 应按 module name/summary 与 forbidden 内容的语义关联度过滤，或仅在 WP 与 forbidden 涉及的模块重叠时添加 |
| L-3 | **P2** | `_compute_phase_map` L166-170 | **全同 tier + 模块数 ≤ tier_count 时不 fallback**：当 3 个模块全部 tier=T1 且 tier_count=3 时，`len(unique_phases) <= 1` 为 true 但 `len(modules) > tier_count` 为 false（3 > 3 = false），不触发 fallback。所有 WP 堆积在 phase_1。 | 极端场景下 phase 分配不合理，但实际影响有限（3 模块 3 phase 本身也合理） | 条件改为 `len(modules) > 1` 或增加额外判断：当所有模块 tier 相同时强制 position-based |
| L-4 | **P2** | `_generate_acceptance_contract` L296-303 | **仅取第一个关联需求的优先级**：遍历 `wp["requirements"]` 取第一个在 `requirements` dict 中存在的 req_id 的 priority。如果 WP 有 [P0-REQ, P2-REQ]，只取 P0；但如果顺序是 [P2-REQ, P0-REQ]，也只取 P2。 | AC 优先级可能不准确，取决于 requirements 列表顺序 | 取最高优先级：`priority = min(...)` 或按 P0 > P1 > P2 排序取最优 |
| L-5 | **P2** | `_position_phase` L183-189 | **不均匀分布**：5 modules / 3 tiers 分布为 [1, 2, 2]，phase_1 始终只有 1 个模块。数学上 `int((index-1)/chunk)+1` 的取整导致前端 phase 总是较少。 | Phase 间工作量可能不均衡，phase_1 偏少 | 改用 `round()` 或累积分配算法确保更均匀分布 |
| L-6 | **P2** | `_topo_sort` L72-84 | **DFS 递归深度无保护**：Python 默认递归限制 1000。超大项目（>500 modules 的线性链）可能触发 RecursionError。 | 极端大项目编译崩溃 | 改为迭代 DFS 或设置 `sys.setrecursionlimit`，或在函数入口检查 `len(packages) > 500` 时切换迭代实现 |

---

## 2. 错误处理 🟡 Yellow

### 发现项

| # | 严重度 | 位置 | 问题描述 | 影响 | 修复建议 |
|---|--------|------|----------|------|----------|
| E-1 | **P1** | `compile_ship_package` L371-412 | **无顶层异常保护**：如果 Step 3-6 中任何一步抛出未预期异常（如 KeyError、TypeError），已写入的 `ship_package.json` 不会被清理，留下半成品输出文件。 | 下游消费者可能读到不完整的 ship_package.json | 包装在 try/except 中：失败时清理已写入文件，或先计算全部结果再一次性写入 |
| E-2 | **P2** | `_write_json_atomic` / `_write_text_atomic` L338-356 | **tempfile.mkstemp 失败时 tmp_path 未定义**：如果 `tempfile.mkstemp` 本身抛出异常（如 parent 目录不存在），`except` 块中 `Path(tmp_path).unlink()` 会触发 `NameError`，掩盖原始错误。 | 真实错误信息被 NameError 覆盖，调试困难 | 在 try 之前初始化 `tmp_path = None`，except 中检查 `if tmp_path` |
| E-3 | **P2** | `_load_frozen_blueprint` L97-108 | **无文件大小限制**：恶意或损坏的超大 JSON 文件（如 10GB）会导致 `json.load` 消耗全部内存。 | 极端场景下 OOM | 添加文件大小检查：`if path.stat().st_size > 100 * 1024 * 1024: raise ValueError("File too large")` |
| E-4 | **P2** | `_check_readiness` L115-131 | **未知 readiness status 静默降级为 conditional_ship**：`status_map.get(fb_status, "conditional_ship")` 对拼写错误（如 "reday"）不报错，静默使用默认值。 | 上游错误被掩盖，可能导致不该 ship 的项目进入 ship 阶段 | 添加 warning log 或对未知 status 抛出 ValueError |
| E-5 | **P2** | `_decompose_work_packages` L248 | **module 缺少 "name" 键时使用 f"Module {i}"**：但如果 module 是空 dict `{}`，不会报错，静默生成无意义的 WP。 | 质量低劣的 architecture 输入产生无意义输出，无警告 | 添加 warning：`if not mod.get("name"): logger.warning(f"Module {i} missing name")` |

---

## 3. 确定性 🟡 Yellow

### 发现项

| # | 严重度 | 位置 | 问题描述 | 影响 | 修复建议 |
|---|--------|------|----------|------|----------|
| D-1 | **P1** | `compile_ship_package` L387, L401 | **`generated_at` 时间戳破坏确定性**：`datetime.now(timezone.utc).isoformat()` 使每次运行的 `meta.generated_at` 不同。虽然测试已正确排除此字段，但任何直接比较完整 JSON 输出的工具都会误判为"不同"。 | 输出不是严格幂等的；diff 工具、缓存系统、增量构建都会受影响 | 使用固定占位符 `"GENERATED_AT_PLACEHOLDER"` 或从输入 frozen_blueprint 继承时间戳 |
| D-2 | **P2** | `_assign_requirements` L200-226 | **匹配依赖 dict 迭代顺序**：`for wp in packages` 遍历顺序决定 `best_match`（分数相同时取第一个）。Python 3.7+ dict 保序，所以实际确定性没问题，但逻辑上依赖插入顺序。 | 理论风险：如果 packages 顺序变化，匹配结果可能不同 | 当前可接受；如需更强保证，可在匹配分数相同时按 WP id 排序取最小 |
| D-3 | — | 整体 | **纯函数性（除时间戳外）良好**：无 `random`、无 `set` 迭代（dict 保序）、无外部 IO（除文件读写）。`_topo_sort` 的 DFS 遍历顺序由 packages 列表顺序决定，是确定的。 | ✅ 正面发现 | 无需修改 |

---

## 4. 边界处理 🟢 Green

### 发现项

| # | 严重度 | 位置 | 问题描述 | 影响 | 修复建议 |
|---|--------|------|----------|------|----------|
| B-1 | **P2** | `_generate_markdown` L323-329 | **Markdown 表格未转义 `|` 字符**：AC criteria 文本中如果包含 `|`，会破坏 Markdown 表格结构。 | 生成的 .md 文件表格渲染错乱 | 对 criteria 文本做 `text.replace("|", "\\|")` |
| B-2 | **P2** | `_decompose_work_packages` L242 | **module id 重复时无去重**：两个 module 都 `{"id": "mod_a"}` 会生成两个不同 WP（WP-001, WP-002），但 `phase_map` 中后一个覆盖前一个，且 `source_ref` 相同。 | phase 分配可能错误，source_ref 不唯一 | 检测重复 id 并添加后缀或报错 |
| B-3 | — | `_safe_get` L44-51 | **✅ 正确处理 None 值、嵌套非 dict、空路径**：`_safe_get(d, default='x')` 返回 `d`（如果 d 不是 None）。行为一致。 | ✅ 正面发现 | 无需修改 |
| B-4 | — | `_check_readiness` L127 | **✅ 空 conditions 列表正确处理**：`fb_conditions = []` 时 `inherited = []`。 | ✅ 正面发现 | 无需修改 |
| B-5 | — | `_decompose_work_packages` L280-293 | **✅ 空模块 catch-all WP 设计合理**：包含所有 requirements，使用 intent.project_name 作为 title。 | ✅ 正面发现 | 无需修改 |
| B-6 | — | `_position_phase` L184 | **✅ total=0 保护**：`if total <= 0: return "phase_1"`。 | ✅ 正面发现 | 无需修改 |

---

## 5. 代码风格 🟢 Green

### 发现项

| # | 严重度 | 位置 | 问题描述 | 影响 | 修复建议 |
|---|--------|------|----------|------|----------|
| S-1 | **P2** | `_decompose_work_packages` L232-293 | **函数过长（62 行）**：包含 phase 查询、WP 构建、依赖计算、约束过滤、需求分配等多个逻辑块。 | 可读性降低，难以单独测试各子步骤 | 拆分为 `_build_wp_from_module(mod, phase_map, bp, i)` 和 `_compute_wp_dependencies(phase_num, packages)` |
| S-2 | **P2** | `compile_ship_package` L371-420 | **重复的 meta 构建代码**：blocked 路径（L381-398）和正常路径（L399-411）有几乎相同的 meta dict 构建逻辑。 | 违反 DRY，修改 meta 结构需改两处 | 提取 `_build_meta(bp)` 函数 |
| S-3 | **P2** | `compile_ship_package` L373 | **冗余 import**：`import os` 在文件顶部已导入（L13），函数内再次 `import os` 是冗余的。 | 代码噪音，不影响功能 | 删除函数内的 `import os` |
| S-4 | — | 整体 | **✅ 命名规范一致**：函数名 `_snake_case`、常量 `_UPPER_CASE`、类名无（不需要）。 | ✅ 正面发现 | — |
| S-5 | — | 整体 | **✅ 文档字符串完整**：每个函数都有清晰的 docstring，模块级 docstring 包含用法示例和契约引用。 | ✅ 正面发现 | — |
| S-6 | — | 整体 | **✅ 函数拆分合理**：7 个 Step 函数各司其职，职责清晰。Helper 函数（`_safe_get`, `_topo_sort`, `_position_phase`）复用性好。 | ✅ 正面发现 | — |
| S-7 | — | 整体 | **✅ 注释质量高**：关键决策点都有中文注释解释 why（如 "全自动化，不设人工审核"），不是简单复述代码。 | ✅ 正面发现 | — |

---

## 6. 测试覆盖 🟡 Yellow

### 发现项

| # | 严重度 | 位置 | 问题描述 | 影响 | 修复建议 |
|---|--------|------|----------|------|----------|
| T-1 | **P1** | 测试文件 | **缺少 `_safe_get` 单元测试**：作为核心 helper（被调用 30+ 次），无单独测试覆盖边界情况：深层嵌套路径、中间值为 None、key 不存在、default 覆盖 None 值。 | `_safe_get` 回归风险无测试保护 | 添加 `test_safe_get_nested`, `test_safe_get_none_intermediate`, `test_safe_get_default_keyword` |
| T-2 | **P1** | 测试文件 | **缺少 `_generate_markdown` 测试**：Markdown 输出格式无任何验证。表格结构、章节完整性、特殊字符处理均未测试。 | 生成的 .md 文件质量无保障 | 添加 `test_markdown_sections_complete`, `test_markdown_table_formatting` |
| T-3 | **P1** | 测试文件 | **缺少 `_topo_sort` 正常路径测试**：仅测试了环检测，未测试正常 DAG 排序结果的正确性（如 A→B→C 应返回 [C, B, A]）。 | 拓扑排序逻辑错误可能不被发现 | 添加 `test_topo_sort_linear_chain`, `test_topo_sort_diamond`, `test_topo_sort_disconnected` |
| T-4 | **P2** | 测试文件 | **缺少 `_assign_requirements` 边界测试**：未测试 round-robin 溢出（需求数 >> WP 数）、单个需求分配到空 WP、所有需求都匹配同一个 WP 的场景。 | 需求分配极端场景无保护 | 添加 `test_requirements_more_reqs_than_wps`, `test_requirements_all_match_one_wp` |
| T-5 | **P2** | 测试文件 | **缺少 `_position_phase` 参数化测试**：未测试 (total=1, tier=3), (total=2, tier=3), (total=7, tier=4) 等边界组合的分布结果。 | Phase 分布算法回归风险 | 添加参数化测试覆盖 (total, tier_count) 组合矩阵 |
| T-6 | **P2** | 测试文件 | **缺少集成测试：大输入规模**：未测试 50+ modules、100+ requirements 的性能和正确性。 | 大规模输入可能有性能或逻辑问题 | 添加 `test_large_blueprint` (100 modules, 200 requirements) |
| T-7 | — | 测试文件 | **✅ 测试覆盖关键业务路径**：golden sample、blocked readiness、forbidden 传递、determinism、schema 校验等核心场景均有测试。 | — | — |
| T-8 | — | 测试文件 | **✅ 测试设计模式良好**：每个测试独立 tempdir + cleanup，`_make_base_bp` factory 减少重复，assert 信息包含实际值便于调试。 | — | — |

---

## 总结

### 各维度状态

| 维度 | 状态 | P0 | P1 | P2 |
|------|------|----|----|-----|
| 1. 逻辑正确性 | 🟡 Yellow | 0 | 2 | 4 |
| 2. 错误处理 | 🟡 Yellow | 0 | 1 | 4 |
| 3. 确定性 | 🟡 Yellow | 0 | 1 | 1 |
| 4. 边界处理 | 🟢 Green | 0 | 0 | 2 |
| 5. 代码风格 | 🟢 Green | 0 | 0 | 3 |
| 6. 测试覆盖 | 🟡 Yellow | 0 | 3 | 3 |
| **合计** | | **0** | **7** | **17** |

### 总评

**Ship Compiler v0.1.1 整体代码质量为中上水平。** 无 P0 阻断性问题，核心编译管线（load → readiness → decompose → acceptance → risk → harmony → write）逻辑清晰，47 个测试全部通过。

**主要优势：**
- 原子写入机制（temp + rename）保证文件写入安全
- `_safe_get` 统一处理嵌套字典访问，防御性编程到位
- 拓扑排序 + 环检测保证依赖图正确性
- 确定性（除时间戳外）经验证通过
- 测试覆盖了核心业务场景（golden sample、blocked、forbidden、determinism）

**需要优先修复的 3 个问题：**
1. **D-1** (P1): `generated_at` 时间戳破坏输出确定性 → 使用固定值或从输入继承
2. **L-1** (P1): 需求匹配阈值硬编码为 2，单字模块名永远无法匹配 → 动态阈值
3. **T-1/T-2/T-3** (P1): `_safe_get`、`_generate_markdown`、`_topo_sort` 正常路径缺少单元测试

**建议修复优先级：**
- 🔴 立即修复：D-1（确定性）
- 🟡 本迭代修复：L-1, L-2, E-1, E-2, T-1~T-3
- 🟢 下迭代修复：其余 P2 项
