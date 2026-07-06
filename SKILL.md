---
name: deepflow
description: "DeepFlow — 多 Agent 协作自动化管线。触发：/spec-pro、/solution-pro、/ship-pro、/research-pro、方案设计。"
version: "2.0.0"
---

# DeepFlow — 多 Agent 协作自动化管线

> DeepFlow 2.0.0 (Spec Pro 2.0.0 + Solution Pro 2.0.0 + Ship Pro 2.0.0 + Research Pro)

**定位**: 支持 Spec Pro（需求梳理）、Solution Pro（方案设计）、Ship Pro（交付编译）、Research Pro（深度研究）的多 Agent 协作自动化管线。

**完整架构说明**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **上手指南**: [docs/guides/QUICKSTART.md](docs/guides/QUICKSTART.md)

## 触发方式

| 命令 | 示例 | 领域 | 详细指南 |
|:---|:---|:---|:---|
| `/spec-pro` | `/spec-pro 我要做一个 AI 算力调度平台` | spec_pro | [domains/spec_pro/SKILL.md](domains/spec_pro/SKILL.md) |
| `/solution-pro` | `/solution-pro 设计一个智能物流仓储系统升级方案` | solution_pro | [domains/solution_pro/SKILL.md](domains/solution_pro/SKILL.md) |
| `/ship-pro` | `/ship-pro` (自动消费 Solution Pro 输出) | ship_pro | [domains/ship_pro/SKILL.md](domains/ship_pro/SKILL.md) |
| `/research-pro` | `/research-pro 分析 AI 芯片市场趋势` | research_pro | [domains/research_pro/SKILL.md](domains/research_pro/SKILL.md) |

## 执行流程（Solution Pro）

### 方式一：主 Agent 触发（推荐）

```
# Solution Pro 方案设计
/spec-pro 我要做一个 AI 算力调度平台
# → Spec Pro 输出 Living Spec → 自动触发 Solution Pro

# Ship Pro 交付编译（自动触发）
# Solution Pro 完成后，completion_handler.py 自动编译 Ship Package
# 手动触发：
cd ~/.openclaw/workspace/.deepflow
python3 domains/ship_pro/scripts/run_pipeline.py prepare <input_path> <output_dir>
```

### 方式二：主 Agent 直接 spawn

```python
# Solution Pro
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

sessions_yield()
```

## 支持的领域

| 领域 | 管线类型 | 特点 | 模式 |
|:---|:---|:---|:---|
| `spec_pro` | 苏格拉底对话 | 需求梳理，输出 Living Spec + 三层版本号 | 对话式 |
| `solution_pro` | 固定 10 阶段闭环 | Harness 2.0.0 + REQ-ID 追踪 + 状态持久化 | 固定管线 |
| `ship_pro` | 5 Agent 管线 | Pydantic 契约笼子 + 质量门禁 + 单一执行引擎 | 固定管线 |
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
| 9. Harness Final | harness_final | ❌ | 最终质量门禁（HARNESS 2.0.0 + REQ-ID 追踪） |
| 10. Summarizer | summarizer | ❌ | 生成最终报告 |

**契约保护**：Cage Validator 在关键阶段前校验契约合规性

## 核心组件

| 组件 | 文件 | 职责 |
|:---|:---|:---|
| **MasterOrchestrator** | `core/master_orchestrator.py` | 主编排器，统一入口 |
| **ModuleOrchestrator** | `domains/solution_pro/module_orchestrator_base.py` | 域编排器基类 |
| **Entry Harness** | `core/quality/entry_harness.py` | 启动验证（DEPRECATED） |
| **Contract Cage** | `core/cage/` | 契约笼子验证框架 |
| **Pydantic Contracts** | `domains/*/contracts/` | Pydantic 模型 = 唯一真相源 |
| **Prompt Registry** | `core/prompt_registry.py` | Prompt 集中式注册表 |
| **PathConfig** | `core/config/path_config.py` | 跨平台路径管理 |
| **Blackboard** | `core/blackboard/` | 统一 Blackboard 状态持久化 |

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

## 版本

- **Version**: 2.0.0
- **Status**: 四域架构完成；Pydantic 契约笼子 + 统一 Blackboard + 路径模板化
- **Date**: 2026-07-06
