# Prompt 注册表

> 所有 Prompt 模板的完整清单和调用关系  
> 最后更新：2026-06-22

---

## 统计

| 域 | Prompt 数量 | 文件位置 |
|:---|:---|:---|
| Spec Pro | 10 | `domains/spec_pro/prompts/` |
| Solution Pro | 25 | `domains/solution/prompts/` |
| Ship Pro | 9 | `domains/ship_pro/prompts/` |
| Research Pro | 6 | `domains/research_pro/prompts/` |
| 通用 | 20+ | `prompts/` |
| **总计** | **70+** | |

---

## Spec Pro Prompts

| 文件名 | 版本 | 调用者 | 用途 |
|:---|:---|:---|:---|
| `parse.md` | 2.0.0 | coordinator.py | 初始解析用户输入 |
| `parse_response.md` | 2.0.0 | coordinator.py | 解析用户回复 |
| `structure.md` | 2.0.0 | coordinator.py | 结构化提取需求 |
| `assess.md` | 2.0.0 | coordinator.py | 质量评估 |
| `harness.md` | 2.0.0 | harness.py | Harness 评分 |
| `guide.md` | 2.0.0 | coordinator.py | 对话引导 |
| `assess_guide.md` | 2.0.0 | coordinator.py | 评估引导 |
| `orchestrator.md` | 2.0.0 | coordinator.py | 编排任务 |
| `structure_guide.md` | 2.0.0 | coordinator.py | 结构化引导 |
| `requirement_structuring.md` | 2.0.0 | coordinator.py | 需求结构化 |

---

## Solution Pro Prompts

### 核心管线 (10 阶段)

| 阶段 | 文件名 | 版本 | 调用者 | 用途 |
|:---|:---|:---|:---|:---|
| 1 | `planner.md` | 2.1.0 | orchestrator_agent.py | 架构设计 |
| 1 | `planner_v2_harness.md` | 2.1.0 | orchestrator_agent.py | Planner + Harness |
| 2 | `reviewer.md` | 2.1.0 | orchestrator_agent.py | 方案评审 |
| 2 | `reviewer_v2_harness.md` | 2.1.0 | orchestrator_agent.py | Reviewer + Harness |
| 3 | `fixer_v2_harness.md` | 2.1.0 | orchestrator_agent.py | 修复评审问题 |
| 4 | `researcher_v2_harness.md` | 2.1.0 | orchestrator_agent.py | 深度研究 |
| 5 | `consolidator.md` | 2.1.0 | orchestrator_agent.py | 合并研究结论 |
| 5 | `consolidator_v2_harness.md` | 2.1.0 | orchestrator_agent.py | Consolidator + Harness |
| 6 | `auditor_v2_harness.md` | 2.1.0 | orchestrator_agent.py | 架构审计 |
| 7 | `fixer_expert_v2_harness.md` | 2.1.0 | orchestrator_agent.py | 修复审计问题 |
| 8 | `harness_v3.md` | 3.0.0 | harness_scorer.py | 质量评分 |
| 8 | `harness_scoring.md` | 3.0.0 | harness_scorer.py | Harness 评分 |
| 9 | `fixer_v2_harness.md` | 2.1.0 | orchestrator_agent.py | 提升质量分数 |
| 10 | `summarizer.md` | 2.1.0 | orchestrator_agent.py | 生成最终方案 |
| 10 | `summarizer_v2_harness.md` | 2.1.0 | orchestrator_agent.py | Summarizer + Harness |

### 辅助 Prompt

| 文件名 | 版本 | 调用者 | 用途 |
|:---|:---|:---|:---|
| `data_collection.md` | 1.0.0 | orchestrator_agent.py | 数据收集 |
| `designer.md` | 1.0.0 | orchestrator_agent.py | UI/UX 设计 |
| `deliver.md` | 1.0.0 | orchestrator_agent.py | 交付打包 |
| `pipeline_orchestrator.md` | 2.0.0 | pipeline_orchestrator.py | 管线编排 |
| `pipeline_orchestrator_v4.md` | 4.0.0 | pipeline_orchestrator.py | 管线编排 V4 |
| `orchestrator_completion.md` | 2.0.0 | completion_handler.py | 完成处理 |
| `cron_watcher.md` | 1.0.0 | cron_watcher.py | 定时监控 |
| `REQ_DEDUP_DESIGN.md` | 1.0.0 | - | 需求去重设计文档 |

---

## Ship Pro Prompts

| 文件名 | 版本 | 调用者 | 用途 |
|:---|:---|:---|:---|
| `architect.md` | 3.0.0 | orchestrator.py | 架构设计 |
| `specifier.md` | 3.0.0 | orchestrator.py | 工作包规格 |
| `decomposer.md` | 3.0.0 | orchestrator.py | 任务分解 |
| `packager.md` | 3.0.0 | orchestrator.py | 打包 |
| `reviewer.md` | 3.0.0 | orchestrator.py | 最终审核 |
| `ship_orchestrator.md` | 3.0.0 | orchestrator.py | 编排 |
| `ship_fixer.md` | 3.0.0 | orchestrator.py | 修复问题 |
| `ship_harness.md` | 3.0.0 | gates.py | 质量门控 |
| `ship_reviewer.md` | 3.0.0 | orchestrator.py | 审核 |
| `ship_pre_scanner.md` | 3.0.0 | orchestrator.py | 预扫描 |
| `cron_watcher.md` | 1.0.0 | cron_watcher.py | 定时监控 |

---

## Research Pro Prompts

| 文件名 | 版本 | 调用者 | 用途 |
|:---|:---|:---|:---|
| `planning.md` | 1.0.0 | orchestrator.py | 研究规划 |
| `search.md` | 1.0.0 | search_agent.py | 搜索关键词生成 |
| `report_writer.md` | 1.0.0 | writer_agent.py | 报告撰写 |
| `citation_verify.md` | 1.0.0 | citation_verifier.py | 引用验证 |
| `finance_analysis.md` | 1.0.0 | analyst_agent.py | 财务分析 |
| `tech_analysis.md` | 1.0.0 | analyst_agent.py | 技术分析 |

---

## 通用 Prompts

### prompts/architecture/ (架构相关)

| 文件名 | 用途 |
|:---|:---|
| `auditor.md` | 架构审计 |
| `correctness.md` | 正确性检查 |
| `fixer.md` | 问题修复 |
| `performance.md` | 性能优化 |
| `planner.md` | 架构规划 |
| `researcher.md` | 架构研究 |
| `security.md` | 安全检查 |

### prompts/code/ (代码相关)

| 文件名 | 用途 |
|:---|:---|
| `correctness.md` | 代码正确性 |
| `fixer.md` | 代码修复 |
| `planner.md` | 代码规划 |
| `security.md` | 代码安全 |
| `verifier.md` | 代码验证 |

### prompts/general/ (通用)

| 文件名 | 用途 |
|:---|:---|
| `auditor.md` | 通用审计 |
| `fixer.md` | 通用修复 |
| `planner.md` | 通用规划 |
| `researcher.md` | 通用研究 |
| `verifier.md` | 通用验证 |

### prompts/system/ (系统级)

| 文件名 | 用途 |
|:---|:---|
| `data_manager_agent.md` | 数据管理 |
| `deepflow_navigator.md` | 系统导航 |
| `pipeline_engine_orchestrator.md` | 管线引擎 |
| `report_extractor.md` | 报告提取 |
| `summarizer.md` | 通用摘要 |

---

## 版本命名规范

```
{major}.{minor}.{patch}

major: 破坏性变更 (架构调整)
minor: 向后兼容 (新增功能)
patch: 向后兼容 (bug 修复)
```

**示例**:
- `2.1.0` - 第 2 版，新增 Harness 功能
- `3.0.0` - 第 3 版，架构重构

---

## 如何添加新 Prompt

1. 在对应域的 `prompts/` 目录创建 `.md` 文件
2. 在文件头部添加 YAML frontmatter:
   ```yaml
   ---
   id: {domain}_{role}_{version}
   version: 2.1.0
   description: 用途描述
   ---
   ```
3. 在对应域的 Cage 配置中注册:
   ```json
   {
     "prompts": {
       "planner_v2_harness.md": "2.1.0"
     }
   }
   ```
4. 在代码中调用:
   ```python
   from core.prompt_registry import load_prompt
   
   prompt = load_prompt("planner_v2_harness.md")
   ```
