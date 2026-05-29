# 需求收集模块架构设计

> **版本**: v1.0
> **日期**: 2026-05-23
> **作者**: 小满 🦞
> **状态**: 架构设计（待忠礼确认）

---

## 1. 大愿景：完整闭环 + Loop

### 1.1 终极形态

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     DeepFlow 完整闭环系统                                │
│                                                                         │
│   ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐   │
│   │  需求收集     │ ──→ │  Solution Pro    │ ──→ │  方案评估        │   │
│   │  (Stage 0)   │     │  (Stage 1-10)    │     │  (Stage 11)      │   │
│   └──────┬───────┘     └──────────────────┘     └────────┬─────────┘   │
│          ↑                                               │             │
│          │              Loop (迭代优化)                   │             │
│          └───────────────────────────────────────────────┘             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**完整流程**:
1. **需求收集** → 结构化需求文档 (requirement_spec.json)
2. **Solution Pro** → 设计方案 (final_solution.md)
3. **方案评估** → 评估报告 (evaluation.json)
4. **Loop 决策** → 是否需要迭代？
   - 需要 → 回到需求收集（补充/修正需求）或回到 Solution Pro（调整方案）
   - 不需要 → 输出最终交付物

### 1.2 Loop 的三种模式

| Loop 类型 | 触发条件 | 回到哪里 | 典型场景 |
|:---|:---|:---|:---|
| **需求 Loop** | 方案评估发现需求不完整/不合理 | Stage 0（需求收集） | "评估发现缺少安全合规需求，需要补充" |
| **方案 Loop** | 需求完整，但方案设计不够好 | Stage 4（Research）或 Stage 7（Fix） | "架构审计发现性能瓶颈，需要重新设计" |
| **全局 Loop** | 用户对最终方案不满意 | Stage 0（从头开始，但保留历史） | "方向不对，我们重新梳理需求" |

### 1.3 Loop 的价值

- **第一次**: 80% 正确的需求 → 70% 正确的方案
- **第二次**: 90% 正确的需求 → 85% 正确的方案
- **第三次**: 95% 正确的需求 → 95% 正确的方案（收敛）

**关键洞察**: Loop 不是重来，而是**增量优化**。每次 Loop 都基于上一次的积累。

---

## 2. 需求收集模块架构

### 2.1 模块在 DeepFlow 中的位置

```
.deepflow/
├── core/                              # 核心框架
│   ├── requirement_collector.py       # ← 新增：需求收集器
│   ├── requirement_spec.py            # ← 新增：需求规格数据结构
│   ├── requirement_quality.py         # ← 新增：需求质量评估器
│   ├── loop_controller.py             # ← 新增：Loop 控制器
│   ├── pipeline_orchestrator.py       # 现有：管线调度器
│   └── entry_harness.py               # 现有：入口验证
├── domains/
│   └── solution/
│       ├── orchestrator_agent.py      # 修改：接收 requirement_spec
│       ├── task_builder.py            # 修改：基于 requirement_spec 构建 task
│       └── stage_evaluator.py         # ← 新增：方案评估器 (Stage 11)
└── prompts/
    └── requirement/                   # ← 新增：需求收集相关 Prompt
        ├── collector_system.md        # 需求收集器系统 Prompt
        ├── question_generator.md      # 问题生成 Prompt
        ├── spec_builder.md            # 结构化文档生成 Prompt
        └── quality_evaluator.md       # 质量评估 Prompt
```

### 2.2 核心组件

```
┌─────────────────────────────────────────────────────────────────┐
│                    RequirementCollector                         │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │  对话管理器      │  │  问题生成器      │  │  结构化引擎   │  │
│  │  (DialogMgr)    │  │  (QuestionGen)  │  │  (SpecBuilder)│  │
│  └────────┬────────┘  └────────┬────────┘  └───────┬───────┘  │
│           │                    │                    │           │
│  ┌────────▼────────────────────▼────────────────────▼───────┐  │
│  │              需求知识库 (Requirement Knowledge Base)       │  │
│  │  - 7维度需求框架                                          │  │
│  │  - 行业需求模板                                           │  │
│  │  - 历史需求基线                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │  质量评估器      │  │  上下文管理器    │  │  历史管理器   │  │
│  │  (QualityEval)  │  │  (ContextMgr)   │  │  (HistoryMgr) │  │
│  └─────────────────┘  └─────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 组件职责

| 组件 | 职责 | 输入 | 输出 |
|:---|:---|:---|:---|
| **DialogMgr** | 管理多轮对话状态，决定何时结束 | 用户消息 | 对话状态 |
| **QuestionGen** | 基于当前需求画像生成下一轮问题 | 当前 spec + 缺失维度 | 2-3 个问题 |
| **SpecBuilder** | 将对话内容结构化为 requirement_spec | 对话历史 | requirement_spec.json |
| **QualityEval** | 评估需求质量，决定是否继续收集 | requirement_spec | 质量评分 + 缺失项 |
| **ContextMgr** | 维护对话上下文，避免重复询问 | 对话历史 | 上下文摘要 |
| **HistoryMgr** | 管理 Loop 历史，实现增量优化 | 历史 spec 列表 | 增量变更 |

---

## 3. 数据流设计

### 3.1 完整数据流

```
用户输入
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 0: RequirementCollector                                   │
│                                                                 │
│  Round 1:                                                       │
│  ├─ 解析初始输入                                                │
│  ├─ 识别已有信息 → 初始 spec (部分填充)                         │
│  ├─ 质量评估 → 40/100 (Insufficient)                           │
│  ├─ 生成问题 → "请问目标用户是谁？预算范围？"                    │
│  └─ 等待用户回答                                                │
│                                                                 │
│  Round 2:                                                       │
│  ├─ 解析用户回答                                                │
│  ├─ 更新 spec → 更多维度填充                                    │
│  ├─ 质量评估 → 65/100 (Acceptable)                             │
│  ├─ 生成问题 → "有哪些已有系统需要对接？"                        │
│  └─ 等待用户回答                                                │
│                                                                 │
│  Round 3:                                                       │
│  ├─ 解析用户回答                                                │
│  ├─ 更新 spec → 接近完整                                        │
│  ├─ 质量评估 → 82/100 (Good) → 触发确认                         │
│  ├─ 展示摘要给用户确认                                          │
│  └─ 用户确认/修正                                               │
│                                                                 │
│  Final:                                                         │
│  ├─ 生成最终 requirement_spec.json                              │
│  ├─ 写入 Blackboard: blackboard/{session_id}/data/              │
│  └─ 输出: requirement_spec.json + quality_report.json           │
└─────────────────────────────────────┬───────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ Solution Pro (Stage 1-10)                                       │
│                                                                 │
│  变化:                                                          │
│  - Data Collection 基于 requirement_spec 搜索（更精准）          │
│  - Planning 基于 requirement_spec 规划（不再猜）                │
│  - Researchers 基于 requirement_spec 约束（聚焦重点）            │
│  - Harness Final 基于 requirement_spec 评估（有意义的评分）      │
│                                                                 │
│  输出: final_solution.md + harness_final.json                   │
└─────────────────────────────────────┬───────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 11: SolutionEvaluator (方案评估器) ← 新增                  │
│                                                                 │
│  输入:                                                          │
│  - requirement_spec.json (需求)                                 │
│  - final_solution.md (方案)                                     │
│  - harness_final.json (质量评分)                                 │
│                                                                 │
│  评估维度:                                                      │
│  - 需求覆盖度: 方案是否覆盖了 requirement_spec 的所有需求？      │
│  - 需求合理性: 需求本身是否有矛盾或不合理？（方案可能暴露）      │
│  - 方案可行性: 方案是否可落地？                                  │
│  - 方案完整性: 方案是否有明显遗漏？                              │
│                                                                 │
│  输出: evaluation.json                                          │
│  {                                                              │
│    "requirement_coverage": 0.85,                                │
│    "requirement_issues": ["安全需求过于笼统，无法设计具体方案"],  │
│    "solution_feasibility": 0.75,                                 │
│    "solution_gaps": ["缺少数据迁移方案"],                        │
│    "loop_recommendation": {                                     │
│      "should_loop": true,                                       │
│      "loop_type": "requirement",                                │
│      "focus": "细化安全需求 + 补充数据迁移约束"                  │
│    }                                                            │
│  }                                                              │
└─────────────────────────────────────┬───────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ LoopController (Loop 控制器)                                    │
│                                                                 │
│  决策树:                                                        │
│  ├─ should_loop = false → 输出最终交付物，结束                   │
│  ├─ should_loop = true + loop_type = "requirement"              │
│  │   → 回到 Stage 0，带上 evaluation 中的 focus                  │
│  │   → RequirementCollector 进入"增量模式"                       │
│  ├─ should_loop = true + loop_type = "solution"                 │
│  │   → 回到 Solution Pro 的特定阶段                              │
│  │   → 保留已有 spec，只重新执行问题阶段                          │
│  └─ should_loop = true + loop_type = "global"                   │
│      → 回到 Stage 0，重置但保留历史                              │
│      → 用户可以说"换个方向"                                     │
│                                                                 │
│  收敛检测:                                                      │
│  - 连续 2 轮 Loop 质量提升 < 5% → 建议停止（边际效益递减）       │
│  - Loop 次数 > 3 → 建议停止（避免无限循环）                      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Blackboard 数据结构（含 Loop 历史）

```
blackboard/{session_id}/
├── data/
│   ├── requirement_spec.json          # 当前需求规格（最新）
│   ├── requirement_spec_v1.json       # 第1轮需求规格（Loop 历史）
│   ├── requirement_spec_v2.json       # 第2轮需求规格（如果有 Loop）
│   ├── quality_report.json            # 需求质量评估报告
│   └── collection.json                # Data Collection 输出（现有）
├── stages/
│   ├── planning.json                  # Planning 输出（现有）
│   ├── ...                            # 其他 stage（现有）
│   ├── harness_final.json             # Harness Final（现有）
│   └── evaluation.json                # ← 新增：方案评估 (Stage 11)
├── loop/
│   ├── loop_history.json              # Loop 历史记录
│   ├── delta_v1_v2.json               # 需求变更增量
│   └── convergence_report.json        # 收敛分析报告
├── final_solution.md                  # 最终方案（现有）
└── execution_log.json                 # 执行日志（现有）
```

---

## 4. 需求收集对话流程（详细）

### 4.1 状态机

```
                    ┌─────────────┐
                    │   INIT      │  用户输入 topic
                    └──────┬──────┘
                           ↓
                    ┌─────────────┐
         ┌─────────│  COLLECTING │◄──────── Loop: 增量收集
         │         └──────┬──────┘
         │                │
         │    每轮: 生成问题 → 用户回答 → 更新 spec → 质量评估
         │                │
         │         质量 ≥ 阈值？
         │         ┌─────┴─────┐
         │         │ No        │ Yes
         │         ↓           ↓
         │  ┌────────────┐ ┌─────────────┐
         │  │ 继续提问    │ │  CONFIRMING │
         │  └────────────┘ └──────┬──────┘
         │                        │
         │              用户确认？
         │              ┌─────┴─────┐
         │              │ No        │ Yes
         │              ↓           ↓
         │       ┌────────────┐ ┌─────────────┐
         └───────│  REVISING  │ │  COMPLETED  │
                 └────────────┘ └──────┬──────┘
                                       ↓
                                requirement_spec.json
                                → Solution Pro
```

### 4.2 对话策略

#### 4.2.1 问题生成策略

```python
class QuestionGenerator:
    """
    基于当前需求画像，生成下一轮问题。
    
    策略:
    1. 优先问高权重缺失维度（业务上下文 > 功能需求 > 非功能需求）
    2. 每轮最多 3 个问题（避免信息过载）
    3. 问题自适应（基于已回答内容动态调整）
    4. 问题类型：开放式 → 选择式 → 确认式（渐进收敛）
    """
    
    # 维度优先级权重
    DIMENSION_PRIORITY = {
        "business_context": 1.0,      # 最高：决定方向
        "users_and_scenarios": 0.9,   # 高：决定设计
        "constraints": 0.85,           # 高：决定取舍
        "functional_requirements": 0.8,
        "non_functional_requirements": 0.7,
        "integration": 0.6,
        "risks_and_assumptions": 0.5   # 最低：可以后续补充
    }
    
    def generate_questions(self, current_spec: dict, max_questions: int = 3) -> list:
        """
        生成下一轮问题
        
        返回:
        [
            {
                "dimension": "business_context",
                "question": "这个系统要解决什么核心问题？现在是怎么做的？",
                "question_type": "open",  # open / choice / confirm
                "importance": "high",
                "expected_detail": "medium"  # low / medium / high
            }
        ]
        """
        # 1. 评估各维度完整度
        scores = self._evaluate_dimensions(current_spec)
        
        # 2. 按优先级排序缺失维度
        missing = [(dim, score) for dim, score in scores.items() if score < 0.7]
        missing.sort(key=lambda x: self.DIMENSION_PRIORITY[x[0]] * (1 - x[1]), reverse=True)
        
        # 3. 取 top N 生成问题
        questions = []
        for dim, score in missing[:max_questions]:
            q = self._generate_question_for_dimension(dim, current_spec, score)
            questions.append(q)
        
        return questions
```

#### 4.2.2 自适应深度控制

```python
class DepthController:
    """
    控制对话深度：什么时候该停？
    
    停止条件:
    1. 质量评分 ≥ 阈值（Quick:60, Standard:75, Deep:85）
    2. 用户表示"够了"
    3. 连续 2 轮质量提升 < 3%（边际效益递减）
    4. 对话轮数达到上限（Quick:3, Standard:6, Deep:10）
    """
    
    THRESHOLDS = {
        "quick": {"quality": 60, "max_rounds": 3, "min_rounds": 1},
        "standard": {"quality": 75, "max_rounds": 6, "min_rounds": 3},
        "deep": {"quality": 85, "max_rounds": 10, "min_rounds": 5}
    }
    
    def should_stop(self, current_round: int, quality_score: float,
                    prev_score: float, mode: str) -> tuple:
        """
        返回:
        (should_stop: bool, reason: str)
        """
        config = self.THRESHOLDS[mode]
        
        if current_round < config["min_rounds"]:
            return False, "最少对话轮数未达到"
        
        if quality_score >= config["quality"]:
            return True, f"质量评分 {quality_score} 达到阈值 {config['quality']}"
        
        if current_round >= config["max_rounds"]:
            return True, f"达到最大对话轮数 {config['max_rounds']}"
        
        if current_round > 1 and (quality_score - prev_score) < 0.03:
            return True, "边际效益递减（连续提升 < 3%）"
        
        return False, "继续收集"
```

### 4.3 对话示例（Standard 模式）

```
用户: Solution Pro：设计一个AI算力调度平台

小满: [解析] 识别到:
  ✅ topic: AI算力调度平台
  ❌ 业务上下文: 缺失
  ❌ 用户与场景: 缺失
  ❌ 约束条件: 缺失
  质量评分: 15/100 → 需要收集

小满: [Round 1 问题]
  1. 这个平台要解决什么问题？现在团队是怎么管理 GPU 资源的？
  2. 大概有多少人会使用？主要是什么角色（研究员/工程师/...）？
  3. 有预算和时间要求吗？

用户: 
  1. 现在GPU利用率只有30%，各团队自己抢资源，经常排队4小时以上
  2. 大约50个AI研究员 + 10个运维 + 5个部门主管看报表
  3. 预算500万，希望6个月上线第一版

小满: [更新 spec] 
  ✅ 业务上下文: 70% (痛点清晰，缺 KPI)
  ✅ 用户与场景: 60% (角色清晰，缺具体场景)
  ✅ 约束条件: 65% (预算时间清晰，缺技术约束)
  质量评分: 55/100 → 继续

小满: [Round 2 问题]
  1. 有没有已经建好的基础设施？（比如 K8s 集群、云服务商）
  2. 最核心的 2-3 个功能是什么？
  3. 对性能和可用性有什么具体要求吗？（比如并发量、可用率）

用户:
  1. 有阿里云 ACK 集群，用的 K8s，监控是 Prometheus + Grafana
  2. 核心功能：任务调度、资源监控大盘、成本分析
  3. 要支持至少1000个并发任务，99.9%可用

小满: [更新 spec]
  ✅ 集成与环境: 80%
  ✅ 功能需求: 75%
  ✅ 非功能需求: 65%
  质量评分: 78/100 → 达到阈值，进入确认

小满: [确认摘要]
  需求收集摘要:
  ━━━━━━━━━━━━━━━━━━━━━━━━
  🎯 目标: AI算力调度平台，GPU利用率从30%→70%
  👥 用户: 50研究员 + 10运维 + 5主管
  💰 约束: 500万预算，6个月
  🔧 基础: 阿里云ACK + K8s + Prometheus
  📦 核心功能: 任务调度 / 资源监控 / 成本分析
  ⚡ 性能: 1000并发，99.9%可用
  
  以上理解对吗？有需要补充或修改的吗？确认后我将启动方案设计。

用户: 基本对的，补充一下：需要支持多租户隔离，不同部门数据不能互通

小满: [更新] 已补充安全需求：多租户数据隔离
  质量评分: 82/100 → 进入 Solution Pro
  
  ✅ 需求收集完成，已写入 requirement_spec.json
  🚀 启动 Solution Pro 10阶段管线...
```

---

## 5. Loop 机制详细设计

### 5.1 LoopController

```python
class LoopController:
    """
    Loop 控制器
    
    职责:
    1. 基于方案评估结果决定是否 Loop
    2. 决定 Loop 类型（需求/方案/全局）
    3. 管理 Loop 历史（增量变更追踪）
    4. 收敛检测（避免无限循环）
    """
    
    MAX_LOOPS = 3
    CONVERGENCE_THRESHOLD = 0.05  # 连续2轮提升 < 5% 视为收敛
    
    def evaluate_loop(self, requirement_spec: dict, solution: dict,
                      evaluation: dict, loop_history: list) -> dict:
        """
        评估是否需要 Loop
        
        返回:
        {
            "should_loop": bool,
            "loop_type": "requirement" | "solution" | "global" | None,
            "focus": "需要改进的方向",
            "reason": "为什么需要 Loop",
            "expected_improvement": "预期改进"
        }
        """
        # 1. 收敛检测
        if len(loop_history) >= self.MAX_LOOPS:
            return {"should_loop": False, "reason": "达到最大 Loop 次数"}
        
        if self._is_converged(loop_history):
            return {"should_loop": False, "reason": "已收敛（边际效益递减）"}
        
        # 2. 判断 Loop 类型
        if evaluation.get("requirement_issues"):
            return {
                "should_loop": True,
                "loop_type": "requirement",
                "focus": evaluation["requirement_issues"],
                "reason": "需求不完整/不合理，导致方案无法深入"
            }
        
        if evaluation.get("solution_gaps"):
            return {
                "should_loop": True,
                "loop_type": "solution",
                "focus": evaluation["solution_gaps"],
                "reason": "需求完整，但方案设计有遗漏"
            }
        
        if evaluation.get("requirement_coverage", 0) < 0.7:
            return {
                "should_loop": True,
                "loop_type": "global",
                "focus": "需求-方案匹配度太低",
                "reason": "方案与需求脱节，可能需要重新梳理"
            }
        
        return {"should_loop": False, "reason": "质量达标"}
```

### 5.2 增量 Loop 模式

```
Loop 1 (初始):
  requirement_spec_v1.json → Solution Pro → final_solution_v1.md → evaluation_v1.json
  ↓ Loop 发现: 安全需求太笼统

Loop 2 (增量):
  RequirementCollector 进入"增量模式":
  - 只针对"安全需求"维度深入提问
  - 不重新问已经清晰的维度
  - 输出: requirement_spec_v2.json (v1 + 安全需求细化)
  - delta_v1_v2.json: {"changed": ["non_functional_requirements.security"], "added": [...]}
  
  Solution Pro 进入"增量模式":
  - 不需要重新 Research 已经 OK 的部分
  - 只针对变更的需求重新设计
  - 输出: final_solution_v2.md (增量更新)

Loop 3 (如果需要):
  继续增量...
```

### 5.3 Loop 历史追踪

```json
// loop/loop_history.json
{
  "session_id": "ai-compute-platform_architecture_a1b2c3d4",
  "loops": [
    {
      "round": 1,
      "timestamp": "2026-05-23T16:00:00+08:00",
      "type": "initial",
      "requirement_quality": 82,
      "solution_coverage": 0.72,
      "evaluation": {
        "requirement_issues": ["安全需求太笼统"],
        "solution_gaps": ["缺少数据迁移方案"]
      },
      "loop_decision": {
        "should_loop": true,
        "type": "requirement",
        "focus": "细化安全需求"
      }
    },
    {
      "round": 2,
      "timestamp": "2026-05-23T16:45:00+08:00",
      "type": "requirement",
      "requirement_quality": 91,
      "solution_coverage": 0.88,
      "delta": {
        "changed_dimensions": ["non_functional_requirements"],
        "added_requirements": ["NFR-004: 多租户数据隔离方案", "NFR-005: 审计日志"],
        "removed_requirements": []
      },
      "evaluation": {
        "requirement_issues": [],
        "solution_gaps": []
      },
      "loop_decision": {
        "should_loop": false,
        "reason": "质量达标"
      }
    }
  ],
  "convergence": {
    "quality_trajectory": [82, 91],
    "coverage_trajectory": [0.72, 0.88],
    "improvement_rate": [null, 0.16],
    "converged": true
  }
}
```

---

## 6. Solution Pro 集成改造

### 6.1 SolutionOrchestratorV21 改造

```python
class SolutionOrchestratorV21:
    def __init__(self, topic: str, ...,
                 requirement_spec: Optional[dict] = None):  # ← 新增参数
        """
        Args:
            requirement_spec: 来自 RequirementCollector 的结构化需求
                             如果为 None，走现有的 topic-only 模式（向后兼容）
        """
        self.requirement_spec = requirement_spec
        # ... 现有逻辑不变
    
    def get_all_tasks(self) -> dict:
        """构建 Worker Tasks"""
        for stage in pipeline:
            if stage == "data_collection":
                # 改造：基于 requirement_spec 生成更精准的搜索策略
                tasks[stage] = build_data_collection_task(
                    self.session_id, self.topic, self.constraints,
                    requirement_spec=self.requirement_spec  # ← 新增
                )
            elif stage == "planning":
                # 改造：基于 requirement_spec 做更精准的规划
                tasks[stage] = build_planner_task(
                    self.session_id, self.topic, self.solution_type,
                    self.constraints, self.stakeholders,
                    requirement_spec=self.requirement_spec  # ← 新增
                )
            # ... 其他 stage 类似改造
```

### 6.2 Task Builder 改造示例

```python
def build_planner_task(session_id, topic, solution_type, constraints,
                       stakeholders, requirement_spec=None):
    """构建 Planner Worker Task"""
    
    base_prompt = read_prompt("solution/planner")
    
    if requirement_spec:
        # 有 requirement_spec：注入完整需求上下文
        spec_summary = _build_spec_summary(requirement_spec)
        prompt = base_prompt + f"""

## 结构化需求（来自需求收集模块）

{spec_summary}

### 使用指南
- 以上需求已经过用户确认，是权威来源
- 你的任务是制定**研究计划**，不是重新收集需求
- 基于以上需求，规划需要深入研究的方向和重点
- 需求中的 functional_requirements 和 non_functional_requirements 是你的规划核心输入
"""
    else:
        # 向后兼容：topic-only 模式
        prompt = base_prompt + f"\n主题: {topic}"
    
    return prompt
```

### 6.3 Stage 11: SolutionEvaluator

```python
class SolutionEvaluator:
    """
    方案评估器 (Stage 11)
    
    职责:
    1. 评估方案对需求的覆盖度
    2. 发现需求中的隐藏问题（方案暴露出来的）
    3. 评估方案可行性
    4. 生成 Loop 建议
    """
    
    def evaluate(self, requirement_spec: dict, solution_path: str,
                 harness_final: dict) -> dict:
        """
        评估方案
        
        Returns:
        {
            "requirement_coverage": 0.85,
            "requirement_issues": [...],
            "solution_feasibility": 0.75,
            "solution_gaps": [...],
            "loop_recommendation": {...}
        }
        """
        pass
```

---

## 7. 实现路线图

### Phase 1: 需求收集核心 (当前)

```
目标: 验证需求收集 → Solution Pro 的价值链路
范围:
  - RequirementCollector 核心类（对话管理 + 问题生成 + 结构化）
  - requirement_spec.json 数据结构
  - 质量评估器（7维度评分）
  - SolutionOrchestratorV21 集成（接收 requirement_spec）
  - Planning Task Builder 改造

交付:
  - 可以通过对话收集需求 → 生成 spec → 喂给 Solution Pro
  - 验证: spec 质量 ≥ 75 + Solution Pro 输出质量提升

预计: 2-3 周
```

### Phase 2: Loop 机制

```
目标: 实现需求-方案-评估闭环
范围:
  - SolutionEvaluator (Stage 11)
  - LoopController
  - 增量 Loop 模式
  - Loop 历史追踪
  
交付:
  - 方案评估 → Loop 建议 → 增量优化
  - 验证: 2轮 Loop 后覆盖率提升 ≥ 15%

预计: 1-2 周
```

### Phase 3: 智能化 + 模板化

```
目标: 提升效率，降低门槛
范围:
  - 行业需求模板（AI平台/电商/金融/...）
  - 历史需求基线复用
  - 智能问题推荐（基于行业/场景）
  - DeepFlow 前端集成
  
交付:
  - 行业模板库
  - 前端需求收集向导
  - 验证: 收集时间减少 50%

预计: 2-3 周
```

---

## 8. 关键设计决策（待忠礼确认）

| # | 决策 | 选项 | 我的建议 |
|:---|:---|:---|:---|
| D1 | RequirementCollector 实现形态 | A. 主Agent引导(我直接对话) B. 子Agent自动化 C. Python类+主Agent混合 | **C**: Python类封装逻辑，主Agent负责对话交互 |
| D2 | 需求收集深度控制 | A. 固定轮数 B. 质量阈值驱动 C. 用户手动控制 | **B**: 质量阈值 + 用户可覆盖 |
| D3 | Loop 是否自动触发 | A. 全自动 B. 推荐+用户确认 C. 用户手动触发 | **B**: 系统推荐 + 用户确认 |
| D4 | requirement_spec 版本管理 | A. 覆盖式 B. 追加式（保留历史） | **B**: 追加式，便于追踪变更 |
| D5 | Solution Pro 向后兼容 | A. 强制 requirement_spec B. 可选（topic-only 仍可用） | **B**: 可选，向后兼容 |

---

*架构设计 v1.0 完成，等待忠礼确认后进入具体实现。*
