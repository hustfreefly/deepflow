# 端到端流程审计报告

> 审计日期: 2026-07-06
> 审计范围: Spec Pro → Solution Pro → Ship Pro 全流程
> 审计视角: 端到端流程能否顺利执行

## 综合评分: 5.5/10

**一句话**: 三个域各自内部设计扎实，但域间桥接依赖主 Agent 手动串联，无自动化全流程入口，断点续跑仅限域内，跨域数据格式存在隐性断裂风险。

---

## 1. 全流程连通性: ⚠️

### Spec Pro → Solution Pro

**入口**: Spec Pro 产出 `spec/spec_handoff_package.json`（via `handoff.py`），Solution Pro 接受 `living_spec` kwarg（via `run_solution_pro(living_spec=...)`）。

**桥接方式**: **手动**。主 Agent 必须：
1. 读取 Spec Pro 的 `spec_handoff_package.json`
2. 提取 `living_spec` 字段
3. 显式传入 `run_solution_pro(living_spec=handoff["living_spec"])`

**问题**:
- ❌ 没有自动加载机制。`run_solution_pro()` 的 `living_spec` 参数是 `kwargs.get("living_spec")`，如果不传，`frozen_spec.py` 会从 topic 重新生成（丢失 Spec Pro 的多轮精炼结果）
- ⚠️ `spec_handoff_package.json` 包含 `handoff_allowed` 字段，但 Solution Pro 不检查它——任何 dict 都能传入
- ⚠️ Spec Pro 的 `living_spec` 结构与 Solution Pro `frozen_spec.py` 期望的 `living_spec` 结构是否完全兼容？`frozen_spec.py` 读取 `living_spec.confirmed` 层的特定字段（narrative, requirements, constraints 等），如果 Spec Pro 输出格式变化，会静默降级为 fallback

**连通性评级**: ⚠️ 可工作但脆弱——依赖主 Agent 正确串联

### Solution Pro → Ship Pro

**入口**: Solution Pro 写入 `data/frozen_spec.json`。Ship Pro 的 `run_ship_pro(project_name)` 自动从统一 blackboard 读取。

**桥接方式**: **半自动**。`_find_solution_pro_output()` 会自动查找 `data/frozen_spec.json`，用 `build_ship_pro_input()` 合并。

**亮点**:
- ✅ 统一 blackboard 路径 `.deepflow/blackboard/{project_name}/` 确保两个域看到同一份数据
- ✅ `build_ship_pro_input()` 有信息守恒验证（检查 requirements 非空）
- ✅ 支持 `supplemental.json` 补充人工决策

**问题**:
- ⚠️ `project_name` 必须一致——Spec Pro 的 session_id、Solution Pro 的 topic slug、Ship Pro 的 project_name 必须匹配。没有自动传递机制
- ⚠️ Solution Pro 的 `run_solution_pro()` 用 `topic` 作为 `BlackboardManager` 的标识生成 session_id，而 Ship Pro 用 `project_name` 查找——如果两者不一致，`FileNotFoundError`

**连通性评级**: ⚠️ 设计合理但命名约定是隐性契约

### 一键全流程入口

**不存在**。

- `UnifiedEntry` 只注册了 `solution_pro`、`code`、`general`、`research_pro`，**没有 `spec_pro` 和 `ship_pro`**
- `EntryHarness._init_session("solution_pro")` 直接 `raise NotImplementedError`——指向 V2 架构
- 没有任何 `run_full_pipeline()` 或 `run_e2e()` 函数（`_archive/v1/e2e_test_runner.py` 已归档）
- 实际全流程运行方式：主 Agent 依次调用 `SpecProCoordinator` → `run_solution_pro()` → `run_ship_pro()`，手动传递数据

**评级**: ❌ 不存在

---

## 2. 数据流完整性: ⚠️

### 数据流图

```
用户输入
  │
  ▼
┌─────────────────────────────────┐
│ Spec Pro                         │
│ Coordinator → Workers → Living Spec │
│ 输出: spec/living_spec.json      │
│       spec/spec_handoff_package.json │
└──────────┬──────────────────────┘
           │ ⚠️ 手动桥接（主 Agent 传递 living_spec）
           ▼
┌─────────────────────────────────┐
│ Solution Pro                     │
│ run_solution_pro(living_spec=...) │
│ frozen_spec.py → data/frozen_spec.json │
│ MasterOrchestrator → Planning → Research → Summary │
│ 输出: data/frozen_spec.json      │
│       stages/solution_document.json │
└──────────┬──────────────────────┘
           │ ✅ 自动桥接（统一 blackboard 路径）
           ▼
┌─────────────────────────────────┐
│ Ship Pro                         │
│ run_ship_pro(project_name)       │
│ _find_solution_pro_output() → build_ship_pro_input() │
│ Orchestrator → Designer → Workers → Consolidator │
│ 输出: ship_pro/stages/ship_package.json │
└─────────────────────────────────┘
```

### 断裂点标注

| # | 位置 | 断裂类型 | 严重度 | 说明 |
|---|------|---------|--------|------|
| 1 | Spec Pro → Solution Pro | **格式隐式契约** | P1 | `living_spec` 的 schema 没有跨域验证。Spec Pro 的 `LivingSpec` Pydantic model 与 Solution Pro `frozen_spec.py` 期望的字段可能不同步 |
| 2 | Spec Pro → Solution Pro | **信息丢失风险** | P1 | 如果主 Agent 忘记传 `living_spec`，`frozen_spec.py` 会从 topic 字符串重新生成，丢失多轮精炼结果，且无任何警告 |
| 3 | Solution Pro → Ship Pro | **命名约定** | P2 | `project_name` vs `topic` vs `session_id` 必须一致，但没有验证 |
| 4 | Solution Pro 内部 | **frozen_spec 废弃中** | P2 | `frozen_spec.py` 已标记 DEPRECATION，但 Ship Pro 仍依赖它作为主要输入源 |
| 5 | Spec Pro handoff | **handoff_allowed 未消费** | P2 | Spec Pro 的 `handoff_allowed` 字段在 Solution Pro 侧完全不检查 |

### 数据格式兼容性

- Spec Pro `LivingSpec` → Solution Pro `frozen_spec.build_frozen_spec(living_spec=...)`:
  - `frozen_spec.py` 读取 `living_spec.get("confirmed", {})` 的各字段
  - 如果 Spec Pro 输出没有 `confirmed` 层（例如只有 `raw`），会 fallback 到纯 topic 生成
  - **风险**: 静默降级，不报错

- Solution Pro `frozen_spec.json` → Ship Pro `build_ship_pro_input()`:
  - `build_ship_pro_input()` 直接透传 frozen_spec 的所有字段
  - 有 `req_count == 0` 的守恒检查 ✅
  - **风险较低**

---

## 3. 错误传播: ⚠️

### Spec Pro 产出低质量 Living Spec → Solution Pro

- Solution Pro 的 `frozen_spec.py` 会尝试从 living_spec 提取信息
- 如果 living_spec 质量低（字段缺失），会 **静默 fallback** 到 topic-based 生成
- **没有质量门控**: Solution Pro 不检查 living_spec 的 quality_report 分数
- **后果**: 低质量 Spec → 低质量 frozen_spec → 下游全部受影响，但无告警

### Solution Pro 某个 Orchestrator 失败 → 其他

- `MasterOrchestrator._run_module()` 有 **模块级隔离**:
  - 超时 → `ModuleTimeoutError`（不降级，直接 fail）
  - 异常 → `ModuleFailureError`（不降级，直接 fail）
  - **不自动降级**: 注释明确说 "no degradation"
- **问题**: Planning 失败 → Research 无法启动（依赖 planning_output）→ 整个 pipeline 停止
- **但没有跨模块恢复**: 如果 Research 失败，Planning 的已完成输出保留（断点续跑可跳过），但没有自动重试

### Ship Pro 某个 Worker 超时 → 整体

- Ship Pro 的 Orchestrator 是 **纯工具库**（`ShipOrchestrator` 不调用 sessions_spawn）
- 调度逻辑在 Orchestrator Agent（LLM）的 prompt 中
- Worker 超时 → Agent 看到超时 → 由 LLM 决定行为（prompt 说 "FAIL → 输出失败详情，不 retry"）
- **问题**: 依赖 LLM 正确解释超时并做出合理决策
- **保护**: L1 验证 + L2 MUST Judge 会捕获缺失/低质量输出

### 错误信息质量

- Solution Pro: `ModuleTimeoutError(module_name, timeout)` — 信息充分 ✅
- Ship Pro: `FileNotFoundError` 带路径信息 ✅
- Spec Pro: `ValueError` 带输入长度信息 ✅
- **跨域错误**: 如果 `frozen_spec.json` 不存在，Ship Pro 的 `FileNotFoundError` 消息清晰说明了期望路径 ✅

---

## 4. 执行可靠性: ⚠️

### 重试机制

| 域 | 重试 | 说明 |
|----|------|------|
| Spec Pro | ❌ 无 | Worker 超时 → fallback 数据（空 JSON），不重试 |
| Solution Pro | ⚠️ 有限 | 断点续跑可重新运行未完成模块，但 `_run_module` 本身不重试 |
| Ship Pro | ⚠️ LLM 决策 | prompt 说 "不 retry"，但 L2/L3 FAIL 允许 1 次修复重试 |

### 超时保护

| 域 | 超时 | 说明 |
|----|------|------|
| Spec Pro | ✅ 每 Worker 180s | `timeoutSeconds: 180` in spawn params |
| Solution Pro | ✅ 模块级差异化 | planning=600s, research=900s, summary=1200s, review_qc=600s |
| Ship Pro | ⚠️ 依赖 Agent | Orchestrator Agent 自行管理，无硬编码超时 |

### 并发控制

| 域 | 并发 | 说明 |
|----|------|------|
| Spec Pro | ✅ 串行 | Workers 按顺序 spawn |
| Solution Pro | ✅ 串行 | Planning → Research → Summary 顺序执行 |
| Ship Pro | ✅ 分层并行 | execution_order 控制层级，层内并行 |

### 状态恢复（断点续跑）

| 域 | 断点续跑 | 说明 |
|----|---------|------|
| Spec Pro | ❌ 无 | session 重新开始，不恢复 |
| Solution Pro | ✅ 双层验证 | `master_state.json` + `module_{name}_state.json`，`_is_module_completed()` 检查 |
| Ship Pro | ⚠️ 部分 | `StateManager` 跟踪 stage，但恢复逻辑在 Agent prompt 中 |
| **跨域** | ❌ 无 | 如果 Ship Pro 失败，不能从 Solution Pro 输出恢复，必须重跑整个 Ship Pro |

---

## 5. 可观测性: ⚠️

### 日志/进度输出

| 域 | 日志级别 | 说明 |
|----|---------|------|
| Spec Pro | ✅ 充分 | `execution_log.json` 记录每轮事件，`quality_trajectory.json` 跟踪质量变化 |
| Solution Pro | ✅ 充分 | `PipelineWatcher` 记录每模块 start/end/duration/gate results，`pipeline_watcher_report.json` |
| Ship Pro | ⚠️ 中等 | `StateManager` 跟踪 stage 状态，但无独立的时间/指标记录 |

### 跨域追踪

- ❌ **无 REQ-ID 全链路追踪**: Spec Pro 创建需求 → Solution Pro 生成 REQ-ID → Ship Pro 分配给 Worker，但没有统一的追踪 ID 贯穿三个阶段
- ❌ **无统一 trace/correlation ID**: 每个域生成自己的 session_id，跨域关联靠命名约定
- ⚠️ **blackboard 路径是唯一的关联线索**: 通过 `.deepflow/blackboard/{project_name}/` 可以追踪，但需要人工拼接

### 执行时间/token 统计

- Solution Pro `PipelineWatcher`: ✅ 每模块 duration，总 duration
- Spec Pro: ⚠️ 有 `execution_log.json` 的时间戳，但无 token 统计
- Ship Pro: ❌ 无 token/时间统计
- **跨域**: ❌ 无汇总报告

### 执行报告

- Solution Pro: `pipeline_watcher_report.json` ✅
- Spec Pro: `quality_report.json`, `harness_report.json` ✅
- Ship Pro: `ship_package.json` 是产出物，不是执行报告
- **跨域汇总报告**: ❌ 不存在

---

## 问题清单（按严重度排序）

| # | 位置 | 问题 | 严重度 | 修复方向 |
|---|------|------|--------|---------|
| 1 | Spec Pro → Solution Pro | 无自动桥接，主 Agent 必须手动传递 `living_spec`，忘记传则静默降级 | **P0** | 在 `run_solution_pro()` 中增加 blackboard 自动发现逻辑：如果 `living_spec` 未传，检查 `data/spec_handoff_package.json` 是否存在 |
| 2 | EntryHarness | `solution_pro` domain 直接 `raise NotImplementedError`，统一入口不可用 | **P0** | 更新 `EntryHarness._init_session()` 支持 V2 架构，或创建新的 `run_full_pipeline()` 入口 |
| 3 | 全流程 | 无一键全流程入口，三个域必须手动串联 | **P1** | 创建 `core/full_pipeline.py`，封装 Spec Pro → Solution Pro → Ship Pro 的完整流程 |
| 4 | Spec Pro → Solution Pro | `handoff_allowed` 字段不被 Solution Pro 消费，质量门控形同虚设 | **P1** | 在 `run_solution_pro()` 中检查 `handoff_allowed`，或在 `frozen_spec.py` 中验证 density gate |
| 5 | 跨域 | 无统一 trace/correlation ID，无法追踪一个 REQ 从 Spec Pro 到 Ship Pro 的完整路径 | **P1** | 在 Spec Pro 阶段生成 `trace_id`，写入所有下游产出 |
| 6 | Solution Pro | `frozen_spec.py` 已标记 DEPRECATION 但仍是 Ship Pro 的主要输入源 | **P2** | 明确 Phase 2 时间线，或在 `frozen_spec.py` 中添加运行时 deprecation warning |
| 7 | Ship Pro | 无硬编码超时保护，依赖 Agent LLM 决策 | **P2** | 在 `run_ship_pro()` 的 prompt 中注入总超时限制，或在 `ShipOrchestrator` 中增加超时检查 |
| 8 | 跨域 | `project_name` / `topic` / `session_id` 命名约定是隐性契约 | **P2** | 在 `run_ship_pro()` 中增加模糊匹配或路径提示 |
| 9 | Spec Pro | Worker 超时后写 fallback 空数据，不重试 | **P2** | 增加 1 次自动重试（在 Coordinator 层） |
| 10 | 跨域 | 无跨域执行报告（时间、token、质量汇总） | **P3** | 创建 `core/reports/e2e_report.py`，汇总三个域的执行指标 |

---

## 亮点

1. **统一 Blackboard 路径设计** ✅ — `.deepflow/blackboard/{project_name}/` 让 Solution Pro 和 Ship Pro 共享数据，`build_ship_pro_input()` 有信息守恒验证
2. **Solution Pro 断点续跑** ✅ — 双层 state 验证（master_state + module_state），模块级超时保护，已完成模块自动跳过
3. **Spec Pro 质量门控体系** ✅ — density gate + harness report + quality trajectory，多层质量保障
4. **Ship Pro 多层验证** ✅ — L1 结构验证 → L2 MUST Judge → L2/L3 语义验证（InfoConservation + Completeness + HarnessV3），Gate 体系完整
5. **PipelineWatcher 可观测性** ✅ — Solution Pro 有独立的运行时监控，记录每模块 duration 和 gate results
6. **测试覆盖** ✅ — 188 + 293 = 481 个测试用例，覆盖 golden cases、regressions、verification constraints
7. **frozen_spec 信息守恒** ✅ — `build_ship_pro_input()` 保留了 frozen_spec 的全部字段，解决了之前 71% 信息丢失的问题
8. **Spec Pro handoff package** ✅ — 标准化的交接格式，包含 living_spec + quality_report + density_gate + semantic_anchors

---

## 总结

DeepFlow 的三个域各自内部工程化程度较高（状态管理、质量门控、断点续跑、多层验证），但**域间桥接是最大短板**。核心问题：

1. **无自动化全流程入口** — 三个域像三个独立工具，需要人工串联
2. **Spec Pro → Solution Pro 桥接脆弱** — 依赖主 Agent 正确传递 `living_spec`，忘记传则静默降级
3. **跨域可观测性缺失** — 无法追踪一个需求从产生到交付的完整路径

**建议优先级**: 先修 P0（自动发现 handoff package + 修复 EntryHarness），再建 P1（全流程入口 + trace ID），最后补 P2/P3。
