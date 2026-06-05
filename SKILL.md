# DeepFlow Skill — 多 Agent 协作自动化管线

> DeepFlow 0.3.0 (Spec Pro v2.4 + Solution Pro V4.4 + Investment + Research Pro)

**定位**: 支持 Spec Pro（需求梳理）、Solution Pro（方案设计）、Investment（投资分析）、Research Pro（深度研究）四领域的多 Agent 协作自动化管线。

**完整架构说明**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 触发方式

| 命令 | 示例 | 领域 |
|:---|:---|:---|
| `/deep` | `/deep 分析 688347.SH 华虹公司 2026年业绩` | investment |
| `深度分析` | `深度分析：中芯国际投资研报` | investment |
| `/solution` | `/solution 设计一个智能物流仓储系统升级方案` | solution |
| `方案设计` | `方案设计：设计企业级微服务架构` | solution |
| `/spec-pro` | `/spec-pro 我要做一个 AI 算力调度平台` | spec_pro |

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
执行完整投资分析管线。
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

执行固定 10 阶段完整管线。
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
| `spec_pro` | 苏格拉底对话 | 需求梳理，输出 Living Spec + 三层版本号 | 对话式 |
| `solution` | 固定 10 阶段闭环 | Harness V4 + REQ-ID 追踪 + 状态持久化 | 固定管线 |
| `investment` | 并行研究+审计 | 投资研报，三维度审计+三情景目标价 | 单模式 |
| `research_pro` | 分层搜索+引用验证 | 多源搜索 → 分层研究 → 引用验证 | 单模式 |

## Solution Pro 固定 10 阶段管线

| 阶段 | Agent 角色 | 并行 | 说明 |
|------|-----------|------|------|
| 1. Data Collection | data_collection | ❌ | 基础数据采集 |
| 2. Planning | planning | ❌ | 制定研究计划 |
| 3. Reviewers | technical/business/risk | ✅ | 三维度方案评审 |
| 4. Research | expert_1/2/3 | ✅ | 并行专家研究 |
| 5. Consolidator | consolidator | ❌ | 整合研究成果 |
| 6. Audit | audit | ❌ | 质量审计 |
| 7. Fix | fix | ❌ | 修复缺陷 |
| 8. Fixer Expert | fixer_expert | ❌ | 专家级修复 |
| 9. Harness Final | harness_final | ❌ | 最终质量门禁（HARNESS V4 + REQ-ID 追踪） |
| 10. Summarizer | summarizer | ❌ | 生成最终报告 |

**契约保护**：Cage Validator 在关键阶段前校验契约合规性

## 核心组件

| 组件 | 文件 | 职责 |
|:---|:---|:---|
| **Unified Entry** | `core/unified_entry.py` | 统一入口，根据 domain 路由 |
| **Entry Harness** | `core/quality/entry_harness.py` | 启动验证、配置检查、生成 execution_plan |
| **Pipeline Orchestrator** | `core/orchestrator/pipeline_orchestrator.py` | 读取 execution_plan，按 phase 调度 Workers |
| **Task Builder** | `core/task_builder.py` | 构建各 Worker Task |
| **DataManager** | `core/data/data_manager_worker.py` | 数据采集+统一搜索 |
| **Contract Cage** | `core/cage/` | 契约笼子验证框架 |
| **Prompt Registry** | `core/prompt_registry.py` | Prompt 集中式注册表 |
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

- **Version**: 0.3.0
- **Status**: Spec Pro v2.4 + Solution Pro V4.4 + 契约笼子 + REQ-ID 质量追踪 + 状态持久化
- **Date**: 2026-06-03
