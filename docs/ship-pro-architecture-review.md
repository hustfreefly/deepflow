# Ship Pro 架构评审报告

> **评审日期**: 2026-07-29  
> **评审人**: 架构评审专家 (Subagent)  
> **评审范围**: Ship Pro V3.0 内部架构 + 上下游接口 + 缺失文件影响  
> **对标系统**: Solution Pro V4.0, Deliver Pro

---

## 一、架构总览

### Ship Pro V3.0 管线

```
Solution Pro (上游)
  └─ frozen_spec.json / frozen_spec.md
  └─ solution_document.json
        │
        ▼
Ship Pro (本系统)
  ├─ Orchestrator (depth-1, 薄层调度)
  │   ├─ Phase 1: Designer → pipeline_plan.json
  │   ├─ Phase 2: Workers (并行) → worker_{role}.json
  │   ├─ Phase 3: Consolidator → ship_package.json
  │   └─ Phase 4: Report
  │
        ▼
Deliver Pro (下游)
  └─ 读取 ship_package.json → 逐 WP 执行
```

### 内部组件

| 组件 | 角色 | 实现方式 | Prompt 文件 |
|------|------|----------|------------|
| Orchestrator | 状态机驱动调度 | exec + sessions_spawn | `orchestrator.md` ✅ |
| Designer | 拆分 Worker 角色 + 生成 PipelinePlan | 子 Agent (spawn) | `designer_module.md` ❌ **缺失** |
| Workers | 按角色生成 Work Packages | 子 Agent (并行 spawn) | `worker_module.md` ❌ **缺失** |
| Consolidator | 合并 WP → ShipPackage | 子 Agent (spawn) | `consolidator.md` ✅ |

---

## 二、问题清单

### 🔴 P0 — 阻塞性问题（必须立即修复）

#### P0-1: `designer_module.md` 缺失 — Designer 阶段无法启动

**现象**:
- `orchestrator.md` Step 1a 调用 `render_prompt('domains/ship_pro/prompts/designer_module.md', ...)`
- 该文件不存在于 `prompts/` 目录
- 目录中只有 `orchestrator.md` 和 `consolidator.md` 两个文件

**影响**:
- Orchestrator 执行到 Step 1a 时，`render_prompt` 会抛异常或返回空内容
- Designer 子 Agent 收到的 prompt 文件不存在 → 写入 `.failed` → 整个管线终止
- **Ship Pro 完全无法运行**

**根因分析**:
- SKILL.md 中 `prompts/` 目录树只列出 `consolidator.md`，说明 designer_module.md 从未被创建
- 但 `__init__.py` 中有 `design_pipeline()` 函数（Python 实现），说明 Designer 逻辑存在于 Python 层而非 prompt 层
- V3.0 重构将 Designer 从 Python exec 改为 spawn 子 Agent，但忘记创建对应的 prompt 文件

**修复建议**:
1. 创建 `domains/ship_pro/prompts/designer_module.md`，内容应包含：
   - 读取 `solution_pro_input.json`（frozen_spec + supplemental）
   - 分析需求领域，决定 Worker 拆分策略
   - 输出 `pipeline_plan.json`（workers 列表 + execution order + rationale）
   - 遵循 `PlannerOutput` Pydantic Schema
2. 参考 Solution Pro 的 `planning_module.md`（31KB）作为模板
3. 确保 prompt 中包含 `semantic_anchors` 透传要求

**优先级**: 🔴 P0 — 没有此文件 Ship Pro 无法启动

---

#### P0-2: `worker_module.md` 缺失 — Worker 阶段无法启动

**现象**:
- `orchestrator.md` Step 2b 调用 `render_prompt('domains/ship_pro/prompts/worker_module.md', worker_role=role)`
- 该文件不存在

**影响**:
- 即使 Designer 阶段通过（假设 P0-1 已修复），Worker 阶段也会失败
- 每个 Worker 角色的 prompt 都无法生成
- **Ship Pro 完全无法运行**

**根因分析**:
- SKILL.md 描述了 Worker prompt 的 6 段式结构（~2.5KB），但这是 Python `prepare_runner_spawn()` 动态生成的
- V3.0 改为 `render_prompt` 模板方式，但模板文件未创建
- `__init__.py` 中 `prepare_runner_spawn()` 仍有完整的 Python 实现（可作为内容来源）

**修复建议**:
1. 创建 `domains/ship_pro/prompts/worker_module.md`，包含 6 段式结构：
   - 角色 + 数据流
   - 模块概述
   - 需求 + 架构约束 + 隐含约束
   - 接口契约（provides / requires / downstream）
   - 输出规范 + 紧凑示例
   - 反模式护栏
2. 使用 `{worker_role}` 模板变量进行角色注入
3. 从 `prepare_runner_spawn()` 的 Python 代码提取现有逻辑作为 prompt 内容基础

**优先级**: 🔴 P0 — 没有此文件 Ship Pro 无法运行

---

### 🟡 P1 — 重要问题（影响可靠性/可维护性）

#### P1-1: 缺少智能重试机制（与 Solution Pro V4.1 不对齐）

**现象**:
- Ship Pro orchestrator: 模块 MISSING → 直接写 `.failed`，无重试
- Solution Pro orchestrator V4.1: 模块 MISSING → 智能重试 2 次（30s + 60s）→ 仍失败才 `.failed`

**影响**:
- 瞬时故障（子 Agent 超时、文件写入延迟）导致整个管线失败
- 需要用户手动重新触发，体验差
- 与 Solution Pro 的容错能力差距大

**修复建议**:
- 在 orchestrator.md 的验证步骤（1d/2e/3d）中增加智能重试逻辑
- 参考 Solution Pro 的 `RETRY_{MODULE}` 状态和 `retry_count` 机制
- 保持 `FAILED` 终态语义不变（重试耗尽后才进入）

---

#### P1-2: Designer 阶段存在 Python/Agent 双重实现，职责不清

**现象**:
- `__init__.py` 有 `design_pipeline()` Python 函数（调用 `PipelineDesigner` 类）
- `orchestrator.md` V3.0 改为 spawn Designer 子 Agent（读 `designer_module.md`）
- 两套实现并存，不知道哪套是实际执行的

**影响**:
- 维护成本高，修改一处容易忘记另一处
- 可能导致行为不一致（Python 版和 Agent 版产出格式不同）
- 新人难以理解实际执行路径

**修复建议**:
- 明确 V3.0 的 Designer 实现方式：是 Python exec 还是 Agent spawn？
- 如果是 Agent spawn → 创建 `designer_module.md`，废弃 `design_pipeline()` Python 入口
- 如果保留 Python exec → 修改 orchestrator.md 不再引用 `designer_module.md`
- 推荐：统一为 Agent spawn（与 Solution Pro 架构对齐）

---

#### P1-3: Worker 阶段的 expected_files 动态构建逻辑复杂且脆弱

**现象**:
```python
# orchestrator.md Step 2d
expected_files = [
    f'stages/worker_outputs/worker_{role.replace(" ", "_")}.json' 
    for role in roles
]
```
- 文件名依赖 `role` 字符串的空格替换
- 如果 Designer 输出的 role 包含特殊字符（`/`, `-`, `.`），文件名可能冲突
- `wait_for_module` 用文件名匹配，不检查文件内容是否对应该 role

**影响**:
- 角色名含特殊字符时文件路径错误 → wait_for 超时
- 两个角色名 normalize 后相同时文件覆盖（如 "Core Infra" 和 "Core_Infra"）

**修复建议**:
- 在 PipelinePlan Schema 中约束 role 命名规则（只允许 `[a-zA-Z0-9_]`）
- 或在文件命名中使用 role 的 hash/ID 而非原始名称
- 在 Worker 输出中增加 `role` 字段，wait_for 时验证内容而非仅文件名

---

#### P1-4: ShipPackage 输出路径不一致

**现象**:
- Consolidator prompt 写 `{output_path}`（运行时注入的绝对路径）
- Orchestrator 等待 `stages/ship_package.json`
- Deliver Pro 搜索 3 个路径：
  1. `ship_pro/ship_package.json`（传统）
  2. `ship_pro/stages/ship_package.json`（当前）
  3. 其他 fallback

**影响**:
- 如果 Consolidator 写入路径与 Orchestrator 等待路径不一致 → 超时
- Deliver Pro 的多路径搜索是 workaround，说明历史上路径变更多次

**修复建议**:
- 统一为单一权威路径：`stages/ship_package.json`（相对于 session_dir）
- 在 Consolidator prompt 中硬编码此路径（不用运行时注入）
- Deliver Pro 只搜索此路径，移除 fallback

---

### 🟢 P2 — 改进建议

#### P2-1: 缺少 L2 LLM Judge 验证（Worker 阶段）

**现象**:
- SKILL.md 提到 "L2 LLM Judge 语义验证（待实现）"
- 当前 WorkerGate 只有 L1 确定性验证（Schema + 内容深度）
- Solution Pro 的 Summary 阶段有完整的 L1+L2+L3 三层验证

**影响**:
- Worker 输出的语义质量（WP 是否真正覆盖需求、AC 是否可测试）无法保证
- Consolidator 阶段的语义整合负担重（需要处理更多低质量输入）

**修复建议**:
- 在 WorkerGate 增加 L2 LLM Judge：
  - 输入：Worker 输出 + 原始需求
  - 判断：WP 描述是否与需求语义对齐、AC 是否可验证
  - 输出：PASS / FAIL + reason

---

#### P2-2: Orchestrator 状态机缺少 RETRY 状态

**现象**:
- Ship Pro 状态机：14 个状态，无 RETRY 状态
- Solution Pro 状态机：有 `RETRY_PLANNING`, `RETRY_RESEARCH`, `RETRY_SUMMARY` 状态

**影响**:
- 无法在状态机层面表达重试逻辑
- 重试逻辑只能写在 exec 代码中，与状态机脱节

**修复建议**:
- 增加 `RETRY_DESIGNER`, `RETRY_WORKERS`, `RETRY_CONSOLIDATOR` 状态
- 与 Solution Pro V4.1 状态机对齐

---

#### P2-3: Consolidator 的 domain_analysis 组装策略依赖不稳定字段

**现象**:
- Consolidator Step 0 从 `pipeline_plan.domain_analysis` 推断组装策略
- `domain_analysis` 字段在 PipelinePlan Schema 中未定义（SKILL.md 未提及）
- 如果 Designer 不输出此字段，fallback 到 deliverables 推断

**影响**:
- 组装策略不稳定，可能每次运行结果不同
- 软件项目可能被当作文档项目处理

**修复建议**:
- 在 `PlannerOutput` Schema 中显式定义 `domain_analysis` 字段
- 或在 Designer prompt 中明确要求输出此字段
- 增加 domain_analysis 的枚举值约束

---

#### P2-4: semantic_anchors 透传链路长，任一环节丢失则下游受损

**现象**:
- Solution Pro → Ship Pro (Designer) → Ship Pro (Workers) → Ship Pro (Consolidator) → Deliver Pro
- 5 个环节，每个都必须原样传递 `semantic_anchors`
- Consolidator 有 MUST 契约笼子，但 Designer 和 Workers 没有

**影响**:
- 如果 Designer 不将 semantic_anchors 写入 pipeline_plan → Workers 不知道要透传
- 如果 Worker 不将 anchored_to 写入 WP → Consolidator 无法计算 anchor_coverage

**修复建议**:
- 在 Designer prompt 中增加 semantic_anchors 透传要求
- 在 Worker prompt 中增加 anchored_to 字段要求
- 在 WorkerGate L1 验证中检查 anchored_to 字段存在性

---

## 三、上下游接口一致性分析

### 3.1 Solution Pro → Ship Pro 接口

| 字段 | Solution Pro 输出 | Ship Pro 输入 | 一致性 |
|------|-------------------|---------------|--------|
| frozen_spec.json | ✅ `data/frozen_spec.json` | ✅ `data/frozen_spec.json` 或 `data/living_spec.json` | ✅ 兼容 |
| solution_document.json | ✅ `stages/solution_document.json` | ⚠️ 未直接引用 | ⚠️ 间接（通过 frozen_spec） |
| semantic_anchors | ✅ 在 solution_pro_input.json 中 | ✅ Orchestrator MUST 契约 | ✅ 有保护 |
| requirements[] | ✅ 标准格式 | ✅ Designer 读取 | ✅ |

**问题**: Ship Pro 的 `solution_pro_input.json` 构建逻辑在 `__init__.py` 的 `build_ship_pro_input()` 中，但 V3.0 orchestrator 直接从 blackboard 读取 `data/frozen_spec.json`，两者可能不一致。

### 3.2 Ship Pro → Deliver Pro 接口

| 字段 | Ship Pro 输出 | Deliver Pro 消费 | 一致性 |
|------|---------------|-----------------|--------|
| work_packages[] | ✅ 完整 WP 对象 | ✅ `_get_wp_data()` 读取 | ✅ |
| wp_id | ✅ `wp_id` 字段 | ✅ 用于目录命名 | ✅ |
| dependency_graph | ✅ edges + execution_layers | ✅ `_get_execution_order()` 优先用 execution_layers | ✅ |
| semantic_anchors | ✅ 在 ShipPackage 顶层 | ✅ `_adapt_ship_pro_wp()` 传递给每个 WP | ✅ |
| anchor_coverage | ✅ 在 ShipPackage 中 | ⚠️ 未见消费代码 | ⚠️ 未使用 |
| statistics | ✅ total_wps, effort_hours 等 | ⚠️ 未见消费代码 | ⚠️ 未使用 |
| status (per WP) | ✅ 固定 "draft" | ✅ Deliver Pro 会更新为 in_progress | ✅ |

**问题**: 
- `anchor_coverage` 和 `statistics` 在 Deliver Pro 中未被消费，属于"生产但不消费"的数据
- Deliver Pro 的 `_adapt_ship_pro_wp()` 适配函数说明 Ship Pro 输出格式与 Deliver Pro 期望格式不完全一致，需要适配层

### 3.3 接口适配层风险

Deliver Pro 有 `_adapt_ship_pro_wp()` 函数，说明两个系统的 WP Schema 存在差异：
- Ship Pro: `WorkPackage` (worker_deliverable.py)
- Deliver Pro: `WorkPackage` (deliver_pro 内部模型)

适配层是必要的，但增加了维护成本。如果 Ship Pro 输出格式变化，适配层需要同步更新。

---

## 四、与 Solution Pro 的对比

| 维度 | Solution Pro V4.0 | Ship Pro V3.0 | 差距 |
|------|-------------------|---------------|------|
| **模块数** | 3 (Planning/Research/Summary) | 3+1 (Designer/Workers/Consolidator+Report) | Ship Pro 多一个并行阶段 |
| **Prompt 文件完整性** | ✅ 所有 module prompt 存在 | ❌ 缺 designer_module.md, worker_module.md | **P0 问题** |
| **状态机** | 有 RETRY 状态 | 无 RETRY 状态 | P2 差距 |
| **智能重试** | ✅ 2 次重试（30s+60s） | ❌ 直接失败 | P1 差距 |
| **验证层** | L1+L2+L3（Summary 阶段） | L1（WorkerGate）+ L1+L2+L3（Consolidator） | 基本对齐 |
| **断点恢复** | ✅ SingleSourceStateManager | ✅ SingleSourceStateManager | ✅ 对齐 |
| **Completion Event** | 忽略（去重） | 忽略（去重） | ✅ 对齐 |
| **执行循环** | EXEC→READ→JUDGE→ACT | EXEC→READ→JUDGE→ACT | ✅ 对齐 |
| **契约笼子** | Pydantic + 文件大小 | Pydantic + 文件大小 + MUST 契约 | ✅ Ship Pro 更强 |

---

## 五、缺失文件影响总结

| 缺失文件 | 被引用位置 | 影响 | 严重程度 |
|----------|-----------|------|----------|
| `designer_module.md` | orchestrator.md Step 1a | Designer 子 Agent 无法启动 → 管线终止 | 🔴 P0 |
| `worker_module.md` | orchestrator.md Step 2b | Worker 子 Agent 无法启动 → 管线终止 | 🔴 P0 |

**关键发现**: 这两个文件的缺失意味着 **Ship Pro V3.0 架构在当前状态下完全无法运行**。任何端到端执行都会在 Phase 1 或 Phase 2 失败。

**可能的解释**:
1. V3.0 重构未完成 — 从 Python exec 模式迁移到 Agent spawn 模式，但 prompt 文件未创建
2. 实际运行使用的是 `__init__.py` 中的 Python 路径（`design_pipeline()` + `prepare_runner_spawn()`），而非 orchestrator.md 描述的 Agent spawn 路径
3. 如果是情况 2，则 orchestrator.md 是"设计文档"而非"执行指令"，但这与 SKILL.md 的描述矛盾

---

## 六、修复优先级建议

### 立即修复（P0，阻塞 E2E）

1. **创建 `designer_module.md`**
   - 从 `pipeline_designer.py` 的 `PipelineDesigner` 类提取逻辑
   - 参考 Solution Pro `planning_module.md` 的结构
   - 包含：输入读取、Worker 拆分策略、PipelinePlan 输出、semantic_anchors 透传

2. **创建 `worker_module.md`**
   - 从 `prepare_runner_spawn()` 的 Python 代码提取 6 段式 prompt 结构
   - 使用 `{worker_role}` 模板变量
   - 包含：角色定义、需求上下文、接口契约、输出 Schema、反模式护栏

### 短期修复（P1，提升可靠性）

3. **增加智能重试机制** — 对齐 Solution Pro V4.1
4. **明确 Designer 实现路径** — Python exec vs Agent spawn 二选一
5. **统一 ShipPackage 输出路径** — 移除 Deliver Pro 的多路径 fallback

### 中期改进（P2，提升质量）

6. **Worker 阶段增加 L2 LLM Judge**
7. **状态机增加 RETRY 状态**
8. **PipelinePlan Schema 增加 domain_analysis 字段**
9. **semantic_anchors 透传链路加固**

---

## 七、结论

Ship Pro V3.0 的架构设计是合理的：
- ✅ Orchestrator 薄层调度 + 状态机驱动
- ✅ Blackboard-based 状态管理
- ✅ 显式执行循环 + 信号路由
- ✅ 断点恢复 + 幂等性保证
- ✅ 与 Solution Pro 架构对齐

**但当前存在 2 个 P0 阻塞性问题**：`designer_module.md` 和 `worker_module.md` 缺失，导致系统完全无法运行。这两个文件必须立即创建，否则 Ship Pro V3.0 只是一个"纸面架构"。

建议修复顺序：P0-1 → P0-2 → P1-1 → P1-2 → P1-3 → P1-4 → P2-*

---

*报告生成时间: 2026-07-29 13:20 GMT+8*  
*评审方法: 文件静态分析 + 上下游接口对比 + 架构模式对照*
