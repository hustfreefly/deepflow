# Solution Pro V2 重构方案：LLM 调用全走 OpenClaw

> **版本**: V1.0 | **日期**: 2026-06-29
> **作者**: 小满（主 Agent）
> **状态**: 待评审

---

## 0. 任务澄清

### 做什么
将 Solution Pro V2 中所有"绕过 OpenClaw 直调 LLM API"的代码，统一重构为走 `spawn_fn`（→ `sessions_spawn`），实现**零额外 API Key**。

### 约束是什么
1. **平台约束**：OpenClaw 的 `exec` 环境是独立 Python 进程，无法 import openclaw SDK → 所有 LLM 调用必须通过 `spawn_fn`（由主 Agent 注入）
2. **V1 教训**：V1 的 `sessions_spawn` 模式是正确的，V2 不应该抛弃它
3. **不能破坏现有正确代码**：V2 核心编排（planning/research/review_qc orchestrator）已经正确使用 `spawn_fn`，不能改坏
4. **向后兼容**：测试时 `spawn_fn=None` 的 fallback 模式需保留

### 成功标准
- ✅ 代码中没有任何 `api_key`、`openai`、`litellm` 直接调用
- ✅ 所有 LLM 评估通过 `spawn_fn` → `sessions_spawn` 完成
- ✅ E2E 测试能在 OpenClaw 环境中跑通（不再需要 spawn bridge 文件系统中转）
- ✅ `spawn_fn=None` 时仍能 fallback 到规则判定（测试模式）

---

## 1. 现状诊断

### 1.1 架构概览

```
V2 Solution Pro 的 LLM 调用路径：

✅ 正确路径（已实现，大部分模块）：
   ModuleOrchestrator._adapted_spawn()
     → spawn_fn (注入的 sessions_spawn)
       → OpenClaw 子 Agent
         → LLM（OpenClaw 内部路由）

❌ 问题路径 1：Spawn Bridge（e2e_test_runner.py）
   Python exec → 写文件到 requests/ → 期望另一个 Agent 轮询 → 写回 outputs/
   = 文件中转，不是真正的 sessions_spawn

❌ 问题路径 2：llm_judge_fn 回调（compliance_checker.py, harness_scorer.py）
   Python 函数 → llm_judge_fn(prompt) → ???
   = 取决于注入者，可能是直调 API
```

### 1.2 问题模块清单

| # | 文件 | 问题 | 严重度 | 影响 |
|---|------|------|--------|------|
| P1 | `e2e_test_runner.py` | Spawn Bridge（文件中转） | P0 | E2E 测试无法在真实环境跑通 |
| P2 | `compliance_checker.py` | `llm_judge_fn` 回调可能被注入直调 API 的函数 | P1 | 合规检查可能绕过 OpenClaw |
| P3 | `harness_scorer.py` | 同上 | P1 | Harness 评分可能绕过 OpenClaw |
| P4 | `planner.py` | V1 legacy，已废弃但未清理 | P2 | 代码噪音 |
| P5 | `ai_native_auditor.py` | `llm_judge_fn` 同类问题 | P1 | 审计可能绕过 OpenClaw |

### 1.3 正确模块（不动）

| 文件 | 状态 | 说明 |
|------|------|------|
| `module_orchestrator_base.py` | ✅ | `_adapted_spawn()` 是正确的 spawn_fn 封装 |
| `planning_orchestrator.py` | ✅ | 正确使用 `_adapted_spawn()` |
| `research_orchestrator.py` | ✅ | 正确使用 `_adapted_spawn()` |
| `review_qc_orchestrator.py` | ✅ | 正确使用 `_adapted_spawn()` |
| `fix_loop_state_machine.py` | ✅ | 正确使用 `spawn_fn` |
| `convergence_layer.py` | ✅ | 正确使用 `spawn_fn` |
| `master_orchestrator.py` | ✅ | 正确传递 `spawn_fn` 给所有子模块 |

---

## 2. 重构方案

### 2.1 P1: 重写 e2e_test_runner.py

**问题**：当前用文件系统中转（Spawn Bridge）模拟 `sessions_spawn`，但生产环境中没有 Agent 轮询 `requests/` 目录。

**方案 A：真 OpenClaw 子 Agent 模式（推荐）**
```
主 Agent（我）→ sessions_spawn Orchestrator → Orchestrator 自己用 spawn_fn 创建 Workers
```
- 删掉 Spawn Bridge 代码
- e2e_test_runner 改为一个"任务模板"，主 Agent 读取后用 sessions_spawn 创建 Orchestrator
- Orchestrator（子 Agent）自己负责调度 Planning → Research → ReviewQC

**方案 B：同步测试模式（仅用于 CI/快速验证）**
```
spawn_fn = mock_spawn_fn  → 返回预设数据或调用 LLM（通过 OpenClaw 路由）
```
- 保留 `llm_recorder.py` 的 `mock_spawn_fn` 模式
- 用于无 OpenClaw 环境的单元测试

**选择**：方案 A（生产） + 方案 B（测试），两者共存。

### 2.2 P2/P3/P5: llm_judge_fn 统一为 spawn_fn

**问题**：`compliance_checker.py`、`harness_scorer.py`、`ai_native_auditor.py` 接受 `llm_judge_fn` 回调，但注入来源不确定——可能是直调 API 的函数。

**方案**：
1. **统一接口**：将 `llm_judge_fn` 改为 `spawn_fn`，使用 `_adapted_spawn()` 模式
2. **内部适配**：创建一个 `LLMJudgeAdapter` 类，将 `spawn_fn` 包装成 `llm_judge_fn` 接口
   ```python
   class LLMJudgeAdapter:
       def __init__(self, spawn_fn):
           self.spawn_fn = spawn_fn
       
       def judge(self, prompt: str, temperature: float = 0.2) -> dict:
           result = self.spawn_fn(
               task=prompt,
               mode="run",
               label="llm_judge",
               timeout=60,
           )
           return result.get("output", {})
   ```
3. **注入点**：在 `master_orchestrator.py` 或各模块初始化时，注入 `LLMJudgeAdapter(spawn_fn)`

**好处**：
- 接口向后兼容（`llm_judge_fn` 仍然存在）
- 实现统一走 `spawn_fn` → `sessions_spawn`
- 测试时可注入 mock adapter

### 2.3 P4: 清理 V1 Legacy 代码

**方案**：
- `planner.py` 标记为 `V1-LEGACY`（已有注释），移到 `v1_legacy/` 目录
- 不删除（V1 session 可能需要续跑）

### 2.4 增强：spawn_fn 契约验证

**问题**：当前 `spawn_fn` 是 duck-typed callable，没有类型约束。

**方案**：添加 Pydantic 验证
```python
class SpawnResult(BaseModel):
    status: Literal["COMPLETE", "FAILED", "TIMEOUT"]
    output: Optional[dict] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
```

---

## 3. 执行计划

| Phase | 内容 | 预计工作量 | 风险 |
|-------|------|-----------|------|
| Phase 1 | 创建 `LLMJudgeAdapter` 类 | 30min | 低 |
| Phase 2 | 重构 `compliance_checker.py`、`harness_scorer.py`、`ai_native_auditor.py` | 1h | 中 |
| Phase 3 | 重写 `e2e_test_runner.py`（Spawn Bridge → 真 sessions_spawn） | 1h | 中 |
| Phase 4 | 移动 V1 legacy 代码 | 15min | 低 |
| Phase 5 | 添加 `SpawnResult` Pydantic 验证 | 30min | 低 |
| Phase 6 | E2E 验证（真实 OpenClaw 环境跑通） | 1h | 高 |

**总预计**：4-5 小时

---

## 4. 与 V1 的对比

| 维度 | V1 | V2（现状） | V2（重构后） |
|------|-----|-----------|------------|
| LLM 调用方式 | sessions_spawn | 混合（spawn_fn + 直调 + Spawn Bridge） | 统一 spawn_fn → sessions_spawn |
| 额外 API Key | 不需要 | 可能需要 | 不需要 |
| 编排模式 | Orchestrator → Workers | MasterOrchestrator → Module Orchestrators → Workers | 同左（不改） |
| 测试模式 | mock spawn_fn | mock spawn_fn + Spawn Bridge | mock spawn_fn（统一） |
| 合规检查 | 规则判定 | llm_judge_fn（来源不确定） | LLMJudgeAdapter → spawn_fn |
| E2E 测试 | 可跑通 | 无法跑通（Spawn Bridge 问题） | 可跑通 |

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `LLMJudgeAdapter` 引入额外 spawn 开销 | 批量评估（一次 spawn 评估多个维度） |
| 重写 e2e_test_runner 可能引入新 bug | 保留旧版本为 `e2e_test_runner_v1.py`，新版本渐进替换 |
| `spawn_fn=None` fallback 被破坏 | 每个模块保留 fallback 规则判定，不强依赖 LLM |

---

## 6. 待讨论

1. **是否需要统一所有 `llm_judge_fn` 为 `spawn_fn`？** 还是只确保注入来源正确？
2. **e2e_test_runner 的方案选择**：真子 Agent 模式 vs 同步测试模式 vs 两者共存？
3. **Phase 优先级**：先修 P1（e2e_test_runner）还是先修 P2/P3/P5（llm_judge_fn）？
