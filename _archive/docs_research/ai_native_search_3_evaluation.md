# AI 输出质量评估方法论研究（2025-2026）

> 研究时间：2026-06-18 | 聚焦：LLM-as-Judge、Eval-Driven Development、Agent 完成标准

---

## 1. LLM-as-Judge：有效性与局限性

**核心洞察**：评估比生成容易。LLM 作为评判者，本质是用一个外部 LLM 执行分类/判别任务，而非重新生成内容。这使其比开放式生成更可靠。[来源：Evidently AI, 2025]

**何时有效**：
- **判别任务**：成对比较（A vs B 哪个更好）、分类（正确/错误/矛盾）、按特定标准打分
- **有明确 rubric**：提供清晰的评分维度和具体示例（few-shot），LLM 评判者一致性可达 85%+
- **外部模型评判**：用更强的模型（如 Claude Sonnet）评估较弱模型的输出，减少自我偏好偏差

**何时失效**：
- **自我偏好偏差**：LLM 倾向给同模型家族的输出更高分
- **冗长偏差**：更长的回答常被评更高分，即使内容质量相同
- **Prompt 敏感**：微小的 prompt 变化导致评分剧烈波动
- **风格 > 实质**：LLM 评判者可能被格式和文风迷惑，忽视事实准确性
- **1-10 评分尺度失效**：容易导致"均值回归"，应改用离散类别（如"完全正确/不完整/矛盾"）

[来源：Evidently AI LLM-as-Judge Guide; Agenta AI 2025]

---

## 2. AI 输出质量的自动化度量方式

**三层评估体系**（Anthropic 2026 推荐）：

| 评估类型 | 特点 | 适用场景 |
|---------|------|---------|
| **Code-based grader** | 快速、客观、确定性 | 格式检查、长度约束、结构化输出验证 |
| **Model-based grader** | 灵活、处理细微差别、非确定性 | 语义正确性、语气、连贯性 |
| **Human grader** | 金标准、昂贵、慢 | 校准自动化指标、边界案例 |

**关键原则**：三者组合使用，不是二选一。用人类标注校准自动化指标，定期计算 agreement rate。

**可自动化的具体指标**：
- 事实忠实度（Faithfulness）：输出是否与提供的上下文一致
- 工具选择准确率：Agent 是否选择了正确的工具
- 幻觉率：输出中事实性错误的比例
- 上下文召回率/精确率：RAG 系统的检索质量
- 策略遵循率：输出是否符合定义的安全/操作策略

[来源：Anthropic "Demystifying Evals for AI Agents", Jan 2026]

---

## 3. Evaluation-Driven Development（评估驱动开发）

**Anthropic 核心主张**：先创建评估，再让 Agent 通过评估。评估定义成功标准，不是事后验证。

**OpenAI 的 Eval-Driven 开发流程**：
1. **定义评估目标**：成功标准是什么（具体、可量化）
2. **收集数据集**：混合生产数据 + 专家标注 + 历史日志 + 边界案例
3. **定义评估指标**：如何验证成功标准被满足
4. **运行并比较**：迭代改进
5. **持续评估（CE）**：每次变更触发评估套件，监控非确定性，随时间扩展测试集

**反模式**（OpenAI 明确警告）：
- ❌ 过度依赖通用学术指标（perplexity、BLEU）
- ❌ 有偏的数据集设计（不反映真实流量分布）
- ❌ "Vibe-based evals"：凭感觉"好像能用"就算通过
- ❌ 忽略人类反馈，不校准自动化指标

[来源：OpenAI "Evaluation Best Practices" Guide, 2025; Anthropic Agent Evals Blog, Jan 2026]

---

## 4. Anthropic/OpenAI 的 AI Eval 最佳实践

**Anthropic 2026 要点**：
- **处理非确定性**：Agent 行为不确定，用 `pass@k`（k 次中至少通过 1 次）和 `pass^k`（k 次全部通过）两个指标
- **Trace-Driven Evaluation**：对复杂 Agent 工作流，追踪决策链、工具调用、guardrails、handoffs，然后对 trace 评分
- **大模型评小模型**：用 Claude Sonnet 3.7 增强对 Haiku 等小模型的评估覆盖
- **联合评估**：Anthropic 与 OpenAI 2025 年首次交叉评估对方模型的安全性

**OpenAI 2025 要点**：
- **按架构分层评估**：单轮交互 → 工作流 → 单 Agent → 多 Agent，复杂度递增，非确定性入口不同
- **用 gpt-5.5 生成评估数据**：利用强模型生成多样化测试数据（常规案例 + 边界案例 + 对抗案例）
- **LLM 擅长判别而非生成**：评估应聚焦于成对比较、分类、按标准打分，而非开放式生成评估

[来源：Anthropic "Demystifying Evals" Jan 2026; OpenAI "Evaluation Best Practices" 2025; OpenAI-Anthropic Joint Safety Evaluation Aug 2025]

---

## 5. AI Agent 的"Done"标准

**Agent 怎么知道做完了？— 不是人类说 done，而是系统自己验证**

**多维度完成标准框架**：

| 维度 | 指标 | 目标参考值 |
|------|------|-----------|
| **目标达成** | 任务完成率（无人干预） | 结构化任务 85-95% |
| **输出质量** | 事实正确率 / 幻觉率 | 幻觉率 < 5% |
| **工具使用** | 工具选择准确率 + 执行成功率 | > 90% |
| **策略遵循** | Guardrail 验证通过率 | 100%（硬约束） |
| **一致性** | 多次运行结果可靠性 | pass^k 指标 |
| **延迟** | 端到端响应时间 | 对话式 < 800ms |

**"Done" 的操作性定义**：
1. **功能完成**：任务目标的所有子项已执行并验证
2. **质量达标**：输出通过预定义的自动化评估（code-based + model-based grader）
3. **无回归**：与基线评估集对比，没有性能下降
4. **策略合规**：所有安全/操作 guardrail 通过
5. **可追溯**：决策 trace 可审计，每步推理有据可查

**关键洞察**：Agent 的"done"不是一个二元状态，而是一个多维向量。每个维度有独立的阈值，全部达标才算 done。这比人类 PM 拍脑袋说"好了"更可靠。

[来源：OpenAI Agent Evals Guide 2025; W&B "AI Agent Evaluation" 2025; Anthropic Agent Evals Blog 2026]

---

## 核心结论

1. **LLM-as-Judge 有效但有条件**：需要清晰的 rubric、离散类别（非数值尺度）、外部模型评判、人类校准。不能盲信。

2. **评估必须是三层的**：Code-based（快/确定性）+ Model-based（灵活/语义）+ Human（校准/边界）。单一层次不够。

3. **Eval-Driven 是正确顺序**：先写评估 → 再开发系统。评估定义"done"，不是事后检查。

4. **Agent 的"done"是多维向量**：功能完成 + 质量达标 + 无回归 + 策略合规 + 可追溯。每个维度可自动化验证。

5. **持续评估 > 一次性评估**：每次变更触发评估套件，生产环境持续监控，测试集随新失败模式扩展。

---

## 来源索引

| # | 来源 | 类型 | 时间 |
|---|------|------|------|
| 1 | [Evidently AI - LLM-as-a-Judge Complete Guide](https://www.evidentlyai.com/llm-guide/llm-as-a-judge) | 技术指南 | 2025 |
| 2 | [Anthropic - Demystifying Evals for AI Agents](https://www.anthropic.com/research) | 官方博客 | 2026-01 |
| 3 | [OpenAI - Evaluation Best Practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices) | 官方文档 | 2025 |
| 4 | [OpenAI - Agent Evals Guide](https://developers.openai.com/api/docs/guides/agent-evals) | 官方文档 | 2025 |
| 5 | [OpenAI-Anthropic Joint Safety Evaluation](https://openai.com/index/openai-anthropic-safety-evaluation/) | 联合报告 | 2025-08 |
