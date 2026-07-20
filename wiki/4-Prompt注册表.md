# Prompt 注册表

> 所有 Prompt 模板的完整清单和调用关系  
> 最后更新: 2026-07-08

---

## 统计

| 域 | Prompt 数量 | 文件位置 |
|:---|:---|:---|
| Spec Pro | 8 | `domains/spec_pro/prompts/` |
| Solution Pro | 39 | `domains/solution_pro/prompts/` |
| Ship Pro | 1 | `domains/ship_pro/prompts/` |
| Research Pro | 8 | `domains/research_pro/prompts/` |
| **总计** | **56** | |

---

## Spec Pro Prompts (8)

| 文件名 | 行数 | 调用者 | 用途 |
|:---|:---|:---|:---|
| `parse.md` | 204 | coordinator.py | 初始解析用户输入 + 域自推断 |
| `parse_response.md` | 154 | coordinator.py | 解析用户回复 |
| `structure.md` | 314 | coordinator.py | 结构化提取需求 + 预计算复杂度 |
| `assess.md` | 300 | coordinator.py | 质量评估 + 跨域评分锚点 |
| `harness.md` | 163 | harness 评估 | Harness 评分 + 三层门控 |
| `guide.md` | 206 | coordinator.py | 对话引导 + 三测试边界过滤 |
| `assess_guide.md` | 78 | coordinator.py | 评估引导 |
| `orchestrator.md` | 143 | coordinator.py | 编排任务 |

**总行数**: 1,562 行

---

## Solution Pro Prompts (39)

### Planning 模块 (9)

| 文件名 | 行数 | 用途 |
|:---|:---|:---|
| `planning_module.md` | 501 | Planning 模块完整指南 |
| `planning_planner.md` | 192 | 规划器 prompt |
| `planning_expert_base.md` | 181 | 专家基座 prompt |
| `expert_planner_base.md` | 123 | 专家规划器基座 |
| `meta_planner.md` | 205 | 元规划器 |
| `convergence_planner.md` | 271 | 收敛规划器 |
| `planner_harness.md` | 262 | 规划器评估 |
| `P0_CONSTRAINT_INJECTION_DESIGN.md` | 266 | P0 约束注入设计 |
| `REQ_DEDUP_DESIGN.md` | 215 | 需求去重设计 |

### Research 模块 (5)

| 文件名 | 行数 | 用途 |
|:---|:---|:---|
| `research_module.md` | 479 | Research 模块完整指南 |
| `research_planner.md` | 189 | 研究规划器 |
| `research_expert_base.md` | 172 | 研究专家基座 |
| `researcher_harness.md` | 184 | 研究员评估 |
| `review_layer_b.md` | 103 | Review Layer B |

### Summary 模块 (13)

| 文件名 | 行数 | 用途 |
|:---|:---|:---|
| `summary_module.md` | 835 | Summary 模块完整指南 (5+1 Phase) |
| `summary_summarizer.md` | 335 | 总结器 |
| `summary_analyzer_base.md` | 172 | 分析器基座 |
| `summary_base_synthesizer.md` | 216 | 基础综合器 |
| `summary_refiner.md` | 173 | 精炼器 |
| `summary_meta_planner.md` | 290 | 元规划审查 |
| `summary_json_extractor.md` | 307 | JSON 结构化提取 |
| `summary_fix_agent.md` | 236 | 修复 Agent |
| `summary_fix_judge.md` | 174 | 修复判断器 |
| `summary_harness_check.md` | 289 | Summary Harness 检查 |
| `summary_review_layer_b.md` | 387 | Summary Review Layer B |
| `reviewer_convergence.md` | 294 | 收敛评审器 |
| `reviewer_meta.md` | 226 | 元评审器 |

### 通用 (12)

| 文件名 | 行数 | 用途 |
|:---|:---|:---|
| `orchestrator.md` | 365 | 主编排器 |
| `harness_agent.md` | 371 | Harness Agent |
| `auditor_harness.md` | 225 | 审计 Harness |
| `consolidator_harness.md` | 175 | 合并 Harness |
| `fixer_harness.md` | 178 | 修复 Harness |
| `fixer_expert_harness.md` | 185 | 修复专家 Harness |
| `reviewer_harness.md` | 188 | 评审 Harness |
| `summarizer_harness.md` | 270 | 总结 Harness |
| `ai_native_cognitive_base.md` | 48 | AI Native 认知基座 |
| `compliance_checker_base.md` | 58 | 合规检查器基座 |
| `_shared_subagent_rules.md` | 43 | 子 Agent 共享规则 |
| `README.md` | 19 | Prompt 目录说明 |

**总行数**: 8,426 行

---

## Ship Pro Prompts (1)

| 文件名 | 行数 | 调用者 | 用途 |
|:---|:---|:---|:---|
| `consolidator.md` | 111 | consolidator worker | 合并 Worker 输出 |

**总行数**: 111 行

---

## Research Pro Prompts (8)

| 文件名 | 行数 | 调用者 | 用途 |
|:---|:---|:---|:---|
| `orchestrator.md` | — | orchestrator.py | 研究编排 |
| `planning.md` | — | orchestrator.py | 研究规划 |
| `search.md` | — | orchestrator.py | 搜索执行 |
| `tech_analysis.md` | — | orchestrator.py | 技术分析 |
| `finance_analysis.md` | — | orchestrator.py | 金融分析 |
| `quality_reviewer.md` | — | orchestrator.py | 质量审查 |
| `report_writer.md` | — | orchestrator.py | 报告撰写 |
| `citation_verify.md` | — | citation_verifier.py | 引用验证 |

---

## 通用 Prompts (根目录)

路径: `prompts/`

| 子目录 | 内容 |
|:---|:---|
| `architecture/` | 架构相关 prompt |
| `code/` | 代码生成 prompt |
| `general/` | 通用 prompt |
| `research_pro/` | Research Pro 共享 prompt |
| `ship_pro/` | Ship Pro 共享 prompt |
| `solution_pro/` | Solution Pro 共享 prompt |
| `spec_pro/` | Spec Pro 共享 prompt |
| `system/` | 系统级 prompt |
| `registry.yaml` | 全局注册表 |

---

## Prompt 设计原则

1. **Prompt 是协作契约**，不是指令列表
   - 包含: Role + Context + Constraints + Examples + Output Schema
2. **多域示例**: 16+ prompt 已泛化，包含 software/investment/hardware/business 示例
3. **DAL 集成**: prompt 中预留 `{domain_context}` 占位符，运行时注入域上下文
4. **结构化输出**: 每个 prompt 定义明确的 JSON Schema，由 Pydantic 验证
