# Ship Pro V7 架构决策书

> **日期**: 2026-07-04
> **评审专家**: 架构评审专家 + Prompt 工程专家 + 多 Agent 编排专家
> **决策者**: 姬忠礼 + 小满
> **参考标杆**: Solution Pro V2 Orchestrator 模式

---

## 一、评审背景

Ship Pro V6 E2E 成功完成（37 WPs, 73/73 REQ-IDs, 3 Gates PASS），但执行过程中暴露两个结构性问题：

1. **主 Agent 充当人肉编排器**：12+ 轮 exec/spawn/yield 交互，上下文污染严重
2. **REQ-ID 追踪本末倒置**：Worker prompt 10% 带宽浪费在确定性追踪任务上

---

## 二、专家共识（3/3 一致）

| # | 议题 | 结论 | AI Native 违规 |
|---|------|------|---------------|
| 1 | REQ-ID 前置追踪 | ❌ 本末倒置，Worker 应专注 WP 质量 | 4.1 违规：确定性任务混入语义任务 |
| 2 | 覆盖度验证 | ✅ 后置 LLM Judge 语义验证 | 4.3 违规：字符串匹配 ≠ 语义验证 |
| 3 | 编排痛点 | 🔴 上下文污染 + 状态机脆弱 + 逻辑隐性化 | 4.2 #7：架构预定义而非自适应 |
| 4 | 纯 Python 编排 | ❌ 不可行（sessions_spawn 硬约束） | — |
| 5 | Worker prompt 效率 | ⚠️ covered_req_ids 是 Low ROI（⭐⭐），应移除 | 4.2 #1：Fake AI Native |

---

## 三、分歧点 + 最终决策

### 分歧 1：是否引入专用 Dispatcher Agent

| 专家 | 立场 | 理由 |
|------|------|------|
| A（架构） | ❌ 不要新层 | "过度工程，违反 Simplicity First" |
| C（编排） | ✅ 引入 Dispatcher | "上下文隔离，流程可编码，Main Agent 解放" |

**最终决策**：✅ **采纳专家 C + 用户意见**

理由：
1. Solution Pro 已验证此模式可行（`run_solution_pro()` → `sessions_spawn(Orchestrator)` → `sessions_yield()`）
2. Main Agent 职责最小化 = 用户明确要求
3. 上下文隔离解决 V6 最严重的污染问题

### 分歧 2：ShipOrchestrator Python 类的定位

| 专家 | 立场 | 理由 |
|------|------|------|
| A（架构） | 降级为状态跟踪器 | "Python 做确定性工作" |
| C（编排） | 保留为工具库 | "Dispatcher 调用其 prepare/verify 方法" |

**最终决策**：✅ **降级为纯工具库**

- 保留 `prepare_planner_spawn()`, `prepare_workers_spawn()`, `prepare_consolidator_spawn()`
- 保留 `verify_planner_output()`, `verify_worker_output()`, `verify_ship_package()`
- 保留 `write_stage()`, `read_stage()`
- **移除**状态机控制逻辑（状态转换由 Dispatcher Agent 自主决定）

---

## 四、V7 架构设计

### 4.1 参考标杆：Solution Pro 模式

```
Solution Pro 实际代码流程：

Main Agent (depth-0):
  1. exec python: result = run_solution_pro(user_input="...", topic="...")
     → Python 内部：初始化 Blackboard、读取 orchestrator.md 模板、填充变量
     → 返回 { session_id, spawn_params: { runtime, mode, label, task } }
  
  2. sessions_spawn(**result["spawn_params"])
     → 启动 Orchestrator 子 Agent (depth-1)
  
  3. sessions_yield()
     → 等待 Orchestrator 完成，收到最终结果

Orchestrator 子 Agent (depth-1):
  → 读取自己的 task prompt（包含完整 pipeline 指令）
  → 自主执行：Planning → Research → Summary
  → 完成后自动回报 Main Agent
```

### 4.2 Ship Pro V7 采用相同模式

```
Main Agent (depth-0):
  1. exec python: result = run_ship_pro(solution_pro_output_path="...")
     → Python 内部：初始化 Blackboard、读取 ship_dispatcher.md 模板、填充变量
     → 返回 { session_id, spawn_params: { runtime, mode, label, task } }
  
  2. sessions_spawn(**result["spawn_params"])
     → 启动 ShipDispatcher 子 Agent (depth-1)
  
  3. sessions_yield()
     → 等待 ShipDispatcher 完成，收到 ShipPackage

ShipDispatcher 子 Agent (depth-1):
  → 读取自己的 task prompt（包含完整 pipeline 指令）
  → 自主执行：Planner → Workers → Judges → Consolidator → Gates
  → 完成后自动回报 Main Agent（含 ShipPackage + Gate 结果）
```

### 4.3 ShipDispatcher 完整 Prompt 设计

```markdown
# Ship Pro V7 Dispatcher

你是 Ship Pro V7 的专用调度 Agent。你的唯一职责：编排完整的 Ship Pipeline。

## 核心约束
1. 你是唯一的编排者。你通过 sessions_spawn 调度所有子 Agent
2. Python(ShipOrchestrator) 只提供 prepare/verify 方法，不做调度决策
3. 所有语义验证由你 spawn 的 Judge 子 Agent 完成
4. 状态通过 Blackboard 文件持久化（pipeline_state.json）

## 执行流程

### Phase 0: 初始化
```bash
exec python: 
  import sys; sys.path.insert(0, '.')
  from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
  orch = ShipOrchestrator(Path("{blackboard_path}"))
```

### Phase 1: Planner
1. `exec python: params = orch.prepare_planner_spawn(solution_input)`
2. `sessions_spawn(**params)` → `sessions_yield()`
3. 收到 Planner 输出后：`exec python: gate = orch.verify_planner_output(planner_output, solution_input)`
4. 如果 `gate.passed == False`：
   - 分析 issues
   - 决定是否重试（最多 1 次）
   - 仍失败 → 记录问题，继续（降级）

### Phase 2: Build（Workers 并行）
1. `exec python: params_list = orch.prepare_workers_spawn(planner_output, solution_input)`
2. 对每个 params：`sessions_spawn(**params)` → `sessions_yield()`
3. 收集所有 Worker 输出
4. `exec python: judge_tasks = orch.prepare_worker_judge_tasks(planner_output, worker_outputs)`
5. 对每个 judge_task：`sessions_spawn(task=judge_task["prompt"])` → `sessions_yield()`
6. 收集 Judge 结果
7. `exec python: result = orch.verify_worker_output(spec, output, judge_results=...)`
8. 失败 Worker → 只重试该 Worker（最多 1 次）

### Phase 3: Consolidate
1. `exec python: params = orch.prepare_consolidator_spawn(planner_output)`
2. `sessions_spawn(**params)` → `sessions_yield()`
3. 收到 ShipPackage
4. `exec python: judge_tasks = orch.prepare_gate_judge_tasks(solution_input, ship_package)`
5. spawn Gate Judges → yield → 收集结果
6. `exec python: results = orch.verify_ship_package(solution_input, ship_package, planner_output, judge_results)`

### Phase 4: 输出
向 Main Agent 回报：
1. ShipPackage（完整 JSON）
2. 所有 Gate 结果汇总（pass/fail + issues）
3. pending_req_ids（延迟需求列表）
4. 执行摘要（WPs 数量、REQ 覆盖率、重试记录）

## 错误恢复策略
| 场景 | 策略 |
|------|------|
| Planner Gate 失败 | 重试 1 次，仍失败则降级继续 |
| Worker Gate 失败 | 只重试失败的 Worker，1 次 |
| Consolidator Gate 失败 | 分析原因，回退到 Build 或降级 |
| StateTransitionError | 读取 pipeline_state.json，跳过已完成阶段 |
| 子 Agent 超时 | 记录超时，继续后续阶段 |

## 状态管理
- 每个阶段完成后：`exec python: orch.state_manager.write_stage(name, data)`
- 状态转换：`exec python: orch.state_manager.update_stage(name, status)`
- 如果遇到 StateTransitionError：先 `read_stage()` 检查当前状态，再决定操作
```

### 4.4 Worker Prompt 改进

```diff
  V6（~10800 字符）：
  ├─ 角色定义（5%）
  ├─ 任务描述（10%）
  ├─ MUST 约束（15%）
- ├─ covered_req_ids 列表（10%）← 移除
  ├─ 输出格式（20%）
  └─ Solution Pro 数据（35%）

  V7（~9000 字符，-17%）：
  ├─ 角色定义 + 质量优先级锚定（8%）← 强化
  ├─ 任务描述 + 成功标准（15%）← 强化
  ├─ MUST 约束（18%）
  ├─ 关键数据高亮（40%）← 强化
  ├─ 输出格式（15%）← 精简
  └─ wp_id_prefix（4%）
```

### 4.5 CompletenessGate 改为 LLM-as-Judge

```
V6（字符串匹配）：
  for wp in worker_outputs:
    covered.update(wp.get("covered_req_ids", []))
  return covered == set(all_req_ids)

V7（LLM-as-Judge）：
  spawn Judge Agent:
    "阅读所有 {N} 个 WPs 和 {M} 个原始需求。
     判断：每个需求是否被至少一个 WP 语义覆盖？
     输出：覆盖率 + 未覆盖需求列表 + 覆盖度矩阵"
```

---

## 五、实施计划

### Step 1: Python 入口 `run_ship_pro()`

参考 `domains/solution_pro/__init__.py` 的 `run_solution_pro()`：
- 初始化 Blackboard
- 读取 `ship_dispatcher.md` 模板
- 填充 `{blackboard_path}`, `{solution_pro_input_path}` 等变量
- 返回 `{ session_id, spawn_params }`

### Step 2: ShipDispatcher Prompt 模板

- 文件：`domains/ship_pro/prompts/ship_dispatcher.md`
- 包含上述 4.3 的完整 Prompt 设计
- 变量占位符：`{blackboard_path}`, `{solution_pro_input_path}`

### Step 3: Worker Prompt 重构

- 移除 `covered_req_ids` 列表
- 增加质量优先级锚定
- 精简输出格式 Schema

### Step 4: CompletenessGate LLM Judge

- 新增 `prepare_completeness_judge_task()` 方法
- 生成语义覆盖度验证 prompt
- Dispatcher spawn Judge 子 Agent 执行

### Step 5: ShipOrchestrator 降级

- 移除状态机硬编码控制
- 保留 prepare/verify/write/read 方法
- 状态转换由 Dispatcher Agent 自主调用

### Step 6: E2E 验证

- 使用同一份 Solution Pro 输入
- Main Agent 只做 3 步：`run_ship_pro()` → `sessions_spawn()` → `sessions_yield()`
- 验证 ShipPackage 质量 ≥ V6

---

## 六、预期效果

| 指标 | V6 | V7 预期 | 变化 |
|------|----|---------|------|
| Main Agent 交互轮数 | 12+ | 3 | -75% |
| Worker prompt 长度 | ~10800 字符 | ~9000 字符 | -17% |
| WP 质量（预估） | baseline | +15-25% | 注意力集中 |
| 覆盖度验证准确性 | 字符串匹配 | 语义匹配 | 质的提升 |
| 状态管理错误 | 频繁 StateTransitionError | 自修复 | 消除 |

---

*决策文档版本: V1.0 | 2026-07-04*
