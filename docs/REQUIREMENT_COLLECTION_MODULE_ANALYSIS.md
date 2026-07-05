# 需求收集模块（Requirement Collection Module）—— 分析与规划

> **版本**: v0.1 (分析稿)
> **日期**: 2026-05-23
> **作者**: 小满 🦞
> **状态**: 分析阶段，待对齐

---

## 1. 现状理解

### 1.1 DeepFlow 当前架构

```
用户 → 一句话topic → SolutionOrchestratorV21.init() → 10阶段管线 → final_solution.md
```

**当前输入接口**:
| 参数 | 类型 | 必填 | 示例 |
|------|------|------|------|
| topic | str | ✅ | "设计一个AI算力调度平台" |
| solution_type | str | ❌ | architecture/business/technical |
| mode | str | ❌ | standard/rigorous |
| constraints | list[str] | ❌ | ["10000+并发", "延迟<5秒"] |
| stakeholders | list[str] | ❌ | ["平台方", "供给方"] |

### 1.2 核心问题：需求信息质量是 Solution Pro 的最大瓶颈

**Solution Pro 的质量天花板 = 输入需求的质量**

当前 Solution Pro 10阶段管线已经非常成熟（Harness 2.0.0 质量门控、Layer 2 约束验证、多Agent并行审计），但它的输入只有一个 topic 字符串 + 可选的 constraints/stakeholders 列表。

**问题清单**:

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| P1 | topic 太短太模糊 → 12个Agent全部在猜用户意图 | 输出泛泛而谈 | 🔴 |
| P2 | 没有业务背景 → Research 只能靠搜索补，搜出来的跟用户实际场景不匹配 | 方案落地性差 | 🔴 |
| P3 | 没有用户画像/使用场景 → 设计出来的架构不贴合实际 | 架构过度设计或不足 | 🟡 |
| P4 | 没有优先级/预算/时间约束 → 方案无法做取舍 | 方案"大而全"无法落地 | 🟡 |
| P5 | 没有已有系统/技术栈信息 → 方案跟现有环境脱节 | 集成方案缺失 | 🟡 |
| P6 | 没有成功标准 → Harness Final 无法做有意义的评估 | 质量门控形同虚设 | 🟡 |

### 1.3 Solution Pro 已有的"需求收集"能力

Solution Pro 内部已经有部分需求收集/结构化能力：

1. **Data Collection Worker (Stage 1)**: 基于 topic 做 web 搜索，收集行业信息
2. **Planning Worker (Stage 2)**: 从 topic + constraints 生成任务计划
3. **structured_requirements.json**: Data Collection 阶段会尝试生成结构化需求清单

**但这些都不够**:
- Data Collection 是向外搜索（搜行业趋势），不是向内收集（问用户要信息）
- Planning 基于的信息太少，被迫大量假设
- structured_requirements.json 是 AI 凭空生成的，不是跟用户交互收集的

---

## 2. 需求收集模块的定位

### 2.1 核心定位

**需求收集模块 = Solution Pro 的"前门"**

它不是一个独立产品，而是 Solution Pro 管线的 **Stage 0**。

```
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 0: 需求收集模块 (Requirement Collection)                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  用户模糊输入 → 多轮对话 → 结构化需求文档 → 质量评估         │  │
│  │                                                               │  │
│  │  输出: requirement_spec.json                                  │  │
│  │        (足够丰富，Solution Pro 可以高质量执行)                │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Solution Pro 10阶段管线 (不变)                                      │
│  Data Collection → Planning → Reviewers → Research → ...            │
│                                                                     │
│  变化: Planning 的输入从 topic 字符串 → requirement_spec.json       │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 目标

| 目标 | 描述 | 衡量标准 |
|------|------|---------|
| **提升输入质量** | 从一句话 → 结构化需求文档 | 需求维度覆盖度 ≥80% |
| **降低用户门槛** | 用户不需要一次性提供完整信息 | 3-5轮对话即可完成 |
| **自适应深度** | 简单需求快问快走，复杂需求深挖 | Quick(2min) / Standard(5min) / Deep(10min) |
| **无缝对接** | 输出直接喂给 Solution Pro | requirement_spec.json → Planning Worker |
| **质量可衡量** | 收集完的需求有质量评分 | 完整性评分 ≥ 70/100 |

### 2.3 与 Solution Pro 的关系

```
需求收集模块                    Solution Pro
┌─────────────┐               ┌──────────────────┐
│  输入:      │               │  输入:            │
│  模糊想法   │──→ 结构化 ──→│  requirement_spec │
│  一句话     │   需求文档    │  .json            │
└─────────────┘               └──────────────────┘
     ↑                              ↓
   用户                        final_solution.md
```

**关键洞察**: 需求收集模块不是替代 Solution Pro 的 Planning 阶段，而是为 Planning 提供 **足够丰富的输入**。Planning 仍然负责制定研究计划，但它不再需要"猜"用户想要什么。

---

## 3. 业界最佳实践研究

### 3.1 传统需求工程方法论

| 方法论 | 核心思想 | 适用场景 | 我们的借鉴 |
|--------|---------|---------|-----------|
| **IREB (国际需求工程委员会)** | 需求 elicitation → documentation → validation → management | 企业级软件项目 | ✅ 需求分类框架（功能/非功能/约束） |
| **BABOK (业务分析知识体系)** | 业务需求 → 利益相关者需求 → 解决方案需求 | 业务系统设计 | ✅ 多层需求分解 |
| **User Story Mapping** | 用户活动 → 用户任务 → 用户故事 | 产品设计 | ✅ 用户旅程视角 |
| **Jobs to be Done (JTBD)** | 关注用户"雇佣"产品来完成的任务 | 产品创新 | ✅ 目标导向的需求发现 |

### 3.2 AI 辅助需求收集最新趋势 (2025-2026)

| 趋势 | 描述 | 工具/平台 | 我们的应用 |
|------|------|----------|-----------|
| **Guided Discovery** | AI 通过结构化问题引导发现需求全貌 | Requiment | ✅ 多轮对话引导 |
| **Context Engineering** | 提供详细上下文给 AI，提升输出质量 | GenAI最佳实践 | ✅ 上下文模板 |
| **Automated Documentation** | AI 将散乱输入转为结构化需求文档 | ReqSpell, Aqua | ✅ 自动结构化 |
| **Voice-to-Requirement** | 语音转需求 | Aqua | 🔵 未来可考虑 |
| **AI-Driven Prioritization** | AI 分析数据辅助需求优先级 | aqua-cloud | ✅ 智能优先级建议 |
| **Duplicate Detection** | 检测重复需求 | ReqSpell | 🔵 中期考虑 |
| **Iterative Refinement** | AI 输出作为草稿，人工迭代验证 | 行业共识 | ✅ 确认-修正循环 |

### 3.3 业界需求收集维度框架

基于 IREB + BABOK + 业界 AI 工具综合分析，高质量需求应覆盖以下维度:

```
需求质量维度（7大维度）
├── 1. 业务上下文 (Business Context)
│   ├── 业务目标/痛点
│   ├── 市场环境
│   └── 成功指标/KPI
├── 2. 用户与场景 (Users & Scenarios)
│   ├── 用户角色/画像
│   ├── 使用场景
│   └── 用户旅程
├── 3. 功能需求 (Functional Requirements)
│   ├── 核心功能
│   ├── 功能优先级
│   └── 功能间依赖
├── 4. 非功能需求 (Non-Functional Requirements)
│   ├── 性能指标
│   ├── 安全要求
│   ├── 可用性/可靠性
│   └── 可扩展性
├── 5. 约束条件 (Constraints)
│   ├── 预算约束
│   ├── 时间约束
│   ├── 技术约束
│   └── 组织/流程约束
├── 6. 集成与环境 (Integration & Environment)
│   ├── 已有系统/技术栈
│   ├── 集成接口要求
│   └── 部署环境
└── 7. 风险与假设 (Risks & Assumptions)
    ├── 已知风险
    ├── 关键假设
    └── 依赖项
```

---

## 4. 需求收集模块设计方案（初步）

### 4.1 设计原则

1. **对话式，不是表单式**: 不是让用户填表，而是像资深咨询师一样引导对话
2. **自适应深度**: 简单需求快问快走(2-3轮)，复杂需求深挖(5-8轮)
3. **渐进式**: 先收集核心信息，再按需深入
4. **确认-修正循环**: 每轮收集后总结给用户确认，而不是最后才确认
5. **输出标准化**: 输出 JSON 格式，Solution Pro 可直接消费
6. **与 DeepFlow 架构对齐**: 遵循三层架构、契约笼子、Blackboard 等现有机制

### 4.2 三模式设计

| 模式 | 触发条件 | 对话轮数 | 时间 | 适用场景 |
|------|---------|---------|------|---------|
| **Quick** | topic 已经比较清晰 + 用户说"快" | 1-2轮 | 2-3分钟 | "设计一个Redis集群方案，3主3从，预算10万" |
| **Standard** | 默认模式 | 3-5轮 | 5-8分钟 | "设计一个AI算力调度平台" |
| **Deep** | topic 复杂 + 用户说"深入" | 5-8轮 | 10-15分钟 | "设计一个企业级数据中台，要支持多租户..." |

### 4.3 对话流程设计

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: 理解 (Understand)                                       │
│ ├─ 解析用户初始输入                                               │
│ ├─ 识别已有信息 vs 缺失维度                                       │
│ └─ 输出: 初始需求画像 + 缺失维度清单                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: 引导 (Guide)                                            │
│ ├─ 按优先级询问缺失维度                                           │
│ ├─ 每轮 2-3 个问题（不超过3个，避免信息过载）                      │
│ ├─ 问题自适应（基于已收集信息动态调整下一个问题）                   │
│ └─ 输出: 增量需求信息                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: 结构化 (Structure)                                      │
│ ├─ 将所有收集到的信息结构化                                       │
│ ├─ 生成 requirement_spec.json                                    │
│ ├─ 质量评估（7维度完整性评分）                                    │
│ └─ 输出: 结构化需求文档 + 质量评分                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: 确认 (Confirm)                                          │
│ ├─ 向用户展示结构化需求摘要                                       │
│ ├─ 用户确认/修正                                                  │
│ ├─ 如有修正 → 更新 requirement_spec.json                         │
│ └─ 输出: 最终需求文档（用户已确认）                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    喂给 Solution Pro
```

### 4.4 输出数据结构（requirement_spec.json）

```json
{
  "meta": {
    "version": "1.0",
    "created_at": "2026-05-23T15:30:00+08:00",
    "collection_mode": "standard",
    "conversation_rounds": 4,
    "quality_score": 82
  },
  "business_context": {
    "objective": "建设企业级AI算力调度平台，统一管理GPU资源",
    "pain_points": [
      "GPU利用率仅30%，资源浪费严重",
      "多团队争抢GPU资源，缺乏统一调度"
    ],
    "success_metrics": [
      {"metric": "GPU利用率", "target": "≥70%", "current": "30%"},
      {"metric": "任务排队时间", "target": "<30分钟", "current": "2-4小时"}
    ],
    "market_context": "2026年AI算力市场快速增长，GPU成本占IT预算40%+"
  },
  "users_and_scenarios": {
    "user_roles": [
      {"role": "AI研究员", "count": "~50人", "key_needs": "快速提交训练任务"},
      {"role": "运维工程师", "count": "~10人", "key_needs": "资源监控和告警"},
      {"role": "部门主管", "count": "~5人", "key_needs": "成本分析和预算"}
    ],
    "key_scenarios": [
      "研究员提交大模型训练任务，期望24h内开始",
      "运维发现GPU故障，需要自动迁移任务",
      "月度成本分析，按部门/项目统计GPU费用"
    ]
  },
  "functional_requirements": [
    {"id": "FR-001", "description": "任务提交与调度", "priority": "P0"},
    {"id": "FR-002", "description": "资源监控大盘", "priority": "P0"},
    {"id": "FR-003", "description": "成本分析与配额管理", "priority": "P1"}
  ],
  "non_functional_requirements": [
    {"id": "NFR-001", "category": "性能", "description": "支持10000+并发任务调度", "priority": "P0"},
    {"id": "NFR-002", "category": "可用性", "description": "调度系统99.99%可用", "priority": "P0"},
    {"id": "NFR-003", "category": "安全", "description": "多租户数据隔离", "priority": "P0"}
  ],
  "constraints": {
    "budget": "500万以内",
    "timeline": "6个月上线MVP",
    "tech_stack": ["Kubernetes", "已有阿里云ACK集群"],
    "org_constraints": "需要跟现有DevOps流程对接"
  },
  "integration": {
    "existing_systems": [
      {"name": "阿里云ACK", "role": "容器编排平台"},
      {"name": "GitLab CI/CD", "role": "持续部署"},
      {"name": "Prometheus+Grafana", "role": "现有监控"}
    ],
    "integration_requirements": [
      "需对接现有LDAP统一认证",
      "需对接现有日志系统(ELK)"
    ]
  },
  "risks_and_assumptions": {
    "known_risks": [
      "GPU供应商交付周期不确定",
      "多租户隔离可能影响性能"
    ],
    "key_assumptions": [
      "已有ACK集群可扩展到100节点",
      "各团队愿意接受配额管理"
    ]
  },
  "stakeholders": ["技术VP", "AI部门负责人", "运维团队", "财务部门"],
  "solution_pro_hints": {
    "recommended_solution_type": "architecture",
    "recommended_focus_areas": [
      {"area": "调度算法", "weight": 0.3, "reason": "核心差异化"},
      {"area": "资源管理", "weight": 0.25, "reason": "直接影响利用率"},
      {"area": "成本优化", "weight": 0.2, "reason": "ROI关键"},
      {"area": "安全隔离", "weight": 0.15, "reason": "多租户必须"},
      {"area": "监控运维", "weight": 0.1, "reason": "运营保障"}
    ],
    "layer2_constraints_hint": {
      "researcher": [
        "必须调研主流GPU调度方案（如Run:ai, Volcano）",
        "必须分析阿里云ACK GPU调度能力"
      ],
      "auditor": [
        "审计是否考虑了GPU碎片化问题",
        "验证多租户隔离方案的可行性"
      ]
    }
  }
}
```

### 4.5 质量评估模型

```
需求质量评分 = Σ(维度权重 × 维度得分) / 7

维度权重:
├── 业务上下文: 20% (最高，决定方向)
├── 用户与场景: 15%
├── 功能需求: 15%
├── 非功能需求: 15%
├── 约束条件: 15%
├── 集成与环境: 10%
└── 风险与假设: 10%

维度得分:
- 0分: 完全缺失
- 40分: 有信息但严重不足
- 70分: 基本满足，有改进空间
- 100分: 充分、清晰、可操作

整体质量等级:
- ≥85: Excellent (Solution Pro 可高质量执行)
- ≥70: Good (Solution Pro 可正常执行)
- ≥50: Acceptable (Solution Pro 可执行，但部分阶段可能不够深入)
- <50: Insufficient (需要继续收集，不建议启动 Solution Pro)
```

### 4.6 与 DeepFlow 架构的集成方案

```
现有架构:
  Main Agent → sessions_spawn → SolutionOrchestratorV21 → 10阶段管线

新增模块:
  Main Agent → RequirementCollector → requirement_spec.json
                                              ↓
             sessions_spawn → SolutionOrchestratorV21(requirement_spec=...) → 10阶段管线

集成点:
  1. RequirementCollector 作为 core/ 下的独立模块
  2. SolutionOrchestratorV21 新增 requirement_spec 参数
  3. Planning Worker 的输入从 topic → requirement_spec
  4. Data Collection Worker 的搜索策略基于 requirement_spec 优化
  5. Blackboard 新增 data/requirement_spec.json
```

---

## 5. 开放问题（需要对齐）

### 5.1 模块形态

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A. 主Agent对话式** | 我（小满）直接跟你对话收集需求 | 自然、灵活、可以利用已有上下文 | 不是自动化管线，依赖我的能力 |
| **B. 子Agent自动化** | 作为 Solution Pro 的 Stage 0，自动执行 | 全自动，无需主Agent介入 | 子Agent无法跟用户交互（OpenClaw限制） |
| **C. 混合模式（推荐）** | 主Agent引导对话 + 子Agent做结构化/评估 | 兼顾交互+自动化 | 实现稍复杂 |

### 5.2 输出粒度

需求收集到什么程度算"够了"？
- **最小可行**: 业务目标 + 核心功能 + 关键约束 (3个维度)
- **标准**: + 用户场景 + 非功能需求 + 集成环境 (6个维度)
- **完整**: + 风险分析 + 成功标准 + Solution Pro hints (全部7个维度)

### 5.3 与现有 Data Collection Worker 的关系

| 选项 | 描述 |
|------|------|
| **A. 替代** | 需求收集模块替代 Data Collection Worker |
| **B. 前置（推荐）** | 需求收集模块在 Data Collection 之前，Data Collection 基于 requirement_spec 做更精准的搜索 |
| **C. 合并** | 把需求收集能力合并到 Data Collection Worker 中 |

### 5.4 是否需要前端 UI

| 选项 | 描述 |
|------|------|
| **A. 纯对话（推荐先做）** | 通过飞书/WebChat 对话完成 |
| **B. 前端表单** | DeepFlow 前端增加需求收集表单 |
| **C. 混合** | 对话 + 可视化需求看板 |

### 5.5 实现优先级

你希望我现在就写代码实现，还是先做以下哪项？
1. 先做 POC（我直接对话收集一个需求，验证输出质量）
2. 先做完整设计文档（技术架构 + 接口定义 + Prompt 设计）
3. 直接开始编码（按契约笼子流程）

---

## 6. 我的建议

### 推荐方案: 混合模式 + 渐进式开发

**Phase 1 (现在)**: 
- 需求收集作为**主Agent对话流程**（我直接引导你收集需求）
- 输出 requirement_spec.json 写入 Blackboard
- Solution Pro Planning Worker 读取 requirement_spec.json

**Phase 2 (中期)**:
- 封装为 RequirementCollector 类
- 支持 Quick/Standard/Deep 三模式
- 自动化质量评估

**Phase 3 (远期)**:
- 集成到 DeepFlow 前端
- 支持需求模板（不同行业/场景）
- 历史需求复用（相似项目的需求基线）

**理由**:
1. Phase 1 最快验证价值——不需要写代码，我现在就能做
2. 通过实际使用验证需求维度框架是否合理
3. 确认 Solution Pro 消费 requirement_spec 的效果后再投入开发

---

*等待忠礼确认方向后，进入具体设计和实施阶段。*
