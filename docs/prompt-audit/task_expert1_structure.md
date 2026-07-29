# Expert 1: Prompt 结构审计

你是 Prompt 系统架构审计专家。你的任务是对 Solution Pro 的 Prompt 系统做结构层深入分析。

## 分析文件清单

请完整读取以下文件（按优先级排序）：

### 核心文件（必读）
1. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/README.md
2. /Users/allen/.openclaw/workspace/.deepflow/prompts/registry.yaml
3. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/orchestrator.md
4. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/planning_module.md
5. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/research_module.md
6. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/summary_module.md

### 基础层文件
7. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/_shared_subagent_rules.md
8. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/ai_native_cognitive_base.md

### 配置文件
9. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/compliance_checker_base.md
10. /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/cross_module_consistency_checker.md

### 归档文件（抽样检查）
11. 扫描 /Users/allen/.openclaw/workspace/.deepflow/domains/solution_pro/prompts/_archive/ 目录，确认哪些文件是真正废弃的

## 分析维度

### 1.1 依赖关系图
- 绘制 Prompt 之间的调用/依赖关系（谁 spawn 谁，谁读谁的输出）
- 识别循环依赖或隐式依赖
- 标注信息流路径（哪些 prompt 在信息传递链上，传递了什么）

### 1.2 信息流完整性
- 从 Orchestrator → Module Agent → Worker，信息是否逐层传递完整？
- 是否有信息在传递过程中丢失或变形？
- 变量注入（{session_id}, {deepflow_root}）是否正确覆盖所有 prompt？
- 识别"注入但不消费"的变量（prompt 中声明了但 Worker 实际不读取）

### 1.3 职责边界
- 每个 prompt 的职责是否清晰？是否有重叠？
- 是否有多余的 prompt（功能重复/被废弃但未移除）？
- 是否有职责缺失（某个关键步骤没有对应的 prompt）？

### 1.4 Registry 准确性
- registry.yaml 中的条目是否与实际文件一一对应？
- 是否有 registry 中有但文件不存在的情况？
- 是否有文件存在但 registry 中未注册的情况？
- changelog 是否与实际文件版本号一致？

### 1.5 代码嵌入比例
- 统计每个 prompt 中 Python 代码占整个 prompt 的比例
- 代码嵌入 vs 纯 prompt 指令的比例
- 代码嵌入是否淹没了真正的 prompt 指令？

## 输出要求

请将分析结果写入文件：
/Users/allen/.openclaw/workspace/.deepflow/docs/prompt-audit/report_expert1_structure.md

输出格式：
1. 依赖关系图（Mermaid 或文字描述）
2. 信息流分析（逐层检查，标注断裂点）
3. 职责边界分析（重叠/遗漏/冗余）
4. Registry 准确性报告（不匹配清单）
5. 代码嵌入比例统计
6. 核心发现 + 改进建议（按优先级排序 P0/P1/P2）
7. 整体评分（A/B/C/D/F，含理由）