# OpenClaw LoOP Engineering 专家研讨会报告

> **日期**: 2026-06-24
> **参与者**: 4 位 AI Native 专家（架构 / 工具链 / 协作模式 / DeepFlow 编排）
> **议题**: 在 OpenClaw 下构筑 Loop 工程的架构设计 + 与 DeepFlow 结合

---

## 一、行业背景：Loop Engineering 是什么

### 1.1 起源与定义

**Peter Steinberger** (2026.05):
> *"You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents."*

**Addy Osmani** 在 2026 年 6 月正式命名为 **Loop Engineering**。

**核心定义**: 设计一个系统，让系统代替你 prompt AI，按目标驱动、按条件检查、自动循环执行。你的角色从"每步打字的人"变成"设计执行机器的人"。

### 1.2 Loop 的 6 个组件（行业共识）

| # | 组件 | 职责 | OpenClaw 对应 |
|---|------|------|--------------|
| 1 | **Automation** | 自动触发 | ✅ cron + heartbeat |
| 2 | **Worktrees** | 隔离工作区 | ✅ sessions_spawn + base_path |
| 3 | **Skills** | 固化指令 | ✅ SKILL.md + Skill Workshop |
| 4 | **Connectors** | 外部工具 | ✅ message + exec + MCP |
| 5 | **Sub-agents** | 做查分离 | ✅ sessions_spawn 角色分离 |
| 6 | **Memory** | 持久记忆 | ✅ memory/ + MEMORY.md |

### 1.3 三大平台 Agent Loop 对比

| | OpenAI Agents SDK | Claude Agent SDK | OpenClaw |
|---|---|---|---|
| **循环机制** | `Runner.run()` while loop | turn-based agentic loop | heartbeat + cron 跨 session loop |
| **停止条件** | final_output 无 tool calls | 无 tool calls 的纯文本 | Goal Checker（确定性） |
| **工具执行** | SDK 内部 | SDK 内部 | exec / sessions_spawn |
| **上下文管理** | session history | 自动 compaction | yield + 文件系统 |
| **容错** | max_turns | max_turns + max_budget_usd | cron watcher + resume |
| **持久化** | 需外部框架 | 外部 checkpoint | 文件系统 + pipeline_state |
| **长时间运行** | ❌ 不支持 | /goal + Routines (云/付费) | ✅ 原生（cron 跨天） |

**核心发现**: OpenAI 和 Claude 的 Loop 都是**单进程内循环**。OpenClaw 有独特优势：**跨 session 的分布式循环 + 原生时间维度**。

---

## 二、专家 1：系统架构视角

### 2.1 Loop 生命周期状态机

```
                    ┌──────────┐
        trigger ──→ │   IDLE   │
                    └────┬─────┘
                         │ loop.start()
                    ┌────▼─────┐
              ┌────→│ PLANNING │──── 确定性 Python
              │     └────┬─────┘
              │          │ plan ready
              │     ┌────▼──────┐
              │     │ EXECUTING │──── LLM Worker (sessions_spawn)
              │     └────┬──────┘
              │          │ worker done
              │     ┌────▼──────┐
              │     │ CHECKING  │──── Goal Checker (确定性)
              │     └──┬────┬───┘
              │   pass │    │ fail
              │  ┌─────▼┐ ┌▼──────┐
              │  │ DONE │ │RESUME │── retry_count < max?
              │  └──────┘ └──┬────┘
              │         yes │    │ no
              │        ┌────▼┐ ┌─▼────┐
              └────────┤PLAN │ │ABORT │
                       └─────┘ └──────┘
```

**状态转换表**:

| 当前状态 | 事件 | 下一状态 | 转换逻辑 |
|---------|------|---------|---------|
| IDLE | loop.start() | PLANNING | 初始化 LoopState |
| PLANNING | plan_ready | EXECUTING | 生成 worker prompt |
| PLANNING | no_more_steps + goal_met | DONE | 所有步骤完成 |
| PLANNING | no_more_steps + !goal_met | ABORT | 无法继续 |
| EXECUTING | worker_done | CHECKING | 收集输出 |
| EXECUTING | timeout | RESUME | retry_count++ |
| CHECKING | goal_met | DONE | Goal Checker 通过 |
| CHECKING | !goal_met + progress | PLANNING | 下一轮 |
| CHECKING | !goal_met + stale×3 | ABORT | No-progress |
| RESUME | retry < max | PLANNING | 带 resume context |
| RESUME | retry ≥ max | ABORT | 超过重试上限 |

### 2.2 Tick 机制

每次 heartbeat/cron wake 时，Loop Engine 执行一次 `tick()`:

```python
class LoopEngine:
    def tick(self) -> LoopDecision:
        """
        输入: self.state (从 checkpoint 恢复)
        输出: LoopDecision {action, next_step, progress}
        """
        self.state.round += 1
        
        # 1. Budget guard
        if self.budget and self.state.spent >= self.budget:
            return LoopDecision(action="stop", reason="budget_exceeded")
        
        # 2. Max rounds guard
        if self.state.round > self.max_rounds:
            return LoopDecision(action="stop", reason="max_rounds")
        
        # 3. Goal check (确定性，非 LLM)
        goal_result = self.checker.check(self.state.context)
        if goal_result.met:
            return LoopDecision(action="done", evidence=goal_result.evidence)
        
        # 4. No-progress detection
        if goal_result.progress <= self.state.last_progress:
            self.state.stale_count += 1
            if self.state.stale_count >= 3:
                return LoopDecision(action="abort", reason="no_progress_3_rounds")
        else:
            self.state.stale_count = 0
        
        # 5. Plan next step (确定性)
        next_step = self.planner.next(self.state)
        
        # 6. Persist checkpoint
        self._save_checkpoint()
        
        return LoopDecision(
            action="continue",
            next_step=next_step,
            progress=goal_result.progress
        )
```

### 2.3 Checkpoint 设计

```python
# checkpoint.json — 每个 tick 后写入
{
  "loop_id": "loop_20260624_230000",
  "domain": "solution_pro",
  "state": "EXECUTING",
  "round": 3,
  "max_rounds": 10,
  "progress": 0.4,
  "stale_count": 0,
  "spent_usd": 0.12,
  "started_at": "2026-06-24T23:00:00+08:00",
  "last_tick_at": "2026-06-24T23:15:00+08:00",
  "completed_phases": [1, 2, 3],
  "current_phase": {
    "id": "reviewers",
    "state": "RUNNING",
    "worker_ids": ["f59a6c6f", "44f8346b"],
    "started_at": "2026-06-24T23:14:00+08:00"
  },
  "goal_checker_history": [
    {"round": 1, "progress": 0.1, "met": false},
    {"round": 2, "progress": 0.3, "met": false},
    {"round": 3, "progress": 0.4, "met": false}
  ]
}
```

**与 pipeline_state.json 的关系**: checkpoint.json 是 Loop 层的状态，pipeline_state.json 是 Domain 层的状态。Loop 读两者，写 checkpoint.json；Domain 写 pipeline_state.json。

### 2.4 创新设计

**创新 1: Temporal Loop — 跨天持续运行**

OpenClaw 独有的 cron 能力让 Loop 可以跨小时甚至跨天运行：

```python
# 场景：一个复杂的 Solution Pro 任务需要 8 小时
# 传统 SDK：进程必须保持运行 8 小时
# OpenClaw：cron 每 5 分钟唤醒一次，每次 tick 几秒

cron(action="add", job={
    "name": "loop_solution_pro_xxx",
    "schedule": {"kind": "every", "everyMs": 300000},  # 5 min
    "payload": {"kind": "agentTurn", "message": "继续 loop_xxx"},
    "sessionTarget": "session:loop_xxx",
    "delivery": {"mode": "announce"}
})
```

**创新 2: Nested Loop — 主 Loop 中触发子 Loop**

主 Loop 在 EXECUTING 阶段可以 spawn 子 Loop：
- 主 Loop: "设计一个微服务系统"
- 子 Loop 1: "深度研究消息队列"（Research Pro）
- 子 Loop 2: "深度研究服务网格"（Research Pro）
- 子 Loop 完成后主 Loop 继续

---

## 三、专家 2：工具链整合视角

### 3.1 Tool Chain Mapping

| Loop 阶段 | OpenClaw 工具 | 说明 |
|-----------|--------------|------|
| **PERCEIVE** | `exec` (读文件) + `memory_search` | 读 checkpoint + 搜索历史 |
| **PLAN** | `exec` (Python 脚本) | 确定性决策，不用 LLM |
| **ACT** | `sessions_spawn` + `sessions_yield` | spawn worker + 等待完成 |
| **OBSERVE** | `exec` (读输出文件) | 收集 worker 结果 |
| **CHECK** | `exec` (Goal Checker Python) | 确定性验证 |
| **PERSIST** | `write` (checkpoint) + `memory` | 写状态 + 更新记忆 |
| **NOTIFY** | `message` (飞书) | 进度通知 / 完成通知 |
| **RECOVER** | `cron` (定时唤醒) | 崩溃后自动恢复 |

### 3.2 Connectors 设计

```python
# connectors.py — Loop 与外部系统的桥梁
class FeishuConnector:
    """飞书通知 connector"""
    
    def on_loop_start(self, loop_id, domain, goal):
        message(action="send", channel="feishu",
                message=f"🔄 Loop 启动: {domain}\n目标: {goal}")
    
    def on_progress(self, loop_id, round_num, progress, evidence):
        # 每 3 轮通知一次，避免刷屏
        if round_num % 3 == 0:
            message(action="send", channel="feishu",
                    message=f"📊 Loop {loop_id}: Round {round_num}, "
                            f"进度 {progress:.0%}\n{evidence}")
    
    def on_done(self, loop_id, result):
        message(action="send", channel="feishu",
                message=f"✅ Loop 完成: {result.summary}")
    
    def on_abort(self, loop_id, reason):
        message(action="send", channel="feishu",
                message=f"❌ Loop 中止: {reason}")

class GitConnector:
    """Git 版本控制 connector"""
    
    def on_phase_done(self, phase_id, output_files):
        exec(command=f"cd {workdir} && git add {' '.join(output_files)} "
                     f"&& git commit -m 'loop: {phase_id} done'")
    
    def on_loop_done(self, loop_id):
        exec(command=f"cd {workdir} && git tag 'loop-{loop_id}-done'")
```

### 3.3 Skills 即 Loop 组件

将常用 Loop pattern 封装为 Skill:

```yaml
# skills/solution_loop/SKILL.md
name: solution_loop
description: 自动运行 Solution Pro 完整 Loop（10 phase + goal check + resume）

trigger:
  keywords: ["解决方案loop", "方案循环", "solution loop"]

workflow:
  1. 解析用户需求 → 生成 goal
  2. 创建 base_path + execution_plan.json
  3. 启动 Loop Engine (cron every 5min)
  4. 每轮: tick() → spawn worker → yield → check
  5. 完成: 删除 cron → 通知用户 → 写报告
  6. 失败: 通知用户 + 诊断报告
```

### 3.4 创新设计

**创新 1: Tool Chain Replay — Loop 执行回放**

每个 Loop run 自动记录完整工具调用链：
```json
{
  "loop_id": "loop_xxx",
  "tool_chain": [
    {"ts": "23:00:00", "tool": "exec", "cmd": "loop_runner.py next", "duration_ms": 120},
    {"ts": "23:00:01", "tool": "sessions_spawn", "task": "sol_data_collection", "duration_ms": 45000},
    {"ts": "23:00:46", "tool": "exec", "cmd": "goal_checker.py check", "duration_ms": 50},
    ...
  ]
}
```

事后可用 `python3 replay.py loop_xxx` 回放整个执行过程，用于调试和优化。

**创新 2: Adaptive Connector — 智能通知频率**

根据 Loop 进度和用户偏好动态调整通知频率：
- 进度 < 30%: 每 5 轮通知一次
- 进度 30-70%: 每 3 轮通知一次
- 进度 > 70%: 每轮通知（用户关心收尾）
- 异常: 立即通知

---

## 四、专家 3：Agent 协作模式视角

### 4.1 Loop 中的角色分离

| 角色 | 执行者 | 职责 | 为什么 |
|------|--------|------|--------|
| **PLANNER** | Python (确定性) | 决定下一步做什么 | LLM 循环控制 33% 成功率 |
| **DOER** | LLM Worker | 生成内容/执行任务 | LLM 擅长生成，不擅长控制 |
| **CHECKER** | Python + LLM | 验证输出质量 | Python 做结构验证，LLM 做语义验证 |
| **MEMORY** | Python (文件系统) | 持久化状态 | LLM 无持久记忆 |
| **WATCHER** | Cron (确定性) | 监控 Loop 健康 | 不能依赖被监控者自我监控 |

**核心原则**: **LLM 只做生成，Python 做所有决策。** 这是从 33% 成功率教训中提炼的铁律。

### 4.2 Reflexion 在 Loop 中的应用

每个 phase 完成后，CHECKER 执行 Reflexion:

```python
class ReflexionChecker:
    def check(self, phase_output, phase_goal):
        # Step 1: 结构验证 (Python, 确定性)
        structural_ok = self._check_structure(phase_output)
        if not structural_ok:
            return CheckResult(passed=False, feedback="结构不完整，缺少: ...")
        
        # Step 2: 语义验证 (LLM, 仅当结构通过时)
        semantic_result = self._llm_evaluate(phase_output, phase_goal)
        if semantic_result.score < 0.7:
            return CheckResult(
                passed=False,
                feedback=semantic_result.feedback,
                improvement_hints=semantic_result.hints
            )
        
        return CheckResult(passed=True, score=semantic_result.score)
    
    def _llm_evaluate(self, output, goal):
        """用独立 LLM 评估，不是 DOER 自己评估自己"""
        prompt = f"""
        你是一个严格的质量评审员。
        
        目标: {goal}
        输出: {output[:3000]}
        
        评分 (0-1): 输出是否满足目标？
        反馈: 如果不满足，具体缺什么？
        改进建议: 下一轮应该重点改进什么？
        
        输出 JSON: {{"score": 0.x, "feedback": "...", "hints": "..."}}
        """
        # 使用 sessions_spawn 创建独立评审 Agent
        # 避免 DOER 自评的确认偏误
        ...
```

**关键**: CHECKER 和 DOER 必须是**不同的 LLM 调用**，避免"运动员当裁判"。

### 4.3 Anti-Context-Rot 策略

长时间 Loop 的上下文退化对抗：

```
┌─────────────────────────────────────────────────┐
│           Anti-Context-Rot 三层策略               │
│                                                 │
│  Layer 1: 隔离 (每轮新 session)                  │
│  ├─ Worker 每次 sessions_spawn 新 session        │
│  ├─ 不携带历史上下文                              │
│  └─ 只传入: 当前 phase prompt + 前置输出摘要      │
│                                                 │
│  Layer 2: 压缩 (checkpoint 摘要)                 │
│  ├─ 每轮 checkpoint 只存结构化数据                │
│  ├─ 不存完整 LLM 输出                             │
│  └─ 下一轮从 checkpoint 重建最小上下文             │
│                                                 │
│  Layer 3: 锚定 (goal 不变)                       │
│  ├─ Goal 定义写入文件，每轮重新读取                │
│  ├─ 不依赖 LLM "记住" 目标                       │
│  └─ 每轮 prompt 开头: "你的目标是: {goal}"        │
└─────────────────────────────────────────────────┘
```

### 4.4 No-Progress Detection

三种检测方法，由简到严：

| 方法 | 机制 | 适用场景 |
|------|------|---------|
| **Progress Float** | `checker.check()` 返回 0.0-1.0 进度值 | 可量化的任务 |
| **Output Delta** | 对比本轮和上轮的输出文件 hash | 文件生成类任务 |
| **Stale Counter** | 连续 3 轮 progress 无增长 → abort | 所有任务（兜底） |

```python
def detect_no_progress(state: LoopState) -> bool:
    """返回 True = 卡住了"""
    if state.round < 3:
        return False  # 前 3 轮不检测
    
    # Method 1: Progress float
    if state.progress_history[-1] > state.progress_history[-3]:
        return False
    
    # Method 2: Output delta
    current_hash = hash_files(state.output_dir)
    if current_hash != state.last_output_hash:
        return False
    
    # Method 3: Stale counter
    state.stale_count += 1
    return state.stale_count >= 3
```

### 4.5 创新设计

**创新 1: Loop DNA — 执行基因图谱**

每个 Loop run 生成一个"DNA"指纹，用于事后分析和持续改进：

```python
class LoopDNA:
    """Loop 执行的完整基因图谱"""
    
    def __init__(self):
        self.genes = []  # 每个 tick 一个 gene
    
    def add_gene(self, tick_num, phase, worker_model, 
                 prompt_hash, output_hash, gate_result, duration):
        self.genes.append({
            "tick": tick_num,
            "phase": phase,
            "model": worker_model,
            "prompt_hash": prompt_hash,  # 同样的 prompt = 同样的 hash
            "output_hash": output_hash,
            "gate": gate_result,
            "duration_s": duration,
            "tokens": {"input": 0, "output": 0},
        })
    
    def fingerprint(self) -> str:
        """生成可比较的指纹"""
        gene_strs = [f"{g['phase']}:{g['gate']}:{g['duration_s']}" 
                     for g in self.genes]
        return "|".join(gene_strs)
    
    def compare(self, other: 'LoopDNA') -> dict:
        """比较两次 run 的差异"""
        # 哪些 phase 耗时差异最大？
        # 哪些 phase 的 gate 结果不同？
        # 同样的 prompt_hash 是否产生不同的 output_hash？
        ...
```

**用途**:
- 同类任务的 Loop DNA 对比 → 发现哪次 run 效率更高
- prompt_hash 相同但 output_hash 不同 → 模型不稳定性检测
- gate_result 全 pass 但最终 goal 未达 → Goal Checker 设计有缺陷

**创新 2: Meta-Loop — 自我进化循环**

```
Loop Run 1 → DNA → 分析瓶颈
                    ↓
            优化 prompt/phase 定义
                    ↓
Loop Run 2 → DNA → 对比 Run 1
                    ↓
            确认改进有效？
              ↓ yes          ↓ no
            固化改进       回滚
```

每次 Loop 运行数据自动写入 `memory/loop_runs/`:
```json
{
  "loop_id": "xxx",
  "domain": "solution_pro",
  "goal": "设计微服务系统",
  "dna_fingerprint": "dc:pass:45|pl:pass:120|rv:pass:180|...",
  "total_rounds": 7,
  "total_duration_min": 35,
  "total_tokens": 125000,
  "goal_met": true,
  "bottleneck_phase": "reviewers",  // 耗时最长
  "retry_phases": ["research"],     // 需要重试的
  "prompt_hashes": {"dc": "abc123", "pl": "def456", ...}
}
```

定期分析所有 loop runs → 自动识别 pattern → 优化 Skill/Prompt。

---

## 五、专家 4：DeepFlow 多域编排视角

### 5.1 跨域 Meta-Loop

```
┌──────────────────────────────────────────────────────┐
│                DeepFlow Meta-Loop                     │
│                                                      │
│  ┌──────────┐    ┌───────────┐    ┌──────────┐      │
│  │ Spec Pro │───→│ Solution  │───→│ Ship Pro │      │
│  │  (6p)    │    │  (10p)    │    │  (5p)    │      │
│  └──────────┘    └───────────┘    └──────────┘      │
│       ↑                                  │           │
│       │          ┌───────────┐           │           │
│       └──────────│ Research  │◄──────────┘           │
│       (需求不清) │  (N p)    │ (需要深度研究)         │
│                  └───────────┘                       │
│                                                      │
│  Meta-Loop 规则:                                      │
│  1. Spec Pro done → auto Solution Pro                │
│  2. Solution Pro done → auto Ship Pro                │
│  3. Ship Pro reviewer 发现需求不清 → 回环 Spec Pro    │
│  4. 任意域需要深度研究 → spawn Research Pro           │
│  5. 所有域 goal met → Meta-Loop done                 │
└──────────────────────────────────────────────────────┘
```

**Meta-Loop Engine**:

```python
class MetaLoopEngine:
    """跨域编排引擎"""
    
    DOMAIN_ORDER = ["spec_pro", "solution_pro", "ship_pro"]
    
    def tick(self):
        current_domain = self.state.current_domain
        
        # 当前域的 Goal Checker
        domain_checker = self.get_checker(current_domain)
        result = domain_checker.check(self.state.context)
        
        if result.met:
            # 当前域完成，推进到下一个域
            next_domain = self._next_domain(current_domain)
            if next_domain:
                self.state.current_domain = next_domain
                return LoopDecision(action="continue", 
                                    next_step=f"start_{next_domain}")
            else:
                return LoopDecision(action="done", 
                                    reason="all domains completed")
        
        if result.needs_research:
            # 需要深度研究，spawn Research Pro 子 Loop
            return LoopDecision(action="spawn_sub_loop",
                                sub_loop="research_pro",
                                reason=result.research_question)
        
        if result.needs_spec_clarification:
            # Ship Pro 发现需求不清，回环到 Spec Pro
            self.state.current_domain = "spec_pro"
            self.state.spec_clarification_needed = result.questions
            return LoopDecision(action="continue",
                                next_step="spec_clarification")
        
        # 当前域未完成，继续执行
        next_step = self.domain_engine.next(current_domain)
        return LoopDecision(action="continue", next_step=next_step)
```

### 5.2 Domain-Specific Goal Checkers

```python
# goal_checkers.py

class SpecProChecker(GoalChecker):
    """Spec Pro 完成标准"""
    def check(self, ctx):
        spec = load_json(ctx.base_path / "spec/living_spec.json")
        trajectory = load_json(ctx.base_path / "spec/quality_trajectory.json")
        
        # 1. living_spec.json 存在且通过 schema
        if not spec or not validate_schema(spec):
            return GoalResult(met=False, progress=0.2, 
                            evidence="living_spec.json missing or invalid")
        
        # 2. harness_result.json 存在且 score ≥ 0.8
        harness = load_json(ctx.base_path / "spec/harness_result.json")
        if not harness:
            return GoalResult(met=False, progress=0.5,
                            evidence="harness not run yet")
        
        score = harness.get("overall_score", 0)
        if score < 0.8:
            return GoalResult(met=False, progress=0.7,
                            evidence=f"harness score {score:.1f} < 0.8")
        
        return GoalResult(met=True, progress=1.0,
                         evidence=f"harness score {score:.1f} ≥ 0.8")


class SolutionProChecker(GoalChecker):
    """Solution Pro 完成标准"""
    def check(self, ctx):
        final = load_json(ctx.base_path / "stages/final_result.json")
        if not final:
            # 计算已完成 phase 比例
            completed = count_completed_phases(ctx)
            return GoalResult(met=False, progress=completed / 10.0,
                            evidence=f"{completed}/10 phases done")
        
        quality = final.get("quality_score", 0)
        if quality < 0.85:
            return GoalResult(met=False, progress=0.9,
                            evidence=f"quality {quality:.2f} < 0.85")
        
        return GoalResult(met=True, progress=1.0,
                         evidence=f"quality {quality:.2f} ≥ 0.85")


class ShipProChecker(GoalChecker):
    """Ship Pro 完成标准"""
    def check(self, ctx):
        package = load_json(ctx.base_path / "blackboard/ship_package.json")
        if not package:
            return GoalResult(met=False, progress=0.5,
                            evidence="ship_package.json not found")
        
        # 5 个 gate 全部通过
        gates = ["architect", "decomposer", "specifier", "reviewer", "packager"]
        passed = sum(1 for g in gates if gate_passed(ctx, g))
        
        if passed < len(gates):
            return GoalResult(met=False, progress=passed / len(gates),
                            evidence=f"{passed}/{len(gates)} gates passed")
        
        return GoalResult(met=True, progress=1.0,
                         evidence="all 5 gates passed")
```

### 5.3 Phase State Machine（域内升级）

```python
class PhaseState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    GATE_CHECKING = "gate_checking"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"

TRANSITIONS = {
    (PENDING, "start"): RUNNING,
    (RUNNING, "worker_done"): GATE_CHECKING,
    (RUNNING, "timeout"): FAILED,
    (RUNNING, "worker_error"): FAILED,
    (GATE_CHECKING, "gate_pass"): DONE,
    (GATE_CHECKING, "gate_fail"): RETRYING,
    (GATE_CHECKING, "gate_conditional"): DONE,
    (RETRYING, "retry_start"): RUNNING,
    (RETRYING, "max_retries"): FAILED,
    (FAILED, "skip"): SKIPPED,
}

class PhaseRunner:
    """替代 loop_runner.py 的模糊文件匹配"""
    
    def advance(self, phase_id: str) -> PhaseDecision:
        phase = self.state.phases[phase_id]
        
        if phase.state == PENDING:
            # 检查依赖是否满足 (DAG)
            deps = self.dag.get_dependencies(phase_id)
            if all(self.state.phases[d].state == DONE for d in deps):
                return PhaseDecision(action="start", phase=phase_id)
            else:
                return PhaseDecision(action="wait", 
                                    reason=f"waiting for: {deps}")
        
        if phase.state == RUNNING:
            # 检查 worker 是否完成
            if self._workers_done(phase):
                return PhaseDecision(action="gate_check", phase=phase_id)
            elif self._timeout(phase):
                return PhaseDecision(action="timeout", phase=phase_id)
            else:
                return PhaseDecision(action="wait", reason="workers running")
        
        # ... 其他状态转换
```

### 5.4 创新设计

**创新 1: Evolutionary Loop — 进化式 Loop**

```
Loop Run 1 (prompt_v1) → DNA → score: 0.72
                                    ↓
                    分析: Phase 3(research) 质量最低
                    优化: 用 LLM 重写 Phase 3 prompt
                                    ↓
Loop Run 2 (prompt_v2) → DNA → score: 0.85
                                    ↓
                    确认: Phase 3 质量提升 18%
                    固化: prompt_v2 → skills/
```

```python
class EvolutionaryLoop:
    """Loop 运行数据自动优化 phase prompts"""
    
    def analyze_run(self, loop_dna: LoopDNA):
        # 找到质量最低的 phase
        weakest = min(loop_dna.genes, key=lambda g: g.get("quality", 1.0))
        
        # 生成改进建议
        improvement_prompt = f"""
        Phase: {weakest['phase']}
        当前 prompt hash: {weakest['prompt_hash']}
        质量分: {weakest.get('quality', 'N/A')}
        耗时: {weakest['duration_s']}s
        
        请分析这个 phase 的输出，提出 prompt 改进建议。
        """
        
        # spawn 分析 Agent
        analysis = sessions_spawn(task=improvement_prompt)
        
        # 生成改进版 prompt
        new_prompt = self._generate_improved_prompt(
            weakest['phase'], analysis)
        
        # A/B 测试：下一轮用新 prompt
        self.prompt_versions[weakest['phase']]['v2'] = new_prompt
    
    def compare_versions(self, phase_id, v1_dna, v2_dna):
        """对比两个 prompt 版本的效果"""
        v1_quality = v1_dna.get_phase_quality(phase_id)
        v2_quality = v2_dna.get_phase_quality(phase_id)
        
        if v2_quality > v1_quality * 1.1:  # 至少 10% 提升
            return "promote_v2"  # 固化新版
        elif v2_quality < v1_quality * 0.9:  # 退步 10%
            return "rollback"  # 回滚
        else:
            return "keep_both"  # 差异不显著
```

**创新 2: Loop Marketplace — 可分享的 Loop 模板**

```yaml
# Loop 模板市场（基于 Skill Workshop）
templates:
  - name: "solution_loop_basic"
    description: "Solution Pro 基础 Loop（10 phase，goal: quality ≥ 0.85）"
    phases: 10
    estimated_time: "30-60 min"
    goal_checker: "SolutionProChecker(threshold=0.85)"
    
  - name: "solution_loop_thorough"
    description: "Solution Pro 深度 Loop（含 Reflexion，goal: quality ≥ 0.95）"
    phases: 10 + 3 reflexion rounds
    estimated_time: "60-120 min"
    goal_checker: "SolutionProChecker(threshold=0.95) + ReflexionChecker"
    
  - name: "full_pipeline_loop"
    description: "完整 3 域 Loop（Spec → Solution → Ship）"
    phases: 6 + 10 + 5
    estimated_time: "2-4 hours"
    goal_checker: "MetaLoopChecker(all_domains_met)"
```

用户可以通过 Skill Workshop 安装 Loop 模板，就像安装 Skill 一样。

---

## 六、综合架构设计

### 6.1 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                    OpenClaw LoOP Engine                       │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐     │
│  │ Meta-Loop   │  │  Loop Engine │  │  Goal Checkers  │     │
│  │ (跨域编排)  │──│  (tick/状态) │──│  (确定性验证)   │     │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘     │
│         │                │                    │              │
│  ┌──────▼──────────────▼────────────────────▼──────────┐   │
│  │              Phase State Machine                      │   │
│  │  PENDING → RUNNING → GATE_CHECKING → DONE/RETRYING  │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              Worker Execution Layer                    │   │
│  │  sessions_spawn → worker prompt → sessions_yield     │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              Persistence Layer                         │   │
│  │  checkpoint.json + pipeline_state.json + Loop DNA    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Connectors Layer                          │   │
│  │  Feishu | Git | Memory | Skill Workshop              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              DeepFlow Integration                      │   │
│  │  Spec Pro | Solution Pro | Ship Pro | Research Pro   │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 文件结构

```
.deepflow/
├── loop_engine/                    # 新建: LoOP 核心引擎
│   ├── __init__.py
│   ├── engine.py                   # LoopEngine (tick/状态机)
│   ├── checkpoint.py               # Checkpoint 管理
│   ├── goal_checkers/              # Goal Checker 注册表
│   │   ├── __init__.py
│   │   ├── base.py                 # GoalChecker 基类
│   │   ├── spec_pro.py
│   │   ├── solution_pro.py
│   │   ├── ship_pro.py
│   │   └── meta.py                 # MetaLoopChecker (跨域)
│   ├── connectors/                 # 外部系统连接器
│   │   ├── feishu.py
│   │   ├── git.py
│   │   └── memory.py
│   ├── dna.py                      # Loop DNA 指纹
│   └── evolution.py                # Evolutionary Loop
│
├── loop_runner.py                  # 已有: 保留，作为 Phase Runner
├── domains/
│   ├── spec_pro/
│   │   ├── phases.yaml             # 新建: 声明式 phase 定义
│   │   └── ...
│   ├── solution_pro/
│   │   ├── phases.yaml
│   │   └── ...
│   └── ship_pro/
│       ├── phases.yaml
│       └── ...
│
├── loop_templates/                 # 新建: Loop 模板
│   ├── solution_basic.yaml
│   ├── solution_thorough.yaml
│   └── full_pipeline.yaml
│
└── loop_runs/                      # 新建: Loop 运行记录
    └── loop_20260624_xxx/
        ├── checkpoint.json
        ├── dna.json
        └── events.jsonl
```

### 6.3 实施路径

| Phase | 内容 | 工作量 | 优先级 |
|-------|------|--------|--------|
| **P1** | Goal Checker 基类 + 3 域 Checker | 4h | 🔴 最高 |
| **P2** | Loop Engine (tick + checkpoint + 状态机) | 6h | 🔴 最高 |
| **P3** | Phase State Machine (替代模糊文件匹配) | 4h | 🟡 高 |
| **P4** | Meta-Loop (跨域编排) | 4h | 🟡 高 |
| **P5** | Connectors (飞书 + Git + Memory) | 3h | 🟢 中 |
| **P6** | Loop DNA + Evolutionary Loop | 4h | 🟢 中 |
| **P7** | Loop Templates + Skill 封装 | 3h | 🔵 低 |
| **总计** | | **~28h** | |

### 6.4 与现有系统的关系

```
现有 loop_runner.py  →  保留，重命名为 phase_runner.py
                        职责：单域内的 phase 推进

新建 loop_engine/    →  Loop 层
                        职责：跨域编排 + Goal 验证 + 状态管理

现有 pipeline_state  →  保留
                        Loop Engine 读取但不写入
                        Loop 有自己的 checkpoint.json

现有 Watcher Cron    →  保留，扩展
                        除了通知用户，还驱动 Loop tick
```

---

## 七、核心结论

### 7.1 五大设计原则

1. **LLM 只做生成，Python 做所有决策** — 从 33% 成功率教训中提炼的铁律
2. **Goal Checker 是 Loop 的灵魂** — "如果你说不清 done 长什么样，你没有 loop，你有个愿望"
3. **Checkpoint 不是文件匹配** — 结构化 checkpoint.json + phase state machine
4. **OpenClaw 的独特优势是时间维度** — cron/heartbeat 让 Loop 可以跨小时甚至跨天运行
5. **Loop 应该可进化** — DNA 指纹 + Evolutionary Loop 让系统自我改进

### 7.2 三个核心创新

1. **Temporal Loop**: 利用 OpenClaw cron 实现跨天持续运行（OpenAI/Claude 做不到）
2. **Loop DNA + Evolutionary Loop**: 每次运行生成基因图谱，自动优化 prompt（业界首创）
3. **Nested Meta-Loop**: 4 域自动编排 + 回环机制 + 子 Loop spawn（DeepFlow 独有）

### 7.3 一句话总结

> **OpenClaw LoOP = 确定性状态机引擎 + Goal Checker + Checkpoint + 跨 session 分布式执行 + 时间维度（cron）。LLM 只是 Loop 中的 Worker，不是 Loop 的驾驶员。**

---

*报告由 4 位 AI Native 专家研讨生成，2026-06-24*
