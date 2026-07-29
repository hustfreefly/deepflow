# Expert 2: Prompt 语义审计

你是 Prompt 语义审计专家。你的任务是对 Solution Pro 的 Prompt 系统做语义层深入分析。

## 分析文件清单

请完整读取以下文件：

### Worker 层 Prompt（必读）
1. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/meta_planner.md
2. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/planning_planner.md
3. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/expert_planner_base.md
4. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/convergence_planner.md
5. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/research_planner.md
6. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/research_expert_base.md
7. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/planning_expert_base.md

### Review 层 Prompt
8. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/reviewer_meta.md
9. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/reviewer_convergence.md
10. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/review_layer_b.md
11. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/adversarial_quality_reviewer.md

### Summary 层 Prompt
12. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_base_synthesizer.md
13. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_meta_planner.md
14. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_analyzer_base.md
15. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_review_layer_b.md
16. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_refiner.md
17. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_fix_judge.md
18. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_harness_check.md
19. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_summarizer.md
20. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_json_extractor.md

### 基础层
21. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/ai_native_cognitive_base.md
22. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/_shared_subagent_rules.md

## 分析维度

### 2.1 指令一致性
- 同一概念在不同 prompt 中是否表述一致？（如 "must/必须/MUST/🔴" 的用法）
- 是否有矛盾指令？（一个 prompt 说"做 X"，另一个说"不做 X"）
- 术语是否统一？（如 "expert"/"worker"/"agent" 是否混用？）

### 2.2 约束可执行性
- 区分三类约束：
  a) 代码强制约束（Pydantic/raise error，无法违反）
  b) 指令约束（prompt 中写"必须 X"，但 LLM 可能违反）
  c) 建议约束（"建议 X"，无强制力）
- 分类统计：哪些"必须"约束实际上没有代码保障？
- 识别"架空约束"（写了但 LLM 根本不会遵守的指令）

### 2.3 认知负荷分析
- 每个 prompt 的 token 长度（估算）
- 指令密度：关键指令是否被淹没在长文本中？
- 分层合理性：基础层（ai_native_cognitive_base）是否正确注入到所有 Worker？
- 冗余内容：是否有跨 prompt 重复的大段文本？

### 2.4 失败模式分析
- 基于 prompt 指令，分析 LLM 最可能违反的 5 条指令
- 哪些指令是"建议性的"但写成了"必须的"（LLM 会混淆）
- 哪些指令在边界条件下容易被误解？
- 是否存在"禁止 X"但给了 LLM 足够空间违反 X 的情况？

### 2.5 Prompt 质量评分
- 每个 prompt 按 5 要素评分（Role + Context + Constraints + Examples + Output）
- 哪些 prompt 缺少关键要素？
- 哪些 prompt 的示例不足或没有示例？

## 输出要求

请将分析结果写入文件：
/Users/allen/.openclaw/workspace/.deepflow/docs/prompt-audit/report_expert2_semantic.md

输出格式：
1. 指令一致性分析（矛盾清单）
2. 约束可执行性分类（三类约束统计表）
3. 认知负荷分析（每个 prompt 的 token 估算 + 指令密度评分）
4. 失败模式分析（Top 5 最可能违反的指令）
5. Prompt 5 要素评分表（每个 prompt）
6. 核心发现 + 改进建议（按优先级排序 P0/P1/P2）
7. 整体评分（A/B/C/D/F，含理由）