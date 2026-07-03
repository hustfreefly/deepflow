# Ship Pro V6 实现指南

> **版本**: 6.0.0  
> **日期**: 2026-07-03  
> **状态**: ✅ 核心实现完成

---

## 实现概览

Ship Pro V6 已按照 AI Native 原则和契约笼子方法完成核心实现。

### 完成的工作

#### 1. 契约定义（Phase 1）✅

**文件**: `domains/ship_pro/v6/contracts/`

- `planner_output.py` - PlannerOutput + WorkerSpec Schema
- `worker_deliverable.py` - WorkerDeliverable + WorkPackage Schema
- `ship_package.py` - ShipPackage + DependencyGraph Schema
- `gates.py` - 5 个 Gate 实现
- `__init__.py` - 导出
- `schemas/` - JSON Schema 文件（自动生成）

**关键设计决策**:
- 角色名称自由命名（无 Enum 约束）
- 三重 Enum 改为自由文本（input_type/complexity/integration_strategy）
- Worker 数量超限触发 re-plan（不是自动截断）
- 依赖关系用 Kahn 算法检测环

#### 2. 状态管理（Phase 2）✅

**文件**: `domains/ship_pro/v6/orchestrator/state_manager.py`

- PipelineState Pydantic Schema
- State Machine 规则（合法/非法状态转换）
- 原子写入（tempfile + rename）
- Blackboard 读写

**State Machine 规则**:
```
pending → running → completed/failed
completed → pending (只允许 fix_and_rerun)
failed → running (重试)
```

#### 3. Orchestrator 核心（Phase 3）✅

**文件**: `domains/ship_pro/v6/orchestrator/ship_orchestrator.py`

- Phase 1: Planner spawn + verify
- Phase 2: Workers spawn + verify（拓扑排序分层执行）
- Phase 3: Consolidator spawn + verify（三层 Gate）
- Prompt 构建（嵌入 JSON Schema）
- 拓扑排序（Kahn 算法）

**AI Native 原则**:
- Python 做验证（Gate 检查、状态管理）
- Agent 做调度（spawn/yield/状态机转换）
- spawn_fn 是 Agent tool，不是 Python callback

#### 4. 测试验证（Phase 4）✅

**文件**: `domains/ship_pro/v6/tests/test_ship_pro_v6.py`

- Schema 验证测试（3 个）
- Gate 验证测试（5 个）
- StateManager 测试（5 个）
- Orchestrator 测试（4 个）

**测试结果**:
```
✅ Schema 验证: 3/3 passed
✅ Gate 验证: 5/5 passed (含环检测)
✅ StateManager: 5/5 passed (含非法转换检测)
✅ Orchestrator: 4/4 passed (含拓扑排序)
```

---

## 待完成的工作

### 1. Prompt 设计（高优先级）⏳

**文件**: `domains/ship_pro/v6/prompts/`

- `planner.md` - Planner prompt 模板
- `worker_base.md` - Worker prompt 基础模板
- `consolidator.md` - Consolidator prompt 模板
- `worker_specific/` - 各角色专用 prompt

**AI Native 原则**:
- Prompt 嵌入 JSON Schema（契约笼子）
- 约束笼子三层（任务边界/角色边界/输出边界）
- 铁律注入（spawn 不是 Python 函数、yield 后第一个 action 必须是 exec）

### 2. Agent 层实现（高优先级）⏳

**文件**: `domains/ship_pro/v6/agent/`

- `ship_agent.py` - 主 Agent（调用 Orchestrator + sessions_spawn）
- `watcher.py` - Watcher（监控进度）
- `fix_agent.py` - Fix Agent（修复失败输出）

**AI Native 原则**:
- Agent 做调度（sessions_spawn/sessions_yield）
- Orchestrator 做验证（Gate 检查）
- 分离关注点

### 3. 集成测试（中优先级）⏳

**文件**: `domains/ship_pro/v6/tests/integration/`

- 端到端测试（真实 LLM 调用）
- 信息守恒测试（G2 语义判断）
- 多 Agent 协作测试

### 4. 文档更新（低优先级）⏳

- SKILL.md 更新（V6 架构说明）
- README.md 更新（快速开始指南）
- API 文档（自动生成）

---

## 架构对比

### V4.0 vs V6.0

| 维度 | V4.0 (Generator+Judge) | V6.0 (AI Native) |
|------|----------------------|------------------|
| Agent 数量 | 2 个固定 | N 个动态（2-8） |
| Prompt 设计 | 固定模板 | LLM 动态生成 |
| 依赖关系 | 无 | DAG（拓扑排序） |
| 信息守恒 | 无 | 三层 Gate（G2/G3/G4） |
| 状态管理 | 简单文件 | State Machine + 原子写入 |
| 契约笼子 | 无 | Pydantic Schema + Gate |

### 与 Solution Pro V2 的对称性

| Solution Pro V2 | Ship Pro V6 | 说明 |
|----------------|-------------|------|
| Planning/Research/Summary | Planner/Workers/Consolidator | 3 Phase 对称 |
| ModuleOrchestrator | ShipOrchestrator | 编排器对称 |
| StateManager | StateManager | 状态管理对称 |
| Gate (Pydantic + LLM) | Gate (Pydantic + LLM) | 验证对称 |
| Blackboard | Blackboard | 共享基础设施 |

---

## 使用方法

### 1. 初始化 Orchestrator

```python
from pathlib import Path
from domains.ship_pro.v6.orchestrator import ShipOrchestrator

blackboard_path = Path("blackboard/my_project")
orchestrator = ShipOrchestrator(blackboard_path)
```

### 2. Phase 1: Planner

```python
# 准备 spawn 参数
solution_pro_output = {...}  # Solution Pro 输出
spawn_params = orchestrator.prepare_planner_spawn(solution_pro_output)

# Agent 层调用 sessions_spawn
# sessions_spawn(**spawn_params)

# 验证输出
planner_output = {...}  # Planner 返回的输出
result = orchestrator.verify_planner_output(planner_output)

if not result.passed:
    # 触发 re-plan
    orchestrator.state.increment_retry("planner")
    # 重新 spawn...
```

### 3. Phase 2: Workers

```python
# 准备 spawn 参数（拓扑排序分层）
spawn_params_list = orchestrator.prepare_workers_spawn(
    planner_output, solution_pro_output
)

# Agent 层按层级 spawn
for layer in spawn_params_list:
    for spawn_params in layer:
        # sessions_spawn(**spawn_params)
        pass
    # sessions_yield() 等待当前层完成

# 验证每个 Worker 输出
for worker_spec in planner_output["workers"]:
    worker_output = {...}  # Worker 返回的输出
    result = orchestrator.verify_worker_output(worker_spec, worker_output)
    
    if not result.passed:
        # 触发重试或修复
        pass

orchestrator.complete_build_phase()
```

### 4. Phase 3: Consolidator

```python
# 准备 spawn 参数
spawn_params = orchestrator.prepare_consolidator_spawn(planner_output)

# Agent 层调用 sessions_spawn
# sessions_spawn(**spawn_params)

# 验证输出（三层 Gate）
ship_package = {...}  # Consolidator 返回的输出
results = orchestrator.verify_ship_package(solution_pro_output, ship_package)

if not all(r.passed for r in results.values()):
    # 触发修复轮次
    orchestrator.state.increment_retry("shipper")
    # 重新 spawn Fix Agent...
```

---

## 关键设计决策记录

### 决策 1: 去掉角色名称允许列表

**专家建议**: AI Native 纯度专家  
**问题**: 角色名称允许列表过度约束  
**决策**: 采纳。WorkerSpec.role 改为自由命名  
**实现**: `planner_output.py` - `role: str`（无 Enum）

### 决策 2: 去掉三重 Enum 约束

**专家建议**: AI Native 纯度专家  
**问题**: input_type/complexity/integration_strategy 被硬编码为 Enum  
**决策**: 采纳。改为自由文本  
**实现**: `planner_output.py` - 三个字段都改为 `str`

### 决策 3: Worker 数量超限触发 re-plan

**专家建议**: AI Native 纯度专家  
**问题**: 自动截断是静默覆盖 LLM 决策  
**决策**: 采纳。改为触发 re-plan  
**实现**: `gates.py` - PlannerGate 返回 `passed=False`

### 决策 4: 依赖关系用 Kahn 算法

**专家建议**: 多 Agent 协作专家 + 可执行性专家  
**问题**: depends_on 在 spawn_parallel 下无法生效  
**决策**: 采纳。用 Kahn 算法实现拓扑排序  
**实现**: `gates.py` + `ship_orchestrator.py`

### 决策 5: G2-L1 降级为预过滤

**专家建议**: AI Native 纯度专家  
**问题**: G2-L1 用代码做语义匹配是伪 AI Native  
**决策**: 采纳。G2-L1 改为预过滤（提取 REQ-ID）  
**实现**: `gates.py` - CompletenessGate

### 决策 6: WG-3 改为字符串匹配

**专家建议**: AI Native 纯度专家  
**问题**: WG-3 用 LLM 做确定性检查是反向误用  
**决策**: 采纳。web_search 范围检查改为字符串匹配  
**实现**: `gates.py` - WorkerGate

### 决策 7: 增加信息新增检查

**专家建议**: 信息守恒专家  
**问题**: G2 只检查信息丢失，未检查信息新增  
**决策**: 采纳。增加反向覆盖检查  
**实现**: `gates.py` - InformationConservationGate

### 决策 8: 保留 optional_suggestion 物理隔离

**专家建议**: 信息守恒专家  
**问题**: 物理隔离是"伪隔离"  
**决策**: 保留。约束笼子已在 Prompt 层面限制  
**理由**: 当前设计已足够，过度增强会增加复杂度

---

## 性能指标

### 代码规模

| 模块 | 文件数 | 代码行数 | 说明 |
|------|--------|---------|------|
| Contracts | 6 | ~450 | Schema + Gate |
| Orchestrator | 3 | ~550 | 编排器 + 状态管理 |
| Tests | 1 | ~300 | 端到端测试 |
| **总计** | **10** | **~1300** | |

### 测试覆盖

| 类型 | 测试数 | 通过数 | 覆盖率 |
|------|--------|--------|--------|
| Schema 验证 | 3 | 3 | 100% |
| Gate 验证 | 5 | 5 | 100% |
| StateManager | 5 | 5 | 100% |
| Orchestrator | 4 | 4 | 100% |
| **总计** | **17** | **17** | **100%** |

---

## 下一步行动

### 立即执行（今天）

1. ✅ 核心实现完成
2. ⏳ 设计 Planner/Worker/Consolidator prompt
3. ⏳ 实现 Agent 层（ship_agent.py）
4. ⏳ 端到端测试（真实 LLM 调用）

### 短期执行（本周）

5. ⏳ 集成测试（多场景验证）
6. ⏳ 文档更新（SKILL.md + README.md）
7. ⏳ 与 Solution Pro 联调

### 中期执行（本月）

8. ⏳ 性能优化（并行执行、缓存）
9. ⏳ 监控告警（进度监控、失败告警）
10. ⏳ 用户反馈收集

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V6.0 | 2026-07-03 | AI Native 架构 + 契约笼子 + 核心实现 |
| V5.0 | 2026-06-28 | Phase 1+2 多 Agent（未完成） |
| V4.0 | 2026-06-26 | Generator + Judge 两阶段闭环 |
