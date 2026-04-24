# DeepFlow 0.1.0 协议层说明书

> **历史文档**: 本文档为 V3.0 设计阶段的历史记录，当前实现见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
> **当前版本**: 0.1.0 (V4.0 内部代号)

> 方案 D：External Coordinator 模式
> 
> 基于 OpenClaw 官方 Agent 执行模型，实现真正的多 Agent 协作

---

## 1. 架构概述

### 1.1 设计目标

- **真正的多 Agent 并行**：每个 Agent 独立 spawn，真实执行
- **Agent 完全控制**：主 Agent 决定何时 spawn、如何处理结果
- **状态持久化**：通过 Blackboard 在多次调用间保持状态
- **符合 OpenClaw 约束**：不违反任何官方限制

### 1.2 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                      主 Agent (Main)                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │ Coordinator │    │ sessions_   │    │ sessions_yield  │  │
│  │  .start()   │───→│   spawn()   │───→│   (等待结果)     │  │
│  │  .resume()  │←───│             │←───│                 │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│         ↑                                                   │
│         │              ┌──────────────┐                     │
│         └──────────────│ Blackboard   │                     │
│                        │ (状态持久化)  │                     │
│                        └──────────────┘                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   PipelineEngine                            │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐     │
│  │  plan   │ → │ execute │ → │ critique│ → │  fix    │ ... │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘     │
│       ↑                                            │        │
│       └──────────── step() ────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 核心接口

### 2.1 Coordinator 接口

```python
class Coordinator:
    async def start(
        self,
        user_input: str,
        session_id: Optional[str] = None,
    ) -> ExecutionStatus:
        """
        开始新任务
        
        执行到第一个 Agent 阶段或完成，返回状态
        """
        
    async def resume(
        self,
        session_id: str,
        agent_results: List[AgentResult],
    ) -> ExecutionStatus:
        """
        注入 Agent 结果，继续执行
        
        继续执行管线，直到下一个 Agent 阶段或完成
        """
```

### 2.2 数据结构

#### ExecutionStatus

```python
@dataclass
class ExecutionStatus:
    state: str  # "RUNNING" | "WAITING_AGENT" | "WAITING_HITL" | "COMPLETED" | "FAILED"
    session_id: str
    domain: str
    pending_requests: List[Dict]  # Agent 执行请求
    completed_stages: List[str]   # 已完成阶段
    iteration: int
    quality_score: float
    final_result: Optional[ExecutionResult]  # 仅当 COMPLETED
    error: Optional[str]  # 仅当 FAILED
    blackboard_path: Optional[str]  # Blackboard 路径
```

#### AgentRequest / AgentResult

```python
@dataclass
class AgentRequest:
    request_id: str
    agent_role: str
    stage_id: str
    instance_name: str
    angle: str
    prompt: str
    model: str
    input_context: str
    timeout: int

@dataclass
class AgentResult:
    request_id: str
    success: bool
    output_file: Optional[str]
    score: float  # 质量分数（0-100 尺度），与 QualityGate/ExecutionStatus 保持一致
    error: Optional[str]
```

---

## 3. 执行流程

### 3.1 典型流程

```
第1轮：开始执行
├─ Agent: Coordinator.start("分析茅台")
├─ Python: 执行到第一个 Agent 阶段
└─ 返回: {state: "WAITING_AGENT", pending_requests: [...]}

第2轮：执行 Agent
├─ Agent: 遍历 pending_requests
├─ Agent: 对每个 request 调用 sessions_spawn()
├─ Agent: 收集所有结果
└─ Agent: Coordinator.resume(session_id, results)

第3轮：继续执行
├─ Python: 注入结果，继续执行
├─ Python: 执行到下一个 Agent 阶段或完成
└─ 返回: {state: "COMPLETED", final_result: {...}} 或再次 WAITING_AGENT

[循环直到完成]
```

### 3.2 状态转换

```
                    start()
                      │
                      ▼
┌─────────┐    ┌─────────────┐    ┌─────────────┐
│  INIT   │───→│   RUNNING   │───→│ WAITING_    │
└─────────┘    └─────────────┘    │   AGENT     │
                      │           └──────┬──────┘
                      │                  │
                      ▼                  │ resume()
               ┌─────────────┐          │
               │  COMPLETED  │←─────────┘
               └─────────────┘
                      ▲
                      │
               ┌─────────────┐
               │   FAILED    │
               └─────────────┘
```

---

## 4. 使用示例

### 4.1 基础使用

```python
from coordinator import Coordinator, AgentResult

async def main():
    coordinator = Coordinator()
    
    # 第1轮：开始执行
    status = await coordinator.start("分析茅台")
    
    while not status.is_completed:
        if status.is_waiting_agent:
            # 执行所有 pending Agent
            results = []
            for req in status.pending_requests:
                # 调用 sessions_spawn 执行
                result = await sessions_spawn(
                    runtime="subagent",
                    mode="run",
                    task=req["prompt"],
                    timeout_seconds=req["timeout"],
                )
                results.append(AgentResult(
                    request_id=req["request_id"],
                    success=True,
                    output_file=result.get("output_file"),
                    score=result.get("score", 0.0),
                ))
            
            # 注入结果，继续执行
            status = await coordinator.resume(status.session_id, results)
        else:
            # 其他状态，继续执行
            status = await coordinator._resume_execution(status.session_id)
    
    # 完成
    print(status.final_result.output)
```

### 4.2 错误处理

```python
async def main_with_error_handling():
    coordinator = Coordinator()
    
    try:
        status = await coordinator.start("分析茅台")
        
        while not status.is_completed:
            if status.state == "FAILED":
                print(f"执行失败: {status.error}")
                break
                
            if status.is_waiting_agent:
                results = []
                for req in status.pending_requests:
                    try:
                        result = await execute_agent(req)
                        results.append(result)
                    except Exception as e:
                        # 记录错误但继续
                        results.append(AgentResult(
                            request_id=req["request_id"],
                            success=False,
                            error=str(e),
                        ))
                
                status = await coordinator.resume(status.session_id, results)
            else:
                status = await coordinator._resume_execution(status.session_id)
                
    except Exception as e:
        print(f"异常: {e}")
```

---

## 5. 关键设计决策

### 5.1 为什么使用文件-based Blackboard？

| 方案 | 优点 | 缺点 | 选择 |
|:---|:---|:---|:---:|
| 内存状态 | 快速 | Python 执行后丢失 | ❌ |
| 数据库 | 持久化 | 增加复杂度 | ❌ |
| **文件 Blackboard** | 持久化、简单、可观测 | I/O 开销 | ✅ |

### 5.2 为什么 callback 返回 pending 而不是直接执行？

```python
# ❌ 直接执行（违反 OpenClaw 约束）
async def callback(...):
    result = await sessions_spawn(...)  # 在 Python 中调用工具，不可用
    return result

# ✅ 收集请求，主 Agent 执行
async def callback(...):
    pending_requests.append(request)  # 收集请求
    return {"error": "PENDING"}  # 返回 pending

# 主 Agent 中执行
for req in status.pending_requests:
    result = await sessions_spawn(...)  # ✅ Agent 工具调用
```

### 5.3 为什么使用 step() 而不是 run()？

```python
# ❌ run() 模式：一次性执行完
result = await engine.run()  # 执行所有 stages，阻塞直到完成

# ✅ step() 模式：分步执行
while True:
    step_result = await engine.step()  # 只执行一个 stage
    if step_result["done"]:
        break
    if step_result.get("state") == "WAITING_AGENT":
        # 返回控制给主 Agent
        return ExecutionStatus(...)
```

---

## 6. 约束与限制

### 6.1 OpenClaw 官方约束

| 约束 | 影响 | 应对 |
|:---|:---|:---|
| `sessions_spawn` 只能在 Agent Run | Python 代码不能直接调用 | 使用 callback 收集请求模式 |
| Agent 执行 Python 时被阻塞 | 不能异步等待 | 每次调用后立即返回 |
| Session 序列化 | 同一 session 不能并行 | 符合， Coordinator 单线程 |
| Max spawn depth = 1 | 子 Agent 不能 spawn | 设计时避免嵌套 spawn |

### 6.2 当前限制

1. **PipelineEngine 需要 `step()` 支持**：当前部分 fallback 到 `run()`
2. **错误恢复**：复杂错误场景的处理待完善
3. **并发优化**：多个 pending request 可以并行 spawn

---

## 7. 调试与观测

### 7.1 Blackboard 结构

```
/tmp/deepflow/{session_id}/
├── blackboard/
│   ├── context.json        # 共享状态
│   ├── stages.json         # 阶段记录
│   ├── quality_scores.json # 质量分数
│   └── convergence.json    # 收敛状态
├── outputs/
│   └── *.md               # Agent 输出文件
└── checkpoints/
    └── iteration_*.json   # 检查点
```

### 7.2 日志

```python
# 启用调试日志
from observability import Observability
Observability.set_level("DEBUG")

# 查看 Coordinator 日志
logger = Observability.get_logger("coordinator")
```

---

## 8. 未来扩展

### 8.1 计划功能

- [ ] 并行 spawn 优化（同时 spawn 多个 pending requests）
- [ ] 更细粒度的 step（stage 内 step）
- [ ] 更好的错误恢复机制
- [ ] 支持暂停/恢复长任务

### 8.2 可能的优化

- [ ] 使用数据库替代文件 Blackboard
- [ ] 缓存 Agent 结果避免重复执行
- [ ] 动态调整并发度

---

## 9. 参考

- OpenClaw 官方文档：`docs/openclaw-official/`
- Coordinator 实现：`.deepflow/coordinator.py`
- PipelineEngine 实现：`.deepflow/pipeline_engine.py`
- 演示脚本：`.deepflow/demo_mode_d.py`

---

**版本**: V3.0 方案 D  
**日期**: 2026-04-15  
**作者**: 小满
