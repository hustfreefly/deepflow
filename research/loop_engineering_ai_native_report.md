# OpenClaw LoOP Engineering — AI Native 专家研讨会报告

> **日期**: 2026-06-25
> **议题**: 以 AI Native 思维重新设计 OpenClaw Loop 工程
> **核心纠偏**: ~~"LLM 只做生成，Python 做决策"~~ → **"给 AI 更好的上下文、工具和反馈，让它可靠地做决策"**

---

## 〇、纠偏：为什么"Python 做决策"不是 AI Native

### 错误思维链
```
33% 成功率 → "LLM 不适合循环控制" → "用 Python 状态机替代"
```
这是**把糟糕的架构设计归咎于 AI 能力**。

### 正确的 AI Native 诊断
```
33% 成功率 → 根因是什么？
  ├─ Prompt 80K tokens → 注意力分散 → Context Engineering 问题
  ├─ 无进度反馈 → LLM 不知道哪些 phase 已完成 → Tool Design 问题
  ├─ 无预算/超时 → 无 guard rails → Harness Design 问题
  └─ 失败后只能重头开始 → Recovery 问题
  
修复方向：给 LLM 更好的驾驶舱，不是抢走方向盘。
```

### 类比
飞行员（LLM）遇到恶劣天气表现不好 → 
- ❌ 防御式：把飞行员换成自动驾驶（剥夺决策权）
- ✅ AI native：给飞行员更好的雷达、仪表、空管支持（增强能力）

---

## 一、专家 1：AI Native Loop Architect

### 1.1 33% 成功率的 AI Native 修复方向

| 根因 | 防御式修复（❌） | AI Native 修复（✅） |
|------|-----------------|-------------------|
| Prompt 80K tokens 注意力分散 | 不让 LLM 做循环控制 | **Compaction**: LLM 每轮总结当前状态，只传摘要 |
| LLM 不知道已完成哪些 phase | Python 文件匹配检查 | **结构化状态工具**: `loop_status()` 返回清晰的 JSON |
| LLM 中途停止 | Python 循环替代 | **Goal + Judge**: 给 LLM 明确 goal，AI judge 判断是否 done |
| 无预算控制 | 无 | **Guard Rails**: max_turns + max_budget + 超时 |
| 失败后重头开始 | resume-prompt（又是求 LLM） | **Checkpoint + 恢复工具**: LLM 可以从断点继续 |

### 1.2 AI-Driven Loop Control 架构

```
┌──────────────────────────────────────────────────────────┐
│                    AI Native Loop                         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Loop Harness（驾驶舱）                │    │
│  │                                                    │    │
│  │  ┌─────────┐  ┌─────────┐  ┌──────────┐          │    │
│  │  │ Context │  │  Tools  │  │Feedback  │          │    │
│  │  │ Manager │  │  Layer  │  │  Loop    │          │    │
│  │  └────┬────┘  └────┬────┘  └────┬─────┘          │    │
│  │       │            │            │                  │    │
│  │       └────────────▼────────────┘                  │    │
│  │                  │                                  │    │
│  │            ┌─────▼─────┐                           │    │
│  │            │   LLM     │  ← 驾驶员（做决策）       │    │
│  │            │  Agent    │                           │    │
│  │            └─────┬─────┘                           │    │
│  │                  │                                  │    │
│  │       ┌──────────▼──────────┐                      │    │
│  │       │   Guard Rails       │  ← 安全边界          │    │
│  │       │ (budget/timeout/    │                      │    │
│  │       │  safety checks)     │                      │    │
│  │       └─────────────────────┘                      │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Goal Definition（自然语言）           │    │
│  │  "ship_package.json 通过所有 5 个 gate，           │    │
│  │   quality_score ≥ 0.85，无 P0 问题"               │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │              AI Judge（验证目标）                   │    │
│  │  每轮检查: 当前状态是否满足 goal？                  │    │
│  │  → 满足 → 停止                                    │    │
│  │  → 不满足 → 继续 + 反馈进度                       │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 1.3 Goal 定义范式（AI Native）

**不是 Python checker 函数，是 AI 可理解的自然语言 goal：**

```python
# ❌ 防御式：Python checker
class SolutionProChecker:
    def check(self, ctx):
        final = load_json("final_result.json")
        return final and final.get("quality_score", 0) >= 0.85

# ✅ AI Native：自然语言 Goal + AI Judge
GOAL = """
Solution Pro 管线完成标准：
1. final_result.json 存在于 stages/ 目录
2. quality_score 字段 ≥ 0.85
3. 所有 10 个 phase 的输出文件都存在
4. 无 P0 级问题（audit.json 中 critical_failures 为空）

请检查当前状态，判断是否满足以上所有条件。
如果全部满足，输出 {"done": true, "evidence": "..."}
如果部分满足，输出 {"done": false, "progress": 0.x, "missing": [...]}
"""
```

### 1.4 Loop Harness 设计（AI Native）

```python
# loop_harness.py — 不是控制 LLM，是赋能 LLM

class LoopHarness:
    """
    给 LLM 一个驾驶舱：
    - 仪表盘：当前状态（结构化、清晰）
    - 导航：目标定义（自然语言）
    - 通信：反馈循环（每次行动后即时反馈）
    - 安全带：Guard rails（预算、超时、安全检查）
    """
    
    def build_turn_prompt(self, goal: str, state_summary: str, 
                          available_tools: list) -> str:
        """每轮给 LLM 的 prompt — 上下文精炼，不是 80K 轰炸"""
        return f"""
# 当前任务目标
{goal}

# 当前状态（AI 总结的精炼摘要）
{state_summary}

# 你可以使用的工具
{format_tools(available_tools)}

# 请决定下一步行动
1. 调用工具执行具体工作
2. 如果认为目标已达成，输出 DONE + 证据
3. 如果遇到无法解决的问题，输出 BLOCKED + 原因

你的决定？
"""
    
    def build_state_summary(self, checkpoint: dict) -> str:
        """用 LLM 总结状态，不是 80K 原始数据"""
        # 关键：这个摘要本身也是 LLM 生成的
        # 不是 Python 拼字符串
        ...
    
    def apply_guard_rails(self, action: dict) -> dict:
        """Guard rails 是建议性的，不是控制性的"""
        if self.budget_exceeded():
            return {"blocked": True, "reason": "budget exceeded",
                    "suggestion": "wrap up current work"}
        if self.timeout_approaching():
            return {"warning": True, "message": "5 minutes remaining",
                    "suggestion": "prioritize remaining tasks"}
        return action  # 通过
```

### 1.5 创新设计

**创新 1: Self-Healing Loop — 自我修复的循环**

```
LLM 执行 action → 失败
  ↓
Harness 反馈: "action failed: {error}. Here are 3 possible fixes: ..."
  ↓
LLM 分析错误 + 选择修复策略
  ↓
LLM 执行修复 → 成功 → 继续
                → 失败 → LLM 尝试下一个修复策略
                          → 3 次都失败 → LLM 决定求助人类
```

关键：修复策略不是预定义的 if/else，是 **LLM 根据错误信息推理出来的**。

**创新 2: Adaptive Phase Discovery — AI 发现最优执行路径**

```
不给 LLM 固定的 phase 列表
给 LLM 一个 "phase menu"（可选动作菜单）

LLM 根据任务特征选择路径：
- 简单任务: [collect → plan → execute → verify] (4 phases)
- 复杂任务: [collect → research → plan → review → execute → 
             fix → re-review → verify] (8 phases)
- 紧急任务: [plan → execute → quick-verify] (3 phases)

LLM 自己决定需要哪些 phases，不是预定义的 DAG。
```

---

## 二、专家 2：Claude Code / Codex 内部机制研究者

### 2.1 Claude Code /goal 在 OpenClaw 的实现

**Claude Code /goal 核心机制**：
1. 用户给出自然语言 goal
2. Agent 自主执行（调工具、写代码、运行测试）
3. 每次 turn 后，小型 LLM judge 检查 goal 是否满足
4. 满足 → 自动停止；不满足 → 继续

**OpenClaw 实现**：

```python
# openclaw_goal.py — /goal 模式的 OpenClaw 版

class OpenClawGoal:
    """
    在 OpenClaw 中实现 /goal 机制
    
    核心：两个 LLM 角色
    - DOER: 主 Agent，执行任务
    - JUDGE: 小型 LLM，判断 goal 是否满足
    """
    
    def __init__(self, goal_text: str, session_key: str):
        self.goal = goal_text
        self.session = session_key
    
    def judge_prompt(self, current_state: str) -> str:
        """给 Judge LLM 的 prompt"""
        return f"""
你是一个严格的目标验证器。

## 目标
{self.goal}

## 当前状态
{current_state}

## 你的任务
逐条检查目标中的每个条件：
1. 条件是否满足？(yes/no)
2. 如果 no，还差什么？

输出 JSON:
{{
  "met": true/false,
  "conditions": [
    {{"name": "条件名", "met": true/false, "detail": "..."}}
  ],
  "progress": 0.0-1.0,
  "next_action_hint": "如果未完成，建议下一步做什么"
}}

注意：你只做判断，不做执行。
"""
    
    def run_judge(self, current_state: str) -> dict:
        """用 sessions_spawn 创建 Judge Agent"""
        # 关键：Judge 是独立的 LLM 调用
        # 不是 DOER 自己评估自己（避免确认偏误）
        judge_result = sessions_spawn(
            task=self.judge_prompt(current_state),
            mode="run",
            runtime="subagent",
            model="fast_model"  # Judge 用小模型即可
        )
        return parse_json(judge_result)
```

### 2.2 Compaction 在 OpenClaw 的实现

**问题**：长 Loop（10+ turns）上下文接近 window 上限
**Claude Code 方案**：自动触发 compaction，LLM 总结历史

```python
# compaction.py — AI-driven 上下文压缩

class ContextCompaction:
    """
    当上下文接近 window 限制时：
    1. LLM 总结之前的所有 turns
    2. 保留关键状态和决策
    3. 用摘要替换完整历史
    4. 继续执行，不丢失上下文
    """
    
    def compact_prompt(self, history: list, goal: str) -> str:
        """给 LLM 的 compaction prompt"""
        return f"""
请总结以下执行历史，保留：
1. 已完成的工作和结果
2. 关键决策和原因
3. 当前进行中的任务
4. 尚未解决的问题
5. 与目标的关系

目标: {goal}

历史:
{format_history(history)}

输出一份结构化摘要（≤ 2000 字），确保下一轮执行的 Agent 
可以仅凭此摘要继续工作，不需要完整历史。
"""
    
    def should_compact(self, context_tokens: int, max_tokens: int) -> bool:
        """当上下文使用超过 70% 时触发"""
        return context_tokens > max_tokens * 0.7
    
    def compact(self, history: list, goal: str) -> str:
        """执行 compaction"""
        summary = sessions_spawn(
            task=self.compact_prompt(history, goal),
            mode="run"
        )
        return summary
```

### 2.3 Hooks 在 OpenClaw 的实现

**不是代码拦截点，是 AI-driven 的检查点：**

```python
# hooks.py — AI-driven 拦截点

class AIHook:
    """
    Hook 不是 if/else 规则
    Hook 是 AI judge 快速检查
    """
    
    def pre_action_hook(self, action: dict, context: str) -> dict:
        """行动前：快速 AI 检查是否合理"""
        check_prompt = f"""
快速检查（1 句话回答）：
即将执行的动作是否合理？有没有明显的风险？

动作: {json.dumps(action, ensure_ascii=False)}
上下文: {context[:1000]}

输出: {{"ok": true/false, "concern": "如有问题说明"}}
"""
        result = quick_llm_call(check_prompt)  # 小模型，<1s
        if not result["ok"]:
            action["warning"] = result["concern"]
        return action
    
    def post_action_hook(self, action: dict, result: dict) -> dict:
        """行动后：快速 AI 检查结果质量"""
        check_prompt = f"""
快速检查（1 句话回答）：
执行结果是否符合预期？有没有异常？

动作: {action['type']}
结果摘要: {str(result)[:500]}

输出: {{"ok": true/false, "issue": "如有问题说明"}}
"""
        check = quick_llm_call(check_prompt)
        if not check["ok"]:
            result["flag"] = check["issue"]
        return result
```

### 2.4 让主 Agent 成为可靠的 Loop 驾驶员

**33% 成功率的真正修复**：

```python
# 给主 Agent 更好的"驾驶舱"

ENHANCED_LOOP_PROMPT = """
# 你的角色
你是一个管线执行驾驶员。你的任务是驱动管线从开始到完成。

# 目标
{goal}

# 你的仪表盘（当前状态）
{structured_state}  ← 关键：结构化、清晰、精炼

# 你的操纵杆（可用工具）
- loop_status(): 查看当前管线状态
- spawn_worker(phase, task): 启动一个 worker 执行具体工作
- check_output(phase): 检查 worker 的输出
- mark_done(phase): 标记某个 phase 完成
- report_progress(): 向用户报告进度

# 你的导航（执行建议）
- 当前应该执行: Phase {next_phase} ({phase_name})
- 已完成的 phases: {completed}
- 还需要做的: {remaining}

# 规则
1. 每次只执行一个 phase（或并行 phases）
2. 执行后必须 check_output 确认结果
3. 确认 OK 后 mark_done
4. 所有 phases 完成后，报告 DONE + 证据
5. 遇到无法解决的问题，报告 BLOCKED + 原因
"""
```

**关键改进**：
- **结构化状态**（不是让 LLM 去翻文件系统）
- **明确的工具列表**（不是隐式的 exec）
- **导航建议**（不是让 LLM 自己猜下一步）
- **清晰的完成条件**（不是模糊的"执行完所有 phase"）

### 2.5 创新设计

**创新: Semantic Checkpoint — AI 驱动的断点恢复**

```
传统 checkpoint: 保存精确状态 → 从精确断点恢复
Semantic checkpoint: LLM 总结"我做到哪了" → 从语义理解恢复

好处：
- 不依赖精确的文件状态
- 可以处理"部分完成"的情况
- 恢复时 LLM 可以理解上下文并灵活继续

实现：
1. 每轮结束: LLM 生成 progress_summary（自然语言）
2. 写入 checkpoint.md（不是 JSON，是 Markdown）
3. 恢复时: 读取 checkpoint.md → LLM 理解并继续

checkpoint.md 示例：
---
## 进度总结 (Round 3)
已完成: data_collection(✅), planning(✅), reviewers(✅ 3/3通过)
进行中: research (2/3 完成, expert_3 超时失败)
下一步: 重新 spawn expert_3，然后继续 consolidator
阻塞: 无
关键发现: expert_1 发现了 3 个竞品方案值得参考
---
```

---

## 三、专家 3：Emergent AI 系统设计师

### 3.1 Emergent Loop 架构

**不是预定义 phase 顺序，是 AI 动态决定执行路径：**

```yaml
# phases_menu.yaml — 不是 script，是 menu
# AI 根据任务特征从中选择需要的 phases

phases_menu:
  # 基础 phases（大多数任务都需要）
  - id: understand
    description: "理解需求，澄清模糊点"
    when: "always"
    
  - id: plan
    description: "制定执行计划"
    when: "always"
    
  - id: execute
    description: "执行核心工作"
    when: "always"
    
  - id: verify
    description: "验证结果质量"
    when: "always"
    
  # 可选 phases（AI 判断是否需要）
  - id: research
    description: "深度研究相关技术和方案"
    when: "任务涉及不熟悉的领域"
    
  - id: review
    description: "多角度评审"
    when: "输出质量要求高"
    
  - id: fix
    description: "根据评审修复问题"
    when: "review 发现了问题"
    
  - id: benchmark
    description: "与竞品/标杆对比"
    when: "需要了解市场定位"
```

**AI 路径选择**：

```python
ROUTE_PROMPT = """
你是一个管线规划师。

## 任务
{user_request}

## 可选的执行阶段（Menu）
{phases_menu}

## 你的任务
根据任务的复杂度和特征，选择需要的 phases 并排序。

示例输出：
```json
{
  "selected_phases": ["understand", "research", "plan", "execute", "review", "fix", "verify"],
  "reasoning": "这是一个复杂的分布式系统设计，需要先研究现有方案，执行后需要评审",
  "estimated_rounds": 7,
  "parallel_groups": [["review", "benchmark"]]
}
```

简单任务可能只需要 3-4 个 phases，复杂任务可能需要 8-10 个。
"""
```

### 3.2 Agent 间动态协作

**不是预定义的输入/输出管道，是 Agent 间自由通信：**

```python
# dynamic_collaboration.py

class DynamicCollaboration:
    """
    Worker 在执行过程中可以：
    1. 请求主 Agent spawn 一个 helper
    2. 向其他 worker 提问
    3. 请求评审自己的中间输出
    """
    
    WORKER_PROMPT_ADDENDUM = """
# 协作能力
在执行任务过程中，如果你需要帮助，可以输出以下指令：

NEED_HELPER: {topic, reason}
  → 主 Agent 会 spawn 一个专家来帮你

NEED_REVIEW: {output_snippet}
  → 主 Agent 会 spawn 一个评审者检查你的中间输出

NEED_INFO: {question}
  → 主 Agent 会搜索或询问答案

你不需要独自解决所有问题。寻求帮助是高效的，不是软弱的。
"""
    
    def handle_worker_request(self, request: dict):
        """主 Agent 处理 worker 的协作请求"""
        if request["type"] == "NEED_HELPER":
            helper = sessions_spawn(
                task=f"你是 {request['topic']} 专家。请帮助解决：{request['reason']}",
                mode="run"
            )
            return helper
        
        elif request["type"] == "NEED_REVIEW":
            reviewer = sessions_spawn(
                task=f"请评审以下内容：\n{request['output_snippet']}",
                mode="run"
            )
            return reviewer
        
        elif request["type"] == "NEED_INFO":
            # 用 web_search 或 memory_search 回答
            ...
```

### 3.3 自适应 Goal 演化

**Goal 不是固定的，可以在执行中演化：**

```python
# goal_evolution.py

class GoalEvolution:
    """
    在执行过程中，AI 发现 goal 需要调整：
    - 原 goal 太大 → 拆分为子目标
    - 原 goal 有遗漏 → 补充新条件
    - 原 goal 不合理 → 提出修改建议
    """
    
    REFLECTION_PROMPT = """
你已经执行了 {rounds} 轮，当前进度 {progress}。

原始目标：
{original_goal}

当前发现：
{discoveries}

请反思：
1. 原始目标是否仍然合理？
2. 是否需要增加/删除/修改某些条件？
3. 是否需要调整优先级？

如果需要调整目标，输出修改后的 goal + 修改原因。
如果目标仍然合理，输出 "GOAL_UNCHANGED"。
"""
    
    def maybe_evolve_goal(self, state: dict) -> str:
        """每 3 轮反思一次 goal"""
        if state["round"] % 3 != 0:
            return state["goal"]  # 不反思，保持原 goal
        
        reflection = sessions_spawn(
            task=self.REFLECTION_PROMPT.format(**state),
            mode="run"
        )
        
        if "GOAL_UNCHANGED" in reflection:
            return state["goal"]
        
        # Goal 演化了 — 记录演化历史
        state["goal_history"].append({
            "round": state["round"],
            "old_goal": state["goal"],
            "new_goal": reflection,
            "reason": "AI reflection"
        })
        return reflection
```

### 3.4 DeepFlow + Emergent 融合

**phases.yaml 从 "script" 变成 "menu"：**

```
传统 DeepFlow:
  phases.yaml = 固定的 phase 列表 + 固定顺序
  loop_runner.py = 按顺序执行每个 phase
  AI = 只填充每个 phase 的内容

Emergent DeepFlow:
  phases_menu.yaml = 可选 phase 菜单 + 适用条件
  AI Router = 根据任务动态选择 phases
  AI = 选择路径 + 填充内容 + 动态协作
```

**实现路径（渐进式，不推翻现有系统）**：

```python
# Phase 1: 保留现有 phases 作为 "默认路径"
# Phase 2: 添加 AI Router 可以选择跳过/添加 phases
# Phase 3: 允许 worker 之间动态协作
# Phase 4: Goal 可以在执行中演化

class EmergentLoopEngine:
    def plan_route(self, task: str, default_phases: list) -> list:
        """AI 决定执行路径 — 可以偏离默认路径"""
        
        route_decision = sessions_spawn(
            task=f"""
任务: {task}
默认路径: {default_phases}

你可以：
1. 使用默认路径
2. 跳过某些 phases（说明原因）
3. 添加额外 phases（说明原因）
4. 重新排序 phases（说明原因）
5. 合并多个 phases 为一个（说明原因）

你的选择？
""",
            mode="run"
        )
        return parse_route(route_decision)
```

### 3.5 创新设计

**创新 1: Fluid Pipeline — 流式管线**

```
传统管线: Phase 1 → Phase 2 → Phase 3（严格顺序）
流式管线: Worker 在执行过程中产出中间结果
         → 下一个 phase 的 worker 可以在前一个还没完成时就开始处理已有的中间结果
         → 像流水线工厂，不是批处理

示例：
- research worker 还在搜索第 3 个来源
- 但前 2 个来源的分析已经可以开始
- plan worker 开始基于已有的 2 个分析制定初步计划
- 当 research 完成第 3 个时，plan 更新计划

这需要 AI 判断 "什么时候有足够的信息可以开始了"
而不是等 "所有输入都到齐了才开始"
```

**创新 2: Swarm Intelligence — 群体智慧**

```
不是一个 Agent 做决策
而是多个 Agent 各自提出方案 → 投票/辩论 → 选择最优

场景：设计微服务架构
- Agent A（架构师）: 提议 5 个微服务
- Agent B（运维专家）: 提议 3 个微服务（更易运维）
- Agent C（业务专家）: 提议 7 个微服务（更灵活）
- Agent D（评审者）: 综合评估，选择最优方案

不需要预定义 "谁先做谁后做"
所有 Agent 可以并行提出方案，由 AI 评审者选择
```

---

## 四、专家 4：Agent Reliability 工程专家

### 4.1 用 5 层架构重新诊断 33% 成功率

| 层级 | 出了什么问题 | AI Native 修复 |
|------|------------|---------------|
| **Context** | 80K tokens prompt，注意力分散 | **Compaction**: 每轮 LLM 总结当前状态，下轮只传 2K 摘要 |
| **Tool** | 工具是 exec("loop_runner.py next")，返回大 JSON，LLM 要自己解析 | **语义工具**: `loop_status()` 返回 LLM 友好的结构化摘要 |
| **Feedback** | Worker 完成后主 Agent 不知道进度（靠 completion events，不可靠） | **主动反馈**: Worker 完成后自动写状态文件 + 通知主 Agent |
| **Guard Rails** | 无预算、无超时、无安全检查 | **三重护栏**: budget + timeout + AI safety judge |
| **Recovery** | 失败后只能重头开始（或靠 resume-prompt 求 LLM） | **Semantic Checkpoint**: LLM 写"我做到哪了"，恢复时读摘要继续 |

### 4.2 Reliability Harness 设计

```
┌──────────────────────────────────────────────────────┐
│              Reliability Harness（驾驶舱）              │
│                                                      │
│  ┌────────────────────────────────────────────┐      │
│  │            📊 仪表盘（Dashboard）            │      │
│  │                                              │      │
│  │  进度: ████████░░ 80% (8/10 phases)         │      │
│  │  预算: $0.12 / $0.50 (24% used)             │      │
│  │  时间: 25 min / 60 min (42% elapsed)        │      │
│  │  健康: ✅ 正常 (no anomalies)                │      │
│  │                                              │      │
│  │  已完成: dc, plan, review×3, research×3     │      │
│  │  当前:   consolidator                       │      │
│  │  待做:   audit, fix, harness, summary       │      │
│  └────────────────────────────────────────────┘      │
│                                                      │
│  ┌────────────────────────────────────────────┐      │
│  │            🎯 导航（Goal + Route）           │      │
│  │                                              │      │
│  │  Goal: "final_result.json quality ≥ 0.85"   │      │
│  │  建议下一步: 执行 consolidator phase        │      │
│  │  预计还需: 4 rounds, ~15 min                │      │
│  └────────────────────────────────────────────┘      │
│                                                      │
│  ┌────────────────────────────────────────────┐      │
│  │            🚨 警报（Anomaly Detection）      │      │
│  │                                              │      │
│  │  AI Monitor 持续检查:                        │      │
│  │  - 进度是否在增长？ ✅                       │      │
│  │  - 质量是否在提升？ ✅                       │      │
│  │  - 是否偏离目标？   ✅                       │      │
│  │  - 是否陷入循环？   ✅                       │      │
│  └────────────────────────────────────────────┘      │
│                                                      │
│  ┌────────────────────────────────────────────┐      │
│  │            🔒 安全带（Guard Rails）          │      │
│  │                                              │      │
│  │  预算上限: $0.50 (hard stop)                │      │
│  │  时间上限: 60 min (hard stop)               │      │
│  │  最大轮次: 15 rounds                        │      │
│  │  禁止操作: 删除文件、修改配置               │      │
│  └────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────┘
```

### 4.3 监控与可观测性（AI Native）

**不是检查文件是否存在，是 AI 评估 "进展是否健康"：**

```python
# ai_monitor.py — AI-native 的 Loop 监控

class AIMonitor:
    """
    用 LLM 监控 Loop 健康度
    不是规则引擎，是 AI judge
    """
    
    HEALTH_CHECK_PROMPT = """
你是 Loop 健康度监控器。

## 当前状态
轮次: {round}/{max_rounds}
进度: {progress}%
预算: ${spent}/${budget}
最近 3 轮的动作: {recent_actions}
最近 3 轮的结果: {recent_results}

## 请检查
1. **进度趋势**: 进度是否在增长？是否卡住了？
2. **效率**: 每轮的 token 消耗是否合理？
3. **方向**: 最近的动作是否在朝目标前进？
4. **异常**: 有没有重复失败、循环、或偏离？
5. **预测**: 按当前速度，能在预算/时间内完成吗？

输出 JSON:
{{
  "health": "healthy|warning|critical",
  "issues": [...],
  "prediction": "on_track|at_risk|will_fail",
  "suggestion": "..."
}}
"""
    
    def check_health(self, state: dict) -> dict:
        """每 2 轮做一次健康检查"""
        if state["round"] % 2 != 0:
            return state.get("last_health", {"health": "unknown"})
        
        result = quick_llm_call(
            self.HEALTH_CHECK_PROMPT.format(**state),
            model="fast_model"  # 小模型即可
        )
        
        if result["health"] == "critical":
            # 严重问题 → 通知用户
            notify(f"⚠️ Loop 健康度严重: {result['issues']}")
        
        return result
```

### 4.4 创新设计

**创新 1: Confidence-Based Routing — 基于置信度的路由**

```python
# AI 不仅做决策，还报告置信度
# 高置信度 → 自动执行
# 低置信度 → 请求人类确认

ACTION_WITH_CONFIDENCE = """
请决定下一步行动，并报告你的置信度。

输出 JSON:
{
  "action": "spawn_worker",
  "phase": "research",
  "task": "...",
  "confidence": 0.95,
  "reasoning": "..."
}

置信度含义：
- > 0.8: 你很有把握，自动执行
- 0.5-0.8: 你有一定把握，执行但标记为 "auto-approved"
- < 0.5: 你不太确定，暂停等人类确认
"""

def handle_action(action: dict):
    if action["confidence"] >= 0.8:
        execute(action)  # 自动执行
    elif action["confidence"] >= 0.5:
        execute(action)
        log("auto-approved", action)
    else:
        # 暂停，请求人类确认
        notify(f"🤔 AI 不确定下一步 (置信度 {action['confidence']}): {action}")
        wait_for_human_approval()
```

**创新 2: Failure Pattern Learning — 失败模式学习**

```python
# 每次 Loop 失败后，AI 分析失败模式
# 下次遇到类似情况时，提前规避

class FailurePatternLearner:
    def analyze_failure(self, loop_run: dict) -> dict:
        """Loop 失败后分析根因"""
        analysis = sessions_spawn(
            task=f"""
分析这次 Loop 失败：

目标: {loop_run['goal']}
执行历史: {loop_run['history']}
失败原因: {loop_run['failure_reason']}

请识别：
1. 失败模式类型（卡住/循环/偏离/超时/质量不足）
2. 在哪一轮开始出问题？
3. 什么信号可以提前预警？
4. 下次遇到类似情况应该怎么做？

输出 JSON 并写入 memory/loop_failures/
""",
            mode="run"
        )
        return analysis
    
    def get_warnings(self, current_state: dict) -> list:
        """当前 Loop 开始前，检查历史失败模式"""
        past_failures = load_all("memory/loop_failures/")
        if not past_failures:
            return []
        
        warnings = sessions_spawn(
            task=f"""
当前 Loop 状态: {current_state}
历史失败模式: {past_failures}

当前 Loop 有没有类似的历史失败模式的早期信号？
如果有，输出预警和建议。
""",
            mode="run"
        )
        return parse_warnings(warnings)
```

---

## 五、综合架构（AI Native 版）

### 5.1 核心设计原则（修正版）

| # | 原则 | 说明 |
|---|------|------|
| 1 | **AI 做决策，Harness 赋能** | 不是 "Python 做决策"，是给 AI 更好的上下文、工具和反馈 |
| 2 | **Goal 是自然语言，Judge 是 AI** | 不是 Python checker，是 AI 理解并验证目标 |
| 3 | **Phases 是菜单，不是脚本** | AI 根据任务动态选择路径，不按固定 DAG |
| 4 | **反馈比控制更有效** | 快速反馈让 AI 自我校正，不是预定义规则 |
| 5 | **涌现优于预设** | Agent 间动态协作，AI 发现最优执行策略 |
| 6 | **可靠性来自驾驶舱，不来自自动驾驶** | Guard Rails + Dashboard + Compaction + Checkpoint |

### 5.2 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│              OpenClaw LoOP Engine (AI Native)                 │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │           Loop Harness (驾驶舱)                      │     │
│  │                                                       │     │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐   │     │
│  │  │ Dashboard  │  │  Navigator │  │ Guard Rails  │   │     │
│  │  │ (状态摘要) │  │ (Goal+Route│  │ (budget/time │   │     │
│  │  │            │  │  建议)     │  │  /safety)    │   │     │
│  │  └────────────┘  └────────────┘  └──────────────┘   │     │
│  └───────────────────────┬─────────────────────────────┘     │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────┐     │
│  │           LLM Agent (驾驶员)                         │     │
│  │                                                       │     │
│  │  接收: 仪表盘 + 目标 + 工具 + 反馈                  │     │
│  │  决定: 下一步做什么 (tool call / done / blocked)     │     │
│  │  可以: 动态选 phase / 请求帮助 / 调整 goal          │     │
│  └───────────────────────┬─────────────────────────────┘     │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────┐     │
│  │           Tool Layer (操纵杆)                        │     │
│  │                                                       │     │
│  │  loop_status()  → 结构化状态摘要                    │     │
│  │  spawn_worker() → 启动 worker                       │     │
│  │  check_output() → 检查结果                          │     │
│  │  mark_done()    → 标记完成                          │     │
│  │  request_help() → 动态协作                          │     │
│  │  evolve_goal()  → 调整目标                          │     │
│  └───────────────────────┬─────────────────────────────┘     │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────┐     │
│  │           Feedback Layer (通信)                      │     │
│  │                                                       │     │
│  │  Worker 完成 → 自动反馈结果                         │     │
│  │  AI Monitor → 健康度评估                            │     │
│  │  AI Judge   → Goal 满足度检查                       │     │
│  │  Compaction → 上下文压缩                            │     │
│  └───────────────────────┬─────────────────────────────┘     │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────┐     │
│  │           Persistence Layer (记忆)                   │     │
│  │                                                       │     │
│  │  Semantic Checkpoint → LLM 写的进度摘要             │     │
│  │  Loop DNA            → 执行基因图谱                 │     │
│  │  Failure Patterns    → 失败模式学习                 │     │
│  │  Goal History        → 目标演化记录                 │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │           DeepFlow Integration                       │     │
│  │                                                       │     │
│  │  phases_menu.yaml → AI 选择的 phase 菜单            │     │
│  │  4 域 + Meta-Loop → AI 编排的跨域流程               │     │
│  │  Dynamic Collab   → Agent 间自由协作                │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 一个完整的 Loop Turn 示例

```
[Cron 唤醒主 Agent]

主 Agent 读取 checkpoint.md:
  "已完成 8/10 phases。当前在 consolidator。上轮 research 全部完成。"

主 Agent 构建 turn prompt:
  - Goal: "final_result.json quality ≥ 0.85"
  - Dashboard: 进度 80%, 预算 $0.12/$0.50, 健康 ✅
  - 工具: loop_status, spawn_worker, check_output, mark_done
  - 建议: 执行 consolidator

主 Agent (LLM) 决策:
  → spawn_worker("consolidator", task=consolidator_prompt)
  → sessions_yield()

Worker 完成 → 写 consolidator.json → 反馈主 Agent

主 Agent 构建下一轮 turn prompt:
  - Dashboard: 进度 90%, consolidator 完成
  - 建议: 执行 audit

主 Agent (LLM) 决策:
  → check_output("consolidator")  ← 先检查
  → 确认 OK
  → mark_done("consolidator")
  → spawn_worker("audit", task=audit_prompt)
  → sessions_yield()

... 继续直到 AI Judge 判断 goal met
```

### 5.4 实施路径

| Phase | 内容 | 工作量 | 关键产出 |
|-------|------|--------|---------|
| **P1** | Goal + AI Judge 机制 | 4h | goal_checker.py (LLM-based) |
| **P2** | Loop Harness + Dashboard | 6h | 结构化 turn prompt + 状态摘要 |
| **P3** | Semantic Checkpoint + Compaction | 4h | checkpoint.md + 上下文压缩 |
| **P4** | Phases Menu + AI Router | 4h | phases_menu.yaml + 动态路径选择 |
| **P5** | Dynamic Collaboration + Goal Evolution | 4h | Worker 间通信 + goal 演化 |
| **P6** | AI Monitor + Failure Pattern Learning | 4h | 健康度监控 + 失败学习 |
| **P7** | DeepFlow Meta-Loop + Swarm | 4h | 跨域 AI 编排 |
| **总计** | | **~30h** | |

---

## 六、与之前报告的关键差异

| 维度 | V1（防御式） | V2（AI Native） |
|------|------------|----------------|
| 决策者 | Python 状态机 | LLM Agent |
| Goal 验证 | Python checker 函数 | AI Judge (LLM) |
| Phase 顺序 | 预定义 DAG | AI 动态选择 (menu) |
| 错误处理 | 预定义 if/else | LLM 分析 + 自适应修复 |
| 进度追踪 | 文件存在性检查 | AI 评估"进展是否健康" |
| Agent 协作 | 预定义管道 | 动态协作（求助/评审） |
| 上下文管理 | Python 截断 | LLM compaction |
| 恢复机制 | resume-prompt (求 LLM) | Semantic checkpoint (LLM 写的摘要) |
| 核心隐喻 | 流水线（工业时代） | 驾驶舱（赋能飞行员） |

---

*AI Native 专家研讨会报告，2026-06-25*
*核心理念：给 AI 更好的驾驶舱，不是抢走方向盘*
