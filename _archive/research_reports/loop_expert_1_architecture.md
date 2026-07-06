# OpenClaw LoOP 核心引擎架构设计

> **作者**: Agent Loop 系统架构师  
> **日期**: 2026-06-24  
> **版本**: 1.0.0  
> **定位**: 从系统架构角度设计 OpenClaw LoOP 的核心引擎

---

## 一、核心洞察：OpenClaw LoOP 的本质

### 1.1 与业界 Agent Loop 的本质区别

| 维度 | OpenAI/Claude Agent Loop | OpenClaw LoOP |
|------|-------------------------|---------------|
| **执行模型** | 单进程 `while` 循环 | 分布式跨 Session 持久循环 |
| **状态存储** | 内存（进程崩溃即丢失） | 磁盘（`pipeline_state.json` + Blackboard） |
| **生命周期** | 秒级～分钟级（单次请求） | 小时级～天级（跨崩溃恢复） |
| **并发模型** | 单线程顺序执行 | 多 Session 并行（`sessions_spawn`） |
| **唤醒机制** | 用户请求触发 | Cron/Heartbeat 定时唤醒 |
| **失败恢复** | 从头开始 | Checkpoint 恢复（断点续传） |

**核心论断**：OpenClaw LoOP 不是 Agent Loop，是 **Agent Workflow Engine**。它更接近 Temporal 的 Durable Execution，而非 OpenAI 的 Runner.run()。

### 1.2 设计哲学

```
"如果你说不清 done 长什么样，你没有 loop，你有个愿望。"
                                    — Goal Checker 是 LoOP 的灵魂

"你不应该再 prompt coding agents 了，你应该设计 prompt 你 agents 的 loops."
                                    — Peter Steinberger
```

**OpenClaw LoOP 三原则**：
1. **状态即代码**：所有状态必须可序列化、可恢复、可审计
2. **检查即控制**：Goal Checker 决定循环继续还是终止
3. **崩溃即常态**：设计假设任何时刻都可能崩溃

---

## 二、Loop 生命周期状态机

### 2.1 完整状态转换图

```
                         ┌──────────────────────────────────────────────────────────┐
                         │                      LoOP State Machine                   │
                         └──────────────────────────────────────────────────────────┘

    ┌─────────┐      ┌──────────┐      ┌────────────┐      ┌──────────┐      ┌─────────┐
    │  IDLE   │─────▶│ PLANNING │─────▶│ EXECUTING  │─────▶│ CHECKING │─────▶│  DONE   │
    └─────────┘      └──────────┘      └────────────┘      └──────────┘      └─────────┘
         ▲                │                    │                   │
         │                │                    │                   │
         │                ▼                    ▼                   ▼
         │           ┌──────────┐        ┌──────────┐        ┌──────────┐
         │           │ ABORTED  │        │ RESUMING │        │  FAILED  │
         │           └──────────┘        └──────────┘        └──────────┘
         │                 ▲                    │                   │
         │                 │                    │                   │
         └─────────────────┴────────────────────┴───────────────────┘
                              (崩溃恢复 / 手动重启)

    状态说明：
    ─────────
    IDLE       : 初始状态，等待触发（用户请求 / Cron 唤醒）
    PLANNING   : 生成执行计划（execution_plan.json + tasks.json）
    EXECUTING  : 执行 Phase Worker（串行/并行 spawn 子 Agent）
    CHECKING   : Goal Checker 验证完成条件（loop_runner.py check）
    RESUMING   : 崩溃恢复，从 Checkpoint 重建状态
    DONE       : 终态，所有 Phase 完成，最终产物已生成
    FAILED     : 终态，达到 max_rounds 或不可恢复错误
    ABORTED    : 终态，用户主动取消或红线违规
```

### 2.2 状态转换规则（Pydantic 实现）

```python
# loop_state_machine.py

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class LoopState(str, Enum):
    """LoOP 生命周期状态。"""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    CHECKING = "checking"
    RESUMING = "resuming"
    DONE = "done"
    FAILED = "failed"
    ABORTED = "aborted"

class TransitionRule(BaseModel):
    """状态转换规则。"""
    from_state: LoopState
    to_state: LoopState
    condition: str  # 自然语言描述，LLM 可读
    guard: Optional[str] = None  # Python 表达式，确定性检查

# 合法转换表
VALID_TRANSITIONS = [
    # 正常流程
    TransitionRule(
        from_state=LoopState.IDLE,
        to_state=LoopState.PLANNING,
        condition="用户请求触发或 Cron 唤醒",
        guard="len(pending_tasks) > 0"
    ),
    TransitionRule(
        from_state=LoopState.PLANNING,
        to_state=LoopState.EXECUTING,
        condition="执行计划已生成且验证通过",
        guard="execution_plan.exists() and tasks.exists()"
    ),
    TransitionRule(
        from_state=LoopState.EXECUTING,
        to_state=LoopState.CHECKING,
        condition="当前 Phase 的 Worker 完成（子 Agent 返回）",
        guard="all(worker.completed for worker in current_phase.workers)"
    ),
    TransitionRule(
        from_state=LoopState.CHECKING,
        to_state=LoopState.DONE,
        condition="Goal Checker 判定完成（所有 Phase 完成 + 最终产物存在）",
        guard="goal_checker.check() == 'done'"
    ),
    TransitionRule(
        from_state=LoopState.CHECKING,
        to_state=LoopState.EXECUTING,
        condition="Goal Checker 判定未完成，继续下一 Phase",
        guard="goal_checker.check() == 'continue'"
    ),
    TransitionRule(
        from_state=LoopState.CHECKING,
        to_state=LoopState.FAILED,
        condition="达到 max_rounds 或不可恢复错误",
        guard="round_num >= max_rounds or fatal_error"
    ),
    
    # 崩溃恢复
    TransitionRule(
        from_state=LoopState.EXECUTING,
        to_state=LoopState.RESUMING,
        condition="检测到崩溃（进程重启 / Heartbeat 发现状态不一致）",
        guard="crash_detector.detect()"
    ),
    TransitionRule(
        from_state=LoopState.RESUMING,
        to_state=LoopState.EXECUTING,
        condition="从 Checkpoint 恢复成功，继续执行",
        guard="checkpoint.restore() == 'ok'"
    ),
    
    # 中止
    TransitionRule(
        from_state=LoopState.PLANNING,
        to_state=LoopState.ABORTED,
        condition="用户主动取消或红线违规",
        guard="user_cancelled or redline_violated"
    ),
    TransitionRule(
        from_state=LoopState.EXECUTING,
        to_state=LoopState.ABORTED,
        condition="用户主动取消或红线违规",
        guard="user_cancelled or redline_violated"
    ),
]

class LoopStateMachine(BaseModel):
    """LoOP 状态机。"""
    current_state: LoopState = LoopState.IDLE
    round_num: int = 0
    max_rounds: int = 5
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def transition(self, to_state: LoopState, context: dict) -> bool:
        """执行状态转换。"""
        # 查找合法转换规则
        rule = next(
            (r for r in VALID_TRANSITIONS 
             if r.from_state == self.current_state and r.to_state == to_state),
            None
        )
        
        if not rule:
            raise ValueError(
                f"非法状态转换: {self.current_state} → {to_state}"
            )
        
        # 执行 Guard 检查（确定性）
        if rule.guard:
            guard_result = eval(rule.guard, {}, context)
            if not guard_result:
                raise ValueError(
                    f"Guard 检查失败: {rule.guard}\n"
                    f"状态转换: {rule.from_state} → {rule.to_state}\n"
                    f"条件: {rule.condition}"
                )
        
        # 执行转换
        self.current_state = to_state
        
        # 记录时间戳
        if to_state == LoopState.PLANNING and self.round_num == 0:
            self.started_at = datetime.now()
        elif to_state in [LoopState.DONE, LoopState.FAILED, LoopState.ABORTED]:
            self.completed_at = datetime.now()
        
        if to_state == LoopState.EXECUTING:
            self.round_num += 1
        
        return True
```

### 2.3 状态机可视化（ASCII 时序图）

```
时间轴 →

T0          T1          T2          T3          T4          T5
│           │           │           │           │           │
▼           ▼           ▼           ▼           ▼           ▼
┌─────┐    ┌──────┐    ┌───────┐    ┌──────┐    ┌──────┐    ┌─────┐
│IDLE │───▶│PLAN  │───▶│EXEC   │───▶│CHECK │───▶│EXEC  │───▶│DONE │
└─────┘    └──────┘    └───────┘    └──────┘    └──────┘    └─────┘
                │           │           │           │
                │           ▼           │           │
                │        ┌───────┐      │           │
                │        │RESUME │──────┘           │
                │        └───────┘                  │
                │                                   │
                ▼                                   ▼
             ┌───────┐                          ┌──────┐
             │ABORTED│                          │FAILED│
             └───────┘                          └──────┘

典型场景：
─────────
场景 1: 正常完成
  IDLE → PLANNING → EXECUTING → CHECKING → DONE

场景 2: 多轮执行
  IDLE → PLANNING → EXECUTING → CHECKING → EXECUTING → CHECKING → DONE
                         (Round 1)          (Round 2)

场景 3: 崩溃恢复
  IDLE → PLANNING → EXECUTING → [崩溃] → RESUMING → EXECUTING → CHECKING → DONE

场景 4: 达到上限
  IDLE → PLANNING → EXECUTING → CHECKING → ... → CHECKING → FAILED
                                               (Round 5, max_rounds=5)
```

---

## 三、Tick 机制：Heartbeat/Cron 唤醒时的行为

### 3.1 Tick 触发源

```
┌─────────────────────────────────────────────────────────────┐
│                    Tick Trigger Sources                      │
└─────────────────────────────────────────────────────────────┘

    ┌──────────┐      ┌──────────┐      ┌──────────┐
    │  Cron    │      │ Heartbeat│      │  User    │
    │  Wake    │      │  Cycle   │      │  Request │
    └────┬─────┘      └────┬─────┘      └────┬─────┘
         │                 │                 │
         └─────────────────┴─────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Tick Event │
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ Loop Engine │
                    │   .tick()   │
                    └─────────────┘
```

### 3.2 Tick 处理流程

```python
# loop_engine.py

class LoopEngine:
    """LoOP 核心引擎。"""
    
    def __init__(self, domain: str, base_path: str):
        self.domain = domain
        self.base_path = Path(base_path)
        self.state_machine = LoopStateMachine()
        self.checkpoint = CheckpointManager(base_path)
        self.goal_checker = GoalChecker(domain, base_path)
    
    async def tick(self) -> TickResult:
        """
        每次 Heartbeat/Cron 唤醒时调用。
        
        输入: 无（从 Checkpoint 恢复状态）
        输出: TickResult（决策 + 动作）
        """
        
        # Step 1: 加载状态（从 pipeline_state.json）
        state = self.checkpoint.load()
        self.state_machine.current_state = state.status
        
        # Step 2: 崩溃检测（可选）
        if self._detect_crash(state):
            state.status = LoopState.RESUMING
            await self._recover_from_crash(state)
        
        # Step 3: 状态机驱动
        match state.status:
            case LoopState.IDLE:
                return await self._handle_idle(state)
            
            case LoopState.PLANNING:
                return await self._handle_planning(state)
            
            case LoopState.EXECUTING:
                return await self._handle_executing(state)
            
            case LoopState.CHECKING:
                return await self._handle_checking(state)
            
            case LoopState.RESUMING:
                return await self._handle_resuming(state)
            
            case LoopState.DONE | LoopState.FAILED | LoopState.ABORTED:
                return TickResult(action="noop", reason="终态，无需操作")
    
    async def _handle_idle(self, state: PipelineState) -> TickResult:
        """IDLE 状态：等待触发。"""
        # 检查是否有待处理任务
        pending = self._get_pending_tasks()
        
        if not pending:
            return TickResult(action="noop", reason="无待处理任务")
        
        # 转换到 PLANNING
        self.state_machine.transition(LoopState.PLANNING, {"pending_tasks": pending})
        
        # 生成执行计划
        plan = await self._generate_execution_plan(pending)
        self.checkpoint.save_plan(plan)
        
        return TickResult(
            action="plan_generated",
            next_state=LoopState.PLANNING,
            plan=plan
        )
    
    async def _handle_executing(self, state: PipelineState) -> TickResult:
        """EXECUTING 状态：执行当前 Phase。"""
        # 读取执行计划
        plan = self.checkpoint.load_plan()
        
        # 找到下一个未完成的 Phase
        next_phase = self._find_next_phase(plan, state)
        
        if not next_phase:
            # 所有 Phase 完成，转换到 CHECKING
            self.state_machine.transition(LoopState.CHECKING, {})
            return TickResult(action="check", next_state=LoopState.CHECKING)
        
        # 执行 Phase（spawn 子 Agent）
        if next_phase.parallel:
            # 并行 Phase：spawn 多个子 Agent
            tasks = [
                sessions_spawn(
                    runtime="subagent",
                    mode="run",
                    task=worker.prompt,
                    label=f"phase_{next_phase.num}_{worker.id}"
                )
                for worker in next_phase.workers
            ]
            await sessions_yield()  # 挂起等待完成
        else:
            # 串行 Phase：spawn 单个子 Agent
            task = sessions_spawn(
                runtime="subagent",
                mode="run",
                task=next_phase.prompt,
                label=f"phase_{next_phase.num}"
            )
            await sessions_yield()
        
        # 子 Agent 完成后，更新状态
        state.current_agent = next_phase.stage
        state.agents[next_phase.stage].state = "done"
        self.checkpoint.save_state(state)
        
        # 转换到 CHECKING
        self.state_machine.transition(LoopState.CHECKING, {})
        
        return TickResult(
            action="phase_completed",
            phase=next_phase.num,
            next_state=LoopState.CHECKING
        )
    
    async def _handle_checking(self, state: PipelineState) -> TickResult:
        """CHECKING 状态：Goal Checker 验证完成条件。"""
        # 调用 loop_runner.py check
        check_result = self.goal_checker.check(
            domain=self.domain,
            base_path=self.base_path,
            round_num=self.state_machine.round_num
        )
        
        match check_result["action"]:
            case "done":
                # 完成
                self.state_machine.transition(LoopState.DONE, {"goal_checker.check()": True})
                return TickResult(action="done", reason=check_result["reason"])
            
            case "resume":
                # 继续执行下一 Phase
                self.state_machine.transition(LoopState.EXECUTING, {})
                return TickResult(
                    action="resume",
                    next_phase=check_result["next_phase"],
                    next_state=LoopState.EXECUTING
                )
            
            case "abort":
                # 中止
                self.state_machine.transition(LoopState.FAILED, {"fatal_error": True})
                return TickResult(action="abort", reason=check_result["reason"])
    
    def _detect_crash(self, state: PipelineState) -> bool:
        """检测是否发生崩溃。"""
        # 策略 1: 状态不一致（EXECUTING 但无活跃子 Agent）
        if state.status == "running":
            active_agents = [a for a in state.agents.values() if a.state == "running"]
            if not active_agents:
                return True
        
        # 策略 2: 时间戳超时（EXECUTING 超过 30 分钟无更新）
        if state.started_at:
            elapsed = datetime.now() - datetime.fromisoformat(state.started_at)
            if elapsed.total_seconds() > 1800:  # 30 分钟
                return True
        
        return False
```

### 3.3 Tick 输入/输出契约

```python
class TickResult(BaseModel):
    """Tick 处理结果。"""
    
    action: Literal[
        "noop",              # 无需操作
        "plan_generated",    # 已生成执行计划
        "phase_completed",   # Phase 已完成
        "check",             # 需要检查
        "resume",            # 继续执行
        "done",              # 完成
        "abort"              # 中止
    ]
    
    next_state: Optional[LoopState] = None
    next_phase: Optional[int] = None
    reason: Optional[str] = None
    
    # 可观测性
    duration_ms: Optional[int] = None
    checkpoint_saved: bool = False
```

---

## 四、Checkpoint 设计：持久化与崩溃恢复

### 4.1 Checkpoint 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Checkpoint Layer                          │
└─────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────┐
    │  pipeline_state.json  (统一状态文件)                  │
    │  ─────────────────────────────────────────────────── │
    │  {                                                   │
    │    "run_id": "abc123",                               │
    │    "status": "running",                              │
    │    "current_agent": "researcher_technical",          │
    │    "round_num": 2,                                   │
    │    "agents": {                                       │
    │      "architect": {"state": "done", ...},            │
    │      "decomposer": {"state": "done", ...},           │
    │      "researcher_technical": {"state": "running",...}│
    │    },                                                │
    │    "started_at": "2026-06-24T10:00:00+08:00",        │
    │    "completed_at": null                              │
    │  }                                                   │
    └──────────────────────────────────────────────────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────┐
    │  execution_plan.json  (执行计划)                      │
    │  ─────────────────────────────────────────────────── │
    │  {                                                   │
    │    "phases": [                                       │
    │      {"phase": 1, "stage": "architect", ...},        │
    │      {"phase": 2, "stage": "decomposer", ...},       │
    │      ...                                             │
    │    ]                                                 │
    │  }                                                   │
    └──────────────────────────────────────────────────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────┐
    │  Blackboard (stages/*.json)  (Phase 产物)             │
    │  ─────────────────────────────────────────────────── │
    │  stages/                                             │
    │  ├── architect.json                                  │
    │  ├── decomposer.json                                 │
    │  ├── reviewer_technical.json                         │
    │  ├── reviewer_business.json                          │
    │  └── ...                                             │
    └──────────────────────────────────────────────────────┘
```

### 4.2 Checkpoint Manager 实现

```python
# checkpoint_manager.py

import json
from pathlib import Path
from pydantic import BaseModel
from typing import Optional

class CheckpointManager:
    """Checkpoint 管理器。"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.state_file = self.base_path / "pipeline_state.json"
        self.plan_file = self.base_path / "execution_plan.json"
    
    def load_state(self) -> "PipelineState":
        """加载状态。"""
        if not self.state_file.exists():
            return PipelineState(run_id="new")
        
        with open(self.state_file) as f:
            data = json.load(f)
        
        return PipelineState(**data)
    
    def save_state(self, state: "PipelineState") -> None:
        """保存状态（原子写入）。"""
        # 写入临时文件
        temp_file = self.state_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(state.dict(), f, indent=2, ensure_ascii=False)
        
        # 原子重命名（防止写入中断导致损坏）
        temp_file.rename(self.state_file)
    
    def load_plan(self) -> dict:
        """加载执行计划。"""
        if not self.plan_file.exists():
            raise FileNotFoundError("execution_plan.json not found")
        
        with open(self.plan_file) as f:
            return json.load(f)
    
    def save_plan(self, plan: dict) -> None:
        """保存执行计划。"""
        with open(self.plan_file, "w") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
    
    def create_snapshot(self) -> str:
        """创建快照（用于审计/调试）。"""
        import shutil
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self.base_path / f"snapshot_{timestamp}"
        snapshot_dir.mkdir()
        
        # 复制关键文件
        for src in [self.state_file, self.plan_file]:
            if src.exists():
                shutil.copy(src, snapshot_dir / src.name)
        
        # 复制 Blackboard
        stages_dir = self.base_path / "stages"
        if stages_dir.exists():
            shutil.copytree(stages_dir, snapshot_dir / "stages")
        
        return str(snapshot_dir)
```

### 4.3 崩溃恢复策略

```python
# crash_recovery.py

class CrashRecoveryStrategy:
    """崩溃恢复策略。"""
    
    def __init__(self, checkpoint: CheckpointManager):
        self.checkpoint = checkpoint
    
    def recover(self) -> "RecoveryResult":
        """
        恢复策略：
        1. 加载最后已知状态
        2. 验证状态一致性
        3. 回滚未完成的操作
        4. 恢复到安全状态
        """
        
        # Step 1: 加载状态
        state = self.checkpoint.load_state()
        
        # Step 2: 一致性检查
        issues = self._check_consistency(state)
        
        if not issues:
            # 状态一致，直接恢复
            return RecoveryResult(
                status="ok",
                resume_state=state,
                message="状态一致，可直接恢复"
            )
        
        # Step 3: 回滚未完成操作
        for issue in issues:
            if issue.type == "orphaned_worker":
                # Worker 已 spawn 但未完成
                # 策略：标记为 failed，让 Goal Checker 决定是否重试
                state.agents[issue.agent_name].state = "gate_fail"
                state.agents[issue.agent_name].last_gate_feedback = (
                    "崩溃恢复：Worker 未完成，需要重试"
                )
            
            elif issue.type == "missing_artifact":
                # Phase 标记为 done 但产物不存在
                # 策略：回滚到上一 Phase
                state.agents[issue.agent_name].state = "pending"
                state.current_agent = issue.agent_name
        
        # Step 4: 保存恢复后的状态
        self.checkpoint.save_state(state)
        
        return RecoveryResult(
            status="recovered",
            resume_state=state,
            issues_fixed=len(issues),
            message=f"已修复 {len(issues)} 个问题"
        )
    
    def _check_consistency(self, state: "PipelineState") -> list:
        """检查状态一致性。"""
        issues = []
        
        # 检查 1: 标记为 running 的 Agent 是否有产物
        for agent_name, agent_state in state.agents.items():
            if agent_state.state == "running":
                # 检查是否有对应的产物文件
                artifact = self._find_artifact(agent_name)
                if not artifact:
                    issues.append(ConsistencyIssue(
                        type="orphaned_worker",
                        agent_name=agent_name,
                        detail="Worker 标记为 running 但无产物"
                    ))
            
            elif agent_state.state == "done":
                # 检查产物是否存在
                artifact = self._find_artifact(agent_name)
                if not artifact:
                    issues.append(ConsistencyIssue(
                        type="missing_artifact",
                        agent_name=agent_name,
                        detail="Agent 标记为 done 但产物不存在"
                    ))
        
        return issues
```

### 4.4 与 pipeline_state.json 的关系

```
┌─────────────────────────────────────────────────────────────┐
│              pipeline_state.json 定位                        │
└─────────────────────────────────────────────────────────────┘

pipeline_state.json 是 LoOP 的 "Single Source of Truth"

    ┌──────────────────────────────────────────────────────┐
    │  旧架构（DeepFlow v1）                                │
    │  ─────────────────────────────────────────────────── │
    │  • pipeline_state.json: 管线状态（Agent 级别）        │
    │  • .completed: 完成标记                               │
    │  • stage_progress: Phase 进度                         │
    │  • Blackboard: Phase 产物                             │
    │                                                       │
    │  问题：状态分散在多个文件，难以一致性检查              │
    └──────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────┐
    │  新架构（LoOP v2）                                    │
    │  ─────────────────────────────────────────────────── │
    │  • pipeline_state.json: 唯一状态文件                  │
    │    - 包含 Loop 状态机状态                             │
    │    - 包含所有 Agent 状态                              │
    │    - 包含 Round 计数                                  │
    │    - 包含时间戳                                       │
    │  • execution_plan.json: 执行计划（只读）              │
    │  • Blackboard: Phase 产物（只读）                     │
    │                                                       │
    │  改进：单一状态文件，原子写入，崩溃安全                │
    └──────────────────────────────────────────────────────┘

关键原则：
─────────
1. 所有状态变更必须通过 pipeline_state.py CLI（禁止直接写文件）
2. 写入使用原子重命名（.tmp → .json）
3. Blackboard 是 "Write-Once, Read-Many"（产物一旦写入不可修改）
4. execution_plan.json 是 "Write-Once"（计划一旦生成不可修改）
```

---

## 五、与 OpenAI/Claude Agent Loop 的本质区别

### 5.1 架构对比

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OpenAI Agent Loop (单进程)                        │
└─────────────────────────────────────────────────────────────────────┘

    User Request
         │
         ▼
    ┌─────────────┐
    │ Runner.run()│◄──────────────────────┐
    │  while loop │                        │
    └─────────────┘                        │
         │                                 │
         ▼                                 │
    ┌─────────────┐                        │
    │  LLM Call   │──── Tool Calls ────────┤
    └─────────────┘                        │
         │                                 │
         ▼                                 │
    ┌─────────────┐                        │
    │ Tool Exec   │──── Results ───────────┘
    └─────────────┘
         │
         ▼ (no tool calls)
    ┌─────────────┐
    │ final_output│
    └─────────────┘

特点：
• 单进程，内存状态
• 秒级～分钟级生命周期
• 崩溃即丢失，无法恢复
• 不支持并行（顺序执行 tool calls）
```

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Claude Agent Loop (单进程 + Hooks)                │
└─────────────────────────────────────────────────────────────────────┘

    User Request
         │
         ▼
    ┌─────────────┐
    │  Turn-based │◄──────────────────────┐
    │    Loop     │                        │
    └─────────────┘                        │
         │                                 │
         ▼                                 │
    ┌─────────────┐                        │
    │ Claude eval │──── Tool Calls ────────┤
    │   prompt    │                        │
    └─────────────┘                        │
         │                                 │
         ▼                                 │
    ┌─────────────┐                        │
    │ Hook: Pre   │ (拦截/修改/阻断)       │
    │ Tool Exec   │                        │
    │ Hook: Post  │                        │
    └─────────────┘                        │
         │                                 │
         ▼ (no tool calls)                 │
    ┌─────────────┐                        │
    │   /goal     │ (Goal Checker)         │
    │   check     │────────────────────────┘
    └─────────────┘

特点：
• 单进程，内存状态
• 支持 Hooks（拦截 tool calls）
• 支持 /goal（可验证终止条件）
• 支持 automatic compaction（上下文压缩）
• 仍然崩溃即丢失
```

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OpenClaw LoOP (分布式跨 Session)                  │
└─────────────────────────────────────────────────────────────────────┘

    Cron/Heartbeat/User Request
         │
         ▼
    ┌─────────────────┐
    │  Main Agent     │
    │  (Loop Engine)  │
    └─────────────────┘
         │
         ├────────────────────────────────────┐
         │                                    │
         ▼                                    ▼
    ┌─────────────────┐              ┌─────────────────┐
    │ Checkpoint Load │              │ Goal Checker    │
    │ (pipeline_state)│              │ (loop_runner.py)│
    └─────────────────┘              └─────────────────┘
         │                                    │
         └────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  State Machine Tick   │
              │  (IDLE→PLAN→EXEC→...) │
              └───────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Worker 1│     │ Worker 2│     │ Worker 3│
    │ (spawn) │     │ (spawn) │     │ (spawn) │
    └─────────┘     └─────────┘     └─────────┘
         │                │                │
         ▼                ▼                ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │Artifact1│     │Artifact2│     │Artifact3│
    │(Blackboard)    │(Blackboard)    │(Blackboard)
    └─────────┘     └─────────┘     └─────────┘
         │                │                │
         └────────────────┴────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  Checkpoint Save      │
              │  (pipeline_state.json)│
              └───────────────────────┘

特点：
• 分布式，跨 Session
• 磁盘状态（崩溃安全）
• 小时级～天级生命周期
• 支持并行（多 Worker spawn）
• 支持崩溃恢复（Checkpoint）
• 支持定时唤醒（Cron/Heartbeat）
```

### 5.2 优势与挑战

| 维度 | OpenClaw LoOP 优势 | OpenClaw LoOP 挑战 |
|------|-------------------|-------------------|
| **持久性** | ✅ 崩溃恢复，断点续传 | ❌ 磁盘 I/O 开销 |
| **生命周期** | ✅ 天级长任务 | ❌ 状态一致性维护复杂 |
| **并发** | ✅ 多 Worker 并行 | ❌ 并发冲突需处理 |
| **可观测性** | ✅ 完整审计轨迹 | ❌ 调试跨 Session 困难 |
| **灵活性** | ✅ 支持 Cron/Heartbeat | ❌ 状态机设计复杂 |

---

## 六、创新性设计：OpenClaw 独有特性

### 6.1 特性一：Goal-as-a-Service (GaaS) — 可组合的终止条件

**业界现状**：
- OpenAI: `max_turns`（简单计数）
- Claude: `/goal` 命令（自然语言描述，LLM 判断）
- LangGraph: 条件边（代码逻辑）

**OpenClaw 创新**：
将 Goal Checker 抽象为 **可组合的服务**，支持声明式定义终止条件。

```yaml
# goal_definition.yaml

goal:
  name: "完成企业知识库系统架构设计"
  
  # 硬性条件（必须全部满足）
  hard_conditions:
    - id: "HC-001"
      type: "file_exists"
      path: "final_result.json"
      description: "最终产物存在"
    
    - id: "HC-002"
      type: "all_phases_done"
      description: "所有 10 个 Phase 完成"
    
    - id: "HC-003"
      type: "quality_gate_pass"
      threshold: 0.8
      description: "质量门禁得分 ≥ 0.8"
  
  # 软性条件（尽量满足，可权衡）
  soft_conditions:
    - id: "SC-001"
      type: "llm_judge"
      prompt: "架构设计是否包含高可用方案？"
      weight: 0.3
      description: "LLM 评判架构完整性"
    
    - id: "SC-002"
      type: "coverage_check"
      target: "requirements.txt"
      weight: 0.2
      description: "需求覆盖率"
  
  # 终止策略
  termination:
    strategy: "hard_must_pass_soft_weighted_sum"
    soft_threshold: 0.6  # 软性条件加权得分 ≥ 0.6
    max_rounds: 5
    timeout_hours: 24
```

```python
# goal_checker.py

class GoalChecker:
    """可组合的 Goal Checker。"""
    
    def __init__(self, goal_def_path: str):
        with open(goal_def_path) as f:
            self.goal_def = yaml.safe_load(f)
    
    def check(self, context: dict) -> GoalResult:
        """检查终止条件。"""
        
        # Step 1: 检查硬性条件
        hard_results = []
        for cond in self.goal_def["hard_conditions"]:
            result = self._check_condition(cond, context)
            hard_results.append(result)
        
        all_hard_pass = all(r.passed for r in hard_results)
        
        if not all_hard_pass:
            return GoalResult(
                decision="continue",
                reason=f"硬性条件未满足: {[r for r in hard_results if not r.passed]}",
                hard_results=hard_results
            )
        
        # Step 2: 检查软性条件（加权求和）
        soft_results = []
        weighted_sum = 0.0
        
        for cond in self.goal_def["soft_conditions"]:
            result = self._check_condition(cond, context)
            soft_results.append(result)
            weighted_sum += result.score * cond.get("weight", 0.0)
        
        soft_threshold = self.goal_def["termination"]["soft_threshold"]
        soft_pass = weighted_sum >= soft_threshold
        
        # Step 3: 综合决策
        if all_hard_pass and soft_pass:
            return GoalResult(
                decision="done",
                reason="所有硬性条件 + 软性条件阈值达成",
                hard_results=hard_results,
                soft_results=soft_results,
                weighted_score=weighted_sum
            )
        else:
            return GoalResult(
                decision="continue",
                reason=f"软性条件未达阈值: {weighted_sum:.2f} < {soft_threshold}",
                soft_results=soft_results,
                weighted_score=weighted_sum
            )
    
    def _check_condition(self, condition: dict, context: dict) -> ConditionResult:
        """检查单个条件。"""
        cond_type = condition["type"]
        
        match cond_type:
            case "file_exists":
                path = Path(condition["path"])
                return ConditionResult(
                    passed=path.exists(),
                    score=1.0 if path.exists() else 0.0
                )
            
            case "all_phases_done":
                state = context["pipeline_state"]
                total = state.total_phases
                done = len([a for a in state.agents.values() if a.state == "done"])
                return ConditionResult(
                    passed=done == total,
                    score=done / total
                )
            
            case "quality_gate_pass":
                # 调用 Harness 评分
                score = self._run_harness(context)
                threshold = condition["threshold"]
                return ConditionResult(
                    passed=score >= threshold,
                    score=score
                )
            
            case "llm_judge":
                # 调用 LLM 评判
                prompt = condition["prompt"]
                score = self._llm_judge(prompt, context)
                return ConditionResult(
                    passed=score >= 0.7,  # LLM 评判阈值
                    score=score
                )
            
            case "coverage_check":
                # 需求覆盖率检查
                target = condition["target"]
                score = self._check_coverage(target, context)
                return ConditionResult(passed=score >= 0.8, score=score)
```

**创新点**：
1. **声明式定义**：用 YAML 描述终止条件，非代码
2. **硬性 + 软性**：硬性必须满足，软性可权衡
3. **可组合**：支持文件存在、Phase 完成、质量门禁、LLM 评判等多种条件类型
4. **可审计**：每次检查生成详细报告，哪些条件通过/未通过

---

### 6.2 特性二：Temporal-Like Recovery — 基于事件溯源的崩溃恢复

**业界现状**：
- OpenAI/Claude: 无恢复（崩溃即丢失）
- Temporal: Event Sourcing（事件溯源，重放历史）
- LangGraph: Checkpoint（但不支持事件重放）

**OpenClaw 创新**：
结合 Temporal 的 Event Sourcing 和 OpenClaw 的 Blackboard，实现 **可审计的崩溃恢复**。

```python
# event_sourcing.py

from dataclasses import dataclass
from datetime import datetime
from typing import Any

@dataclass
class LoopEvent:
    """LoOP 事件（不可变）。"""
    event_id: str
    event_type: str  # "phase_started", "phase_completed", "worker_spawned", ...
    timestamp: datetime
    data: dict[str, Any]
    checkpoint_snapshot: Optional[str] = None  # 快照路径

class EventStore:
    """事件存储（追加写入）。"""
    
    def __init__(self, base_path: str):
        self.event_log = Path(base_path) / "event_log.jsonl"
    
    def append(self, event: LoopEvent) -> None:
        """追加事件（原子写入）。"""
        with open(self.event_log, "a") as f:
            f.write(json.dumps(event.__dict__, default=str) + "\n")
    
    def load_history(self) -> list[LoopEvent]:
        """加载事件历史。"""
        if not self.event_log.exists():
            return []
        
        events = []
        with open(self.event_log) as f:
            for line in f:
                data = json.loads(line)
                events.append(LoopEvent(**data))
        
        return events

class TemporalRecovery:
    """Temporal-Like Recovery。"""
    
    def __init__(self, event_store: EventStore, checkpoint: CheckpointManager):
        self.event_store = event_store
        self.checkpoint = checkpoint
    
    def recover(self) -> "RecoveryResult":
        """
        恢复策略：
        1. 加载事件历史
        2. 重放事件，重建状态
        3. 与 Checkpoint 对比，找到不一致
        4. 回滚未完成事件
        5. 恢复到安全状态
        """
        
        # Step 1: 加载事件历史
        events = self.event_store.load_history()
        
        # Step 2: 重放事件，重建状态
        reconstructed_state = PipelineState(run_id="reconstructed")
        
        for event in events:
            match event.event_type:
                case "phase_started":
                    phase = event.data["phase"]
                    reconstructed_state.agents[phase] = AgentState(state="running")
                
                case "phase_completed":
                    phase = event.data["phase"]
                    reconstructed_state.agents[phase].state = "done"
                
                case "worker_spawned":
                    worker_id = event.data["worker_id"]
                    # 记录 Worker 已 spawn
                
                case "checkpoint_saved":
                    snapshot_path = event.data["snapshot_path"]
                    # 记录 Checkpoint
        
        # Step 3: 加载最后 Checkpoint
        checkpoint_state = self.checkpoint.load_state()
        
        # Step 4: 对比，找不一致
        inconsistencies = self._find_inconsistencies(
            reconstructed_state,
            checkpoint_state
        )
        
        # Step 5: 回滚未完成事件
        for issue in inconsistencies:
            if issue.type == "worker_spawned_but_not_completed":
                # Worker 已 spawn 但未完成
                # 策略：标记为 failed，让 Goal Checker 决定是否重试
                reconstructed_state.agents[issue.agent_name].state = "gate_fail"
        
        # Step 6: 保存恢复后的状态
        self.checkpoint.save_state(reconstructed_state)
        
        return RecoveryResult(
            status="recovered",
            events_replayed=len(events),
            inconsistencies_fixed=len(inconsistencies),
            resume_state=reconstructed_state
        )
```

**创新点**：
1. **事件溯源**：所有状态变更记录为事件（追加写入，不可变）
2. **可重放**：崩溃后重放事件历史，重建状态
3. **可审计**：完整执行轨迹，便于调试和合规
4. **与 Checkpoint 结合**：事件重放 + Checkpoint 快照，双重保障

---

## 七、总结与展望

### 7.1 核心架构总结

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw LoOP 核心架构                        │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────────┐
    │  Layer 4: Application Layer (应用层)                      │
    │  ─────────────────────────────────────────────────────── │
    │  • DeepFlow Pipeline (Solution Pro / Ship Pro / ...)     │
    │  • Custom Workflows (用户自定义)                          │
    └──────────────────────────────────────────────────────────┘
                              ▲
                              │
    ┌──────────────────────────────────────────────────────────┐
    │  Layer 3: Goal Layer (目标层)                             │
    │  ─────────────────────────────────────────────────────── │
    │  • Goal-as-a-Service (GaaS)                              │
    │  • Hard/Soft Conditions, LLM Judge, Quality Gates        │
    └──────────────────────────────────────────────────────────┘
                              ▲
                              │
    ┌──────────────────────────────────────────────────────────┐
    │  Layer 2: State Machine Layer (状态机层)                  │
    │  ─────────────────────────────────────────────────────── │
    │  • Loop State Machine (IDLE→PLAN→EXEC→CHECK→DONE)        │
    │  • Tick Engine (Heartbeat/Cron 唤醒)                      │
    │  • Event Sourcing (事件溯源)                              │
    └──────────────────────────────────────────────────────────┘
                              ▲
                              │
    ┌──────────────────────────────────────────────────────────┐
    │  Layer 1: Persistence Layer (持久化层)                    │
    │  ─────────────────────────────────────────────────────── │
    │  • Checkpoint Manager (pipeline_state.json)              │
    │  • Event Store (event_log.jsonl)                         │
    │  • Blackboard (stages/*.json)                            │
    └──────────────────────────────────────────────────────────┘
```

### 7.2 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **状态存储** | 磁盘（JSON） | 崩溃安全，支持天级长任务 |
| **并发模型** | 多 Session 并行 | 利用 OpenClaw `sessions_spawn` |
| **恢复策略** | Event Sourcing + Checkpoint | 可审计，可重放 |
| **终止条件** | Goal-as-a-Service | 声明式，可组合 |
| **唤醒机制** | Cron/Heartbeat | 支持定时任务，无需人工值守 |

### 7.3 未来展望

1. **可视化 Dashboard**：实时展示 LoOP 状态、事件流、Worker 进度
2. **分布式 Lock**：支持多 Main Agent 并发执行同一 LoOP（需分布式锁）
3. **自适应调度**：根据历史执行数据，动态调整 max_rounds、timeout
4. **跨平台 LoOP**：支持在多个 OpenClaw 实例间迁移 LoOP（需状态序列化）

---

## 附录：代码示例索引

| 文件 | 说明 |
|------|------|
| `loop_state_machine.py` | 状态机定义 + 转换规则 |
| `loop_engine.py` | Tick 处理逻辑 |
| `checkpoint_manager.py` | Checkpoint 管理 |
| `crash_recovery.py` | 崩溃恢复策略 |
| `goal_checker.py` | Goal-as-a-Service 实现 |
| `event_sourcing.py` | 事件溯源 + Temporal-Like Recovery |

---

*文档版本: 1.0.0*  
*最后更新: 2026-06-24*  
*字数: 约 2400 字*
