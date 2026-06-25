# Goal 声明式 vs 过程式 Prompt 设计调研

> 调研日期：2026-06-25
> 调研范围：2025-2026 年业界最新实践

---

## 核心发现（TL;DR）

1. **Goal 声明式 Prompt 已在生产环境验证可行**：OpenAI Codex `/goal`、Anthropic Claude Code `/goal` 均已上线，核心前提是模型能力足够强（GPT-4o/GPT-5/Claude Sonnet 4.5+）。
2. **过程式 Prompt 并非过时，而是退居"参考架构"角色**：复杂编排任务仍需要流程参考，但应作为"可选路径"而非"强制步骤"。
3. **最佳实践是混合模式**：Goal 声明 + 约束注入 + 参考流程（非强制）+ Few-shot 示例。
4. **长 Prompt 遵循度的核心解法**：结构化分段（XML tags）+ 关键约束前置/后置（避免"Lost in the Middle"）+ 约束重复强调。
5. **Prompt 外置是必然趋势**：Prompt 应作为版本化代码资产管理，与业务逻辑解耦。

---

## 模式对比

| 模式 | 优点 | 缺点 | 适用场景 | 案例 |
|------|------|------|---------|------|
| **纯 Goal 声明式** | 最大化 LLM 自主性；适应性强；Prompt 简短 | 不可预测；难以调试；可能偏离意图 | 探索性任务、创意生成、简单工具调用 | OpenAI Codex `/goal` |
| **Goal + Constraints** | 保留自主性同时划定边界；可审计 | 约束设计需要经验；约束冲突风险 | 生产 Agent、安全敏感场景 | Anthropic Claude Code |
| **Goal + Reference Plan** | 兼顾灵活性和可控性；新手友好 | Prompt 较长；LLM 可能过度依赖参考流程 | 复杂编排、多步骤工作流 | DeepFlow Ship Orchestrator |
| **纯过程式** | 完全可预测；易于调试；适合弱模型 | 脆弱（输入变化就崩溃）；无法处理意外情况；限制 LLM 能力 | 确定性流水线、合规审计、弱模型 | 传统 RPA 工作流 |
| **混合分层式** | 最佳平衡；支持渐进式复杂度 | 设计复杂度高；需要更多迭代 | 生产级多 Agent 系统 | Anthropic Orchestrator-Workers |

---

## Goal 声明式 Prompt 模板库

### 模板 1：纯 Goal 式

```markdown
# Goal
将用户输入的自然语言需求转换为可执行的 SQL 查询。

# Success Criteria
- SQL 语法正确，可在 PostgreSQL 14+ 执行
- 查询结果直接回答用户问题
- 无破坏性操作（SELECT only）

# Available Tools
- `query_database(sql: str)` → 执行 SQL 并返回结果
- `list_tables()` → 返回数据库 schema
```

**适用场景**：简单、单步任务，模型能力强。

---

### 模板 2：Goal + Constraints（推荐生产使用）

```markdown
# Goal
分析用户提供的代码仓库，识别性能瓶颈并给出优化建议。

# Constraints
- 只分析 Python 和 TypeScript 文件
- 优化建议必须有量化依据（benchmark 或复杂度分析）
- 不得修改生产代码，只输出建议报告
- 安全约束：不得读取 `.env`、`credentials/` 等敏感文件
- 输出格式：Markdown 报告，包含「问题描述」「影响范围」「优化方案」「预期收益」

# Available Tools
- `read_file(path)` → 读取文件内容
- `run_benchmark(cmd)` → 执行性能测试
- `analyze_complexity(code)` → 返回时间/空间复杂度

# Autonomy Scope
- ✅ 自主选择分析哪些文件
- ✅ 自主决定分析顺序
- ✅ 自主设计 benchmark 方案
- ❌ 不得修改任何文件
- ❌ 不得安装新依赖

# Success Criteria
- 报告覆盖 Top 3 性能瓶颈
- 每个建议附带量化数据
- 报告可在 5 分钟内读完
```

**适用场景**：生产 Agent，需要安全边界和输出质量保证。

---

### 模板 3：Goal + Reference Plan（混合模式，推荐复杂编排）

```markdown
# Goal
根据用户的自然语言描述，生成完整的 API 文档并部署到内部文档站点。

# Reference Workflow（非强制，仅供参考）
以下是完成此任务的常见路径，你可以根据实际情况调整：
1. 解析用户需求 → 确定 API 端点列表
2. 读取代码中的路由定义和类型签名
3. 生成 OpenAPI spec
4. 渲染为 HTML 文档
5. 部署到文档站点

# Constraints
- 必须从源代码提取真实类型签名，不得猜测
- 文档必须包含请求/响应示例
- 部署前必须通过 lint 检查
- 如果代码中找不到某个端点的定义，必须明确标注「未找到实现」

# Available Workers
- `code_analyzer` → 分析代码结构，提取类型签名
- `doc_generator` → 从 OpenAPI spec 生成 HTML
- `deployer` → 部署到文档站点
- `linter` → 检查文档格式合规性

# Autonomy Scope
- ✅ 自主决定文档结构和章节组织
- ✅ 自主选择示例数据的值
- ✅ 可以跳过 Reference Workflow 中的步骤
- ❌ 不得修改源代码
- ❌ 不得部署到生产环境（只部署到 staging）

# Success Criteria
- 每个 API 端点都有文档
- 文档包含可运行的 curl 示例
- 部署后 URL 可访问
```

**适用场景**：复杂多步任务，需要给 LLM 参考但不限制其自主性。

---

### 模板 4：Goal + Few-shot

```markdown
# Goal
将客户反馈分类到对应类别，并生成处理建议。

# Categories
- `BUG` - 功能异常、报错
- `FEATURE` - 功能请求、改进建议
- `UX` - 用户体验、界面问题
- `PERFORMANCE` - 速度、性能相关
- `OTHER` - 无法归类

# Examples

## Input
"每次打开报表页面都要等 10 秒以上，之前只要 2 秒"
## Output
```json
{
  "category": "PERFORMANCE",
  "confidence": 0.95,
  "suggestion": "排查报表页面近期变更，检查 SQL 查询是否退化或索引失效",
  "priority": "high"
}
```

## Input
"希望能导出 PDF 格式的月度报告"
## Output
```json
{
  "category": "FEATURE",
  "confidence": 0.98,
  "suggestion": "添加到产品 Backlog，评估 PDF 导出工作量",
  "priority": "medium"
}
```

# Constraints
- 只输出 JSON，不要其他内容
- confidence < 0.7 时标记为 `NEEDS_REVIEW`
- 同一反馈可归多个类别（多标签分类）

# Success Criteria
- 分类准确率 > 90%
- 每条建议具有可操作性
```

**适用场景**：需要精确输出格式或领域特定分类标准。

---

## 关键技术详解

### ReAct（Reasoning + Acting）

**核心思想**：交替执行「思考」→「行动」→「观察」循环。

```
Thought: 我需要先了解数据库 schema 才能写 SQL
Action: list_tables()
Observation: [users(id, name, email), orders(id, user_id, amount, created_at)]
Thought: 用户问的是"消费最多的用户"，需要 JOIN users 和 orders
Action: query_database("SELECT u.name, SUM(o.amount) as total FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.name ORDER BY total DESC LIMIT 10")
Observation: [Alice: 50000, Bob: 32000, ...]
Thought: 已得到结果，可以回答用户
Final Answer: 消费最多的用户是 Alice，总消费 50000 元。
```

**Prompt 设计要点**：
- 明确定义 Thought/Action/Observation 格式
- 提供 2-3 个完整的 ReAct 示例
- 工具描述必须精确（参数类型、返回值）

**2025 最佳实践**：
- 结合 CoT（Chain-of-Thought）提升推理质量
- 工具结果缓存避免重复调用
- 实现 fallback 机制处理工具调用失败

---

### Plan-and-Execute

**核心思想**：先规划（生成步骤列表），再逐步执行。

```markdown
# Planning Phase
将任务分解为子步骤，输出执行计划：
1. [子步骤1] - 预估耗时 - 依赖
2. [子步骤2] - 预估耗时 - 依赖
...

# Execution Phase
按计划逐步执行，每步完成后：
- 记录实际结果
- 评估是否需要调整后续计划
- 如果某步失败，重新规划剩余步骤
```

**适用场景**：长周期任务（> 5 步）、需要进度追踪。

**2025 演进**：
- 动态重规划（遇到错误时调整计划而非终止）
- 子步骤并行化（无依赖的步骤同时执行）
- 与 ReAct 结合（每步内部使用 ReAct 模式）

---

### Reflexion（自我反思）

**核心思想**：Agent 执行后自我评估，生成改进建议，迭代执行。

```markdown
# After each action, reflect:
1. 这次行动的结果是否符合预期？
2. 如果不符合，根因是什么？
3. 下一步应该如何调整？
4. 是否有更好的方法？

# Reflection Output Format
- Success: true/false
- Issue: [描述问题]
- Root Cause: [根因分析]
- Adjustment: [调整方案]
```

**适用场景**：代码生成（写→测试→修复→再测试）、写作（草稿→评审→修改）。

**生产案例**：
- OpenAI Codex：写代码 → 跑测试 → 失败时分析错误 → 修复 → 再测试
- Anthropic Claude Code：修改文件 → 运行 lint → 修复 lint 错误

---

### Tree of Thoughts（ToT）

**核心思想**：探索多条推理路径，选择最优解。

```markdown
# 对于复杂决策：
1. 生成 3-5 个可能的解决方案
2. 对每个方案评估：
   - 可行性（1-10）
   - 风险（1-10）
   - 预期收益（1-10）
3. 选择综合评分最高的方案
4. 如果最高分 < 阈值，回到步骤 1 生成更多方案
```

**适用场景**：策略规划、架构设计、需要权衡取舍的决策。

---

### Self-Ask

**核心思想**：将复杂问题分解为子问题，递归回答。

```markdown
# 当遇到复杂问题时：
1. 我需要知道什么才能回答这个问题？
2. 对于每个子问题：
   - 我能直接回答吗？
   - 需要进一步分解吗？
3. 综合子问题答案，形成最终答案
```

**示例**：
```
问题：「DeepFlow 的采集器是否支持 ARM 架构？」
→ 子问题1：DeepFlow 采集器是什么？
→ 子问题2：DeepFlow 支持哪些架构？
→ 子问题3：ARM 架构是否在支持列表中？
```

---

### LATS（Language Agent Tree Search）

**核心思想**：结合 MCTS（蒙特卡洛树搜索）+ LLM，系统性探索最优行动路径。

```
                    [Root: 初始状态]
                   /        |        \
            [Action A]  [Action B]  [Action C]
            /    \         |           \
      [A1]    [A2]      [B1]         [C1]
      /  \      |         |
   [A1a][A1b] [A2a]     [B1a] ← 最优路径
```

**核心组件**：
1. **LLM 作为动作生成器**：在每个节点采样可能的动作
2. **LLM 作为价值函数**：评估每个状态的预期收益
3. **外部反馈**：环境返回的客观反馈（测试结果、API 响应）
4. **Reflexion 机制**：失败路径的反思用于指导后续搜索

**适用场景**：
- 需要探索大量可能性的决策问题
- 有明确验证标准的任务（测试通过、数学证明）
- 需要平衡探索与利用的复杂规划

**2025 实现**：
- LangGraph 提供 MCTS 风格的图基础设施
- 遗传粒子过滤替代 MCTS（更高效）
- 贝叶斯树优化（不确定性引导）

---

## 长 Prompt 遵循度问题的解决方案

### 问题本质："Lost in the Middle"

LLM 对长上下文呈现 U 型注意力分布：
- ✅ 开头内容：高关注度
- ❌ 中间内容：显著衰减
- ✅ 结尾内容：高关注度

即使 100K+ context window，此问题依然存在（MIT 2025 研究）。

### 解决方案矩阵

| 技术 | 原理 | 实施难度 | 效果 |
|------|------|---------|------|
| **指令括号法** | 关键约束放在开头和结尾 | 低 | ⭐⭐⭐⭐ |
| **XML 标签分段** | 结构化分隔不同内容区域 | 低 | ⭐⭐⭐⭐⭐ |
| **Prompt 压缩** | 删除冗余 token，保留核心信息 | 中 | ⭐⭐⭐⭐ |
| **文档数限制** | RAG 只保留 Top 3-5 最相关文档 | 低 | ⭐⭐⭐⭐ |
| **递归自改进** | LLM 自我评审并改进输出 | 中 | ⭐⭐⭐⭐⭐ |
| **上下文分解** | 复杂任务拆分为子任务分别处理 | 中 | ⭐⭐⭐⭐⭐ |
| **Ms-PoE** | 多尺度位置编码（模型层面） | 高（需训练） | ⭐⭐⭐⭐⭐ |

### 实操指南：结构化 Prompt 模板

```markdown
<!-- 开头：角色 + 核心约束（高关注度区域） -->
# System
你是一个 [角色]。你必须遵守以下约束：
1. [最关键约束1]
2. [最关键约束2]
3. [最关键约束3]

<!-- 中间：背景信息 + 工具说明（低关注度区域） -->
# Context
[背景信息，可较长]

# Available Tools
[工具列表和说明]

# Reference Workflow
[参考流程，非强制]

<!-- 结尾：任务 + 输出格式 + 约束重申（高关注度区域） -->
# Current Task
[具体任务描述]

# Output Format
[期望的输出格式]

# Reminder
记住：
- [重申最关键约束1]
- [重申最关键约束2]
```

### 关键原则

1. **重要内容前置后置**：核心约束放开头，任务指令放结尾
2. **XML 标签强制分段**：`<context>`, `<tools>`, `<constraints>`, `<task>`
3. **约束数量 ≤ 7**：超过 7 条约束，遵循度急剧下降
4. **约束具体化**：「输出不超过 500 字」优于「输出要简洁」
5. **负面示例优先**：告诉 LLM「不要做什么」比「要做什么」更有效

---

## Few-shot vs Zero-shot：复杂编排任务的选择

### 决策矩阵

| 场景 | 推荐方式 | 原因 |
|------|---------|------|
| 输出格式严格定义 | Few-shot（1-3 例） | 确保格式一致性 |
| 领域特定分类 | Few-shot（3-5 例） | 建立分类边界 |
| 通用任务探索 | Zero-shot | 快速迭代，无需准备示例 |
| 输出风格/语气要求 | Few-shot（2-3 例） | 锚定风格基线 |
| 多步编排逻辑 | Zero-shot + Reference Plan | 给参考不给强制步骤 |
| 工具调用编排 | Few-shot（2-3 完整链路） | 展示工具组合方式 |

### 2025 最佳实践：Guided Zero-Shot

**核心理念**：Zero-shot 为主，用 1-2 个示例锚定关键行为。

```markdown
# Task
分析用户需求并调用合适的工具完成任务。

# Anchor Example（仅展示关键决策点）
User: "帮我查一下昨天的部署失败原因"
→ Step 1: `search_logs(date="yesterday", level="ERROR")`
→ Step 2: 分析错误日志，提取关键信息
→ Step 3: 如果是代码问题，`get_commit(hash=...)`
→ Final: 汇总分析报告

# Your Turn
User: "[实际需求]"
```

**优势**：
- Token 消耗低（相比完整 Few-shot）
- 保留 LLM 自主性
- 锚定关键决策模式

---

## Prompt 外置 vs 内嵌：管理最佳实践

### 2025 行业共识：Prompt 作为版本化代码资产

| 实践 | 说明 |
|------|------|
| **外置存储** | Prompt 与业务代码分离，独立迭代 |
| **语义化版本** | v1.0 → v1.1（约束调整）→ v2.0（结构重构） |
| **不可变版本** | 已发布版本不修改，只创建新版本 |
| **A/B 测试** | Feature flag 控制 Prompt 版本切换 |
| **Golden Dataset** | 标准测试集验证 Prompt 变更不退化 |
| **回滚机制** | 生产问题可快速回滚到上一版本 |

### 推荐架构

```
prompts/
├── orchestrator/
│   ├── ship_pro_v3.md          # 当前生产版本
│   ├── ship_pro_v4_draft.md    # 草稿
│   └── tests/
│       ├── golden_cases.json   # 标准测试用例
│       └── eval.py             # 评估脚本
├── workers/
│   ├── code_analyzer.md
│   ├── doc_generator.md
│   └── deployer.md
└── shared/
    ├── constraints.md          # 共享约束
    └── output_formats.md       # 输出格式定义
```

### 关键原则

1. **Prompt 变更必须经过评估**：不能直接 push 到生产
2. **领域专家可编辑 Prompt**：不需要工程师介入（低代码/无代码）
3. **Prompt 与工具定义绑定**：工具变更时同步更新相关 Prompt
4. **监控 Prompt 性能**：跟踪故障率、延迟、Token 消耗

---

## 对 Ship Pro Orchestrator Prompt 的改写建议

### 当前问题（V3）

假设当前 V3 是纯过程式 Prompt（Phase 1 → Phase 5）：

```markdown
# 典型过程式结构（问题标注）
Phase 1: 需求解析
- 步骤 1.1: 提取用户意图
- 步骤 1.2: 识别目标组件
- 步骤 1.3: 确认参数

Phase 2: 方案设计
- 步骤 2.1: 查询可用 Worker
- 步骤 2.2: 生成执行计划
- 步骤 2.3: 用户确认

Phase 3: 任务分发
- ...

Phase 4: 执行监控
- ...

Phase 5: 结果汇总
- ...
```

**问题分析**：
1. ❌ **过度约束**：强制 LLM 按固定步骤执行，无法处理意外情况
2. ❌ **脆弱性**：输入格式变化可能导致某个 Phase 失败，整个流程崩溃
3. ❌ **能力浪费**：LLM 的推理能力被限制为「步骤执行器」
4. ❌ **不可恢复**：某步失败后缺乏自适应机制
5. ❌ **长 Prompt 遵循度差**：5 个 Phase 的详细指令容易「Lost in the Middle」

---

### 建议改写方案：Goal 声明式 + Reference Workflow

```markdown
# Ship Pro Orchestrator v4 (Goal-Based)

## Role
你是 Ship Pro 的编排 Agent，负责将用户的部署/发布需求转化为可执行的工作流，协调各专业 Worker 完成任务。

## Goal
根据用户需求，设计并执行最优的 Worker 编排方案，确保任务完成且质量达标。

## Core Constraints（必须遵守）
1. 所有文件修改必须通过 Worker 执行，Orchestrator 不直接操作
2. 生产环境操作前必须获得用户确认
3. 每个 Worker 调用必须有明确的输入/输出定义
4. 失败时优先尝试恢复，无法恢复时向用户报告并请求指导
5. 不得跳过质量检查步骤（lint、test、security scan）

## Available Workers
| Worker | 能力 | 输入 | 输出 |
|--------|------|------|------|
| `code_analyzer` | 分析代码结构、依赖关系 | 文件路径/目录 | 结构图、依赖列表 |
| `test_runner` | 执行测试套件 | 测试范围 | 测试报告 |
| `doc_generator` | 生成文档 | 代码/配置 | Markdown/HTML 文档 |
| `deployer` | 部署到指定环境 | 部署配置 | 部署结果 |
| `security_scanner` | 安全漏洞扫描 | 代码/配置 | 安全报告 |
| `linter` | 代码规范检查 | 文件路径 | Lint 报告 |

## Reference Workflow（非强制，仅供参考）
以下是典型部署任务的处理路径，可根据实际情况调整：

1. **理解需求** → 解析用户意图，确认目标环境和范围
2. **分析现状** → 调用 `code_analyzer` 了解当前状态
3. **制定计划** → 生成 Worker 编排方案，展示给用户确认
4. **执行任务** → 按依赖顺序调用 Workers，监控执行状态
5. **质量验证** → 运行 `test_runner` + `security_scanner` + `linter`
6. **部署交付** → 调用 `deployer`，验证部署结果
7. **汇总报告** → 输出执行摘要

## Autonomy Scope
### ✅ 自主决策（无需用户确认）
- 选择分析哪些文件
- Worker 调用顺序优化
- 失败重试策略（最多 3 次）
- 并行执行无依赖的子任务

### ⚠️ 需要用户确认
- 生产环境部署
- 删除文件或数据
- 修改核心配置
- 超出预估 Token 预算 50% 以上

### ❌ 禁止行为
- 直接修改源代码（必须通过 Worker）
- 跳过安全检查
- 在未确认的情况下操作生产环境
- 隐藏错误信息

## Success Criteria
- 任务完成率 > 95%（非用户取消）
- 所有质量检查通过
- 用户无需二次追问即可理解执行结果
- 执行报告包含：做了什么、为什么这么做、结果如何

## Error Handling
- Worker 失败 → 分析错误原因 → 尝试替代方案 → 失败则报告用户
- 用户需求不明确 → 提出澄清问题（最多 3 个）→ 基于最佳理解执行
- 超出能力范围 → 明确告知用户限制 → 建议替代方案

## Output Format
执行完成后输出：
```markdown
## 执行摘要
- **目标**：[用户原始需求]
- **方案**：[实际执行的 Worker 编排]
- **结果**：[成功/部分成功/失败]

## 详细执行记录
| 步骤 | Worker | 输入 | 输出 | 状态 |
|------|--------|------|------|------|
| ... | ... | ... | ... | ✅/❌ |

## 后续建议
- [如有未完成的工作或改进建议]
```
```

---

### 改写对比

| 维度 | V3（过程式） | V4（Goal 声明式） |
|------|-------------|------------------|
| **灵活性** | 低（固定步骤） | 高（自主选择路径） |
| **可预测性** | 高（确定性流程） | 中（约束保证边界） |
| **容错性** | 低（步骤失败即终止） | 高（自适应恢复） |
| **Prompt 长度** | 长（每步详细说明） | 中（目标+约束+参考） |
| **LLM 能力利用** | 低（执行器角色） | 高（决策者角色） |
| **调试难度** | 低（流程可追踪） | 中（需要日志记录） |
| **适用模型** | 弱模型也可 | 需要强模型（GPT-4o+） |

---

### 渐进式迁移策略

如果担心一步到位风险太大，可以分阶段迁移：

**Phase 1（立即）**：
- 将 Phase 1-5 改为「Reference Workflow」
- 添加「Autonomy Scope」章节
- 保留原有步骤作为参考

**Phase 2（1-2 周）**：
- 收集 LLM 实际执行路径数据
- 识别 LLM 经常偏离的步骤（这些应该改为约束而非步骤）
- 优化约束定义

**Phase 3（1 月后）**：
- 完全移除强制步骤
- 基于数据优化 Autonomy Scope
- 添加 Few-shot 示例（基于真实成功案例）

---

## 附录：业界参考资源

### 必读论文/文章
1. **Anthropic** - "Building Effective Agents" (2025) - Orchestrator-Workers 模式定义
2. **Anthropic** - "Effective Context Engineering for AI Agents" (2025) - 上下文工程最佳实践
3. **OpenAI** - "Using Goals in Codex" (2025) - Goal-based prompting 生产案例
4. **LATS Paper** - "Language Agent Tree Search" (arXiv:2310.04406) - 统一推理-行动-规划框架
5. **Reflexion Paper** - "Reflexion: Language Agents with Verbal Reinforcement Learning" - 自我反思机制

### 关键概念演进
```
Prompt Engineering (2023)
    ↓
Context Engineering (2025) - Anthropic 提出
    ↓
Harness Engineering (2026) - 整体 AI 系统设计
```

### 工具/框架
- **LangGraph** - 状态化 Agent 图，支持 MCTS 风格工作流
- **CrewAI** - 多 Agent 角色编排
- **AutoGen** - 微软多 Agent 对话框架
- **Prompt Management Tools** - LangWatch, Maxim, Humanloop（版本化、评估、监控）

---

## 结论

**Goal 声明式 Prompt 是 2025-2026 年的明确趋势**，但并非要完全取代过程式 Prompt。最佳实践是：

1. **强模型 + 复杂任务** → Goal 声明 + 约束 + 参考流程
2. **弱模型 + 确定性任务** → 过程式（保持可预测性）
3. **生产 Agent** → 混合模式 + Prompt 版本管理 + 评估体系

对于 Ship Pro Orchestrator，建议采用 **V4 Goal 声明式方案**，渐进式迁移，保留 Reference Workflow 作为安全网。
