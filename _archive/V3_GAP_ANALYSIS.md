# Ship Pro 2.0.0 系统性差距分析

> **日期**: 2026-06-25  
> **分析对象**: 2.0.0 管线输出 vs 8位专家共识理想架构  
> **目的**: 一次性识别所有差距，统一规划修复方案

---

## 一、架构层差距（5 个核心问题）

### GAP-A1: 缺少编排层模块 ❌

**现状**: 2.0.0 输出 9 个模块，缺少 4 个核心模块：
- ❌ MainLoopOrchestrator（主循环编排器）
- ❌ GoalParser（目标解析器）
- ❌ ErrorAnalyzer（错误分析器）
- ❌ PhaseSelector（阶段选择器）

**理想**: 8位专家共识明确要求"必须有编排层"，负责串联所有组件形成完整执行路径。

**影响**: 没有编排层 = 9 个零件没有引擎，无法形成完整 Loop。

**根因**: Architect 只映射了 1/44 需求（REQ-001），其余 43 个需求未映射到组件。编排层相关需求（如 REQ-006 错误分析、REQ-008 Goal 解析）被遗漏。

---

### GAP-A2: 需求覆盖率极低 ❌

**现状**: Architect 只映射了 1/44 需求（2.3%）

**理想**: P0 需求覆盖率 ≥ 80%，P1 ≥ 60%

**影响**: 大量需求（错误分析、Goal 解析、HITL 通知等）未被组件承接。

**根因**: 
- Spec Pro planning 阶段正确提取了 44 个 REQ
- 但 final_result 只传递了 REQ-001 给 Ship Pro
- Architect 只看到 1 个需求，自然只映射 1 个

---

### GAP-A3: 确定性逻辑违反"全 LLM 控制"原则 ⚠️

**现状**: 
- CircuitBreaker 技术栈包含"状态机"、"阈值"
- QualityHarness 技术栈包含"阈值"

**理想**: PRINCIPLE-C-002 要求"全 LLM 控制，Python 仅做执行器"，禁止硬编码规则引擎。

**影响**: 这些模块本质是确定性逻辑，不是 LLM 驱动。

**根因**: 
- 语义检查识别出这个问题，但只给 WARNING（非 BLOCKER）
- Worker 没有被迫修正

---

### GAP-A4: Hermes 对等协作协议未落地 ⚠️

**现状**: Reviewer 指出"Hermes 对等协作协议只在 domain_details 中声明，未传递到任何 WP"

**理想**: PRINCIPLE-C-005 要求"Hermes 是对等协作伙伴，不是子 Agent"，必须有双向通信协议。

**影响**: 如果实现时按 Worker 模式处理 Hermes，违反对等原则。

**根因**: Architect 没有为 Hermes 创建独立 WP，Specifier 也没有为对等通信生成 AC。

---

### GAP-A5: HITL 超时升级机制缺失 ⚠️

**现状**: Reviewer 指出"HITL 超时 24 小时未传递到任何 WP 的 acceptance_criteria"

**理想**: PRINCIPLE-C-010 要求"HITL 超时 24 小时后升级处理"。

**影响**: 如果 Worker 卡住 24 小时，没有自动升级机制。

**根因**: SLA 约束在 Architect 输出中存在，但 Decomposer 没有将其分配到具体 WP。

---

## 二、管线层差距（4 个问题）

### GAP-P1: 原则覆盖映射不完整 ⚠️

**现状**: 只有 3 条原则覆盖映射（缺 PRINCIPLE-C-001）

**理想**: 每条 BLOCKER 原则都应该有 `principle_coverage` 映射。

**影响**: PRINCIPLE-C-001（一步到位）没有被任何组件承接。

**根因**: Architect 生成 principle_coverage 时遗漏了 C-001。

---

### GAP-P2: 模型选择不合理 ⚠️

**现状**: Reviewer 指出"所有 9 个 WP 的 model_tier 均设为 claude-opus，包括基础设施层（WP-001）和低优先级优化组件（WP-007/WP-008）"

**理想**: 应该根据 WP 复杂度和优先级选择合适模型（如 WP-001 用 flash，WP-005 用 opus）。

**影响**: 成本浪费 40-70%（PRINCIPLE-C-002 明确要求成本优化）。

**根因**: Specifier 没有根据 WP 的 complexity 和 priority 调整 model_tier。

---

### GAP-P3: Reviewer 过于宽松 ⚠️

**现状**: Reviewer 给出 4 个 medium issues，但 verdict 仍是 PASS

**理想**: 如果有 medium issue 涉及原则违反（如 Hermes 协议缺失），应该 FAIL 或 PASS_WITH_CONDITIONS。

**影响**: 问题被放过，下游实现时才发现。

**根因**: Reviewer 的 verdict 逻辑过于宽松，medium issue 不影响 verdict。

---

### GAP-P4: 语义检查未覆盖全部阶段 ⚠️

**现状**: 语义检查只在 architect 阶段执行，decomposer/specifier 未触发

**理想**: architect/decomposer/specifier 三个阶段都应该执行语义检查。

**影响**: decomposer 的 WP 粒度、specifier 的原则 AC 质量无法通过语义检查验证。

**根因**: 
- Orchestrator 在 architect 阶段执行语义检查后提前退出
- 后续阶段没有新的 Orchestrator 续跑语义检查流程

---

## 三、代码质量差距（2 个问题）

### GAP-C1: 语义检查 severity 映射过松 ⚠️

**现状**: 语义检查给出 WARNING（如"令牌桶限流"措辞冲突），不触发重试

**理想**: WARNING 也应该触发重试，让 Worker 修正措辞。

**影响**: 措辞歧义被放过，实现时可能真的写成确定性逻辑。

**根因**: `merge_gate_results` 函数只在 severity=BLOCKER 时触发重试。

---

### GAP-C2: Orchestrator 上下文溢出 ⚠️

**现状**: Orchestrator 在 architect 阶段执行语义检查后，后续阶段提前退出

**理想**: Orchestrator 应该完整跑完 5 个阶段。

**影响**: 需要多次 spawn 新 Orchestrator 续跑，增加复杂度。

**根因**: 
- 语义检查的多步流程（semantic-task → 评估 → 写文件 → merge）消耗大量上下文
- Orchestrator prompt 本身较长（包含完整管线流程）

---

## 四、系统性修复方案

### 修复优先级排序

| 优先级 | 修复项 | 影响范围 | 工作量 |
|--------|--------|---------|--------|
| 🔴 P0 | F1: Spec Pro 需求传递修复 | 解决 GAP-A2 | 2-3 小时 |
| 🔴 P0 | F2: Architect prompt 强化 | 解决 GAP-A1, GAP-A3 | 2-3 小时 |
| 🟡 P1 | F3: 语义检查 severity 升级 | 解决 GAP-C1 | 1 小时 |
| 🟡 P1 | F4: Reviewer verdict 收紧 | 解决 GAP-P3 | 1-2 小时 |
| 🟡 P1 | F5: Decomposer/Specifier prompt 强化 | 解决 GAP-A4, GAP-A5, GAP-P2 | 2-3 小时 |
| 🟠 P2 | F6: Orchestrator prompt 压缩 | 解决 GAP-C2 | 2-3 小时 |

**总计**: 10-15 小时

---

### 修复方案详情

#### F1: Spec Pro 需求传递修复（解决 GAP-A2）

**问题**: final_result.json 只传递了 REQ-001，其余 43 个需求丢失。

**修复**: 
1. 修改 `inject_principles.py`，同时注入 `requirements` 字段
2. 从 planning.json 提取 44 个 REQ，注入到 final_result.json
3. 确保 Ship Pro Architect 能看到全部需求

**验证**: Architect 输出中 `requirements` 字段包含 44 个 REQ，P0 覆盖率 ≥ 80%。

---

#### F2: Architect prompt 强化（解决 GAP-A1, GAP-A3）

**问题**: Architect 没有生成 MainLoopOrchestrator 等编排层模块。

**修复**: 
1. 在 Architect prompt 中明确列出 8 位专家共识的 4 个核心模块（GoalParser, PhaseSelector, WorkerAllocator, ErrorAnalyzer）
2. 添加反模式检查清单：
   - ❌ 禁止使用"状态机"、"阈值"等确定性逻辑
   - ✅ 必须使用"LLM API"、"prompt 驱动"
3. 在 gate_architect 中增加检查：如果架构原则包含"全 LLM 控制"，检查模块 tech stack 是否包含确定性关键词

**验证**: Architect 输出包含 MainLoopOrchestrator 模块，CircuitBreaker 的 tech stack 改为"LLM 驱动的错误分析"。

---

#### F3: 语义检查 severity 升级（解决 GAP-C1）

**问题**: WARNING 不触发重试。

**修复**: 
1. 修改 `merge_gate_results` 函数，WARNING 也触发重试（但优先级低于 BLOCKER）
2. 在 Orchestrator prompt 中明确：如果语义检查给出 WARNING，要求 Worker 修正后重新 gate

**验证**: 2.0.0 中 Architect 的"令牌桶限流"措辞被修正为"基于 OpenClaw 的限流配置"。

---

#### F4: Reviewer verdict 收紧（解决 GAP-P3）

**问题**: Reviewer 给出 4 个 medium issues 但 verdict 仍是 PASS。

**修复**: 
1. 修改 Reviewer prompt，明确 verdict 规则：
   - 如果有 medium issue 涉及原则违反 → PASS_WITH_CONDITIONS
   - 如果有 medium issue 涉及核心模块缺失 → FAIL
2. 在 gate_reviewer 中增加检查：如果 issues 中包含"principle"关键词且 severity=medium，强制 verdict=PASS_WITH_CONDITIONS

**验证**: 2.0.0 中 Reviewer 对 Hermes 协议缺失给出 PASS_WITH_CONDITIONS，要求 Specifier 补充。

---

#### F5: Decomposer/Specifier prompt 强化（解决 GAP-A4, GAP-A5, GAP-P2）

**问题**: 
- Hermes 对等协作协议未落地
- HITL 超时升级机制缺失
- 模型选择不合理

**修复**: 
1. Decomposer prompt 增加：
   - 如果 Architect 输出包含 Hermes 相关 domain_details，必须创建独立 WP
   - 如果 Architect 输出包含 SLA 约束（如 hitl_timeout），必须分配到具体 WP
2. Specifier prompt 增加：
   - 根据 WP 的 complexity 和 priority 选择 model_tier：
     - complexity=low 或 priority=P2 → flash
     - complexity=medium 或 priority=P1 → standard
     - complexity=high 或 priority=P0 → opus

**验证**: 2.0.0 中包含 Hermes 通信协议 WP，HITL 超时 AC，WP-001 使用 flash 模型。

---

#### F6: Orchestrator prompt 压缩（解决 GAP-C2）

**问题**: Orchestrator 上下文溢出，提前退出。

**修复**: 
1. 压缩 Orchestrator prompt：
   - 删除冗余说明（如"禁止跳过验证"重复 3 次）
   - 使用更简洁的指令格式
   - 将详细流程放在外部文档，prompt 中只放链接
2. 语义检查结果缓存：避免重复评估相同输出
3. 如果 Orchestrator 提前退出，自动 spawn 新 Orchestrator 续跑（当前已实现）

**验证**: 2.0.0 中单个 Orchestrator 完整跑完 5 个阶段（含语义检查）。

---

## 五、验证计划

### 回归测试清单

修复完成后，重跑 Ship Pro 2.0.0，验证：

| 测试项 | 预期结果 | 验证方法 |
|--------|---------|---------|
| 需求覆盖 | P0 覆盖率 ≥ 80% | 检查 Architect requirements 字段 |
| 编排层模块 | 包含 MainLoopOrchestrator | 检查 Architect modules 字段 |
| 确定性逻辑 | CircuitBreaker 不含"状态机" | 检查 tech stack 关键词 |
| Hermes 协议 | 有独立 WP | 检查 Decomposer work_packages |
| HITL 超时 | 有 AC 覆盖 | 检查 Specifier acceptance_criteria |
| 模型选择 | WP-001 使用 flash | 检查 Specifier model_tier |
| Reviewer verdict | medium issue → PASS_WITH_CONDITIONS | 检查 Reviewer verdict |
| 语义检查覆盖 | architect + decomposer + specifier | 检查 semantic_*.json 文件 |
| Orchestrator 完整性 | 单个 Orchestrator 跑完 5 阶段 | 检查 pipeline_state.json |

### 成功标准

2.0.0 相比 2.0.0 的改进：
- ✅ 模块数从 9 → 10+（含 MainLoopOrchestrator）
- ✅ 需求覆盖率从 2.3% → 80%+
- ✅ 确定性逻辑从 2 个模块 → 0 个
- ✅ Hermes/HITL 有独立 WP
- ✅ 模型选择合理（不全用 opus）
- ✅ Reviewer verdict 收紧
- ✅ 语义检查覆盖 3 个阶段
- ✅ 单个 Orchestrator 跑完全程

---

## 六、实施计划

### 阶段 1: Spec Pro 修复（2-3 小时）
- F1: inject_principles.py 增加 requirements 注入

### 阶段 2: Architect 修复（2-3 小时）
- F2: Architect prompt 强化
- F3: 语义检查 severity 升级

### 阶段 3: Reviewer/Decomposer/Specifier 修复（3-5 小时）
- F4: Reviewer verdict 收紧
- F5: Decomposer/Specifier prompt 强化

### 阶段 4: Orchestrator 优化（2-3 小时）
- F6: Orchestrator prompt 压缩

### 阶段 5: 2.0.0 验证（1 小时）
- 重跑 Ship Pro 2.0.0
- 执行回归测试清单
- 对比 2.0.0 vs 2.0.0 结果

**总计**: 10-15 小时

---

## 七、总结

2.0.0 验证了 AI Native Gate 的可行性（语义检查首次执行），但暴露了 11 个系统性差距。这些差距分为三类：

1. **架构层**（5 个）：缺编排层、需求覆盖低、确定性逻辑、Hermes/HITL 缺失
2. **管线层**（4 个）：原则映射不完整、模型选择不合理、Reviewer 宽松、语义检查覆盖不全
3. **代码质量**（2 个）：severity 映射松、Orchestrator 上下文溢出

通过 6 个修复方案（F1-F6），预计 10-15 小时完成，2.0.0 应该达到理想架构状态。

**核心改进**: 从"试错式优化"转为"系统性修复"，一次性解决所有差距。
