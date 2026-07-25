# DeepFlow 跨域系统审查报告（2026-07-25）

> 触发：Solution Pro 2.5D 实战暴露 21 问题后，3 个 Agent 并行审查 Ship Pro / Deliver Pro+Core / Spec Pro+Research Pro。
> 本报告合并三份审查结果，按优先级统一排序。

---

## 🔴 P0 — 高危，与今日生产事故同类，未修复

### P0-1: Deliver Pro project_name 无 sanitize（slash 全链路崩溃）
- **与今日事故同类**：Solution Pro 的 session_id 含 "/"（CoWoS-S/L）导致 validate 误判失败 → cron 自删 → 系统假死。Deliver Pro 的 project_name **完全没有 sanitize**，含 "/" 时全链路路径错位。
- **证据**：`domains/deliver_pro/__init__.py:224`、`orchestrator.py:63,72` — 直接拼接 `blackboard_root / project_name`；`wp_runner.py` 11 处 `.parent.parent` 推导 deepflow_root（slash 时全部错位）。
- **修复**：project_name 进路径前统一 sanitize（复用 `core/config/path_config.py:_sanitize_session_id`）；wp_runner 的 `.parent.parent` 改为显式参数。

### P0-2: NO_REPLY 防护全域缺失（spec/research/ship 三域零防护）
- **今日实证**：Solution Pro 子 Agent 因重复完成事件回 NO_REPLY 死亡 4 次。只有 solution_pro 有生存铁律，其他三域 prompt **零 NO_REPLY 规则**。
- **证据**：`grep NO_REPLY domains/spec_pro/prompts/ domains/research_pro/prompts/` 无结果；ship_pro orchestrator prompt 有"每次 turn 必须 tool call"但无 NO_REPLY 禁令。
- **修复**：将 `domains/solution_pro/prompts/_shared_subagent_rules.md` 提升为全域共享（`core/prompts/` 或 `domains/_shared/`），增加 NO_REPLY 铁律，所有域子 Agent prompt 必须引用。

## 🟡 P1 — 文档与实现矛盾 / 契约不完整

### P1-1: Ship Pro Orchestrator prompt 与 V8 决策矛盾（yield 残留）
- **证据**：`docs/V8_DECISIONS.md:172` 声明"禁止 sessions_yield（用 cron wake 替代）"，但 `__init__.py:408-670` Orchestrator prompt 有 **7+ 处** yield 指令。文档说一套，prompt 做一套。
- **风险**：如果 yield 即死（Solution Pro A1），Ship Pro Orchestrator 同样会死。
- **修复**：统一——要么 prompt 改为 cron wake，要么确认 V8 架构已废弃并更新决策文档。

### P1-2: Solution Pro MD-first 未接线（render_final_solution_md 死代码）
- **证据**：`solution_living_md.py:45` 的 `render_final_solution_md()` 存在且功能完整，但**生产链路零调用**（仅 test 调用）。`generate_solution_track()` 找 `final_solution.md` → 不存在 → track 未生成。
- **修复**：finalize 相位增加 MD 渲染步骤（render → 写 final_solution.md / solution_design.md）；修复 `summary_json_extractor.md` 的 frozen_spec.md 错误引用。

### P1-3: Spec Pro 输出契约半钉死
- **证据**：`parse.md`/`structure.md`/`assess.md`/`guide.md`/`harness.md` 均未钉死输出路径/格式，依赖 `coordinator.py:_build_round_task()` 动态注入。注入失败 = worker 不知道写哪里。
- **修复**：每个 worker prompt 增加 `## 输出契约` 节。

### P1-4: Research Pro MD-first 仅 prompt 级约定
- **证据**：最终产出 `report/final.md` 路径是 prompt 约定的，无代码级 render 兜底。LLM 偏离格式无代码防线。
- **修复**：增加 `render_research_report_md()` 或至少 finalize 时验证 MD 存在。

## 🟢 P2 — 架构债，不紧急但应清理

### P2-1: Ship Pro project_name/role sanitize 不完整
- role 只替换空格不替换 `/`（`ship_orchestrator.py:540`、`__init__.py:758`）；`_get_project_blackboard()` 无 sanitize。

### P2-2: Deliver Pro legacy 迁移中的 `.parent` 风险
- `phase_deriver.py:332` 的 Legacy 2 路径用 `wp_dir.parent`，slash 场景下迁移源错位。

### P2-3: Spec Pro 无断点恢复入口
- 有 `coord_state.json`/`round_result.json` 但无 `resume()` 方法。中途死亡只能从头开始。

### P2-4: Ship Pro 双路径写入机制（stages/ vs stages/worker_outputs/）
- Worker 写 `worker_outputs/`，state_manager 写 `stages/`，有 fallback 但架构不清晰。

---

## 跨域模式总结

| 模式 | 涉及域 | 严重度 |
|------|--------|--------|
| **sanitize 不统一**（slash 路径） | solution✅已修 deliver🔴未修 ship🟡部分 | 🔴 |
| **NO_REPLY 防护缺失** | solution✅有 spec🔴无 research🔴无 ship🟡无 | 🔴 |
| **文档与实现漂移** | ship🔴(yield矛盾) solution🟡(MD死代码) | 🟡 |
| **MD-first 接线不完整** | solution🔴(死代码) research🟡(无兜底) ship🟡(non-blocking) spec✅ | 🟡 |
| **输出契约半钉死** | spec🟡 research🟡 ship✅ solution✅已改善 | 🟡 |

## 各域判定

| 域 | 判定 | 核心风险 |
|---|------|---------|
| Solution Pro | ✅ 已修复（今日） | MD-first 未接线 |
| Ship Pro | 🟡 CONDITIONAL | yield 残留 + sanitize 不完整 |
| Deliver Pro | 🔴 高危 | project_name 无 sanitize（同类 bug 未修） |
| Spec Pro | 🟡 CONDITIONAL | 无 NO_REPLY + 输出契约半钉死 + 无恢复入口 |
| Research Pro | 🟡 CONDITIONAL | 无 NO_REPLY + MD 无代码兜底 |
