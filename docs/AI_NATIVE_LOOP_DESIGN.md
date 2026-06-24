# AI Native LoOP V2 架构设计

> **版本**: V2.0 Hybrid  
> **日期**: 2026-06-25  
> **作者**: 小满（整合 4 位 AI 专家报告 + 现有 loop_runner.py 分析）  
> **状态**: 设计稿，待忠礼审阅

---

## 一、问题诊断：为什么 33% 成功率？

### 1.1 错误诊断 vs 正确诊断

| | 错误诊断 | 正确诊断（4 专家共识） |
|---|---|---|
| 归因 | "LLM 不适合循环控制" | Context/Tool/Feedback 设计差 |
| 修复方向 | 用 Python 替代 LLM 决策 | 给 LLM 更好的上下文、工具和反馈 |
| 类比 | 飞行员犯错 → 换成自动驾驶 | 飞行员犯错 → 改善仪表盘和空管 |

### 1.2 四层根因（5-Layer 诊断）

```
Layer 1: Context Engineering — 80K tokens 塞满上下文，注意力崩溃
Layer 2: Tool Design — 工具返回自由文本，LLM 需要"阅读理解"
Layer 3: Feedback Loop — 主 Agent 数完成事件，进度感知断裂
Layer 4: Guard Rails — 无预算上限、无超时、无偏离检测
Layer 5: Recovery — 失败从头开始，无 checkpoint/resume
```

### 1.3 当前 loop_runner.py 的局限性

现有设计（Phase Worker 模式）解决了 Orchestrator 的循环问题，但引入了新的限制：

| 特性 | 当前 loop_runner.py | AI Native 目标 |
|------|-------------------|---------------|
| Phase 选择 | Python 硬编码顺序 | LLM 从菜单中动态选择 |
| 反馈类型 | 文件存在性检查（pass/fail） | 语义诊断（为什么失败） |
| 上下文管理 | 无（每个 worker 独立） | Compaction（LLM 总结历史） |
| 错误恢复 | 重试或中止 | AI 选择恢复策略 |
| Goal 定义 | `.completed` 文件存在 | 自然语言 + LLM Judge 验证 |
| Phase 间协作 | 预定义 DAG | Worker 可动态请求帮助 |

---

## 二、混合架构设计哲学

### 2.1 核心原则

```
Python 做骨架（保底）+ LLM 做肉（智能）

Python 负责：                    LLM 负责：
├─ 状态持久化                    ├─ Phase 内决策
├─ Checkpoint/Resume             ├─ 动态 Phase 路由
├─ 预算控制（token/turn/cost）    ├─ 语义质量判断
├─ 文件完整性检查                 ├─ 上下文压缩（Compaction）
├─ 超时熔断                      ├─ 目标验证（Goal Judge）
└─ 审计日志                      ├─ 恢复策略选择
                                 └─ Agent 间动态协作
```

### 2.2 设计原则

1. **LLM 是驾驶员，不是乘客** — LLM 决定做什么，Python 提供工具和安全边界
2. **反馈比控制更有效** — 不是 `if/else`，是 `do → observe → adapt`
3. **约束即创造力** — 不告诉 LLM 步骤，给目标和约束，让 LLM 发现路径
4. **渐进式升级** — 不推翻现有系统，逐层替换

---

## 三、架构总览

```
┌─────────────────────────── AI NATIVE LOOP HARNESS ───────────────────────────┐
│                                                                              │
│  ┌─── 仪表盘 (Dashboard) ──────────────────────────────────────────────────┐ │
│  │  Phase: 4/10 ████░░░░░░  │  Health: 🟢  │  Tokens: 45K/200K  │ $0.12  │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Layer 1: Context Compaction ─────────────────────────────────────────┐ │
│  │  历史压缩 → 结构化摘要 → 注入下一个 Worker 的 context                    │ │
│  │  触发: 每 3 轮 or context > 60K tokens                                  │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Layer 2: Worker Contract (结构化返回) ───────────────────────────────┐ │
│  │  WorkerResult {status, summary, artifacts, confidence, issues}           │ │
│  │  每个 Worker 必须返回结构化 JSON + 交班简报                            │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Layer 3: Feedback Stream ────────────────────────────────────────────┐ │
│  │  Worker 完成 → 结构化进度报告 → 健康评估 → 主 Agent 决策建议            │ │
│  │  不是"数事件"，是实时进度感知                                           │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Layer 4: AI Guard Rails ─────────────────────────────────────────────┐ │
│  │  小模型 Judge 实时评估: 是否偏离目标? 是否需要干预?                     │ │
│  │  Hooks: PreToolUse (安全检查) + PostToolUse (质量验证)                   │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Layer 5: Recovery Engine ────────────────────────────────────────────┐ │
│  │  Checkpoint + AI 选择恢复策略:                                          │ │
│  │  retry_same │ retry_with_context │ skip │ split │ switch_model │ human  │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Layer 6: Goal Judge (/goal 模式) ────────────────────────────────────┐ │
│  │  自然语言 Goal → LLM Judge 验证 → 满足则自动停止                        │ │
│  │  Goal 可演化（加约束/加子目标）但不丢失原始目标                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Layer 7: Emergent Orchestration (Phase Menu) ────────────────────────┐ │
│  │  phases.yaml = 菜单（不是脚本）                                         │ │
│  │  LLM 从菜单中选下一道菜（动态路由）                                     │ │
│  │  Worker 可动态请求 spawn 其他 Worker（请求-响应式协作）                  │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─── Python 骨架（保底） ─────────────────────────────────────────────────┐ │
│  │  pipeline_state.json │ checkpoint/resume │ budget limits │ audit log     │ │
│  │  file integrity check │ timeout circuit breaker │ stale detection       │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 四、七层详细设计

### Layer 1: Context Compaction（上下文压缩）

**灵感来源**: Claude Code 的 Compaction 机制

**核心思想**: 不是截断历史，是让 LLM 总结"下一个 phase 需要的信息"

```python
class ContextCompactor:
    """上下文压缩器 — LLM 总结，不是代码截断"""
    
    COMPACT_PROMPT = """你是一个项目进度分析师。

已完成 {completed_count} 个 phase，以下是每个 phase 的产出摘要。
请为下一个 phase 生成一份"工作上下文摘要"。

要求：
1. 保留：已完成的关键决策和产出（只保留下一个 phase 需要的）
2. 保留：当前未解决的问题
3. 生成：下一个 phase 应该做什么（基于已完成上下文）
4. 压缩比：原始 token 的 30% 以内

输出 JSON:
{{
    "completed_phases": [{{"phase": N, "name": "...", "key_decisions": [...], "artifacts": [...]}}],
    "open_issues": [...],
    "next_phase_brief": "...",
    "goal_alignment": "当前产出与原始目标的对齐程度"
}}"""
    
    def compact(self, history: list[dict], current_phase: int) -> dict:
        """
        输入：所有已完成 phase 的 WorkerResult
        输出：结构化摘要（< 2K tokens）
        """
        prompt = self.COMPACT_PROMPT.format(completed_count=current_phase - 1)
        result = llm_call(prompt, context=json.dumps(history, ensure_ascii=False))
        return json.loads(result)
    
    def should_compact(self, token_count: int, threshold: int = 60_000) -> bool:
        return token_count > threshold
```

**触发条件**:
- 每 3 个 phase 自动触发
- context token 数超过 60K 时强制触发
- 主 Agent 可以手动触发

**与现有系统的集成**:
- 现有 `loop_runner.py` 的 `resume-prompt` 只做文件存在性检查
- Compaction 补充了"语义层面"的上下文传递

---

### Layer 2: Worker Contract（结构化返回契约）

**核心思想**: Worker 不仅完成任务，还负责"交班简报"

```python
from pydantic import BaseModel
from typing import Literal

class WorkerResult(BaseModel):
    """每个 Worker 必须返回的结构化结果"""
    
    # 基本状态
    status: Literal["success", "partial", "failed"]
    phase: int
    phase_name: str
    
    # 产出
    artifacts: dict[str, str]  # {"file_name": "file_path"}
    summary: str  # 一句话摘要（给下一个 phase 的上下文输入）
    
    # 质量自评
    confidence: float  # 0-1，自评置信度
    issues: list[str]  # 发现的问题
    warnings: list[str]  # 非致命但需要注意的问题
    
    # 给 AI Judge 的元数据
    metrics: dict[str, float]  # 可量化的指标
    
    # 动态协作请求（Emergent 层用）
    help_needed: list[dict] | None = None  # 需要其他 Worker 帮助时填写
```

**集成方式**: 
- Worker prompt 末尾追加结构化输出要求
- `loop_runner.py` 的 `next` 命令解析 WorkerResult 而非检查文件

```python
# Worker prompt 尾部追加
STRUCTURED_OUTPUT_SUFFIX = """

## 🔴 输出格式（必须严格遵守）

完成任务后，在最后输出以下 JSON（用 ```json 包裹）：

```json
{
    "status": "success|partial|failed",
    "phase": <phase_number>,
    "phase_name": "<phase_name>",
    "artifacts": {"<file_name>": "<file_path>"},
    "summary": "<一句话总结你做了什么>",
    "confidence": <0.0-1.0>,
    "issues": ["<发现的问题>"],
    "warnings": ["<需要注意的事项>"],
    "metrics": {},
    "help_needed": null
}
```
"""
```

---

### Layer 3: Feedback Stream（反馈流）

**核心思想**: 不是"数完成事件"，是实时进度感知

```python
class FeedbackStream:
    """Worker → loop_runner → 主 Agent 的反馈流"""
    
    def on_worker_complete(self, result: WorkerResult, state: dict) -> dict:
        """Worker 完成后，生成结构化进度报告"""
        return {
            "event": "worker.complete",
            "phase": result.phase,
            "phase_name": result.phase_name,
            "status": result.status,
            "progress": f"{result.phase}/{state['total_phases']}",
            "progress_bar": self._progress_bar(result.phase, state['total_phases']),
            "health": self._assess_health(result),
            "recommendation": self._recommend_next(result, state),
            "compacted_context": None,  # Layer 1 填充
        }
    
    def _progress_bar(self, current: int, total: int) -> str:
        filled = "█" * current
        empty = "░" * (total - current)
        return f"{filled}{empty} {current}/{total}"
    
    def _assess_health(self, result: WorkerResult) -> str:
        """健康度评估"""
        if result.status == "failed" or result.confidence < 0.5:
            return "critical"
        elif result.status == "partial" or result.confidence < 0.7 or result.issues:
            return "warning"
        return "healthy"
    
    def _recommend_next(self, result: WorkerResult, state: dict) -> dict:
        """给主 Agent 的决策建议"""
        if result.status == "failed":
            return {"action": "recover", "reason": f"Phase {result.phase} failed", "strategies": ["retry_with_context", "split_phase"]}
        elif result.status == "partial":
            return {"action": "continue_with_note", "reason": f"Phase {result.phase} partial, issues: {result.issues}"}
        else:
            return {"action": "continue", "reason": f"Phase {result.phase} success"}
```

**主 Agent 看到的反馈格式**:

```
📊 Pipeline 进度: Phase 4/10 ████░░░░░░
🏥 健康度: 🟢 healthy
📋 Phase 4 (research) 完成
   摘要: 完成 3 位专家调研，覆盖技术/商业/风险维度
   置信度: 0.85
   下一步建议: continue → Phase 5 (consolidator)
```

---

### Layer 4: AI Guard Rails（AI 护栏）

**核心思想**: Hook 是建议性的（guard rails），不是控制性的（steering wheel）

#### PreToolUse Hook（Worker spawn 前）

```python
class PreSpawnHook:
    """Worker spawn 前的安全检查"""
    
    CHECK_PROMPT = """你是执行守卫。在 spawn 一个 Worker 之前检查：

待 spawn: Phase {phase} ({phase_name})
已完成: {completed_phases}
当前预算: {tokens_used}/{tokens_budget} tokens, {turns_used}/{turns_budget} turns
活跃 Workers: {active_workers}

检查项：
1. 重复检测：这个 phase 是否已完成？（检查 completed_phases）
2. 依赖检查：前置依赖是否满足？
3. 预算检查：是否还有足够预算？（> 20% 剩余）
4. 目标对齐：这个 spawn 是否与 goal 相关？

输出 JSON:
{{"approved": true/false, "reason": "...", "injected_context": "..."}}"""
```

#### PostToolUse Hook（Worker 完成后）

```python
class PostWorkerHook:
    """Worker 完成后的质量验证"""
    
    VERIFY_PROMPT = """你是质量审计员。验证 Worker 的产出：

Phase: {phase} ({phase_name})
Worker 摘要: {summary}
Worker 置信度: {confidence}
产出文件: {artifacts}

检查项：
1. 产出文件是否存在且非空？
2. 摘要是否与产出一致？
3. 置信度是否合理？（过高可能是虚假自信，过低需要检查）

输出 JSON:
{{"verified": true/false, "quality_score": 0-1, "issues": [...]}}"""
```

**与 Python 骨架的协作**:
- Python 做硬约束（文件存在性、token 预算、超时）
- LLM Judge 做软约束（语义对齐、质量评估、偏离检测）

---

### Layer 5: Recovery Engine（恢复引擎）

**核心思想**: 失败 → 分析原因 → 选择策略 → 最小代价恢复

```python
class RecoveryEngine:
    """AI 驱动的恢复策略选择"""
    
    STRATEGIES = {
        "retry_same": "重试当前 phase（适用于随机性失败）",
        "retry_with_context": "补充上下文后重试（适用于上下文不足）",
        "retry_with_prompt_fix": "修复 prompt 后重试（适用于 prompt 设计问题）",
        "skip_and_note": "跳过当前 phase，标记为部分完成",
        "split_phase": "拆分为更小的子任务",
        "switch_model": "换更强的模型（适用于模型能力不足）",
        "human_review": "请求人工介入（适用于无法自动判断的情况）",
    }
    
    ANALYZE_PROMPT = """你是故障恢复专家。

失败的 Phase: {phase} ({phase_name})
失败原因: {issues}
Worker 置信度: {confidence}
已完成 Phases: {completed_phases}
已用资源: {tokens_used} tokens, {turns_used} turns
剩余预算: {tokens_remaining} tokens, {turns_remaining} turns
历史失败模式: {failure_history}

可选恢复策略:
{strategies}

请分析根因并选择最优恢复策略。
如果同一错误已出现 2+ 次，选择更激进的策略（switch_model 或 human_review）。

输出 JSON:
{{
    "root_cause": "...",
    "strategy": "...",
    "reason": "...",
    "estimated_cost": "...",
    "fallback_strategy": "..."
}}"""
```

**与 Checkpoint 集成**:

```python
# 每个 phase 完成后自动 checkpoint
def checkpoint(state: PipelineState, result: WorkerResult):
    """保存 checkpoint，支持从任意 phase 恢复"""
    checkpoint_data = {
        "phase": result.phase,
        "timestamp": datetime.now(SHANGHAI_TZ).isoformat(),
        "completed_phases": state.completed_phases,
        "artifacts": result.artifacts,
        "compacted_context": state.last_compaction,  # Layer 1 的压缩上下文
    }
    write_json(state.base_path / "checkpoints" / f"phase_{result.phase}.json", checkpoint_data)
```

---

### Layer 6: Goal Judge（/goal 模式）

**灵感来源**: Claude Code 的 `/goal` 机制

**核心思想**: 自然语言定义完成标准 + LLM Judge 验证

```python
class GoalJudge:
    """LLM 评估 Goal 是否满足"""
    
    JUDGE_PROMPT = """你是目标验证 Judge。

原始目标:
{goal}

当前状态:
{state_summary}

已完成产出:
{artifacts_summary}

评估要求：
1. 逐项检查 goal 中的每个条件
2. 对每个条件判断：pass / fail / partial
3. 给出整体评估（satisfied: true/false）
4. 如果不满足，说明差距和建议

输出 JSON:
{{
    "satisfied": true/false,
    "confidence": 0.0-1.0,
    "checks": [
        {{"condition": "...", "status": "pass|fail|partial", "gap": "..."}}
    ],
    "suggestion": "如果未满足，建议下一步"
}}"""
    
    def evaluate(self, goal: str, state: PipelineState, artifacts: dict) -> GoalEvaluation:
        """每 3 轮评估一次 Goal 满足度"""
        result = llm_call(self.JUDGE_PROMPT.format(
            goal=goal,
            state_summary=state.to_summary(),
            artifacts_summary=self._summarize_artifacts(artifacts),
        ))
        return GoalEvaluation(**json.loads(result))
```

**Goal 定义示例**:

```
/goal "solution_pro 管线完成全部 10 个 phase，final_result.json 包含完整的
      技术方案、风险评估和实施建议，quality_score ≥ 0.85"

/goal "ship_pro 管线生成 ship_package.json，通过 format_check + schema_check 
      + content_quality 三个 gate，所有 TASK 有明确的验收标准"
```

**Goal 演化**:

```python
class EvolvableGoal:
    """Goal 可以演化但不能丢失"""
    
    def __init__(self, initial_goal: str):
        self.original = initial_goal
        self.current = initial_goal
        self.constraints: list[str] = []
        self.sub_goals: list[str] = []
        self.history: list[tuple[str, str]] = []  # [(event, description)]
    
    def evolve(self, new_constraint: str = None, new_sub_goal: str = None):
        if new_constraint:
            self.constraints.append(new_constraint)
            self.history.append(("constraint_added", new_constraint))
        if new_sub_goal:
            self.sub_goals.insert(0, new_sub_goal)
            self.history.append(("sub_goal_added", new_sub_goal))
```

---

### Layer 7: Emergent Orchestration（涌现式编排）

**灵感来源**: AutoGen GroupChat + CrewAI Hierarchical

**核心思想**: phases.yaml 从"脚本"变成"菜单"

```yaml
# phases_menu.yaml（替代 phases.yaml）
# 每个 phase 定义适用条件和产出，LLM 动态选择

phases:
  - name: data_collection
    applicable_when: "需要收集外部数据或信息"
    produces: ["data/collection.json"]
    requires: []  # 无前置依赖
    domain: solution_pro
    
  - name: planning
    applicable_when: "需要制定执行计划或架构设计"
    produces: ["planning.json"]
    requires: ["data_collection"]  # 依赖 data_collection
    
  - name: reviewers
    applicable_when: "需要多角度审查方案"
    produces: ["reviewer_technical.json", "reviewer_business.json", "reviewer_risk.json"]
    requires: ["planning"]
    parallel: true
    
  - name: research
    applicable_when: "存在需要深入调研的技术或业务问题"
    produces: ["research_expert_1.json", "research_expert_2.json", "research_expert_3.json"]
    requires: ["planning"]
    parallel: true
    
  - name: consolidator
    applicable_when: "有多个评审/调研结果需要整合"
    produces: ["consolidator.json"]
    requires: ["reviewers", "research"]
    
  # ... 更多 phases
```

**Phase Selector（LLM 路由）**:

```python
class PhaseSelector:
    """LLM 从菜单中选择下一个 phase"""
    
    SELECT_PROMPT = """你是 Phase 路由器。

当前目标: {goal}
已完成 Phases: {completed}
已有产出: {artifacts}
Phase 菜单:
{menu}

请选择下一个应该执行的 phase。
规则：
1. 只能选择 requires 已满足的 phase
2. 如果多个 phase 都可选，选择优先级最高的
3. 如果所有必要 phase 都已完成，返回 "complete"
4. 如果发现需要新的调研，可以插入额外 phase

输出 JSON:
{{
    "next_phase": "phase_name" | "complete",
    "reason": "...",
    "skip_phases": ["可以跳过的 phase 列表"],
    "extra_phases": ["需要插入的额外 phase 列表"]
}}"""
```

**请求-响应式协作**:

```python
# Worker 在执行过程中可以请求帮助
WORKER_HELP_REQUEST_FORMAT = """
如果你在执行过程中发现需要其他专家的帮助，在输出中包含：

```json
"help_needed": [
    {
        "type": "research|review|code",
        "description": "你需要什么帮助",
        "priority": "high|medium|low",
        "context": "相关的上下文信息"
    }
]
```

主 Agent 会评估你的请求并决定是否 spawn 额外的 Worker。
"""
```

---

## 五、执行流程（完整 Loop）

```
用户: /deep solution_pro "为 XX 公司设计微服务方案"

主 Agent:
  1. 初始化
     ├─ 创建 pipeline_state.json
     ├─ 解析 /goal → EvolvableGoal
     ├─ 清理旧的 .completed 文件
     └─ 创建 Watcher Cron

  2. 主循环（Phase Worker 模式 + AI Native 增强）
     while not done:
       ├─ [Python] loop_runner.py next → 获取下一个 phase（或交给 LLM 路由）
       ├─ [Layer 1] Context Compaction → 压缩历史上下文
       ├─ [Layer 4] PreSpawn Hook → 检查是否应该 spawn
       ├─ [LLM] sessions_spawn(worker_prompt + 结构化输出要求 + 压缩上下文)
       ├─ [LLM] sessions_yield()
       ├─ [Python] 解析 WorkerResult
       ├─ [Layer 2] 验证 WorkerResult 格式
       ├─ [Layer 4] PostWorker Hook → 质量验证
       ├─ [Layer 3] FeedbackStream → 生成进度报告
       ├─ [Python] checkpoint → 保存断点
       ├─ [Layer 6] Goal Judge（每 3 轮）→ 评估目标满足度
       │    ├─ satisfied → break
       │    └─ not satisfied → continue
       ├─ [Layer 5] 如果 failed → Recovery Engine 选择策略
       └─ [Python] 更新 pipeline_state.json

  3. 收尾
     ├─ [Python] 写 .completed
     ├─ [Layer 6] 最终 Goal 评估
     ├─ [Python] 生成报告
     ├─ 清理 Watcher Cron
     └─ 通知用户
```

---

## 六、迁移路径（渐进式升级）

### Phase 0: 基础增强（1-2 天）— 不动 loop_runner.py

在现有 `loop_runner.py` 之上叠加 AI Native 层：

| 改动 | 文件 | 说明 |
|------|------|------|
| WorkerResult 契约 | `contracts/worker_result.py` | Pydantic 模型 + prompt 后缀 |
| Feedback Stream | `scripts/feedback_stream.py` | 解析 WorkerResult，生成进度报告 |
| Compaction 脚本 | `scripts/context_compactor.py` | 读取已完成 phase 的产出，生成压缩摘要 |

**风险**: 低。不修改核心循环，只在 Worker prompt 末尾追加结构化输出要求。

### Phase 1: Hook 系统（2-3 天）

| 改动 | 文件 | 说明 |
|------|------|------|
| PreSpawn Hook | `hooks/pre_spawn.py` | spawn 前安全检查 |
| PostWorker Hook | `hooks/post_worker.py` | 完成后质量验证 |
| Goal Judge | `scripts/goal_judge.py` | 自然语言 Goal 验证 |

**风险**: 中。Hook 的 LLM 调用增加延迟和成本，但可以用小模型（qwen3.7-plus）降低。

### Phase 2: Recovery + Checkpoint（2-3 天）

| 改动 | 文件 | 说明 |
|------|------|------|
| Checkpoint 机制 | `scripts/checkpoint.py` | 每个 phase 后保存断点 |
| Recovery Engine | `scripts/recovery_engine.py` | AI 选择恢复策略 |
| loop_runner.py 升级 | `scripts/loop_runner.py` | 集成 checkpoint + recovery |

**风险**: 中。需要修改 loop_runner.py 的核心逻辑。

### Phase 3: Emergent Orchestration（3-5 天）

| 改动 | 文件 | 说明 |
|------|------|------|
| Phase Menu | `configs/phases_menu.yaml` | 替代 phases.yaml |
| Phase Selector | `scripts/phase_selector.py` | LLM 动态路由 |
| 请求-响应协作 | `scripts/collaboration.py` | Worker 间动态协作 |
| Goal 演化 | `scripts/evolvable_goal.py` | 自适应目标调整 |

**风险**: 高。这是最大的架构变更，需要充分测试。

### Phase 4: 全量集成（持续）

- 4 域统一迁移
- 性能优化（Compaction 缓存、Judge 模型选择）
- 监控仪表盘（飞书卡片）

---

## 七、成本与风险评估

### 7.1 Token 成本分析

| 层 | 调用频率 | 模型 | 预估 token/次 |
|---|---|---|---|
| Compaction | 每 3 轮 | qwen3.7-plus | 2K in + 1K out |
| PreSpawn Hook | 每个 phase | qwen3.7-plus | 500 in + 200 out |
| PostWorker Hook | 每个 phase | qwen3.7-plus | 1K in + 300 out |
| Goal Judge | 每 3 轮 | qwen3.7-plus | 2K in + 500 out |
| Recovery Engine | 失败时 | qwen3.7-max | 3K in + 1K out |
| Phase Selector | 每轮（Phase 3） | qwen3.7-plus | 1K in + 300 out |

**10 phase 管线总增量**: ~15K tokens（Hook）+ ~5K tokens（Compaction/Judge）≈ 20K tokens
**成本增量**: < $0.10 per run（可接受）

### 7.2 延迟分析

| 层 | 额外延迟 |
|---|---|
| Compaction | +5-10s（每 3 轮） |
| PreSpawn Hook | +2-3s（每个 phase） |
| PostWorker Hook | +2-3s（每个 phase） |
| Goal Judge | +3-5s（每 3 轮） |
| **总计（10 phase）** | **+30-60s（占管线总时长的 5-10%）** |

### 7.3 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Hook LLM 误判导致错误拦截 | 中 | 中 | 小模型 + 宽松阈值 + fallback to pass |
| Compaction 丢失关键信息 | 低 | 高 | 保留原始产出文件，压缩只用于 prompt |
| Recovery 策略选择不当 | 中 | 中 | 最多重试 2 次，超过直接 human_review |
| Phase Selector 选错 phase | 中 | 低 | requires 约束保底 + Python 验证 |
| Goal 演化漂移 | 低 | 中 | 记录完整演化历史，人工可审计 |

---

## 八、与现有系统的关系

| 现有组件 | 保留/升级/替代 | 说明 |
|----------|--------------|------|
| `loop_runner.py` | **升级** | 集成 Layer 2-5，保留 `next`/`check` 命令 |
| `pipeline_state.json` | **保留** | 作为 Python 骨架的状态存储 |
| `contracts/` Pydantic 模型 | **扩展** | 新增 WorkerResult 模型 |
| `pipeline_watcher.py` | **保留** | 与 Feedback Stream 并行工作 |
| `run_pipeline.py` | **保留** | 作为 Ship Pro 的入口 |
| `watcher_config.json` | **保留** | 契约笼子不变 |
| Orchestrator prompt | **瘦身** | 从 400+ 行 → ~100 行（去掉 phase 控制逻辑） |
| Worker prompt | **追加** | 末尾追加结构化输出后缀 |

---

## 九、成功标准

| 指标 | 当前值 | 目标值 | 验证方式 |
|------|--------|--------|----------|
| 管线完成率 | 33% | ≥ 70% | 3 个 case 至少 2 个完成 |
| 平均完成时间 | ~30min | ~25min | 含 Compaction 开销 |
| Token 效率 | ~200K/管线 | ~150K/管线 | Compaction 压缩后 |
| 恢复成功率 | 0%（失败从头来） | ≥ 50% | checkpoint 恢复 |
| Goal 满足率 | N/A | ≥ 80% | LLM Judge 评估 |

---

## 十、开放问题（需忠礼决策）

1. **Phase 3（Emergent Orchestration）是否要做？** — 风险最高，收益也最大。保守派建议 Phase 0-2 先跑通。

2. **Compaction 模型选择** — qwen3.7-plus（快+便宜）还是 qwen3.7-max（准+贵）？建议 plus，因为压缩任务不需要顶级推理。

3. **Goal Judge 评估频率** — 每 3 轮还是每轮？每轮更及时但成本更高。

4. **Hook 失败策略** — Hook LLM 调用失败时，默认 pass（继续执行）还是默认 block（等恢复）？建议 pass（不阻塞主流程）。

5. **是否需要在 Phase 0 之前先做基线测试？** — 用当前系统跑 3 个 case 记录基线数据，以便后续对比。

---

*本文档整合自 4 位 AI 专家报告：AI Native Loop Architect、Claude Code/Codex 研究者、Agent Reliability 工程专家、Emergent AI 系统设计师。*
