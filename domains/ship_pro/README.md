# Ship Pro - AI Native 架构

> **版本**: current | **日期**: 2026-07-03 | **状态**: 已实现，待测试

## 🎯 核心理念

**Ship Pro = Solution Pro V2 的镜像架构**

- **动态执行**: LLM 动态决策 Worker 数量、角色、Prompt、依赖
- **固定编排**: Python 编排器控制流程、Gate 验证、状态管理
- **AI Native**: LLM 做语义决策，Python 做确定性执行

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Ship Pro 架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Phase 1: Planner (动态)                                      │
│  ├── LLM 分析 Solution Pro 输出                               │
│  ├── LLM 决定 Worker 数量/角色/依赖                           │
│  ├── LLM 生成 Worker Prompt                                   │
│  └── 输出: PlannerOutput (JSON Schema 约束)                   │
│                                                               │
│  Phase 2: Workers (动态 + 固定编排)                           │
│  ├── 编排器读取 PlannerOutput                                 │
│  ├── 拓扑排序计算执行顺序                                     │
│  ├── 按层级 spawn Workers (并行执行同层)                      │
│  ├── 每个 Worker 完成后验证 WorkerGate                        │
│  └── 输出: Worker Outputs (JSON Schema 约束)                  │
│                                                               │
│  Phase 3: Consolidator (动态 + 固定验证)                      │
│  ├── LLM 汇总所有 Worker 输出                                 │
│  ├── LLM 解决冲突、生成 ShipPackage                           │
│  ├── 三层 Gate 验证:                                          │
│  │   ├── G1: InformationConservationGate (信息守恒)           │
│  │   ├── G2: CompletenessGate (完整性)                        │
│  │   └── G3: HarnessV3 (交付质量)                             │
│  └── 输出: ShipPackage (JSON Schema 约束)                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 📂 文件结构

```
domains/ship_pro/
├── contracts/                    # 契约定义
│   ├── planner_output.py        # PlannerOutput Schema
│   ├── worker_deliverable.py    # WorkerDeliverable Schema
│   ├── ship_package.py          # ShipPackage Schema
│   └── gates.py                 # Gate 实现
├── orchestrator/                 # 编排器
│   ├── ship_orchestrator.py     # 主编排器
│   └── state_manager.py         # 状态管理
├── agent/                        # Agent 层
│   └── ship_agent.py            # Agent 实现
├── prompts/                      # Prompt 模板
│   ├── planner.md               # Planner Prompt
│   ├── worker_base.md           # Worker 基础模板
│   ├── consolidator.md          # Consolidator Prompt
│   └── agent.md                 # Agent Prompt
├── tests/                        # 测试
│   └── test_ship_pro.py      # 端到端测试
└── run_ship_pro.py           # 启动脚本
```

## 🚀 快速开始

### 1. 准备 Solution Pro 输出

确保你有 Solution Pro 的输出文件（`final_solution.json`）：

```json
{
  "solution_name": "AI Native Loop Engineering Framework",
  "architecture_overview": "...",
  "key_design_decisions": [...],
  "implementation_plan": [...],
  "risk_mitigation": [...],
  "verification_results": {...}
}
```

### 2. 运行 Ship Pro

```bash
cd /Users/allen/.openclaw/workspace/.deepflow

python3 domains/ship_pro/run_ship_pro.py \
  --solution-pro-output /path/to/solution_pro_output.json \
  --blackboard-path /tmp/ship_pro_blackboard
```

### 3. 查看输出

```bash
# 查看 ShipPackage
cat /tmp/ship_pro_blackboard/stages/ship_package.json | jq

# 查看 Pipeline 状态
cat /tmp/ship_pro_blackboard/pipeline_state.json | jq

# 查看所有阶段输出
ls -la /tmp/ship_pro_blackboard/stages/
```

## 🧪 测试

### 单元测试

```bash
cd /Users/allen/.openclaw/workspace/.deepflow
pytest domains/ship_pro/tests/test_ship_pro.py -v
```

### 端到端测试

```bash
# 使用 Solution Pro 的真实输出测试
python3 domains/ship_pro/run_ship_pro.py \
  --solution-pro-output blackboard/OpenClaw\ AI\ Native\ Loop\ Engineering\ Framework/stages/final_solution.json \
  --blackboard-path /tmp/ship_pro_e2e_test
```

## 📋 契约笼子方法

Ship Pro 严格遵循契约笼子方法：

### 1. 定义契约（Pydantic Schema）

```python
class PlannerOutput(BaseModel):
    input_type: str
    complexity: str
    domain: str
    analysis_summary: str
    workers: List[WorkerSpec]
    integration_strategy: str

class WorkerSpec(BaseModel):
    role: str  # 自由命名，无 Enum 约束
    task_description: str
    required_inputs: List[str]
    expected_output_stage: str
    output_schema: str
    depends_on: List[str]
    needs_web_search: bool
    web_search_scope: Optional[str]
    must_constraints: List[str]
    solution_pro_refs: List[str]
```

### 2. 声明契约（JSON Schema）

所有 Schema 自动生成 JSON Schema，供 LLM 参考：

```bash
ls domains/ship_pro/contracts/schemas/
# planner_output.json
# worker_deliverable.json
# ship_package.json
```

### 3. 执行契约（Gate 验证）

每个阶段完成后，必须通过 Gate 验证：

```python
# Phase 1: PlannerGate
gate_result = orchestrator.verify_planner_output(planner_output)

# Phase 2: WorkerGate (per worker)
gate_result = orchestrator.verify_worker_output(worker_spec, worker_output)

# Phase 3: 三层 Gate
gate_results = orchestrator.verify_ship_package(solution_pro_output, ship_package)
```

## 🔐 约束笼子（三层）

### 第一层：任务边界

- ✅ 你可以：分析、规划、执行、汇总
- ❌ 你不能：修改 Solution Pro 输出、添加新需求、删除已有需求

### 第二层：角色边界

- ✅ 你可以：专注于自己的角色任务
- ❌ 你不能：执行其他角色的任务、干预其他角色的输出

### 第三层：输出边界

- ✅ 你可以：输出符合 JSON Schema 的结构化数据
- ❌ 你不能：输出自由文本、解释你的决策、添加额外说明

## 🛡️ 铁律提醒

### 铁律 1: sessions_spawn 是 tool call，不是 Python 函数

```python
# ✅ 正确
sessions_spawn(runtime="subagent", mode="run", label="worker_1", task="...")

# ❌ 错误
from openclaw import sessions_spawn  # 永远失败
```

### 铁律 2: yield 后第一个 action 必须是 exec

```python
# ✅ 正确
sessions_yield()
exec("python3 verify.py")  # 第一个 action 是 exec

# ❌ 错误
sessions_yield()
print("继续执行...")  # 生成文字会导致 session 中断
```

### 铁律 3: 每个阶段是原子操作

```
spawn → yield → exec 验证 → 下一个阶段
中间不插入任何 text
```

## 📊 Gate 验证详情

### PlannerGate

- ✅ Worker 数量在 2-8 范围内
- ✅ 依赖图无环（拓扑排序验证）
- ✅ 所有 Worker 都有 `solution_pro_refs`
- ✅ 所有 Worker 都有 `must_constraints`

### WorkerGate

- ✅ 输出符合 WorkerDeliverable Schema
- ✅ MUST 约束保留检查（LLM 语义判断）
- ✅ web_search 范围检查（简单字符串匹配）

### 三层 Gate（Consolidator）

1. **InformationConservationGate**: 信息守恒检查
   - 信息丢失检查：Solution Pro 的需求是否都有对应 work_package
   - 信息新增检查：work_packages 是否都对应 Solution Pro 的需求

2. **CompletenessGate**: 完整性检查
   - REQ-ID 覆盖检查（代码）
   - 覆盖深度评估（LLM）

3. **HarnessV3**: 交付质量评估
   - 工作包数量合理性（3-15）
   - 依赖关系合理性（DAG 无环、无过度耦合）
   - 验收标准可操作性（每个 WP 至少 2 个 AC）

## 🔄 失败处理

### Retry 机制

每个阶段最多重试 2 次：

```python
if gate_result.passed:
    # 继续
else:
    if retry_count < 2:
        state_manager.increment_retry(stage_name)
        state_manager.update_stage(stage_name, "pending")
        # 重新运行
    else:
        state_manager.update_stage(stage_name, "failed")
        raise RuntimeError(...)
```

### Fix Context

如果 Gate 失败，生成 fix_context 帮助 LLM 修复：

```json
{
  "failed_gates": ["InformationConservationGate"],
  "issues": [
    "信息丢失: REQ-001 没有对应的 work_package",
    "信息新增: WP-005 不对应任何 Solution Pro 需求"
  ]
}
```

## 📈 性能指标

### 预期性能

- **Phase 1 (Planner)**: 1-2 分钟
- **Phase 2 (Workers)**: 5-10 分钟（取决于 Worker 数量）
- **Phase 3 (Consolidator)**: 2-3 分钟
- **总计**: 10-15 分钟

### Token 消耗

- **Planner**: ~10K tokens
- **Workers**: ~5K tokens × N workers
- **Consolidator**: ~15K tokens
- **总计**: ~50K-100K tokens

## 🎓 经验教训

Ship Pro 吸收了 Solution Pro V2 的所有经验教训：

| # | Solution Pro 教训 | Ship Pro 改进 |
|---|------------------|-----------------|
| S1 | stage_progress 缺失 | StateManager 管理所有阶段状态 |
| S2 | convergence 未聚合 | Consolidator 聚合所有 Worker 输出 |
| S5 | 无 state machine | State Machine 规则保护状态转换 |
| D1-D4 | Blackboard 格式混乱 | read_json() 双重编码自动解包 |
| I1-I3 | 信息守恒失效 | 三层 Gate 验证（G1/G2/G3） |
| M1 | spawn 不是 Python 函数 | Agent Prompt 铁律提醒 |
| M3 | yield 后生成文字 | Agent Prompt 铁律提醒 |

## 📚 相关文档

- [架构设计](../../docs/design/ship_pro_architecture.md)
- [角色规格](../../docs/design/ship_pro_role_specifications.md)
- [收敛设计](../../docs/design/ship_pro_convergence_design.md)
- [专家评审决策](../../docs/design/ship_pro_expert_review_decisions.md)

## 🆘 故障排查

### 问题 1: Planner Gate 失败

**症状**: `Worker 数量超出范围`

**解决**: 检查 Solution Pro 输出的复杂度，可能需要简化需求

### 问题 2: Worker Gate 失败

**症状**: `MUST 约束未保留`

**解决**: 检查 Worker Prompt 是否正确传递了 `must_constraints`

### 问题 3: Consolidator Gate 失败

**症状**: `信息丢失: REQ-XXX 没有对应的 work_package`

**解决**: 检查 Worker 输出是否覆盖了所有 Solution Pro 需求

## 📝 版本历史

- **current** (2026-07-03): AI Native 架构，动态 Worker + 固定编排
- **V5.0** (未完成): Phase 1+2 多 Agent 架构
- **V4.0** (2026-06-26): Generator + Judge 两阶段闭环
- **V3.0** (2026-06-20): 6 Agent 线性流水线
