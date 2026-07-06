# LoOP 可靠性机制：Agent 协作模式视角

> **作者角色**: LLM Agent 协作模式研究员  
> **研究背景**: Multi-agent orchestration, loop-based architectures, agentic reliability  
> **目标系统**: OpenClaw LoOP (Loop-based Task Execution Pattern)

---

## 1. Loop 中的角色分离：四角色混合分配模型

### 1.1 设计原则

借鉴 StateFlow (COLM 2024) 的核心洞察——**heuristic transitions 与 LLM-decided transitions 的混合策略**，LoOP 的角色分配应遵循一个基本原则：**确定性操作用 Python，语义判断用 LLM**。这与 Karpathy 的 "AI Native" 决策规则高度一致。

### 1.2 四角色分配矩阵

| 角色 | 执行载体 | 理由 | 失败模式 |
|:-----|:---------|:-----|:---------|
| **PLANNER** | Python (确定性) + LLM (一次性) | 计划生成需要语义理解，但一旦生成应固化为 DAG/FSM，不应每轮重新规划 | Plan drift：LLM 每轮重新理解计划导致偏移 |
| **DOER** | LLM (per-phase worker) | 执行需要创造性，但必须限制在单 phase 范围内 | 上下文污染、指令遗忘 |
| **CHECKER** | Python (规则校验) + LLM (语义评估) | 关键洞察：**CHECKER 分层**。L0=Python 断言（零失败率），L1=LLM 评分（有失败率但可校准） | Checker 自身的 hallucination |
| **MEMORY** | Python (外部存储) | 记忆绝不能依赖 LLM 的上下文窗口。必须外化为结构化存储 | Context rot 的根本原因就是 MEMORY 角色被内化到了 LLM 上下文 |

### 1.3 核心创新：Python 作为 "执行骨架"

与 MetaAgent (ICML 2025) 的自动 FSM 构建不同，LoOP 的独特约束是 **LLM 不能 spawn LLM**（depth 限制）。这意味着 Python 不仅是辅助工具，而是**执行骨架本身**：

```
Python Loop Controller (确定性)
├── Phase 1: LLM DOER → 产出 artifact
├── Phase 1: Python CHECKER L0 → 断言验证
├── Phase 1: LLM CHECKER L1 → 语义评分 (可选)
├── Phase 1: Python MEMORY → 写入 checkpoint
├── Phase 2: LLM DOER → 基于 checkpoint 继续
└── ...
```

**关键设计决策**：循环控制流（for/while/branch）必须 100% 在 Python 中。LLM 只负责 "phase 内的局部决策"，永远不负责 "下一个 phase 是什么" 的全局决策。这直接解决了 Solution Pro 33% 成功率的根因——LLM 循环逻辑脆弱。

---

## 2. Reflexion 在 Loop 中的应用

### 2.1 Reflexion 模式回顾

Reflexion (NeurIPS 2023) 的核心机制：Agent 执行 → 环境反馈 → **自我反思生成 verbal reinforcement** → 下次执行时注入反思 → 性能提升。在 LoOP 中，我们将 "环境反馈" 替换为 "CHECKER 评估"。

### 2.2 Phase-Level Reflexion 架构

每个 phase 完成后，执行以下 Reflexion 三元组：

1. **DOER 执行** → 产出 `artifact_i`
2. **CHECKER 评估** → 产出 `evaluation_i = {score, issues[], suggestions[]}`
3. **REFLECTOR 总结** → 产出 `reflection_i = "Phase {i} 发现 {issues}，下一步应 {corrections}"`

`reflection_i` 被注入到 Phase `i+1` 的 DOER prompt 前缀中。

### 2.3 CHECKER Agent Prompt 设计

CHECKER L1（语义评估层）的 prompt 应遵循 **结构化评估协议**：

```markdown
## 评估协议

你需要评估以下 Phase 产出物。评估维度：

### 维度 1: 任务完成度 (0-10)
- 10: 完全满足 Phase 目标描述
- 5-9: 核心功能完成但有遗漏
- 0-4: 重大缺陷

### 维度 2: 与 Plan 的对齐度 (0-10)
- 对照原始 Plan 中的 Phase 目标逐条检查
- 每遗漏一条目标扣 2 分

### 维度 3: 可集成性 (0-10)
- 产出物能否被后续 Phase 直接使用？
- 格式是否符合预期？

### 输出格式
```json
{
  "scores": {"completion": N, "alignment": N, "integrability": N},
  "issues": ["issue1", "issue2"],
  "reflection": "一句话总结本 phase 的核心问题和改进方向",
  "verdict": "PASS | REVISE | FAIL"
}
```

判定规则：
- 总分 ≥ 24 → PASS
- 总分 18-23 → REVISE（附具体修改要求）
- 总分 < 18 → FAIL（触发 phase 重试或降级）
```

### 2.4 Reflexion 的边界条件

**重要发现**：Reflexion 不是万能的。在 LoOP 中需要注意：

- **Reflexion 饱和**：同一 phase 重试超过 2 次后，改进幅度递减（参考 Reflexion 论文 Figure 3）。应设置 `max_retries=2`，超过后触发降级策略。
- **Reflection 污染**：过多的历史 reflection 会加速 context rot。解决方案：只保留最近 1 条 reflection，更早的压缩为 checkpoint。

---

## 3. Anti-Context-Rot 策略

### 3.1 Context Rot 的数学模型

设 LLM 的有效注意力窗口为 `W`，当前上下文长度为 `L`。当 `L > 0.7W` 时，LLM 对上下文中间部分的回忆能力显著下降（"Lost in the Middle" 现象，Liu et al. 2023）。在 10+ phase 的 Loop 中，如果不做管理，`L` 将线性增长：

```
L_n = L_0 + n * (prompt_template + artifact + evaluation + reflection)
```

以 GPT-4 级别模型为例，每个 phase 约增加 3-5K tokens，10 个 phase 后 `L ≈ 50-70K`，进入危险区。

### 3.2 三层防御策略

| 层级 | 策略 | 机制 | 信息损失 |
|:-----|:-----|:-----|:---------|
| **L0: Compaction** | 滑动窗口压缩 | 只保留最近 2 个 phase 的完整上下文，更早的压缩为摘要 | 中（细节丢失） |
| **L1: Checkpoint** | 结构化状态外化 | 每个 phase 结束时，将关键产出写入外部文件（JSON/MD），下一 phase 只读 checkpoint | 低（结构化保留） |
| **L2: Memory** | 语义检索记忆 | 将历史 phase 的 reflection 和 issues 存入向量存储，按需检索相关记忆 | 最低（按需召回） |

### 3.3 推荐组合：Checkpoint + Rolling Reflection

**最优实践**：L1 + 改良版 L0。

```
每个 Phase 的 DOER 输入 = 
    System Prompt (固定)
  + Original Plan (固定，不变)
  + Current Phase Spec (从 Plan 提取)
  + Previous Phase Checkpoint (结构化 JSON，< 2K tokens)
  + Latest Reflection (1 条，< 500 tokens)
  + Relevant Memory (按需检索，< 1K tokens)
```

**总上下文预算**：每个 worker < 8K tokens 输入。这保证了即使 10+ phase，每个 worker 的上下文始终在安全范围内。

**关键设计**：Original Plan 永远完整保留。这防止了 "plan drift"——LLM 在长上下文中逐渐偏离原始目标的现象。Plan 是锚，checkpoint 是路标。

---

## 4. No-Progress Detection：三种检测方法对比

### 4.1 方法一：Artifact Diff 检测

**原理**：比较相邻 phase 的产出物差异。如果 `diff(artifact_i, artifact_{i+1}) < threshold`，判定为无进展。

| 优势 | 劣势 | 适用场景 |
|:-----|:-----|:---------|
| 客观、零 LLM 成本 | 需要定义 "差异" 的度量方式 | 代码生成、文档撰写等有明确产出的任务 |

### 4.2 方法二：CHECKER Score Plateau

**原理**：连续 N 个 phase 的 CHECKER 评分变化 < ε，判定为收敛（可能是局部最优或卡住）。

| 优势 | 劣势 | 适用场景 |
|:-----|:-----|:---------|
| 语义层面检测，不依赖产出格式 | 依赖 CHECKER 的评分稳定性 | 有明确评估标准的任务 |

### 4.3 方法三：Action Repetition Detection

**原理**：检测 DOER 是否在重复相同的操作（相同 tool call、相同文件修改）。

| 优势 | 劣势 | 适用场景 |
|:-----|:-----|:---------|
| 实现简单，精确度高 | 只能检测显式重复，无法检测语义重复 | 所有场景（作为兜底层） |

### 4.4 推荐：三层级联检测

```python
def detect_no_progress(phase_history):
    # L0: Action Repetition (零成本，精确)
    if last_n_actions_same(phase_history, n=3):
        return "STUCK: action_repetition"
    
    # L1: Artifact Diff (低成本，客观)
    if artifact_similarity(phase_history[-2], phase_history[-1]) > 0.9:
        return "STUCK: artifact_plateau"
    
    # L2: Score Plateau (需要 CHECKER，语义层面)
    if score_stddev(phase_history[-3:], threshold=0.5):
        return "STUCK: score_plateau"
    
    return "PROGRESSING"
```

**降级策略**：检测到 stuck 后，依次执行：(1) 注入新的 reflection 提示；(2) 跳过当前 phase 进入下一个；(3) 终止 Loop 并报告部分完成。

---

## 5. Loop Fingerprinting：可追溯的运行指纹

### 5.1 设计理念

每次 Loop 运行都应产生一个**不可变的指纹文档**，用于事后分析和持续改进。这借鉴了分布式系统中的 **distributed tracing** 思想（如 OpenTelemetry）。

### 5.2 指纹结构

```json
{
  "run_id": "loop-20260624-abc123",
  "task_hash": "sha256(task_description)[:12]",
  "fingerprint": {
    "plan": {"phases": 10, "strategy": "sequential"},
    "execution": {
      "phases_completed": 8,
      "phases_failed": 1,
      "phases_skipped": 1,
      "total_retries": 3,
      "retry_distribution": [0, 1, 0, 2, 0, 0, 0, 0]
    },
    "context_profile": {
      "avg_worker_tokens": 6200,
      "peak_worker_tokens": 9100,
      "total_llm_calls": 18,
      "total_tokens_consumed": 112000
    },
    "quality_trajectory": {
      "checker_scores": [7, 8, 6, 9, 8, 9, 9, 10],
      "reflections_generated": 8,
      "reflections_actioned": 6
    },
    "outcome": {
      "status": "partial_success",
      "completion_ratio": 0.8,
      "degradation_events": ["phase_4_retry_x2"]
    }
  },
  "timestamp": "2026-06-24T23:47:00+08:00"
}
```

### 5.3 指纹的用途

1. **事后分析**：失败 run 的 fingerprint 可以精确定位哪个 phase 开始退化
2. **模式识别**：积累 50+ run 的指纹后，可以发现 "phase_4 经常失败" 这类模式
3. **基线建立**：同类任务的 fingerprint 对比，建立成功率基线

---

## 6. Agent Improvement Loop：Meta-Loop 设计

### 6.1 三层改进循环

```
┌─────────────────────────────────────────────────┐
│  Layer 3: Skill Evolution (跨任务，周级)          │
│  → 修改 Skill prompt / CHECKER 评估标准           │
├─────────────────────────────────────────────────┤
│  Layer 2: Plan Template Optimization (跨任务，日级)│
│  → 优化 Plan 模板的 phase 划分策略                 │
├─────────────────────────────────────────────────┤
│  Layer 1: Runtime Adaptation (任务内，分钟级)      │
│  → Reflection + CHECKER 驱动的实时调整             │
└─────────────────────────────────────────────────┘
```

### 6.2 Layer 3 的具体机制

借鉴 OpenAI 的 Agent Improvement Loop 理念：

```
traces (fingerprint 集合)
  → evaluations (哪些 phase 类型失败率高？)
  → hypotheses (失败原因分类：prompt 不清？context 不够？phase 粒度太粗？)
  → interventions (修改 Skill prompt / 调整 phase 粒度 / 增强 CHECKER 标准)
  → validation (A/B 对比修改前后的成功率)
```

**具体实现**：维护一个 `loop_analytics.json`，每次 run 结束后追加 fingerprint。当积累 10+ 同类任务指纹时，触发分析：

```python
# 伪代码
if len(fingerprints_by_type["code_generation"]) >= 10:
    avg_scores = compute_avg_quality_trajectory(fingerprints_by_type["code_generation"])
    worst_phases = find_phases_below_threshold(avg_scores, threshold=7.0)
    # 生成改进建议
    suggestions = llm_analyze(worst_phases, fingerprints_sample)
    # 写入 Skill 改进提案
    create_skill_improvement_proposal(suggestions)
```

---

## 7. 创新性设计

### 7.1 创新一：Checkpoint-Mediated Agent Handoff (CMAH)

**学术来源**：借鉴人类软件工程中的 "shift handoff" 协议（航空、医疗领域的交接班制度）。

**核心思想**：每个 phase 的 DOER 不是一个持续运行的 LLM session，而是一个**全新的、无状态的 worker**。phase 间的连续性完全由 **checkpoint 文件** 中介：

```
Phase N DOER (无状态)
    → 产出 artifact_N
    → CHECKER 评估
    → Python 生成 checkpoint_N = {
        artifact_summary,      # 产出物摘要 (< 500 tokens)
        decisions_made,        # 本 phase 做出的关键决策
        unresolved_issues,     # 未解决的问题
        next_phase_hints,      # 给下一个 phase 的建议
        plan_progress          # Plan 完成进度标记
      }
    → 写入 checkpoint_N.json

Phase N+1 DOER (全新 session)
    ← 读取 checkpoint_N.json
    ← 读取 Original Plan
    ← 读取 Current Phase Spec
    → 开始执行（拥有完整上下文，无历史污染）
```

**为什么创新**：
- 传统 multi-agent 系统假设 agent 间共享上下文（如 AutoGen 的 shared chat history），这正是 context rot 的根源
- CMAH 将 agent 间通信**降维为结构化文件**，每个 agent 的上下文都是干净的
- 这实现了真正的 "无状态 worker" 模式，与 Kubernetes pod 的设计理念一致

**工程可行性**：完全可行。OpenClaw 的 sessions_spawn 已经支持每次创建干净的子 agent。checkpoint 文件通过文件系统传递。

### 7.2 创新二：Adversarial CHECKER with Calibrated Confidence (ACCC)

**学术来源**：借鉴校准预测（calibrated prediction, Guo et al. 2017）和对抗评估（adversarial evaluation, 红队测试）。

**核心思想**：CHECKER 不是单一评估者，而是**两个对抗角色**的组合：

1. **Validator（验证者）**：评估产出物是否满足要求
2. **Adversary（对抗者）**：尝试找出产出物的隐藏缺陷

两者的分歧度（divergence）作为**置信度校准信号**：

```
checker_result = {
    validator_score: 8,
    adversary_findings: ["edge_case_not_handled", "error_path_missing"],
    adversary_score: 5,
    divergence: 3,  # |8 - 5| = 3
    confidence: "LOW"  # divergence > 2 → 低置信度
}

if confidence == "LOW":
    # 触发第三轮评估：Judge（裁判）
    judge_result = llm_judge(artifact, validator_args, adversary_args)
    final_score = judge_result.score
```

**为什么创新**：
- 传统 CHECKER 只有一个评估视角，容易产生系统性盲区
- 对抗机制强制产生**多角度评估**，divergence 本身就是一个强信号
- 当 divergence 高时，自动引入 Judge，形成**动态评估深度**，避免过度评估简单 phase

**工程可行性**：每次评估需要 2-3 次 LLM 调用，成本增加 2-3x。但只对 L1 语义评估层使用（不是每个 phase 都需要），且可以用更便宜的模型做 Adversary。总体成本可控在 1.5x 以内。

### 7.3 创新三（附加）：Progressive Fidelity Execution (PFE)

**核心思想**：每个 phase 先用低成本模型快速验证可行性（low fidelity），通过后再用高质量模型精确执行（high fidelity）：

```
Phase N:
  Step 1 (Low-fi): 小模型 (如 Qwen-7B) 生成草稿方案 → 成本 < 100 tokens
  Step 2 (Gate): Python 规则检查草稿方案的结构完整性
  Step 3 (High-fi): 仅当 Step 2 通过 → 大模型精确执行
  Step 4 (CHECKER): 标准评估流程
```

**价值**：在 early phases（如需求分析、架构设计）中，60%+ 的尝试可能在 low-fi 阶段就被过滤掉，节省大量高质量模型的 token 消耗。

---

## 总结：可靠性机制优先级

| 优先级 | 机制 | 预期收益 | 实施成本 |
|:-------|:-----|:---------|:---------|
| **P0** | Python 循环控制 + 无状态 Worker (CMAH) | 解决 33% → 80%+ 成功率 | 中（架构重构） |
| **P0** | Checkpoint-based Context Management | 消除 context rot | 低 |
| **P1** | 三层 No-Progress Detection | 防止无限循环 | 低 |
| **P1** | Loop Fingerprinting | 支持持续改进 | 低 |
| **P2** | Reflexion per Phase | 提升单次质量 | 中 |
| **P2** | Adversarial CHECKER (ACCC) | 提升评估可靠性 | 中（成本 1.5x） |
| **P3** | Agent Improvement Meta-Loop | 长期持续优化 | 高（需数据积累） |
| **P3** | Progressive Fidelity Execution | 降低成本 | 中 |

> **核心结论**：LoOP 可靠性的关键不在 LLM 能力，而在**工程架构**。将循环控制、状态管理、进度检测全部外化到 Python，让 LLM 只做它擅长的事（语义理解和生成），是突破 33% 成功率瓶颈的根本路径。这与 StateFlow 的 "heuristic + LLM" 混合策略一脉相承，但更进一步——**循环本身必须是 heuristic 的（Python），只有 phase 内部才是 LLM 的**。

---

*参考文献*  
- StateFlow: "StateFlow: Augmenting LLM Agents with Finite State Machine" (COLM 2024)  
- MetaAgent: "MetaAgent: Automatically Building Multi-Agent Systems" (ICML 2025)  
- Reflexion: "Reflexion: Language Agents with Verbal Reinforcement Learning" (NeurIPS 2023)  
- Lost in the Middle: "Lost in the Middle: How Language Models Use Long Contexts" (TACL 2024)  
- Calibrated Prediction: "On Calibration of Modern Neural Networks" (ICML 2017)  
- OpenAI Agent Improvement: "OpenAI Cookbook: Agent Improvement Loop" (2025)
