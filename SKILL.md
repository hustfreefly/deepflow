# DeepFlow Skill — 多 Agent 协作自动化管线

> DeepFlow 0.1.1 (V4.0 投资分析 + V3.1 方案设计)

**定位**: 支持投资分析和方案设计双领域的多 Agent 协作自动化管线。

**完整架构说明**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 触发方式

| 命令 | 示例 | 领域 |
|:---|:---|:---|
| `/deep` | `/deep 分析 688347.SH 华虹公司 2026年业绩` | investment |
| `深度分析` | `深度分析：中芯国际投资研报` | investment |
| `/solution` | `/solution 设计一个智能物流仓储系统升级方案` | solution |
| `方案设计` | `方案设计：设计企业级微服务架构` | solution |

## 执行流程

### 方式一：统一入口（推荐）

```python
from core.unified_entry import UnifiedEntry
from core.config.path_config import PathConfig

# 获取 DeepFlow 基础路径
base_path = str(PathConfig.resolve().base_dir)

# 投资分析
entry = UnifiedEntry()
result = entry.run({
    "domain": "investment",
    "code": "688981.SH",
    "name": "中芯国际"
})

# 方案设计
result = entry.run({
    "domain": "solution",
    "topic": "设计一个智能物流仓储系统升级方案",
    "solution_type": "architecture",
    "constraints": ["预算500万", "周期6个月"]
})
```

### 方式二：主 Agent 直接 spawn（Agent Run 模式）

```python
# 投资分析
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="investment_analysis",
    task="""
你是 DeepFlow Investment Orchestrator Agent。

股票: 688981.SH 中芯国际
执行完整投资分析管线:
1. DataManager 数据采集
2. 统一搜索补充
3. Planner 制定计划
4. Researchers ×6 并行分析
5. Auditors ×3 并行审计
6. Fixer 修正
7. Summarizer 生成报告

所有输出写入 blackboard/ 目录。
""",
    timeout_seconds=1800
)

# 方案设计
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="solution_design",
    task="""
你是 DeepFlow Solution Pro Orchestrator Agent。

任务: 设计一个智能物流仓储系统升级方案
类型: architecture
约束: 预算500万，周期6个月

执行 10 阶段完整管线:
1. Data Collection
2. Planning + Reviewers
3. Research ×N
4. Consolidator
5. Audit + Fix
6. Harness Final
7. Summarizer

所有输出写入 blackboard/ 目录。
""",
    timeout_seconds=1800
)

# 等待完成
sessions_yield()
```

## 支持的领域

| 领域 | 管线类型 | 特点 | 模式 |
|:---|:---|:---|:---|
| `investment` | 并行研究+审计 | 投资研报，三维度审计+三情景目标价 | 单模式 |
| `solution` | 10阶段完整闭环 | 方案设计，Harness V2 质量保障 | Quick/Standard/Pro |

### Solution Pro 三种模式

| 模式 | 适用场景 | 执行时间 | Agent数 | 特点 |
|:---|:---|:---:|:---:|:---|
| **Quick** | 方案预览、初步思路 | 2-3分钟 | 3个 | 快速、轻量 |
| **Standard** | 一般架构设计 | 8-15分钟 | 8-10个 | 平衡质量与时效 |
| **Pro** | 复杂企业级方案 | 20-30分钟 | 12+个 | Harness V2 + Layer 2 约束验证 |

## 核心组件

| 组件 | 文件 | 职责 |
|:---|:---|:---|
| **Unified Entry** | `core/unified_entry.py` | 统一入口，根据 domain 路由 |
| **Entry Harness** | `core/entry_harness.py` | 启动验证、配置检查、生成 execution_plan |
| **Pipeline Orchestrator** | `core/pipeline_orchestrator.py` | 读取 execution_plan，按 phase 调度 Workers |
| **Task Builder** | `core/task_builder.py` | 构建各 Worker Task |
| **DataManager** | `core/data_manager_worker.py` | 数据采集+统一搜索 |
| **Contract Cage** | `cage/` | 契约笼子验证框架 |
| **Prompt Registry** | `prompts/prompt_registry.py` | Prompt 集中式注册表 |
| **PathConfig** | `core/config/path_config.py` | 跨平台路径管理 |

## 输出

所有输出写入 Blackboard：`blackboard/{session_id}/`

| 文件 | 说明 |
|:---|:---|
| `tasks.json` | 所有 Worker Tasks |
| `execution_plan.json` | 执行计划 |
| `config/data/v0/*.json` | 采集的基础数据 |
| `stages/*.json` | 各 Worker 输出 |
| `final_report.md` | 最终报告 |

## 依赖

- Python 3.10+
- OpenClaw Agent Run 环境
- 数据源：Tushare, 新浪财经（投资模块）
- 搜索：Gemini API, DuckDuckGo（方案设计模块）

## 版本

- **Version**: 0.1.1
- **Status**: Phase 1 完成 + Solution Pro V3.1 发布
- **Date**: 2026-05-06
