from core.blackboard.blackboard_manager import BlackboardManager
import os

bb = BlackboardManager('OpenClaw AI Native Loop Engineering Framework')
experts_dir = os.path.join(str(bb.session_dir), 'stages', 'research_experts')
os.makedirs(experts_dir, exist_ok=True)

report_content = """# Fractal Loop 架构师 研究报告

## 研究范围

本报告围绕 OpenClaw AI Native Loop Engineering Framework 的分形 Loop 架构展开深度研究，覆盖以下五个核心问题：

1. **分形中断级联传播机制**：Interrupt 如何在 Project Loop → Domain Loop → Phase Loop 三层之间传播，业界参考实现及延迟上限
2. **DAG 分解的非对称验证（UC-011）**：分解者与验证者分离的 LLM session 设计，prompt 策略与验证 rubric
3. **并发上限下的资源配额隔离（UC-004, REQ-006, REQ-034）**：max 6 子 Agent 场景下的 token/时间/工具配额方案
4. **resume 操作幂等性（UC-005, REQ-024）**：状态快照格式、checkpoint 频率、crash recovery 流程
5. **happens-before 关系在 DAG 拓扑排序中的正确性（UC-003, REQ-010）**：向量时钟 vs Lamport 时间戳的选择

覆盖需求：REQ-001, REQ-006, REQ-010, REQ-024, REQ-033, REQ-034, REQ-042, REQ-076, REQ-077, REQ-078

---

## 发现与分析

### Finding 1: 分形中断（Fractal Interrupt）在三层 Loop 中的级联传播机制

#### 问题定义

OpenClaw 的分形 Loop 架构包含三层嵌套：外 Loop（Project Loop）、中 Loop（Domain Loop）、内 Loop（Phase Loop）。当一个中断信号（如用户取消、子 Agent 失败、Zone 0 安全违规）产生时，它需要在三层之间正确传播——既要能从上向下级联取消，也要能从下向上冒泡报告。

#### 业界参考实现分析

**Temporal Workflow（推荐参考，v2.x 系列）**

Temporal 提供了最成熟的级联中断机制，其核心原语包括：

- **Cancellation（优雅取消）**：Temporal Service 记录 `WorkflowExecutionCancelRequested` 事件，调度一个 Workflow Task，允许 Workflow 代码执行清理逻辑。在 Java SDK 中，cancellation scope 从外部向内部传播，主 Workflow 方法运行在根 scope 中，当收到取消请求时根 scope 被取消。
- **Termination（强制终止）**：类似 `kill -9`，记录 `WorkflowExecutionTerminated` 事件，Workflow 代码无法处理终止。用于 Workflow 卡死的场景。
- **ParentClosePolicy（父子关闭策略）**：这是级联传播的核心控制机制，有三种策略：
  - `PARENT_CLOSE_POLICY_TERMINATE`：子 Workflow 立即终止
  - `PARENT_CLOSE_POLICY_ABANDON`：子 Workflow 不感知父 Workflow 关闭，继续执行
  - `PARENT_CLOSE_POLICY_REQUEST_CANCEL`：子 Workflow 收到取消请求，可优雅清理
- **Signal 机制**：异步信号发送到运行中的 Workflow，有顺序保证但"fire and forget"。2025年1月 GA 的 Workflow Update 机制支持同步调用并可返回值/错误。

**延迟基准数据**（来源：Temporal 官方 benchmark，2024年5月 & 2025年9月更新）：
- `SignalWorkflowExecution` p50 延迟：Temporal Cloud 7.64ms，自托管 17.5ms
- Workflow 创建约 160ms，Task 等待约 300ms
- 端到端最低延迟：Temporal Cloud ~100ms
- Eager Workflow Start 实验特性：p50 16.7ms（eager） vs 29.3ms（non-eager）

**AWS Step Functions（次要参考）**

AWS Step Functions 提供 Catch/Retry 机制用于错误传播：
- `Retry` 配置：`IntervalSeconds`、`MaxAttempts`、`BackoffRate`、`JitterStrategy`（防止雷群效应）
- `Catch` 配置：指定错误名称和 fallback state
- 嵌套 Workflow 错误传播：通过嵌套状态机实现 Catch 传播，或使用 Lambda Wrapper 转换错误类型
- Distributed Map 的 `ToleratedFailureThreshold`：可定义失败阈值，超出后整个 Map Run 失败
- 2023年11月引入的 `redrive` 功能：可从失败点重启，而非重跑整个流程

**Prefect v3（2024年9月 GA，参考对比）**

Prefect v3 采用了不同的设计哲学：
- 从严格 DAG 约束转向原生 Python 控制流（if/else、while loops）
- 引入事务性编排（Transactional Orchestration）：可将任务分组为原子单元，定义显式失败模式包括回滚
- ControlFlow 框架：基于 LLM 的 AI 编排，Agent 动态决定调用哪些函数、处理什么数据
- Task Runners：`ThreadPoolTaskRunner`（默认并发）、`ProcessPoolTaskRunner`（CPU 密集）、`DaskTaskRunner`/`RayTaskRunner`（分布式）
- 性能：比 v2 快 10x，分布式工作流运行时开销减少 98%

#### 推荐的级联传播架构

```
Project Loop (外 Loop)
  ├── Domain Loop A (中 Loop)
  │     ├── Phase Loop 1 (内 Loop) → [Agent Task]
  │     └── Phase Loop 2 (内 Loop) → [Agent Task]
  └── Domain Loop B (中 Loop)
        └── Phase Loop 3 (内 Loop) → [Agent Task]
```

**传播策略设计**：

| 中断类型 | 向下传播（Parent→Child） | 向上传播（Child→Parent） |
|---------|------------------------|------------------------|
| 用户取消 | TERMINATE 级联到所有子 Loop | N/A（源自顶层） |
| 子 Agent 失败 | N/A（源自底层） | Phase Loop 先 REQUEST_CANCEL；若 Phase Loop 无法恢复，冒泡到 Domain Loop；Domain Loop 决策：重试/切换/上报 |
| Zone 0 安全违规 | TERMINATE 立即级联（不等清理） | 立即冒泡到 Project Loop，触发全局中止 |
| 超时 | 每层有独立超时，Phase Loop 超时 → Domain Loop 收到超时信号 → 决策 | 冒泡到上层，上层可延长或终止 |

**延迟上限建议**：

基于 Temporal 的基准数据和 OpenClaw 的 LLM Agent 特性，推荐以下延迟上限：

| 传播路径 | p99 延迟上限 | 理由 |
|---------|------------|------|
| Phase Loop → Domain Loop | < 200ms | 内层到中层，主要是状态写入 + 信号通知 |
| Domain Loop → Project Loop | < 350ms | 中层到外层，可能需要聚合多个 Phase Loop 状态 |
| Project Loop → 所有子 Loop（全级联） | < 500ms | 端到端级联，参考 Temporal Cloud signal p50 7.64ms × 层级深度 + LLM 决策开销 |
| Zone 0 安全中断（任意层 → 全局中止） | < 100ms | 安全关键路径，必须走 fast path，跳过清理 |

**总体 p99 上限建议：< 500ms**（全级联场景），安全中断 < 100ms。

依据：Temporal Cloud 的 signal p50 为 7.64ms，考虑 OpenClaw 的 LLM Agent 开销（状态序列化、决策推理），3 层传播 × ~100ms/层 + 缓冲 ≈ 500ms。Zone 0 安全中断应走独立 fast path，类似硬件中断的 NMI（Non-Maskable Interrupt），不经过正常消息队列。

---

### Finding 2: DAG 分解的非对称验证（UC-011）设计

#### 问题定义

UC-011 要求 DAG 分解者和验证者必须是独立的 LLM session。这防止了"自己验证自己"的偏差问题——同一个 LLM session 在分解任务时可能引入系统性偏见，如果由同一个 session 验证，这些偏见会被强化而非纠正。

#### 业界最新研究进展

**Graph of Verification (GoV) 框架**（arXiv 2506.12509, 2025年6月）

GoV 是目前最相关的学术参考。其核心思想：
- 将 LLM 的推理过程建模为 DAG，节点为推理步骤，边为依赖关系
- **自适应多粒度验证**（"node block" 架构）：
  - 形式化任务（数学、代码）：原子级验证，每个节点是一个可独立验证的断言
  - 自然语言任务：段落级验证，将整个推理段落作为一个验证单元
  - 粒度可动态调整，解决验证精度与鲁棒性之间的权衡
- 支持 step-by-step 的结构化验证，holistic 方法常遗漏的错误可被捕获

**VeriGuard 框架**（arXiv 2510.05156, 2025年末）

VeriGuard 提供了双阶段安全验证架构，直接可类比到我们的非对称验证设计：
- **阶段一（离线）**：澄清用户意图 → 建立精确安全规范 → 合成行为策略 → 广泛测试 + 形式化验证 → 迭代精炼直到策略被证明正确且安全
- **阶段二（在线）**：运行时监控器，在 Agent 执行每个动作前，对照预验证的策略进行轻量级验证
- 关键洞见：将昂贵的 exhaustive verification 放在离线阶段，在线阶段只做 lightweight monitoring，实现成本可控的安全保障

**VeriLLM 协议**（2025年）

去中心化 LLM 推理的可验证协议，验证者可以以约 1% 的推理成本验证结果。结合轻量级经验重跑和最小化链上检查。

**Rubric-based 评估趋势**（2025-2026）

- "Step-wise Rubric Rewards for LLM Reasoning"（2026年5月）：将单个 rubric 项目路由到特定步骤进行评估
- "Breaking the Exploration Bottleneck: Rubric-Scaffolded RL for General LLM Reasoning"（2025年9月）
- "Autorubric: A Unified Framework for Rubric-Based LLM Evaluation"（2026年2月）

#### 推荐的非对称验证架构

```
┌─────────────────────┐     ┌─────────────────────┐
│   Decomposer Session │     │   Verifier Session   │
│   (LLM Session A)    │     │   (LLM Session B)    │
│                      │     │                      │
│  1. 接收目标 + 约束   │     │  1. 接收 DAG 分解结果 │
│  2. 生成任务 DAG      │────>│  2. 独立验证每个节点  │
│  3. 输出:             │     │  3. 验证依赖边正确性  │
│     - DAG 结构        │     │  4. 输出:             │
│     - 节点描述        │     │     - PASS/FAIL/      │
│     - 依赖关系        │     │       PARTIAL         │
│     - 预估资源        │     │     - 修正建议        │
│     - 验证 rubric     │     │     - 置信度分数      │
└─────────────────────┘     └─────────────────────┘
          │                            │
          │        ┌──────────┐        │
          └───────>│ Arbiter  │<───────┘
                   │ (可选)    │
                   │ 裁决争议  │
                   └──────────┘
```

**Decomposer Session Prompt 策略**：

```
System Prompt 关键要素：
1. 角色定义：你是任务分解专家，负责将复杂目标分解为可执行的 DAG
2. 输出格式约束：
   - 每个节点必须包含：node_id, description, input_deps, output_spec, estimated_complexity
   - 依赖关系必须显式声明：predecessors[], successors[]
   - 每个节点必须是原子可验证的（GoV 原则）
3. 分解约束：
   - 最大并行度 ≤ 6（UC-004）
   - 每个节点必须有明确的完成标准（success criteria）
   - 必须生成验证 rubric（用于 Verifier 评估）
4. 自检要求：在输出前，自行检查是否存在循环依赖、遗漏节点、过度分解
```

**Verifier Session Prompt 策略**：

```
System Prompt 关键要素：
1. 角色定义：你是独立验证者，你的唯一任务是验证 DAG 分解的正确性
2. 你没有参与分解过程，你只看到最终输出
3. 验证维度（Rubric）：
   a. 完整性（Completeness）：所有目标需求是否都被覆盖？
   b. 正确性（Correctness）：每个节点的描述是否准确反映其职责？
   c. 依赖合理性（Dependency Soundness）：依赖关系是否必要且充分？
   d. 并行可行性（Parallel Feasibility）：无依赖的节点是否可真正并行？
   e. 粒度适当性（Granularity）：是否存在过度分解或分解不足？
   f. 资源可行性（Resource Feasibility）：预估资源是否在配额内？
4. 输出格式：
   - 每个维度打分 1-5
   - 总体 PASS（≥4分所有维度）/ FAIL（任一维度 <3）/ PARTIAL（3分存在）
   - FAIL 时必须提供具体修正建议
   - PARTIAL 时提供可选改进建议
5. 对抗性要求：你必须假设 Decomposer 可能犯错，你的职责是找出错误
```

**验证 Rubric 详细设计**：

| 维度 | 权重 | 1分（严重缺陷） | 3分（可接受） | 5分（优秀） |
|------|------|---------------|-------------|-----------|
| 完整性 | 25% | >30% 需求未覆盖 | 10-30% 需求未覆盖 | 所有需求明确覆盖 |
| 正确性 | 20% | >30% 节点描述有误 | 10-30% 有歧义 | 所有节点精确无歧义 |
| 依赖合理性 | 20% | 存在多余或缺失依赖 | 少量可优化依赖 | 依赖关系最小且充分 |
| 并行可行性 | 15% | 并行节点存在隐式依赖 | 部分并行可行 | 所有无依赖节点可真正并行 |
| 粒度适当性 | 10% | 严重过度/不足分解 | 基本合理 | 粒度最优，每节点 5-30min 工作量 |
| 资源可行性 | 10% | 超出配额 >50% | 超出配额 ≤20% | 所有节点在配额内 |

**重试机制**：
- 最多 3 轮 Decomposer → Verifier 迭代
- 每轮 Verifier 的修正建议作为 Decomposer 的额外输入
- 3 轮后仍 FAIL → 上报给用户，请求人工介入或目标澄清

---

### Finding 3: 并发上限下的资源配额隔离方案（UC-004, REQ-033）

#### 问题定义

REQ-033 约束最大并发 6 个子 Agent，UC-004 要求 DAG 并行度受限于此。UC-006 要求子 Agent 独立资源配额。核心挑战：在 OpenClaw 当前 `sessions_spawn` 能力下，如何实现每个子 Agent 的独立 token/时间/工具配额？

#### OpenClaw 当前架构能力（基于 2025-2026 研究）

**sessions_spawn 机制**：
- 创建新的非阻塞后台进程，立即返回 run ID
- 子 Agent 运行在独立 session 中（如 `agent:<agentId>:subagent:<uuid>`）
- 完成后向父/请求者聊天频道报告结果

**已有的隔离能力**：
- **上下文隔离**：子 Agent 默认使用隔离上下文，干净的子 transcript，最小化 token 使用
- **工具隔离**：子 Agent 不继承 session 特定工具
- **模型选择**：可为子 Agent 配置比主 Agent 更经济的模型
- **嵌套深度限制**：depth-2 workers 不能再生成子 Agent，防止 fan-out 失控

**并发控制模型**：
- **Lane-based 并发**：FIFO 队列系统
- 4 个全局 lane：`main`（入站消息）、`cron`（定时任务）、`subagent`（sessions_spawn 的子 Agent）、`nested`（嵌套工具调用）
- 每个 lane 有独立可配置并发上限，`subagent` lane 默认 cap 为 8
- 可通过 `agents.defaults.maxConcurrent` 全局设置或 `subagents.maxConcurrent` 按 lane 设置
- **Session 隔离**：通过 `dmScope` 确保同一 session 内任务串行执行，防止竞态

#### 推荐的资源配额隔离方案

**方案架构：Token Bucket + Deadline + Tool ACL 三维隔离**

```
┌─────────────────────────────────────────────────┐
│              Resource Quota Manager              │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Token     │  │ Deadline  │  │ Tool ACL │      │
│  │ Bucket    │  │ Enforcer  │  │ Controller│     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │              │              │             │
│  ┌────▼──────────────▼──────────────▼────┐      │
│  │         sessions_spawn wrapper         │      │
│  │  (Quota-Aware Spawn Controller)        │      │
│  └────┬──────────┬──────────┬────────────┘      │
│       │          │          │                     │
│  ┌────▼───┐ ┌───▼────┐ ┌───▼────┐              │
│  │Child A │ │Child B │ │Child C │  ... (max 6)  │
│  │50K tok │ │30K tok │ │80K tok │              │
│  │10min   │ │5min    │ │15min   │              │
│  │[r,w,e] │ │[r]     │ │[r,w]   │              │
│  └────────┘ └────────┘ └────────┘              │
└─────────────────────────────────────────────────┘
```

**维度一：Token 配额（Token Bucket per Sub-Agent）**

实现方式：
- 每个子 Agent session 创建时分配 token budget（通过 `token_budget` 参数或等价机制）
- Token 消耗通过 LLM API 调用的 `usage` 字段实时追踪
- 当 token 消耗达到 budget 的 80% 时，向子 Agent 发送警告信号
- 达到 100% 时，强制终止当前 LLM 调用，返回已完成的部分结果
- 未使用的 token 不回收（防止总预算超支）

推荐配额分配策略（总预算 300K tokens，6 个子 Agent 为例）：
| 任务复杂度 | 单 Agent 配额 | 占比 |
|-----------|-------------|------|
| 简单（信息收集、格式化） | 20K-30K tokens | 7-10% |
| 中等（代码生成、分析） | 40K-60K tokens | 13-20% |
| 复杂（架构设计、多步推理） | 80K-120K tokens | 27-40% |

**维度二：时间配额（Deadline Enforcement）**

实现方式：
- `sessions_spawn` 的 `mode: "run"` 已是 one-shot 执行
- 增加 `timeout_seconds` 参数（当前 OpenClaw 的 exec 工具已有此参数）
- 超时策略：
  - Soft timeout（80% 时间）：发送信号要求子 Agent 加速收敛
  - Hard timeout（100% 时间）：强制终止，收集已有输出
- 超时后的行为由 DAG 调度器决策：重试、切换策略、或标记为失败并上报

**维度三：工具 ACL（Tool Access Control List）**

实现方式：
- 当前 OpenClaw 子 Agent 已不继承 session 特定工具
- 扩展：为每个子 Agent 定义显式工具白名单
- 工具分类：
  - `read_only`：read, web_search, web_fetch, codegraph_search（安全，无副作用）
  - `read_write`：edit, write, exec（有副作用，需授权）
  - `dangerous`：apply_patch, 系统级 exec（需显式审批）
- 子 Agent 的工具 ACL 在 spawn 时确定，运行时不可扩展

**并发调度策略（max 6 约束下的 DAG 调度）**

推荐算法：**改进的 HEFT（Heterogeneous Earliest Finish Time）**

经典 HEFT 算法：
- 按 upward rank（从任务到出口任务的最长路径，含计算+通信成本）降序排列任务
- 将任务分配到使其 earliest finish time 最早的处理器
- 使用 insertion-based 方法利用空闲时间槽

改进点（适配 LLM Agent 场景）：
- **异构 Agent 能力**：不同子 Agent 可能使用不同模型（opus vs sonnet），计算能力不同
- **动态 DAG**：DAG 可能在执行中动态调整（新依赖发现），需要 online scheduling
- **Token 作为资源约束**：传统 HEFT 只考虑时间，我们需要将 token 预算作为第二维约束
- **优先级继承**：来自 Zone 0 安全中断的任务继承最高优先级，抢占普通任务

调度伪代码：
```python
def schedule_dag(dag, max_concurrent=6, token_budget=300000):
    ready_queue = topological_ready(dag)  # 入度为0的节点
    running = {}  # agent_id -> task_node
    completed = set()
    
    while ready_queue or running:
        # 空闲 Agent 槽位
        available_slots = max_concurrent - len(running)
        
        if available_slots > 0 and ready_queue:
            # 按 HEFT upward rank 排序
            ready_queue.sort(key=lambda n: n.upward_rank, reverse=True)
            
            # 在 token 预算内贪心分配
            for task in ready_queue[:available_slots]:
                if task.estimated_tokens <= remaining_budget:
                    agent = spawn_sub_agent(task, token_budget=task.estimated_tokens)
                    running[agent.id] = task
                    ready_queue.remove(task)
        
        # 等待任一完成
        completed_agent = wait_for_any(running)
        completed_task = running.pop(completed_agent.id)
        completed.add(completed_task.id)
        remaining_budget -= completed_task.actual_tokens
        
        # 更新 ready queue
        for successor in completed_task.successors:
            if all(pred in completed for pred in successor.predecessors):
                ready_queue.append(successor)
    
    return completed
```

---

### Finding 4: resume 操作幂等性（UC-005）的工程实现

#### 问题定义

UC-005 要求 resume 操作具有幂等性——无论 resume 被调用多少次，结果都应一致。这需要：精确的状态快照、合理的 checkpoint 频率、可靠的 crash recovery 流程。

#### 业界参考：Temporal 的 Replay 机制

Temporal 的持久化执行模型是目前最成熟的参考实现：

**核心机制**：
- **不可变事件历史**（Immutable Event History）：每个 Workflow 执行的每个事件都追加到 append-only log
- **确定性重放**（Deterministic Replay）：crash 后，通过重放事件历史重建内存状态。已成功执行的 Activity 不重新执行，而是使用记录的结果
- **Continue-As-New**：长运行 Workflow 定期将状态转移到新的执行，防止事件历史过大导致重放性能退化
- **Workflow ID 幂等键**：使用 Workflow ID 作为幂等键，防止重复启动

**Replay 2025 新特性**：
- Activity Operations Commands：暂停、恢复、重置、更新运行中的 Activity
- Reset Workflows with Child Workflows：重置时级联重置子 Workflow

**AWS Step Functions Redrive**（2023年11月引入）：
- 从失败点重启，而非重跑整个流程
- 使用与上次失败执行相同的输入
- 适用于需要外部操作或调查后重试的场景

#### 推荐的状态快照设计

**状态快照格式：JSON + Protobuf 混合方案**

基于 Protobuf vs JSON 的 benchmark 数据（2024-2025 多项基准测试一致结论）：

| 指标 | Protobuf | JSON | 建议 |
|------|----------|------|------|
| 序列化速度 | 快 5-10x | 基准 | 热路径用 Protobuf |
| 反序列化速度 | 快 5-10x | 基准 | 热路径用 Protobuf |
| 载荷大小 | 小 50-80% | 基准 | 存储/传输用 Protobuf |
| Schema 演进 | 内建 forward/backward 兼容 | 需额外 JSON Schema | Protobuf 胜出 |
| 人类可读性 | 需工具 | 原生可读 | 调试日志用 JSON |

**推荐方案**：
- **运行时状态**：Protobuf 序列化（高性能、小体积、schema 安全）
- **调试/审计日志**：JSON 序列化（人类可读、便于排查）
- **存储**：Protobuf 持久化到文件/数据库
- **API 交互**：JSON（与 LLM API、用户界面兼容）

**状态快照 Schema（Protobuf 定义）**：

```protobuf
syntax = "proto3";

message LoopState {
  string session_id = 1;
  LoopType loop_type = 2;  // PROJECT, DOMAIN, PHASE
  LoopStatus status = 3;   // RUNNING, PAUSED, FAILED, COMPLETED, CANCELLED
  int64 created_at = 4;
  int64 updated_at = 5;
  int32 version = 6;       // schema version for forward compatibility
  
  // DAG 状态
  DAGState dag = 7;
  
  // 子 Agent 状态
  repeated SubAgentState agents = 8;
  
  // 中断状态
  InterruptState interrupt = 9;
  
  // 检查点元数据
  CheckpointMeta checkpoint = 10;
  
  // 扩展字段（未来兼容性）
  map<string, string> metadata = 15;
}

message DAGState {
  repeated DAGNode nodes = 1;
  repeated DAGEdge edges = 2;
  string scheduling_algorithm = 3;  // "HEFT", "CPOP", "ROUND_ROBIN"
}

message DAGNode {
  string node_id = 1;
  string description = 2;
  NodeStatus status = 3;  // PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
  bytes input_data = 4;
  bytes output_data = 5;
  int64 started_at = 6;
  int64 completed_at = 7;
  int32 retry_count = 8;
  int32 max_retries = 9;
  ResourceQuota quota = 10;
  ResourceUsage actual_usage = 11;
}

message SubAgentState {
  string agent_id = 1;
  string session_key = 2;
  string assigned_node_id = 3;
  AgentStatus status = 4;
  int64 token_budget = 5;
  int64 token_used = 6;
  int64 deadline_ms = 7;
  repeated string allowed_tools = 8;
}

message CheckpointMeta {
  int64 checkpoint_id = 1;
  int64 timestamp = 2;
  string snapshot_format = 3;  // "protobuf", "json"
  bytes snapshot_hash = 4;     // 用于完整性校验
  int64 event_sequence = 5;    // 事件序号，用于确定重放位置
}
```

**Checkpoint 频率建议**：

| 事件类型 | 是否触发 Checkpoint | 理由 |
|---------|-------------------|------|
| Phase Loop 完成 | ✅ 是 | 自然边界，状态干净 |
| Domain Loop 完成 | ✅ 是 | 更高层级边界 |
| 子 Agent 完成 | ✅ 是 | 节点级粒度，恢复成本合理 |
| 子 Agent 失败 | ✅ 是 | 需要记录失败状态用于重试决策 |
| 中断信号接收 | ✅ 是 | 关键状态转换点 |
| LLM API 调用完成 | ⚠️ 每 N 次（建议 N=5） | 频繁 checkpoint 开销大，但 LLM 调用是主要成本点 |
| 工具调用完成 | ❌ 否（除非是写操作） | 读操作可重放，写操作需要记录 |

**推荐**：每完成一个 DAG 节点（Phase Loop 级别）必须 checkpoint。在节点内部，每 5 次 LLM API 调用做一次轻量 checkpoint（仅记录 token 消耗和当前步骤）。

**Crash Recovery 流程**：

```
                    ┌──────────────┐
                    │  系统启动     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ 加载最新      │
                    │ checkpoint    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ 验证完整性    │
                    │ (hash check)  │
                    └──────┬───────┘
                           │
                ┌──────────▼──────────┐
                │ 完整性 OK?           │
                └──┬──────────────┬───┘
                   │ Yes          │ No
            ┌──────▼──────┐  ┌───▼──────────┐
            │ 确定性重放   │  │ 从上一个完整   │
            │ 未完成的     │  │ checkpoint 恢复│
            │ 事件         │  │ (可能丢失部分) │
            └──────┬──────┘  └───┬──────────┘
                   │              │
            ┌──────▼──────────────▼───┐
            │ 重建 DAG 状态            │
            │ - 已完成节点：跳过        │
            │ - 运行中节点：标记为      │
            │   "需要验证"             │
            │ - 未开始节点：正常调度    │
            └──────┬──────────────────┘
                   │
            ┌──────▼──────────────────┐
            │ 运行中节点验证            │
            │ - 检查输出是否完整        │
            │ - 完整 → 标记完成         │
            │ - 不完整 → 重试或回滚     │
            └──────┬──────────────────┘
                   │
            ┌──────▼──────────────────┐
            │ 恢复 Loop 执行            │
            │ - 从 resume point 继续   │
            │ - 幂等性保证：重复 resume │
            │   产生相同结果            │
            └─────────────────────────┘
```

**幂等性保证机制**：
1. **Checkpoint ID 单调递增**：每次 checkpoint 生成唯一递增 ID，resume 时取最大 ID 的 checkpoint
2. **事件序号（event_sequence）**：类似 Temporal 的事件历史序号，确保重放顺序一致
3. **Snapshot Hash**：每个 checkpoint 计算 snapshot 的 SHA-256 hash，resume 时验证完整性
4. **幂等键**：每个 DAG 节点的执行使用 `session_id + node_id + checkpoint_id` 作为幂等键
5. **Activity 幂等性**：所有 LLM API 调用和工具调用必须设计为幂等的（类似 Temporal 的要求）

---

### Finding 5: Happens-Before 关系在 DAG 拓扑排序中的正确性（UC-003）

#### 问题定义

UC-003 要求 DAG 拓扑排序保证 happens-before 关系的正确性。核心问题：在分形 Loop 的并发执行中，如何确保因果依赖被正确维护？是否需要向量时钟或 Lamport 时间戳？

#### 理论基础

**Lamport 时间戳（Logical Clock）**：
- 每个进程维护一个计数器，每个事件递增
- 发送消息时附带计数器值，接收时取 max(本地, 收到) + 1
- 保证：如果 A → B（A happens-before B），则 timestamp(A) < timestamp(B)
- **局限**：逆命题不成立——timestamp(A) < timestamp(B) 不意味着 A → B（可能是并发事件）
- 无法检测并发关系

**向量时钟（Vector Clock）**：
- 每个节点维护一个向量（每个进程一个分量）
- 本地事件：递增自己的分量
- 发送消息：附带整个向量
- 接收消息：逐元素取 max，然后递增自己的分量
- **优势**：可以精确判断两个事件的关系：
  - V(A) < V(B)（所有分量 ≤ 且至少一个 <）→ A → B
  - V(A) || V(B)（存在交叉大小关系）→ A 和 B 并发
  - V(A) > V(B) → B → A

**DAG 拓扑排序与 Happens-Before**：
- DAG 的偏序关系天然对应 happens-before 关系
- 拓扑排序将偏序线性化：对于每条边 (u, v)，u 在排序中出现在 v 之前
- 关键定理：DAG 的拓扑排序 ⟺ happens-before 关系的线性扩展

#### 分析：是否需要向量时钟？

**场景分析**：

| 场景 | 需要向量时钟？ | 理由 |
|------|-------------|------|
| 单 Loop 内 DAG 调度 | ❌ 不需要 | DAG 边已显式定义 happens-before，拓扑排序即可 |
| 跨 Loop 因果追踪 | ⚠️ 视情况 | 如果子 Agent 之间有隐式通信，需要向量时钟检测并发冲突 |
| 审计日志因果排序 | ✅ 推荐 | 需要精确重建事件因果链，用于调试和合规 |
| 并发写入冲突检测 | ✅ 推荐 | 多个子 Agent 可能写同一资源，需要检测并发写入 |
| Zone 0 安全事件排序 | ✅ 必须 | 安全事件需要精确的因果排序，以确定违规的因果链 |

**推荐方案：DAG 拓扑排序 + 轻量向量时钟混合方案**

```
┌──────────────────────────────────────────────────────┐
│                  Hybrid Ordering System               │
│                                                       │
│  ┌─────────────────┐    ┌──────────────────────┐     │
│  │ DAG Topological  │    │ Vector Clock Layer    │     │
│  │ Sort (Primary)   │    │ (Secondary/Audit)     │     │
│  │                  │    │                       │     │
│  │ • 确定执行顺序    │    │ • 跨 Loop 因果追踪    │     │
│  │ • 并发度计算      │    │ • 审计日志排序        │     │
│  │ • 资源调度        │    │ • 冲突检测            │     │
│  └────────┬─────────┘    └──────────┬────────────┘     │
│           │                         │                   │
│  ┌────────▼─────────────────────────▼──────────┐       │
│  │           Unified Event Timeline              │       │
│  │                                               │       │
│  │  event_id | node_id | lamport_ts | vector_clk │       │
│  │  ---------+---------+------------+----------- │       │
│  │  e001     | n1      | 1          | [1,0,0]   │       │
│  │  e002     | n2      | 1          | [0,1,0]   │  ← 并发│
│  │  e003     | n1      | 2          | [2,0,0]   │       │
│  │  e004     | n3      | 2          | [1,1,1]   │  ← e003之后│
│  └───────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────┘
```

**具体实现建议**：

1. **DAG 拓扑排序（主排序）**：
   - 使用 Kahn's algorithm（BFS-based）或 DFS-based 拓扑排序
   - 时间复杂度：O(V + E)，V=节点数，E=边数
   - 在 DAG 构建时（Decomposer 阶段）即确定
   - 运行时调度器按拓扑序执行，并发执行无依赖的节点

2. **Lamport 时间戳（辅助排序）**：
   - 每个事件（LLM 调用、工具调用、状态转换）分配 Lamport 时间戳
   - 用于审计日志的全局排序
   - 实现简单，开销极低（单计数器递增）

3. **向量时钟（按需启用）**：
   - 仅在以下场景启用：
     a. 跨 Loop 的子 Agent 有共享资源访问
     b. Zone 0 安全事件需要精确因果链
     c. 用户请求 debug 因果追踪
   - 向量大小 = max_concurrent（最大 6），开销可控
   - 每个子 Agent 维护自己的向量分量

4. **Happens-Before 正确性验证算法**：

```python
def verify_happens_before(dag, execution_log):
    """验证执行日志是否满足 DAG 的 happens-before 约束"""
    # 1. 从 DAG 构建偏序关系
    partial_order = build_partial_order(dag)
    
    # 2. 从执行日志提取实际执行顺序
    actual_order = extract_execution_order(execution_log)
    
    # 3. 验证：对于每对 (u, v) ∈ partial_order，
    #    u 在 actual_order 中必须出现在 v 之前
    for u, v in partial_order.edges:
        u_time = actual_order[u].timestamp
        v_time = actual_order[v].timestamp
        if u_time >= v_time:
            raise HappensBeforeViolation(
                f"Node {u} (ts={u_time}) should happen before "
                f"node {v} (ts={v_time})"
            )
    
    # 4. 如果有向量时钟，额外验证并发节点确实并发
    for u, v in concurrent_pairs(dag):
        if execution_log has vector_clocks:
            assert are_concurrent(
                execution_log[u].vector_clock,
                execution_log[v].vector_clock
            ), f"Nodes {u} and {v} should be concurrent"
    
    return True
```

**为什么不用纯向量时钟替代拓扑排序？**

- 拓扑排序是 DAG 的**结构属性**，在执行前就确定，用于指导调度
- 向量时钟是**运行时观测**，在执行过程中动态维护，用于验证和审计
- 两者互补：拓扑排序决定"应该怎么执行"，向量时钟验证"实际是否按预期执行"
- 性能：拓扑排序 O(V+E) 一次性计算；向量时钟每次事件 O(N)（N=进程数，最大 6）

---

## 技术推荐（对比评估）

### 1. 中断传播机制

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **Temporal-style ParentClosePolicy** | 成熟、经过大规模验证、3种策略灵活 | 需要 Temporal 基础设施 | 如果引入 Temporal 作为编排层 |
| **自定义事件总线 + 优先级队列** | 轻量、无外部依赖、可深度定制 | 需自行处理边界情况 | OpenClaw 原生实现 |
| **AWS Step Functions Catch/Retry** | 全托管、与 AWS 生态集成 | 供应商锁定、延迟较高 | 如果部署在 AWS |

**推荐**：自定义事件总线 + 优先级队列，参考 Temporal 的 ParentClosePolicy 设计三种传播策略。理由：OpenClaw 已有 lane-based 并发模型，扩展为事件总线成本低；避免引入 Temporal 的运维复杂度。

### 2. DAG 调度算法

| 算法 | 时间复杂度 | 适用场景 | 局限性 |
|------|-----------|---------|--------|
| **HEFT** | O(n² × p) | 异构环境、静态调度 | 不支持动态 DAG |
| **CPOP** | O(n² × p) | 关键路径敏感场景 | 不如 HEFT 灵活 |
| **改进 HEFT（推荐）** | O(n² × p) + 动态扩展 | LLM Agent 异构能力 + 动态 DAG | 需要自定义实现 |
| **MARL-based** | 训练成本高 | 大规模动态环境 | 过度工程化 |

**推荐**：改进 HEFT 算法，增加 token 预算作为第二维约束 + 动态 DAG 支持。n（节点数）通常 < 20，p（处理器数）≤ 6，性能不是瓶颈。

### 3. 状态序列化格式

| 格式 | 序列化速度 | 体积 | Schema 演进 | 人类可读 | 推荐用途 |
|------|-----------|------|------------|---------|---------|
| **Protobuf** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | 运行时状态持久化 |
| **JSON** | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | 调试日志、API 交互 |
| **MessagePack** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 折中方案 |

**推荐**：Protobuf 用于运行时状态持久化（checkpoint），JSON 用于调试/审计日志和 API 交互。双格式输出，通过 `snapshot_format` 字段区分。

### 4. Checkpoint 策略

| 策略 | Checkpoint 频率 | 恢复精度 | 存储开销 | 推荐 |
|------|---------------|---------|---------|------|
| **每事件** | 极高 | 精确 | 极高 | ❌ 性能不可接受 |
| **每 DAG 节点完成** | 中等 | 节点级 | 中等 | ✅ 推荐 |
| **每 Loop 完成** | 低 | Loop 级 | 低 | ⚠️ 可能丢失过多工作 |
| **混合（推荐）** | 节点完成 + 每5次LLM调用 | 接近精确 | 可控 | ✅✅ 最佳 |

**推荐**：混合策略——每个 DAG 节点完成时做完整 checkpoint，节点内部每 5 次 LLM API 调用做轻量 checkpoint（仅记录 token 消耗和当前步骤索引）。

---

## 风险识别

### 风险 1: LLM 非确定性导致 Replay 不一致
- **描述**：Temporal 的 deterministic replay 要求 Workflow 代码确定性执行。但 LLM API 调用天然非确定性（temperature > 0），相同输入可能产生不同输出。
- **影响**：resume 后重放可能产生不同的 DAG 分解或 Agent 决策
- **缓解**：
  1. 所有 LLM 调用记录完整 input/output 到 checkpoint
  2. resume 时优先使用已记录的输出（cache hit），仅对未执行部分调用 LLM
  3. 关键决策点（DAG 分解、Zone 0 检查）使用 temperature=0
- **严重性**：高

### 风险 2: 向量时钟在大规模场景下的开销
- **描述**：向量时钟大小 = 进程数。当前 max 6 子 Agent 可控，但如果未来扩展，向量时钟开销线性增长
- **影响**：每个事件需要 O(N) 的向量更新和比较
- **缓解**：
  1. 向量时钟仅在需要时启用（安全事件、审计模式）
  2. 使用 Hybrid Logical Clock (HLC) 替代，结合物理时钟和逻辑计数器
  3. 限制向量时钟的进程数上限为 max_concurrent（6）
- **严重性**：低（当前规模下）

### 风险 3: 非对称验证的延迟开销
- **描述**：Decomposer → Verifier 双 session 设计增加了一倍以上的 LLM 调用成本和时间
- **影响**：DAG 分解阶段的延迟可能从 ~5s 增加到 ~15s（含 1-2 轮验证迭代）
- **缓解**：
  1. Verifier 使用更小/更快的模型（如 sonnet 而非 opus）
  2. 限制最大 3 轮迭代
  3. 对简单目标（节点数 < 5）跳过验证
  4. 缓存常见模式的验证结果
- **严重性**：中

### 风险 4: Checkpoint 存储膨胀
- **描述**：频繁 checkpoint 导致大量状态数据持久化，特别是包含 LLM 完整 input/output 时
- **影响**：磁盘空间消耗、checkpoint 加载时间增加
- **缓解**：
  1. 轻量 checkpoint 仅记录元数据（token 消耗、步骤索引），不记录完整 LLM 输出
  2. 完整 checkpoint 使用 Protobuf 压缩
  3. 设置 checkpoint 保留策略（保留最近 N 个，旧的归档/删除）
  4. LLM 输出存储 hash + 引用，而非完整内容
- **严重性**：中

### 风险 5: 中断传播与并发执行的竞态
- **描述**：当 6 个子 Agent 并发执行时，中断信号需要在所有子 Agent 上一致地生效，但网络延迟可能导致子 Agent 在不同时间收到中断
- **影响**：部分子 Agent 已停止，部分仍在执行，可能导致不一致状态
- **缓解**：
  1. 中断信号使用向量时钟标记，子 Agent 拒绝执行 timestamp < interrupt_timestamp 的事件
  2. 两阶段中断：先 pause（暂停所有子 Agent），再 decision（取消/恢复）
  3. 类似分布式事务的 2PC（Two-Phase Commit）协议
- **严重性**：高

---

## 覆盖需求

covered_req_ids: [REQ-001, REQ-006, REQ-010, REQ-024, REQ-033, REQ-034, REQ-042, REQ-076, REQ-077, REQ-078]

### 需求覆盖映射

| REQ ID | 描述 | 覆盖 Finding |
|--------|------|-------------|
| REQ-001 | OpenClaw AI Native Loop Engineering Framework | Finding 1-5（整体架构） |
| REQ-006 | 子Agent失败时自动分析/重试/切换/上报 | Finding 1（级联传播）、Finding 3（资源配额） |
| REQ-010 | 任务分解为DAG时考虑依赖关系和并行度 | Finding 2（DAG 分解验证）、Finding 5（happens-before） |
| REQ-024 | Loop状态跨Session存活，中断后可恢复 | Finding 4（resume 幂等性） |
| REQ-033 | 最大并发6个子Agent | Finding 3（并发上限隔离） |
| REQ-034 | 必须有死循环熔断机制 | Finding 1（中断传播）、Finding 3（时间配额） |
| REQ-042 | Loop框架自动分解目标为任务DAG | Finding 2（DAG 分解验证） |
| REQ-076 | 分形Loop + 间歇式心跳 + 全LLM控制 | Finding 1（三层 Loop 中断传播） |
| REQ-077 | 外/中/内三层 Loop | Finding 1（三层架构）、Finding 4（跨层 checkpoint） |
| REQ-078 | Dream Loop, Meta-Loop, 分形中断, 失败恢复决策树 | Finding 1（分形中断）、Finding 4（失败恢复） |

### 约束覆盖映射

| UC ID | 描述 | 覆盖 Finding |
|-------|------|-------------|
| UC-001 | 分形 interrupt 级联传播时限 | Finding 1（<500ms p99） |
| UC-002 | DAG 无环性运行时验证 | Finding 5（拓扑排序正确性验证） |
| UC-003 | DAG 拓扑排序 happens-before 正确性 | Finding 5（混合排序方案） |
| UC-004 | DAG 并行度受限于并发上限 | Finding 3（max 6 调度策略） |
| UC-005 | resume 操作的幂等性 | Finding 4（checkpoint + replay） |
| UC-006 | 子 Agent 独立资源配额 | Finding 3（三维隔离方案） |
| UC-011 | DAG 分解的非对称验证 | Finding 2（双 session 验证架构） |
"""

with open(os.path.join(experts_dir, 'fractal_loop_architect.md'), 'w') as f:
    f.write(report_content)

print(f"Report written to: {os.path.join(experts_dir, 'fractal_loop_architect.md')}")
print(f"Report length: {len(report_content)} characters")
