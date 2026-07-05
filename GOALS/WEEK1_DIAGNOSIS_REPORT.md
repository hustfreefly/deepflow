# DeepFlow 2.1.0 Week 1 诊断报告

> **诊断目标**: 修复测试基线 + 建立跨域契约 schema  
> **原则**: 只查原因，不修改文件  
> **生成日期**: 2026-07-06  
> **来源**: Hermes 快速检查 + 4 个 Codex CLI 并行 Review

---

## 0. 执行摘要

当前 DeepFlow 仓库处于**高熵状态**：
- 大量未提交修改（M）和删除（D），尤其是 `solution_pro` 的 `_archive` 迁移、blackboard_sessions 清理、文件重命名。
- 测试基线 `455 passed / 21 failed / 5 errors / 46 skipped`。
- 失败集中在三类：外部项目污染、`ModuleNotFoundError`、spec_pro 状态断言。
- AI Native 合规方面：`solution_pro` 已自审发现 Fix 1/4 硬编码问题；`spec_pro` 状态机疑似硬编码；`ship_pro` 缺少独立 Judge；`loop_engine` 空壳。

**建议先稳定基线，再推进架构改造**。基线不稳时做重构，会引入不可控回归。

---

## 1. 测试基线诊断

### 1.1 失败分类（Codex + Hermes 验证）

| 失败组 | 数量 | 根因 | 修复优先级 |
|--------|------|------|------------|
| `projects/resumefit/tests/` | 10 | 嵌套项目 `src.inter...` 导入错误，与 DeepFlow 无关 | P0 — 必须从主基线排除 |
| `tests/diagnostics/test_validation.py` | 9 | `ModuleNotFoundError: deepflow` / `ModuleNotFoundError: core`，包未安装 + 路径问题 | P0 — 修复导入/安装或设置 PYTHONPATH |
| `tests/unit/test_spec_pro_regressions.py` | 2 | `assert 'asking' == 'confirming'` 状态断言失败；测试引用已删除的 `scripts/runners/run_spec_pro.py` | P0 — 状态机硬编码 + 测试过时 |
| `domains/ship_pro/tests/test_ship_pro.py` | 1 | schema contract drift | P1 — 对齐契约 |
| `domains/solution_pro/eval/test_v6_improvements.py` | 4 errors | collection error，eval 目录被 pytest 收集 | P1 — 排除或修复 |
| `tests/test_e2e_living_spec_v2.py` | 1 error | collection error / custom-runner 问题 | P1 — 需要进一步看详情 |

### 1.2 关键发现

- `pytest.ini` **没有 `testpaths`**，因此 pytest 默认递归当前目录，导致 `domains/*/tests/` 和 `projects/resumefit/` 都被收集。这是失败的主因之一。
- `pyproject.toml` 中 `testpaths = ["tests"]` 被 pytest 忽略（WARNING: ignoring pytest config in pyproject.toml!），因为 `pytest.ini` 存在时优先。
- `src/deepflow` 存在，但 `deepflow` 包未安装到当前 Python 环境，所以 `tests/diagnostics/` 中 `import deepflow.diagnostics` 失败。
- `PYTHONPATH=src:.` 可将失败从 24 降至 6 failed + 5 errors（Codex 验证）。
- `tests/unit/test_spec_pro_regressions.py` 第 87-90 行仍引用已删除的 `scripts/runners/run_spec_pro.py`。

- `projects/resumefit/` 不应该由 DeepFlow 主测试基线负责。应将其从 `pytest` 默认路径中排除，或作为独立项目运行。

- `tests/diagnostics/test_validation.py` 中调用 `domains/spec_pro/spec_pro_api.py --help` 失败，因为 `import core.bootstrap` 时 `ModuleNotFoundError: core`。说明这些测试假设包已安装或 `PYTHONPATH` 已设置，但当前环境没有。

- `tests/unit/test_spec_pro_regressions.py` 中 `test_read_output_persists_reconstructed_state` 和另一个测试断言状态为 `confirming`，实际为 `asking`。这很可能是 `spec_pro/coordinator.py` 或 `process_guard.py` 的硬编码状态机逻辑改动导致的，需要结合 spec_pro 最新代码分析。

---

## 2. Git 状态与架构漂移诊断

### 2.1 高熵信号（Codex + Hermes）

- 大量 `solution_pro` 文件被删除（D）：`deterministic_checks.py`, `e2e_test_runner.py`, `golden_case_runner.py`, `harness_validator.py`, `lightweight_spec_agent.py`, `orchestrator_agent.py`, `prefix_extractor.py`, `progress_tracker.py`, `security_validator.py`, `fix_loop_state_machine.py` 等。
- 大量 `solution_pro/prompts/v1/` 被删除，正在从 v1 向 v2 迁移。
- `blackboard_sessions/` 被大量删除，属于调试数据清理。
- `domains/solution_pro/_archive/` 和 `prompts_archive/` 出现，部分文件被归档但可能仍被测试/脚本引用。
- `cage/active/ship_pro_v3.0.yaml` 被删除，但新增 `cage/active/ship_pro_v2.0.yaml`，说明版本回滚。

### 2.2 迁移中的架构漂移（Codex 验证）

- **frozen_spec → living_spec 迁移中**:
  - `domains/solution_pro/convergence_layer.py:474` prefers `living_spec` but falls back to `frozen_spec`.
  - `domains/ship_pro/orchestrator/ship_orchestrator.py:1055` still takes `frozen_spec_path`.
  - CAGE contract `solution_pro_v2.0.yaml:26` uses `spec/living_spec.json -> data/frozen_spec.json`.
  - CAGE contract `ship_pro_v2.0.yaml:19` consumes `data/frozen_spec.json`.
- **v1 prompts → v2/current prompts 迁移中**:
  - 已删除 `domains/solution_pro/prompts/v1/*.md`。
  - 当前代码使用 `summary_module.md`，但部分文档仍指向 v1 prompt 文件。
- **ship_pro v3 → v2 回滚中**:
  - 已删除 `cage/active/ship_pro_v3.0.yaml`。
  - 新增/未跟踪 `cage/active/ship_pro_v2.0.yaml`。
  - 已归档 `cage/active/_deprecated/ship_pro_v3.0.yaml`。

### 2.3 被引用但已删除的文件（Codex 验证）

- `tests/unit/test_spec_pro_regressions.py:87-90` 仍引用已删除的 `scripts/runners/run_spec_pro.py`。
- 未找到 active code 对 `solution_pro/deterministic_checks.py` 的 import。
- 未找到 `_archive/` 或 `prompts_archive/` 被 active code 直接 import。

### 2.4 危险 drift（Codex 验证）

- `domains/solution_pro/__init__.py:24` 仍描述旧的 `_SolutionDispatcher` / 10-stage 行为，但 live entry 返回 `spawn_params`。
- `domains/solution_pro/master_orchestrator.py:5` 文档说 Planning → Research → ReviewQC，但实际执行 Planning → Research → Summary（lines 133-140）。
- `domains/solution_pro/module_orchestrator_base.py:451` 的 `check_contract` 被 bypass：`result = None` 后 `result.get(...)` 被 catch 返回 `True`，验证名存实亡。

### 2.5 建议

1. 先做一次 **git diff --stat** 和 **git diff --name-status** 完整统计，确认哪些删除是预期的。
2. 检查当前工作目录是否能通过 `python -c "import domains.solution_pro"` 等基本导入测试。
3. 将 `blackboard_sessions/` 和 `ARCHIVED/` 加入 `.gitignore` 或确保不被测试引用。
4. 修复 `module_orchestrator_base.py:451` 的 `check_contract` bypass，这是真正的架构漏洞。
5. 统一文档和代码行为：要么更新 `__init__.py` 和 `master_orchestrator.py` 的 docstring，要么修改代码以匹配文档。

---

## 3. 跨域契约诊断

### 3.1 当前契约文件

- `contracts/integration/spec_to_solution.md` — 已修改，但与当前代码不匹配。
- `domains/spec_pro/contracts/living_spec.py` — LivingSpec schema。
- `domains/solution_pro/schemas/schemas.py` — Solution Pro 内部 schema，但缺少 `FinalSolution` 的统一定义。
- `domains/ship_pro/contracts/ship_package.py` — ShipPackage 契约。

### 3.2 关键发现（Codex 验证）

**输入输出路径**
- **Spec Pro → Solution Pro 输入**：`domains/spec_pro/contracts/living_spec.py` 中 `LivingSpec` 是核心；运行时路径通过 blackboard 传递，通常：`data/living_spec.json` → `solution_pro` 读入。
- **Solution Pro 输出**：`summary_orchestrator.py:200` 写出 `final_solution.md` 或 JSON，但无统一 `FinalSolution` schema。
- **Solution Pro → Ship Pro 输入**：`ShipOrchestrator` 接受 `solution_pro_output: Dict[str, Any]` 参数，没有固定文件路径 handoff。
- **Ship Pro 输出**：`pipeline_state.json`, `stages/planner_output.json`, `stages/worker_{role}.json`, `stages/ship_package.json`。

**Schema Mismatches**
- `LivingSpec.route_recommendation` 是 `Optional[str]`，但 integration doc 说是 `dict / None`。
- `SolutionProHints` 字段是 `focus_areas/complexity_notes/priority_dimensions`，但 doc 说是 `focus_areas/layer2_hints/anti_patterns`。
- `SuccessMetric` 只有 `metric`/`target`，但 doc 推荐 `current`。
- `ShipPackage` 需要 `solution_name`, `work_packages`, `dependency_graph`, `metadata`, `semantic_anchors`, `anchor_coverage`；但 Solution Pro 最终输出不保证这些字段。
- `ShipPackage.semantic_anchors` 期望 Solution Pro 透传，但 Solution Pro 最终输出没有 `semantic_anchors` 要求。
- 没有跨域 REQ-ID 追踪字段。`requirement_index` 在 `LivingSpec` 中只是 `list`，没有 REQ-ID 结构。

### 3.3 问题

- 没有显式的 **跨域 REQ-ID 追踪** 机制。
- `frozen_spec.py` 已进入废弃路径（文件中有 DEPRECATION NOTICE），但多个模块仍引用 `frozen_spec_path`。
- `solution_pro/schemas/schemas.py` 中有 `PlanningConvergenceSchema`, `ResearchConvergenceSchema`, `FinalConvergenceSchema` 等，但没有明确与 ship_pro 的输入契约对接。
- `ship_pro` 是否消费 `solution_pro` 的 `FinalSolution`？当前 `ShipOrchestrator` 的输入可能不一致。

---

## 4. AI Native 合规诊断（按域）

### 4.1 `spec_pro`

- **风险**: 状态机跳转由硬编码规则驱动；harness 超时 fallback 会给出默认 PASS。
- **证据**:
  - `test_spec_pro_regressions.py` 状态断言失败（`asking` vs `confirming`）。
  - 存在 harness 超时后默认返回 PASS 的 fallback 路径。
- **目标**: 引入独立 Clarification Judge，状态机由 Judge 输出驱动；超时必须显式失败或降级，不能默认 PASS。

### 4.2 `solution_pro`

- **风险**: Fix 1/4 是硬编码语义判断；Convergence Gate B 是代码实现；AI Native Auditor 是单视角评估。
- **证据**:
  - `convergence_layer.py`: `_evaluate_gate_a` / `_evaluate_gate_b` 是代码权重/规则。
  - `ai_native_auditor.py`: 单一 Agent 自评，没有独立 Judge。
  - `harness_scorer.py`: `GateALayer2Calibration` 是代码权重校准。
  - `information_conservation.py` 未真正使用 LLM 做语义守恒。
- **目标**: 实现 L1/L2/L3 三层 Gate；L2 全部独立 spawn Judge；至少 2 个独立视角评估。

### 4.3 `ship_pro`

- **风险**: 用计数和字段做完整性检查，缺少语义 Judge；Consolidator 单视角。
- **证据**:
  - `ship_orchestrator.py:246`: `validate_ship_package_structure()` 用 `work_packages` 数量和字段做完整性检查。
  - `CompletenessGate` 可能 fallback 到 PASS。
  - 没有 `InformationConservationGate` 验证方案意图是否被保留。
- **目标**: 新增 Plan Judge / Worker Judge / Integration Judge；增加语义守恒验证。

### 4.4 `research_pro`

- **风险**: 来源质量和引用支持度由代码阈值判断，缺少独立 LLM Judge。
- **证据**:
  - `citation_verifier.py:57`: 正则提取 `[N]` 引用是可接受的格式提取（L1）。
  - 但引用是否支持主张、来源是否真正回答研究问题，只有阈值判断，没有 LLM Judge。
- **目标**: 新增 Research Judge 和 Citation Judge。

### 4.5 `loop_engine`

- **风险**: 几乎空壳，没有调度能力。
- **证据**: 仅 1 文件 33 行。
- **目标**: 实现状态机调度器。

---

## 5. 需要用户确认的关键决策（请回复）

在修复之前，以下问题需要你的确认：

1. **是否授权 Week 1 修复？** 当前诊断已完成。如果授权，我将按下方执行顺序开始修复。如果不授权，我停在这里。
2. **Git 工作目录**: 当前大量未提交修改和删除。是否先 stash/清理当前工作目录再做修复？（推荐先清理，避免在混乱基线上继续。）
3. **resumefit**: 是否将 `projects/resumefit/` 从主测试基线中排除？（Codex 和 Hermes 都确认应该排除。）
4. **frozen_spec 废弃**: 是否允许彻底废弃 `frozen_spec.py`，完全切换到 `living_spec.py`？这会影响 `ship_pro` 和 CAGE contract。
5. **blackboard_sessions**: 是否允许将 `blackboard_sessions/` 加入 `.gitignore` 并删除已跟踪的调试数据？
6. **优先修复策略**: 你希望先快速稳定测试基线（只做排除和修复 import），还是同时处理架构 drift（如 `check_contract` bypass）？

---

## 6. 建议的 Week 1 执行顺序（待授权）

1. **稳定 Git 工作目录** — 提交或清理当前修改/删除，明确基线。
2. **隔离 resumefit** — 从主 pytest 路径排除。
3. **修复导入路径** — 让 `tests/diagnostics/` 和 `tests/unit/` 能正确找到 `core` 和 `deepflow`。
4. **修复 spec_pro 状态断言** — 确定是状态机硬编码问题还是测试过时，然后修复。
5. **收集全量测试** — 统一 `pytest.ini` 和 `pyproject.toml`，确保 `domains/*/tests/` 也被收集。
6. **建立跨域契约 schema** — 定义 `LivingSpec` → `FinalSolution` → `ShipPackage` 的 REQ-ID 追踪。
7. **输出 Week 1 完成报告** — `pytest -q` 全绿，契约文档化。

---

*本报告为诊断阶段输出，未修改任何文件。等待用户授权后进入修复阶段。*
