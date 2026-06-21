# Spec Pro Harness 设计

> **版本**: v1.0
> **日期**: 2026-05-23
> **作者**: 小满 🦞
> **状态**: ✅ 设计完成

---

## 1. 为什么 Spec Pro 需要自己的 Harness

### 1.1 Solution Pro Harness 评什么

| 维度 | 评的是 | 本质 |
|:---|:---|:---|
| 完整性 | 方案是否覆盖所有方面 | "该有的都有" |
| 必要性 | 方案是否过度设计 | "不要多余的" |
| 目标一致性 | 方案是否服务原始目标 | "不跑偏" |

**评价对象**: 方案（Solution）—— 一个"答案"

### 1.2 Spec Pro Harness 评什么

Spec Pro 产出的不是"答案"，而是"问题的精确定义"。这是根本不同。

| 维度 | 评的是 | 本质 |
|:---|:---|:---|
| **清晰度** | 需求表述是否无歧义 | "读得懂" |
| **完整度** | 关键维度是否覆盖 | "问全了" |
| **可执行度** | 下游引擎能否消费 | "用得上" |
| **一致度** | 需求之间是否矛盾 | "不打架" |
| **对话健康度** | 对话是否在有效推进 | "没绕圈" |

**评价对象**: 需求规格（Spec）—— 一个"问题定义"

### 1.3 核心差异总结

```
Solution Pro Harness:  "这个答案好不好？"
Spec Pro Harness:      "这个问题问清楚了吗？"

Solution Pro: 评估 → 方案 → 是否完整/必要/对齐目标
Spec Pro:     评估 → 规格 → 是否清晰/完整/可执行/一致
              评估 → 对话 → 是否在推进/有没有绕圈
              评估 → 推断 → 推断是否合理/有没有越界
```

---

## 2. 业界参考

### 2.1 INCOSE 需求质量标准

INCOSE（国际系统工程委员会）定义了高质量需求的标准：

| 标准 | 含义 | Spec Pro 映射 |
|:---|:---|:---|
| **Clear（清晰）** | 只有一个解读方式 | → 清晰度检查 |
| **Unambiguous（无歧义）** | 不含模糊词 | → 歧义检测 |
| **Testable（可验证）** | 能写出验证方法 | → 可执行度检查 |
| **Necessary（必要）** | 不可删除 | → 必要性检查 |
| **Complete（完整）** | 无遗漏 | → 完整度检查 |
| **Consistent（一致）** | 互相不矛盾 | → 一致度检查 |
| **Traceable（可追溯）** | 能追溯到源头 | → 溯源标记 |

### 2.2 EARS 需求语法

EARS（Easy Approach to Requirements Syntax）用结构化模板表达需求：

```
泛在型:   "系统应 [能力]"
事件驱动: "当 [事件] 发生时，系统应 [响应]"
状态驱动: "当系统处于 [状态] 时，系统应 [能力]"
可选型:   "如果 [条件]，系统应 [能力]"
异常型:   "如果 [异常]，系统应 [响应] 并 [报告]"
```

**对我们的启发**: Living Spec 中的 capabilities 可以用类似结构化表达，提升可执行度。

### 2.3 Agentic AI 终止条件（业界共识）

| 终止机制 | 描述 | Spec Pro 映射 |
|:---|:---|:---|
| **Quality Threshold** | 质量达标就停 | → 需求质量分 ≥ 阈值 |
| **Step Limit** | 最大步数硬上限 | → 最大轮数 |
| **Convergence** | 边际收益递减 | → 连续2轮提升 < 3% |
| **Kill Criteria** | 异常终止条件 | → 对话质量崩溃检测 |
| **HITL Override** | 人类说停就停 | → 用户说"够了" |

### 2.4 多层 Guardrails（2025-2026 最佳实践）

```
Layer 1: Input Guard    → 输入验证（拦截无意义输入）
Layer 2: Process Guard  → 过程监控（对话健康度、推断越界）
Layer 3: Output Guard   → 输出检查（需求质量、下游适配性）
Layer 4: Safety Valve   → 安全阀（最大轮数、Kill Criteria）
```

---

## 3. Spec Pro Harness 总体设计

### 3.1 四层 Harness 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Spec Pro Harness（四层质量保障）                  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Layer 1: Input Guard（输入守门）                             │  │
│  │  时机: 每轮对话开始时                                         │  │
│  │  职责: 验证用户输入有效性，防止垃圾输入污染 Spec               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Layer 2: Process Guard（过程监控）                           │  │
│  │  时机: 每轮对话结束时                                         │  │
│  │  职责: 监控对话健康度、推断可信度、收敛趋势                    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Layer 3: Output Guard（输出门禁）                            │  │
│  │  时机: 达到停止条件时                                         │  │
│  │  职责: 评估 Living Spec 最终质量，决定 PASS/WARN/BLOCK         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Layer 4: Safety Valve（安全阀）                              │  │
│  │  时机: 全程监控                                               │  │
│  │  职责: 硬上限 + Kill Criteria + 异常检测                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Harness 执行位置

```
Round N 执行流:

  主Agent 收到用户回答
      ↓
  ┌── Input Guard ──┐   ← Layer 1: 验证输入
  │  输入有效？      │
  │  Yes → 继续     │
  │  No → 请用户重新 │
  └─────────────────┘
      ↓
  spawn Orchestrator Worker
      ├── spawn ResponseWorker → 解析回答，更新 Spec
      ├── spawn AssessWorker → 质量评估
      └── spawn QuestionWorker → 生成下轮问题
      ↓
  ┌── Process Guard ─┐  ← Layer 2: 监控过程
  │  对话在推进吗？   │
  │  推断合理吗？     │
  │  收敛趋势正常？   │
  └──────────────────┘
      ↓
  ┌── 停止判断 ──────┐
  │  质量达标？→ Yes → 进入 Output Guard
  │  轮数上限？→ Yes → 进入 Output Guard
  │  边际递减？→ Yes → 进入 Output Guard
  │  用户说够？→ Yes → 进入 Output Guard
  │  以上都No → 继续下一轮
  └──────────────────┘
      ↓
  ┌── Output Guard ──┐  ← Layer 3: 最终门禁
  │  需求质量评估     │
  │  一致度检查       │
  │  下游适配检查     │
  │  → PASS / WARN / BLOCK
  └──────────────────┘

  全程: Safety Valve 监控异常
```

---

## 4. 四层详细设计

### 4.1 Layer 1: Input Guard（输入守门）

**时机**: 每轮收到用户回答时

**检查项**:

| 检查 | 方法 | 处理 |
|:---|:---|:---|
| **非空检查** | 回答是否为空或纯空白 | 提示用户重新输入 |
| **意义检查** | 是否有实质内容（不是纯"嗯""哦"） | 追问"能否展开说说？" |
| **矛盾检测** | 新信息是否与已确认 Spec 矛盾 | 标注矛盾点，请用户澄清 |
| **范围检查** | 回答是否跟当前问题相关 | 如果跑题，温和引导回来 |

**实现方式**: ResponseWorker 在解析回答时顺带执行，不需要单独 Worker。

```markdown
# ResponseWorker Prompt 中的 Input Guard 指令

## Input Guard（在解析前先执行）

在解析用户回答之前，先执行以下检查:

1. **有效性**: 回答是否有实质信息？
   - 如果用户只说"嗯"/"好的"/"知道了" → 标记 needs_followup
   - 如果用户说"我不想回答这个" → 标记 skipped，跳过该维度

2. **一致性**: 新信息是否与已确认的需求矛盾？
   - 例: 之前确认"预算500万"，现在说"预算50万" → 标记 contradiction
   - 在输出中标注矛盾点，由主Agent请用户澄清

3. **相关性**: 回答是否跟提问相关？
   - 如果完全跑题 → 标记 off_topic
   - 主Agent会温和引导回来

输出:
```json
{
  "input_guard": {
    "valid": true,
    "contradictions": [],
    "off_topic": false,
    "skipped_dimensions": [],
    "needs_followup": []
  }
}
```
```

### 4.2 Layer 2: Process Guard（过程监控）

**时机**: 每轮结束后，Orchestrator Worker 内部检查

**检查维度**:

#### 4.2.1 对话推进度（Progress Rate）

```
定义: 每轮对话带来的信息增量
计算: quality_delta = quality_after - quality_before

健康标准:
- 前3轮: 每轮 +8~15 分（快速填充）
- 4-6轮: 每轮 +3~8 分（精细补充）
- 7+轮:  每轮 +1~3 分（边际递减正常）

异常检测:
- 连续2轮 delta < 2 → "边际递减" 警告
- 单轮 delta < 0 → "质量回退" 警告（用户修正可能引入矛盾）
- 连续3轮同一维度缺失 → "死循环" 警告（某个维度始终填不上）
```

#### 4.2.2 推断可信度监控（Inference Integrity）

```
检查项:
- 推断置信度是否合理（不应全部 >0.9，也不应全部 <0.4）
- 推断被拒绝率是否过高（>50% 拒绝 → 推断策略有问题）
- 推断是否越界（推断了用户明确说不需要的东西）

健康标准:
- 推断确认率: 40-80%（太高=推断太保守，太低=推断太激进）
- 平均置信度: 0.5-0.8

异常检测:
- 连续3个推断被拒绝 → "推断偏差" 警告（调整推断策略）
- 置信度 >0.9 的推断被拒绝 → "过度自信" 警告
```

#### 4.2.3 对话平衡度（Conversation Balance）

```
检查项:
- 各维度是否均衡推进（不应一个维度85分另一个0分）
- 问题类型是否多样（不应全是澄清类问题）
- 用户是否被过度追问某个维度

健康标准:
- 维度间分差: 最高-最低 ≤ 40分
- 问题类型: 至少使用过4种（6类中）
- 单维度追问: 不超过连续2轮

异常检测:
- 某维度连续3轮被追问仍然低分 → "维度卡死" 警告
- 只用了1种问题类型 → "问题单一" 警告
```

**Process Guard 输出**:

```json
{
  "process_guard": {
    "progress": {
      "round": 3,
      "quality_trajectory": [15, 38, 55, 68],
      "delta_trajectory": [null, 23, 17, 13],
      "status": "healthy",
      "warnings": []
    },
    "inference": {
      "total": 8,
      "confirmed": 5,
      "rejected": 1,
      "pending": 2,
      "confirm_rate": 0.83,
      "status": "healthy",
      "warnings": []
    },
    "balance": {
      "max_dimension_score": 85,
      "min_dimension_score": 40,
      "gap": 45,
      "question_types_used": 4,
      "status": "warning",
      "warnings": ["维度间分差45 > 40，建议关注低分维度"]
    },
    "overall_status": "healthy",
    "action": "continue"
  }
}
```

**Process Guard 触发的行为**:

| 状态 | 行为 |
|:---|:---|
| healthy | 正常继续 |
| warning | 继续，但调整策略（提示 QuestionWorker 关注弱项） |
| degraded | 降低质量阈值，建议用户尽快确认 |
| critical | 触发 Kill Criteria，建议停止 |

### 4.3 Layer 3: Output Guard（输出门禁）

**时机**: 达到停止条件时

**三个子门禁**:

#### 4.3.1 需求质量门禁（Spec Quality Gate）

**借鉴 INCOSE 六标准 + 我们的7维度**:

```
┌─────────────────────────────────────────────────────────────┐
│  需求质量门禁 — 5维度评分                                   │
├──────────────────────┬──────────┬───────────────────────────┤
│ 维度                  │ 权重     │ INCOSE 映射              │
├──────────────────────┼──────────┼───────────────────────────┤
│ 清晰度 (Clarity)     │ 25%     │ Clear + Unambiguous       │
│ 完整度 (Completeness)│ 25%     │ Complete + Necessary       │
│ 可执行度 (Executable)│ 20%     │ Testable + Traceable       │
│ 一致度 (Consistency) │ 15%     │ Consistent                 │
│ 下游适配度 (Fit)     │ 15%     │ Appropriate（适度详细）    │
└──────────────────────┴──────────┴───────────────────────────┘

总分 = 清晰度×0.25 + 完整度×0.25 + 可执行度×0.20 + 一致度×0.15 + 适配度×0.15
```

**各维度详细评估**:

**清晰度 (Clarity)**:
- 目标描述是否只有一种解读？
- 功能边界是否清晰？（"支持大量用户" → 模糊；"支持10000并发" → 清晰）
- 术语是否一致？（不应同一概念用不同名称）
- 评估方法: 检查 confirmed 层的描述中是否有模糊词（"大量""高性能""易用"等无量化词）

**完整度 (Completeness)**:
- 7个需求维度是否都有覆盖？
- 每个维度的深度是否够？（不是只有标题，要有细节）
- 评估方法: 同之前的7维度评分

**可执行度 (Executability)**:
- 需求是否足够具体，下游引擎能直接使用？
- 功能描述是否可转化为技术方案？
- 质量属性是否有量化指标？
- 评估方法: 检查 capabilities 是否有 always/should/never 分层，quality_attributes 是否有数字

**一致度 (Consistency)**:
- 需求之间是否矛盾？
- 例: "预算50万" + "要用最贵的方案" → 矛盾
- 约束条件与功能需求是否兼容？
- 评估方法: 交叉检查 confirmed 层各维度间的逻辑一致性

**下游适配度 (Fitness for Downstream)**:
- Living Spec 的格式是否符合 Solution Pro 的输入要求？
- 是否包含 solution_pro_hints？
- 是否有足够的 focus_areas 引导 Research？
- 评估方法: 结构完整性检查（必要字段是否存在）

**门禁决策**:

```
┌───────────┬────────────┬────────────────────────────────────────┐
│ 决策       │ 分数       │ 行为                                  │
├───────────┼────────────┼────────────────────────────────────────┤
│ PASS      │ ≥ 75       │ Spec 质量达标，可以交付下游            │
│ WARN      │ 60-74      │ 质量可用但有改进空间，标注不足项交付   │
│ SOFT_BLOCK│ 45-59      │ 质量不足，建议补充，但用户可选择继续   │
│ HARD_BLOCK│ < 45       │ 质量严重不足，不建议启动下游引擎       │
└───────────┴────────────┴────────────────────────────────────────┘

特殊规则:
- 清晰度 < 50 → 至少 WARN（模糊的需求会导致下游做无用功）
- 一致度 < 40 → 至少 SOFT_BLOCK（矛盾的需求会导致下游混乱）
- 可执行度 < 40 → 至少 WARN（太抽象的需求下游无法消费）
```

#### 4.3.2 推断审计门禁（Inference Audit Gate）

```
检查项:
1. 所有推断是否都已处理（confirmed 或 rejected）？
   - 仍有 pending 推断 → 标记在最终报告中

2. 被拒绝的推断是否影响了 Spec 完整性？
   - 拒绝的推断覆盖了某个关键维度 → 该维度可能不完整

3. 推断来源标注是否清晰？
   - 每个推断都有 basis → PASS
   - 有推断没有 basis → WARN

输出:
{
  "inference_audit": {
    "total": 10,
    "confirmed": 6,
    "rejected": 2,
    "pending": 2,
    "decision": "PASS",
    "notes": "2个推断待确认，已在 Spec 中标注"
  }
}
```

#### 4.3.3 对话轨迹门禁（Conversation Trajectory Gate）

```
检查项:
1. 总轮次是否合理？
   - Standard 模式 3-6 轮 → 正常
   - < 3 轮 → 可能收集不充分
   - > 6 轮 → 可能效率不高

2. 质量轨迹是否单调递增？
   - 单调递增 → 健康
   - 有回退 → 标注哪轮回退 + 原因

3. 维度推进是否均衡？
   - 所有维度都有提升 → 健康
   - 某维度始终为0 → 标注

输出:
{
  "trajectory_audit": {
    "total_rounds": 4,
    "quality_trajectory": [15, 38, 55, 68, 82],
    "is_monotonic": true,
    "dimensions_never_improved": [],
    "decision": "PASS"
  }
}
```

**Output Guard 综合决策**:

```
最终决策 = worst(需求质量门禁, 推断审计门禁, 对话轨迹门禁)

但用户可以 override:
- WARN/SOFT_BLOCK → 用户说"可以了" → 放行（标注风险）
- HARD_BLOCK → 用户确认 → 仍然放行（明确标注"用户强制放行"）
```

### 4.4 Layer 4: Safety Valve（安全阀）

**全程监控，不可被 override**:

#### 4.4.1 硬上限

```python
SAFETY_LIMITS = {
    "max_rounds": {
        "quick": 5,      # Quick 模式最多5轮（含确认轮）
        "standard": 10,
        "deep": 15
    },
    "max_tokens_per_round": 50000,    # 单轮最大 token
    "max_total_tokens": 300000,       # 整个会话最大 token
    "max_inferences": 20,             # 最多推断数
    "max_worker_timeout": 300,        # Worker 超时秒数
}
```

#### 4.4.2 Kill Criteria（异常终止）

```
触发条件:
1. 连续3轮质量不升反降 → 对话已失控
2. 用户输入连续3次无效（空/无意义）→ 用户可能不想继续
3. Worker Agent 连续2次超时 → 系统异常
4. 推断拒绝率 > 80% → 推断引擎严重偏差
5. Living Spec 被检测到严重自相矛盾 → 数据已不可信

Kill 行为:
- 立即停止收集
- 保存当前 Spec（标注为 KILLED + 原因）
- 输出当前能给出的最佳 Spec
- 明确告知用户停止原因
```

#### 4.4.3 成本守卫

```
检查项:
- 每轮 token 消耗追踪
- 预估剩余轮次 × 平均 token = 预估剩余成本
- 如果预估总成本超过 budget → 建议用户切换到更轻量的模式

输出:
{
  "cost_guard": {
    "rounds_completed": 3,
    "tokens_used": 85000,
    "avg_tokens_per_round": 28333,
    "estimated_remaining_rounds": 2,
    "estimated_total_tokens": 141666,
    "budget": 300000,
    "status": "within_budget"
  }
}
```

---

## 5. Harness Worker 设计（OpenClaw 实现）

### 5.1 Harness 作为独立 Worker

```
在 Output Guard 阶段，spawn 一个专门的 HarnessWorker:

  SpecProOrchestrator Worker:
    1. 检测到停止条件
    2. spawn HarnessWorker:
       task: "你是 Spec Pro HarnessWorker。
              读取: living_spec.json + quality_report.json + conversation_log.json
              执行: 三层 Output Guard 检查
              写入: harness_report.json"
    3. 等待完成
    4. 读取 harness_report.json
    5. 基于决策写入 round_result.json
```

### 5.2 HarnessWorker Prompt

```markdown
# Spec Pro HarnessWorker

你是 Spec Pro 的质量门禁评估专家。你的任务是评估 Living Spec 是否可以交付给下游引擎。

## 评估框架（5维度）

### 维度 1: 清晰度 (Clarity) — 权重 25%
评估: 需求表述是否无歧义，下游能否准确理解

检查:
- confirmed 层中的描述是否有量化指标？
  - "高性能" → 模糊（扣分）
  - "支持10000并发，P99 < 200ms" → 清晰（满分）
- 术语是否一致？
- 功能边界是否明确？

评分:
- 100: 所有需求都有明确量化指标
- 75: 大部分需求有量化，少数定性描述但足够清晰
- 50: 混合量化和模糊描述
- 25: 大部分描述模糊
- 0: 全部是泛泛描述

### 维度 2: 完整度 (Completeness) — 权重 25%
评估: 关键需求维度是否都有覆盖

检查 7 个子维度:
1. 目标与痛点 (weight 20%)
2. 用户与场景 (weight 15%)
3. 能力要求 (weight 15%)
4. 质量属性 (weight 15%)
5. 约束边界 (weight 15%)
6. 环境与集成 (weight 10%)
7. 风险与假设 (weight 10%)

### 维度 3: 可执行度 (Executability) — 权重 20%
评估: 下游引擎能否直接消费这份 Spec

检查:
- capabilities 是否有 always/should/never 分层？
- quality_attributes 是否有具体数字？
- constraints 是否有具体值（预算金额、时间节点）？
- solution_pro_hints 是否存在且有 focus_areas？

### 维度 4: 一致度 (Consistency) — 权重 15%
评估: 需求之间是否有矛盾

检查:
- 约束条件与功能需求是否兼容？
  - 例: "预算50万" + "全用AWS最贵方案" → 矛盾
- 质量属性之间是否兼容？
  - 例: "99.999%可用" + "不能做冗余部署" → 矛盾
- 能力要求是否有冲突？
  - 例: always_do: "开放所有API" + never_do: "不允许外部访问" → 矛盾

### 维度 5: 下游适配度 (Downstream Fitness) — 权重 15%
评估: 结构是否完整，是否适合下游消费

检查:
- living_spec.json 结构是否符合标准？
- 必要字段是否存在？
- solution_pro_hints 是否可操作？
- route_recommendation 是否合理？

## 推断审计
额外检查:
- 仍有 pending 推断？→ 标注
- 推断拒绝率是否异常？→ 标注
- 推断 basis 是否清晰？→ 标注

## 对话轨迹审计
额外检查:
- 质量轨迹是否单调递增？
- 有无回退轮次？
- 轮次是否合理？

## 输出格式

写入: {blackboard}/spec/harness_report.json

```json
{
  "harness_version": "1.0",
  "timestamp": "...",
  
  "dimensions": {
    "clarity":      {"score": 75, "weight": 0.25, "reasoning": "...", "issues": [...]},
    "completeness": {"score": 82, "weight": 0.25, "reasoning": "...", "issues": [...]},
    "executability":{"score": 70, "weight": 0.20, "reasoning": "...", "issues": [...]},
    "consistency":  {"score": 90, "weight": 0.15, "reasoning": "...", "issues": [...]},
    "fitness":      {"score": 85, "weight": 0.15, "reasoning": "...", "issues": [...]}
  },
  
  "overall_score": 79.5,
  
  "gates": {
    "spec_quality": {"score": 79.5, "decision": "PASS", "threshold": 75},
    "inference_audit": {"pending": 2, "decision": "PASS", "notes": "..."},
    "trajectory_audit": {"rounds": 4, "monotonic": true, "decision": "PASS"}
  },
  
  "final_decision": "PASS",
  "final_reasoning": "需求质量79.5分达到75分阈值，推断审计和对话轨迹均PASS",
  
  "improvements_if_more_time": [
    "可以补充风险与假设维度",
    "建议量化质量属性中的'易用性'指标"
  ],
  
  "warnings": [],
  
  "downstream_readiness": {
    "solution_pro": true,
    "readiness_notes": "Living Spec 可被 Solution Pro Standard 模式消费"
  }
}
```

## 决策规则

PASS:          总分 ≥ 75 且 无子门禁 HARD_BLOCK
WARN:          总分 60-74
SOFT_BLOCK:    总分 45-59
HARD_BLOCK:    总分 < 45 或 一致度 < 40

特殊规则:
- 清晰度 < 50 → 至少 WARN
- 一致度 < 40 → 至少 SOFT_BLOCK
- 可执行度 < 40 → 至少 WARN
```

---

## 6. Harness 报告展示

### 6.1 用户可见的 Harness 摘要

```
┌─────────────────────────────────────────────────┐
│  📋 Spec Pro 质量门禁报告                        │
├─────────────────────────────────────────────────┤
│                                                 │
│  综合评分: 79.5/100  等级: A  决策: ✅ PASS     │
│                                                 │
│  ┌─────────────────────────────────────────────┐│
│  │ 清晰度    ████████░░  75  PASS              ││
│  │ 完整度    █████████░  82  PASS              ││
│  │ 可执行度  ████████░░  70  PASS              ││
│  │ 一致度    ██████████  90  PASS              ││
│  │ 下游适配  █████████░  85  PASS              ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  对话统计: 4轮对话 · 6个推断(5确认/1待确认)     │
│  质量轨迹: 15 → 38 → 55 → 68 → 82             │
│                                                 │
│  ⚠️ 如有更多时间可改进:                         │
│  - 补充风险与假设维度                           │
│  - 量化'易用性'指标                             │
│                                                 │
│  ✅ 可以启动 Solution Pro                       │
└─────────────────────────────────────────────────┘
```

### 6.2 BLOCK 场景展示

```
┌─────────────────────────────────────────────────┐
│  📋 Spec Pro 质量门禁报告                        │
├─────────────────────────────────────────────────┤
│                                                 │
│  综合评分: 52/100  等级: C  决策: ⚠️ SOFT_BLOCK│
│                                                 │
│  问题:                                          │
│  - 清晰度不足: 多个关键需求没有量化指标         │
│  - 约束边界缺失: 没有预算和时间约束             │
│                                                 │
│  建议:                                          │
│  - 再花2轮对话补充约束信息                      │
│  - 或者降低期望，使用 Quick 模式执行            │
│                                                 │
│  你的选择:                                      │
│  1. 继续补充（推荐）                            │
│  2. 用当前 Spec 启动（标注风险）                │
│  3. 放弃                                        │
└─────────────────────────────────────────────────┘
```

---

## 7. 与 Solution Pro Harness 的对比

| 维度 | Solution Pro Harness | Spec Pro Harness |
|:---|:---|:---|
| **评价对象** | 方案（Solution） | 需求规格（Spec） |
| **核心问题** | "答案好不好？" | "问题问清楚了吗？" |
| **评分维度** | 完整性/必要性/目标一致性 | 清晰度/完整度/可执行度/一致度/适配度 |
| **层数** | 2层（中期+最终） | 4层（输入/过程/输出/安全阀） |
| **独特机制** | Layer 2 约束注入 | 推断审计 + 对话轨迹 |
| **终止条件** | 评分 ≥ 0.85 PASS | 评分 ≥ 75 PASS + 3子门禁 |
| **过程监控** | 无（批处理） | 对话推进度 + 平衡度 + 推断监控 |
| **Kill Criteria** | Worker连续失败 | 质量回退 + 推断偏差 + 输入无效 |
| **实现方式** | Python 函数 (harness_scorer.py) | HarnessWorker Agent（Prompt驱动） |

---

## 8. 新增文件（Harness 相关）

```
prompts/spec_pro/
├── ...（已有的6个Prompt）
└── harness.md                # ← 新增: HarnessWorker Prompt

cage/spec_pro.yaml            # ← 更新: 增加 Harness 契约
```

---

*Spec Pro Harness 设计 v1.0 完成。*
