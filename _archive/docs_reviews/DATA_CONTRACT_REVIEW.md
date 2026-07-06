# 数据契约评审报告

> **评审范围**: `.v3/` 目录下 5 个核心模块的所有 dataclass 和 Enum 类型
> **评审人**: 数据契约评审专家（Subagent）
> **日期**: 2026-04-14

---

## 总评

- **数据契约评分: 5.5/10**
- **⚠️ 关键前置发现**: `v3_protocols.py` 文件**不存在**！协议层尚未创建。本次评审基于对 5 个实际代码模块的交叉审计。
- **主要优点**:
  - Enum 定义清晰，各模块内部枚举值完整且无冗余
  - `GateDecision(str, Enum)` 设计合理，字符串枚举便于序列化
  - `QualityReport` / `DimensionScore` 的 `__post_init__` 自动计算逻辑良好
  - `BlackboardConfig` 的 `session_dir` property 设计优雅
  - `ResilienceManager` 的 `Task` / `Result` / `Checkpoint` 字段完备
- **主要缺陷**:
  - **P0**: 两套质量配置体系（`QualityConfig` vs `DomainQualityConfig`）尺度冲突（0-100 vs 0-1），需跨模块手动转换
  - **P0**: `QualityGate.Task` 与 `pipeline_engine.py` 中构造 `Task()` 的参数不匹配
  - **P0**: `BlackboardManager.add_quality_score()` 签名与调用方传参不匹配
  - **P1**: `PipelineState.CONVERGED` 枚举值从未被设置为状态，是死状态
  - **P1**: `_determine_next_stage` 返回 `"wait_hitl"` 但管线模板中无此 stage_id
  - **P1**: 两套质量维度配置命名不一致（`DimensionConfig` vs `QualityDimension`）
  - **P2**: 部分默认值缺乏合理性验证

---

## 数据类字段对比

### PipelineState (pipeline_engine.py)

| 枚举值 | 定义 | 实际使用 | 一致? | 说明 |
|--------|------|---------|-------|------|
| INIT | ✅ | ✅ `__init__` | ✅ | 初始状态 |
| RUNNING | ✅ | ✅ `run()` 开始 | ✅ | |
| WAITING_HITL | ✅ | ✅ `_execute_gate_stage`, `_execute_stage` | ✅ | |
| CONVERGED | ✅ | ❌ **从未设置** | ❌ | `_build_result` 检查此值但 state 永远不会被设为它；收敛时设的是 DONE |
| MAX_ITERATIONS | ✅ | ✅ `_determine_next_stage` | ✅ | |
| FAILED | ✅ | ✅ 多处异常处理 | ✅ | |
| DONE | ✅ | ✅ `run()` 正常结束 | ✅ | |

**问题**: `CONVERGED` 是**死状态**——代码中 `self.state = PipelineState.CONVERGED` 从未出现。收敛时设置的是 `DONE`。

### StageResult (pipeline_engine.py)

| 字段 | 实际类型 | 协议（定义）类型 | 一致? |
|------|---------|--------------|-------|
| success | bool | bool | ✅ |
| output_file | Optional[str] | Optional[str] | ✅ |
| score | float = 0.0 | float | ✅ |
| error | Optional[str] | Optional[str] | ✅ |
| duration_ms | int = 0 | int | ✅ |

**评价**: 字段完整，类型一致。

### PipelineResult (pipeline_engine.py)

| 字段 | 实际类型 | 协议（定义）类型 | 一致? |
|------|---------|--------------|-------|
| success | bool | bool | ✅ |
| state | PipelineState | PipelineState | ✅ |
| iteration | int | int | ✅ |
| final_score | float | float | ✅ |
| output_files | List[str] | List[str] | ✅ |
| error | Optional[str] | Optional[str] | ✅ |
| duration_sec | float = 0.0 | float | ✅ |

**评价**: 字段完整。注意 `output_files` 来自 `self._blackboard.list_files("*.md")`，返回 `List[Path]` 而非 `List[str]`——存在**类型不匹配**。

### GateDecision (quality_gate.py)

| 枚举值 | 定义 | 实际使用 | 一致? |
|--------|------|---------|-------|
| PASS | ✅ | ✅ `_compute_decision` | ✅ |
| HITL | ✅ | ✅ `_compute_decision`, `_build_reasoning` | ✅ |
| REJECT | ✅ | ✅ `_compute_decision`, `_build_reasoning` | ✅ |

**评价**: 3 个值完整覆盖门控决策，无冗余。`str, Enum` 设计便于 JSON 序列化。

### DimensionScore (quality_gate.py)

| 字段 | 实际类型 | 协议（定义）类型 | 一致? |
|------|---------|--------------|-------|
| name | str | str | ✅ |
| score | float | float | ✅ |
| weight | float | float | ✅ |
| threshold | float | float | ✅ |
| passed | bool (computed) | bool (field(init=False)) | ✅ |

**评价**: `__post_init__` 自动计算 `passed`，设计合理。`gap` 和 `is_failed` property 提供便捷访问。

### QualityReport (quality_gate.py)

| 字段 | 实际类型 | 协议（定义）类型 | 一致? |
|------|---------|--------------|-------|
| overall_score | float | float | ✅ |
| dimensions | Dict[str, DimensionScore] | Dict[str, DimensionScore] | ✅ |
| decision | GateDecision | GateDecision | ✅ |
| reasoning | str | str | ✅ |
| timestamp | float | float (default_factory=time.time) | ✅ |

**评价**: 字段完整。`all_passed` / `failed_dimensions` property 提供便捷访问。

### QualityConfig (quality_gate.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| dimensions | List[DimensionConfig] | 必填 | ✅ |
| auto_pass_threshold | float | 80.0 | ✅ |
| hitl_threshold | float | 70.0 | ✅ |
| convergence_improvement_threshold | float | 2.0 | ✅ |
| convergence_stagnation_count | int | 3 | ✅ |
| convergence_oscillation_count | int | 4 | ✅ |
| convergence_divergence_count | int | 3 | ✅ |

**评价**: 字段完整。⚠️ 所有阈值尺度为 **0-100**，见下方尺度分析。

### DimensionConfig (quality_gate.py)

| 字段 | 实际类型 | 协议（定义）类型 | 一致? |
|------|---------|--------------|-------|
| name | str | str | ✅ |
| weight | float | float | ✅ |
| threshold | float | float | ✅ |

**评价**: 简洁。`validate()` 方法验证 `threshold` 范围为 0-100。

### CircuitState (resilience_manager.py)

| 枚举值 | 定义 | 实际使用 | 一致? |
|--------|------|---------|-------|
| CLOSED | ✅ | ✅ 初始状态、record_success | ✅ |
| OPEN | ✅ | ✅ record_failure | ✅ |
| HALF_OPEN | ✅ | ✅ state property 自动检测超时 | ✅ |

**评价**: 3 个值覆盖完整熔断器状态机。

### HealthLevel (resilience_manager.py)

| 枚举值 | 定义 | 实际使用 | 一致? |
|--------|------|---------|-------|
| HEALTHY | ✅ | ✅ check_resource_health | ✅ |
| DEGRADED | ✅ | ✅ check_resource_health | ✅ |
| CRITICAL | ✅ | ✅ check_resource_health | ✅ |
| UNKNOWN | ✅ | ✅ 资源监控禁用时 | ✅ |

**评价**: 4 个值完整。

### HealthStatus (resilience_manager.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| level | HealthLevel | 必填 | ✅ |
| cpu_usage | float | 0.0 | ✅ |
| memory_usage_mb | float | 0.0 | ✅ |
| active_agents | int | 0 | ✅ |
| message | str | "" | ✅ |

**评价**: `is_healthy` property 便捷。

### Task (resilience_manager.py) ⚠️

| 字段 | resilience_manager 定义 | pipeline_engine 使用 | 一致? |
|------|------------------------|---------------------|-------|
| agent_id | str | ❌ **未提供** | ❌ |
| task_prompt | str | ❌ **未提供** | ❌ |
| model | str = "default" | ❌ **未提供** | ❌ |
| fallback_model | str = "lightweight" | ❌ **未提供** | ❌ |
| timeout | Optional[float] | ✅ | ✅ |
| metadata | Dict[str, Any] | ❌ **未提供** | ❌ |

**pipeline_engine.py 第 306 行实际构造**:
```python
task = Task(
    id=f"{stage.id}_{instance_name}",    # ← Task 没有 id 字段！
    coro=agent_executor(),               # ← Task 没有 coro 字段！
    stage=stage.id,                      # ← Task 没有 stage 字段！
)
```

**🔴 P0 严重问题**: `pipeline_engine.py` 用 `id`, `coro`, `stage` 构造 `Task`，但 `resilience_manager.py` 定义的 `Task` 字段是 `agent_id`, `task_prompt`, `model`, `fallback_model`, `timeout`, `metadata`。**两者完全不兼容！**

### Result (resilience_manager.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| success | bool | 必填 | ✅ |
| output | str | "" | ✅ |
| error | str | "" | ✅ |
| score | float | 0.0 | ✅ |
| execution_time | float | 0.0 | ✅ |
| attempt | int | 1 | ✅ |
| model_used | str | "" | ✅ |
| degraded | bool | False | ✅ |

**评价**: 字段完整。⚠️ 类名 `Result` 过于通用，建议改为 `AgentResult` 或 `TaskResult` 避免命名冲突。

### Checkpoint (resilience_manager.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| stage | str | 必填 | ✅ |
| data | Dict[str, Any] | 必填 | ✅ |
| timestamp | float | field(default_factory=time.time) | ✅ |

**评价**: 简洁合理。

### AgentConfig (config_loader.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| role | str | 必填 | ✅ |
| agent_id | Optional[str] | None | ✅ |
| model | Optional[str] | None | ✅ |
| prompt | Optional[str] | None | ✅ |
| timeout | int | 300 | ✅ |
| retry | int | 1 | ✅ |
| instances | List[Dict[str, str]] | field(default_factory=list) | ✅ |
| parallel | str | "all" | ✅ |

**评价**: 字段完整。`__post_init__` 验证 role 在 `SUPPORTED_ROLES` 中。

### QualityDimension (config_loader.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| name | str | 必填 | ✅ |
| weight | float | 1.0 | ✅ |
| threshold | float | 0.80 | ✅ |
| description | str | "" | ✅ |

**评价**: ⚠️ 与 `quality_gate.DimensionConfig` 功能相同但命名不同，且尺度为 **0-1**。

### DomainQualityConfig (config_loader.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| dimensions | List[QualityDimension] | field(default_factory=list) | ✅ |
| global_threshold | float | 0.80 | ✅ |
| auto_pass_threshold | float | 0.85 | ✅ |
| human_gate_threshold | float | 0.70 | ✅ |

**评价**: ⚠️ 与 `quality_gate.QualityConfig` 功能相同但命名/尺度/字段名均不同。

### PipelineStage (config_loader.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| id | str | 必填 | ✅ |
| name | str | 必填 | ✅ |
| type | str | "agent" | ✅ |
| agent | Optional[str] | None | ✅ |
| next | Optional[str] | None | ✅ |
| on_converged | Optional[str] | None | ✅ |
| on_not_converged | Optional[str] | None | ✅ |
| on_pass | Optional[str] | None | ✅ |
| on_fail | Optional[str] | None | ✅ |
| parallel | bool | False | ✅ |
| condition | Optional[str] | None | ✅ |

**评价**: ⚠️ `condition` 字段从未被 `pipeline_engine.py` 使用。可能是预留字段或死代码。

### DomainConfig (config_loader.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| domain | str | 必填 | ✅ |
| version | str | "3.0" | ✅ |
| description | str | "" | ✅ |
| intent_keywords | List[str] | field(default_factory=list) | ✅ |
| default_action | str | "analyze" | ✅ |
| pipeline | str | "iterative" | ✅ |
| max_iterations | int | 10 | ✅ |
| convergence_threshold | float | 0.02 | ✅ |
| min_iterations | int | 3 | ✅ |
| target_score | float | 0.88 | ✅ |
| agents | List[AgentConfig] | field(default_factory=list) | ✅ |
| quality | DomainQualityConfig | field(default_factory=DomainQualityConfig) | ✅ |
| delivery | DeliveryConfig | field(default_factory=DeliveryConfig) | ✅ |
| resilience | ResilienceConfig | field(default_factory=ResilienceConfig) | ✅ |
| source_file | Optional[str] | None | ✅ |

**评价**: 字段完整。`enable_hitl` property 逻辑正确（仅 gated 管线启用）。

### PipelineTemplate (config_loader.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| name | str | 必填 | ✅ |
| description | str | "" | ✅ |
| stages | List[PipelineStage] | field(default_factory=list) | ✅ |
| source_file | Optional[str] | None | ✅ |

**评价**: 简洁合理。

### BlackboardConfig (blackboard_manager.py)

| 字段 | 实际类型 | 默认值 | 一致? |
|------|---------|--------|-------|
| base_dir | Path | field(default_factory=lambda: ...) | ✅ |
| session_id | str | "" | ✅ |
| max_file_size_mb | int | 10 | ✅ |
| auto_cleanup | bool | True | ✅ |

**评价**: ⚠️ `session_id` 默认为空字符串，虽然构造时会覆盖，但作为 dataclass 默认值不够安全。

---

## 尺度标注问题

| 类型 | 字段 | 实际尺度 | 字段名暗示 | 清晰? |
|------|------|---------|-----------|-------|
| QualityConfig | auto_pass_threshold | **0-100** (80.0) | "threshold" 无尺度暗示 | ❌ |
| QualityConfig | hitl_threshold | **0-100** (70.0) | "threshold" 无尺度暗示 | ❌ |
| QualityConfig (DimensionConfig) | threshold | **0-100** (validate: 0-100) | "threshold" 无尺度暗示 | ❌ |
| DomainQualityConfig | global_threshold | **0-1** (0.80) | "threshold" 无尺度暗示 | ❌ |
| DomainQualityConfig | auto_pass_threshold | **0-1** (0.85) | 同名但不同尺度！ | 🔴 |
| DomainQualityConfig | human_gate_threshold | **0-1** (0.70) | 与 hitl_threshold 不同名但同概念 | ❌ |
| QualityDimension | threshold | **0-1** (0.80) | "threshold" 无尺度暗示 | ❌ |
| DomainConfig | target_score | **0-1** (0.88) | "score" 暗示 0-1 但不明确 | ❌ |
| DomainConfig | convergence_threshold | **0-1** (0.02) | "threshold" 无尺度暗示 | ❌ |

### 🔴 尺度冲突核心问题

同一系统中存在**两套质量评分体系**：
1. **QualityGate 体系**（`quality_gate.py`）：使用 **0-100** 尺度
2. **DomainConfig 体系**（`config_loader.py` + `pipeline_engine.py`）：使用 **0-1** 尺度

**pipeline_engine.py 第 400 行的手动转换暴露了问题**：
```python
current_score = quality_report.overall_score / 100.0  # 转为0-1范围
```

这个手动转换是正确的，但它说明两套体系的尺度差异没有被清晰标注或文档化。

### 字段名歧义

| 字段对 | 问题 |
|--------|------|
| `QualityConfig.auto_pass_threshold` (80.0) vs `DomainQualityConfig.auto_pass_threshold` (0.85) | **同名不同尺度，极易混淆** |
| `QualityConfig.hitl_threshold` vs `DomainQualityConfig.human_gate_threshold` | **同概念不同名** |
| `QualityConfig` vs `DomainQualityConfig` | **命名过于相似，容易用错** |

---

## 改进建议

### 1. P0 必须修复

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| P0-1 | **Task 字段不匹配** | `pipeline_engine.py:306` 用 `id, coro, stage` 构造 Task，但 `resilience_manager.py:81` 定义为 `agent_id, task_prompt, model...` | 方案 A：修改 `resilience_manager.Task` 增加 `id`, `coro`, `stage` 字段；方案 B：创建独立的 `PipelineTask` dataclass；方案 C：让 `execute_with_resilience` 接受 `coro` 参数而非 `Task` 对象。**推荐方案 C**：改为 `async def execute_with_resilience(self, coro, agent_id, ...)` |
| P0-2 | **add_quality_score 签名不匹配** | `blackboard_manager.py` 签名 `add_quality_score(stage, score, passed)` 但调用方 `pipeline_engine.py:409` 传入 `add_quality_score(current_score, quality_report.decision.value)` | 修改调用方：`self._blackboard.add_quality_score(stage.id, current_score, quality_report.decision == GateDecision.PASS)` |
| P0-3 | **PipelineResult.output_files 类型不匹配** | `pipeline_engine.py` 返回 `List[str]` 但 `list_files()` 返回 `List[Path]` | 改为 `output_files: List[Path] = field(default_factory=list)` 或在 `_build_result` 中 `list(map(str, ...))` |
| P0-4 | **尺度混乱未标注** | `QualityConfig` (0-100) vs `DomainQualityConfig` (0-1) | 统一为单一尺度，或在类型定义上添加清晰的注释/类型别名如 `Score0to100` / `Score0to1` |

### 2. P1 建议修复

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| P1-1 | **CONVERGED 死状态** | `PipelineState.CONVERGED` 从未被设置 | 要么删除该枚举值（收敛时用 DONE），要么在收敛检测后设置 `self.state = PipelineState.CONVERGED` |
| P1-2 | **wait_hitl stage_id 不存在** | `_determine_next_stage` 返回 `"wait_hitl"` 但任何管线模板中无此 stage | 修复：在 `_execute_gate_stage` 的 HITL 分支中返回实际存在的 stage_id，或让 gate 阶段直接暂停等待外部触发 |
| P1-3 | **DimensionConfig vs QualityDimension 命名冲突** | `quality_gate.DimensionConfig` 与 `config_loader.QualityDimension` 功能相同 | 统一为一个定义（建议在 `v3_protocols.py` 中），或重命名为 `GateDimensionConfig` / `LoaderQualityDimension` 以区分 |
| P1-4 | **condition 字段死代码** | `PipelineStage.condition` 从未被 pipeline_engine 使用 | 要么删除，要么在 pipeline_engine 中实现条件跳转逻辑 |
| P1-5 | **Result 类名过于通用** | `resilience_manager.Result` 容易与其他模块的 Result 冲突 | 重命名为 `AgentResult` 或 `TaskResult` |
| P1-6 | **两套阈值命名不一致** | `QualityConfig.hitl_threshold` vs `DomainQualityConfig.human_gate_threshold` | 统一为同一名称 |

### 3. P2 可选优化

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| P2-1 | **session_id 空字符串默认值** | `BlackboardConfig.session_id: str = ""` | 改为 `session_id: str = field(default_factory=lambda: uuid4().hex[:8])` 或在 `__post_init__` 中验证非空 |
| P2-2 | **QualityConfig 无 frozen** | 所有 dataclass 均可变 | 考虑对纯数据契约类添加 `@dataclass(frozen=True)` 保证不可变性 |
| P2-3 | **PipelineStage 缺少 __repr__** | `PipelineStage` 默认 repr 不够清晰 | 添加自定义 `__repr__` 便于调试 |
| P2-4 | **DomainQualityConfig 权重和仅 warning** | `__post_init__` 中权重和≠1.0 仅 logger.warning | 提升为 ValueError 或在文档中明确说明允许偏离 |
| P2-5 | **ResilienceConfig.fallback_model** | 默认值为 None，实际使用时需要默认降级模型 | 设置合理默认值如 `"lightweight"` 或在 ResilienceManager 中处理 None 情况 |

---

## 附录：数据类全景图

```
┌─────────────────────────────────────────────────────────┐
│                    v3_protocols.py (不存在)               │
│  本应集中定义所有数据契约的协议层文件                       │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   pipeline_engine   quality_gate    resilience_manager
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │ PipelineState│   │ GateDecision│   │ CircuitState│
   │ StageResult │   │ DimensionScore│ │ HealthLevel │
   │ PipelineResult│ │ QualityReport│   │ HealthStatus│
   └─────────────┘   │ DimensionConfig│ │ Task ⚠️     │
                     │ QualityConfig │   │ Result      │
                     └─────────────┘   │ Checkpoint  │
                                       └─────────────┘
                          │
                          ▼
                    config_loader
   ┌─────────────────────────────────┐
   │ AgentConfig                     │
   │ QualityDimension (≠DimensionConfig)│
   │ DomainQualityConfig (≠QualityConfig)│
   │ PipelineStage                   │
   │ DomainConfig                    │
   │ PipelineTemplate                │
   │ DeliveryConfig                  │
   │ ResilienceConfig                │
   └─────────────────────────────────┘
                          │
                          ▼
                  blackboard_manager
   ┌─────────────────────────────────┐
   │ BlackboardConfig                │
   └─────────────────────────────────┘
```

---

*评审完成。建议在创建 `v3_protocols.py` 时先修复所有 P0 问题，确保协议层定义与实际使用一致。*
