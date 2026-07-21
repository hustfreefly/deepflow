# DeepFlow Orchestrator 命名规范提案

> 调研日期: 2026-07-21
> 范围: Solution Pro / Ship Pro / Deliver Pro 三层架构命名

---

## 一、现状调研

### 1.1 Solution Pro 架构

```
Main Agent (depth-0)
  └─ run_solution_pro() → spawn_params
      └─ Orchestrator Agent (depth-1, LLM)  ← L1: 薄层调度器
          ├─ Planning Module Agent (depth-2, LLM)  ← L2
          │   ├─ Meta Planner (depth-3)
          │   ├─ Expert Planners ×N (depth-3)
          │   └─ Convergence Planner (depth-3)
          ├─ Research Module Agent (depth-2, LLM)  ← L2
          │   ├─ Research Experts ×N (depth-3)
          │   └─ Convergence (depth-3)
          └─ Summary Module Agent (depth-2, LLM)  ← L2
              ├─ Synthesizer (depth-3)
              └─ JSON Extractor (depth-3)
```

**命名现状**:

| 层级 | 组件 | 类型 | 命名 | 问题 |
|:---:|:---|:---:|:---|:---|
| L1 | `orchestrator.md` | LLM Prompt | Orchestrator | ✅ OK |
| L1 | (无 Python 类) | Python | — | ⚠️ 无对应 |
| L2 | `planning_module.md` | LLM Prompt | Planning Module Agent | ✅ OK |
| L2 | `research_module.md` | LLM Prompt | Research Module Agent | ✅ OK |
| L2 | `summary_module.md` | LLM Prompt | Summary Module Agent | ✅ OK |
| 支撑 | `task_builder.py` | Python | validate_stage_output | ✅ OK |
| 支撑 | `post_validator.py` | Python | validate_solution_output | ✅ OK |
| 支撑 | `information_conservation.py` | Python | InformationConservationValidator | ✅ OK |

**特点**: L1 是纯 LLM Agent（无 Python Orchestrator 类），Module Agent 内部管理 Worker。

---

### 1.2 Ship Pro 架构

```
Main Agent (depth-0)
  └─ run_ship_pro() → spawn_params
      └─ Dispatcher Agent (depth-1, LLM)  ← L1: 薄层调度器
          ├─ Planner Agent (depth-2, LLM)  ← L2: Pipeline 设计
          ├─ Worker Architects ×N (depth-2, LLM)  ← L2: 并行 WP 生成
          └─ Consolidator Agent (depth-2, LLM)  ← L2: 合并产出
```

**命名现状**:

| 层级 | 组件 | 类型 | 命名 | 问题 |
|:---:|:---|:---:|:---|:---|
| L1 | `ship_orchestrator.py` | Python | **ShipOrchestrator** | ⚠️ 是 Python 类不是 LLM Agent |
| L1 | Dispatcher prompt (在 `__init__.py`) | LLM | Dispatcher | ⚠️ 与 Solution Pro "Orchestrator" 不一致 |
| L2 | Planner (spawn by Dispatcher) | LLM | Planner | ✅ OK |
| L2 | Worker Architects (spawn by Dispatcher) | LLM | Worker | ✅ OK |
| L2 | Consolidator (spawn by Dispatcher) | LLM | Consolidator | ✅ OK |
| 支撑 | `pipeline_designer.py` | Python | PipelineDesigner | ✅ OK |
| 支撑 | `conservation_judge.py` | Python | run_conservation_judge | ✅ OK |
| 支撑 | `state_manager.py` | Python | StateManager | ✅ OK |

**特点**: Python `ShipOrchestrator` 做 spawn 准备 + 验证，LLM Dispatcher 做调度。L1 的 Python 类和 LLM Agent 用了不同名字（ShipOrchestrator vs Dispatcher）。

---

### 1.3 Deliver Pro 架构

```
Main Agent (depth-0)
  └─ run_deliver_pro() → BatchDriver.drive_all()
      └─ BatchDriver (Python)  ← L1: 薄层调度器（多 WP 分层驱动）
          └─ 对每个 WP:
              └─ DeliverProDriver (Python)  ← L2: 单 WP Phase 驱动
                  └─ DeliverProOrchestrator (Python)  ← L2 支撑: 单 WP 状态管理
                      ├─ Analyze Agent (depth-1, LLM)  ← L3
                      ├─ Workers ×N (depth-1, LLM)  ← L3
                      ├─ Validate Agent (depth-1, LLM)  ← L3
                      └─ Package Agent (depth-1, LLM)  ← L3
```

**命名现状**:

| 层级 | 组件 | 类型 | 命名 | 问题 |
|:---:|:---|:---:|:---|:---|
| L1 | `batch_driver.py` | Python | **BatchDriver** | 🔴 不像 Orchestrator |
| L2 | `driver.py` | Python | **DeliverProDriver** | ⚠️ "Driver" 含义模糊 |
| L2 支撑 | `orchestrator.py` | Python | **DeliverProOrchestrator** | 🔴 不是 L1 却叫 Orchestrator |
| L3 | `deliver_analyze.md` | LLM | Analyze Agent | ✅ OK |
| L3 | `deliver_worker_base.md` | LLM | Worker | ✅ OK |
| L3 | `deliver_validate.md` | LLM | Validate Agent | ✅ OK |
| L3 | `deliver_package.md` | LLM | Package Agent | ✅ OK |
| 支撑 | `smart_assembler.py` | Python | SmartAssembler | ✅ OK |
| 支撑 | `state_manager.py` | Python | DeliverProStateManager | ✅ OK |
| 支撑 | `failure_recovery.py` | Python | WorkerFailureRecovery | ✅ OK |

**特点**:
- L1 (`BatchDriver`) 是纯 Python 代码（无 LLM Agent），确定性驱动多 WP 分层执行
- L2 (`DeliverProDriver`) 是 Python 薄层封装，调 Orchestrator 的方法
- L2 支撑 (`DeliverProOrchestrator`) 做实际工作（准备 spawn params、验证输出、状态转换）
- **命名冲突**: "Orchestrator" 被 L2 支撑占用了，L1 反而叫 "Driver"

---

## 二、问题总结

### 2.1 跨域命名不一致

| 概念 | Solution Pro | Ship Pro | Deliver Pro |
|:---|:---|:---|:---|
| **L1 调度器 (LLM)** | Orchestrator | Dispatcher | (无 LLM Agent) |
| **L1 调度器 (Python)** | (无) | ShipOrchestrator | BatchDriver |
| **L2 执行者 (LLM)** | Module Agent | Planner / Worker / Consolidator | (无 L2 LLM Agent) |
| **L2 执行者 (Python)** | (无) | (无) | DeliverProDriver |
| **L2 支撑 (Python)** | task_builder | PipelineDesigner | DeliverProOrchestrator |

### 2.2 三个核心问题

1. **Solution Pro L1 叫 "Orchestrator"，Ship Pro L1 叫 "Dispatcher"** → 同一个角色不同名
2. **Deliver Pro L1 叫 "BatchDriver"，L2 支撑却叫 "Orchestrator"** → 层级倒挂
3. **Solution Pro 无 Python Orchestrator，Ship Pro 有，Deliver Pro 有两个** → 架构差异导致命名混乱

---

## 三、统一命名规范（提案）

### 3.1 命名原则

```
层级定义:
  L0 = Main Agent（入口函数）
  L1 = 域级调度器（决定"做什么、什么顺序"）
  L2 = 模块/阶段执行者（实际做语义工作）
  L3 = 任务级 Worker（最底层的实际执行者）

命名规则:
  L1 Python 类 → {Domain}Orchestrator
  L1 LLM Agent → {Domain}Orchestrator (或 prompt 中叫 "薄层调度器")
  L2 Python 类 → {Domain}{Role} (具体角色名，不用 Orchestrator)
  L2 LLM Agent → {Domain}{Module}Agent
  L3 LLM Agent → {Domain}Worker 或 {Phase}Agent

禁止:
  ❌ L2 或更低层级使用 "Orchestrator" 命名
  ❌ 同一层级用不同术语（如 Orchestrator vs Dispatcher vs Driver）
```

### 3.2 统一后对照表

| 概念 | Solution Pro | Ship Pro | Deliver Pro |
|:---|:---|:---|:---|
| **L0 入口** | `run_solution_pro()` | `run_ship_pro()` | `run_deliver_pro()` |
| **L1 Python** | (无，可选未来添加) | `ShipOrchestrator` ✅ | `DeliverOrchestrator` 🔄 |
| **L1 LLM** | `Orchestrator` ✅ | `ShipOrchestrator` Agent 🔄 | (无 LLM Agent) |
| **L2 Python** | — | — | `DeliverRunner` 🔄 |
| **L2 LLM** | `Planning/Research/Summary Agent` ✅ | `Planner/Consolidator Agent` ✅ | — |
| **L3 LLM** | Expert Planners, Research Experts | Worker Architects | `Analyze/Worker/Validate/Package Agent` ✅ |

### 3.3 具体改动清单

#### Deliver Pro（3 处重命名）

| 当前名称 | 新名称 | 文件 | 理由 |
|:---|:---|:---|:---|
| `BatchDriver` | **`DeliverOrchestrator`** | `batch_driver.py` → `orchestrator.py` | L1 域级调度器，统一用 Orchestrator |
| `DeliverProOrchestrator` | **`DeliverWPRunner`** | `orchestrator.py` → `wp_runner.py` | L2 单 WP Phase 执行，不是 Orchestrator |
| `DeliverProDriver` | **`DeliverRunner`** | `driver.py`（文件名不变） | L2 薄层封装，简化命名 |

#### Ship Pro（1 处调整）

| 当前名称 | 新名称 | 文件 | 理由 |
|:---|:---|:---|:---|
| Dispatcher prompt 中的 "Dispatcher" | **`ShipOrchestrator Agent`** | `__init__.py` 中 `_build_orchestrator_prompt` | L1 LLM Agent 与 Python 类名统一 |

> 注: `ShipOrchestrator` Python 类名已正确，不需改。只需把 LLM Agent 从 "Dispatcher" 改为 "ShipOrchestrator Agent"。

#### Solution Pro（无改动）

| 当前名称 | 新名称 | 理由 |
|:---|:---|:---|
| `orchestrator.md` → "Orchestrator" | **不变** | ✅ 已符合规范 |
| Module Agents | **不变** | ✅ 已符合规范 |

---

## 四、改名后的架构对照图

```
                    ┌──────────────────────────────────────────────────────┐
                    │                   Main Agent (L0)                    │
                    └──────────┬───────────────────┬───────────────────┬──┘
                               │                   │                   │
              ┌────────────────┴──┐  ┌─────────────┴──────┐  ┌────────┴──────────┐
              │ run_solution_pro()│  │  run_ship_pro()    │  │ run_deliver_pro() │
              └────────┬──────────┘  └────────┬───────────┘  └────────┬──────────┘
                       │                      │                       │
    ┌──────────────────┴───────────────────┐  │                       │
    │  L1: SolutionOrchestrator (LLM)     │  │                       │
    │  prompt: orchestrator.md            │  │                       │
    └──┬────────────┬──────────────┬───────┘  │                       │
       │            │              │          │                       │
  ┌────┴─────┐ ┌────┴──────┐ ┌────┴──────┐   │                       │
  │ Planning │ │ Research  │ │ Summary   │   │                       │
  │ Agent(L2)│ │ Agent(L2) │ │ Agent(L2) │   │                       │
  └──────────┘ └───────────┘ └───────────┘   │                       │
                                              │                       │
    ┌─────────────────────────────────────────┴────────────────────┐  │
    │  L1: ShipOrchestrator (Python) + ShipOrchestrator Agent(LLM) │  │
    └──┬────────────────┬──────────────────┬───────────────────────┘  │
       │                │                  │                           │
  ┌────┴─────┐  ┌───────┴───────┐  ┌──────┴──────────┐               │
  │ Planner  │  │ Workers ×N    │  │ Consolidator    │               │
  │ (L2)     │  │ (L2)          │  │ (L2)            │               │
  └──────────┘  └───────────────┘  └─────────────────┘               │
                                                                       │
    ┌──────────────────────────────────────────────────────────────────┴─┐
    │  L1: DeliverOrchestrator (Python) ← 原 BatchDriver               │
    │  多 WP 分层驱动 + 确定性 Phase 转换                                │
    └──┬────────────────┬──────────────────┬─────────────────────────────┘
       │                │                  │
  ┌────┴──────────┐ ┌───┴───────────┐ ┌───┴───────────┐
  │ DeliverRunner │ │ DeliverRunner │ │ DeliverRunner │
  │ (L2, WP-001)  │ │ (L2, WP-002)  │ │ (L2, WP-N)   │
  │ 原DriverPro   │ │               │ │               │
  └──┬────────────┘ └───────────────┘ └───────────────┘
     │
     ├─ Analyze Agent (L3)
     ├─ Workers ×N (L3)
     ├─ Validate Agent (L3)
     └─ Package Agent (L3)
```

---

## 五、影响评估

### 5.1 Deliver Pro 改名影响

| 改动 | 影响文件 | 风险 |
|:---|:---|:---:|
| `BatchDriver` → `DeliverOrchestrator` | `batch_driver.py`, `__init__.py`, tests | 低（grep + 替换） |
| `DeliverProOrchestrator` → `DeliverWPRunner` | `orchestrator.py`, `driver.py`, tests | 中（多处引用） |
| `DeliverProDriver` → `DeliverRunner` | `driver.py`, `batch_driver.py`, tests | 低 |
| 文件重命名 | `batch_driver.py` → `orchestrator.py`, `orchestrator.py` → `wp_runner.py` | 中（需先移再改） |

### 5.2 Ship Pro 改名影响

| 改动 | 影响文件 | 风险 |
|:---|:---|:---:|
| "Dispatcher" → "ShipOrchestrator Agent" | `__init__.py` (prompt 文本) | 极低（只改 prompt 字符串） |

### 5.3 Solution Pro 影响

无。已符合规范。

---

## 六、执行顺序建议

1. **Phase 1**: Deliver Pro 重命名（最大改动，先做）
   - 先 `DeliverProOrchestrator` → `DeliverWPRunner`（释放 "orchestrator.py" 文件名）
   - 再 `BatchDriver` → `DeliverOrchestrator`（移到 `orchestrator.py`）
   - 最后 `DeliverProDriver` → `DeliverRunner`
   - 更新所有 import + tests

2. **Phase 2**: Ship Pro prompt 文本调整（极小改动）

3. **Phase 3**: 更新 MEMORY.md + 文档

---

## 七、命名速查表

| 域 | L1 调度 | L2 执行 | L3 任务 |
|:---|:---|:---|:---|
| **Solution Pro** | `SolutionOrchestrator` (LLM) | `Planning/Research/SummaryAgent` (LLM) | Expert Planner, Research Expert |
| **Ship Pro** | `ShipOrchestrator` (Python + LLM) | `Planner / Consolidator` (LLM) | Worker Architect |
| **Deliver Pro** | `DeliverOrchestrator` (Python) | `DeliverRunner` (Python) | Analyze/Worker/Validate/Package Agent |
