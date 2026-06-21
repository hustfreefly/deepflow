# 专家咨询报告：AI 产品架构视角
## Deep Research 类产品如何确保"LLM 驱动的结构化输出"质量

> **作者角色**: AI 产品架构专家  
> **调研日期**: 2026-07-18  
> **调研范围**: Manus AI / OpenAI Deep Research / Google Gemini Deep Research / Perplexity Pro Search / Elicit & Consensus / Anthropic Claude  

---

## 目录

1. [核心发现摘要](#1-核心发现摘要)
2. [逐产品深度分析](#2-逐产品深度分析)
3. [四大核心问题回答](#3-四大核心问题回答)
4. [业界 Benchmark 与评估标准](#4-业界-benchmark-与评估标准)
5. [业界共同趋势](#5-业界共同趋势)
6. [可借鉴的最佳实践](#6-可借鉴的最佳实践)
7. [针对我们场景的推荐方案](#7-针对我们场景的推荐方案)

---

## 1. 核心发现摘要

经过对 6 款主流 Deep Research 产品的深入调研，核心发现如下：

| 发现维度 | 关键结论 |
|---------|---------|
| **结构决策** | 业界主流采用"LLM 自主规划 + 人工审核修正"的混合模式，而非纯自动或纯预设 |
| **质量保证** | 三层防线：(1) 规划阶段的结构约束 (2) 执行阶段的交叉验证 (3) 输出阶段的自检/评分 |
| **迭代机制** | 所有产品都实现了某种形式的"反思-修正"循环，但深度差异巨大 |
| **评估标准** | 2025 年出现了多个专用 Benchmark（DeepResearchBench、DRACO、Rigorous Bench），但尚无统一标准 |
| **最大差距** | JSON 格式正确率 >95% vs. 叶子值准确率仅 65-80%——"结构正确 ≠ 内容正确" |

---

## 2. 逐产品深度分析

### 2.1 Manus AI

#### 架构概览

Manus AI 采用 **多 Agent 协作架构**，核心组件为 Planner Agent + Executor Agent + Verification Agent，运行在云端虚拟计算环境（Ubuntu sandbox）中。

```
用户请求 → Planner Agent（任务分解）→ Executor Agents（并行执行）→ Verification Agent（质量审查）→ 输出报告
```

#### 结构决策机制

- **Planner Agent** 接收用户请求后，自主将复杂问题分解为多个独立子任务，生成包含依赖关系、成本预期和风险边界的执行计划
- **Wide Research 模式**：对于大规模研究任务，可部署数百个独立子 Agent 并行处理，每个 Agent 拥有独立的上下文窗口，避免"上下文污染"
- **CodeAct 机制**：不使用固定的 JSON Schema 或工具 API，而是通过生成并执行 Python 代码作为通用动作机制，实现更灵活的动作空间

#### 质量保证机制

| 机制 | 具体实现 |
|------|---------|
| **多模型协作** | 底层使用 Claude 3.5/3.7 + Qwen 多个基础模型，组合各自优势 |
| **Verification Agent** | 独立的验证子 Agent，负责审查进度、检测偏差、触发重新规划 |
| **文件化记忆** | 使用 `todo.md` 追踪计划步骤，中间结果持久化到文件，防止上下文压缩导致信息丢失 |
| **Quality Mode** | 专为深度报告（27+ 页）设计的模式，支持多步推理、交叉引用、趋势量化 |
| **三角验证** | 通过多个独立来源交叉验证事实性声明 |

#### 关键洞察

> Manus 的核心创新在于用 **CodeAct 替代固定 Schema**——让 LLM 用代码而非 JSON 来表达动作，大幅降低了结构化输出的格式约束问题。但这也将"结构正确性"的责任从解码层转移到了代码执行层。

---

### 2.2 OpenAI Deep Research（o3/o4-mini）

#### 架构概览

OpenAI Deep Research 基于 o3 模型的早期优化版本，专为网页浏览和多步推理优化。2025 年 2 月推出，支持 web search 和 code execution 工具。

#### 结构决策机制

- **自主研究计划**：模型接收复杂查询后，自主制定研究计划，分解为多个子任务
- **工具调用链**：通过 web search → 分析 → 再搜索的多轮循环，逐步构建知识图谱
- **不直接支持 Structured Output**：o3-deep-research 模型本身不支持 API 层面的 JSON Schema 约束（社区反馈），需要后续用 GPT-5-pro 等模型做结构化转换

#### 质量保证机制

| 机制 | 具体实现 |
|------|---------|
| **System Card 评估** | 使用 PersonQA（人物事实）和 SimpleQA（4000 道事实题）评估幻觉率 |
| **幻觉率指标** | Deep Research 模型幻觉率仅 13%（PersonQA），显著优于 GPT-4o 的 30% |
| **搜索驱动降幻觉** | 重度依赖在线搜索来减少错误，每个事实性声明都有来源支撑 |
| **后训练惩罚** | 对错误答案和"过度自信的错误答案"施加不同权重的惩罚，推动模型承认不确定性 |
| **OpenAI Evals 框架** | 开发者可自定义评估任务，测试结构化输出的可靠性 |

#### 幻觉率对比数据

| 模型 | PersonQA 幻觉率 |
|------|---------------|
| Deep Research (o3-based) | **13%** |
| GPT-4.5 | 19% |
| o1 | 20% |
| GPT-4o | 30% |
| o3 | 33% |
| o4-mini | 48% |
| GPT-5-thinking | 比 o3 降低 65% |

#### 关键洞察

> OpenAI 的核心发现：**标准训练和评估流程奖励"猜测"而非"承认不确定"**，这是幻觉的根本原因。解决方案是重新设计评估指标——奖励不确定性表达，严厉惩罚自信的错误。

---

### 2.3 Google Gemini Deep Research

#### 架构概览

Google Gemini Deep Research Agent 是一个完整的 Agentic 系统，基于 Gemini 3/3.1 Pro 模型，具备自主规划、执行、反思能力。

#### 结构决策机制（6 阶段流程）

```
阶段1: 查询分析 → 问题分解为可管理的子任务
阶段2: 策略制定 → 为每个子任务设计搜索查询
阶段3: 自主检索 → 执行多达 160 次网页搜索
阶段4: 推理与反思 → 持续评估信息质量，识别不完整/错误信息
阶段5: 分析综合 → 提取模式、关键洞察，逻辑化组织发现
阶段6: 报告生成 → 带引用的结构化报告，可含可视化图表
```

#### 质量保证机制

| 机制 | 具体实现 |
|------|---------|
| **有意义的自我反思** | Gemini 3 模型能评估自身行动结果，识别错误/不完整信息，修订计划并重试 |
| **可配置安全过滤器** | 概率和严重度双维度的内容过滤阈值 |
| **自动红队测试（ART）** | 内部团队模拟攻击，识别安全弱点 |
| **模型硬化** | 在大量真实场景数据上微调，学会忽略恶意指令 |
| **Thinking Budget** | 开发者可调节模型"思考时间"，平衡质量/速度/成本 |
| **Deep Think 模式** | 实验性增强推理模式，在形成回答前考虑多个假设 |
| **人工协作规划** | 用户可在执行前审查、修改 AI 生成的研究计划 |

#### 关键洞察

> Google 的独特之处在于 **"有意义的自我反思"** 能力和 **Thinking Budget** 机制。前者让模型能判断"我收集的信息够不够好"，后者让开发者能控制"值得花多少时间思考"。

---

### 2.4 Perplexity Pro Search

#### 架构概览

Perplexity Pro 在 2025 年进化为深度研究平台，核心特点是多步搜索 + 多模型协作 + 丰富的引用系统。

#### 结构决策机制

- **Deep Research 模式**：执行 20-50 次定向查询的多遍搜索
- **研究计划生成**：解释用户查询 → 制定详细研究计划 → 并行网页搜索 → 交叉引用 → 综合报告
- **Focus Modes**：用户可限定搜索范围（Academic / Writing / YouTube / Reddit / Math）
- **Pages 功能**：自动生成带标题、章节、可视化的交互式报告

#### 质量保证机制

| 机制 | 具体实现 |
|------|---------|
| **10x 丰富引用** | Pro 用户的引用源覆盖范围是免费版的 10 倍，每个事实声明都有编号链接 |
| **自动事实核查** | 在呈现答案前，实时将信息与多个独立来源比对 |
| **上下文探索** | 将信息组织为动态知识地图，展示概念间关联 |
| **Model Council** | 路由查询到 GPT-5.2 / Claude 4.6 / Gemini 3.1 Pro 等前沿模型，选择最佳或综合多模型结果 |
| **Premium 数据源** | 整合 Statista / PitchBook / Wiley 等专业数据 |
| **无限文件处理** | 上传分析 PDF/CSV/图片，AI 交叉引用结构化数据 |

#### 关键洞察

> Perplexity 的核心策略是 **"模型委员会"（Model Council）**——不依赖单一模型，而是让多个前沿模型竞争/协作，选最优结果。这是对"单模型质量保证"范式的根本性突破。

---

### 2.5 Elicit / Consensus（学术搜索）

#### 架构概览

Elicit 和 Consensus 是面向学术研究的 AI 工具，核心挑战是从海量论文中提取结构化数据并确保准确性。

#### Elicit 的结构化机制

- **125M+ 论文库**搜索、摘要、数据提取
- **自定义提取 Schema**：用户定义要提取的数据字段（如样本量、方法、结论），AI 自动从论文中提取
- **系统化提取流程**：定义 Schema → AI 批量提取 → 结构化表格输出

#### Consensus 的结构化机制

- **Consensus Meter**：对 Yes/No 型研究问题，可视化展示学术界的共识程度
- **论文级声明提取**：从每篇论文中提取具体研究结论，而非整体摘要
- **结构化聚合**：跨论文聚合发现，展示一致/矛盾的证据

#### 质量保证机制

| 机制 | 具体实现 |
|------|---------|
| **多模型共识管道** | 使用 Claude Sonnet 4 + Kimi K2.5 双模型提取，Gemini 3 Flash 做 tiebreaker |
| **挑战感知路由** | 根据论文特征（扫描 PDF / 复杂表格）自动选择提取模式（纯文本 / 混合视觉） |
| **人工等效验证** | 管道提取的聚合 Meta 分析结论，与人工提取在统计上无显著差异 |
| **来源限定** | 仅从同行评审论文中提取，排除非学术来源 |

#### 关键洞察

> 学术领域的核心创新是 **"多模型共识 + tiebreaker"** 模式：两个模型独立提取 → 一致则采纳 → 不一致则第三个模型仲裁。这比单模型自检更可靠。

---

### 2.6 Anthropic Claude Research

#### 架构概览

Anthropic 在 2025 年推出了 Claude 的 Structured Outputs 功能，并通过 200K-1M token 的超长上下文支持长文档结构化输出。

#### 结构决策机制

- **Constrained Decoding（约束解码）**：在推理过程中主动限制 token 生成，确保严格匹配开发者定义的 JSON Schema
- **超长上下文**：200K token（~500 页）→ 1M token（2026 年 Sonnet 4.6），支持整个代码库或数十篇论文的单次处理
- **Constitutional AI**：通过宪法原则引导模型自主判断输出质量

#### 质量保证机制

| 机制 | 具体实现 |
|------|---------|
| **约束解码** | 推理时主动限制 token 空间，保证格式 100% 匹配 Schema |
| **格式 vs. 内容分离** | 明确承认：格式正确 ≠ 内容正确，模型仍可能"幻觉"但格式完美 |
| **内部代码审查** | Claude 审查自身代码库，2025 年底 Claude 写的代码接近人类质量 |
| **企业级安全测试** | Claude Fable 5 等模型经过广泛安全性、可靠性测试 |
| **人类反馈 + 宪法 AI** | 结合 RLHF 和 Constitutional AI 原则进行对齐 |

#### 关键洞察

> Anthropic 最诚实的认知：**"Structured Outputs 保证格式一致性，但不保证内容真实性"**。这是业界对"结构质量"和"内容质量"最清晰的分离。

---

## 3. 四大核心问题回答

### 3.1 这些产品如何让 LLM 自主决定"该用什么结构"？

业界存在 **三种主要范式**：

| 范式 | 代表产品 | 机制 |
|------|---------|------|
| **LLM 自主规划** | Manus AI, Gemini Deep Research | LLM 分析用户查询后自主生成研究计划和报告结构 |
| **预定义 Schema + LLM 填充** | Elicit, Consensus, OpenAI API | 开发者/用户预定义结构，LLM 负责内容填充 |
| **混合模式** | Perplexity, Claude | 系统提供结构模板/建议，LLM 可自适应调整 |

**最佳实践趋势**：LLM 先生成结构提案 → 人工审核/修改 → 执行填充。这平衡了自主性和可控性。

**技术实现路径**：
1. **Manus 的 CodeAct**：LLM 用代码定义结构（最灵活，但最难验证）
2. **OpenAI 的 JSON Schema**：开发者定义 Schema，模型严格遵守（最可控，但缺乏灵活性）
3. **Gemini 的 6 阶段流程**：LLM 自主分析→规划→执行→反思→综合→生成（最完整）

### 3.2 它们用什么机制验证结构质量？

验证机制分为 **三个层次**：

#### 第一层：格式层验证
- **约束解码**（Anthropic, OpenAI）：推理时限制 token 空间，保证 Schema 匹配
- **后处理校验**：生成后用 JSON Schema validator 检查
- **DeepJSONEval**：测试深层嵌套 JSON 的性能

#### 第二层：内容层验证
- **交叉引用**（Perplexity, Manus）：多源比对事实性声明
- **自动事实核查**（Perplexity）：实时与独立来源比对
- **幻觉率评估**（OpenAI）：PersonQA / SimpleQA 基准测试

#### 第三层：结构合理性验证
- **自我反思**（Gemini）：模型评估"我的结构是否适合这个研究问题"
- **Verification Agent**（Manus）：独立 Agent 审查结构完整性
- **LLM-as-Judge**：用强模型评估弱模型输出的结构质量

**关键差距**：
> JSON 格式正确率 >95%（大多数模型）  
> 叶子值准确率仅 65-80%（SOB Benchmark 数据）  
> **格式正确 ≠ 内容正确 ≠ 结构合理**

### 3.3 迭代循环中是否包含结构化质量检查？

| 产品 | 迭代机制 | 结构质量检查 |
|------|---------|-------------|
| **Manus AI** | analyze → plan → execute → observe 循环 | ✅ Verification Agent 审查 + todo.md 追踪 |
| **OpenAI DR** | 多轮搜索 → 分析 → 再搜索 | ⚠️ 隐式（通过搜索质量间接保证） |
| **Gemini DR** | 6 阶段 + 自我反思 | ✅ 有意义的自我反思，可修订计划 |
| **Perplexity** | 20-50 次查询的多遍搜索 | ✅ 自动事实核查 + Model Council |
| **Elicit/Consensus** | 多模型共识 + tiebreaker | ✅ 共识度检测，低共识触发仲裁 |
| **Claude** | 约束解码 + Constitutional AI | ⚠️ 格式层保证，内容层依赖训练 |

**结论**：所有产品都有某种形式的迭代质量检查，但深度和显式程度差异巨大。最完整的是 Gemini（自我反思）和 Perplexity（Model Council）。

### 3.4 业界是否有"结构质量评估"的标准或 Benchmark？

**2025-2026 年出现了多个专用 Benchmark**：

| Benchmark | 发布时间 | 评估维度 | 关键发现 |
|-----------|---------|---------|---------|
| **SOB** (Structured Output Benchmark) | 2025 | 值准确率、格式正确率、多模态 | 格式正确率 >95%，值准确率仅 65-80% |
| **StructEval** | 2025.05 | 18 种格式、44 种任务类型 | SOTA 模型平均仅 75.58% |
| **DeepJSONEval** | 2025 | 深层嵌套 JSON | 性能随嵌套深度下降 |
| **DeepResearchBench** | 2025 | 100 个 PhD 级研究任务、22 个领域 | 使用 RACE + FACT 双评估框架 |
| **Rigorous Bench** | 2025.10 | 推理深度、事实可靠性、报告质量 | 多维评估，超越简单"答案检查" |
| **DRACO** | 2026.02 | 准确性、完整性、客观性 | 基于真实用户研究任务设计 |
| **Cleanlab 新基准** | 2025.12 | Field Accuracy、Output Accuracy | 发现现有 Benchmark 的 ground-truth 有大量错误 |

**关键结论**：
- **尚无统一标准**，但趋势是从"格式正确率"转向"值准确率"和"多维质量评估"
- **DeepResearchBench** 的 RACE + FACT 框架最接近"结构质量评估"的完整定义
- **Cleanlab 的发现**提醒我们：评估基准本身的质量也需要保证

---

## 4. 业界 Benchmark 与评估标准

### 4.1 结构化输出质量评估

#### 格式层指标
- **JSON Schema 匹配率**：最基础的指标，大多数模型 >95%
- **格式 adherence**：StructEval 引入的格式遵循度指标
- **嵌套深度耐受性**：DeepJSONEval 发现性能随深度下降

#### 内容层指标
- **Value Accuracy（值准确率）**：SOB 的核心指标，叶子值的正确性
- **Field Accuracy（字段准确率）**：Cleanlab 的字段级准确度
- **Semantic Tree Edit Distance (STED)**：平衡语义灵活性和结构严格性的 JSON 比较指标

#### 综合质量指标
- **RACE 框架**（DeepResearchBench）：Reference-based Adaptive Criteria-driven Evaluation with Dynamic Weighting
- **FACT 框架**（DeepResearchBench）：Framework for Factual Abundance and Citation Trustworthiness
- **多维评估**：Rigorous Bench 的推理深度 + 事实可靠性 + 报告质量

### 4.2 幻觉评估

| 评估集 | 用途 | 关键指标 |
|--------|------|---------|
| **PersonQA** | 人物事实问答 | 准确率 + 幻觉率 |
| **SimpleQA** | 4000 道事实题 | 准确率 |
| **生产级事实评估** | GPT-5 使用 | 重大事实错误率 |

---

## 5. 业界共同趋势

### 趋势 1：从"单模型"到"多模型协作"

- Perplexity 的 Model Council（GPT-5.2 + Claude 4.6 + Gemini 3.1 Pro）
- Elicit/Consensus 的双模型提取 + tiebreaker
- Manus 的多基础模型（Claude + Qwen）

**含义**：单模型的质量保证已不够，多模型交叉验证成为新范式。

### 趋势 2：从"格式保证"到"值准确率"

- SOB Benchmark 揭示的 15-30% 差距
- Cleanlab 对现有 Benchmark ground-truth 错误的发现
- StructEval 的综合评估方法

**含义**：JSON 格式正确只是起点，真正的挑战是叶子值的准确性。

### 趋势 3：从"一次性生成"到"反思-修正循环"

- Gemini 的"有意义的自我反思"
- Manus 的 analyze → plan → execute → observe 循环
- MIT SEAL 的自适配 LLM

**含义**：高质量输出不是一次生成的，而是通过多轮反思迭代出来的。

### 趋势 4：从"黑盒生成"到"可审计追溯"

- Perplexity 的 10x 丰富引用
- OpenAI 的搜索驱动降幻觉
- DeepResearchBench 的 FACT 框架（引用可信度评估）

**含义**：每个结构化输出都必须可追溯到来源，"无来源 = 不可信"。

### 趋势 5：评估基准本身的"质量革命"

- Cleanlab 发现现有 Benchmark 的 ground-truth 有大量错误
- 新 Benchmark 强调"经过验证的高质量 ground-truth"
- 多维评估取代单一准确率

**含义**：我们在设计质量评估时，必须首先确保评估标准本身的质量。

### 趋势 6：结构质量与内容质量的显式分离

- Anthropic 的明确声明：格式正确 ≠ 内容正确
- OpenAI 的"完美结构但逻辑错误可能制造可靠性幻觉"警告
- 业界开始分别评估结构层和内容层

**含义**：质量评估必须分为独立的结构质量检查和内容质量检查。

---

## 6. 可借鉴的最佳实践

### 6.1 结构决策最佳实践

| 实践 | 来源 | 具体方法 |
|------|------|---------|
| **LLM 规划 + 人工审核** | Gemini, Manus | LLM 生成结构提案，用户可修改后再执行 |
| **CodeAct 替代固定 Schema** | Manus | 用代码表达结构，更灵活但需要执行验证 |
| **Focus Modes** | Perplexity | 预定义几种结构模板（学术/商业/技术），用户选择 |
| **渐进式结构细化** | Gemini 6 阶段 | 从粗到细逐步确定结构，每步可修正 |

### 6.2 质量保证最佳实践

| 实践 | 来源 | 具体方法 |
|------|------|---------|
| **多模型共识** | Elicit/Consensus | 2+ 模型独立提取 → 一致则采纳 → 不一致则仲裁 |
| **自动事实核查** | Perplexity | 生成后实时与多源比对 |
| **自我反思** | Gemini | 模型评估"我的输出是否足够好"，不够则重新执行 |
| **Verification Agent** | Manus | 独立 Agent 专门负责质量审查 |
| **幻觉率评估** | OpenAI | 使用 PersonQA/SimpleQA 定期评估 |

### 6.3 迭代循环最佳实践

| 实践 | 来源 | 具体方法 |
|------|------|---------|
| **analyze→plan→execute→observe** | Manus | 四步循环，每步有明确输入输出 |
| **Todo.md 追踪** | Manus | 文件化计划追踪，防止上下文丢失 |
| **Thinking Budget** | Gemini | 控制思考时间，平衡质量/成本 |
| **Model Council** | Perplexity | 多模型竞争/协作，选最优 |

### 6.4 评估最佳实践

| 实践 | 来源 | 具体方法 |
|------|------|---------|
| **RACE + FACT 双框架** | DeepResearchBench | 分别评估报告质量和信息检索质量 |
| **多维评估** | Rigorous Bench | 推理深度 + 事实可靠性 + 报告质量 |
| **值准确率 > 格式正确率** | SOB | 关注叶子值的正确性而非仅格式 |
| **LLM-as-Judge** | 业界通用 | 用强模型评估弱模型输出 |

---

## 7. 针对我们场景的推荐方案

### 7.1 场景分析

我们的 Deep Research 系统需要解决的核心问题：
1. **结构自主性**：LLM 需要自主决定报告结构，但不能完全不可控
2. **质量可衡量**：需要明确的质量指标和评估机制
3. **迭代可追溯**：每次迭代的质量变化需要可追踪
4. **成本可控**：多模型/多轮迭代的成本需要管理

### 7.2 推荐架构：三层质量门控

```
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 1: 结构规划层                           │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│  │ LLM 自主  │ →  │ 人工审核  │ →  │ 结构模板  │                  │
│  │ 规划结构  │    │ /修正    │    │ 约束验证  │                  │
│  └──────────┘    └──────────┘    └──────────┘                  │
│  输出：经审核的结构提案 + 研究计划                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 2: 内容执行层                           │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│  │ 多模型    │ →  │ 交叉引用  │ →  │ 自动事实  │                  │
│  │ 并行提取  │    │ 验证     │    │ 核查     │                  │
│  └──────────┘    └──────────┘    └──────────┘                  │
│  输出：带引用的结构化内容草稿                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Layer 3: 质量评估层                           │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│  │ 结构完整  │ +  │ 值准确率  │ +  │ 引用可信  │                  │
│  │ 性检查   │    │ 抽样验证  │    │ 度评估   │                  │
│  └──────────┘    └──────────┘    └──────────┘                  │
│  输出：质量评分报告 + 改进建议                                    │
│  决策：质量达标 → 交付 | 质量不达标 → 回到 Layer 2 迭代           │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 推荐的质量指标体系

#### 结构质量指标（权重 30%）

| 指标 | 定义 | 目标值 | 评估方法 |
|------|------|--------|---------|
| Schema 匹配率 | 输出符合预定义 Schema 的比例 | >98% | JSON Schema Validator |
| 结构完整性 | 所有必需章节/字段都存在 | 100% | 结构检查器 |
| 层次合理性 | 章节层次深度和逻辑是否合理 | 评分 1-5 | LLM-as-Judge |
| 信息密度均衡 | 各章节内容量是否均衡（无空章节/过长章节） | 变异系数 <0.5 | 统计分析 |

#### 内容质量指标（权重 50%）

| 指标 | 定义 | 目标值 | 评估方法 |
|------|------|--------|---------|
| 值准确率 | 叶子值（数据、事实）的正确率 | >85% | 抽样人工验证 |
| 引用覆盖率 | 事实性声明有来源引用的比例 | >90% | 引用检查器 |
| 引用准确率 | 引用来源确实支撑声明的比例 | >85% | LLM 交叉验证 |
| 幻觉率 | 无来源支撑的声明比例 | <15% | PersonQA 类测试 |
| 矛盾检测 | 报告内部是否存在自相矛盾 | 0 处 | LLM 一致性检查 |

#### 过程质量指标（权重 20%）

| 指标 | 定义 | 目标值 | 评估方法 |
|------|------|--------|---------|
| 来源多样性 | 引用的独立来源数量 | >20 | 来源统计 |
| 搜索深度 | 研究轮次和查询次数 | 根据任务复杂度 | 过程日志 |
| 迭代收敛性 | 质量评分是否逐轮提升 | 单调递增 | 质量趋势分析 |
| 成本效率 | 每单位质量的 token 消耗 | 持续优化 | 成本追踪 |

### 7.4 推荐的技术实现路径

#### 阶段 1：基础框架（1-2 周）

1. **结构模板库**：预定义 5-10 种常见研究报告结构模板
2. **JSON Schema 约束**：使用 Anthropic/OpenAI 的 Structured Outputs 保证格式
3. **基础引用系统**：每个事实声明必须附带来源 URL

#### 阶段 2：质量保证（2-4 周）

4. **自动事实核查模块**：对报告中的事实性声明进行多源比对
5. **结构完整性检查器**：验证所有必需章节存在且内容非空
6. **LLM-as-Judge 评分**：用强模型对输出进行多维度评分

#### 阶段 3：迭代优化（4-6 周）

7. **自我反思循环**：模型评估输出质量，不达标则自动迭代
8. **多模型共识**：关键数据点由 2+ 模型独立提取并交叉验证
9. **质量趋势追踪**：记录每次迭代的质量评分变化

#### 阶段 4：高级功能（6-8 周）

10. **人工审核接口**：关键节点允许人工介入修正
11. **成本优化**：Thinking Budget + 模型路由（简单任务用便宜模型）
12. **评估基准建设**：建立内部的质量评估数据集

### 7.5 关键决策建议

| 决策点 | 推荐选择 | 理由 |
|--------|---------|------|
| 结构决策方式 | **LLM 提案 + 人工审核** | 平衡自主性和可控性 |
| 格式保证机制 | **约束解码（Structured Outputs）** | 100% 格式正确，零后处理成本 |
| 内容验证策略 | **多模型共识 + 自动事实核查** | 比单模型自检更可靠 |
| 迭代触发条件 | **质量评分 < 阈值** | 避免无意义的迭代 |
| 评估标准 | **RACE + FACT 双框架** | 分别评估结构和内容 |
| 幻觉容忍度 | **<15%（PersonQA 标准）** | 对齐 OpenAI Deep Research 水平 |

---

## 附录 A：产品对比矩阵

| 维度 | Manus AI | OpenAI DR | Gemini DR | Perplexity | Elicit/Consensus | Claude |
|------|----------|-----------|-----------|------------|-----------------|--------|
| 结构决策 | LLM 自主（CodeAct） | LLM 自主 | LLM 自主 + 人工审核 | 模板 + LLM | 预定义 Schema | 约束解码 |
| 质量保证 | Verification Agent | 搜索驱动降幻觉 | 自我反思 | Model Council | 多模型共识 | 约束解码 |
| 迭代机制 | 4 步循环 | 多轮搜索 | 6 阶段 + 反思 | 20-50 次查询 | 共识仲裁 | 无显式迭代 |
| 引用系统 | 代码追踪 | 内联引用 | 内联引用 | 10x 丰富引用 | 论文级引用 | 无内置引用 |
| 幻觉率 | 未公开 | 13%（PersonQA） | 未公开 | 未公开 | 未公开 | 未公开 |
| 上下文窗口 | 依赖底层模型 | 依赖底层模型 | 依赖底层模型 | 依赖底层模型 | N/A | 200K-1M |
| 多模型 | Claude + Qwen | 仅 OpenAI | 仅 Google | GPT-5.2 + Claude + Gemini | Claude + Kimi + Gemini | 仅 Anthropic |

## 附录 B：Benchmark 对比

| Benchmark | 评估对象 | 核心指标 | 适用场景 |
|-----------|---------|---------|---------|
| SOB | 结构化输出 | 值准确率、格式正确率 | 数据提取任务 |
| StructEval | 多格式输出 | 格式遵循、结构正确 | 通用结构化生成 |
| DeepResearchBench | 深度研究报告 | RACE + FACT | 研究报告质量评估 |
| Rigorous Bench | 研究 Agent | 推理深度、事实可靠性 | Agent 综合评估 |
| DRACO | 深度研究工具 | 准确性、完整性、客观性 | 用户视角评估 |
| Cleanlab 基准 | 结构化输出 | Field Accuracy、Output Accuracy | 生产环境评估 |

---

## 参考文献

1. OpenAI Deep Research System Card - https://openai.com/index/deep-research-system-card/
2. OpenAI Structured Outputs Guide - https://developers.openai.com/api/docs/guides/structured-outputs
3. OpenAI Hallucination Research - https://openai.com/index/why-language-models-hallucinate/
4. Manus AI Architecture Analysis - https://arxiv.org/abs/2505.02024
5. Manus Wide Research Documentation - https://manus.im/features/wide-research
6. Google Gemini Deep Research Overview - https://gemini.google/overview/deep-research/
7. Google AI Responsibility Report 2026 - https://ai.google/static/documents/ai-responsibility-update-2026.pdf
8. Perplexity DRACO Benchmark - https://research.perplexity.ai/articles/evaluating-deep-research-performance-in-the-wild-with-the-draco-benchmark
9. DeepResearchBench - https://deepresearch-bench.github.io/
10. StructEval - https://tiger-ai-lab.github.io/StructEval/
11. Cleanlab Structured Output Benchmark - https://cleanlab.ai/blog/structured-output-benchmark/
12. Interfaze SOB Benchmark - https://interfaze.ai/blog/introducing-structured-output-benchmark
13. Anthropic Structured Outputs Documentation - https://docs.anthropic.com/
14. Consensus AI - https://consensus.app/
15. Elicit AI - https://elicit.com/
16. Multi-Model AI Consensus Pipeline (bioRxiv) - https://www.biorxiv.org/content/10.64898/2026.02.17.706322v1
17. Rigorous Bench Analysis - https://medium.com/@huguosuo/a-rigorous-benchmark-with-multidimensional-evaluation-for-deep-research-agents
18. Epoch AI DeepResearchBench Results - https://epoch.ai/benchmarks/deepresearchbench

---

*本报告基于 2025-2026 年公开信息编写，产品功能和数据可能随版本更新变化。*
