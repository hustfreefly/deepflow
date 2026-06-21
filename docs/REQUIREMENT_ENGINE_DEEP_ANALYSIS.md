# 需求引擎深度分析 —— 从业界最优实践到 DeepFlow 定位

> **版本**: v1.0
> **日期**: 2026-05-23
> **作者**: 小满 🦞
> **状态**: 深度研究 + 概念重构

---

## 1. 重新理解问题：你说的 vs 我原先理解的

### 1.1 我之前的理解（偏差）

```
需求收集 → Solution Pro → 评估
 Stage 0     Stage 1-10    Stage 11
```
把需求收集当作 Solution Pro 的"前门"，线性流水线。

### 1.2 你实际在说的（正确理解）

```
         ┌─────────────────────────────────────────┐
         │          DeepFlow Loop 系统              │
         │                                         │
         │   ┌──────────┐                          │
         │   │ 需求引擎  │ ← 独立引擎，不是 Stage 0 │
         │   └─────┬────┘                          │
         │         ↓                               │
         │   ┌──────────┐                          │
         │   │Solution  │ ← 执行引擎               │
         │   │  Pro     │                          │
         │   └─────┬────┘                          │
         │         ↓                               │
         │   ┌──────────┐                          │
         │   │ 评估引擎  │ ← 独立引擎              │
         │   └─────┬────┘                          │
         │         │                               │
         │         ↓ (需要迭代？)                   │
         │    Yes → 回到需求引擎（增量补充）         │
         │    No  → 输出最终交付物                  │
         └─────────────────────────────────────────┘
```

**关键差异**:
- 三个引擎**并列**，不是从属
- 需求引擎是 Loop 的**入口和回流点**
- 它"承上启下"——连接用户世界和 AI 世界

---

## 2. 业界深度研究：5个关键模式

### 2.1 Perfection System（完美系统）

> 来源: Google ADK, Claude Code 社区, 2025-2026 多Agent设计模式

**核心模式**:
```
Generator（生成）→ Critic × N（多维评审）→ Revision（修正）→ 循环直到完美
```

**角色分离（关键原则）**:
- **Generator/Worker**: 唯一可以修改产物的 Agent
- **Critic/Diagnosis**: 只能诊断问题，**不能修改**产物
- **Loop Agent**: 控制循环，决定何时终止
- **Planning Agent**: 解读 Critic 报告，生成变更清单

**终止条件**:
- 所有 Critic 一致通过（unanimous approval）
- 或达到质量阈值
- 或达到最大迭代次数（安全阀）

**对我们的启发**:
- Solution Pro 已经有 Generator（Workers）+ Critic（Auditors）+ Harness（质量门禁）
- 缺失的是：**当 Critic 发现的问题追溯到需求层面时，谁来补需求？**
- → 这就是需求引擎的核心价值：**它是 Loop 中的"需求修复器"**

### 2.2 LangGraph 状态机 + Checkpoint + HITL

> 来源: LangChain/LangGraph 官方, IBM, AWS Bedrock AgentCore

**核心设计**:
```
State Machine（图结构）
  ├─ Nodes: 各个处理步骤
  ├─ Edges: 步骤间的流转（支持条件分支 + 循环）
  ├─ Checkpoints: 每步保存状态快照
  └─ Interrupts: 在关键点暂停，等待人类输入
```

**HITL 四种模式**:
1. **Review**: 人类审查 Agent 的输出
2. **Approve/Reject**: 人类批准或拒绝高风险操作
3. **Provide Context**: 人类补充 Agent 需要的信息 ← **这就是需求收集！**
4. **Correct**: 人类修正 Agent 的错误

**对我们的启发**:
- 需求引擎本质上就是 Loop 中的 **"Provide Context" 节点**
- 它不需要每次都从头开始——Checkpoint 机制让它可以从上次中断处继续
- 这天然支持"增量补充"场景

### 2.3 Context Engineering（上下文工程）

> 来源: 2025-2026 行业共识, Anthropic, OpenAI, Addy Osmani (Google)

**核心观点**:
> "The quality of AI output is bounded by the quality of its context, not the quality of its model."

**Living Spec（活文档）**:
- 需求文档不是静态的，而是随项目演进而持续更新的
- 包含: Agent角色 + 架构关键文件 + 代码风格示例 + 三层边界（Always/Ask first/Never）
- 每次 Loop 迭代都更新 Spec

**三层边界模型（Guardrails）**:
| 层级 | 含义 | 映射到我们的场景 |
|:---|:---|:---|
| **Always do** | Agent 必须自主执行 | "必须调研国产方案" |
| **Ask first** | 需要人类确认 | "数据库选型需确认" |
| **Never do** | 绝对禁止 | "不得修改生产环境配置" |

**对我们的启发**:
- 需求引擎的产出不是一次性的 JSON，而是一个 **Living Spec**
- 它随着 Loop 不断演化，每一轮都更精确
- Solution Pro 的每一轮执行都基于 Spec 的**最新版本**

### 2.4 Information Asymmetry Bridge（信息不对称桥梁）

> 来源: IREB 需求工程, BABOK 业务分析, MIT Sloan

**核心洞察**:
> 用户知道"他要什么"，但不知道"AI需要什么信息才能做好"。
> AI 知道"它需要什么信息"，但不知道"用户知道什么"。

**需求工程的核心问题就是弥合这个信息鸿沟**:

```
用户心智模型                    AI 执行模型
┌─────────────┐               ┌─────────────────┐
│ "我要一个    │    需求引擎    │  topic: ...      │
│  AI算力平台" │ ──→ 桥梁 ──→ │  constraints: [] │
│              │               │  stakeholders: []│
│ (大量隐含    │               │  (结构化，但     │
│  未表达信息) │               │   可能不完整)    │
└─────────────┘               └─────────────────┘
```

**三种弥合策略**:
1. **Elicitation（引导发现）**: 通过提问挖掘用户未说出的信息
2. **Inference（推理补全）**: 基于行业知识推断缺失信息（标注为"推断，待确认"）
3. **Validation（验证确认）**: 把推断结果给用户确认

**对我们的启发**:
- 需求引擎不只是"收集"，还要"推断 + 验证"
- 这大幅降低用户负担——不需要事无巨细地描述

### 2.5 Mixture of Agents + Reflection（混合Agent + 反思）

> 来源: AutoGen, Microsoft Agent Framework

**Mixture of Agents 模式**:
```
Orchestrator（编排器）
  ├─ Layer 1: 多个 Worker Agent 并行处理
  ├─ Layer 2: 聚合结果
  ├─ Layer 3: 反思 + 发现盲区
  └─ 循环: 带着反思结果重新执行
```

**对我们的启发**:
- 需求引擎本身也可以用多 Agent 架构
- 一个 Agent 引导对话，另一个 Agent 做推理补全，第三个 Agent 做质量评估
- 但这是优化，不是核心——先把单 Agent 做对

---

## 3. 重新定义需求引擎

### 3.1 它不是什么

| 它不是... | 为什么不是 |
|:---|:---|
| Solution Pro 的 Stage 0 | 它是独立引擎，在 Loop 中反复被调用 |
| 一个表单/问卷 | 它是智能对话，自适应引导 |
| 一次性的数据收集 | 它产出 Living Spec，随 Loop 演化 |
| 被动的信息接收器 | 它主动推断 + 验证 + 发现盲区 |

### 3.2 它是什么

**需求引擎 = DeepFlow Loop 系统的"上下文工程引擎"**

它的核心职责是：
1. **弥合信息鸿沟**: 把用户的心智模型转化为 AI 可执行的结构化上下文
2. **维护 Living Spec**: 需求文档随 Loop 迭代持续演化
3. **承上启下**: 向上连接用户（对话），向下喂养 Solution Pro（结构化输入）
4. **Loop 回流点**: 当评估引擎发现需求层面的问题时，需求引擎负责修复

### 3.3 三引擎协作模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DeepFlow 三引擎系统                           │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐      │
│  │  需求引擎     │    │  Solution Pro │    │  评估引擎        │      │
│  │  (Context     │    │  (Execution   │    │  (Evaluation     │      │
│  │   Engine)     │    │   Engine)     │    │   Engine)        │      │
│  ├──────────────┤    ├──────────────┤    ├──────────────────┤      │
│  │ 职责:        │    │ 职责:        │    │ 职责:            │      │
│  │ • 引导对话   │    │ • 10阶段管线 │    │ • 方案评估       │      │
│  │ • 推断补全   │    │ • 多Agent    │    │ • 需求覆盖度     │      │
│  │ • 结构化     │    │ • 质量门控   │    │ • 问题溯源       │      │
│  │ • 质量评估   │    │ • 研究报告   │    │ • Loop 决策      │      │
│  ├──────────────┤    ├──────────────┤    ├──────────────────┤      │
│  │ 输入:        │    │ 输入:        │    │ 输入:            │      │
│  │ • 用户对话   │    │ • Living Spec│    │ • Living Spec    │      │
│  │ • 评估反馈   │    │ • 约束条件   │    │ • final_solution │      │
│  │ • 历史Spec   │    │ • stakeholder│    │ • harness_final  │      │
│  ├──────────────┤    ├──────────────┤    ├──────────────────┤      │
│  │ 输出:        │    │ 输出:        │    │ 输出:            │      │
│  │ • Living Spec│    │ • solution   │    │ • evaluation.json│      │
│  │ • delta.json │    │ • harness    │    │ • loop_advice    │      │
│  └──────────────┘    └──────────────┘    └──────────────────┘      │
│         ↑                                        │                  │
│         └──────── Loop（迭代优化）────────────────┘                  │
│                                                                     │
│  共享状态: Blackboard/{session_id}/                                 │
│  ├── spec/                  (需求引擎产出)                          │
│  │   ├── living_spec.json   (当前版本)                              │
│  │   ├── spec_v1.json       (历史版本)                              │
│  │   └── delta.json         (变更记录)                              │
│  ├── stages/                (Solution Pro 产出)                     │
│  │   └── ...                                                       │
│  └── evaluation/            (评估引擎产出)                          │
│      ├── eval_v1.json                                              │
│      └── loop_advice.json                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. 需求引擎的场景矩阵

### 4.1 四大场景

| 场景 | 名称 | 触发条件 | 引擎行为 | 典型对话 |
|:---|:---|:---|:---|:---|
| **S1: Genesis** | 创世 | 全新任务，无历史 | 完整引导，从零构建 Spec | "设计一个AI算力调度平台" |
| **S2: Supplement** | 补充 | 已有 Spec，用户想补充 | 定向深入，只问缺失维度 | "补充一下安全需求" |
| **S3: Refine** | 精化 | Loop 中评估反馈 | 精准修复，针对评估问题 | 评估说"安全需求太笼统"→ 追问细节 |
| **S4: Pivot** | 转向 | 用户对方案方向不满 | 保留历史，重新梳理 | "方向不对，我们换个思路" |

### 4.2 场景切换状态机

```
            ┌─────────┐
            │  START   │
            └────┬─────┘
                 │
           ┌─────┴──────┐
           │            │
     有历史Spec?    无历史Spec
           │            │
           ↓            ↓
    ┌──────────┐  ┌──────────┐
    │ Supplement│  │ Genesis  │
    │ / Refine  │  │          │
    └─────┬────┘  └─────┬────┘
          │              │
          ↓              ↓
    ┌──────────────────────┐
    │    Living Spec 更新    │
    └──────────┬───────────┘
               ↓
    ┌──────────────────────┐
    │  Solution Pro 执行    │
    └──────────┬───────────┘
               ↓
    ┌──────────────────────┐
    │  评估引擎 评估        │
    └──────────┬───────────┘
               ↓
        ┌──────┴──────┐
        │             │
   需要Loop?      不需要Loop
        │             │
        ↓             ↓
  ┌──────────┐  ┌──────────┐
  │ Refine   │  │  DONE    │
  │ (回到    │  │ 输出交付物│
  │  需求引擎)│  └──────────┘
  └──────────┘
```

---

## 5. 需求引擎的内部架构

### 5.1 核心组件

```
┌─────────────────────────────────────────────────────────────────┐
│                       Requirement Engine                        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Spec Manager (核心)                     │  │
│  │                                                          │  │
│  │  职责:                                                   │  │
│  │  - 管理 Living Spec 的完整生命周期                        │  │
│  │  - 版本控制（v1, v2, ...）                               │  │
│  │  - 增量变更追踪（delta.json）                             │  │
│  │  - 与 Blackboard 集成                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │  Dialog Agent   │  │  Inference     │  │  Quality       │   │
│  │  (对话引导)     │  │  Engine        │  │  Assessor      │   │
│  │                 │  │  (推理补全)    │  │  (质量评估)    │   │
│  │ • 理解用户意图  │  │               │  │               │   │
│  │ • 生成引导问题  │  │ • 行业知识推断│  │ • 7维度评分   │   │
│  │ • 确认-修正循环 │  │ • 缺失项补全  │  │ • 缺失项清单  │   │
│  │ • 摘要展示     │  │ • 标注"推断"  │  │ • Loop建议    │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
│                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │  Scenario       │  │  Knowledge     │  │  Loop          │   │
│  │  Router         │  │  Base          │  │  Context       │   │
│  │  (场景路由)     │  │  (知识库)      │  │  Manager       │   │
│  │                 │  │               │  │  (Loop上下文)  │   │
│  │ • Genesis      │  │ • 行业模板    │  │               │   │
│  │ • Supplement   │  │ • 历史Spec    │  │ • 评估反馈    │   │
│  │ • Refine       │  │ • 最佳实践    │  │ • 变更记录    │   │
│  │ • Pivot        │  │               │  │ • 收敛检测    │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Living Spec 数据结构（重构版）

```json
{
  "meta": {
    "engine_version": "1.0",
    "spec_version": 3,
    "scenario": "refine",
    "created_at": "2026-05-23T15:00:00+08:00",
    "updated_at": "2026-05-23T16:30:00+08:00",
    "quality_score": 88,
    "loop_round": 2
  },
  
  "layers": {
    "confirmed": {
      "_description": "用户已确认的需求，权威来源",
      "business_context": { ... },
      "users_and_scenarios": { ... },
      "functional_requirements": [ ... ],
      "non_functional_requirements": [ ... ],
      "constraints": { ... },
      "integration": { ... }
    },
    "inferred": {
      "_description": "AI 推断的需求，标注待确认",
      "items": [
        {
          "id": "INF-001",
          "dimension": "non_functional_requirements",
          "content": "预计需要支持多租户数据隔离",
          "confidence": 0.75,
          "inference_basis": "类似AI平台通常需要多租户",
          "status": "pending_confirmation"
        }
      ]
    },
    "guardrails": {
      "always_do": ["必须调研国产方案", "必须考虑成本优化"],
      "ask_first": ["数据库选型需用户确认"],
      "never_do": ["不得修改生产环境"]
    }
  },
  
  "solution_pro_context": {
    "recommended_type": "architecture",
    "focus_areas": [ ... ],
    "layer2_hints": { ... },
    "anti_patterns": ["不要过度设计", "避免引入过多开源组件"]
  },
  
  "loop_context": {
    "previous_issues": [
      "安全需求过于笼统（来自评估 v1）"
    ],
    "resolved_in_this_round": [
      "安全需求已细化：多租户隔离 + 审计日志 + 数据加密"
    ],
    "remaining_gaps": []
  }
}
```

**关键设计**: 
- **三层分离**: confirmed（已确认）/ inferred（推断待确认）/ guardrails（边界）
- **推断标注**: AI 推断的内容明确标记，不影响 Solution Pro 执行，但会提示用户确认
- **Loop 上下文**: 记录每一轮修复了什么、还剩什么

---

## 6. 与 Solution Pro 的集成方式

### 6.1 Solution Pro 的消费方式

```python
# Solution Pro 接收 Living Spec 作为上下文
class SolutionOrchestratorV21:
    def __init__(self, topic, ..., living_spec=None):
        self.living_spec = living_spec
    
    def get_all_tasks(self):
        # 每个 Worker 的 Task 都注入 Living Spec 的相关部分
        for stage in pipeline:
            if stage == "planning":
                tasks[stage] = build_planner_task(
                    ...,
                    living_spec=self.living_spec  # ← 完整 Spec
                )
            elif stage == "research":
                tasks[stage] = build_researcher_task(
                    ...,
                    focus_areas=self.living_spec["solution_pro_context"]["focus_areas"],
                    guardrails=self.living_spec["layers"]["guardrails"]
                )
            elif stage == "harness_final":
                tasks[stage] = build_harness_final_task(
                    ...,
                    confirmed_requirements=self.living_spec["layers"]["confirmed"]
                    # ← Harness 基于 confirmed 需求做覆盖度评估
                )
```

### 6.2 评估引擎的反馈格式

```json
{
  "evaluation": {
    "coverage_score": 0.72,
    "requirement_gaps": [
      {
        "dimension": "non_functional_requirements",
        "specific": "安全需求过于笼统，无法设计具体隔离方案",
        "severity": "high",
        "loop_target": "requirement_engine"
      }
    ],
    "solution_gaps": [
      {
        "aspect": "数据迁移",
        "specific": "缺少从旧系统迁移的方案",
        "severity": "medium",
        "loop_target": "solution_pro"
      }
    ]
  },
  "loop_advice": {
    "should_loop": true,
    "requirement_engine_tasks": [
      "细化安全需求：多租户隔离方案、数据加密策略、审计日志要求"
    ],
    "solution_pro_tasks": [
      "补充数据迁移方案设计"
    ]
  }
}
```

### 6.3 需求引擎处理 Loop 回流

```
评估引擎输出 loop_advice.requirement_engine_tasks
  ↓
需求引擎 Scenario Router:
  ├─ 有 requirement_engine_tasks → 场景 = Refine
  ├─ Refine 模式下:
  │   1. 读取 living_spec 的当前版本
  │   2. 读取 loop_advice 中的具体任务
  │   3. 只针对这些任务生成引导问题
  │   4. 与用户对话收集补充信息
  │   5. 更新 living_spec（新版本）
  │   6. 生成 delta.json（变更记录）
  │   7. 重新喂给 Solution Pro（只重做受影响的阶段）
```

---

## 7. 关键设计决策（更新版）

### 7.1 需求引擎的实现形态

| 选项 | 描述 | 分析 |
|:---|:---|:---|
| A. Python 类 + 主Agent对话 | `RequirementEngine` 类封装逻辑，主Agent（小满）负责对话 | ✅ 最灵活，利用主Agent的上下文能力 |
| B. 纯子Agent | 完全自动化，无需主Agent | ❌ 子Agent无法跟用户交互 |
| C. Prompt-only | 只做 Prompt 模板，不做代码 | ⚠️ 太轻，无法管理状态 |

**推荐: A**

理由:
- 需求引擎的核心是**对话**，而 OpenClaw 的主Agent（我）天然具备对话能力
- Python 类负责**状态管理**（Living Spec 版本控制、质量评估、场景路由）
- 我负责**对话引导**（理解用户意图、生成问题、确认修正）
- 这跟 DeepFlow 的"主Agent + 子Agent"模式一致

### 7.2 需求维度的重新思考

原来我提的 7 维度框架还是偏传统。基于业界最新实践，重构为:

```
Living Spec 维度（面向 AI Agent 执行优化）
├── 1. 目标与痛点 (Why)
│   ├── 核心问题是什么
│   ├── 为什么要解决
│   └── 成功长什么样
├── 2. 用户与场景 (Who & When)
│   ├── 谁在用
│   ├── 在什么场景下用
│   └── 用户旅程
├── 3. 能力要求 (What)
│   ├── 必须做什么（Always）
│   ├── 应该做什么（Should）
│   └── 不能做什么（Never）
├── 4. 质量属性 (How Well)
│   ├── 性能指标
│   ├── 安全合规
│   └── 可用性/可靠性
├── 5. 约束边界 (Boundaries)
│   ├── 预算/时间
│   ├── 技术约束
│   └── 组织约束
├── 6. 环境与集成 (Where)
│   ├── 已有系统
│   ├── 集成接口
│   └── 部署环境
└── 7. 已知风险与假设 (What If)
    ├── 已知风险
    ├── 关键假设
    └── 依赖项
```

**变化**: 
- 维度 3 从"功能需求"变成"能力要求"，用 Always/Should/Never 三层表达
- 这是业界 Living Spec 的标准做法，更适合 AI Agent 消费

### 7.3 需求引擎的"推断-验证"机制

这是区别于传统"需求收集"的关键创新:

```
步骤 1: 用户说 "设计一个AI算力调度平台"

步骤 2: 需求引擎不只是问问题，它先做推断:
  ┌─────────────────────────────────────────────────────────┐
  │ 推断结果（基于行业知识）:                                │
  │                                                         │
  │ ✅ 推断: 用户可能需要 GPU 资源调度（置信度 0.95）        │
  │ ✅ 推断: 可能需要支持多种 GPU 类型（A100/H100）（0.8）   │
  │ ❓ 推断: 可能需要多租户隔离（0.6，待确认）              │
  │ ❓ 推断: 可能需要对接 Slurm/PBS（0.5，待确认）          │
  │ ⬜ 缺失: 预算范围（无法推断）                           │
  │ ⬜ 缺失: 已有基础设施（无法推断）                       │
  └─────────────────────────────────────────────────────────┘

步骤 3: 需求引擎的提问策略变为:
  "基于你说的AI算力调度平台，我推断你可能需要:
   1. GPU 资源统一调度（A100/H100 混合集群）
   2. 多租户隔离（不同部门独立资源池）
   3. 对接现有调度系统（Slurm 或 K8s）
   
   以上哪些是对的？哪些需要调整？
   另外我还需要知道:
   - 大概的预算和上线时间？
   - 已经有哪些基础设施？"

→ 这比"请告诉我你的需求"高效 10 倍
```

---

## 8. 待对齐的核心问题

### 8.1 需求引擎的产出标准

我提议 Living Spec 的质量标准:

| 级别 | 覆盖度 | 适用场景 | Solution Pro 行为 |
|:---|:---|:---|:---|
| **S** (90+) | 7维度全覆盖 + 三层边界清晰 | 企业级关键项目 | Pro 模式全力执行 |
| **A** (75-89) | 核心维度覆盖 + 部分推断 | 一般企业项目 | Standard 模式 |
| **B** (60-74) | 目标+能力+约束覆盖 | 快速探索 | Quick 模式 |
| **C** (<60) | 信息严重不足 | 不建议启动 | 提示用户补充 |

### 8.2 Loop 的颗粒度控制

当评估引擎说"需要 Loop"时:
- **粗颗粒**: Solution Pro 全部重跑（简单但浪费）
- **细颗粒**: 只重做受影响的阶段（高效但复杂）
- **推荐**: 先做粗颗粒，验证 Loop 价值后再优化

### 8.3 第一步做什么

我建议:
1. **先对齐概念**: 确认"三引擎 + Living Spec + 四场景"这个框架
2. **再做架构设计**: 详细技术架构（接口定义 + 数据结构 + Prompt 设计）
3. **然后 POC**: 我用一个真实需求跑一遍完整 Loop（需求→方案→评估→补充需求→再方案）
4. **最后编码**: 按契约笼子流程实施

---

## 9. 总结：需求引擎的本质

> **需求引擎不是"收集需求的工具"，而是 DeepFlow Loop 系统的"上下文工程引擎"。**
> 
> 它的核心能力是：
> 1. **弥合鸿沟** — 把用户心智模型转化为 AI 可执行的结构化上下文
> 2. **主动推断** — 不只是被动收集，而是基于行业知识主动推断 + 验证
> 3. **持续演化** — 产出 Living Spec，随 Loop 迭代不断更新
> 4. **精准修复** — 在 Loop 回流时，针对评估发现的具体问题精准补充

**一句话**: 需求引擎是连接"人的世界"和"AI 的世界"的桥梁，也是 Loop 系统的枢纽。

---

*等待忠礼确认概念框架后，进入详细技术架构设计。*
