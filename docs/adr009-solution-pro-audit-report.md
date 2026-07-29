# ADR-009 Solution Pro MD-first 落实情况审计报告

> 审计时间: 2026-07-29 15:57
> 审计范围: `.deepflow/domains/solution_pro/` + 跨域消费
> 审计方法: 3 专家并行（架构完整性 / 契约一致性 / 测试覆盖）

---

## 综合评级

| 维度 | 评级 | 核心结论 |
|------|------|---------|
| 架构完整性 | **C** | 实际是 "JSON-first with MD sidecar"，不是 MD-first |
| 契约一致性 | **C+** | Round-trip 保留率 79%，5 个 HIGH 级问题 |
| 测试覆盖 | **C** | frozen_living_md.py 完全没有测试 |
| **综合** | **C+** | **MD-first 仅停留在工具层，未落地到执行层** |

---

## 一、架构完整性审计（评级 C）

### 1.1 MD-first 落地情况

| 检查项 | 状态 | 证据 |
|--------|------|------|
| solution_living_md.py 存在 | ✅ | 含 render/parse/validate 三函数 |
| solution_living_md.py 被调用 | ✅ | `__init__.py:365-374` 调用 `render_final_solution_md()` |
| frozen_living_md.py 存在 | ✅ | 含 render/parse/validate 三函数 |
| frozen_living_md.py 被调用 | ✅ | `__init__.py:220-221` 调用 `render_frozen_spec_md()` |
| 无 JSON 写入残留 | ❌ | 大量 JSON 写入逻辑存在 |
| MD 是主写入路径 | ❌ | MD 是 JSON 的**事后衍生物**，非主路径 |

### 1.2 发现的问题

| # | 问题 | 严重程度 | 证据 |
|---|------|---------|------|
| 1 | **write_stage() 硬编码 .json 后缀** | 🔴 Critical | `core/blackboard/blackboard_manager.py`: `_stage_path()` 返回 `f"{stage_name}.json"`，`write_stage()` 用 `json.dump()` |
| 2 | **双写问题：JSON 主写 + MD 侧车** | 🔴 Critical | `__init__.py:371-374`：先读 JSON，再渲染 MD 侧车。JSON 是真相源 |
| 3 | **Prompt 仍指向 JSON 作为完成条件** | 🔴 Critical | `summary_module.md:728`："输出写入 stages/final_solution.json"；`orchestrator.md:147`：检查 `.json` 存在性 |
| 4 | **Ship Pro 直接读 frozen_spec.json** | 🟡 High | `ship_orchestrator.py:1502-1508`：从 `frozen_spec.json` 提取 requirements |
| 5 | **blackboard.py 注册表全 JSON** | 🟡 High | `STAGE_PATH_REGISTRY` 所有路径均为 `.json` |
| 6 | **read_stage() 只读 JSON** | 🟡 High | 用 `json.load()` 读取，无 MD 解析能力 |
| 7 | **pulse.py 状态机全 JSON** | 🟡 Medium | `_solution_pulse_state.json` 是唯一状态文件 |
| 8 | **测试用例验证 JSON** | 🟡 Medium | `test_verification_constraints.py:150`：`load_stage("final_solution.json")` |
| 9 | **MD 渲染是非阻断的可选步骤** | 🟡 Medium | `render_solution_md()` 失败只 log ERROR，不阻断流程 |
| 10 | **write_stage 陷阱** | 🟠 Medium | Prompt instructs `bb.write_stage('base_solution', markdown_string)`，但 `write_stage` 会 `json.dump(markdown_string)` → 写入 JSON 编码的字符串 |

### 1.3 调用链对比

**实际调用链（当前状态）：**
```
Worker Agent (LLM)
  → bb.write_stage('final_solution', dict)
    → stages/final_solution.json  ← 🔴 JSON 是真相源
  → [Post-completion] render_solution_md()
    → read JSON → render → write final_solution.md  ← 🟡 MD 是衍生品
  → [Ship Pro] read frozen_spec.json  ← 🔴 跨域消费也是 JSON
```

**声称的 MD-first 调用链（应然状态）：**
```
Worker Agent (LLM)
  → bb.write_stage('final_solution', markdown_string)
    → stages/final_solution.md  ← MD 是真相源
  → [Downstream] parse_final_solution_md() → dict  ← 需要时再解析
```

---

## 二、契约一致性审计（评级 C+）

### 2.1 Round-trip 完整性

| 模块 | 字段数 | 完整保留 | 部分保留 | 丢失 | 保留率 |
|------|-------|---------|---------|------|-------|
| final_solution | 15 | 11 | 3 | 1 | 83% |
| frozen_spec | 19 | 13 | 3 | 3 | 76% |
| **综合** | **34** | **24** | **6** | **4** | **79%** |

### 2.2 发现的问题

#### solution_living_md.py

| # | 字段 | 问题 | 严重程度 |
|---|------|------|---------|
| 1 | `full_solution` | **类型不匹配**: render 写入结构化 dict，parse 返回原始字符串。下游期望 dict 时崩溃 | 🔴 HIGH |
| 2 | `gate_decisions` | **完全丢失**: render 写入 L1/L2/L3 表格，parse 完全没有解析 | 🟡 MEDIUM |
| 3 | `constraint_coverage` | **部分丢失**: overview 统计数据全部丢失，只恢复 uncovered 列表 | 🟡 MEDIUM |
| 4 | `risk_summary` | **截断丢失**: risk→40字符、mitigation→60字符硬截断 | 🟡 MEDIUM |
| 5 | `metadata` dict values | **截断丢失**: dict 值截断为 80 字符 JSON | 🟢 LOW |

#### frozen_living_md.py

| # | 字段 | 问题 | 严重程度 |
|---|------|------|---------|
| 6 | `schema_version` | **完全丢失**: frontmatter 不解析 version | 🔴 HIGH |
| 7 | `session_id` | **完全丢失**: frontmatter 不解析 session | 🟡 MEDIUM |
| 8 | `key_decisions` | **类型不匹配**: dict 扁平化为 str，原始 rationale/alternatives 丢失 | 🔴 HIGH |
| 9 | `risk_summary` | **类型不匹配**: dict 扁平化为 str，severity/probability 丢失 | 🔴 HIGH |
| 10 | `implementation_phases` | **类型不匹配**: dict 扁平化为 str，tasks/timeline/effort 丢失 | 🔴 HIGH |
| 11 | `gate_decisions` | **完全丢失**: 表格不解析 | 🟡 MEDIUM |

### 2.3 边界情况

| 场景 | 行为 | 评级 |
|------|------|------|
| 空列表 `[]` | render 写 "(none)"，parse 返回 `[]` | ✅ OK |
| `None` 值 | 跳过渲染 → parse 无此字段 | ⚠️ 字段缺失 |
| 特殊字符 `\|` | 表格内 pipe 未转义，破坏解析 | 🟡 潜在风险 |
| 超长文本 | 多处硬截断 ([:40], [:60], [:80]) | 🔴 信息丢失 |
| 空 semantic_anchors | render `<!-- empty -->`，parse 返回 `[]` | ✅ OK |

---

## 三、测试覆盖审计（评级 C）

### 3.1 测试覆盖情况

| 模块 | 测试数 | 覆盖场景 | 缺失场景 |
|------|-------|---------|---------|
| solution_living_md.py | 15 | round-trip, render, parse, validate, BUG-001 回归 | 真实数据 round-trip 仅 1 例 |
| frozen_living_md.py | **0** | — | **完全没有测试** |
| Ship Pro 集成 | 2 | 基本 MD 存在性检查 | 无 MD→parse→消费 端到端测试 |

### 3.2 发现的问题

| # | 缺失测试 | 风险 | 建议 |
|---|---------|------|------|
| 1 | frozen_living_md.py 全部测试 | 🔴 HIGH | 补充 render/parse/validate/round-trip 测试 |
| 2 | frozen_spec → Ship Pro 消费端到端 | 🟡 MEDIUM | 验证 MD 是否真正被 Ship Pro 消费 |
| 3 | 特殊字符（pipe、换行）在表格中 | 🟡 MEDIUM | 补充边界测试 |
| 4 | 大规模数据性能 | 🟢 LOW | 100+ requirements 的 round-trip |

---

## 四、综合结论

### 核心判断

**ADR-009 在 Solution Pro 的 MD-first 迁移处于"工具就绪、执行未迁移"状态。**

- ✅ 工具层完备：render/parse/validate 三函数齐全
- ❌ 执行层未迁移：write_stage 硬编码 JSON，Prompt 指向 JSON，跨域消费 JSON
- ❌ 契约有缺陷：79% round-trip 保留率，5 个 HIGH 级信息丢失
- ❌ 测试有盲区：frozen_living_md.py 零测试

### 修复优先级

| 优先级 | 修复项 | 影响范围 |
|--------|-------|---------|
| 🔴 P0 | write_stage() 支持 MD 写入（检测 content 类型） | core/blackboard |
| 🔴 P0 | 更新所有 Prompt 完成条件从 .json → .md | prompts/solution_pro/ |
| 🔴 P0 | frozen_spec parse 增加 frontmatter + 结构化字段保留 | frozen_living_md.py |
| 🔴 P0 | frozen_living_md.py 补充完整测试 | tests/ |
| 🟡 P1 | Ship Pro 跨域消费从 .json → .md | ship_pro/ |
| 🟡 P1 | solution_living parse 增加 gate_decisions + full_solution 结构化解析 | solution_living_md.py |
| 🟡 P1 | 去除硬截断或提高阈值 | 两个 living_md 模块 |
| 🟡 P2 | 更新测试用例验证 MD 产物 | tests/ |

---

*报告生成: 3 专家并行审计 | 审计文件: solution_living_md.py, frozen_living_md.py, __init__.py, blackboard_manager.py, prompts/*, tests/*
