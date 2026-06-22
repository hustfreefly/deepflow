# V6 路径隔离实施计划（契约笼子模式）

> 基于 V6 方案（3/3 专家评审通过）
> 方法论：契约笼子（DECLARE → REVIEW → EXECUTE → VERIFY）
> 自驱动：不完成不停止

---

## 总体 Loop 结构

```
Loop = Phase（每个 Phase 是一个完整契约笼子循环）

Phase 1: Core 基础设施（5 Steps）
  ├─ Step 1: blackboard_manager.py Path.home() fallback 修复
  ├─ Step 2: blackboard_bridge.py Path.home() 修复
  ├─ Step 3: BlackboardManager API 增强（7 个新方法）
  ├─ Step 4: 单元测试
  └─ Step 5: 其他 core Path.home() 清理

Phase 2A: solution_pro Python（5 Steps）
  ├─ Step 6: task_builder.py 去路径化
  ├─ Step 7: orchestrator_agent.py 去路径化
  ├─ Step 8: completion_handler.py 去路径化
  ├─ Step 9: 其他 solution_pro Python
  └─ Step 10: 集成测试（中间验证点）

Phase 2B: solution_pro Prompt（1 Step）
  └─ Step 11: Prompt 模板去路径化

Phase 3: spec_pro（2 Steps）
  ├─ Step 12: coordinator.py 去路径化
  └─ Step 13: 集成测试

Phase 4: ship_pro（3 Steps）
  ├─ Step 14: Python 去路径化
  ├─ Step 15: Prompt 去路径化
  └─ Step 16: 集成测试

Phase 5: research_pro + prompts（3 Steps）
  ├─ Step 17: research_pro Python
  ├─ Step 18: prompts/system 目录
  └─ Step 19: 全域集成测试

Phase 6: CI + 回归（1 Step）
  └─ Step 20: CI 卡点 + 全域回归测试
```

## 契约笼子执行规范

每个 Step 执行 4 个阶段：

### 1. DECLARE（声明契约）
- 明确修改哪些文件
- 明确 API 变更
- 明确验收标准（grep 命令 / pytest 命令）
- 写入 `.deepflow/contracts/step_N_contract.md`

### 2. REVIEW（专家评审）
- spawn 1 位专家评审契约
- 评审通过 → 进入 EXECUTE
- 评审不通过 → 修正契约，重新评审

### 3. EXECUTE（实施）
- 按契约修改代码
- 每个 Step 一个 git commit
- commit message: `fix(path-isolation): Step N - description`

### 4. VERIFY（验证）
- 运行契约中的验收命令
- 全部通过 → 进入下一个 Step
- 不通过 → 修正代码，重新验证

## 进度追踪

| Phase | Step | DECLARE | REVIEW | EXECUTE | VERIFY | 状态 |
|:---|:---|:---|:---|:---|:---|:---|
| 1 | 1 | ✅ | ✅ | 🔄 | ⬜ | 进行中 |
| 1 | 2-5 | ⬜ | ⬜ | ⬜ | ⬜ | 待开始 |
| 2A | 6-10 | ⬜ | ⬜ | ⬜ | ⬜ | 待开始 |
| 2B | 11 | ⬜ | ⬜ | ⬜ | ⬜ | 待开始 |
| 3 | 12-13 | ⬜ | ⬜ | ⬜ | ⬜ | 待开始 |
| 4 | 14-16 | ⬜ | ⬜ | ⬜ | ⬜ | 待开始 |
| 5 | 17-19 | ⬜ | ⬜ | ⬜ | ⬜ | 待开始 |
| 6 | 20 | ⬜ | ⬜ | ⬜ | ⬜ | 待开始 |
