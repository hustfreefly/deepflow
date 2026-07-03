# Ship Pro V6 — 角色规格定义

> **版本**: 6.0.0 | **日期**: 2026-07-03  
> **配套文档**: `ship_pro_v6_architecture.md`, `ship_pro_v6_convergence_design.md`

---

## 角色总览

| 角色 | Phase | 动态/固定 | 职责 | Web Search |
|------|-------|----------|------|:---:|
| Analyzer | Phase 1 | 动态 | 分析输入，规划拆解策略 | ✅ |
| Planner | Phase 1 | 动态 | 生成 PlannerOutput（WorkerSpec 列表） | ✅ |
| Worker × N | Phase 2 | 动态 | 执行拆解，产出交付物片段 | 部分 ✅ |
| Meta Shipper | Phase 3 | 动态 | 规划整合策略 | ❌ |
| Consolidator | Phase 3 | 动态 | 合并产出，解决冲突 | ❌ |
| Harness Judge | Phase 3 | 固定 | 质量验证（4 层 Gate） | ❌ |
| Fix Agent | Phase 3 | 固定 | 定向修复 | ❌ |
| Orchestrator | 全局 | 固定 | 编排调度（spawn/yield/gate/next） | ❌ |

> **注意**: Phase 1 中 Analyzer 和 Planner 合并为一次 LLM 调用（分析+规划一体化），减少 spawn 开销。

---

## 1. Phase 1: Planner（分析+规划一体化）

### 输入

| 来源 | 内容 | 必须 |
|------|------|:---:|
| Solution Pro | `final_solution.json` | ✅ |
| 约束笼子 | 三层约束（任务/角色/输出边界） | ✅ |
| web search | 领域背景（可选，LLM 自行决定） | ⬜ |

### 输出（Pydantic Schema）

```python
class PlannerOutput(BaseModel):
    """Phase 1 输出 — Planner 的结构化决策"""
    
    # 分析结论
    input_type: str           # "engineering" | "research" | "investment" | "other"
    complexity: str           # "low" | "medium" | "high"
    domain: str               # 领域描述
    analysis_summary: str     # 1-2 句分析结论
    
    # 拆解计划
    workers: list[WorkerSpec]  # 2 ≤ len ≤ 8
    
    # 整合策略
    integration_strategy: str  # "sequential" | "parallel_merge" | "hierarchical"

class WorkerSpec(BaseModel):
    """单个 Worker 的规格定义"""
    
    role: str                 # 角色名称（如 "wp_decomposer", "ac_writer"）
    task_description: str     # 任务描述（LLM 动态生成）
    
    # 输入约束
    required_inputs: list[str]  # 需要读取的 Blackboard stage 列表
    
    # 输出约束
    expected_output_stage: str   # 输出写入的 stage 名称
    output_schema: str           # 输出必须符合的 Pydantic 模型名
    
    # 依赖关系
    depends_on: list[str]     # 依赖的其他 Worker role
    
    # 权限
    needs_web_search: bool    # 是否需要 web search 权限
    web_search_scope: str     # 搜索范围描述（如 "API 文档、技术栈最佳实践"）
    
    # 约束引用
    must_constraints: list[str]  # 从 Solution Pro 继承的 MUST 约束 ID
    solution_pro_refs: list[str] # 引用的 Solution Pro 具体字段路径
```

### 行为约束

- **分析+规划一体化**: 一次 LLM 调用内完成分析和规划，不拆成两个 Agent
- **不讨论方案合理性**: 禁止在输出中评价 Solution Pro 方案的优劣
- **Worker 数量约束**: 2 ≤ N ≤ 8，超过时必须合并角色
- **约束引用必须具体**: 每个 WorkerSpec 的 `solution_pro_refs` 必须引用 `final_solution.json` 的具体字段路径（如 `implementation_plan[0]`、`architecture_overview`）

### Planner Gate

| 检查项 | 类型 | 标准 | FAIL 处理 |
|--------|------|------|-----------|
| Worker 数量 | 代码 | 2 ≤ N ≤ 8 | 自动截断 + WARNING |
| 角色名称 | 代码 | 在允许列表内或有理由 | WARNING |
| 依赖图无环 | 代码 | 拓扑排序成功 | FAIL → 重新规划 |
| 约束引用非空 | 代码 | `solution_pro_refs` 非空 | FAIL → 重新规划 |
| web_search 理由 | LLM | 搜索范围与任务相关 | WARNING |

### 允许的角色名称（参考列表）

| 角色 | 适用场景 | 说明 |
|------|---------|------|
| `wp_decomposer` | 工程 | 拆解工作包 |
| `ac_writer` | 工程 | 编写验收标准 |
| `dependency_analyzer` | 工程 | 分析依赖关系 |
| `task_planner` | 通用 | 规划任务清单 |
| `template_generator` | 通用 | 生成模板/表格 |
| `deliverable_packager` | 通用 | 打包交付物 |
| `research_planner` | 研究 | 规划调研步骤 |
| `data_source_analyzer` | 研究/投资 | 分析数据源 |
| `checklist_builder` | 投资 | 构建检查清单 |

> Planner 可以自定义角色名称，但必须在 `task_description` 中说明理由。

---

## 2. Phase 2: Worker × N

### 输入

| 来源 | 内容 | 必须 |
|------|------|:---:|
| Orchestrator | 程序化拼接的 Prompt（WorkerSpec + 约束笼子模板） | ✅ |
| Blackboard | `final_solution.json`（Solution Pro 输出） | ✅ |
| Blackboard | 依赖 Worker 的产出（如有） | ⬜ |
| web search | 实施细节（如有权限） | ⬜ |

### 输出

每个 Worker 写入指定的 Blackboard stage（由 `WorkerSpec.expected_output_stage` 定义）。

输出必须符合 `WorkerSpec.output_schema` 指定的 Pydantic 模型。

### Worker Prompt 模板（Orchestrator 程序化拼接）

```markdown
# Worker: {role}

## 你的任务
{task_description}

## 约束笼子

### 任务边界
- 你只做"拆解+交付"，不做"设计+决策"
- Solution Pro 没说的不补充，说了的不修改

### 角色边界
- 你的角色是 {role}
- 只生成交付物，不讨论方案优劣
- 不修改其他 Worker 的产出

### 输出边界
- 输出写入: stages/{expected_output_stage}.json
- 输出格式: 必须符合 {output_schema} Schema
- 额外建议标记为 optional_suggestion，不影响主交付物

## 输入数据
从 Blackboard 读取:
{required_inputs 列表}

## 依赖
{depends_on 列表，如有}

## MUST 约束（从 Solution Pro 继承，不可违反）
{must_constraints 列表}

## 参考字段
{solution_pro_refs 列表}
{web_search_scope 提示（如有权限）}
```

### 行为约束

- **不修改其他 Worker 的产出**
- **不讨论方案优劣**
- **web search 只补充实施细节**（API 用法、配置参数），不引入架构决策
- **额外建议**标记为 `optional_suggestion`

### web_search 失败策略

> **来源**: Solution Pro V2 教训 A4 — web_search Gemini 地区限制导致 11 次空重试

如果 web_search 失败（地区限制、超时、404 等），Worker 必须：
1. **最多重试 1 次**（换关键词或缩小范围）
2. 如果仍然失败，**跳过搜索，基于 LLM 内部知识继续工作**
3. 在产出中标记 `web_search_skipped: true` + 原因
4. **禁止无限重试或报错终止**

这个策略由 Orchestrator 在 Worker Prompt 模板中注入，不需要 Worker 自行实现。

---

## 3. Phase 3: Shipper

### 3.1 Meta Shipper（动态层）

#### 输入

| 来源 | 内容 | 必须 |
|------|------|:---:|
| Blackboard | 所有 Worker 产出 | ✅ |
| Blackboard | `final_solution.json` | ✅ |
| PlannerOutput | 整合策略 | ✅ |

#### 输出

`integration_plan` — 规划如何合并各 Worker 产出。

#### 行为约束

- **不补充新内容**: 只规划"怎么合并"，不增加新 WP 或新需求
- **冲突解决**: 如果 Worker 产出有冲突，选择与 Solution Pro 更一致的方案

### 3.2 Consolidator（动态层）

#### 输入

| 来源 | 内容 | 必须 |
|------|------|:---:|
| Meta Shipper | `integration_plan` | ✅ |
| Blackboard | 所有 Worker 产出 | ✅ |

#### 输出

`ship_package_draft` — 合并后的交付物包草稿。

#### 行为约束

- **严格按计划合并**: 不增加、不删减、不修改
- **冲突标记**: 如果合并时发现冲突，标记为 `conflict` 而非自行解决

### 3.3 Harness Judge（固定层）

> 详见 `ship_pro_v6_convergence_design.md`

### 3.4 Fix Agent（固定层）

#### 输入

| 来源 | 内容 | 必须 |
|------|------|:---:|
| Harness Judge | Gate FAIL 报告 + 修复建议 | ✅ |
| Blackboard | `ship_package_draft` | ✅ |

#### 输出

`ship_package_refined` — 修复后的交付物包。

#### 行为约束

- **定向修复**: 只修复 Gate FAIL 报告中标记的问题
- **不引入新内容**: 修复时不增加新 WP 或新需求
- **最多 2 轮**: 超过 2 轮仍 FAIL → CONDITIONAL 退出

---

## 4. Orchestrator（固定编排器）

### 职责

| 职责 | 说明 |
|------|------|
| 流程调度 | spawn → yield → gate → next 循环 |
| Prompt 组装 | 根据 PlannerOutput + 约束笼子模板程序化拼接 Worker Prompt |
| Gate 执行 | 每个 Worker 完成后执行 Pydantic Gate |
| Checkpoint | 每个 Phase 完成后持久化状态 |
| 超时管理 | 单 Worker 600s，Phase 900s |

### 继承关系

```python
class ShipOrchestrator(ModuleOrchestrator):
    """Ship Pro V6 编排器 — 继承 ModuleOrchestrator 基类"""
    
    MAX_WORKERS = 8
    WORKER_TIMEOUT = 600
    PHASE_TIMEOUT = 900
    
    def stage_sequence(self) -> list[dict]:
        return [
            {"name": "planner", "executor": "spawn"},           # Phase 1
            {"name": "build", "executor": "spawn_parallel"},    # Phase 2
            {"name": "shipper", "executor": "spawn"},           # Phase 3
        ]
```

### 🔴 铁律（来自 Solution Pro V2 经验教训）

#### 铁律 1: sessions_spawn 是 Agent tool，不是 Python 函数

> **来源**: Solution Pro V2 教训 M1 — 多次尝试 `from openclaw import sessions_spawn` 导致失败

```python
# ✅ 正确: Orchestrator 用 tool call 调度
sessions_spawn(runtime="subagent", mode="run", task="...")

# ❌ 绝对禁止: 在 Python 代码中 import
from openclaw import sessions_spawn  # 永远失败！

# ❌ 绝对禁止: 在 exec 中定义 spawn_fn callback
spawn_fn = lambda task: sessions_spawn(...)  # 架构错误！
```

**架构检查**:
```
✅ 正确: Orchestrator (Agent) → tool call sessions_spawn → Worker Agent
❌ 错误: Orchestrator → exec python → Python 代码想调 sessions_spawn
```

#### 铁律 2: yield 唤醒后第一个 action 必须是 exec

> **来源**: Solution Pro V2 教训 M3 — yield 后生成文字导致 session 中断

```markdown
## ⚠️ Yield 唤醒规则（铁律）

sessions_yield 返回后：
1. 第一个 action **必须**是 exec 验证代码
2. **禁止**生成任何文字（包括"我继续"、"好的"、"现在检查"）
3. 验证完成后才能输出分析文字

违反此规则 = pipeline 中断 = 任务失败
```

#### 铁律 3: 每个模块是原子操作

spawn → yield → exec 验证 → 下一个模块。中间不插入任何 text。

### 编排流程

```
Phase 1: Planner
  → spawn Planner Agent
  → yield → gate（PlannerOutput Pydantic + Planner Gate）
  → checkpoint

Phase 2: Build
  → 读取 PlannerOutput.workers
  → 对每个 WorkerSpec: 程序化拼接 Prompt
  → spawn_parallel Workers（遵守依赖顺序）
  → yield → 对每个 Worker: gate（output_schema Pydantic）
  → checkpoint

Phase 3: Shipper
  → spawn Meta Shipper → yield → gate
  → spawn Consolidator → yield → gate
  → 执行固定验证层（4 层 Gate）
  → PASS → finalize
  → FAIL → spawn Fix Agent → yield → 重跑验证
  → checkpoint
```

---

## 5. 与 Solution Pro 角色对应

| Solution Pro 角色 | Ship Pro 角色 | 差异 |
|------------------|--------------|------|
| Planning Planner | Planner | Ship Pro 的 Planner 同时做分析+规划 |
| Planning Expert × N | Worker × N | 职责不同但模式相同（动态 spawn） |
| Research Expert × N | — | Ship Pro 无独立 Research 阶段 |
| Devil's Advocate | — | Ship Pro 无对抗角色（约束笼子替代） |
| Gap Analyst | — | Ship Pro 的完整性检查替代 |
| Base Synthesizer | Consolidator | 都是合并产出 |
| Meta Summary Planner | Meta Shipper | 都是规划整合策略 |
| Analyzer × N | — | Ship Pro 无独立分析阶段 |
| Fix Judge + Fix Agent | Fix Agent | Ship Pro 合并为单一角色 |
| Harness Check | Harness Judge | 相同模式 |
| Summarizer | — | Ship Pro 的 Consolidator 替代 |
| JSON Extractor | — | Ship Pro 的 Pydantic Gate 替代 |
