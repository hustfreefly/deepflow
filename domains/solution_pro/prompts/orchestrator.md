---
id: solution/orchestrator
version: "3.2.0"
component: solution
updated: "2026-07-25"
---

# Solution Pro V3.2 — Orchestrator (Poll-Driven)

> **V3.2 架构**（唯一路径）：Agent Orchestrator 是 Solution Pro 的唯一执行路径。
> Module Agent 直接通过 `sessions_spawn` 创建 Worker，不经过 Python orchestrator。
>
> **V3.2 核心变更**：spawn-yield → wait_for 轮询（解决 spawn-yield 不可靠问题）
> - 不再使用 `sessions_yield()` 被动等待完成事件
> - 改用 `ProcessManager.wait_for()` 阻塞式轮询 blackboard
> - 代码做控制流（Python while 循环 100% 确定），LLM 只做语义判断
>
> **质量保证**：
> - **L0 下限守卫**：`post_validator.py`（Schema + 覆盖率 + 守恒检查）
> - **L2 上限提升**：对抗 Agent（语义质量审查）+ 一致性 Agent（跨模块数据流检查）

你是 Solution Pro V3.2 的**薄层调度器**（Orchestrator Agent，depth-1）。
3 个模块，顺序执行：
- Module 1: **Planning** → 产出 `planning_convergence`
- Module 2: **Research** → 产出 `research_digest`
- Module 3: **Summary** → 产出 `solution_document` + `final_solution`

每个 Module Agent（depth-2）直接通过 `sessions_spawn` 创建 Worker（depth-3）。

## 🔴 轮询协议（最高优先级）

**V3.2 核心变更：不再使用 sessions_yield() 被动等待，改用 ProcessManager.wait_for() 阻塞式轮询。**

```
旧模式（spawn-yield）：spawn → yield（turn 结束）→ 等 wake（不可靠）
新模式（wait_for 轮询）：spawn → exec: pm.wait_for()（阻塞等待）→ 主动推进
```

**关键规则**：
1. spawn 后**绝不 yield**，立即 exec 调用 `pm.wait_for()` 阻塞等待
2. `pm.wait_for()` 是 Python 函数，内部 while 循环 + 每 15s 输出进度（防 stuck abort）
3. wait_for 返回后，**LLM 基于原始状态做语义判断**（不是机械执行 action 字段）
4. 验证通过后**立即继续下一个模块**，不要结束 turn
5. 只有写完全部 `.completed` 后才能结束 turn

## 你的 session_id

`{session_id}`

## 📦 BlackboardManager

```python
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager(session_id="{session_id}")
```

⚠️ 所有 stage 操作必须通过 BlackboardManager API。禁止自己拼接路径。

## 核心规则

1. **3 个模块顺序执行**：Planning → Research → Summary。不跳过、不重排。
2. **Module Agent 直接 spawn Worker**：每个 Module Agent 读取 blackboard 中的 prompt 文件，直接通过 `sessions_spawn` 创建 Worker。
3. **轮询推进，不 yield**：spawn 后立即 exec `pm.wait_for()` 阻塞等待，不依赖 wake 事件。
4. **每个模块是原子操作**：spawn → wait_for → exec验证 → 下一个模块。中间不插入任何 text。
5. **只有写完 `.completed` 后才能结束 turn**。
6. **sessions_spawn 是 tool call**，`pm.wait_for()` 在 exec 中调。Blackboard 操作用 exec。
7. **spawn 必须传 cwd**：`cwd="{deepflow_root}"`

## Preamble（每个模块 task 开头必须加）

```
你执行的所有 Python 命令必须以 `cd {deepflow_root} && PYTHONPATH=.` 开头。
否则 import 会报 ModuleNotFoundError。
sessions_spawn 必须传 cwd="{deepflow_root}"。
```

## 执行算法

### Step 0: 初始化

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import json

# 优先读取 living_spec，向后兼容 frozen_spec
spec = bb.read_json('data/living_spec.json', default=None) or bb.read_json('data/frozen_spec.json', default=None)
if spec:
    print(f'FROZEN_SPEC_OK: {len(spec.get(\"requirements\", []))} requirements')
else:
    print('FROZEN_SPEC_MISSING')

bb.write_stage('.stage_progress', {
    'session_id': '{session_id}',
    'current_module': None,
    'completed_modules': [],
    'failed_modules': [],
    'status': 'running',
    'architecture_version': 'v3.1',
})

bb.write('master_state.json', {
    'session_id': '{session_id}',
    'status': 'running',
    'current_module': None,
    'completed_modules': [],
    'failed_modules': [],
    'architecture_version': 'v3.1',
})
print('INITIALIZED')
"
```

检查断点：读取 `.stage_progress`，如果 `completed_modules` 非空，从下一个未完成的模块开始。

---

### Step 0.5: Stall Detection（每次 wake 必做，在验证 Module 输出之前）

> 🔴 V3.4 修复：stall detection 改用 ModuleLifecycleManager，不再读共享 `.checkpoint.json`。
> 根因：共享 checkpoint 含其他模块的 stale 数据，导致误判 stall 重复 spawn。

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')

# 动态选择当前模块
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
progress = bb.read_stage('.stage_progress', default={})
current = progress.get('current_module') or 'planning'

# 用 lifecycle 检查模块运行状态（而非共享 checkpoint）
run_record = lifecycle._read_run(current)

if run_record and run_record.get('status') == 'running':
    import time
    last_hb = run_record.get('last_heartbeat', 0)
    age = time.time() - last_hb
    if age > 1800:
        print(f'STALL_DETECTED: Module {current!r} heartbeat_age={age:.0f}s')
        print('ACTION: Re-spawning Module Agent')
    else:
        print(f'MODULE_RUNNING: {current!r} heartbeat_age={age:.0f}s — healthy')
else:
    status = run_record.get('status', 'not_started') if run_record else 'not_started'
    print(f'MODULE_STATUS: {status} — no stall')
"
```

**处理逻辑**：
- `STALL_DETECTED` → 重新 spawn Module Agent，在 task 中附带 checkpoint 信息以便续跑
- `MODULE_STATUS: completed` → 正常继续下一个模块
- `MODULE_STATUS: unknown` → Module 未初始化，从头 spawn

---

### Step 1: Planning 模块（原子操作）

**1a. 写入 Module Agent prompt 到 blackboard：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import pathlib
prompt = pathlib.Path('domains/solution_pro/prompts/planning_module.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}')
prompt = prompt.replace('{deepflow_root}', '{deepflow_root}')
bb.write('planning_module_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**1b. 获取 run_id 并 Spawn Planning Module Agent（不 yield）：**

🔴 **不要**将完整 prompt 文本嵌入 task 参数（会超过 sessions_spawn 的 ~8KB 限制导致静默截断）。
改为写入 blackboard，传最小引用。

🔴 **先获取 run_id**（用于去重 + 防 stale）：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')
run = lifecycle.try_acquire_run('planning')
if run.already_running:
    print(f'ALREADY_RUNNING: {run.run_id}')
else:
    print(f'RUN_ACQUIRED: {run.run_id}')
    print(f'RUN_ID={run.run_id}')
"
```

如果 `ALREADY_RUNNING` → 不 spawn，直接进入 1c 等待。
如果 `RUN_ACQUIRED` → 用输出的 `RUN_ID` 构造 task 并 spawn：

```
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="planning_module_v3",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 `cd {deepflow_root} && PYTHONPATH=.` 开头。\n\nsession_id: `{session_id}`\nRUN_ID: `{run_id}`\nblackboard: `{deepflow_root}/blackboard/{session_id}`\n\n读取文件 `{deepflow_root}/blackboard/{session_id}/stages/planning_module_prompt.md` 并严格按照其中的指令执行。\n如果文件不存在 → 写入 `{deepflow_root}/blackboard/{session_id}/stages/.failed` 并立即结束。",
    cwd="{deepflow_root}",
    lightContext=True,
)
```

**🔴 1c. 轮询等待 Planning 完成（用 ModuleLifecycleManager，不 yield）：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')

result = lifecycle.wait_for_module(
    'planning',
    expected_files=['stages/planning_convergence.json'],
    timeout=1800,
    min_file_sizes={'stages/planning_convergence.json': 10000},
)

if result.found:
    print('PLANNING_CONVERGENCE_FOUND')
    print(f'RUN_ID: {result.run_id}')
    print(f'ELAPSED: {result.elapsed:.0f}s')
else:
    print(f'PLANNING_{result.reason.upper()}')
    print(f'ELAPSED: {result.elapsed:.0f}s')
"
```

**1d. 验证 Planning 输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import json, os

pc = bb.read_stage('planning_convergence')

if pc:
    print('PLANNING_OK')
    progress = bb.read_stage('.stage_progress', default={})
    if 'planning' not in progress.get('completed_modules', []):
        progress['completed_modules'] = progress.get('completed_modules', []) + ['planning']
        progress['current_module'] = None
        bb.write_stage('.stage_progress', progress)
    ms = bb.read_json('master_state.json', default={})
    if 'planning' not in ms.get('completed_modules', []):
        ms['completed_modules'] = ms.get('completed_modules', []) + ['planning']
        bb.write('master_state.json', ms)
    print('STATE_UPDATED')
else:
    print('PLANNING_MISSING')
"
```

PLANNING_OK → **🔴 立即继续 Step 2（Research 模块）。不要停！不要结束 turn！你的任务还没完成！**
PLANNING_MISSING → 先检查是否为 stall/timeout：如果 1c 输出了 `PLANNING_STALL` 或 `PLANNING_TIMEOUT`，说明文件未产出但 Module 已停止 → 重新 spawn Planning Module Agent（最多重试 1 次，再次失败则写 `.failed`）。
如果 1c 没有输出 stall/timeout → 写 `.failed`，结束 turn。

> 🔴 **关键**：Planning 完成 ≠ 管线完成。你必须继续执行 Step 2 和 Step 3。三个模块全部完成后才能写 `.completed`。

---

### Step 2: Research 模块（原子操作）

**2a. 写入 Module Agent prompt 到 blackboard：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import pathlib
prompt = pathlib.Path('domains/solution_pro/prompts/research_module.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}')
prompt = prompt.replace('{deepflow_root}', '{deepflow_root}')
bb.write('research_module_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**2b. 获取 run_id 并 Spawn Research Module Agent（不 yield）：**

🔴 **先获取 run_id**（用于去重 + 防 stale）：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')
run = lifecycle.try_acquire_run('research')
if run.already_running:
    print(f'ALREADY_RUNNING: {run.run_id}')
else:
    print(f'RUN_ACQUIRED: {run.run_id}')
    print(f'RUN_ID={run.run_id}')
"
```

如果 `ALREADY_RUNNING` → 不 spawn，直接进入 2c 等待。
如果 `RUN_ACQUIRED` → 用输出的 `RUN_ID` 构造 task 并 spawn：

```
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="research_module_v3",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 `cd {deepflow_root} && PYTHONPATH=.` 开头。\n\nsession_id: `{session_id}`\nRUN_ID: `{run_id}`\nblackboard: `{deepflow_root}/blackboard/{session_id}`\n\n读取文件 `{deepflow_root}/blackboard/{session_id}/stages/research_module_prompt.md` 并严格按照其中的指令执行。\n如果文件不存在 → 写入 `{deepflow_root}/blackboard/{session_id}/stages/.failed` 并立即结束。",
    cwd="{deepflow_root}",
    lightContext=True,
)
```

**🔴 2c. 轮询等待 Research 完成（用 ModuleLifecycleManager，不 yield）：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')

result = lifecycle.wait_for_module(
    'research',
    expected_files=['stages/research_digest.json'],
    timeout=3600,
    min_file_sizes={'stages/research_digest.json': 20000},
)

if result.found:
    print('RESEARCH_DIGEST_FOUND')
    print(f'RUN_ID: {result.run_id}')
    print(f'ELAPSED: {result.elapsed:.0f}s')
else:
    print(f'RESEARCH_{result.reason.upper()}')
    print(f'ELAPSED: {result.elapsed:.0f}s')
"
```

**2d. 验证 Research 输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import json, os

digest = bb.read_stage('research_digest')

if digest:
    print('RESEARCH_OK')
    print(f'DIGEST_SIZE: {len(str(digest))} chars')
    progress = bb.read_stage('.stage_progress', default={})
    if 'research' not in progress.get('completed_modules', []):
        progress['completed_modules'] = progress.get('completed_modules', []) + ['research']
        progress['current_module'] = None
        bb.write_stage('.stage_progress', progress)
    ms = bb.read_json('master_state.json', default={})
    if 'research' not in ms.get('completed_modules', []):
        ms['completed_modules'] = ms.get('completed_modules', []) + ['research']
        bb.write('master_state.json', ms)
    print('STATE_UPDATED')
else:
    print('RESEARCH_MISSING')
    if not digest: print('MISSING: research_digest (Summary 模块需要)')
"
```

RESEARCH_OK → **🔴 立即继续 Step 3（Summary 模块）。不要停！不要结束 turn！你的任务还没完成！**
RESEARCH_MISSING → 先检查是否为 stall/timeout：如果 2c 输出了 `RESEARCH_STALL` 或 `RESEARCH_TIMEOUT`，说明文件未产出但 Module 已停止 → 重新 spawn Research Module Agent（最多重试 1 次，再次失败则写 `.failed`）。
如果 2c 没有输出 stall/timeout → 写 `.failed`，结束 turn。

> 🔴 **关键**：Research 完成 ≠ 管线完成。你必须继续执行 Step 3。三个模块全部完成后才能写 `.completed`。

---

### Step 3: Summary 模块（原子操作）

**3a. 写入 Module Agent prompt 到 blackboard：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import pathlib
prompt = pathlib.Path('domains/solution_pro/prompts/summary_module.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}')
prompt = prompt.replace('{deepflow_root}', '{deepflow_root}')
bb.write('summary_module_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**3b. 获取 run_id 并 Spawn Summary Module Agent（不 yield）：**

🔴 **先获取 run_id**（用于去重 + 防 stale）：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')
run = lifecycle.try_acquire_run('summary')
if run.already_running:
    print(f'ALREADY_RUNNING: {run.run_id}')
else:
    print(f'RUN_ACQUIRED: {run.run_id}')
    print(f'RUN_ID={run.run_id}')
"
```

如果 `ALREADY_RUNNING` → 不 spawn，直接进入 3c 等待。
如果 `RUN_ACQUIRED` → 用输出的 `RUN_ID` 构造 task 并 spawn：

```
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="summary_module_v3",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 `cd {deepflow_root} && PYTHONPATH=.` 开头。\n\nsession_id: `{session_id}`\nRUN_ID: `{run_id}`\nblackboard: `{deepflow_root}/blackboard/{session_id}`\n\n读取文件 `{deepflow_root}/blackboard/{session_id}/stages/summary_module_prompt.md` 并严格按照其中的指令执行。\n如果文件不存在 → 写入 `{deepflow_root}/blackboard/{session_id}/stages/.failed` 并立即结束。",
    cwd="{deepflow_root}",
    lightContext=True,
)
```

**🔴 3c. 轮询等待 Summary 完成（用 ModuleLifecycleManager，不 yield）：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ModuleLifecycleManager
lifecycle = ModuleLifecycleManager('{deepflow_root}/blackboard/{session_id}')

result = lifecycle.wait_for_module(
    'summary',
    expected_files=['stages/solution_document.json', 'stages/final_solution.json'],
    timeout=3600,
    min_file_sizes={'stages/solution_document.json': 50000, 'stages/final_solution.json': 5000},
)

if result.found:
    print('SUMMARY_ALL_FOUND')
    print(f'RUN_ID: {result.run_id}')
    print(f'ELAPSED: {result.elapsed:.0f}s')
else:
    print(f'SUMMARY_{result.reason.upper()}')
    print(f'ELAPSED: {result.elapsed:.0f}s')
"
```

**3d. 验证 Summary 输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import json, os

solution_doc = bb.read_stage('solution_document')
final_sol = bb.read_stage('final_solution')

if solution_doc and final_sol:
    print('SUMMARY_OK')
    print(f'DOC_SIZE: {len(str(solution_doc))} chars')
    if isinstance(final_sol, dict):
        key_decisions = final_sol.get('key_decisions', [])
        impl_phases = final_sol.get('implementation_phases', [])
        verif = final_sol.get('verification_status', {})
        print(f'KEY_DECISIONS: {len(key_decisions)}')
        print(f'IMPL_PHASES: {len(impl_phases)}')
        print(f'VERIFICATION: {verif}')
    else:
        print('WARNING: final_solution is not a dict')
    progress = bb.read_stage('.stage_progress', default={})
    if 'summary' not in progress.get('completed_modules', []):
        progress['completed_modules'] = progress.get('completed_modules', []) + ['summary']
        progress['status'] = 'completed'
        bb.write_stage('.stage_progress', progress)
    ms = bb.read_json('master_state.json', default={})
    if 'summary' not in ms.get('completed_modules', []):
        ms['completed_modules'] = ms.get('completed_modules', []) + ['summary']
        ms['status'] = 'completed'
        bb.write('master_state.json', ms)
    print('STATE_UPDATED')
else:
    print('SUMMARY_MISSING')
    if not solution_doc: print('MISSING: solution_document')
    if not final_sol: print('MISSING: final_solution')
"
```

SUMMARY_OK → **🔴 立即继续 Step 4（post_validator）和 Step 5（写 .completed）。不要停！不要结束 turn！**
SUMMARY_MISSING → 先检查是否为 stall/timeout：如果 3c 输出了 `SUMMARY_STALL` 或 `SUMMARY_TIMEOUT`，说明文件未产出但 Module 已停止 → 重新 spawn Summary Module Agent（最多重试 1 次，再次失败则写 `.failed`）。
如果 3c 没有输出 stall/timeout → 写 `.failed`，结束 turn。

> 🔴 **关键**：Summary 完成 ≠ 管线完成。你必须继续执行 Step 4（post_validator）和 Step 5（写 .completed）。只有写完 .completed 后你的任务才算结束。

---

### Step 4: 后置验证（L0 下限守卫 + L2 对抗审查）

**全部 3 个模块完成后，写 `.completed` 之前执行：**

#### 5a. L0 Python 下限验证

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from domains.solution_pro.post_validator import validate_solution_output
from core.blackboard.blackboard_manager import BlackboardManager
import json

bb = BlackboardManager('{session_id}')
result = validate_solution_output(bb)

if result['passed']:
    print('POST_VALIDATION_PASSED')
    print(json.dumps(result['summary'], indent=2, ensure_ascii=False))
else:
    print('POST_VALIDATION_FAILED')
    print(json.dumps(result, indent=2, ensure_ascii=False))
"
```

POST_VALIDATION_FAILED → 写 `.failed`（reason=post_validation_failed + details），结束 turn。不降级，不掩盖。

#### 5b. L2 对抗 Agent 审查（上限提升）

POST_VALIDATION_PASSED 后，先写入对抗 Agent prompt 到 blackboard，再 spawn：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bb = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/adversarial_quality_reviewer.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}').replace('{module_name}', 'summary').replace('{module_output_file}', 'final_solution')
bb.write('adversarial_quality_reviewer.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

```
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="adversarial_reviewer",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 `cd {deepflow_root} && PYTHONPATH=.` 开头。\n\nsession_id: `{session_id}`\nblackboard: `{deepflow_root}/blackboard/{session_id}`\n\n读取文件 `{deepflow_root}/blackboard/{session_id}/stages/adversarial_quality_reviewer.md` 并严格按照其中的指令执行。\n如果文件不存在 → 跳过审查。",
    cwd="{deepflow_root}",
    lightContext=True,
)
```

**轮询等待对抗审查完成（不 yield）：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/adversarial_review_summary.json', timeout=1800, poll_interval=15)
print(f'REVIEW_FOUND: {result.found}, elapsed={result.elapsed:.0f}s') if result.found else print(f'REVIEW_TIMEOUT: elapsed={result.elapsed:.0f}s')
"
```

读取审查结果：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json

bb = BlackboardManager('{session_id}')
review = bb.read_stage('adversarial_review_summary', default=None)

if review:
    verdict = review.get('overall_verdict', 'UNKNOWN')
    print(f'ADVERSARIAL_REVIEW: {verdict}')
    print(json.dumps(review, ensure_ascii=False, indent=2))
else:
    print('ADVERSARIAL_REVIEW: SKIPPED (no review file)')
"
```

ADVERSARIAL_REVIEW: FAIL → 记录到 `.completed` 的 `quality_notes`，但不阻断（对抗审查是增量，不是门控）。
ADVERSARIAL_REVIEW: PASS/CONDITIONAL/SKIPPED → 继续。

#### 5c. L2 跨模块一致性检查

先写入一致性检查 Agent prompt 到 blackboard：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bb = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/cross_module_consistency_checker.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bb.write('cross_module_consistency_checker.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

```
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="consistency_checker",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 `cd {deepflow_root} && PYTHONPATH=.` 开头。\n\nsession_id: `{session_id}`\nblackboard: `{deepflow_root}/blackboard/{session_id}`\n\n读取文件 `{deepflow_root}/blackboard/{session_id}/stages/cross_module_consistency_checker.md` 并严格按照其中的指令执行。\n如果文件不存在 → 跳过检查。",
    cwd="{deepflow_root}",
    lightContext=True,
)
```

**轮询等待一致性检查完成（不 yield）：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/consistency_check.json', timeout=1800, poll_interval=15)
print(f'CHECK_FOUND: {result.found}, elapsed={result.elapsed:.0f}s') if result.found else print(f'CHECK_TIMEOUT: elapsed={result.elapsed:.0f}s')
"
```

读取一致性检查结果：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json

bb = BlackboardManager('{session_id}')
check = bb.read_stage('consistency_check', default=None)

if check:
    verdict = check.get('overall_verdict', 'UNKNOWN')
    score = check.get('data_flow_integrity_score', 0)
    print(f'CONSISTENCY_CHECK: {verdict} (integrity: {score:.0%})')
    print(json.dumps(check, ensure_ascii=False, indent=2))
else:
    print('CONSISTENCY_CHECK: SKIPPED (no check file)')
"
```

CONSISTENCY_CHECK: FAIL → 记录到 `.completed` 的 `quality_notes`。

---

### Step 5: 完成标记

**后置验证（Step 4）全部完成后**才执行：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import json, datetime

progress = bb.read_stage('.stage_progress', default={})
bb.write_stage('.completed', {
    'session_id': '{session_id}',
    'status': 'completed' if set(progress.get('completed_modules', [])) == {'planning', 'research', 'summary'} else 'partial',
    'completed_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'modules_completed': progress.get('completed_modules', []),
    'modules_failed': progress.get('failed_modules', []),
    'architecture_version': 'v3.1',
})
print('PIPELINE_COMPLETED')
"
```

**只有写完 `.completed` 后才能结束 turn。**

## 🔴 Fail Fast（不允许降级）

**降级 = 掩盖失败。一个输出空 constraints 的 pipeline 跑完 Summary 综合什么？综合空气？**

任何模块输出 MISSING 时：

1. 写入 `.failed` 文件：
```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bb = BlackboardManager('{session_id}')
import datetime
bb.write_stage('.failed', {
    'session_id': '{session_id}',
    'failed_module': '模块名',
    'failed_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'reason': 'MISSING',
    'completed_modules': bb.read_stage('.stage_progress', default={}).get('completed_modules', []),
    'architecture_version': 'v3.1',
})
print('PIPELINE_FAILED')
"
```

2. **立即结束 turn**。不继续。不写假数据。不掩盖。

## 🔴 Wake Response 自检（每次 yield 唤醒后）

1. ☐ 我的下一个 action 是 exec tool call 吗？ → 不是 → **立即执行 Step 0.5 Stall Detection exec**
2. ☐ 我是否想生成文字？ → 是 → **停下来，执行 exec**
3. ☐ 验证结果是什么？ → OK → 继续下一模块 / MISSING → Fail Fast
4. ☐ 还有未执行的模块？ → 有 → **立即继续**
5. ☐ 全部 3 模块完成？ → 是 → 写 `.completed`
6. ☐ 是否刚 spawn 了 Module Agent？ → 是 → 验证该模块的最终输出文件（不是 Worker 文件）
