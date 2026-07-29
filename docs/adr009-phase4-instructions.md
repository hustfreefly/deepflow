# ADR-009 Phase 4: Prompt 迁移 — 子 Agent 指令

## 任务概述

将 Solution Pro 的 prompt 文件中所有交付物 `.json` 引用改为 `.md` 引用。

---

## 改动范围

**目标目录**: `domains/solution_pro/prompts/`

**改动规则**:
- `frozen_spec.json` → `frozen_spec.md`
- `final_solution.json` → `final_solution.md`
- `solution_document.json` → `solution_document.md`
- `living_spec.json` → `living_spec.md`（如果存在）

**不要改的**:
- `shared_state.json` — 内部状态文件，保持 JSON
- `master_state.json` — 内部状态文件，保持 JSON
- `planning_convergence.json` — 内部收敛文件，保持 JSON
- `research_convergence.json` — 内部收敛文件，保持 JSON
- `final_convergence.json` — 内部收敛文件，保持 JSON
- 其他内部 stage（如 `meta_planning.json`、`convergence_planning.json` 等）— 这些是内部中间产物，不是跨域交付物

**判断标准**: 只有**跨域交付物**（frozen_spec、final_solution、solution_document、living_spec）需要改为 .md。内部状态和中间产物保持 .json。

---

## 具体步骤

1. **扫描所有 prompt 文件**: `domains/solution_pro/prompts/*.md`
2. **查找 .json 引用**: `grep -rn "\.json" domains/solution_pro/prompts/`
3. **逐个判断**: 是跨域交付物还是内部文件？
4. **替换交付物引用**: `.json` → `.md`
5. **同时更新代码引用**: 如果 prompt 中有 `bb.read_json('data/frozen_spec.json')` 这样的代码示例，改为 `bb.read_stage('frozen_spec')` 或 `parse_frozen_spec_md(bb.read_stage('frozen_spec'))`

---

## 验证标准

- [ ] `grep -rn "frozen_spec\.json" domains/solution_pro/prompts/` 返回空
- [ ] `grep -rn "final_solution\.json" domains/solution_pro/prompts/` 返回空
- [ ] `grep -rn "solution_document\.json" domains/solution_pro/prompts/` 返回空
- [ ] 内部状态文件引用（shared_state.json 等）保持不变
- [ ] 现有测试通过

---

## 完成后报告

1. 修改了哪些 prompt 文件
2. 每个文件改了什么
3. 测试是否通过
