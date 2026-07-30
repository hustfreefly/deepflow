# FixFlow Worker A — orchestrator.py 双问题修复

## Phase 0: 决策门

| 问题 | 不修会怎样 | 本质 | 决策 |
|------|-----------|------|:----:|
| A1: VALIDATING 分支非 PASS verdict 崩溃 | 任何验证失败都直接 terminal_failed，无法进入 fix 循环 | 代码（异常处理 + 路径错误） | ✅ 代码修 |
| A2: batch 级 task 字符串过长 | 最终 gate/synthesis 任务被截断，导致输出失败 | 代码（task 构造）+ Prompt（引用方式） | ✅ 混合修（代码侧） |

## Phase 1: 诊断

### A1 症状与根因
- **症状**: `DeliverOrchestrator._get_wp_next_action()` 在 phase="VALIDATING" 且 verdict != "PASS" 时抛异常，未进入 `fix_integrate` 或 `package_failed`。
- **根因假设**:
  1. `self.stages_dir` 在 `DeliverOrchestrator` 上不存在（只有 `DeliverWPRunner`/`DeliverRunner` 有），导致 `AttributeError`。
  2. `action="fix_integrate"` 不在 `PulseAction.action` 的 `Literal` 枚举中，触发 Pydantic ValidationError。
- **修复方向**:
  - 将 `self.stages_dir / "validate" / "validation_result.json"` 改为 `self._wp_dir(wp_id) / "stages" / "validation_result.json"`。
  - 在 `PulseAction.action` 的 `Literal` 中加入 `"fix_integrate"`。
  - 用 `try/except` 包裹 verdict 读取和 fix 决策，任何异常返回 `package_failed` 而不是抛错。
- **测试 A**: 写一个 test 构造 `validation_result.json` verdict=FAIL + has_fixable=True，断言 `_get_wp_next_action` 返回 `action="fix_integrate"` 且不抛异常。

### A2 症状与根因
- **症状**: `_build_infer_contract_action()` 3673 chars、`_build_final_synthesis_action()` 5619 chars、`_build_run_final_gate_action()` 7912 chars，远超 inline-task 上限。
- **根因假设**: 把 `living_spec` / `contract` / `synthesis` 大段 JSON 直接 inline 到 `task` 字符串中，未使用文件引用模式。
- **修复方向**:
  - 将摘要/内容写入 blackboard 文件：
    - `blackboard/{project}/_infer_contract_context.md`
    - `blackboard/{project}/final_synthesis/_synthesis_input.md`
    - `blackboard/{project}/final_synthesis/_gate_input.md`
  - `task` 字符串只保留角色说明 + 文件引用 + 输出要求，控制在 1500 字符以内（理想 < 500）。
- **测试 A**: 写一个 test 用 synthetic 大文件调用三个 builder，断言 `len(task) < 2000`（最好 < 500），并验证 task 包含文件引用路径。

## Phase 2: 执行约束

- 不修改其他不相关文件
- 保留现有 API 和调用签名
- 使用 `Path` 和原子写入（已有模式）
- 任何新字段/枚举必须加 Pydantic 约束

## Phase 3: 验证清单

- [ ] A1 test 修复前复现崩溃 / 修复后不崩溃
- [ ] A2 test 三个 task 长度均 < 2000
- [ ] `pytest domains/deliver_pro/tests/test_orchestrator.py` 通过（不要全量 pytest，避免冲突）
- [ ] `ruff check domains/deliver_pro/orchestrator.py` 无新增错误
- [ ] 输出修改摘要 + git diff
