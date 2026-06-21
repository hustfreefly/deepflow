# Ship Pro 产出质量审计报告

> **审计对象**: `blackboard/智能简历生成系统_architecture_d99f733a/ship_package.json` + `.md`
> **Schema**: `domains/ship_pro/schemas/ship_package.schema.json`
> **审计时间**: 2026-06-13
> **审计工具**: jsonschema (Python) + 人工逐字段审查

---

## 1. Schema 校验

**状态**: 🟢 GREEN

**方法**: `jsonschema.validate(pkg, schema)` — Draft-07 完整验证

**发现项**:
- ✅ JSON Schema Draft-07 验证通过，无错误
- ✅ `additionalProperties: false` 约束满足（无多余字段）
- ✅ 所有 const/enum/pattern 约束均符合（`WP-\d{3}`, `AC-\d{3}`, `REQ-\d{3}` 等）
- ✅ 顶层 6 个 required 字段全部存在：`meta`, `readiness`, `work_packages`, `acceptance_contract`, `risk_contract`, `harmony_brief`

**严重度**: 无

---

## 2. 字段完整性

**状态**: 🟡 YELLOW

**发现项**:

| # | 字段路径 | 问题 | 严重度 |
|---|---------|------|--------|
| 2.1 | `work_packages[*].constraints` | **全部 8 个 WP 的 constraints 为空数组** `[]`。Schema 允许空数组（无 `minItems`），但语义上每个 WP 至少应有技术约束（如依赖库版本、性能限制、兼容性要求）。 | **P1** |
| 2.2 | `work_packages[6-7].requirements` | WP-007（保真度自检器）和 WP-008（半导体封装行业知识库）的 requirements 为空数组。Schema 不要求 minItems，但这两个组件在 frozen_blueprint 中有对应的功能描述，应有内部需求映射。 | **P2** |
| 2.3 | `acceptance_contract[6-7].req_id` | AC-007 和 AC-008 的 `req_id` 为空字符串 `""`。Schema 中 `req_id` 非 required，但 AC-001~AC-006 都有 REQ 映射，这里不一致。 | **P2** |
| 2.4 | `risk_contract.known_gaps` | 空数组。Harness 审计通常会产出 known_gaps，此处全部清空可能表示信息丢失。 | **P2** |
| 2.5 | `risk_contract.forbidden_actions` | 空数组。对于包含 LLM 调用的系统，应有 "禁止伪造量化指标" 等约束。 | **P2** |
| 2.6 | `risk_contract.human_review_points` | 空数组。与所有 WP 的 `human_review_required: false` 一致，但内容优化器（WP-003）的 acceptance_criteria 明确写了 "LLM Rewriter需用户显式确认"，存在语义矛盾。 | **P1** |
| 2.7 | `harmony_brief.constraints` | 空数组。项目有明确的性能约束（<5秒/<30秒），应在此处汇总。 | **P2** |

**严重度汇总**: 2× P1 + 5× P2

---

## 3. 值质量

**状态**: 🔴 RED

**发现项**:

| # | 字段路径 | 问题 | 严重度 |
|---|---------|------|--------|
| 3.1 | `acceptance_contract[0].criteria` | AC-001 的 criteria 值为 `"智能简历生成系统"` — 这是**项目名称**，不是验收标准。应为 REQ-001 对应的可验证验收条件（如 "系统能从纯文本/Markdown输入生成完整简历"）。 | **P0** |
| 3.2 | `acceptance_contract[1-5].criteria` | AC-002~AC-006 的 criteria 直接复制了用户原始需求描述（如 "保真度90%-95%以上"、"与目标JD高度贴合"），**不是组件级可验证的验收标准**。应转化为具体测试条件（如 "对3份真实简历测试，Jaccard相似度≥0.90"）。 | **P1** |
| 3.3 | `acceptance_contract[6-7].criteria` | AC-007/AC-008 的 criteria 为 `"XXX 功能实现完成，满足设计规格"` — 这是**模板占位符**，不是具体验收标准。 | **P1** |
| 3.4 | `work_packages[*].acceptance_criteria[0]` | 所有 8 个 WP 的第一条 acceptance_criteria 都是 `"XXX 功能实现完成，满足设计规格"` — **模板化生成**，无实际验收价值。 | **P1** |
| 3.5 | `work_packages[*].acceptance_criteria[2]` | 所有 8 个 WP 的第三条 acceptance_criteria 都是 `"XXX 与上下游组件集成验证通过"` — **模板化生成**，未定义具体集成测试场景。 | **P2** |
| 3.6 | `risk_contract.risk_register[1-5].description` | 5 条 risk_register 条目的 description 字段包含 **Python dict 字符串表示**（如 `"{'id': 'REC-001', ...}"`），不是结构化 JSON 对象。说明序列化时 `str(dict)` 而非 `json.dumps(dict)`。 | **P1** |
| 3.7 | `work_packages[*].constraints` | 全部为空。WP-001（输入解析层）应有 "支持文件大小≤10MB" 等约束；WP-005（渲染管道）应有 "PDF生成时间<3秒" 等约束。frozen_blueprint 的 architecture.modules 中有详细技术约束，未传递到 ship_package。 | **P1** |
| 3.8 | `work_packages[0-2].estimated_complexity` | Phase 1 的 3 个 WP 全部标记为 `large`，Phase 2 的 3 个 WP 全部标记为 `medium`，Phase 3 的 2 个 WP 全部标记为 `small`。分布过于均匀，可能是按 phase 机械分配而非基于实际复杂度评估。 | **P2** |
| 3.9 | `work_packages[0-5].requirements` | WP-001~WP-006 各映射 1 个 REQ（1:1），但 frozen_blueprint 的 REQ 描述是用户级需求，一个用户级需求可能对应多个组件。缺乏需求分解说明。 | **P2** |
| 3.10 | `harmony_brief.project_context.non_goals` | 空数组。对于有明确范围边界的个人工具项目，应列出不做什么（如 "不支持多人协作"、"不支持在线存储"）。 | **P2** |

**严重度汇总**: 1× P0 + 4× P1 + 5× P2

---

## 4. Markdown 同步

**状态**: 🟡 YELLOW

**发现项**:

| # | 问题 | 严重度 |
|---|------|--------|
| 4.1 | MD 标题被截断：`# Ship Package: 三层可降级架构（基线纯规则<5秒/增强含LLM<30秒/本地LLM隐私优先）+ 统一中间表示层（扩展` — 缺少右括号和后续内容。 | **P1** |
| 4.2 | Harmony Brief 的 Objective 在 MD 中被截断：`...python-docx DOCX + reportlab PDF）+ 双渲染管道（python-docx DOCX + repo` — 明显在 `reportlab` 处被截断。 | **P1** |
| 4.3 | Risk Register 在 MD 中以原始 dict 字符串展示（如 `"{'id': 'REC-001', ...}"`），可读性极差。应格式化为结构化表格。 | **P2** |
| 4.4 | MD 缺少 `harmony_brief.project_context.success_criteria` 的展示（JSON 中有 4 项指标）。 | **P2** |
| 4.5 | MD 缺少 `harmony_brief.not_verified_policy` 的展示。 | **P2** |
| 4.6 | MD 中 WP 的 `source_ref` 字段未展示（JSON 中有值如 `"architecture.modules[COMP-01]"`）。 | **P2** |
| 4.7 | WP-007/WP-008 的 Requirements 在 MD 中标注为 `None`，而 JSON 中为空数组 `[]`。语义一致但表示不精确。 | **P2** |

**数据一致性**:
- ✅ WP 数量一致（8 个）
- ✅ AC 数量一致（8 个）
- ✅ Risk register 数量一致（6 个）
- ✅ 依赖关系一致
- ✅ Phase 分配一致
- ✅ Package order 一致

**严重度汇总**: 2× P1 + 5× P2

---

## 5. 可读性

**状态**: 🟡 YELLOW

**发现项**:

| # | 问题 | 严重度 |
|---|------|--------|
| 5.1 | MD 作为人类可读文档，**缺少执行摘要（Executive Summary）章节**。应在文档开头用 3-5 句话概括：项目目标、WP 总数、Phase 分布、关键风险、就绪状态。 | **P1** |
| 5.2 | Risk Register 章节直接输出原始 Python dict 字符串，对人类读者极不友好。应解析为表格（ID | 标题 | 优先级 | 描述）。 | **P1** |
| 5.3 | 缺少 **依赖关系图** 或至少文字描述的依赖拓扑。当前只有每个 WP 的 Dependencies 列表，无法快速理解整体执行顺序。 | **P2** |
| 5.4 | 缺少 **需求追溯矩阵**（RTM）。Acceptance Contract 表格只展示了 AC→WP 映射，缺少 REQ→AC→WP 的完整追溯链。 | **P2** |
| 5.5 | Harmony Brief 章节过于简略，仅展示了 Objective（被截断）和 Execution Order。缺少 constraints、forbidden_actions、success_criteria 等关键信息。 | **P1** |
| 5.6 | 缺少 **Phase 分组**。8 个 WP 按 WP-001~WP-008 顺序列出，未按 Phase 1/2/3 分组展示。 | **P2** |

**严重度汇总**: 3× P1 + 3× P2

---

## 总结

### 各维度状态

| 维度 | 状态 | P0 | P1 | P2 |
|------|------|----|----|-----|
| 1. Schema 校验 | 🟢 GREEN | 0 | 0 | 0 |
| 2. 字段完整性 | 🟡 YELLOW | 0 | 2 | 5 |
| 3. 值质量 | 🔴 RED | 1 | 4 | 5 |
| 4. Markdown 同步 | 🟡 YELLOW | 0 | 2 | 5 |
| 5. 可读性 | 🟡 YELLOW | 0 | 3 | 3 |
| **合计** | | **1** | **11** | **18** |

### 总评

**Ship Package 产出质量：有条件通过（Conditional Pass）**

**核心问题**（阻塞级）:
1. **AC-001 验收标准无效**（P0）：criteria 是项目名称而非验收条件，无法作为测试依据。必须修复。

**高优先级问题**（建议阻塞）:
2. **Acceptance Criteria 模板化**（P1）：8 个 WP 中，第一条和第三条 AC 均为模板占位符，仅第二条包含实际技术规格。验收合同形同虚设。
3. **Risk register 序列化错误**（P1）：5/6 条 risk 条目的 description 是 Python dict 字符串而非结构化数据，下游无法解析。
4. **Constraints 全部为空**（P1）：8 个 WP 均无约束条件，frozen_blueprint 中的技术约束（性能指标、文件大小限制等）未传递。
5. **Human review points 矛盾**（P1）：WP-003 的 AC 明确要求 "LLM Rewriter需用户显式确认"，但 `human_review_required: false` 且 `human_review_points` 为空。
6. **MD 内容截断**（P1）：标题和 Harmony Brief 被截断，影响文档完整性。

**数据流追溯**:
- frozen_blueprint → ship_package 的模块映射（COMP-01~08 → WP-001~008）正确
- 需求映射（REQ-001~006 → WP-001~006）正确，但 WP-007/008 无需求映射
- frozen_blueprint 的 architecture.modules 中的技术规格已正确传递到 WP 的 acceptance_criteria[1]
- **但** frozen_blueprint 的 constraints（为 None）未被检测为问题并传递到 risk_contract.known_gaps

**建议**:
1. 修复 P0 问题后重新提交
2. 将模板化 AC 替换为具体可验证标准
3. 修复 risk_register 序列化（使用 `json.dumps` 替代 `str(dict)`）
4. 从 frozen_blueprint 的 modules 中提取技术约束填充 WP constraints
5. 解决 human_review_points 矛盾
6. 修复 MD 截断问题，增加执行摘要和 Phase 分组
