# 通用模块必要性评审

> **评审对象**: QualityGate / ModuleOrchestrator / InformationConservationTracker  
> **评审目标**: 判断是否有必要单独开发为通用模块

---

## 一、当前实现现状

### 1.1 QualityGate（质量门控）

**Solution Pro**:
- `post_validator.py` (9.3KB) — L0 下限守卫
- 检查项：Schema 验证、需求覆盖率、信息守恒
- 调用时机：Agent 完成后

**Ship Pro**:
- 4 个 Gate（分散在多个文件）：
  - `PlannerGate.check()` — L1 Schema 验证
  - `WorkerGate.check()` — L1+L2（LLM Judge）
  - `InformationConservationGate.check()` — L1 需求追踪
  - `CompletenessGate.check()` — L1+L2 端到端覆盖

**Deliver Pro**:
- `smart_assembler.py` — MANIFEST 验证 + AC 覆盖
- `contracts/delivery_manifest.py` — semantic_anchors 字段

**痛点**:
- ❌ 三域 Gate 实现分散，标准不统一
- ❌ 每个域都要重复实现 L1+L2 验证逻辑
- ❌ 没有统一的 Gate API，调用方式不一致

---

### 1.2 ModuleOrchestrator（模块编排）

**Solution Pro**:
- `orchestrator.md` — Agent Orchestrator（薄层调度器）
- 模式：spawn → wait_for → validate → 下一个模块
- 3 个模块顺序执行：Planning → Research → Summary

**Ship Pro**:
- `orchestrator.py` — Python Orchestrator
- 模式：tick() → analyze → spawn_workers → validate → package
- 多 Worker 并行执行

**Deliver Pro**:
- `batch_driver.py` + `orchestrator.py`
- 模式：tick() 双层去重 + DELIVERED 状态管理
- 多阶段流水线

**痛点**:
- ❌ 三域编排模式不统一（Agent vs Python vs 混合）
- ❌ 每个域都要重复实现 spawn → wait → validate 逻辑
- ❌ 没有统一的 Orchestrator 基类或 API

---

### 1.3 InformationConservationTracker（信息守恒追踪）

**Solution Pro**:
- `information_conservation.py` (21KB) — 信息守恒验证器
- 功能：验证端到端信息不丢失
- 检查：semantic_anchors 保留、covered_req_ids 追踪

**Ship Pro**:
- `conservation_judge.py` — LLM Judge 验证信息守恒
- 功能：语义层面检查信息是否丢失

**Deliver Pro**:
- `execution_plan.py` — timeout_seconds 字段
- `state_manager.py` — 备份机制
- 功能：V10 N6 守恒 Gate（semantic_anchors + covered_req_ids + 0.8 阈值）

**痛点**:
- ❌ 信息守恒是 P2 优先级原则（"调试时信息守恒优先于一切"）
- ❌ 三域验证分散，没有统一追踪
- ❌ 信息流断裂是常见故障根因（Spec Pro → Solution Pro → Ship Pro → Deliver Pro）

---

## 二、历史故障关联

### 2.1 V34-V40 故障（Solution Pro）

| 故障 | 根因 | 相关模块 |
|------|------|---------|
| V34/V35 | task 参数截断（28KB prompt 塞进 sessions_spawn） | PromptUtils ✅ 已解决 |
| V36 | spawn-yield 不可靠（wake 事件丢失） | ProcessManager ✅ 已解决 |
| V37 | planning_convergence.json 未生成 | ModuleOrchestrator ❓ |
| V38 | 文件判别标准不对齐（Orchestrator 提前结束） | QualityGate ❓ |
| V39 | JSON 损坏（写入中断） | PromptUtils ✅ 已解决 |
| V40 | planning_module_prompt.md not found | ModuleOrchestrator ❓ |

### 2.2 Deliver Pro 故障

| 故障 | 根因 | 相关模块 |
|------|------|---------|
| Worker MANIFEST 写错路径 | 路径不一致 | QualityGate ❓ |
| MANIFEST 缺失/损坏 | 无验证 | QualityGate ❓ |
| AC<80% auto FAIL | 无覆盖率检查 | QualityGate ❓ |
| 信息流断裂 | Spec Pro 没输出交付件规格 | InformationConservationTracker ❓ |

### 2.3 跨域故障

| 故障 | 根因 | 相关模块 |
|------|------|---------|
| Planning→Research 断裂 | checkpoint 断点续跑失败 | ModuleOrchestrator ❓ |
| 需求追踪丢失 | 没有端到端追踪 | InformationConservationTracker ❓ |

---

## 三、必要性初步判断

| 模块 | 痛点真实性 | 复用价值 | 过度设计风险 | 初步判断 |
|------|-----------|---------|-------------|---------|
| **QualityGate** | ✅ 高（三域都有 Gate） | ✅ 高（统一标准） | ⚠️ 中（可能过度抽象） | ⚠️ 有条件必要 |
| **ModuleOrchestrator** | ✅ 高（三域编排模式不同） | ⚠️ 中（模式差异大） | 🔴 高（ProcessManager 教训） | ❌ 可能不必要 |
| **InformationConservationTracker** | ✅ 高（P2 原则） | ✅ 高（跨域追踪） | ⚠️ 中（可能复杂） | ⚠️ 有条件必要 |

---

## 四、待专家评审问题

1. **QualityGate**: 
   - 三域 Gate 能否统一为一个 API？
   - 还是应该保持域特异性，只提取公共模式？

2. **ModuleOrchestrator**:
   - 三域编排模式差异太大（Agent vs Python vs 混合），能否统一？
   - 还是应该让各域保持独立，只提取公共函数（如 `spawn_and_wait`）？

3. **InformationConservationTracker**:
   - 信息守恒验证能否跨域统一？
   - 还是应该每个域独立实现，只提供公共接口？

4. **过度设计风险**:
   - 这三个模块是否会重蹈 ProcessManager 覆辙（340 行代码，过度抽象）？
   - 有没有更简单的方案（如：只提取公共函数，不做类封装）？

---

**下一步**: 召唤专家评审
