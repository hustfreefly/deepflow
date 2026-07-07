# Prompt 层泛化性审计报告

> Agent A | 模型: qwen3.7-max | 耗时: 3m47s | 审计范围: 36 个 prompt

## 汇总评分

| # | Prompt | 评分 | 主要问题 |
|---|--------|:---:|---------|
| 1 | meta_planner.md | 3/10 | 示例全软件（CRUD API/支付/ML）；domain枚举写死；Gate B全软件检查项 |
| 2 | expert_planner_base.md | 3/10 | 两个示例全软件（Security用HTTPS/bcrypt；Performance用API响应时间） |
| 3 | reviewer_convergence.md | 4/10 | 验证命令全软件（curl/psql/ESLint）；约束示例HTTPS/TLS/PostgreSQL |
| 4 | planner_harness.md | 4/10 | 方案类型2/3绑定软件；维度提取全技术指标 |
| 5 | convergence_planner.md | 4/10 | 合并示例全软件（Redis/Memcached/PostgreSQL）；验证命令curl/wrk |
| 6 | planning_planner.md | 5/10 | 约束维度偏软件（安全/性能/可用性）；示例GDPR/TLS |
| 7 | planning_expert_base.md | 5/10 | 示例约束全软件（TLS 1.3 + AES-256-GCM） |
| 8 | review_layer_b.md | 5/10 | 可操作性检查示例用软件命令 |
| 9 | fixer_expert_harness.md | 5/10 | 修复流程用软件术语（重构/性能瓶颈/回归测试） |
| 10 | research_expert_base.md | 5/10 | 示例用软件术语（TLS/10万WebSocket并发） |
| 11 | research_planner.md | 6/10 | 领域分析枚举偏软件（架构密集？安全敏感？） |
| 12 | planning_module.md | 6/10 | 框架通用，Phase 0搜索偏技术标准 |
| 13 | research_module.md | 6/10 | 框架通用，"技术推荐"措辞隐含软件假设 |
| 14 | summary_summarizer.md | 6/10 | 文档大纲偏软件（架构设计/技术选型） |
| 15 | summary_base_synthesizer.md | 6/10 | 输出模板偏软件（架构设计/技术选型含方案对比表格） |
| 16-33 | 其他prompt | 6-8/10 | 基本泛化，微调即可 |
| 34 | ai_native_cognitive_base.md | 9/10 | 完全领域无关 ✅ |
| 35 | compliance_checker_base.md | 9/10 | 完全领域无关 ✅ |

## 三大系统性问题

### 问题 1: 示例层硬编码（最严重，影响 12 个 prompt）
LLM 模仿示例生成输出 → 即使指令通用，软件示例也导致软件化输出。
- 修复：多领域示例（软件+投资+商业）或参数化占位符

### 问题 2: 枚举层硬编码（中等，影响 6 个 prompt）
domain分类、方案类型、约束维度写死为软件概念。
- 修复：改为"LLM推断+约束"模式

### 问题 3: 验证方法绑定（中等，影响 5 个 prompt）
verification_method 示例全软件命令（curl/psql/wrk/ESLint）。
- 修复：多领域验证方法示例

## 泛化性良好的部分（13 个 prompt，评分 7+）
- Summary 模块下游 prompt（analyzer_base, refiner, fix_agent, fix_judge）
- ai_native_cognitive_base.md / compliance_checker_base.md
- orchestrator.md（流程编排通用）
- 各 harness 评审 prompt（框架通用，示例略偏）
