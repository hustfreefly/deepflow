# Solution Pro Harness 控制体系 — 全面洞察分析

> **作者**: 小满（AI Agent）
> **日期**: 2026-06-06
> **目的**: 系统性总结 DeepFlow Solution Pro 的 Harness 设计思路，作为 DeepSeek Harness PM 申请的核心素材

---

## 一、核心命题：什么是 Harness？

在 DeepFlow 的实践中，**Harness 不是单一组件，而是一整套让 AI Agent 在约束中高质量工作的控制系统**。

用一个类比：
- **Model** = 一个聪明但没有经验的员工
- **Harness** = 公司的 SOP、质量门禁、审批流程、KPI 体系、导师制度的总和

DeepFlow 的核心发现：**模型能力再强，没有 Harness 就是在裸奔。**

具体来说，Solution Pro 的 Harness 回答了五个根本问题：

| 问题 | 回答 | 对应机制 |
|------|------|---------|
| Agent 该做什么？ | 声明式需求冻结 | Frozen Spec + REQ-ID |
| Agent 怎么做？ | 结构化约束注入 | Control Contract + Layer 2 |
| 做得好不好？ | 多维质量门控 | Harness V4 四维评分 |
| 有没有跑偏？ | 需求追踪闭环 | REQ-ID Traceability Matrix |
| 如何持续改进？ | 审计-修复-验证循环 | Auditor → Fixer → Expert Fix → Harness Final |

---

## 二、Harness 控制的时间线：全生命周期视角

Solution Pro 的 Harness 不是一个"最后检查"，而是**贯穿 10 个阶段的持续质量控制系统**：

```
Phase 1: Data Collection        → [无 Harness] 纯采集
Phase 2: Planning               → [Planning Harness] 规划质量自评 + 生成 Control Contract
Phase 3: Reviewers ×3 (并行)    → [Self-Harness] 每个 Reviewer 自评 + 结构化 feedback
Phase 4: Researchers ×N (并行)  → [Self-Harness + Layer 2] 约束响应 + 自评
Phase 5: Consolidator           → [Self-Harness] 整合质量自评
Phase 6: Auditors ×3 (并行)     → [Audit] 独立审计 + 诚实性检查
Phase 7: Fixer                  → [Fix] 针对审计问题修复
Phase 8: Fixer Expert           → [Expert Fix] 深度修复 + PragmaticGuard
Phase 9: Harness Final          → [Final Gate] 四维评分 + 覆盖矩阵 + 全局理解检查
Phase 10: Summarizer            → [Response Harness] 必须响应 Harness Final 意见
```

**关键洞察**：质量不是最后检查的，而是在每个阶段都嵌入的。每个 Worker 既是执行者又是自评者，同时有独立的审计者做交叉验证。

---

## 三、六层控制机制深度解析

### 3.1 第一层：需求冻结（Frozen Spec）

**核心思想**：在任何 Agent 开始工作之前，先把"做什么"变成一份不可变的契约。

```python
# frozen_spec.py — 确定性脚本，不是 LLM 生成
def build_frozen_spec(topic, constraints, living_spec):
    # 从 living_spec.confirmed 中提取 12 种 category 的需求
    # 自动分配 REQ-ID（REQ-001, REQ-002, ...）
    # 按 5 个分组聚合（Core/Functional/NonFunctional/Boundaries/Context）
    # 构建 executive_summary（指针 + 上下文模式）
```

**设计精妙之处**：

1. **确定性生成**：Frozen Spec 由 Python 脚本生成，不是 LLM 输出。这保证了 REQ-ID 的稳定性和可追溯性。

2. **二级分组体系**：12 种细粒度 category 自动聚合为 5 个高层 group，便于 Harness Final 做分组覆盖度检查。

```
Core（核心）: objective + pain_point + scenario
Functional（功能）: capability + integration
NonFunctional（质量）: quality_attribute + constraint + success_metric
Boundaries（边界）: prohibition + guardrail + guardrail_prohibition
Context（上下文）: user + risk + assumption + hint
```

3. **Executive Summary 的指针+上下文模式**：不是把需求复制一遍，而是用 REQ-ID 指针引用 + 关键上下文字段（why, for_whom, success_criteria, constraints）。这让 Harness Final 能快速理解方案的"灵魂"，而不需要重新解析所有需求。

4. **P0 需求的特殊地位**：`Core` 组必须 100% 覆盖，否则方案不可行。`Boundaries` 组的任何覆盖失败都是 Critical 问题。这体现了"**不是所有需求都平等**"的设计哲学。

### 3.2 第二层：控制契约（Control Contract）

**核心思想**：Planning 完成后，用确定性脚本刷新后续所有 Worker 的任务定义。LLM 负责"想"，代码负责"落实"。

```python
# control_contract.py
def rewrite_after_planning(base_path):
    """
    Planning 完成后执行：
    1. 读取 Planner 的输出（required_experts, layer2_constraints, audit_strategy）
    2. 归一化为固定 3 个 Research 槽位
    3. 为每个 Worker 注入 Layer 2 约束 + REQ-ID 追踪指令
    4. 生成 control_contract.json + 刷新 tasks.json
    """
```

**设计精妙之处**：

1. **"固定槽位 + 动态内容"模式**：10 阶段管线是固定的（B 方案），但 Planner 可以决定每个槽位里装什么内容。这平衡了**稳定性**和**灵活性**。

2. **确定性归一化**：`_normalize_experts()` 确保无论 Planner 输出什么格式，最终都是 3 个 Research Expert 槽位。多了截断，少了补默认。这防止了 LLM 的"创意发挥"破坏管线结构。

3. **Acceptance Criteria 从 Frozen Spec 生成**：不是从 Planner 输出取，而是直接从 Frozen Spec 的 `requirement_groups` 生成。这保证了验收标准与原始需求的一致性，避免了"Planner 理解偏差"导致的验收标准偏离。

### 3.3 第三层：Layer 2 约束注入

**核心思想**：不同角色的 Worker 需要不同的约束。Planner 为每个角色生成场景特定的约束，运行时注入到 Prompt。

```python
# task_builder.py
def inject_layer2_constraints(base_prompt, worker_role, layer2_constraints):
    """
    将 Planner 生成的约束注入 Worker Prompt
    - 每个角色最多 2 条约束（P1-1 修复：防止约束过载）
    - Fallback 到默认约束
    - 要求 Worker 输出 layer2_response 响应
    """
```

**设计精妙之处**：

1. **约束分层**：
   - **Layer 1**（全局）：REQ-ID 追踪、Schema 规范 — 所有 Worker 必须遵守
   - **Layer 2**（场景）：Planner 为每个角色定制的约束 — 按需注入

2. **约束数量限制（最多 2 条）**：这是一个从实践中提炼的规则。太多约束会导致 Worker "注意力分散"，反而降低质量。

3. **Fallback 机制**：如果 Planner 没有为某个角色生成约束，使用预定义的默认约束。例如：
   ```python
   "reviewer_technical": [
       "[必要性] 检查技术选型是否贴合实际资源约束",
       "[完整性] 验证关键架构设计点是否充分"
   ]
   ```

4. **约束响应闭环**：Worker 不只是"被约束"，还必须在输出中显式响应每条约束：
   ```json
   {
     "layer2_response": {
       "constraints": [
         {"constraint": "...", "satisfied": true, "note": "如何满足的理由（至少10字）"}
       ]
     }
   }
   ```

### 3.4 第四层：Harness V4 四维评分

**核心思想**：用统一的四维评分体系作为所有质量门控的"通用语言"。

```python
Overall = Completeness×0.30 + Necessity×0.20 + Alignment×0.30 + Global_Impact×0.20
```

**设计精妙之处**：

1. **四个维度的选择逻辑**：
   - **Completeness（完整性）**：有没有遗漏？— 覆盖度问题
   - **Necessity（必要性）**：有没有多余？— 过度设计问题
   - **Alignment（目标一致性）**：有没有跑偏？— 方向问题
   - **Global Impact（全局影响）**：有没有短视？— 长期问题

   这四个维度覆盖了质量问题的**全部象限**：做少了、做多了、做歪了、做短了。

2. **权重的非均匀分配**：完整性和目标一致性各 30%，必要性和全局影响各 20%。这反映了核心判断：**方向正确比面面俱到更重要，但两个都很重要**。

3. **Alignment 的特殊规则**：`alignment < 0.6 → 强制升级为 CRITICAL_WARNING`。即使总分达标，如果方向跑偏了，也必须警告。这是一个从实践中发现的关键规则 —— **方案偏离目标比不完整更危险**。

4. **五级决策阈值**：
   ```
   PASS (≥0.85)              → 质量达标
   PASS_WITH_CONDITIONS      → 有条件通过
   WARNING (0.70-0.84)       → 需关注
   CRITICAL_WARNING (0.60-0.69) → 强烈建议修改
   BLOCK_RECOMMENDATION (<0.60) → 建议重新规划（但不阻断）
   ```
   注意 `BLOCK_RECOMMENDATION` **不阻断**管线。这是一个务实的设计：AI Agent 的质量门是"建议"而非"硬门禁"，因为某些场景下用户可能接受低分方案。

5. **每个 Worker 都做自评**：不是只有最终检查才有 Harness 评分。Reviewer、Researcher、Consolidator、Fixer — 每个 Worker 都在输出中包含 `harness_check` 字段。这实现了"质量内建"（Built-in Quality）。

### 3.5 第五层：REQ-ID 追踪闭环

**核心思想**：从需求定义到最终报告，每条需求都有唯一的 ID，每个 Worker 都必须声明覆盖了哪些需求。

```
Frozen Spec (REQ-001~REQ-N)
    ↓
每个 Worker 输出:
    "covered_req_ids": ["REQ-001", "REQ-003"]
    "requirement_evidence": [{"req_id": "REQ-001", "status": "covered", "evidence": "..."}]
    ↓
Harness Final 生成:
    requirements_traceability_matrix.json
    ↓
Summarizer 读取覆盖矩阵，在 final_solution.md 中输出"需求覆盖度"章节
```

**设计精妙之处**：

1. **单一权威来源**：REQ-ID 只能来自 `frozen_spec.json`。Worker 不能臆造新 REQ-ID，不能修改已有 REQ-ID。这防止了"需求蔓延"。

2. **三种覆盖状态**：`covered` / `partial` / `missing`。比二元的"覆盖/未覆盖"更精确。P0 需求标记为 `missing` 时必须说明原因。

3. **Evidence 要求**：不能只说"覆盖了"，必须给出具体证据（"在 3.2 节设计了 Redis 缓存方案"）。这防止了敷衍。

4. **Structured Requirements 的定位**：`structured_requirements.json`（Planner 生成）只能作为"覆盖提示"，不能覆盖 `frozen_spec.json` 的权威。这是双文件制衡。

### 3.6 第六层：审计-修复-验证循环

**核心思想**：独立审计 → 针对性修复 → 专家级深度修复 → 最终质量门控。四步形成闭环。

```
Phase 6: Auditors ×3 (并行)
    → 独立审计（不依赖 Worker 自评）
    → Worker 诚实性检查（对比自评 vs 实际质量）
    → 问题按 P0/P1/P2 分级
        ↓
Phase 7: Fixer
    → 读取审计报告，按优先级修复
    → P0 必须修复，P1 建议修复
    → 自检修复效果
        ↓
Phase 8: Fixer Expert
    → 深度修复（专家级别）
    → PragmaticGuard：技术债务 ≤ 2，架构一致性检查
    → P0 必须 100% 修复，否则扣 40 分
        ↓
Phase 9: Harness Final
    → 四维评分（最终门控）
    → 全局理解一致性检查
    → 需求分组覆盖度检查
    → 生成 requirements_traceability_matrix.json
        ↓
Phase 10: Summarizer
    → 必须响应 Harness Final 的每条 feedback 和 improvement
    → 不采纳的必须有 ≥20 字的详细理由
    → 代码级验证（validate_summarizer_harness_response）
```

**设计精妙之处**：

1. **审计与修复分离**：Auditor 只发现问题不做修复，Fixer 只做修复不做评判。"运动员不当裁判"的原则贯穿始终。

2. **Worker 诚实性检查**（`worker_honesty_check`）：Auditor 专门检查 Worker 的自评是否"放水"：
   ```json
   {
     "worker": "researcher_expert_1",
     "self_assessed": "green",
     "actual_quality": "yellow",
     "honesty_gap": "optimistic",
     "issues": ["覆盖了 8 个维度但遗漏了安全评审"]
   }
   ```
   这是对"AI 自我评估不可靠"这个实践洞察的直接回应。

3. **PragmaticGuard（防发散检查）**：Fixer Expert 有一个特殊的"实用主义守卫"：
   - 技术债务 ≤ 2（防止修复引入更多问题）
   - 架构一致性（防止修复偏离整体架构）
   - 修复方案不能是 "TODO"（必须具体）

4. **Summarizer 响应验证**：这是整个管线的最后一个 Harness，也是最严格的。它不是检查"方案质量"，而是检查"报告是否忠实反映了上游的所有反馈"。代码级验证：
   ```python
   # 每条 feedback 必须被响应
   for feedback in final_feedback:
       assert feedback in [item["feedback"] for item in hr["feedback_addressed"]]
   # 不采纳的必须有 ≥20 字理由
   if not item["adopted"]:
       assert len(item["action"]) >= 20
   ```

---

## 四、Schema 分层验证：运行时质量守门员

### 4.1 三层 Schema 设计

```python
# Core Layer（所有阶段必须）
REQUIRED_FIELDS = ["status", "stage", "covered_req_ids"]

# Standard Layer（非 exempt 阶段）
STANDARD_FIELDS = REQUIRED_FIELDS + ["harness_check"]

# Optional Layer
OPTIONAL_FIELDS = ["layer2_response", "metadata"]
```

### 4.2 Exempt 阶段的设计逻辑

```python
HARNESS_EXEMPT_STAGES = frozenset(["data_collection", "planning", "summarizer"])
```

- **data_collection**: 采集阶段，只有事实没有判断，不需要质量评分
- **planning**: 有自己的 `quality_assessment` 机制，但不是标准 4 维
- **summarizer**: 有独立的 `harness_response` 验证机制，不需要重复评分

### 4.3 运行时验证的接入点

```python
# completion_handler.py
def _check_expected_outputs(base_path, expected_stages, required_artifacts):
    for rel_path in paths:
        if rel_path.endswith('.json'):
            data = json.load(open(base_path / rel_path))
            valid, err_msg = validate_stage_output(data, stage_name)
            if not valid:
                schema_errors[stage_name] = err_msg
    
    # 有 schema 错误 → 降级为 partial（即使文件都在）
    if schema_errors and status == 'completed':
        status = 'partial'
```

**关键洞察**：文件存在 ≠ 文件正确。Schema 验证是"存在性检查"之上的第二道防线。

---

## 五、从实践中发现的反模式与解法

### 5.1 反模式一：运动员 = 裁判

**发现**：单 Agent 审计 + 修复 = 无效。Agent 会给自己打高分，然后"修复"不存在的问题。

**解法**：
- 3 个 Reviewer 并行（技术/业务/风险）
- 3 个 Auditor 并行
- 独立的 Harness Final Worker
- Worker 诚实性检查（Auditor 检查 Worker 自评是否放水）

### 5.2 反模式二：评审评分 ≠ 实际质量

**发现**：4 位专家评 3-5.5/10，实际代码验证 8.5/10。评审会臆造问题。

**解法**：
- 从定量评分（0-10）改为定性评级（green/yellow/red）
- 但保留 Harness V4 的 0-1 评分（因为是机器验证，不是人类评审）
- 增加 `level` 字段（high/medium/low）作为定性补充

### 5.3 反模式三：文档 ≠ 修复

**发现**：改了 SKILL.md 不等于改了执行行为。LLM 读了文档不代表会遵守。

**解法**：
- 契约笼子（Contract Cage）：声明 → 执行 → 验证的闭环
- 代码级验证：`validate_summarizer_harness_response()` 不是建议，是检查
- `enforce_harness_response()` 在 Prompt 中嵌入验证代码，让 LLM 知道"不通过会被拒绝"

### 5.4 反模式四：约束过载

**发现**：给 Worker 太多约束反而降低质量。LLM 注意力有限。

**解法**：
- Layer 2 约束最多 2 条（P1-1 修复）
- 分层：Layer 1（全局强制）+ Layer 2（场景特定）
- Fallback 到默认约束（保证最低质量）

### 5.5 反模式五：需求蔓延

**发现**：Worker 会臆造新需求，或者修改已有需求的优先级。

**解法**：
- REQ-ID 只能来自 `frozen_spec.json`
- Worker 不能新增 REQ-ID
- P0 需求未覆盖必须标记 `missing` 并说明原因

---

## 六、Harness 控制的架构模式总结

### 6.1 声明-执行-验证（Declare-Execute-Verify）

这是 DeepFlow Harness 的核心模式：

```
声明（Declare）:
  - Frozen Spec 声明"做什么"
  - Control Contract 声明"怎么做"
  - Layer 2 约束声明"做到什么标准"
  - Schema 声明"输出长什么样"

执行（Execute）:
  - Workers 在约束下工作
  - 每个 Worker 输出包含 covered_req_ids + harness_check + layer2_response

验证（Verify）:
  - Schema 验证（格式正确性）
  - Harness 评分（质量达标性）
  - REQ-ID 追踪（需求覆盖度）
  - 诚实性检查（自评可信度）
  - 响应验证（反馈闭环）
```

### 6.2 确定性 + LLM 混合架构

DeepFlow 的一个核心设计决策：**关键控制点用确定性代码，创造性工作用 LLM**。

| 组件 | 实现方式 | 原因 |
|------|---------|------|
| Frozen Spec 生成 | Python 脚本 | REQ-ID 必须稳定可追溯 |
| Control Contract 刷新 | Python 脚本 | 任务定义不能被 LLM "创意修改" |
| Pipeline 编排 | LLM Orchestrator | 需要处理动态情况 |
| Worker 执行 | LLM Workers | 创造性工作 |
| Harness 评分 | LLM Workers | 需要理解内容的质量判断 |
| Schema 验证 | Python 代码 | 格式检查必须精确 |
| Summarizer 响应验证 | Python 代码 | 反馈闭环必须可靠 |

### 6.3 渐进式信任模型

```
Worker 自评 → Auditor 审计自评 → Harness Final 独立评分 → Summarizer 响应验证
     ↓                ↓                    ↓                       ↓
   低信任           中信任               高信任                  最高信任
  (可能放水)     (交叉验证)           (独立评估)             (代码级验证)
```

### 6.4 容错 ≠ 放松标准

```python
# Orchestrator Prompt 中的错误分类
errors:
  retry: worker 超时、输出文件暂未出现     → 重试一次
  skip: 非关键 worker 缺输出              → 记录失败，继续后续
  abort: execution_plan 无法读取           → 停止管线
```

- Worker 可以失败（容错），但失败会被记录
- 非关键 Worker 失败不阻断管线（务实）
- 但通过质量门的输出必须达标（标准不妥协）

---

## 七、Harness 的进化历程

```
V1.0 (2026-04): 基础管线
  → 简单的串行执行，无质量门控
  → 问题：输出质量不可控

V2.0 (2026-04): 引入 Harness 评分
  → 每个 Worker 增加自评
  → 问题：自评不可靠（放水）

V3.0 (2026-05): 多维审查
  → 3 Reviewer + 3 Auditor 并行
  → Layer 2 约束注入
  → 问题：评审评分 ≠ 实际质量

V4.0 (2026-05): 定性评分 + REQ-ID
  → green/yellow/red 替代 0-10
  → REQ-ID 追踪闭环
  → 问题：Planner 输出不稳定

V4.4 (2026-06): 固定管线 + 动态内容
  → B 方案：固定 10 阶段
  → Control Contract 确定性刷新
  → Schema 分层验证
  → Summarizer 响应验证
  → Harness Final 全局理解检查
  → 需求分组覆盖度检查
```

**进化规律**：每一版都是在实践中发现问题 → 设计解法 → 验证效果。这不是理论推导，而是工程实践的自然演进。

---

## 八、对 Harness Engineering 的元认知

### 8.1 Harness 的本质是什么？

**Harness = 让 AI Agent 在不确定性中产出确定性结果的控制系统。**

具体来说：
- **输入控制**：Frozen Spec 确保需求不被篡改
- **过程控制**：Layer 2 约束 + Schema 规范确保执行不走样
- **输出控制**：Harness 评分 + REQ-ID 追踪确保质量达标
- **反馈控制**：审计-修复-验证循环确保持续改进

### 8.2 Harness 的核心矛盾

**控制力度 vs 创造力**：
- 控制太严 → Agent 变成填表机器，失去创造力
- 控制太松 → Agent 自由发挥，质量不可控

DeepFlow 的平衡点：
- **结构性工作**（格式、覆盖度、追踪）→ 代码级强制
- **判断性工作**（评分、建议、分析）→ LLM 自由发挥 + 交叉验证

### 8.3 Harness 的三个层次

```
L1: Prompt Harness — 通过 Prompt 约束 Agent 行为
L2: Code Harness — 通过代码验证 Agent 输出
L3: Process Harness — 通过流程设计确保质量
```

DeepFlow 三层都用：
- L1: Harness V4 Prompt 模板 + Layer 2 约束注入
- L2: Schema 验证 + Summarizer 响应验证 + Harness Score 计算
- L3: 10 阶段管线 + 审计-修复循环 + REQ-ID 追踪

### 8.4 最重要的实践洞察

> **"Harness 的核心不是限制 Agent，而是让 Agent 知道'做好'的标准是什么。"**

多数 Agent 框架的问题是：给了 Agent 一个任务，但没告诉它什么叫"做好了"。DeepFlow 的做法是：
1. 先定义"做好"的标准（Frozen Spec + Schema + 评分维度）
2. 再让 Agent 去做（Workers）
3. 最后用标准验证（Harness Final）

这就是**声明-执行-对齐**的核心理念。

---

## 九、与 DeepSeek 岗位的映射

| DeepSeek JD 要求 | DeepFlow 对应实践 |
|------------------|-------------------|
| "Harness Engineering 第一手实践" | 从零设计了完整的 Harness 控制体系 |
| "Agent Loop、Tool Use、Subagent" | 10 阶段管线 + sessions_spawn/yield |
| "Prompt Engineering" | 36+ Worker Prompt 模板 |
| "Context Engineering" | 契约笼子 + Layer 2 约束 + Frozen Spec |
| "定义 Agent 是否真的帮助到用户的指标" | Harness V4 四维评分 + REQ-ID 覆盖矩阵 |
| "与研究员深度协作" | Control Contract + Planner 动态生成专家 |
| "产品路线图规划" | V1→V4.4 的清晰演进路径 |
| "Vibe Coding" | 用 AI 辅助构建了整个多 Agent 框架 |
| "UI/UX 设计素养" | 渐进式交付（30s→2min→8min）+ 前端 Dashboard |

---

*本文档基于 DeepFlow V0.4.0 / Solution Pro V4.4 的完整代码和文档分析。*
*所有洞察均来自实际工程实践，非理论推导。*
