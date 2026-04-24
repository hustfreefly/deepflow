# DeepFlow Skill — 多 Agent 协作自动化管线

> DeepFlow 0.1.0 (V4.0) — 基于通用多 Agent 协作框架的垂直场景适配

**定位**: 当前重点适配投资分析场景，框架设计支持扩展至其他领域。

**完整架构说明**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 触发方式

| 命令 | 示例 |
|:---|:---|
| `/deep` | `/deep 分析 688347.SH 华虹公司 2026年业绩` |
| `深度分析` | `深度分析：中芯国际投资研报` |

## 执行流程（Agent Run 模式）

### 方式一：统一入口（推荐）

```python
# 主 Agent 执行：一键初始化并生成调用指令
result = exec("python3 /Users/allen/.openclaw/workspace/.deepflow/deepflow.py --code 688981.SH --name 中芯国际")
# result 包含 session_id 和 sessions_spawn 调用参数

# 主 Agent 解析 result，执行 sessions_spawn
sessions_spawn(
    runtime="subagent",
    mode="run",
    label=f"orchestrator_{result['session_id']}",
    task=result['call_instruction']['params']['task'],
    timeout_seconds=1800
)

# 等待完成
sessions_yield()
```

### 方式二：分步执行（原始方式，保留）

```python
# Step 1: 初始化（生成 tasks.json + execution_plan.json）
exec("python3 /Users/allen/.openclaw/workspace/.deepflow/core/master_agent.py --code 688981.SH --name 中芯国际")

# Step 2: 读取 Orchestrator Task
orchestrator_task = read("/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/orchestrator_task.txt")

# Step 3: spawn Orchestrator Agent
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="orchestrator",
    task=orchestrator_task,
    timeout_seconds=1800
)

# Step 4: 等待完成
sessions_yield()
```

## 支持的领域

| 领域 | 管线类型 | 特点 |
|:---|:---|:---|
| `investment` | 并行研究+审计 | 投资研报，三维度审计+三情景目标价 |

## 核心组件

| 组件 | 文件 | 职责 |
|:---|:---|:---|
| **Master Agent** | `core/master_agent.py` | 生成 session_id，构建 Tasks |
| **Orchestrator** | `orchestrator_agent.py` | 调度 Workers，sessions_spawn |
| **Task Builder** | `core/task_builder.py` | 构建各 Worker Task |
| **DataManager** | `core/data_manager_worker.py` | 数据采集+统一搜索 |
| **Contract Cage** | `cage/` | 契约笼子验证框架 |

## 输出

所有输出写入 Blackboard：`/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/`

| 文件 | 说明 |
|:---|:---|
| `tasks.json` | 所有 Worker Tasks |
| `data/v0/*.json` | 采集的基础数据 |
| `stages/*.json` | 各 Worker 输出 |
| `final_report.md` | 最终投资报告 |

## 依赖

- Python 3.10+
- OpenClaw Agent Run 环境
- 数据源：Tushare, 新浪财经

## 版本

- **Version**: 0.1.0
- **Status**: Phase 1 完成
- **Date**: 2026-04-23

