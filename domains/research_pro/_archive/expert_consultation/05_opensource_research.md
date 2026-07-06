# 开源项目与技术调研：LLM 自动化研究报告生成

> 调研时间：2026-01  
> 调研范围：GitHub 开源项目、学术论文、技术博客、产品文档  
> 关键词：deep research, automated research report, LLM research agent, structured report generation

---

## 核心发现摘要

### 最佳开源 Deep Research 项目架构

1. **GPT Researcher** (27.5k+ stars)
   - 架构：多 Agent 系统 + Plan-and-Solve 模式
   - 核心组件：Planner Agent → Execution Agents → Crawler Agents → Summarizer → Reviewer → Writer
   - 特点：并行信息收集、迭代审查、确定性结果

2. **STORM (Stanford)** (开源，NAACL 2024)
   - 架构：两阶段流程（Pre-writing + Writing）+ 多视角问答
   - 核心创新：模拟对话（Wikipedia writer ↔ Topic expert）、视角发现机制
   - 特点：生成 Wikipedia 级别文章、99% 事实准确率（Co-STORM）

3. **LlamaIndex Research Agents**
   - 架构：事件驱动的多 Agent 工作流（Workflows 1.0）
   - 组件：ResearchAgent → WriteAgent → ReviewAgent
   - 特点：自反思循环、AgentWorkflow 自动重试、LlamaReport 结构化输出

4. **AutoGen (Microsoft)**
   - 架构：异步事件驱动的多 Agent 协作框架
   - 特点：灵活的 Agent 角色定义、Human-in-the-Loop、工具集成
   - 适用：复杂工作流编排、内容生成管线

5. **Tavily Research API**
   - 架构：Agent-in-a-Box + 模块化端点（/search, /extract, /crawl, /research）
   - 特点：JSON Schema 自定义输出、结构化提示、Agent 原生防火墙
   - 优势：实时数据、grounding 技术、token 优化（reflections 机制）

---

## 详细项目分析

### 1. GPT Researcher

**GitHub**: https://github.com/assafelovic/gpt-researcher  
**Stars**: ~27,500-27,600 (2025-2026)  
**文档**: https://docs.gptr.dev

#### 核心架构

```
用户查询
  ↓
Planner Agent (生成研究问题大纲)
  ↓
多个 Execution Agents (并行执行)
  ↓
Crawler Agents (抓取在线资源)
  ↓
Summarization Module (总结 + 来源追踪)
  ↓
Filtering & Aggregation (过滤 + 聚合)
  ↓
Reviewer Agent (验证正确性) → Revisor Agent (修订)
  ↓
Writer Agent (生成最终报告)
  ↓
Publisher (输出格式：Markdown/PDF/HTML)
```

#### 关键技术特性

1. **Plan-and-Solve 模式**
   - 基于论文 "Plan-and-Solve Prompting"
   - 避免无限循环，确保确定性结果
   - 问题分解 → 并行求解 → 聚合总结

2. **Deep Research 功能**
   - 递归工作流，树状探索模式
   - 广度 + 深度探索结合
   - 适合复杂、多层次研究主题

3. **多模型混合**
   - `gpt-4o-mini`（快速、低成本）+ `gpt-4o`（复杂推理）
   - 根据任务复杂度动态选择模型

4. **MCP 集成**
   - 连接 GitHub、数据库、自定义 API
   - 混合研究（Web + 本地文档）

5. **内联图像生成**
   - 使用 Google Gemini 自动生成插图
   - 嵌入研究报告中

#### 质量保证机制

- **Reviewer-Revisor 循环**：Reviewer 验证事实准确性，Revisor 根据反馈修订
- **来源追踪**：所有信息保留原始来源引用
- **并行验证**：多个 Execution Agent 独立收集信息，交叉验证
- **过滤机制**：自动过滤低质量或不相关来源

#### 可复用技术方案

```python
# 核心设计模式
1. 多 Agent 角色分离（Planner/Researcher/Reviewer/Writer）
2. 并行信息收集（asyncio + 多 Crawler）
3. 迭代审查循环（Reviewer → Revisor → 直到通过）
4. 来源追踪（每个摘要保留 URL + 标题）
5. 分层 LLM 调用（简单任务用小模型，复杂推理用大模型）
```

---

### 2. STORM (Stanford OVAL Lab)

**GitHub**: https://github.com/stanford-oval/storm  
**论文**: "STORM: Synthesis of Topic Outlines through Retrieval and Multi-perspective Question Asking" (NAACL 2024)  
**变体**: Co-STORM (EMNLP 2024) - 人机协作版本

#### 核心架构

```
阶段 1: Pre-writing (预写作)
  ├─ 视角发现 (Perspective Discovery)
  │   └─ 分析现有 Wikipedia 文章，提取不同观点
  ├─ 多视角问答 (Multi-perspective Question Asking)
  │   ├─ 模拟对话：Wikipedia Writer ↔ Topic Expert
  │   ├─ 每个视角生成问题
  │   └─ 基于检索结果动态调整问题
  └─ 大纲合成 (Outline Synthesis)
      └─ 整合信息 + 内部知识 → 结构化大纲

阶段 2: Writing (写作)
  ├─ 基于大纲填充内容
  └─ 插入引用（来自检索来源）
```

#### 关键技术特性

1. **多视角发现机制**
   - 自动识别主题的多个 viewpoints
   - 通过 survey 现有文章发现不同立场
   - 避免单一视角偏见

2. **模拟对话**
   - Wikipedia Writer：提出问题，尝试理解
   - Topic Expert：基于检索结果回答
   - 多轮迭代，逐步深入

3. **Grounded Information**
   - 所有问题基于检索到的互联网来源
   - 避免幻觉，确保事实性
   - 引用可追溯

4. **模块化设计**
   - 可替换 LLM（OpenAI/Anthropic/Mistral）
   - 可替换 Retriever（You.com/Bing/自定义）
   - 支持本地文档 grounding

5. **Co-STORM 增强**
   - 人机协作：人类可介入对话
   - 动态 Mind Map：层次化概念结构
   - Moderator Agent：引导对话方向
   - 99% 事实准确率

#### 质量保证机制

- **多视角覆盖**：强制要求多个 viewpoints，避免片面
- **检索 grounding**：所有信息基于真实来源
- **迭代问答**：多轮对话逐步完善理解
- **大纲审查**：先生成大纲，再生成全文，确保结构合理
- **引用验证**：每个事实都有来源引用

#### 可复用技术方案

```python
# 核心设计模式
1. 两阶段流程（Pre-writing → Writing）
2. 视角发现算法（从现有文章提取 viewpoints）
3. 模拟对话机制（Writer ↔ Expert 多轮交互）
4. 大纲优先（先生成结构化大纲，再填充内容）
5. 检索 grounding（所有问题基于检索结果）
6. Mind Map 可视化（Co-STORM 的层次化概念图）
```

---

### 3. LlamaIndex Research Agents

**文档**: https://developers.llamaindex.ai  
**关键组件**: Workflows 1.0 (2025-06), LlamaReport (2024-12 beta, 2025 Q1 GA)

#### 核心架构

```
ResearchAgent (信息收集)
  ↓
WriteAgent (草稿生成)
  ↓
ReviewAgent (评审 + 反馈)
  ↓
[循环直到质量达标]
  ↓
最终报告
```

#### 关键技术特性

1. **Workflows 1.0**
   - 异步、事件驱动架构
   - 支持复杂路由、并行处理
   - 可观测性（LangSmith 集成）

2. **AgentWorkflow**
   - 自反思循环
   - 自动重试机制（质量不达标时重新执行）
   - 支持多 Agent 协作

3. **LlamaReport**
   - 智能文档处理（LlamaParse）
   - 灵活模板系统
   - 结构化输出（JSON/Markdown/PDF）

4. **多模态报告**
   - 文本 + 图像交错
   - LlamaParse 高分辨率 OCR
   - 适合 PDF、幻灯片、财务报告

5. **Pydantic Programs**
   - 结构化输出（JSON objects, DataFrames）
   - 类型安全
   - 可验证的 schema

#### 质量保证机制

- **ReviewAgent 反馈循环**：评审草稿，提供改进建议
- **自反思**：Agent 评估自己的输出，决定是否需要重新执行
- **结构化验证**：Pydantic schema 确保输出格式正确
- **可观测性**：LangSmith 追踪每一步，便于调试

#### 可复用技术方案

```python
# 核心设计模式
1. 事件驱动工作流（Workflows 1.0）
2. 多 Agent 角色分离（Research/Write/Review）
3. 自反思循环（Agent 评估自己的输出）
4. Pydantic 结构化输出（类型安全 + 验证）
5. LlamaParse 文档解析（保留结构、表格、图表）
```

---

### 4. AutoGen (Microsoft Research)

**GitHub**: https://github.com/microsoft/autogen  
**版本**: 0.4 (2025-01) - 异步事件驱动架构

#### 核心架构

```
Multi-Agent System
  ├─ AssistantAgent (执行任务)
  ├─ UserProxyAgent (人机交互)
  ├─ GroupChat (多 Agent 协作)
  └─ Tools (外部工具集成)
```

#### 关键技术特性

1. **异步事件驱动**
   - 高可扩展性
   - 支持动态工作流
   - 适合复杂、长时间运行的任务

2. **灵活的角色定义**
   - 可自定义 Agent 行为
   - System prompt 驱动
   - 支持 specialized agents（Researcher/Writer/Critic）

3. **Human-in-the-Loop**
   - UserProxyAgent 可介入关键决策
   - 适合需要人工审核的场景
   -  ethical considerations

4. **工具集成**
   - Web search、databases、APIs
   - Code execution（安全沙箱）
   - File I/O

5. **AutoGen Studio**
   - 低代码界面
   - 快速原型设计
   - 可视化 Agent 交互

#### 质量保证机制

- **Critic Agent**：验证内容准确性
- **Human review**：关键节点人工审核
- **Tool validation**：外部工具提供事实核查
- **Iterative refinement**：多轮对话逐步完善

#### 可复用技术方案

```python
# 核心设计模式
1. 异步事件驱动架构（适合长时间任务）
2. 灵活角色定义（System prompt 驱动）
3. Human-in-the-Loop（关键决策点）
4. GroupChat 多 Agent 协作
5. 工具集成（Web search/DB/API）
```

---

### 5. Tavily Research API

**文档**: https://docs.tavily.com  
**产品**: Chat Research (https://chat-research.tavily.com)

#### 核心架构

```
Modular Endpoints
  ├─ /search (语义搜索 + AI 答案)
  ├─ /extract (URL 内容提取)
  ├─ /crawl (站点级内容发现)
  └─ /research (Agent-in-a-Box)
      ├─ 多次迭代搜索
      ├─ 推理 + 去重
      └─ 多 Agent 协调
```

#### 关键技术特性

1. **Agent Harness**
   - 软件层增强 LLM 运行时
   - 上下文管理、工具调用、循环控制
   - **Reflections 机制**：蒸馏工具输出为 reflections，而不是携带所有历史 tokens
   - 显著降低 token 消耗

2. **Grounding 技术**
   - 从验证过的 URL 提取 ground truth
   - 处理歧义实体（同名不同人/物）
   - 确保准确性

3. **JSON Schema 自定义**
   - 用户可定义输出 schema
   - 字段描述、数据类型、枚举
   - 确保输出符合应用需求

4. **结构化提示**
   - 保证输出一致性
   - 可靠、组织良好的结果
   - 避免格式不一致

5. **Agent 原生防火墙**
   - 防止 prompt injection
   - 数据泄露保护
   - 安全的研究工作流

6. **输出格式**
   - Structured Output（JSON，适合 pipeline/UI）
   - Report（Markdown/PDF，适合人类阅读）
   - CLI 支持 `--json` flag

#### 质量保证机制

- **Grounding**：从可信来源建立 ground truth
- **Relevance scoring**：搜索结果包含相关性分数
- **Feedback loops**：可选 human-in-the-loop 验证
- **Deduplication**：自动去重
- **Structured validation**：JSON Schema 验证输出

#### 可复用技术方案

```python
# 核心设计模式
1. Reflections 机制（蒸馏工具输出，降低 token 消耗）
2. Grounding 技术（从可信 URL 建立 ground truth）
3. JSON Schema 自定义输出（类型安全 + 验证）
4. 模块化端点（search/extract/crawl/research）
5. Agent 原生防火墙（安全防护）
6. 双输出模式（Structured Output vs Report）
```

---

### 6. 学术论文

#### 6.1 STORM (NAACL 2024)

**论文**: "STORM: Synthesis of Topic Outlines through Retrieval and Multi-perspective Question Asking"  
**作者**: Stanford OVAL Lab  
**链接**: https://storm-project.stanford.edu/research/storm/

**核心贡献**:
1. **两阶段流程**：Pre-writing（研究 + 大纲）→ Writing（填充 + 引用）
2. **多视角问答**：自动发现多个 viewpoints，生成多样化问题
3. **模拟对话**：Wikipedia Writer ↔ Topic Expert，基于检索的迭代问答
4. **大纲合成**：整合检索信息 + LLM 内部知识

**评估结果**:
- 超越传统 RAG baseline
- 经验丰富的 Wikipedia 编辑认为有用
- 生成的文章结构完整、引用丰富

**局限**:
- 来源偏见风险
- 过度关联不相关事实的风险

---

#### 6.2 Co-STORM (EMNLP 2024)

**论文**: "Co-STORM: Collaborative Knowledge Curation"  
**核心创新**: 人机协作知识管理

**关键技术**:
1. **多 Agent 类型**：Co-STORM experts + Moderator agent
2. **Human-in-the-Loop**：人类可引入新视角、引导对话
3. **动态 Mind Map**：层次化概念结构，降低认知负荷
4. **协作话语协议**：结构化的对话流程

**评估结果**:
- 99% 事实准确率
- 人类偏好优于传统搜索引擎和 RAG chatbot
- 更好的组织性和主题覆盖

---

#### 6.3 AutoSurvey (NeurIPS 2024)

**论文**: "AutoSurvey: Large Language Models Can Automatically Write Surveys"  
**作者**: Yidong Wang et al.  
**链接**: https://arxiv.org/abs/2406.10252

**核心贡献**:
1. **自动化文献综述生成**
2. **系统流程**：
   - 初始检索
   - 大纲生成
   - 子章节起草（专门 LLM）
   - 整合 + 细化
   - 严格评估

**解决的问题**:
- 上下文窗口限制
- 参数化知识约束
- 快速演进领域的综述更新

---

#### 6.4 AutoSurvey2 (2025-10)

**论文**: "AutoSurvey2: Empowering Researchers with Next Level Automated Literature Surveys"  
**核心改进**:
1. **多阶段管线**
2. **并行章节生成**
3. **迭代细化**
4. **实时检索最新论文**
5. **结构化评估**

**特点**:
- 确保主题完整性
- 事实准确性验证
- 适合快速演进领域

---

#### 6.5 SurveyPilot (ACL 2025)

**论文**: "SurveyPilot: An Agentic Framework for Automated Human Opinion Collection from Social Media"  
**作者**: Viet Thanh Pham et al.  
**链接**: https://aclanthology.org/2025.acl-long.221/

**核心贡献**:
1. **有限状态编排的 Agent 框架**
2. **社交媒体意见收集**
3. **透明性和可追溯性**
4. **偏见缓解**：遗传算法提高结果多样性
5. **与真实调查结果对齐**

**特点**:
- 不同于研究报告生成，专注于人类意见收集
- 适合社会科学研究

---

## 架构对比

| 项目 | 架构类型 | 迭代机制 | 质量保证 | 结构化输出 | 开源 | Stars |
|------|---------|---------|---------|-----------|------|-------|
| GPT Researcher | 多 Agent + Plan-and-Solve | Reviewer-Revisor 循环 | 多 Agent 验证 + 来源追踪 | Markdown/PDF | ✅ | 27.5k |
| STORM | 两阶段 + 多视角问答 | 模拟对话迭代 | 多视角覆盖 + Grounding | Wikipedia 格式 | ✅ | - |
| LlamaIndex | 事件驱动工作流 | 自反思循环 | ReviewAgent + Pydantic | JSON/Markdown/PDF | ✅ | - |
| AutoGen | 异步事件驱动 | 多轮对话 | Critic + Human review | 自定义 | ✅ | - |
| Tavily | 模块化端点 | /research 迭代搜索 | Grounding + Schema 验证 | JSON/Markdown | ❌ (API) | - |

---

## 核心问题解答

### Q1: 最好的开源 deep research 项目用了什么架构？

**答案**: 最佳实践是 **多 Agent 系统 + 迭代审查循环**

典型架构：
```
1. Planner Agent (问题分解 + 大纲生成)
2. 多个 Researcher Agents (并行信息收集)
3. Reviewer Agent (质量评审)
4. Revisor Agent (根据反馈修订)
5. Writer Agent (最终报告生成)
```

关键设计模式：
- **Plan-and-Solve**: 先分解问题，再并行求解
- **两阶段流程**: Pre-writing (研究 + 大纲) → Writing (填充 + 引用)
- **迭代审查**: Reviewer → Revisor 循环，直到质量达标
- **多视角覆盖**: 强制要求多个 viewpoints，避免片面

代表项目：
- GPT Researcher (最成熟，27.5k stars)
- STORM (学术最强，多视角问答)
- LlamaIndex (工程最强，事件驱动工作流)

---

### Q2: 它们如何保证结构化输出的质量？

**答案**: 多层次质量保证机制

1. **结构层面**
   - **大纲优先**: 先生成结构化大纲，再填充内容（STORM）
   - **Pydantic Schema**: 类型安全 + 验证（LlamaIndex）
   - **JSON Schema**: 自定义输出格式（Tavily）

2. **内容层面**
   - **多 Agent 验证**: Reviewer + Revisor 循环（GPT Researcher）
   - **自反思**: Agent 评估自己的输出（LlamaIndex）
   - **Critic Agent**: 专门评审角色（AutoGen）

3. **事实层面**
   - **Grounding**: 从可信来源建立 ground truth（Tavily）
   - **来源追踪**: 所有信息保留原始引用（GPT Researcher, STORM）
   - **检索 grounding**: 所有问题基于检索结果（STORM）

4. **覆盖层面**
   - **多视角发现**: 强制要求多个 viewpoints（STORM）
   - **并行收集**: 多个 Execution Agent 独立收集（GPT Researcher）
   - **去重机制**: 自动去重（Tavily）

5. **迭代层面**
   - **Reviewer-Revisor 循环**: 直到质量达标（GPT Researcher）
   - **自反思循环**: 自动重试（LlamaIndex）
   - **Human-in-the-Loop**: 关键节点人工审核（AutoGen, Co-STORM）

---

### Q3: 有没有"迭代式研究 + 结构质量保证"的现成实现？

**答案**: 有，以下是最佳选择

#### 最成熟的实现

1. **GPT Researcher**
   - ✅ 迭代式研究：Reviewer-Revisor 循环
   - ✅ 结构质量保证：大纲优先 + 多 Agent 验证
   - ✅ 开源：https://github.com/assafelovic/gpt-researcher
   - ✅ 文档完善：https://docs.gptr.dev
   - ✅ 社区活跃：27.5k stars

2. **STORM**
   - ✅ 迭代式研究：模拟对话多轮迭代
   - ✅ 结构质量保证：两阶段流程 + 多视角覆盖
   - ✅ 开源：https://github.com/stanford-oval/storm
   - ✅ 学术支撑：NAACL 2024, EMNLP 2024
   - ✅ 99% 事实准确率（Co-STORM）

3. **LlamaIndex Workflows**
   - ✅ 迭代式研究：自反思循环 + AgentWorkflow
   - ✅ 结构质量保证：ReviewAgent + Pydantic Schema
   - ✅ 开源：https://github.com/run-llama/llama_index
   - ✅ 工程化强：事件驱动、可观测性
   - ✅ LlamaReport 支持结构化输出

#### 快速集成方案

4. **Tavily Research API**
   - ✅ 迭代式研究：/research 端点自动迭代
   - ✅ 结构质量保证：JSON Schema + Grounding
   - ❌ 非开源（API 服务）
   - ✅ 易于集成：REST API
   - ✅ Reflections 机制降低 token 消耗

---

### Q4: 最前沿的技术方向是什么？

**答案**: 五大前沿方向

#### 1. 多 Agent 协作系统

**趋势**: 从单一 Agent 到多 Agent 团队协作

**代表**:
- GPT Researcher: Chief Editor + Researcher + Reviewer + Writer
- LlamaIndex: ResearchAgent + WriteAgent + ReviewAgent
- AutoGen: GroupChat 多 Agent 协作

**前沿研究**:
- 动态 Agent 生成（根据任务复杂度）
- Agent 间通信协议优化
- 并行 vs 串行策略选择

---

#### 2. 自反思与迭代细化

**趋势**: Agent 能够评估自己的输出并自动改进

**代表**:
- LlamaIndex AgentWorkflow: 自反思循环
- GPT Researcher: Reviewer-Revisor 循环
- Co-STORM: 人机协作迭代

**前沿研究**:
- 自动质量评估指标
- 迭代终止条件优化
- 避免无限循环的策略

---

#### 3. 多视角知识发现

**趋势**: 自动识别和整合多个 viewpoints

**代表**:
- STORM: 视角发现 + 多视角问答
- Co-STORM: 动态 Mind Map

**前沿研究**:
- 自动偏见检测
- 视角覆盖度评估
- 冲突信息处理

---

#### 4. 结构化输出与验证

**趋势**: 从自由文本到可验证的结构化输出

**代表**:
- LlamaIndex: Pydantic Programs
- Tavily: JSON Schema 自定义
- AutoSurvey: 结构化评估

**前沿研究**:
- 自动 schema 生成
- 输出一致性验证
- 多模态结构化（文本 + 图像 + 表格）

---

#### 5. 实时检索与 Grounding

**趋势**: 从静态知识库到实时互联网检索

**代表**:
- Tavily: Grounding 技术
- STORM: 检索 grounding
- GPT Researcher: 实时 Web 搜索

**前沿研究**:
- 来源可信度评估
- 实时事实核查
- 跨语言检索

---

#### 6. 人机协作（Human-in-the-Loop）

**趋势**: 从全自动到人机协作

**代表**:
- Co-STORM: 人类介入对话
- AutoGen: UserProxyAgent
- SurveyPilot: 人工审核

**前沿研究**:
- 最佳介入时机
- 人机界面设计
- 协作效率评估

---

## 推荐技术路线

### 场景 1: 快速构建原型

**推荐**: GPT Researcher  
**理由**:
- 最成熟，文档完善
- 开箱即用
- 社区活跃，易于扩展

**实施步骤**:
```bash
git clone https://github.com/assafelovic/gpt-researcher
cd gpt-researcher
pip install -r requirements.txt
# 配置 API keys
python main.py
```

---

### 场景 2: 学术级研究报告

**推荐**: STORM  
**理由**:
- 学术支撑最强（NAACL 2024, EMNLP 2024）
- 多视角覆盖，避免偏见
- 99% 事实准确率（Co-STORM）
- 生成 Wikipedia 级别文章

**实施步骤**:
```bash
pip install storm
# 配置 LLM 和 Retriever
python -m storm Examples
```

---

### 场景 3: 企业级生产系统

**推荐**: LlamaIndex Workflows + LlamaReport  
**理由**:
- 工程化最强（事件驱动、可观测性）
- 结构化输出（Pydantic Schema）
- 多模态支持（文本 + 图像）
- 企业级特性（LangSmith 集成）

**实施步骤**:
```bash
pip install llama-index
# 定义 Workflows
# 配置 ResearchAgent/WriteAgent/ReviewAgent
# 集成 LlamaReport
```

---

### 场景 4: 快速 API 集成

**推荐**: Tavily Research API  
**理由**:
- 最简单的集成方式（REST API）
- Reflections 机制降低 token 消耗
- JSON Schema 自定义输出
- Grounding 技术确保准确性

**实施步骤**:
```python
import requests

response = requests.post(
    "https://api.tavily.com/research",
    json={
        "query": "Your research topic",
        "schema": {"title": "string", "summary": "string", ...}
    },
    headers={"Authorization": "Bearer…_KEY"}
)
```

---

### 场景 5: 自定义多 Agent 系统

**推荐**: AutoGen  
**理由**:
- 最灵活的 Agent 定义
- 异步事件驱动架构
- Human-in-the-Loop 支持
- 适合复杂工作流

**实施步骤**:
```bash
pip install autogen
# 定义 Agent 角色
# 配置 GroupChat
# 实现自定义工作流
```

---

## 可直接复用的技术方案

### 方案 1: Plan-and-Solve 模式

**来源**: GPT Researcher  
**适用场景**: 复杂研究任务

```python
# 伪代码
def plan_and_solve(query):
    # 1. Plan: 分解问题
    sub_questions = planner.generate_questions(query)
    
    # 2. Solve: 并行收集信息
    results = parallel_execute([
        researcher.search(q) for q in sub_questions
    ])
    
    # 3. Aggregate: 聚合总结
    report = aggregator.summarize(results)
    
    # 4. Review: 迭代审查
    while not reviewer.approve(report):
        report = revisor.revise(report, reviewer.feedback)
    
    return report
```

---

### 方案 2: 两阶段流程

**来源**: STORM  
**适用场景**: 长篇文章生成

```python
# 伪代码
def two_stage_generation(topic):
    # Stage 1: Pre-writing
    perspectives = discover_perspectives(topic)
    outline = []
    for perspective in perspectives:
        qa_pairs = simulate_dialogue(perspective, topic)
        outline.extend(qa_pairs)
    structured_outline = synthesize_outline(outline)
    
    # Stage 2: Writing
    article = write_article(structured_outline)
    article = insert_citations(article)
    
    return article
```

---

### 方案 3: 自反思循环

**来源**: LlamaIndex  
**适用场景**: 需要质量保证的任务

```python
# 伪代码
def self_reflecting_research(query):
    while True:
        # 1. Research
        findings = research_agent.search(query)
        
        # 2. Write
        draft = write_agent.write(findings)
        
        # 3. Review
        feedback = review_agent.review(draft)
        
        # 4. Self-reflect
        if review_agent.is_satisfactory(feedback):
            return draft
        # 否则继续循环
```

---

### 方案 4: Reflections 机制

**来源**: Tavily  
**适用场景**: Token 优化

```python
# 伪代码
def reflections_based_research(query):
    context = []
    reflections = []
    
    for iteration in range(max_iterations):
        # 1. Search
        results = search(query, context)
        
        # 2. Distill to reflections
        new_reflections = distill(results)
        reflections.extend(new_reflections)
        
        # 3. Update context (only reflections, not raw results)
        context = reflections
        
        # 4. Check if sufficient
        if is_sufficient(context):
            break
    
    return generate_report(context)
```

---

### 方案 5: 多视角问答

**来源**: STORM  
**适用场景**: 避免偏见，全面覆盖

```python
# 伪代码
def multi_perspective_qa(topic):
    # 1. Discover perspectives
    perspectives = discover_perspectives(topic)
    
    # 2. Multi-perspective questioning
    all_qa = []
    for perspective in perspectives:
        # Simulate dialogue
        writer = WikipediaWriter(perspective)
        expert = TopicExpert()
        
        for turn in range(max_turns):
            question = writer.ask_question()
            answer = expert.answer(question, retrieve(topic))
            all_qa.append((question, answer))
            
            if writer.is_satisfied():
                break
    
    # 3. Synthesize
    outline = synthesize_outline(all_qa)
    return outline
```

---

## 实施建议

### 1. 选择合适的架构

| 需求 | 推荐架构 | 理由 |
|------|---------|------|
| 快速原型 | GPT Researcher | 最成熟，开箱即用 |
| 学术级质量 | STORM | 多视角覆盖，99% 准确率 |
| 企业级系统 | LlamaIndex Workflows | 工程化强，可观测性 |
| 快速集成 | Tavily API | REST API，最简单 |
| 自定义系统 | AutoGen | 最灵活 |

### 2. 质量保证策略

**必须实施的**:
1. ✅ **大纲优先**: 先生成结构，再填充内容
2. ✅ **来源追踪**: 所有信息保留原始引用
3. ✅ **迭代审查**: Reviewer-Revisor 循环
4. ✅ **Grounding**: 基于可信来源验证

**可选实施的**:
- ⚠️ **多视角覆盖**: 适合争议性话题
- ⚠️ **Human-in-the-Loop**: 适合高风险决策
- ⚠️ **自反思**: 适合复杂推理任务

### 3. 性能优化

**Token 优化**:
- 使用 Reflections 机制（Tavily）
- 分层 LLM 调用（简单任务用小模型）
- 并行信息收集

**延迟优化**:
- 并行 Execution Agents
- 异步工作流
- 缓存检索结果

**成本优化**:
- 混合模型策略（gpt-4o-mini + gpt-4o）
- 迭代终止条件优化
- 来源过滤（只保留高质量来源）

---

## 总结

### 最佳实践

1. **架构**: 多 Agent 系统 + 迭代审查循环
2. **质量保证**: 大纲优先 + 多 Agent 验证 + Grounding
3. **结构化输出**: Pydantic/JSON Schema + 类型安全
4. **前沿方向**: 自反思、多视角、人机协作

### 推荐项目

1. **GPT Researcher**: 最成熟，适合大多数场景
2. **STORM**: 学术最强，适合高质量要求
3. **LlamaIndex**: 工程最强，适合企业级系统
4. **Tavily**: 集成最简单，适合快速开发

### 技术趋势

1. 多 Agent 协作系统
2. 自反思与迭代细化
3. 多视角知识发现
4. 结构化输出与验证
5. 实时检索与 Grounding
6. 人机协作（Human-in-the-Loop）

---

**文档版本**: v1.0  
**最后更新**: 2026-01  
**维护者**: Research Pro Expert Consultation System
