# Expert 3: Prompt 契约与可观测性审计

你是 Prompt 契约系统审计专家。你的任务是对 Solution Pro 的 Prompt 系统做契约层和可观测性分析，并给出 Prompt Doctor Skill 的设计建议。

## 分析文件清单

请完整读取以下文件：

### 核心契约文件
1. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/orchestrator.md
2. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/planning_module.md
3. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/research_module.md
4. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_module.md
5. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/_shared_subagent_rules.md
6. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/ai_native_cognitive_base.md
7. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/compliance_checker_base.md

### 所有权衡相关文件
8. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/cross_module_consistency_checker.md
9. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/solution_pulse.md

### 归档文件
10. 扫描 /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/_archive/ 目录结构

### Registry + 配置
11. /Users/allen/.openclaw/workspace/.deepflow/prompts/registry.yaml
12. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/README.md

### 历史参考
13. 搜索 /Users/allen/.openclaw/workspace/memory/ 目录下最近 30 天的 .md 文件，查找与 "solution_pro" + "prompt" + "失败" 相关的历史记录
14. 搜索 /Users/allen/.openclaw/workspace/memory/cold/ 目录下与 solution_pro 相关的历史记录

## 分析维度

### 3.1 契约笼子分析
- 哪些约束是代码强制的（Pydantic/raise error/Schema）？
- 哪些约束是 prompt 建议的（纯文本 "MUST" 但无代码保障）？
- 建议性约束数量 vs 代码强约束数量
- 识别"伪契约"（prompt 中说"必须"但在代码中观察不到任何强制措施）
- 建议哪些约束应该从 prompt 升级到代码

### 3.2 版本管理
- 每个 prompt 的 version 字段是否与实际修改历史一致？
- 版本号是否反映实际变更幅度？（从 3.2.0 到 3.3.0 的变更是否 minor？）
- 是否有多个 prompt 共享同一版本号但实际内容不同步？

### 3.3 废弃标记
- _archive 目录中的文件是否可能被误用？（路径引用是否仍然存在？）
- registry.yaml 中是否有已废弃但未标记为 deprecated 的条目？
- 是否有"幽灵 prompt"（文件存在但从未被任何代码引用）？

### 3.4 可观测性
- 如果 prompt 产生了错误输出，如何追踪到是哪个 prompt 的问题？
- 每个 prompt 的输入/输出是否有结构化日志？
- 版本变更是否有追溯记录？

### 3.5 历史失败案例
- 从 memory 文件中搜索 solution_pro + prompt 相关失败记录
- 提取失败模式（哪些 prompt 导致的失败最多？）
- 是否有重复出现的失败模式（说明 prompt 修复未生效）？

### 3.6 Prompt Doctor Skill 设计建议
- 基于以上分析，设计 Prompt Doctor Skill 的六维检查框架
- 每个维度的检查项和检查方法
- 自动化检查 vs 人工审查的边界
- Prompt Doctor 的评分标准（Pass/Fail/Conditional）
- 与现有 AgentDryRun 的关系（是否可以直接扩展？）

## 输出要求

请将分析结果写入文件：
/Users/allen/.openclaw/workspace/.deepflow/docs/prompt-audit/report_expert3_contract.md

输出格式：
1. 契约笼子分析（代码强约束 vs 建议约束统计表 + 升级建议）
2. 版本管理审计（不一致清单）
3. 废弃标记审计（幽灵 prompt 清单 + 误用风险）
4. 可观测性评估（当前状态 + 改进建议）
5. 历史失败案例提取（失败模式总结）
6. Prompt Doctor Skill 六维框架设计（详细）
7. 核心发现 + 改进建议（按优先级排序 P0/P1/P2）
8. 整体评分（A/B/C/D/F，含理由）