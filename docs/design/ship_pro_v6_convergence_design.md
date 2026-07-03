# Ship Pro V6 — 收敛机制设计

> **版本**: 6.0.0 | **日期**: 2026-07-03  
> **配套文档**: `ship_pro_v6_architecture.md`, `ship_pro_v6_role_specifications.md`

---

## 设计来源

- `ship_pro_v6_architecture.md` — 4 Phase 架构
- `ship_pro_v6_role_specifications.md` — 角色规格
- Solution Pro `convergence_design_v3.md` — 收敛模式参考

---

## 核心问题

Ship Pro 的收敛挑战与 Solution Pro 不同：

| Solution Pro 挑战 | Ship Pro 挑战 |
|------------------|--------------|
| 从 200+ 个 Finding 收敛到 1 个方案 | 从 N 个 Worker 产出收敛到 1 个交付包 |
| 约束可能互相矛盾 | Worker 产出可能重叠或冲突 |
| 需要 Devil's Advocate 对抗 | 不需要对抗，需要整合 |
| 信息守恒 = 约束不丢失 | 信息守恒 = Solution Pro 的需求都有对应交付物 |

---

## 收敛架构总览

```
Phase 1: Planner
  PlannerOutput (结构化 JSON)
    ↓
  ┌─────────────────────────────────┐
  │ Planner Gate                     │
  │ - Worker 数量 2~8               │
  │ - 依赖图无环                    │
  │ - 约束引用非空                  │
  │ - 角色名称合规                  │
  └─────────────────────────────────┘
    ↓ PASS

Phase 2: Build (Workers × N)
  Worker 产出 × N (各自独立 stage)
    ↓
  ┌─────────────────────────────────┐
  │ Worker Gate (per worker)        │
  │ - output_schema Pydantic 验证   │
  │ - must_constraints 保留检查     │
  └─────────────────────────────────┘
    ↓ PASS

Phase 3: Shipper
  ┌─────────────────────────────────┐
  │ Step 1: Meta Shipper (LLM)     │ → integration_plan
  │ Step 2: Consolidator (LLM)     │ → ship_package_draft
  │ Step 3: 固定验证层 (4 Gate)     │ → ship_package / FAIL
  │ Step 4: Fix Agent (可选)        │ → ship_package_refined
  │ Step 5: Finalize               │ → ship_package.json + summary.md
  └─────────────────────────────────┘
```

---

## 约束笼子（三层）

### 约束 1: 任务边界约束

```
Ship Pro 只做"拆解 + 交付"，不做"设计 + 决策"。

如果 Solution Pro 没说的 → Ship Pro 不补充
如果 Solution Pro 说了的 → Ship Pro 不修改

违反检测:
  - Phase 3 信息守恒检查: 检测 Ship Pro 产出中是否存在
    Solution Pro 未提及的需求/功能
  - 如果存在 → 标记为 WARNING（人工审查）或 FAIL（自动拒绝）
```

### 约束 2: 角色边界约束

```
每个角色只做自己该做的事:

Planner:
  ✅ 规划"怎么拆"
  ❌ 讨论"该不该拆"
  ❌ 评价 Solution Pro 方案优劣

Worker:
  ✅ 生成交付物（WP/AC/依赖图/模板）
  ❌ 讨论方案优劣
  ❌ 修改其他 Worker 的产出

Shipper:
  ✅ 汇总已有产出
  ✅ 解决冲突（选择与 Solution Pro 更一致的方案）
  ❌ 补充新内容
  ❌ 删减已有产出

违反检测:
  - Prompt 注入约束（每个角色的 prompt 明确写入禁止项）
  - Phase 3 Gate 验证产出是否包含禁止内容
```

### 约束 3: 输出边界约束

```
每个阶段的输出必须符合 Pydantic Schema。

Schema 里没有的字段 → LLM 不能自由发挥
如果 LLM 想加内容 → 必须标记为 optional_suggestion

optional_suggestion 存储:
  - 物理隔离: ship_package.metadata.optional_suggestions
  - Summarizer 禁止读取该字段
  - Phase 3 信息守恒检查验证"主交付物中是否存在 optional_suggestion 的内容"

违反检测:
  - Pydantic Gate: 多余字段直接 FAIL
  - 信息守恒检查: 主交付物包含 optional_suggestion 内容 → FAIL
```

---

## Phase 1: Planner Gate

### 验证清单

| # | 检查项 | 类型 | 标准 | FAIL 处理 |
|---|--------|------|------|-----------|
| PG-1 | Worker 数量 | 代码 | 2 ≤ N ≤ 8 | 自动截断 + WARNING |
| PG-2 | 角色名称 | 代码 | 在允许列表内或 `task_description` 中有理由 | WARNING |
| PG-3 | 依赖图无环 | 代码 | 拓扑排序成功 | FAIL → 重新规划 |
| PG-4 | 约束引用非空 | 代码 | 每个 WorkerSpec 的 `solution_pro_refs` 非空 | FAIL → 重新规划 |
| PG-5 | web_search 理由 | LLM | 搜索范围与任务相关 | WARNING |
| PG-6 | output_schema 存在 | 代码 | 引用的 Pydantic 模型已注册 | FAIL → 重新规划 |

### Gate 逻辑

```python
class PlannerGate:
    """Phase 1 Planner 输出验证"""
    
    def check(self, planner_output: PlannerOutput) -> GateResult:
        issues = []
        
        # PG-1: Worker 数量
        if not (2 <= len(planner_output.workers) <= 8):
            issues.append(GateIssue(
                id="PG-1", severity="warning",
                message=f"Worker 数量 {len(planner_output.workers)} 不在 [2,8] 范围内"
            ))
        
        # PG-3: 依赖图无环
        if self._has_cycle(planner_output.workers):
            issues.append(GateIssue(
                id="PG-3", severity="fail",
                message="Worker 依赖图存在环"
            ))
        
        # PG-4: 约束引用非空
        for w in planner_output.workers:
            if not w.solution_pro_refs:
                issues.append(GateIssue(
                    id="PG-4", severity="fail",
                    message=f"Worker {w.role} 未引用 Solution Pro 字段"
                ))
        
        # PG-6: output_schema 存在
        for w in planner_output.workers:
            if not self._schema_exists(w.output_schema):
                issues.append(GateIssue(
                    id="PG-6", severity="fail",
                    message=f"Worker {w.role} 的 output_schema '{w.output_schema}' 未注册"
                ))
        
        has_fail = any(i.severity == "fail" for i in issues)
        return GateResult(
            verdict="FAIL" if has_fail else "PASS",
            issues=issues
        )
```

---

## Phase 2: Worker Gate（per worker）

### 验证清单

| # | 检查项 | 类型 | 标准 | FAIL 处理 |
|---|--------|------|------|-----------|
| WG-1 | Schema 验证 | 代码 | 输出符合 `output_schema` | increment-retry → 重新 spawn |
| WG-2 | MUST 约束保留 | 代码+LLM | `must_constraints` 中的约束在产出中有体现 | increment-retry → 重新 spawn |
| WG-3 | web_search 范围 | LLM | 搜索内容在 `web_search_scope` 范围内 | WARNING |

### Gate 逻辑

```python
class WorkerGate:
    """Phase 2 单个 Worker 输出验证"""
    
    def check(self, worker_spec: WorkerSpec, worker_output: dict) -> GateResult:
        issues = []
        
        # WG-1: Schema 验证
        schema = get_schema(worker_spec.output_schema)
        try:
            schema.model_validate(worker_output)
        except ValidationError as e:
            issues.append(GateIssue(
                id="WG-1", severity="fail",
                message=f"Schema 验证失败: {e}"
            ))
        
        # WG-2: MUST 约束保留
        for constraint_id in worker_spec.must_constraints:
            if not self._constraint_preserved(constraint_id, worker_output):
                issues.append(GateIssue(
                    id="WG-2", severity="fail",
                    message=f"MUST 约束 {constraint_id} 未在产出中体现"
                ))
        
        has_fail = any(i.severity == "fail" for i in issues)
        return GateResult(
            verdict="FAIL" if has_fail else "PASS",
            issues=issues
        )
```

---

## Phase 3: 固定验证层（4 Gate）

### 验证清单

| Gate | 名称 | 类型 | 标准 | 场景无关 |
|------|------|------|------|:---:|
| G1 | Pydantic Gate | 代码 | 字段存在、类型正确、必填项非空 | ✅ |
| G2 | 信息守恒检查 | 代码+LLM | Solution Pro 的需求都有对应交付物 | ✅ |
| G3 | 完整性检查 | 代码+LLM | 覆盖深度达标 | ✅ |
| G4 | Harness V3 | LLM | AC 质量 + 依赖合理性 + 可操作性 | ✅ |

### G1: Pydantic Gate

```python
class ShipPackageGate:
    """G1: Schema 格式验证"""
    
    def check(self, ship_package: dict) -> GateResult:
        try:
            ShipPackage.model_validate(ship_package)
            return GateResult(verdict="PASS", issues=[])
        except ValidationError as e:
            return GateResult(
                verdict="FAIL",
                issues=[GateIssue(
                    id="G1", severity="fail",
                    message=f"ShipPackage Schema 验证失败: {e}"
                )]
            )
```

### G2: 信息守恒检查

> **核心**: Solution Pro 的 MUST 约束在 Ship Pro 产出中有对应。

```python
class InformationConservationGate:
    """G2: 信息守恒检查"""
    
    def check(self, ship_package: dict, solution_pro_output: dict) -> GateResult:
        issues = []
        
        # L1 代码检查: key_design_decisions 覆盖
        decisions = solution_pro_output.get("key_design_decisions", [])
        for decision in decisions:
            if not self._decision_covered(decision, ship_package):
                issues.append(GateIssue(
                    id="G2-L1", severity="fail",
                    message=f"设计决策未覆盖: {decision.get('id', '?')}"
                ))
        
        # L2 LLM 检查: 语义一致性
        semantic_issues = self._llm_semantic_check(ship_package, solution_pro_output)
        issues.extend(semantic_issues)
        
        # L3 optional_suggestion 渗透检查
        if self._suggestion_leaked(ship_package):
            issues.append(GateIssue(
                id="G2-L3", severity="fail",
                message="optional_suggestion 内容渗透到主交付物"
            ))
        
        has_fail = any(i.severity == "fail" for i in issues)
        return GateResult(
            verdict="FAIL" if has_fail else "PASS",
            issues=issues
        )
```

#### 覆盖深度定义

| 深度 | 定义 | 适用优先级 |
|------|------|-----------|
| 浅层 | 提到关键词 | P2 REQ |
| 中层 | 描述实现方式 | P1 REQ |
| 深层 | 给出具体代码/配置/参数 | P0 REQ |

#### Solution Pro MUST 约束提取

Solution Pro 的 `final_solution.json` 中需要增加 `must_constraints` 字段：

```json
{
  "must_constraints": [
    {
      "id": "MUST-001",
      "description": "必须使用 Python 3.10+",
      "category": "tech_stack",
      "source": "UC-009"
    },
    {
      "id": "MUST-002",
      "description": "必须支持离线模式",
      "category": "feature",
      "source": "UC-012"
    }
  ]
}
```

> **待 Solution Pro 侧配合**: 在 Summary 模块的 JSON Extractor 阶段增加 `must_constraints` 提取逻辑。

### G3: 完整性检查

```python
class CompletenessGate:
    """G3: 完整性检查 — 所有需求都有对应产出"""
    
    def check(self, ship_package: dict, solution_pro_output: dict) -> GateResult:
        issues = []
        
        # L1 代码检查: 需求覆盖
        requirements = solution_pro_output.get("requirements", [])
        work_packages = ship_package.get("work_packages", [])
        
        for req in requirements:
            if not self._req_has_wp(req, work_packages):
                issues.append(GateIssue(
                    id="G3-L1", severity="fail",
                    message=f"需求 {req['id']} 无对应工作包"
                ))
        
        # L2 LLM 检查: 覆盖深度
        for req in requirements:
            depth = self._llm_coverage_depth(req, work_packages)
            required_depth = self._required_depth(req["priority"])
            if depth < required_depth:
                issues.append(GateIssue(
                    id="G3-L2", severity="warning",
                    message=f"需求 {req['id']} 覆盖深度不足 ({depth} < {required_depth})"
                ))
        
        has_fail = any(i.severity == "fail" for i in issues)
        return GateResult(
            verdict="FAIL" if has_fail else "PASS",
            issues=issues
        )
```

### G4: Harness V3

> **核心**: 交付物质量评估 — AC 质量、依赖合理性、可操作性。

```python
class HarnessV3Gate:
    """G4: Harness V3 — 交付物质量评估"""
    
    HARNESS_PROMPT = """
你是交付物质量评估专家。评估以下 Ship Package 的质量。

## 评估维度

### 1. AC 质量（Acceptance Criteria）
- 每条 AC 是否可执行？（能直接用来写测试）
- 每条 AC 是否可验证？（有明确的通过/失败标准）
- 每条 AC 是否具体？（不含"功能实现完成"等模板文本）

### 2. 依赖合理性
- 依赖关系是否合理？（无循环依赖、无不必要的依赖）
- 关键路径是否清晰？
- 并行度是否合理？

### 3. 可操作性
- 拿到这个交付包，开发人员能否直接开始工作？
- 每个 WP 的范围是否明确？（不大不小）
- 交付物清单是否完整？

## 输入

### Ship Package
{ship_package}

### Solution Pro 原始方案（参考）
{solution_pro_summary}

## 输出（JSON）
{
  "ac_quality": {
    "score": 0-10,
    "issues": ["..."],
    "executable_count": N,
    "verifiable_count": N,
    "specific_count": N
  },
  "dependency_rationality": {
    "score": 0-10,
    "issues": ["..."],
    "critical_path_length": N,
    "parallel_groups": N
  },
  "actionability": {
    "score": 0-10,
    "issues": ["..."],
    "ready_to_start_count": N,
    "total_wp_count": N
  },
  "overall_score": 0-10,
  "verdict": "PASS|CONDITIONAL|FAIL",
  "fix_suggestions": ["..."]
}

## 判定标准
- overall_score >= 7 → PASS
- overall_score >= 5 → CONDITIONAL（附 fix_suggestions）
- overall_score < 5 → FAIL
"""
```

---

## Phase 3 收敛循环

```
                    ┌──────────────┐
                    │ Meta Shipper │
                    │   (LLM)      │
                    └──────┬───────┘
                           ↓ integration_plan
                    ┌──────────────┐
                    │ Consolidator │
                    │   (LLM)      │
                    └──────┬───────┘
                           ↓ ship_package_draft
              ┌────────────────────────────┐
              │ 固定验证层 (G1→G2→G3→G4)   │
              └────────────┬───────────────┘
                           ↓
              ┌────────────────────────────┐
              │ Verdict?                    │
              │ PASS → Finalize ✅          │
              │ FAIL → Fix Agent → 重跑验证 │
              │ Max 2 轮                    │
              └────────────────────────────┘
```

### Fix Agent 行为

```python
class FixAgent:
    """定向修复 — 只修复 Gate FAIL 报告中标记的问题"""
    
    FIX_PROMPT = """
你是修复专家。根据以下 Gate FAIL 报告，定向修复 Ship Package。

## 修复规则
1. 只修复报告中标记的问题
2. 不增加新 WP 或新需求
3. 不修改与问题无关的内容
4. 修复后输出完整的 ship_package（不是 diff）

## Gate FAIL 报告
{gate_report}

## 当前 Ship Package
{ship_package_draft}

## 输出
修复后的完整 ship_package（JSON）
"""
```

---

## 信息守恒报告

### 输出格式

```json
{
  "gate": "information_conservation",
  "verdict": "PASS|FAIL",
  "checks": [
    {
      "id": "G2-L1-001",
      "constraint_id": "MUST-001",
      "description": "必须使用 Python 3.10+",
      "status": "PASS",
      "evidence": "WP-003 中明确指定 Python 3.11"
    },
    {
      "id": "G2-L1-002",
      "constraint_id": "MUST-002",
      "description": "必须支持离线模式",
      "status": "FAIL",
      "evidence": "未找到离线模式相关的 WP 或 AC"
    }
  ],
  "coverage_rate": 0.5,
  "missing_constraints": ["MUST-002"],
  "leaked_suggestions": false
}
```

---

## Optional Suggestion 机制

### 存储

```json
{
  "ship_package": {
    "modules": [...],
    "work_packages": [...],
    "dependencies": {...},
    "metadata": {
      "optional_suggestions": [
        {
          "source": "wp_decomposer",
          "suggestion": "建议增加一个性能测试 WP",
          "rationale": "当前 WP 列表缺少性能测试",
          "impact": "low"
        }
      ],
      "search_logs": [
        {
          "worker": "ac_writer",
          "query": "Python asyncio best practices 2026",
          "results_used": 2
        }
      ],
      "worker_prompts": {
        "wp_decomposer": "...(完整 prompt)...",
        "ac_writer": "...(完整 prompt)..."
      }
    }
  }
}
```

### 隔离规则

| 规则 | 说明 |
|------|------|
| Summarizer 禁止读取 | Consolidator 和 Harness Judge 的 prompt 中不包含 `optional_suggestions` |
| 信息守恒检查验证 | G2-L3 检查主交付物是否包含 suggestion 内容 |
| 人工审查 | 最终交付时，`optional_suggestions` 单独展示给用户决策 |

---

## 超时配置

| 组件 | 超时 | 说明 |
|------|------|------|
| Planner | 600s | Phase 1 单次 LLM 调用 |
| 单 Worker | 600s | Phase 2 单个 Worker |
| Phase 2 总计 | 900s | 所有 Worker 完成 |
| Meta Shipper | 300s | Phase 3 Step 1 |
| Consolidator | 600s | Phase 3 Step 2 |
| Fix Agent | 600s | Phase 3 Step 4（每轮） |
| Phase 3 总计 | 1800s | 含最多 2 轮 Fix |
| **Pipeline 总计** | **3600s (1h)** | 硬上限 |

---

## 状态管理

### State Machine 规则

> **来源**: Solution Pro V2 教训 S5 — 无 state machine 保护导致非法状态转换

```
合法状态转换:
  pending → running     (Orchestrator 开始执行)
  running → completed   (Gate PASS)
  running → failed      (Gate FAIL 且 retry 耗尽)
  failed  → running     (Fix Agent 修复后重试)
  
非法转换（代码强制拒绝）:
  completed → running   (已完成的阶段不能重跑，除非 fix_and_rerun)
  completed → pending   (已完成不能回退)
  failed → completed    (失败不能直接标记完成)
```

**实现**: `PipelineStateManager` 在每次状态变更时检查转换合法性，非法转换 raise `StateTransitionError`。

**fix_and_rerun 例外**: 当 Phase 3 Gate FAIL 触发 Fix Agent 时，Orchestrator 将受影响的 Worker 状态从 `completed` 重置为 `pending`（通过 `fix_context` 命令），这是唯一允许的 `completed → pending` 转换。

### Blackboard Stage 文件

| Phase | Stage | 创建者 | 消费者 |
|-------|-------|--------|--------|
| 1 | `planner_output` | Planner | Orchestrator, Phase 3 |
| 2 | `worker_{role}` | Worker × N | Consolidator, Harness |
| 3 | `integration_plan` | Meta Shipper | Consolidator |
| 3 | `ship_package_draft` | Consolidator | Harness, Fix Agent |
| 3 | `harness_report` | Harness Judge | Fix Agent, Orchestrator |
| 3 | `ship_package_refined` | Fix Agent | Harness (重跑) |
| 3 | `ship_package` | Orchestrator | 最终交付 |
| 3 | `summary` | Orchestrator | 用户 |

### Pipeline State

```json
{
  "run_id": "run_20260703_124400",
  "status": "running",
  "current_phase": "build",
  "phases": {
    "planner": {"status": "completed", "gate": "PASS"},
    "build": {
      "status": "running",
      "workers": {
        "wp_decomposer": {"status": "completed", "gate": "PASS"},
        "ac_writer": {"status": "running", "gate": null},
        "dependency_analyzer": {"status": "pending", "gate": null}
      }
    },
    "shipper": {"status": "pending"}
  },
  "fix_rounds": 0,
  "max_fix_rounds": 2
}
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 6.0.0 | 2026-07-03 | 初始设计 |
