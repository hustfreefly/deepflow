# 架构一致性评审报告

> 评审人: 架构一致性评审 Agent (subagent)
> 日期: 2026-04-14
> 评审范围: ADR-001~007 vs v3_protocols.py vs v3_contract_validator.py vs pipeline_engine.py/coordinator.py

---

## 总评

- **一致性评分: 4.5/10**
- **主要优点:**
  - ADR-001 (Score Scale) 已在代码中完全实现，YAML 0-1→0-100 自动转换已生效
  - ADR-005 (HITL) 的默认拒绝策略已在 `_wait_for_hitl()` 中实现
  - ADR-005 的 `continue_pipeline()` 修复已正确实现（调用 `_continue_iterative()` 而非 `engine.run()`）
  - ADR-007 的 PipelineState 枚举在代码中完整定义（10 个状态）
  - ADR-006 的 prompt format 错误处理已在 `run_stage()` 中实现

- **主要缺陷:**
  - **ADR-002/003 的构造注入完全未实现** — PipelineEngine.__init__ 不接受 quality_gate 或 resilience_manager 参数
  - **ADR-004 的 CircuitBreaker 统一未执行** — pipeline_engine.py L34 仍有独立的 CircuitBreaker 类（字符串状态）
  - **v3_protocols.py 缺失 3 个关键 Protocol** — HITLProtocol、PromptTemplateContract、StateMachineProtocol/LifecycleProtocol
  - **v3_contract_validator.py 的 LifecycleState 与 PipelineState 完全不一致** — 两套状态枚举并存
  - **v3_protocols.py 的 QualityGateProtocol.check_convergence threshold 默认值使用 0-1 尺度 (0.92)**，与 ADR-001 的 0-100 尺度矛盾
  - **ADR-007 的状态转换守卫未实现** — 代码中无 `_transition_to()` 或 `validate_state_transition()`

---

## ADR 一致性矩阵

| ADR | 内部一致 | 与代码一致 | 与协议一致 | 可追溯 |
|-----|---------|-----------|-----------|--------|
| ADR-001 | ✅ | ✅ 部分 | ⚠️ 尺度矛盾 | ✅ |
| ADR-002 | ✅ | ❌ 未实现 | ⚠️ Protocol 存在但未用 | ✅ |
| ADR-003 | ✅ | ❌ 未实现 | ⚠️ Protocol 存在但未用 | ✅ |
| ADR-004 | ✅ | ❌ 未执行 | ⚠️ Protocol 存在 | ✅ |
| ADR-005 | ✅ | ✅ 部分 | ❌ Protocol 缺失 | ✅ |
| ADR-006 | ✅ | ✅ 部分 | ❌ Protocol 缺失 | ✅ |
| ADR-007 | ✅ | ✅ 部分 | ❌ Protocol 缺失 | ✅ |

---

## 发现的不一致

### 矛盾决策

| ADR-A | ADR-B | 矛盾点 | 建议 |
|-------|-------|--------|------|
| ADR-002 | ADR-003 | 两者均定义构造注入到 PipelineEngine.__init__，参数签名互相引用但各自独立定义。ADR-002 定义 `quality_gate` 参数，ADR-003 定义 `resilience_manager` 参数，但未明确两者同时注入时的初始化顺序 | 合并 ADR-002 和 ADR-003 为单一的"组件注入"ADR，明确注入顺序和依赖关系 |
| ADR-003 | ADR-004 | ADR-003 说 ResilienceManager 管理 CircuitBreaker，ADR-004 说统一使用 ResilienceManager 的 CircuitBreaker。两者语义重叠，ADR-004 实质是 ADR-003 的子决策 | 将 ADR-004 合并为 ADR-003 的子章节，而非独立 ADR |

### 与代码不一致

| ADR | 决策 | 代码实际 | 差距 |
|-----|------|---------|------|
| ADR-002 §1 | PipelineEngine.__init__ 接受 `quality_gate` 参数 | `__init__(self, config_path, session_id)` — 无 quality_gate 参数 | **未实现**。Coordinator._create_engine() 也未注入 |
| ADR-002 §3 | 收敛检测委托给 QualityGate.check_convergence() | PipelineEngine.check_convergence() 完全自建，无委托逻辑 | **未实现** |
| ADR-002 §4 | run_gated() 中 QualityGate 评估后做门控判断 | run_gated() 中无 QualityGate 评估，仅用 score < hitl_threshold 判断 | **未实现** |
| ADR-003 §1 | PipelineEngine.__init__ 接受 `resilience_manager` 参数 | 同上，无 resilience_manager 参数 | **未实现** |
| ADR-003 §2 | spawn_agent() 使用 ResilienceManager.execute_with_resilience() | spawn_agent() 直接调用 sessions_spawn，无 ResilienceManager 包装 | **未实现** |
| ADR-003 §3 | 移除 pipeline_engine.py 的 CircuitBreaker 类 | L34 仍有 `class CircuitBreaker`，使用字符串状态 ('closed'/'open'/'half_open') | **未执行** |
| ADR-004 §1 | 删除 pipeline_engine.py 的 CircuitBreaker，统一引用 resilience_manager.CircuitBreaker | 仍存在独立 CircuitBreaker 类，未导入 ResilienceManager 的 | **未执行** |
| ADR-004 §2 | 状态模型统一为 CircuitState 枚举 | 仍使用字符串 `self.state = 'closed'`，非枚举 | **未执行** |
| ADR-006 §1 | 每个 stage 声明变量契约，执行前验证 | run_stage() 仅有 try/except KeyError，无显式契约验证 | **部分实现**（有错误处理但无契约声明） |
| ADR-006 §3 | 支持 `{var?}` 可选变量语法 | 未实现 | **未实现** |
| ADR-007 §3 | `_transition_to()` 状态转换守卫 | 无此方法，状态直接赋值 `self.state = PipelineState.XXX` | **未实现** |
| ADR-007 §4 | 状态转换合法性验证（VALID_TRANSITIONS） | 代码中无 VALID_TRANSITIONS 定义 | **未实现** |
| ADR-007 §2 状态转换矩阵 | 定义了 10×9 的转换合法性矩阵 | 代码中无任何转换验证 | **未实现** |

### 与协议不一致

| ADR | 决策 | 协议实际 | 差距 |
|-----|------|---------|------|
| ADR-001 §3 | ScoreProtocol 定义（target_score 范围 [0,100]） | v3_protocols.py 有 ScoreScale 枚举和 normalize_score()，但**无 ScoreProtocol 类** | Protocol 类缺失 |
| ADR-001 §4 | 收敛检测阈值 2.0 分（0-100 尺度） | QualityGateProtocol.check_convergence() 默认 `threshold=0.92`（0-1 尺度） | **尺度矛盾** |
| ADR-002 §3 | QualityEvaluatorProtocol | v3_protocols.py 有 QualityGateProtocol ✅ | 一致（名称略有差异） |
| ADR-003 §4 | ResilienceProtocol | v3_protocols.py 有 ResilienceProtocol ✅ | 基本一致 |
| ADR-005 §4 | HITLProtocol | v3_protocols.py **无任何 HITL 相关 Protocol** | **Protocol 完全缺失** |
| ADR-006 §4 | PromptTemplateContract | v3_protocols.py **无 PromptTemplateContract** | **Protocol 完全缺失** |
| ADR-007 §5 | StateMachineProtocol / LifecycleProtocol | v3_protocols.py **无状态机相关 Protocol** | **Protocol 完全缺失** |
| ADR-005 §5 | HITL 状态流转规范（EXECUTING→HITL_WAITING→EXECUTING/FAILED） | v3_contract_validator.py 的 LifecycleState 定义为 `HITL`（非 `HITL_WAITING`），转移矩阵完全不同 | **状态名和转移矩阵均不一致** |

---

## 深度问题

### P0-1: v3_contract_validator.py 的 LifecycleState 与 PipelineState 完全两套体系

```
PipelineState (pipeline_engine.py):      LifecycleState (v3_contract_validator.py):
  INIT                                     INIT
  PLANNING                                 PLANNING
  EXECUTING                                EXECUTING
  CRITIQUING                            →  CHECKING          ← 名称不同!
  FIXING                                   FIXING
  VERIFYING                                HITL               ← PipelineState 无 HITL
  HITL_WAITING                          →  DELIVERING        ← 名称不同!
  SUMMARIZING                              DONE               ← PipelineState 多 SUMMARIZING
  DONE                                     FAILED
  FAILED
```

**影响**: v3_contract_validator.py 的状态验证器 (`validate_lifecycle_sequence`) 无法正确验证 PipelineEngine 的实际状态转移，因为两套枚举的语义和名称均不匹配。

### P0-2: QualityGateProtocol.check_convergence 的 threshold 默认值使用 0-1 尺度

```python
# v3_protocols.py L140-148
def check_convergence(
    self,
    scores: list[QualityScore],
    iteration: int,
    threshold: float = 0.92,  # ← 0-1 尺度！
    min_iterations: int = 2,
) -> tuple[bool, str]:
```

ADR-001 明确要求统一为 0-100 尺度，默认 target_score=90.0。但 Protocol 接口仍使用 0.92。

### P0-3: 注入型 ADR（002/003）完全停留在文档层面

ADR-002 和 ADR-003 的"决策"部分包含完整的代码示例，但:
- PipelineEngine.__init__ 签名未变更
- Coordinator._create_engine() 未注入任何组件
- v3_protocols.py 中的 ProtocolInjector 类存在但从未被调用

这意味着 ADR-002/003 是**设计意图**而非**已实施决策**。

### P0-4: ADR-007 的状态转换矩阵是纸面规范

ADR-007 §2 定义了 10×9 的状态转换合法性矩阵和 `_transition_to()` 守卫，但:
- PipelineEngine 中状态赋值全部为直接 `self.state = PipelineState.XXX`
- 无任何转换验证逻辑
- 非法状态转换不会报错

---

## 可追溯性评估

| ADR | 追溯到审计问题 | 验证方法可执行 | 隐式决策 |
|-----|-------------|-------------|---------|
| ADR-001 | ✅ [P0-2], [P1-2] | ✅ 验证方法具体（4 个测试用例） | 无 |
| ADR-002 | ✅ [P1-4], [P1-6] | ⚠️ 验证方法存在但代码未实现 | 注入时机由 Coordinator 决定（隐式） |
| ADR-003 | ✅ [P1-5] | ⚠️ 验证方法存在但代码未实现 | Task↔StageResult TypeAdapter 需要但未详述 |
| ADR-004 | ✅ [P1-5], [P1-2] | ✅ 验证方法具体（6 个检查项） | 回退路径维护成本未量化 |
| ADR-005 | ✅ [P1-1], [P0-3] | ✅ 验证方法具体（6 个测试用例） | 生产环境 HITL 集成方式未定义 |
| ADR-006 | ⚠️ [P1-5] 引用模糊 | ⚠️ 验证方法存在但 `{var?}` 语法未实现 | 契约声明与 YAML 配置的优先级未明确 |
| ADR-007 | ✅ [P0-2], [P0-3] | ⚠️ 验证方法存在但守卫未实现 | VERIFYING 状态"已定义但未使用"无迁移计划 |

---

## 改进建议

### 1. P0 必须修复

1. **统一尺度声明**: 修复 v3_protocols.py 中 `QualityGateProtocol.check_convergence` 的 `threshold` 默认值从 `0.92` 改为 `92.0`，确保与 ADR-001 的 0-100 尺度一致
2. **实现注入型 ADR 的代码**: 修改 `PipelineEngine.__init__` 签名，添加 `quality_gate` 和 `resilience_manager` 可选参数；修改 `Coordinator._create_engine()` 执行实际注入
3. **统一状态枚举**: 将 v3_contract_validator.py 的 `LifecycleState` 与 pipeline_engine.py 的 `PipelineState` 统一为同一枚举，或至少建立明确的映射关系。当前两套体系会导致状态验证器无法正确工作
4. **补充缺失的 Protocol 定义**: 在 v3_protocols.py 中添加:
   - `HITLProtocol`（对应 ADR-005 §4）
   - `PromptTemplateContract`（对应 ADR-006 §4）
   - `StateMachineProtocol`（对应 ADR-007 §5）

### 2. P1 建议修复

5. **执行 ADR-004 CircuitBreaker 统一**: 删除 pipeline_engine.py L34 的 `class CircuitBreaker`，改为从 resilience_manager 导入；统一状态模型为 CircuitState 枚举
6. **实现 ADR-007 状态转换守卫**: 添加 `_transition_to()` 方法和 `VALID_TRANSITIONS` 字典，在所有状态赋值处使用守卫
7. **合并重叠 ADR**: ADR-002 + ADR-003 可合并为 "组件注入规范"，ADR-004 作为 ADR-003 的子章节
8. **实现 ADR-006 的契约验证**: 在 `run_stage()` 中添加 `_extract_template_variables()` 方法和契约验证逻辑

### 3. P2 可选优化

9. **ADR-007 中 VERIFYING 状态明确用途或移除**: 当前 PipelineState 定义了 VERIFYING 但代码中从未使用，ADR 中也未说明其用途。建议要么明确用途并实现，要么从枚举中移除
10. **ADR 文档增加"实施状态"字段**: 每个 ADR 增加 `Status: 已实现/部分实现/未实现` 标记，避免文档与实际代码脱节
11. **v3_contract_validator.py 的 REQUIRED_PROMPT_VARS 与 ADR-006 契约对齐**: 当前 validator 要求 7 个必需变量（session_id/domain/pipeline/stage/role/context/task），但 ADR-006 的契约定义中各 stage 的变量集合不同。应对齐或明确 validator 是独立于 ADR 的检查

---

## 总结

7 个 ADR 的**内部逻辑一致性良好**，没有发现直接的矛盾决策。但**与代码和协议的差距较大**：

- **与代码一致率: ~35%**（7 个 ADR 中，仅 ADR-001 和 ADR-005 的部分决策已实现）
- **与协议一致率: ~45%**（v3_protocols.py 覆盖了 ADR-002/003 的 Protocol 定义，但缺失 ADR-005/006/007 的 Protocol）
- **核心问题**: ADR-002/003/004/007 的决策仍停留在文档层面，未反映到代码中；v3_contract_validator.py 的状态体系与实际代码脱节

**建议优先修复 P0 项**（特别是尺度统一和注入实现），再逐步推进 P1 项的代码实现，最后在 ADR 文档中增加实施状态标记，确保文档与代码持续同步。
