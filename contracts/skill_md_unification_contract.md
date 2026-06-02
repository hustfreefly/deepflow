---
id: contracts/skill_md_unification_contract
version: "1.0.0"
updated: "2026-06-01"
---

# SKILL.md 统一化契约

**创建时间**: 2026-05-31 10:37
**目标**: 统一 Solution Pro 的执行入口，消除 Agent 的困惑

---

## 1. 修复目标

### 1.1 核心问题
- Agent 不知道走哪个入口（run_v3 / run_harness_v2 / run / run_legacy）
- `_resolve_spawn_fn()` 在子 Agent 环境中必然失败
- README.md 和 QUICKSTART.md 描述两种不同的执行方式

### 1.2 修复策略
采用**方案1：SKILL.md 统一入口**（UX专家评分 9/10，产品专家评分 8/10）

### 1.3 成功标准
- [ ] Agent 读取 SKILL.md 后，100% 知道正确的执行方式
- [ ] SKILL.md 包含完整的 `sessions_spawn` 调用模板
- [ ] SKILL.md 包含执行前自检清单
- [ ] SKILL.md 包含执行后验证清单
- [ ] 旧入口（run_v3/run_legacy）标记为 deprecated

---

## 2. 实施步骤

### Step 1: 创建 domains/solution/SKILL.md
**输入**: 
- 现有 QUICKSTART.md 的"方案设计 — 三步启动"部分
- 现有 skills/solution-pro/SKILL.md 的欢迎界面部分
- 评审专家的建议

**输出**:
- domains/solution/SKILL.md（Agent 唯一执行指南）

**验证**:
- [ ] 文件存在且可读
- [ ] 包含"快速启动模板"（可直接复制的 sessions_spawn 代码）
- [ ] 包含"执行前自检"（3项检查）
- [ ] 包含"执行后验证"（检查 blackboard 输出）
- [ ] 包含"禁止使用的旧入口"列表

### Step 2: 统一 _resolve_spawn_fn()
**输入**:
- domains/solution/orchestrator_agent.py 中的 `_resolve_spawn_fn()`
- domains/solution/pipeline_orchestrator.py 中的 `_resolve_spawn_fn()`
- 其他模块中的重复实现

**输出**:
- core/agents/spawn_resolver.py（统一的 spawn_fn 解析逻辑）

**验证**:
- [ ] spawn_resolver.py 存在且可导入
- [ ] 所有模块引用统一的 `resolve_spawn_fn()`
- [ ] 在子 Agent 环境中返回 None（不崩溃）
- [ ] 在主 Agent 环境中返回 sessions_spawn（如果可用）

### Step 3: 废弃旧入口
**输入**:
- SolutionOrchestratorV21.run_v3()
- SolutionOrchestratorV21.run_legacy()
- SolutionOrchestratorV21.run() 静态方法

**输出**:
- 添加 `@deprecated` 装饰器
- 添加 DeprecationWarning
- 添加文档注释指向 SKILL.md

**验证**:
- [ ] run_v3() 调用时打印 deprecation warning
- [ ] run_legacy() 调用时打印 deprecation warning
- [ ] warning 消息指向 domains/solution/SKILL.md
- [ ] 现有测试仍然通过

---

## 3. 验证清单

### 3.1 功能验证
- [ ] Agent 读取 SKILL.md 后可以正确执行 Solution Pro
- [ ] 执行前自检可以检测到 spawn_fn 不可用
- [ ] 执行后验证可以检查 blackboard 输出完整性

### 3.2 兼容性验证
- [ ] 现有 pytest 测试全部通过
- [ ] 现有 blackboard 输出格式不变
- [ ] 现有 prompts 不受影响

### 3.3 文档验证
- [ ] README.md 更新为指向 SKILL.md
- [ ] QUICKSTART.md 更新为指向 SKILL.md
- [ ] CHANGELOG.md 记录此次变更

---

## 4. 风险评估

### 4.1 技术风险
- **风险**: 废弃旧入口可能影响现有脚本
- **缓解**: 只添加 deprecation warning，不删除代码

### 4.2 兼容性风险
- **风险**: 外部系统可能依赖 run_v3()
- **缓解**: 保留 run_v3() 功能，只添加警告

### 4.3 用户体验风险
- **风险**: Agent 可能忽略 SKILL.md
- **缓解**: 在 README.md 顶部添加强指向

---

## 5. 时间估算

- Step 1 (SKILL.md): 15分钟
- Step 2 (spawn_resolver): 20分钟
- Step 3 (deprecated): 10分钟
- 验证: 10分钟
- **总计**: 55分钟

---

## 6. 签字确认

**声明人**: 小满 🦞
**声明时间**: 2026-05-31 10:37
**状态**: 待执行
