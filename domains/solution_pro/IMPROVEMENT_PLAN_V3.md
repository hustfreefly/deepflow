# Solution Pro V3 改进计划

> **基于**: E2E V3 质量评估 (2026-07-01)  
> **评分**: 方案 7.0/10 | 过程 6.8/10 | Verdict: CONDITIONAL_PASS  
> **原则**: 出了问题不是改 bug，是检查已有方案有没有落地。patch < deploy

---

## 发现 → 修复 映射表

| E2E 发现 | 系统性缺陷 | 修复 | 状态 | 影响文件 |
|---------|-----------|------|------|---------|
| 56% Expert 零引用 | S1: 研究→方案信息断裂 | Fix 1: 研究利用追踪器 | ✅ 已实施 | `information_conservation.py` |
| Orchestrator 3 次失败 | S2: LLM 做流程控制 | Fix 2: Python-only 控制器 | 📋 已设计 | `master_orchestrator.py` |
| 31/31 自验证 = 运动员裁判 | S3: 验证非独立 | Fix 3: 独立 Verification Module | 📋 已设计 | 新增 `verification_module.py` |
| Devil Advocate 3/10 被忽略 | S4: 发现追踪缺失 | Fix 4: Finding Ledger | ✅ 已实施 | `review_qc_orchestrator.py` |
| LLM-as-Judge TPR 30-40% | S5: 过度依赖 LLM 判断 | Fix 5: 确定性检查层增强 | ✅ 已实施 | 新增 `deterministic_checks.py` |
| 验证证据章节号不匹配 | S6: 追溯性瑕疵 | Fix 6: 章节号一致性检查 | ✅ 包含在 Fix 5 | `deterministic_checks.py` |
| SHOULD 约束无验证 | S7: 验证范围不足 | Fix 7: P1 验证扩展 | 📋 已设计 | `verification_module.py` |

---

## Fix 1: 研究利用追踪器 ✅

**问题**: 9 个 Research Expert 中 5 个零引用，360KB 研究产出仅 1 处引用标记。  
**根因**: `information_conservation.py` 只检查 REQ ID 和 Constraint ID 的传播，不检查 Expert Finding 利用率。  
**修复**:

```python
# 新增 _check_research_utilization() 方法
# 检查维度: expert_id 或 finding 关键词是否出现在下游方案中
# 权重: 研究利用率占总分 20%（原: 需求 40% + 约束 40% + 追溯 20%）
#       改后: 需求 35% + 约束 30% + 追溯 15% + 研究利用 20%
# 阈值: L2 research_utilization_min = 0.6, L3 = 0.5
# 安全底线: 研究利用率 < 0.3 → 降级为 WARNING
```

**文件**: `information_conservation.py`  
**验证**: 下次 E2E 时 `validate()` 会输出 `research_utilization` + `uncited_experts` 字段

---

## Fix 2: Python-only 控制器 📋

**问题**: 11K 字符 prompt 导致 LLM 不执行，多步 spawn 链断裂。  
**根因**: Module 级 orchestrator 仍是 LLM Agent，不是 Python 控制器。  
**修复设计**:

```
当前: MasterOrchestrator (Python) → ModuleOrchestrator (LLM Agent) → Worker (LLM)
改后: MasterOrchestrator (Python) → Worker (LLM，简洁指令 + 自读文件)
```

**关键变更**:
- 删除中间 LLM Orchestrator 层
- Worker Agent 用简洁指令（<200 字）+ "读取文件 X 并执行"
- 所有流程控制（超时、降级、状态管理）由 Python MasterOrchestrator 处理
- spawn prompt 大小限制: ≤ 500 字

**实施条件**: 需要重构 `planning_orchestrator.py` 和 `research_orchestrator.py` 的 spawn 链

---

## Fix 3: 独立 Verification Module 📋

**问题**: 31/31 PASS 是方案自己验证自己。  
**根因**: ReviewQC 内部的 verification 是对自己产出的检查。  
**修复设计**:

```
当前: ReviewQC → [内部 verification] → 自报 PASS
改后: ReviewQC → 产出方案 → MasterOrchestrator spawn [独立 Verification Module] → 不同模型验证
```

**关键设计**:
- Verification Module 由 MasterOrchestrator 直接 spawn（不经过 ReviewQC）
- 使用不同模型（cross-model validation）
- Verification Agent 不读取 ReviewQC 的 verification_result
- 只看 frozen_spec + solution_document，独立验证
- 扩展验证范围: 31 MUST + 58 SHOULD = 全部 89 约束

**新增文件**: `verification_module.py`

---

## Fix 4: Finding Ledger ✅

**问题**: Devil Advocate 10 个 finding 中 3 个被完全忽略（复杂度过高、Zone 0 边界、阈值无来源）。  
**根因**: Fix Loop 没有强制要求对每个 finding 做显式决策。  
**修复**:

```python
# _run_fix_loop() 增加 finding_ledger 产出
# _build_finding_ledger() 从 research_output 提取所有外部 finding
# _update_ledger_after_fix() 修复后更新 decision 状态
# _detect_unaddressed_findings() 检测未处理的 finding
# 
# 每个 finding 必须有:
# - decision: adopted / rejected / partial
# - rationale: 决策理由（LLM 生成，代码强制存在）
# 
# 即使 ABORT 也保留 ledger（部分修复也有记录）
```

**文件**: `review_qc_orchestrator.py`

---

## Fix 5: 确定性检查层增强 ✅

**问题**: LLM-as-Judge TPR 仅 30-40%，四层 QA 体系被 Judge 可靠性锁定。  
**修复**: 新增 `deterministic_checks.py`，提供 6 个零 LLM 调用的确定性检查。  
**文件**: 新增 `deterministic_checks.py`

---

## 改进前后对比

| 维度 | 改进前 | 改进后 | 预期提升 |
|------|--------|--------|---------|
| 研究利用率 | 无检查（56% Expert 零引用） | 强制检查 + 20% 权重 | 56% → ≥80% |
| 发现追踪 | 无追踪（3/10 被忽略） | Finding Ledger 强制决策 | 忽略率 30% → 0% |
| 确定性检查 | 仅文件存在性 | 6 个零 LLM 检查 | LLM 调用减少 30% |
| 验证独立性 | 自验证（运动员=裁判） | 独立 Module + 不同模型 | 可信度提升 |
| Orchestrator | LLM Agent（大 prompt 不执行） | Python-only 控制器 | 失败率降低 |

---

## 下一步

### 立即可做（本次 session）
- [x] Fix 1: 研究利用追踪器 → `information_conservation.py`
- [x] Fix 4: Finding Ledger → `review_qc_orchestrator.py`
- [x] Fix 5: 确定性检查层 → `deterministic_checks.py`

### 需要讨论（架构变更）
- [ ] Fix 2: Python-only 控制器 — 需要重构 spawn 链
- [ ] Fix 3: 独立 Verification Module — 需要新增 Module + 修改 MasterOrchestrator
- [ ] Fix 7: P1 验证扩展 — 依赖 Fix 3

### 验证
- [ ] 跑单元测试验证 Fix 1/4/5 不破坏现有功能
- [ ] 下次 E2E 时检查 `research_utilization` 和 `finding_ledger` 输出

---

*Created: 2026-07-01 | Based on E2E V3 quality assessment*
