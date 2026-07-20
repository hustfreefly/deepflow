---
name: deepflow
description: "DeepFlow V3.0.0 — 多 Agent 管线框架。四域管线（Spec→Solution→Ship→Deliver）+ 独立研究引擎 Research Pro。"
version: "3.0.0"
---

# DeepFlow Skill

> 多 Agent 管线框架，运行在 OpenClaw 之上。

---

## 五域使用指南

### 1. Spec Pro — 需求梳理引擎

**版本**: V2.2.0
**触发**: 用户说"梳理需求"、"需求分析"、"Living Spec"

```python
from domains.spec_pro import SpecProCoordinator

coordinator = SpecProCoordinator(
    user_input="用户需求描述",
    scenario="genesis",  # genesis | supplement | refine | pivot
)
# coordinator 运行在主 Agent 侧，通过 sessions_spawn 与子 Agent 对话
result = coordinator.run()
# 输出: Living Spec → blackboard/{project}/spec_pro/living_spec.md
```

**关键参数**:
- `user_input`: 用户原始需求文本
- `scenario`: 场景（genesis=新建 / supplement=补充 / refine=精炼 / pivot=转向）
- `project_name`: 项目名（决定 blackboard 路径）

**Prompts**: 8 个（parse, assess, structure, orchestrator, harness, guide, assess_guide, parse_response）

---

### 2. Solution Pro — 方案设计引擎

**版本**: V3.1.0
**触发**: 用户说"设计解决方案"、"架构设计"、"技术方案"

```python
from domains.solution_pro import run_solution_pro

result = run_solution_pro(
    user_input="设计一个高并发消息系统",
    project_name="my_project",
    trace_id=None,  # 可选，跨域追踪
)
# result 包含 spawn_params，主 Agent 用 sessions_spawn 启动编排器
```

**架构**:
- **DAL（Domain Analysis Layer）**: 自动推断用户意图域（software/investment/general），生成 DomainProfile
- **三模块编排**:
  - `Planning Orchestrator`: 方案规划，多专家并行
  - `Research Orchestrator`: 深度研究，信息收集
  - `Summary Orchestrator`: 总结收敛，输出方案文档
- **三层门控**: L1 代码粗筛 → L2 LLM 语义 → L3 合并决策
- **收敛层**: 多专家输出收敛为单一方案

**Prompts**: 40+ 个（planning_expert_base, research_expert_base, summary_analyzer_base, harness_agent, orchestrator, convergence_planner, ...）

---

### 3. Ship Pro — 交付包生成引擎

**版本**: V2.0.0
**触发**: 用户说"生成工作包"、"拆分任务"、"交付编译"

```python
from domains.ship_pro import run_ship_pro

result = run_ship_pro(
    project_name="my_project",
    trace_id=None,  # 可选，跨域追踪
)
# result 包含 spawn_params，主 Agent 用 sessions_spawn 启动编排器
```

**架构（V2.0.0 单入口 Dispatcher）**:
```
Main Agent (depth-0)
  → exec: result = run_ship_pro(project_name=...)
  → sessions_spawn(**result["spawn_params"])
  → 等待完成事件 → 拿到 ShipPackage

Orchestrator (depth-1, 全权调度)
  → 读取统一 blackboard 中的 Solution Pro 输出
  → exec: design_pipeline() → Designer prompt
  → spawn: Designer LLM → PipelinePlan
  → exec: prepare_runner_spawn() → Worker prompts
  → spawn: Workers (并行/分层)
  → exec: L1 validation
  → spawn: Consolidator
  → exec: ShipPackage validation
  → 输出最终报告
```

**关键组件**:
- `PipelineDesigner`: LLM 自动设计执行管线
- `Ship Orchestrator`: 全权调度 Workers + Consolidator
- `Conservation Judge`: 信息守恒检查
- `Ship Package`: 最终交付物（任务拆分 + 上下文 + 依赖图）

**Prompts**: consolidator

---

### 4. Deliver Pro — 执行引擎

**版本**: V1.0.0
**触发**: 用户说"执行交付"、"生成最终报告"、"交付成果"

```python
from domains.deliver_pro import run_deliver_pro

result = run_deliver_pro(
    project_name="my_project",
    trace_id=None,
)
```

**5 Phase 流水线**:
| Phase | 职责 | 方式 |
|:-----:|:-----|:----:|
| P1 Analyze | WP → execution_plan | LLM Agent |
| P2 Generate | Workers 并行生成内容 | LLM Agent × N |
| P3 Integrate | Code-First Assembly（确定性拼接） | Python（零 LLM） |
| P4 Validate | 质量评估（6维度+保留率门禁） | LLM Judge |
| P5 Package | 交付清单+元数据 | LLM Agent |

**核心设计**: Code-First Assembly — 用确定性拼接替代 LLM 组装，解决 84% 内容丢失问题。
**关键文件**: `smart_assembler.py`（组装引擎）, `orchestrator.py`（流水线调度）, `contracts/`（18 个 Pydantic 模型）

---

### 5. Research Pro — 多专家并行研究

**版本**: V1.0
**触发**: 用户说"深度研究"、"调研"、"分析"

```python
from domains.research_pro import run_research_pro

result = run_research_pro(
    query="分析贵州茅台的投资价值",
    mode="standard",  # quick | standard
)
# result 包含 spawn_params
```

**关键组件**:
- `DDGS Client`: DuckDuckGo 搜索
- `Safe Fetcher`: 安全网页抓取
- `Tier Classifier`: 来源分级（T1/T2/T3）
- `Citation Verifier`: 引用验证
- `Source Registry`: 来源注册表

---

## 域间协作

```
Spec Pro → living_spec.md → Solution Pro → solution_design.md → Ship Pro → ship_package.md → Deliver Pro → deliver_final.md
```

所有域通过统一 Blackboard 共享状态：
```
.deepflow/blackboard/{project_name}/
├── spec_pro/living_spec.md       ← Spec Pro 输出
├── solution_pro/solution_design.md ← Solution Pro 输出
├── ship_pro/ship_package.md      ← Ship Pro 输出
├── deliver_pro/deliver_final.md  ← Deliver Pro 最终交付
└── ...
```

---

## AI Native 设计

### 三层门控

所有关键决策点：
- **L1**: 代码粗筛（字段存在、类型匹配、无环依赖）
- **L2**: LLM 语义评估（独立视角，语义合理性）
- **L3**: 合并决策（L1 + L2 → PASS / CONDITIONAL / FAIL）

### DAL（Domain Analysis Layer）

```
domain_analysis → DomainProfile → 全链路透传
```

Solution Pro 入口自动推断域，生成 DomainProfile，沿 Planning → Research → Summary 全链路传递。

---

## 测试

```bash
cd /Users/allen/.openclaw/workspace
python3 -m pytest .deepflow/domains/ -v
# 467 tests: Spec 60 + Solution 143 + Ship 36 + Deliver 213 + Research 15
```

---

*DeepFlow V3.0.0 — 让 Agent 管线像流水线一样可靠。*
