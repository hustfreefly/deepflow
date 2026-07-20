# Deliver Pro 薄层 Orchestrator 改造方案

> **日期**: 2026-07-19
> **作者**: Solution Pro 架构专家
> **状态**: 设计提案
> **约束**: 不加大 Module Agent 层，不删 Orchestrator Agent，基于现有代码

---

## 方案概述（3-5 句）

借鉴 Solution Pro V3.1 的"薄层调度器"模式，将 Deliver Pro Orchestrator prompt 从 589 行/12+ exec 代码块精简为 ~80 行的纯调度指令。核心改动：**让 Orchestrator 调 `DeliverProDriver` 的 step 方法，而不是自己写 inline Python 构造对象**。Driver 已有 step1-step7 方法（213 tests pass），只需在 prompt 中暴露为简单 exec 调用。Orchestrator 的职责退化为：exec 调 Driver → spawn → yield → exec 验证 → 下一步。

---

## 问题诊断

### 当前 Deliver Pro Orchestrator 的 7 个 BLOCKER

| # | BLOCKER | 根因 |
|---|---------|------|
| 1 | LLM 必须写 `import sys; sys.path.insert(0, ...)` | prompt 包含完整 import 模板 |
| 2 | LLM 必须构造 `WorkPackage.model_validate(json.load(...))` | 每步都重新构造 wp + orch |
| 3 | LLM 必须管理 `orch` 对象状态 | 跨步骤引用 Python 对象（不可能） |
| 4 | LLM 必须拼接复杂 f-string | exec 代码块含嵌套引号/花括号 |
| 5 | LLM 必须判断 next_wave 逻辑 | 业务逻辑泄漏到 prompt |
| 6 | LLM 必须构造 ValidationVerdict 对象 | Phase 5 需要 Pydantic 构造 |
| 7 | 每步 exec 15-20 行代码 | token 浪费 + 出错概率高 |

### 根因

**Driver 已存在但未被使用**。`DeliverProDriver` 封装了所有 7 个 step，每个 step 是 1 个方法调用。但 Orchestrator prompt 完全忽略它，选择每步重新构造对象。

---

## 具体修改清单

| 文件 | 修改内容 | 行数变化 |
|------|---------|---------|
| `domains/deliver_pro/__init__.py` | 重写 `_build_orchestrator_prompt()` — 用 Driver 调用替代 12+ exec 代码块 | 589→~80 行（-509 行） |
| `domains/deliver_pro/driver.py` | 新增 `driver_init_script()` 静态方法 — 生成初始化 exec 脚本 | +20 行 |
| `domains/deliver_pro/driver.py` | 新增 `step_check(phase)` 统一验证方法 — 返回简单 dict | +30 行 |
| 无需改动 | `orchestrator.py` — 不动 | 0 |
| 无需改动 | `contracts/` — 不动 | 0 |
| 无需改动 | tests — 现有 213 tests 不受影响 | 0 |

---

## Orchestrator Prompt 精简后的结构（~80 行）

```markdown
你是 Deliver Pro Orchestrator — 薄层调度器。

## 你的职责
按顺序执行 5 个 Phase。每个 Phase = exec 调 Driver → spawn → yield → exec 验证。
你不写业务逻辑。你只调 Driver 方法和检查输出。

## 环境
- DeepFlow root: `{deepflow_root}`
- WP ID: `{wp_id}`
- 项目: `{project_name}`

## 🔴 铁律
1. spawn 后必须 sessions_yield()
2. yield 唤醒后第一个 action 必须是 exec 验证
3. 不写 import/构造对象 — 调 Driver
4. 重复完成事件 → 忽略，继续当前步骤

## 执行算法

### Step 0: 初始化 Driver
exec（所有后续 exec 都用这个 preamble）:
```
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from domains.deliver_pro.driver import DeliverProDriver
d = DeliverProDriver('{wp_id}', '{project_name}')
# 你的操作
import json; print(json.dumps(RESULT))
"
```
验证: 输出含 `Driver init` → 继续

### Step 1: Phase 1 — Analyze
1. exec: `import json; print(json.dumps(d.step1_analyze()))`
2. sessions_spawn(**返回的 params)
3. sessions_yield()
4. 唤醒后 exec: `ok, info = d.step2_check_analyze(); print(ok, info)`
5. ok=True → 继续 Step 2 | ok=False → 报告错误

### Step 2: Phase 2 — Workers
1. exec: `import json; print(json.dumps(d.step3_workers()))`
2. 对每个 params → sessions_spawn(**params)
3. sessions_yield()
4. 唤醒后 exec: `done, info = d.step4_check_workers(); print(done, json.dumps(info))`
5. done=True → 继续 Step 3
6. done=False + next_wave>0 → 回到步骤 1（spawn 下一波）
7. done=False + stuck=True → 报告错误

### Step 3: Phase 3 — Assembly（exec 直接执行，不 spawn）
1. exec: `import json; print(json.dumps(d.step5_integrate()))`
2. 检查 status ≠ "ASSEMBLY_ERROR" → 继续 Step 4

### Step 4: Phase 4 — Validate（最多 5 轮）
round = 1
while round <= 5:
  1. exec: `import json; print(json.dumps(d.step6_validate(round)))`
  2. sessions_spawn(**params) → sessions_yield()
  3. 唤醒后 exec: `verdict, info = d.step6_check_validate(); print(verdict, info)`
  4. PASS → 跳出循环 → 继续 Step 5
  5. FIX → round += 1 → 继续循环
  6. STOP → 跳出循环 → 继续 Step 5

### Step 5: Phase 5 — Package
1. exec: `import json; print(json.dumps(d.step7_package()))`
2. sessions_spawn(**params) → sessions_yield()
3. 唤醒后 exec: `ok, info = d.step7_check_package(); print(ok, info)`
4. ok=True → 流水线完成

## 完成条件
- Phase 1-5 全部执行
- final_deliverable 非空
```

---

## 关键设计决策

### 1. 为什么不加 Module Agent 层？

约束要求不加。Solution Pro 的 Module Agent 解决的是"模块内部有复杂多 Worker 编排"的问题。Deliver Pro 的 Phase 2 Workers 已经是直接 spawn Worker，不需要中间层。

### 2. 为什么 Driver 方法够用？

`DeliverProDriver` 已经封装了所有状态管理：
- `step1_analyze()` → 内部调 `orch.prepare_analyze_spawn()`
- `step4_check_workers()` → 内部处理 stuck detection、next_wave、failed tasks
- `step7_package()` → 内部读 validation_result.json，构造 ValidationVerdict

Orchestrator 不需要知道这些细节。

### 3. exec preamble 模式

所有 exec 共享同一个 preamble（3 行）：
```python
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from domains.deliver_pro.driver import DeliverProDriver
d = DeliverProDriver('{wp_id}', '{project_name}')
```

对比当前每步 5-8 行 import + 构造。Driver `__init__` 是幂等的（读 wp.json + 创建 orch），多次调用无副作用。

### 4. 与 Solution Pro 的对比

| 维度 | Solution Pro | Deliver Pro（改造后） |
|------|-------------|---------------------|
| Orchestrator 职责 | spawn → yield → verify → next | spawn → yield → verify → next |
| 业务逻辑位置 | Module Agent prompt | Driver step 方法 |
| exec 代码量/步 | 3-5 行（BlackboardManager 调用） | 3-5 行（Driver 调用） |
| 状态管理 | BlackboardManager | DeliverProDriver |
| prompt 行数 | ~509 行（含 L0/L2 验证） | ~80 行 |

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Driver `__init__` 每次 exec 重复构造对象 | 确定 | 低（<100ms） | 可接受；如需优化可加 module-level cache |
| Driver step 方法签名变更 | 低 | 中 | 213 tests 保护；改签名需更新 prompt |
| Orchestrator 无法处理 Driver 异常输出 | 中 | 中 | prompt 中加入错误处理规则（已有） |
| 现有 blackboard 集成不兼容 | 低 | 低 | Driver 内部已用 blackboard_path |
| `step4_check_workers` 的 stuck detection 在 prompt 中不透明 | 低 | 低 | Driver 返回 `stuck: True` 字段，prompt 只需检查 |

---

## 实施步骤

1. **修改 `driver.py`**（+50 行）：
   - 新增 `driver_init_script(wp_id, project_name)` → 返回 preamble 字符串
   - 新增 `step_check(phase, **kwargs)` → 统一验证入口（可选）

2. **重写 `__init__.py` 的 `_build_orchestrator_prompt()`**（-509 行）：
   - 删除 12+ exec 代码块
   - 替换为 Driver 方法调用表
   - 保留铁律规则和完成条件

3. **运行现有 tests**：确认 213 tests 仍 pass（不改 orchestrator.py/contracts/）

4. **端到端验证**：用一个简单 WP 跑完整 5 Phase

---

## 总结

**核心思路**：DeliverProDriver 是现成的"薄层"，只是没被 Orchestrator 使用。改造 = 让 Orchestrator 调 Driver，而不是自己写 inline Python。这与 Solution Pro 的"Orchestrator 只调度不执行"原则完全一致，只是不需要引入 Module Agent 中间层。
