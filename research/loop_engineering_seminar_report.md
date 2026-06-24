# OpenClaw LoOP 工程研讨会报告

> **日期**: 2026-06-24 23:50 | **主持**: 小满 | **参会**: 4 位 AI Native 专家
> **主题**: 在 OpenClaw 平台上构建 LoOP 工程，实现长时间自主任务执行

---

## 一、研讨会背景

### 什么是 Loop Engineering？

**Loop Engineering** 是 2026 年 5-6 月由 Peter Steinberger 提出、Addy Osmani 命名的新兴工程实践：

> *"You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents."*

核心定义：**设计一个系统，让系统代替人 prompt AI，按目标驱动、按条件检查、自动循环执行。**

人的角色从"每步打字的人"变成"设计执行机器的人"。

### 为什么现在？

| 时间 | 范式 | 问题 |
|------|------|------|
| 2022 | 单轮 Prompt | 复合错误率：10步×90%准确率=35%成功率 |
| 2023-24 | Agent Loop (ReAct) | LLM 做循环控制，脆弱不可靠 |
| **2025-26** | **Loop Engineering** | **确定性代码做循环，LLM 只做推理引擎** |

我们的亲身经历完美印证了这个趋势：Solution Pro orchestrator 33% 成功率 → Phase Worker 模式（Python 循环控制）。

---

## 二、4 位专家视角汇总

### Expert 1: 系统架构师 — Loop 生命周期设计

**核心贡献**: 6 状态生命周期 + Tick 机制 + OpenClaw 独有优势

#### Loop 生命周期状态机

```
    ┌──────┐
    │ IDLE │ ← 等待触发
    └──┬───┘
       │ trigger
    ┌──▼───────┐
    │ PLANNING │ ← LLM 生成 Plan（一次性）
    └──┬───────┘
       │ plan_ready
    ┌──▼───────┐     ┌──────────┐
    │EXECUTING │────▶│ CHECKING │ ← Python Goal Checker
    └──▲───────┘     └──┬───────┘
       │ not_done       │ done → DONE ✅
       │ (spawn next)   │ stuck → ABORT ❌
       └────────────────┘
                          │ budget_exceeded → TIMEOUT ⏰
                          │ error → RESUMING 🔄
```

**关键设计**: 循环控制流 100% 在 Python 中，LLM 只负责 phase 内的局部决策。

#### Tick 机制（每次 heartbeat/cron wake）

```python
def tick(self) -> LoopDecision:
    """每次唤醒执行一次 tick"""
    # 1. 预算检查
    if self.budget and self.spent >= self.budget:
        return LoopDecision(action="stop", reason="budget_exceeded")
    
    # 2. 最大轮次检查
    if self.round > self.max_rounds:
        return LoopDecision(action="stop", reason="max_rounds")
    
    # 3. Goal 检查（确定性，非 LLM）
    goal = self.checker.check(self.context)
    if goal.met:
        return LoopDecision(action="done", evidence=goal.evidence)
    
    # 4. 无进展检测
    if self.stale_count >= 3:
        return LoopDecision(action="abort", reason="no_progress")
    
    # 5. 继续 → 返回下一步动作
    return LoopDecision(action="continue", next_step=self.plan_next())
```

#### OpenClaw 独有优势 vs OpenAI/Claude SDK

| 维度 | OpenAI SDK | Claude SDK | **OpenClaw** |
|------|-----------|-----------|-------------|
| 循环驱动 | while loop（单进程） | while loop（单进程） | **cron + heartbeat（跨 session）** |
| 长时间运行 | ❌ 不支持 | Routines（云/付费） | **✅ 原生（cron 跨天）** |
| 崩溃恢复 | 需外部框架 | 需外部框架 | **✅ checkpoint + cron 自动恢复** |
| 多 Agent | handoff | N/A | **✅ sessions_spawn + yield** |

---

### Expert 2: 工具链专家 — 6 阶段工具映射

**核心贡献**: PERCEIVE→PLAN→ACT→OBSERVE→CHECK→PERSIST 全链路工具映射 + 3 个创新 Pattern

#### 工具映射矩阵

| 阶段 | 核心任务 | OpenClaw 工具 |
|------|---------|--------------|
| **PERCEIVE** | 感知项目状态 | `exec("loop_runner.py next")` |
| **PLAN** | 决定下一步 | Python 确定性决策 |
| **ACT** | 执行 worker | `sessions_spawn` + `sessions_yield` |
| **OBSERVE** | 收集输出 | `read` + `exec("validate_contract.py")` |
| **CHECK** | 终止条件验证 | Goal Checker（Python） |
| **PERSIST** | 持久化 + 通知 | `feishu_doc` + `feishu_bitable` + `memory` |

#### 三大创新 Pattern

1. **Memory-Guided Loop**: 每次运行前搜索历史经验，注入 worker prompt → 错误率随项目数递减
2. **Adaptive Harness Loop**: 根据系统负载动态调整并行度（高负载→串行，低负载→并行）
3. **Cron-Triggered Loop**: 定时自主运行（每日巡检 / 每周质量门禁）

#### Skills 封装

| Skill 名 | 触发词 | 功能 |
|----------|--------|------|
| `solution_loop` | "跑 Solution Pro" | 自动运行 10 phase 管线 |
| `spec_review_loop` | "评审需求" | 需求质量迭代检查 |
| `research_synthesis` | "技术调研" | 并行调研 + 综合 |

---

### Expert 3: 协作模式研究员 — 可靠性机制

**核心贡献**: 四角色分离 + Anti-Context-Rot + Loop Fingerprinting + 3 个学术创新

#### 四角色分离模型

| 角色 | 执行载体 | 理由 |
|------|---------|------|
| **PLANNER** | Python + LLM（一次性） | Plan 生成需要语义理解，但一旦生成应固化为 DAG |
| **DOER** | LLM（per-phase worker） | 执行需要创造性，限制在单 phase 范围 |
| **CHECKER** | Python（L0 断言）+ LLM（L1 语义） | 分层验证：L0 零失败率，L1 有校准 |
| **MEMORY** | Python（外部存储） | 记忆绝不能依赖 LLM 上下文窗口 |

**核心原则**: 循环控制流 100% 在 Python 中。LLM 只负责"phase 内的局部决策"。

#### Anti-Context-Rot 策略

```
每个 Phase 的 DOER 输入 = 
    System Prompt (固定)          ~2K tokens
  + Original Plan (固定，不变)     ~1K tokens  ← 锚点！
  + Current Phase Spec            ~1K tokens
  + Previous Phase Checkpoint     ~2K tokens  ← 结构化 JSON
  + Latest Reflection             ~500 tokens ← 只保留最近 1 条
  + Relevant Memory               ~1K tokens  ← 按需检索
  ─────────────────────────────────────
  总计: < 8K tokens（安全范围）
```

**关键**: Original Plan 永远完整保留。Plan 是锚，checkpoint 是路标。

#### 三层 No-Progress Detection

```python
def detect_no_progress(phase_history):
    # L0: Action Repetition（零成本，精确）
    if last_n_actions_same(phase_history, n=3):
        return "STUCK: action_repetition"
    
    # L1: Artifact Diff（低成本，客观）
    if artifact_similarity(phase_history[-2], phase_history[-1]) > 0.9:
        return "STUCK: artifact_plateau"
    
    # L2: Score Plateau（语义层面）
    if score_stddev(phase_history[-3:], threshold=0.5):
        return "STUCK: score_plateau"
    
    return "PROGRESSING"
```

#### Loop Fingerprinting

每次运行生成不可变指纹 JSON：

```json
{
  "run_id": "loop-20260624-abc123",
  "execution": {"phases_completed": 8, "total_retries": 3},
  "context_profile": {"avg_worker_tokens": 6200, "total_llm_calls": 18},
  "quality_trajectory": {"checker_scores": [7,8,6,9,8,9,9,10]},
  "outcome": {"status": "partial_success", "completion_ratio": 0.8}
}
```

用途：事后分析 + 模式识别 + 基线建立 → 驱动 Meta-Loop 持续优化。

#### 三个学术创新

1. **CMAH（Checkpoint-Mediated Agent Handoff）**: 无状态 worker + checkpoint 文件中介，彻底消除跨 phase context rot。借鉴 K8s pod 理念。
2. **ACCC（Adversarial CHECKER + Calibrated Confidence）**: Validator vs Adversary 对抗评估，divergence 驱动动态评估深度。
3. **PFE（Progressive Fidelity Execution）**: 低成本模型快速筛选 + 高质量模型精确执行，节省 token。

---

### Expert 4: DeepFlow 多域编排架构师 — 跨域整合

**核心贡献**: Contract Bus + Phase State Machine + Loop DNA + Evolutionary Loop

#### 跨域 Meta-Loop：Contract Bus

```
┌──────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐
│ Spec Pro │──▶│ Solution Pro │──▶│ Ship Pro │──▶│Research  │
│ (需求域) │   │ (方案域)     │   │ (交付域) │   │Pro (研究) │
└────┬─────┘   └──────┬───────┘   └────┬─────┘   └────┬─────┘
     │                │                │               │
     └────────────────┴────────────────┴───────────────┘
                        │
                  ┌─────▼──────┐
                  │ CONTRACT   │ ← 域间通信唯一通道
                  │ BUS        │
                  └────────────┘
```

**核心设计**: 每个域完成后产出标准化契约，下游域从契约读取输入，而非直接依赖文件。

**回环机制**: Ship Pro Reviewer 发现需求不清 → BackloopDecider → 定向回环 Spec Pro（最大 ≤ 2 次）。

#### Phase State Machine + DAG

```
PENDING → RUNNING → GATE_CHECKING → DONE
                ↘               ↘ FAILED → RETRYING (max 2) → SKIPPED
```

**DAG 支持**: Phase 3 (reviewers) 和 Phase 4 (research) 可并行 → 节省 ~30% 时间。

#### Domain-Specific Goal Checkers

| 域 | "Done" 定义 | 检查方式 |
|----|------------|---------|
| Spec Pro | harness ≥ 0.8 + 需求覆盖率 ≥ 90% | Python 断言 |
| Solution Pro | quality_score ≥ 0.85 + 全 REQ-ID 覆盖 | Python + LLM |
| Ship Pro | 5 个 gate 全通过 | Pydantic 验证 |
| Research Pro | 字数 ≥ 5000 + sources ≥ 10 | Python 断言 |

#### 两个创新架构

1. **Loop DNA**: 每次 run 的完整基因图谱（prompt_hash → worker_model → gate_score → retry_count），支持回溯、复制、进化对比。
2. **Evolutionary Loop**: 利用 DNA 历史数据，自动分析高分/低分 run 差异，生成 prompt 优化建议 → 形成自我进化循环。

---

## 三、交叉讨论：共识与分歧

### 4 位专家的共识点

| # | 共识 | 支持专家 |
|---|------|---------|
| 1 | **循环控制流必须 100% 在 Python 中** | 全部 4 位 |
| 2 | **LLM 只做 phase 内的局部决策** | 全部 4 位 |
| 3 | **Checkpoint 替代文件匹配** | Expert 1/3/4 |
| 4 | **Original Plan 永远保留（防 drift）** | Expert 3 |
| 5 | **每个 worker 上下文 < 8K tokens** | Expert 3 |
| 6 | **Goal Checker 是 Loop 的灵魂** | 全部 4 位 |
| 7 | **OpenClaw 的时间维度是独特优势** | Expert 1/2 |

### 分歧点与解决方案

| 分歧 | Expert A 观点 | Expert B 观点 | **决议** |
|------|-------------|-------------|---------|
| CHECKER 用 LLM 吗？ | Expert 3: 分层 L0(Python)+L1(LLM) | Expert 4: 全 Python | **采纳分层方案**：L0 必须 Python，L1 可选 LLM |
| 回环到上游域？ | Expert 4: 支持（≤2 次） | Expert 3: 风险高 | **采纳但谨慎**：最大 2 次 + 回环原因必须记录 |
| Loop 运行数据存哪？ | Expert 1: pipeline_state.json | Expert 4: checkpoints/ 目录 | **两者结合**：checkpoint 目录 + 汇总到 loop_progress.json |
| Reflexion 每 phase 都做？ | Expert 3: 每 phase DOER→CHECKER→REFLECTOR | Expert 2: 成本太高 | **关键 phase 做**：gate_fail 时触发，gate_pass 跳过 |

---

## 四、综合架构方案

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│  Layer 4: META-LOOP（跨域编排）                          │
│  └─ Contract Bus + BackloopDecider + TriggerRouter       │
├─────────────────────────────────────────────────────────┤
│  Layer 3: INTELLIGENCE（智能层）                         │
│  └─ Goal Checkers + Loop DNA + Evolutionary Loop         │
├─────────────────────────────────────────────────────────┤
│  Layer 2: LOOP ENGINE（循环引擎）                        │
│  └─ Phase State Machine + Checkpoint + DAG Scheduler     │
├─────────────────────────────────────────────────────────┤
│  Layer 1: EXECUTION（执行层）                            │
│  └─ sessions_spawn + sessions_yield + Worker Pool        │
├─────────────────────────────────────────────────────────┤
│  Layer 0: OPENCLAW PRIMITIVES（基础设施）                │
│  └─ cron + heartbeat + memory + message + exec           │
└─────────────────────────────────────────────────────────┘
```

### 4.2 核心文件结构

```
.deepflow/
├── loop_engine/
│   ├── __init__.py
│   ├── engine.py          # LoopEngine: tick() + state machine
│   ├── checkpoint.py      # PhaseCheckpoint: 持久化
│   ├── goal_checker.py    # GoalChecker 基类 + 域专属实现
│   ├── dag.py             # DAG 调度器
│   ├── fingerprint.py     # Loop DNA 记录器
│   ├── contract_bus.py    # 跨域契约总线
│   └── no_progress.py     # 三层无进展检测
├── loop_skills/
│   ├── solution_loop.md   # Skill: 自动运行 Solution Pro
│   ├── spec_review.md     # Skill: 需求评审 Loop
│   └── research_loop.md   # Skill: 研究 Loop
├── loop_data/
│   ├── runs/              # 每次 run 的 checkpoint + DNA
│   ├── analytics.json     # 指纹聚合（驱动 Evolutionary Loop）
│   └── learnings.md       # Memory-Guided 经验库
└── research/              # 研究报告（本文件所在）
```

### 4.3 执行流程（一次完整 run）

```
1. 触发
   用户消息 / cron wake → TriggerRouter 识别意图
   → 创建 run 目录 + 初始化 loop_progress.json

2. PLANNING（一次性）
   sessions_spawn(planner_worker) → LLM 生成 Plan (DAG)
   → 写入 plan.json → 固化为 Phase State Machine

3. LOOP（循环）
   WHILE goal_not_met AND budget_ok AND not_stuck:
     a. PERCEIVE: engine.tick() → 读 checkpoint → 决定 next phase
     b. ACT: sessions_spawn(worker) → sessions_yield
     c. OBSERVE: 读输出 + Pydantic gate 验证
     d. CHECK: GoalChecker.check() → progress score
     e. PERSIST: 写 checkpoint + 更新 Bitable 看板
     f. REFLECT (if gate_fail): CHECKER L1 → reflection → 注入下一轮
     g. DETECT: no_progress 三层检测

4. 终止
   goal_met → DONE → 通知用户 + 写 Loop DNA
   budget_exceeded → TIMEOUT → 保存中间状态 + 通知
   no_progress → ABORT → Doctor 诊断 + 通知

5. 后处理
   Loop DNA 写入 analytics.json
   经验写入 learnings.md
   如果积累 10+ 同类 run → 触发 Evolutionary Loop 分析
```

### 4.4 与 DeepFlow 的结合点

| DeepFlow 组件 | LoOP 升级 | 效果 |
|--------------|----------|------|
| `loop_runner.py` | → `loop_engine/engine.py` | 文件匹配 → Phase State Machine |
| `pipeline_state.json` | → `checkpoint.py` | 全局状态 → 每 phase 独立 checkpoint |
| `run_pipeline.py` | → `engine.py` CLI 封装 | 保持 CLI 接口，底层升级 |
| `watcher_cron` | → `cron` + `engine.tick()` | 进度通知 → 完整 Loop 驱动 |
| `契约笼子` | → Goal Checker L0 | Pydantic gate 成为 Goal Checker 的 L0 层 |
| `Doctor` | → `no_progress.py` | T1-T4 检测成为 Loop 内置诊断 |
| `DocUpdate` | → Evolutionary Loop | DNA 数据驱动 prompt 自动优化 |

---

## 五、创新亮点总结

### 业界首创的 5 个设计

| # | 创新 | 来源专家 | 为什么首创 |
|---|------|---------|-----------|
| 1 | **GaaS（Goal-as-a-Service）** | Expert 1 | 声明式终止条件（YAML），硬性+软性条件可组合 |
| 2 | **Temporal-Like Recovery** | Expert 1 | Event Sourcing 事件溯源 + Checkpoint 快照双重恢复 |
| 3 | **CMAH（Checkpoint-Mediated Agent Handoff）** | Expert 3 | 无状态 worker + 文件中介，K8s pod 理念 |
| 4 | **Loop DNA + Evolutionary Loop** | Expert 4 | 运行基因图谱 + 自动 prompt 进化，生物学类比 |
| 5 | **Memory-Guided Loop** | Expert 2 | 利用 OpenClaw memory 实现跨项目学习曲线 |
| 6 | **ACCC（Adversarial CHECKER）** | Expert 3 | Validator vs Adversary 对抗 + divergence 校准 |
| 7 | **Contract Bus（跨域契约总线）** | Expert 4 | 域间通信唯一通道，解耦域依赖 |

### Expert 1 的核心论断

> **"OpenClaw LoOP 不是 Agent Loop，是 Agent Workflow Engine。它更接近 Temporal 的 Durable Execution，而非 OpenAI 的 Runner.run()。"**

**LoOP 三原则**：
1. **状态即代码**：所有状态必须可序列化、可恢复、可审计
2. **检查即控制**：Goal Checker 决定循环继续还是终止
3. **崩溃即常态**：设计假设任何时刻都可能崩溃

### OpenClaw 独有的 3 个优势

| # | 优势 | 为什么其他平台做不到 |
|---|------|-------------------|
| 1 | **时间维度 Loop** | cron/heartbeat 原生支持跨小时/跨天循环 |
| 2 | **分布式 Worker** | sessions_spawn 创建隔离子 Agent，push-based 完成 |
| 3 | **记忆复利** | memory_search 让每次 Loop 自动继承历史经验 |

---

## 六、实施路线图

| 阶段 | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| **P0** | Phase State Machine + Checkpoint | 1 周 | 🔴 最高 |
| **P1** | Goal Checker（4 域专属） | 3 天 | 🔴 最高 |
| **P2** | Contract Bus + 跨域触发 | 1 周 | 🟡 高 |
| **P3** | DAG Scheduler（Phase 3/4 并行） | 3 天 | 🟡 高 |
| **P4** | Loop DNA 记录器 | 2 天 | 🟢 中 |
| **P5** | Skills 封装（solution_loop 等） | 2 天 | 🟢 中 |
| **P6** | No-Progress Detection 三层级联 | 1 天 | 🟢 中 |
| **P7** | Memory-Guided Loop | 2 天 | 🔵 低 |
| **P8** | Evolutionary Loop | 2 周 | 🔵 低 |

**P0+P1 = 核心引擎（~10 天），完成后即可投入使用。**

### 报告文件索引

| 文件 | 内容 | 字数 |
|------|------|------|
| `loop_engineering_seminar_report.md` | 📋 综合研讨报告（本文件） | ~4500 |
| `loop_expert_1_architecture.md` | 🏗️ Expert 1: 系统架构（状态机+Tick+GaaS） | ~2400 |
| `loop_expert_2_toolchain.md` | 🔧 Expert 2: 工具链整合（6阶段映射+3 Pattern） | ~2200 |
| `loop_expert_3_collaboration.md` | 🧠 Expert 3: 协作模式（四角色+CMAH+ACCC） | ~2500 |
| `loop_expert_4_deepflow.md` | 🌊 Expert 4: DeepFlow 整合（Contract Bus+DNA） | ~2500 |

---

## 七、核心结论

> **"Loop Engineering 的本质不是'怎么循环'，而是'怎么定义 done'。"**

> **"循环本身必须是 Python 的（确定性），只有 phase 内部才是 LLM 的（概率性）。"**

> **"OpenClaw 的时间维度 + 分布式 Worker + 记忆复利，让它天然适合构建长时间自主 Loop。"**

---

*本报告由 4 位 AI Native 专家研讨生成，详细子报告见 `.deepflow/research/loop_expert_*.md`*
*版本: 1.0 | 字数: ~4500*
