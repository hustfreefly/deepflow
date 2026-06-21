# Spec Pro 概念设计 v2（终版）

> **版本**: v2.0 (概念对齐完成)
> **日期**: 2026-05-23
> **作者**: 小满 🦞
> **状态**: ✅ 概念已对齐，待进入技术架构

---

## 1. 定位

**Spec Pro = DeepFlow 的上下文工程引擎**

它负责弥合"用户心智模型"和"AI 执行模型"之间的信息鸿沟。
它不是 Solution Pro 的附属，也不是前置 Stage，而是一个独立模块，与 Solution Pro **配合**工作。

### 1.1 命名

| 模块 | 职责 | 关系 |
|:---|:---|:---|
| **Spec Pro** | 上下文工程：引导、收集、推断、结构化需求 | 智能前端 |
| **Solution Pro** | 方案设计：10阶段多Agent管线，深度研究+质量门控 | 重型执行引擎 |

Spec Pro 产出的 Living Spec 可以喂给 Solution Pro，也可以在未来喂给其他执行模块。
**谁来决定用哪个执行模块？** Spec Pro 有建议权（self-recommendation），但没有决定权。决定权留给用户或更高层的编排逻辑。

### 1.2 核心能力

| 能力 | 描述 |
|:---|:---|
| **引导对话** | 像资深咨询师一样引导用户梳理需求，不是填表 |
| **主动推断** | 基于行业知识推断缺失信息，标注置信度，让用户确认 |
| **结构化输出** | 产出 Living Spec（JSON），下游引擎可直接消费 |
| **质量评估** | 评估需求完整度，给出评分和缺失项清单 |
| **路由建议** | 根据任务复杂度建议执行引擎（轻量/Standard/Pro），但不做最终决定 |

---

## 2. 四场景设计

### 2.1 场景矩阵

| 场景 | 名称 | 触发条件 | Spec Pro 行为 | 优先级 |
|:---|:---|:---|:---|:---:|
| **S1: Genesis** | 创世 | 全新任务，无历史 Spec | 从零构建完整 Living Spec | 🔴 **首先实现** |
| **S2: Supplement** | 补充 | 已有 Spec，用户想补充 | 定向深入缺失维度，增量更新 | 🔵 后续 |
| **S3: Refine** | 精化 | Loop 中评估反馈 | 精准修复评估指出的问题维度 | 🔵 后续 |
| **S4: Pivot** | 转向 | 用户对方向不满 | 保留历史，重新梳理 | 🔵 后续 |

### 2.2 设计原则

- **Genesis 先行**: 先把从零到一做透，其他场景复用 Genesis 的核心组件
- **架构预留**: 数据结构、接口设计、状态管理都为 S2-S4 留好扩展点
- **不做过度设计**: 当前只实现 Genesis，但接口签名预留 `scenario` 参数

---

## 3. Genesis 场景详细设计

### 3.1 对话流程

```
用户输入（一句话或一段描述）
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Parse（解析）                                           │
│                                                                  │
│  • 解析用户输入，提取已有信息                                    │
│  • 行业知识推断：基于 topic 推断可能需要的维度                   │
│  • 输出: 初始需求画像（已填充 + 推断 + 缺失）                   │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Guide（引导对话）                                       │
│                                                                  │
│  循环:                                                           │
│  1. 质量评估当前 Spec                                            │
│  2. 判断是否达到阈值 → 是 → 跳到 Phase 3                        │
│  3. 生成 2-3 个引导问题（优先高权重缺失维度）                    │
│  4. 展示推断结果让用户确认                                       │
│  5. 用户回答 → 更新 Spec → 回到步骤 1                           │
│                                                                  │
│  停止条件:                                                       │
│  • 质量评分 ≥ 阈值（Quick:60 / Standard:75 / Deep:85）          │
│  • 达到最大轮数（Quick:3 / Standard:6 / Deep:10）               │
│  • 边际效益 < 3%（连续2轮提升微弱）                              │
│  • 用户说"够了"                                                 │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: Structure（结构化）                                     │
│                                                                  │
│  • 将所有对话内容结构化为 Living Spec                            │
│  • 区分 confirmed / inferred / guardrails 三层                  │
│  • 生成质量评估报告                                              │
│  • 生成路由建议（建议用哪个执行引擎）                            │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: Confirm（确认）                                         │
│                                                                  │
│  • 向用户展示 Spec 摘要                                          │
│  • 用户确认 / 修正                                               │
│  • 如有修正 → 更新 Spec → 重新展示                              │
│  • 用户确认后 → 写入 Blackboard                                  │
└─────────────────────────────────────────────────────────────────┘
  ↓
输出: living_spec.json + quality_report.json + route_recommendation.json
```

### 3.2 推断-验证机制（核心创新）

```
传统做法（被动收集）:
  用户: "设计AI算力平台"
  AI: "请问目标用户是谁？"  ← 从零开始问，效率低

Spec Pro 做法（推断-验证）:
  用户: "设计AI算力平台"
  AI: 基于行业知识推断:
      "AI算力平台通常需要关注:
       1. GPU资源调度（A100/H100混合集群）← 推断，置信度0.9
       2. 多租户隔离（不同部门独立资源池）← 推断，置信度0.7
       3. 任务队列与优先级管理            ← 推断，置信度0.8
       
       以上哪些符合你的情况？哪些需要调整？
       另外我还需要知道:
       - 预算和上线时间？          ← 无法推断，必须问
       - 已有哪些基础设施？        ← 无法推断，必须问"

  → 一轮对话 = 传统做法 3 轮的信息量
```

### 3.3 Living Spec 数据结构

```json
{
  "meta": {
    "engine": "spec_pro",
    "version": "1.0",
    "scenario": "genesis",
    "created_at": "2026-05-23T16:00:00+08:00",
    "conversation_rounds": 4,
    "quality_score": 82,
    "quality_level": "A"
  },

  "layers": {
    "confirmed": {
      "_doc": "用户已确认的需求，权威来源",
      "objective": "建设AI算力调度平台，统一管理GPU资源",
      "pain_points": [
        "GPU利用率仅30%",
        "各团队争抢资源，排队4小时+"
      ],
      "success_metrics": [
        {"metric": "GPU利用率", "target": "≥70%", "current": "30%"}
      ],
      "users": [
        {"role": "AI研究员", "count": "~50人", "key_needs": "快速提交训练任务"}
      ],
      "key_scenarios": [
        "研究员提交大模型训练任务，期望24h内开始"
      ],
      "capabilities": {
        "always_do": ["任务调度", "资源监控", "成本分析"],
        "should_do": ["自动扩缩容", "故障自愈"],
        "never_do": ["不允许跨租户数据访问"]
      },
      "quality_attributes": [
        {"category": "性能", "spec": "1000并发任务", "priority": "P0"},
        {"category": "可用性", "spec": "99.9%", "priority": "P0"}
      ],
      "constraints": {
        "budget": "500万",
        "timeline": "6个月MVP",
        "tech_stack": ["K8s", "阿里云ACK"]
      },
      "integration": {
        "existing_systems": [
          {"name": "阿里云ACK", "role": "容器编排"},
          {"name": "Prometheus+Grafana", "role": "监控"}
        ]
      },
      "risks_and_assumptions": {
        "risks": ["GPU供应商交付周期不确定"],
        "assumptions": ["ACK集群可扩展到100节点"]
      }
    },

    "inferred": {
      "_doc": "AI推断的需求，待用户确认",
      "items": [
        {
          "id": "INF-001",
          "dimension": "quality_attributes",
          "content": "预计需要审计日志（合规要求）",
          "confidence": 0.7,
          "basis": "企业级平台通常需要审计",
          "status": "pending_confirmation"
        }
      ]
    },

    "guardrails": {
      "always_do": ["必须调研国产方案", "必须考虑成本优化"],
      "ask_first": ["数据库选型", "GPU品牌选择"],
      "never_do": ["不得修改生产环境", "不得假设无限制预算"]
    }
  },

  "route_recommendation": {
    "suggested_engine": "solution_pro",
    "suggested_mode": "standard",
    "reasoning": "任务涉及多租户架构+资源调度+成本分析，复杂度中高，建议Solution Pro Standard模式",
    "confidence": 0.85
  },

  "solution_pro_hints": {
    "focus_areas": [
      {"area": "调度算法", "weight": 0.30, "reason": "核心差异化"},
      {"area": "资源管理", "weight": 0.25, "reason": "直接影响利用率"},
      {"area": "成本优化", "weight": 0.20, "reason": "ROI关键"},
      {"area": "安全隔离", "weight": 0.15, "reason": "多租户必须"},
      {"area": "监控运维", "weight": 0.10, "reason": "运营保障"}
    ],
    "layer2_hints": {
      "researcher": [
        "必须调研主流GPU调度方案（Run:ai, Volcano, HAMi）",
        "必须分析阿里云ACK GPU调度能力与局限"
      ],
      "auditor": [
        "审计是否考虑GPU碎片化问题",
        "验证多租户隔离方案可行性"
      ]
    },
    "anti_patterns": [
      "不要过度设计（先满足MVP）",
      "避免引入过多开源组件增加运维负担"
    ]
  }
}
```

### 3.4 质量评估模型

```
需求质量评分 = Σ(维度权重 × 维度得分)

维度与权重:
┌─────────────────────┬────────┬────────────────────────────────┐
│ 维度                 │ 权重   │ 评分标准                       │
├─────────────────────┼────────┼────────────────────────────────┤
│ 目标与痛点 (Why)     │  20%   │ 问题清晰、目标可衡量 = 100     │
│ 用户与场景 (Who)     │  15%   │ 角色明确、场景具体 = 100       │
│ 能力要求 (What)      │  15%   │ Always/Should/Never三层清晰    │
│ 质量属性 (How Well)  │  15%   │ 有具体指标和优先级             │
│ 约束边界 (Bounds)    │  15%   │ 预算/时间/技术约束明确         │
│ 环境与集成 (Where)   │  10%   │ 已有系统、集成接口清晰         │
│ 风险与假设 (What If) │  10%   │ 已识别关键风险和假设           │
└─────────────────────┴────────┴────────────────────────────────┘

质量等级:
┌───────┬──────────┬─────────────────────────────────────┐
│ 等级  │ 分数     │ 含义                                 │
├───────┼──────────┼─────────────────────────────────────┤
│ S     │ 90-100   │ 卓越：7维全覆盖，三层边界清晰        │
│ A     │ 75-89    │ 良好：核心维度覆盖，部分推断         │
│ B     │ 60-74    │ 可用：目标+能力+约束覆盖             │
│ C     │ <60      │ 不足：建议继续收集                   │
└───────┴──────────┴─────────────────────────────────────┘
```

### 3.5 路由建议（recommendation, not decision）

```json
{
  "route_recommendation": {
    "suggested_engine": "solution_pro | lightweight | direct_answer",
    "suggested_mode": "quick | standard | rigorous",
    "reasoning": "为什么这样建议",
    "confidence": 0.0-1.0,
    "complexity_assessment": {
      "score": 70,
      "factors": [
        "多租户架构 → 高复杂度",
        "已有K8s基础 → 降低复杂度",
        "预算明确 → 降低不确定性"
      ]
    },
    "disclaimer": "此建议仅供参考，最终执行引擎由用户或编排层决定"
  }
}
```

---

## 4. 技术架构（预留扩展）

### 4.1 模块结构

```
.deepflow/
├── core/
│   └── spec_pro/                    # ← Spec Pro 模块
│       ├── __init__.py
│       ├── engine.py                # SpecProEngine 主类
│       ├── spec_manager.py          # Living Spec 管理（版本控制、读写）
│       ├── quality_assessor.py      # 需求质量评估
│       ├── inference_engine.py      # 推断引擎（行业知识推断）
│       ├── dialog_manager.py        # 对话管理（状态机、轮次控制）
│       ├── route_recommender.py     # 路由建议
│       ├── models.py                # 数据结构定义
│       └── knowledge/               # 行业知识库
│           ├── templates/           # 行业需求模板
│           └── patterns/            # 常见需求模式
├── prompts/
│   └── spec_pro/                    # ← Spec Pro Prompt
│       ├── system.md                # 系统 Prompt
│       ├── parse.md                 # 解析 Prompt
│       ├── guide.md                 # 引导对话 Prompt
│       ├── infer.md                 # 推断 Prompt
│       ├── structure.md             # 结构化 Prompt
│       └── assess.md                # 评估 Prompt
└── blackboard/{session_id}/
    └── spec/                        # ← Spec Pro 产出
        ├── living_spec.json         # 当前 Living Spec
        ├── quality_report.json      # 质量评估报告
        └── route_recommendation.json# 路由建议
```

### 4.2 核心类设计（预留扩展）

```python
class SpecProEngine:
    """
    Spec Pro 主引擎
    
    Genesis 场景的完整实现，架构预留 Supplement/Refine/Pivot。
    """
    
    def __init__(self, 
                 scenario: str = "genesis",  # genesis | supplement | refine | pivot
                 mode: str = "standard",     # quick | standard | deep
                 existing_spec: dict = None, # 用于 supplement/refine/pivot
                 loop_context: dict = None,  # 用于 refine（评估反馈）
                 spawn_fn=None):
        """
        Args:
            scenario: 场景类型（当前只实现 genesis）
            mode: 对话深度
            existing_spec: 已有 Spec（S2/S3/S4 场景使用）
            loop_context: Loop 上下文（S3 场景使用，包含评估反馈）
        """
        self.scenario = scenario
        self.mode = mode
        self.existing_spec = existing_spec
        self.loop_context = loop_context
        # ...
    
    def collect(self, user_input: str, session_id: str) -> dict:
        """
        Genesis 场景：从零开始收集需求
        
        返回:
        {
            "living_spec": {...},
            "quality_report": {...},
            "route_recommendation": {...},
            "conversation_log": [...]
        }
        """
        # Phase 1: Parse
        initial_profile = self._parse(user_input)
        
        # Phase 2: Guide (对话循环)
        spec = initial_profile
        for round_num in range(self._max_rounds()):
            quality = self.quality_assessor.assess(spec)
            
            should_stop, reason = self._check_stop(round_num, quality)
            if should_stop:
                break
            
            questions = self._generate_questions(spec, quality)
            # → 返回给主Agent，等待用户回答
            yield {"type": "questions", "questions": questions, "quality": quality}
            # ← 主Agent传入用户回答
            user_answers = yield
            spec = self._update_spec(spec, user_answers)
        
        # Phase 3: Structure
        living_spec = self._structure(spec)
        
        # Phase 4: Confirm
        yield {"type": "summary", "living_spec": living_spec}
        # ← 用户确认/修正
        confirmation = yield
        
        # 写入 Blackboard
        self._save(session_id, living_spec)
        
        return {"living_spec": living_spec, ...}
    
    def supplement(self, existing_spec: dict, focus: str) -> dict:
        """S2: 补充场景（预留）"""
        raise NotImplementedError("Supplement scenario not yet implemented")
    
    def refine(self, existing_spec: dict, evaluation_feedback: dict) -> dict:
        """S3: 精化场景（预留）"""
        raise NotImplementedError("Refine scenario not yet implemented")
    
    def pivot(self, existing_spec: dict, new_direction: str) -> dict:
        """S4: 转向场景（预留）"""
        raise NotImplementedError("Pivot scenario not yet implemented")
```

### 4.3 对话状态机

```
                    ┌──────────┐
                    │  START   │
                    └────┬─────┘
                         ↓
                    ┌──────────┐
                    │  PARSE   │ 解析初始输入 + 推断
                    └────┬─────┘
                         ↓
               ┌──────────────────┐
               │    COLLECTING    │◄──┐
               └────────┬─────────┘   │
                        │             │
                  质量达标？          │
                  ┌─────┴─────┐      │
                  │No         │Yes   │
                  ↓            ↓      │
           ┌────────────┐ ┌────────┐ │
           │ ASK_USER   │ │CONFIRM │ │
           │ (2-3问题)  │ └───┬────┘ │
           └─────┬──────┘     │      │
                 │            │用户修正
                 └────────────┘      │
                 (用户回答)           │
                                     │
                              确认？  │
                         ┌────┴────┐  │
                         │Yes  No──┘──┘
                         ↓
                    ┌──────────┐
                    │  SAVE    │ 写入 Blackboard
                    └────┬─────┘
                         ↓
                    ┌──────────┐
                    │  DONE    │ 输出 Living Spec
                    └──────────┘
```

---

## 5. 与 Solution Pro 的集成方式

### 5.1 Solution Pro 消费 Living Spec

```python
# 现有调用方式（topic-only，向后兼容）
orch = SolutionOrchestratorV21(
    topic="设计AI算力调度平台",
    constraints=["500万预算", "6个月"]
)

# 新调用方式（有 Living Spec）
orch = SolutionOrchestratorV21(
    topic="设计AI算力调度平台",
    living_spec=living_spec  # ← 新增参数，Spec Pro 的产出
)
```

### 5.2 Living Spec 如何提升 Solution Pro 各阶段

| Solution Pro 阶段 | 无 Living Spec（现状） | 有 Living Spec（改进） |
|:---|:---|:---|
| **Data Collection** | 基于 topic 泛搜 | 基于 confirmed 需求精准搜索 |
| **Planning** | 猜用户意图，自己假设 | 基于完整需求做规划，不需要猜 |
| **Reviewers** | 评审自己猜的需求 | 评审用户确认的需求 |
| **Researchers** | 泛泛研究 | 聚焦 focus_areas，遵守 guardrails |
| **Consolidator** | 整合泛泛研究 | 整合聚焦研究 |
| **Auditors** | 审计泛泛方案 | 基于 confirmed 需求审计覆盖度 |
| **Harness Final** | 评估空泛的"完整性" | 基于 confirmed 需求评估真实覆盖度 |
| **Summarizer** | 生成泛泛报告 | 生成针对性报告，标注需求覆盖 |

---

## 6. 实施路线

### Phase 1: Spec Pro Genesis（当前目标）

```
目标: 完整实现 Genesis 场景
范围:
  ├── SpecProEngine 核心类
  ├── SpecManager (Living Spec 管理)
  ├── QualityAssessor (7维度评分)
  ├── InferenceEngine (推断-验证)
  ├── DialogManager (对话状态机)
  ├── RouteRecommender (路由建议)
  ├── Prompt 设计 (parse/guide/infer/structure/assess)
  └── Solution Pro 集成 (living_spec 参数)

交付:
  ├── 用户可以通过对话完成需求收集
  ├── 输出高质量 Living Spec
  ├── Solution Pro 可消费 Living Spec
  └── 验证: Spec 质量 ≥ A级 + Solution Pro 输出质量提升

预留:
  ├── supplement() / refine() / pivot() 接口签名
  ├── scenario 参数
  └── existing_spec / loop_context 参数
```

### Phase 2: Loop 设计（Spec Pro 完成后）

```
目标: 实现 Spec Pro + Solution Pro + 评估 的闭环
范围:
  ├── 评估引擎 (方案评估 + 问题溯源)
  ├── Loop Controller (决策 + 收敛检测)
  ├── Spec Pro Refine 场景实现
  └── 增量执行 (只重做受影响的阶段)
```

### Phase 3: 补充场景 + 智能化

```
目标: 实现 S2(Supplement) + S4(Pivot) + 行业模板
范围:
  ├── Spec Pro Supplement 场景
  ├── Spec Pro Pivot 场景
  ├── 行业需求模板库
  └── 历史 Spec 复用
```

---

## 7. 验收标准（Genesis）

### 功能验收

- [ ] 用户输入一句话 → Spec Pro 引导 3-5 轮对话 → 输出 Living Spec
- [ ] 推断-验证机制正常工作（推断项标注置信度）
- [ ] 质量评分准确（人工校验偏差 < 10 分）
- [ ] Living Spec 写入 Blackboard，Solution Pro 可读取
- [ ] Solution Pro 有 living_spec 参数时输出质量明显优于无参数
- [ ] 路由建议正常生成（建议 + 理由 + 置信度）

### 质量验收

- [ ] 同一需求，有 Spec Pro vs 无 Spec Pro，Solution Pro 输出质量对比提升明显
- [ ] Living Spec 的 confirmed 层信息准确（用户确认过的）
- [ ] inferred 层标注合理（置信度高的确实合理）
- [ ] guardrails 三层（Always/Ask/Never）对 Solution Pro 有实际约束效果

### 架构验收

- [ ] 接口预留 supplement/refine/pivot 扩展点
- [ ] scenario 参数可切换（虽然只实现 genesis）
- [ ] Living Spec 数据结构支持版本控制
- [ ] 与 Solution Pro 向后兼容（无 living_spec 时行为不变）

---

*概念设计 v2 完成。忠礼确认后进入技术架构详细设计。*
