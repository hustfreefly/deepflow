# AI Agent 架构研究：多 Agent 协作与质量保证（2025-2026）

> 研究时间：2026-06-18 | 来源：综合 3 组搜索，覆盖 Microsoft、LangChain、OpenAI、Google、SonarSource 等

---

## 1. Agent 分工：按能力分，不按岗位分

**核心结论**：2025 年的最佳实践已明确抛弃"模拟人类岗位"的角色设计，转向**按认知能力分工**。

主流模式：
- **Orchestrator-Worker（编排者-执行者）**：一个编排 Agent 负责分解任务、路由、验证；多个 Worker Agent 按专长执行。编排者的核心能力是**任务分解 + 质量验证**，不是"项目管理"。（来源：Microsoft AI Agent Design Patterns, Google Vertex AI）
- **Handoff / Router 模式**：Agent 评估任务后决定"自己做 or 转给更合适的 Agent"。分工依据是**领域专长匹配度**，不是层级关系。（来源：LangChain, dev.to 2025 架构指南）
- **Skills 模式（轻量替代）**：单 Agent 动态加载不同 prompt/知识，模拟多角色。适合复杂度不高的场景，避免多 Agent 的通信开销。（来源：Google Agent Patterns）

**关键洞察**：分工的本质是**上下文隔离 + 专长注入**。每个 Agent 应该是一个独立的认知单元，有明确的输入/输出契约，而不是"扮演某个职位"。

---

## 2. 评审/验证：分层质量门（Quality Gates）

**核心结论**：2025 年共识是**多层自动化验证 + 关键节点人类介入**，不是二选一。

验证分层：
1. **运行时自动门控**：每个 Agent 输出先过质量门——置信度、格式合规、事实一致性检查，然后才能传递给下游。这是"验证前置"，区别于事后评估。（来源：SonarSource "Quality Gate for Agentic AI", EU AI Act 2025 合规要求）
2. **LLM-as-Judge**：用另一个 LLM 评估输出质量。OpenAI 的 Self-Evolving Agents 框架将此与人类判断结合，形成混合评审。（来源：OpenAI Cookbook, 2025）
3. **人类介入点（HITL）**：在高风险决策、模糊边界、跨域冲突处设置人类检查点。LangGraph 原生支持 checkpoint + replay，让人类可以在任意节点介入。（来源：LangGraph 文档, ZenML 对比分析）

**关键洞察**：质量门不是"评审环节"，而是**运行时强制执行的约束条件**。Agent 无法绕过质量门，就像 CI/CD 无法绕过测试。

---

## 3. Prompt 专家角色：不是"项目经理"，是"认知架构师"

**核心结论**：搜索中未直接出现"Prompt 工程师"角色定义，但从架构模式可推导出正确角色。

最佳实践中的角色定义：
- **编排 Agent 的 prompt**：定义任务分解策略、路由规则、验证标准。本质是**系统约束设计者**，不是"项目经理"。
- **Worker Agent 的 prompt**：定义领域专长边界、输入/输出格式、失败处理策略。本质是**认知能力封装者**。
- **质量门 Agent 的 prompt**：定义验证维度、通过/失败阈值、反馈格式。本质是**质量标准定义者**。

**关键洞察**：Prompt 专家的正确角色是**认知架构师（Cognitive Architect）**——设计每个 Agent 的认知边界、输入输出契约、失败模式，而不是写"你是一个项目经理"这样的角色描述。

---

## 4. 反馈闭环：收敛性设计

**核心结论**：死循环是多 Agent 系统的头号故障模式。2025 年的解决方案是**显式收敛机制**。

防死循环策略：
- **收敛分数（Convergence Score）**：监控 Agent 是否在可接受步数内达成目标。如果决策序列出现重复模式，判定为未收敛，强制终止。（来源：Turing College "Evaluating AI Agents", 2025）
- **Reflexion 模式**：Agent 将失败转化为程序性知识，下次迭代时应用。关键是**失败→学习→应用**的单向链，不是"重试直到成功"。（来源：LangChain Agent Improvement Loop）
- **Trace-Driven 改进**：用执行轨迹（trace）记录 Agent 实际行为，基于 trace 做针对性改进，而不是盲目调整 prompt。（来源：LangChain, 2025）
- **最大迭代次数 + 降级策略**：硬超时保护，超时后降级到单 Agent 或人类介入。（来源：OpenClaw 实践，与业界共识一致）

**关键洞察**：反馈闭环的目标是**收敛**，不是"持续改进"。每次反馈必须让系统状态更接近目标，否则就是死循环的伪装。

---

## 5. 多 Agent vs 单 Agent：决策标准

**核心结论**：多 Agent 不是默认选择。2025 年共识是**简单场景用单 Agent + Skills，复杂场景才上多 Agent**。

用多 Agent 的场景：
- 任务需要**多个不同领域的专长**，且单个 context window 装不下
- 需要**并行处理**多个独立子任务
- 需要**强上下文隔离**（避免不同领域的知识互相污染）
- 需要**不同的模型/配置**处理不同子任务

用单 Agent 的场景：
- 任务在单个 context window 内可完成
- 子任务之间**高度耦合**，需要频繁共享上下文
- 延迟敏感（多 Agent 的通信开销显著）
- 成本敏感（多 Agent 的 token 消耗成倍增加）

**关键洞察**：Skills 模式（单 Agent 动态加载专长）是多 Agent 的**轻量替代**。先试 Skills，不够再用多 Agent。（来源：Google Agent Patterns）

---

## 来源索引

| # | 来源 | 类型 | 关键内容 |
|---|------|------|----------|
| 1 | Microsoft AI Agent Design Patterns (learn.microsoft.com) | 架构指南 | Orchestrator-Worker、Hierarchical、Blackboard 模式 |
| 2 | Google Vertex AI Agent Patterns | 设计模式 | Coordinator/Dispatcher、Adaptive Agent Network、Skills 模式 |
| 3 | LangChain / LangGraph 文档 | 框架实践 | Agent Improvement Loop、Trace-Driven 改进、HITL checkpoint |
| 4 | OpenAI Self-Evolving Agents Cookbook | 框架实践 | LLM-as-Judge + 人类混合评审、迭代改进 |
| 5 | SonarSource Quality Gate for Agentic AI | 质量保证 | 运行时质量门、自动化验证标准 |

---

## 对 DeepFlow 的启示

1. **角色定义**：将"项目经理/产品经理"等人类岗位描述，替换为"编排者/执行者/验证者"等认知能力描述
2. **质量门**：在 Agent 输出传递前强制验证，不是事后评审
3. **收敛保护**：所有反馈闭环必须有最大迭代次数 + 降级策略
4. **默认单 Agent**：先用 Skills 模式，只在复杂度超标时才拆分为多 Agent
