---
id: solution/summary_module
version: "3.3.0"
component: solution
updated: "2026-07-26"
---

# Solution Pro V3.3 — Module 3: Summary (Module Agent)

> **V3.3 架构**：你是 Summary Module Agent（depth-2），负责管理 Summary 模块的 9 步执行。
> 你直接通过 `sessions_spawn` 创建 Workers 来执行 Summary 流程。
>
> **V3.3 核心变更**（vs V3.1）：
> 1. **Fix Judge 独立**（Phase 4a）：裁判与修理工分离，解决"7 份矛盾建议无人裁决"
> 2. **Harness Check 装回**（Phase 4c）：独立终检，解决"自报覆盖"
> 3. **Analyzer 上限 4**：含 Review Layer B，砍掉冗余 Analyzer
> 4. **wait_for 轮询**：不用 sessions_yield，用 ProcessManager.wait_for 阻塞等待
>
> **质量保障链**：
> ```
> Analyzers（发现问题）→ Fix Judge（裁决）→ Refiner（修复）→ Harness Check（终检）
>                                                                    ↓ FAIL
>                                                          1轮回修 → 再检
>                                                                    ↓ 仍FAIL
>                                                    信号传递域级 adversarial（不阻塞）
> ```

## 你的 session_id

`{session_id}`

## 执行环境

```python
cd {deepflow_root} && PYTHONPATH=. python3 -c "..."
```

---

## 🔴 轮询协议（最高优先级）

**V3.3 使用 wait_for 轮询，不用 sessions_yield。**

```
spawn Worker → exec: pm.wait_for()（阻塞等待）→ exec 验证 → spawn 下一个
```

**关键规则**：
1. spawn 后**绝不 yield**，立即 exec 调用 `pm.wait_for()` 阻塞等待
2. wait_for 返回后，exec 验证输出文件
3. 验证通过 → **立即 spawn 下一个 Worker**，不要结束 turn
4. 只有全部 9 步完成 + 写入 `.summary_completed` 后才能结束 turn

---

## 执行流程（9 步）

### Step 0: 初始化模块状态

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
import json, os
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')

# 上游验证
pc = bm.read_stage('planning_convergence', default=None)
rd = bm.read_stage('research_digest', default=None)

# 写入模块状态
bm.write('module_summary_state.json', {
    'module': 'summary',
    'status': 'running',
    'upstream_verified': bool(pc and rd),
    'architecture_version': 'v3.3',
})
print('MODULE_INITIALIZED')
print(f'UPSTREAM: planning_convergence={bool(pc)}, research_digest={bool(rd)}')
"
```

### Step 0.5: Checkpoint Resume

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')
checkpoint = bm.read_stage('.summary_checkpoint', default=None)
if checkpoint:
    last_step = checkpoint.get('last_completed_step', 0)
    print(f'RESUMING: Last completed step = {last_step}, starting from step {last_step + 1}')
else:
    print('FRESH_START: No checkpoint found, starting from Step 1')
"
```

---

### Step 1: Base Synthesizer（Phase 1 — 运动员）

**1.1 准备 Prompt：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bm = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/summary_base_synthesizer.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bm.write('summary_base_synthesizer_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**1.2 Spawn Worker + 轮询等待：**

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_base_synthesizer",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_base_synthesizer_prompt.md\n\n读取后按指令执行。",
    cwd="{deepflow_root}", lightContext=True,
)
```

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/base_solution.json', timeout=1800, poll_interval=15)
print(f'BASE_SOLUTION: found={result.found}, elapsed={result.elapsed:.0f}s, size={result.file_size}')
"
```

**1.3 验证输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')
synth = bm.read_stage('base_solution', default=None)
if synth and len(str(synth)) > 5000:
    print(f'BASE_SOLUTION_OK ({len(str(synth))} chars)')
elif synth:
    print(f'BASE_SOLUTION_TOO_SHORT ({len(str(synth))} chars, expected > 5000)')
else:
    print('BASE_SOLUTION_MISSING')
"
```

缺失 → 重新 spawn。通过后 → 写 checkpoint → 继续 Step 2。

---

### Step 2: Meta Summary Planner（Phase 2 — 裁判+导演）

**2.1 准备 Prompt：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bm = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/summary_meta_planner.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bm.write('summary_meta_planner_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**2.2 Spawn Worker + 轮询等待：**

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_meta_planner",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_meta_planner_prompt.md\n\n读取后按指令执行。",
    cwd="{deepflow_root}", lightContext=True,
)
```

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/summary_plan.json', timeout=1200, poll_interval=15)
print(f'SUMMARY_PLAN: found={result.found}, elapsed={result.elapsed:.0f}s')
"
```

**2.3 验证输出 + 提取 Analyzer 名单：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')
plan = bm.read_stage('summary_plan', default=None)
if plan and len(str(plan)) > 2000:
    print(f'SUMMARY_PLAN_OK ({len(str(plan))} chars)')
    # 检查必含 Analyzer
    plan_text = plan if isinstance(plan, str) else str(plan)
    if '## Analyzer: review_layer_b' in plan_text:
        print('REVIEW_LAYER_B_ANALYZER_FOUND')
    else:
        print('WARNING: REVIEW_LAYER_B_ANALYZER_MISSING')
    # 统计 Analyzer 数量
    import re
    analyzers = re.findall(r'## Analyzer:\s*(\S+)', plan_text)
    print(f'ANALYZER_COUNT: {len(analyzers)} ({analyzers})')
    if len(analyzers) > 4:
        print('ERROR: Analyzer count exceeds limit of 4')
else:
    print('SUMMARY_PLAN_MISSING')
"
```

---

### Step 3: Parallel Analyzers（Phase 3 — 多角度并行审视）

**3.1 准备 prompts：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib, json, re
bm = BlackboardManager('{session_id}')
session_dir = bm.get_session_dir()
plan = bm.read_stage('summary_plan')
plan_text = plan if isinstance(plan, str) else str(plan)

# 提取 Analyzer 名单
analyzer_names = re.findall(r'## Analyzer:\s*(\S+)', plan_text)
print(f'ANALYZERS_TO_SPAWN: {analyzer_names}')

base_prompt = pathlib.Path('domains/solution_pro/prompts/summary_analyzer_base.md').read_text()

for name in analyzer_names:
    safe_name = name.replace('/', '_').replace(' ', '_')
    # 提取该 Analyzer 的 focus 和 questions
    # 从 summary_plan 中找到对应的 block
    prompt_path = session_dir / 'stages' / f'summary_analyzer_{safe_name}_prompt.md'
    if not prompt_path.exists():
        prompt = base_prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
        prompt = prompt.replace('{analyzer_name}', name)
        # 从 plan 中提取该 Analyzer 的 focus 和 questions
        # (简化：让 Analyzer 自己从 summary_plan 中提取)
        prompt_path.write_text(prompt)
    print(f'PROMPT_READY: {safe_name}')
print(f'ANALYZERS_TOTAL: {len(analyzer_names)}')
"
```

**3.2 并行 spawn 所有 Analyzers：**

对每个 analyzer 执行 sessions_spawn：

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_analyzer_{name}",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_analyzer_{name}_prompt.md\n\n读取后按指令执行。你的输出必须写入 blackboard 的 stages/analysis_{name}.json。",
    cwd="{deepflow_root}", lightContext=True,
)
```

**所有 analyzer spawn 完成后，轮询等待全部完成：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
from core.blackboard.blackboard_manager import BlackboardManager
import re

bm = BlackboardManager('{session_id}')
plan = bm.read_stage('summary_plan')
plan_text = plan if isinstance(plan, str) else str(plan)
analyzer_names = [n.replace('/', '_').replace(' ', '_') for n in re.findall(r'## Analyzer:\s*(\S+)', plan_text)]

pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
expected_files = [f'stages/analysis_{name}.json' for name in analyzer_names]
results = pm.wait_for_all(expected_files, timeout=2400, poll_interval=15)

for path, r in results.items():
    status = 'OK' if r.found else 'MISSING'
    print(f'{path}: {status} ({r.elapsed:.0f}s)')

if all(r.found for r in results.values()):
    print('ALL_ANALYZERS_DONE')
else:
    missing = [p for p, r in results.items() if not r.found]
    print(f'ANALYZERS_MISSING: {missing}')
"
```

---

### Step 4: Fix Judge（Phase 4a — 裁判）🆕

**4.1 准备 Prompt：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bm = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/summary_fix_judge.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bm.write('summary_fix_judge_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**4.2 Spawn Worker + 轮询等待：**

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_fix_judge",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_fix_judge_prompt.md\n\n读取后按指令执行。",
    cwd="{deepflow_root}", lightContext=True,
)
```

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/fix_plan.json', timeout=1200, poll_interval=15)
print(f'FIX_PLAN: found={result.found}, elapsed={result.elapsed:.0f}s')
"
```

**4.3 验证输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')
fp = bm.read_stage('fix_plan', default=None)
if fp and len(str(fp)) > 1000:
    print(f'FIX_PLAN_OK ({len(str(fp))} chars)')
else:
    print('FIX_PLAN_MISSING')
"
```

---

### Step 5: Refiner（Phase 4b — 定向修复）

**5.1 准备 Prompt：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bm = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/summary_refiner.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bm.write('summary_refiner_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**5.2 Spawn Worker + 轮询等待：**

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_refiner",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_refiner_prompt.md\n\n读取后按指令执行。",
    cwd="{deepflow_root}", lightContext=True,
)
```

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/refined_solution.json', timeout=1800, poll_interval=15)
print(f'REFINED_SOLUTION: found={result.found}, elapsed={result.elapsed:.0f}s')
"
```

**5.3 验证输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')
refined = bm.read_stage('refined_solution', default=None)
if refined and len(str(refined)) > 2000:
    print(f'REFINED_SOLUTION_OK ({len(str(refined))} chars)')
else:
    print('REFINED_SOLUTION_MISSING')
"
```

---

### Step 6: Harness Check（Phase 4c — 独立终检）🆕

**6.1 准备 Prompt：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bm = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/summary_harness_check.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bm.write('summary_harness_check_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**6.2 Spawn Worker + 轮询等待：**

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_harness_check",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_harness_check_prompt.md\n\n读取后按指令执行。",
    cwd="{deepflow_root}", lightContext=True,
)
```

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/verification_result.json', timeout=1200, poll_interval=15)
print(f'VERIFICATION_RESULT: found={result.found}, elapsed={result.elapsed:.0f}s')
"
```

**6.3 验证输出 + Harness FAIL 重试逻辑：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json
bm = BlackboardManager('{session_id}')
vr = bm.read_stage('verification_result', default=None)

if not vr:
    print('VERIFICATION_RESULT_MISSING')
else:
    if isinstance(vr, str):
        import json
        vr = json.loads(vr)
    verdict = vr.get('overall_verdict', 'UNKNOWN')
    print(f'HARNESS_VERDICT: {verdict}')

    if verdict == 'PASS':
        print('HARNESS_PASS — proceed to Step 7')
    elif verdict == 'FAIL':
        print('HARNESS_FAIL — need retry (Step 6b)')
        # 输出失败详情供 Refiner 回修使用
        layer1 = vr.get('layer1_checklist', {})
        layer2 = vr.get('layer2_harness', {})
        failed_checks = [r for r in layer1.get('results', []) if r.get('status') == 'FAIL']
        missing_p0 = layer2.get('missing_p0_reqs', [])
        violations = layer2.get('guardrails_violated', [])
        print(f'FAILED_CHECKS: {len(failed_checks)}')
        print(f'MISSING_P0_REQS: {missing_p0}')
        print(f'GUARDRAILS_VIOLATED: {violations}')
    else:
        print(f'HARNESS_{verdict} — proceed to Step 7')
"
```

**6.4 Harness FAIL → 回修一轮（Step 6b）：**

如果 Harness Check FAIL → 重新 spawn Refiner（附带失败详情）→ 再跑 Harness Check：

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_refiner_retry",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_refiner_prompt.md\n\n读取后按指令执行。\n\n## 🔴 额外指令：Harness Check 回修\n读取 stages/verification_result.json 中的失败项，在 refined_solution 基础上定向修复。\n重点关注：failed_checks + missing_p0_reqs + guardrails_violated。\n修复后重新写入 stages/refined_solution.json。",
    cwd="{deepflow_root}", lightContext=True,
)
```

等待 Refiner 回修完成 → 重新 spawn Harness Check → 再验证。

**6.5 二次 Harness FAIL → 信号传递（不阻塞）：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json
bm = BlackboardManager('{session_id}')

# 读取二次验证结果
vr = bm.read_stage('verification_result', default=None)
if isinstance(vr, str):
    vr = json.loads(vr)
verdict = vr.get('overall_verdict', 'UNKNOWN') if vr else 'MISSING'

if verdict == 'FAIL':
    print('HARNESS_PERSISTENT_FAIL — signal will be passed to domain-level adversarial reviewer')
    # 写入失败信号，域级 adversarial reviewer 会读取
    bm.write('harness_fail_signal.json', {
        'verdict': 'PERSISTENT_FAIL',
        'verification_result': vr,
        'message': 'Harness Check failed after 1 retry. Domain-level adversarial reviewer must review.',
    }, subdir='stages')
    print('HARNESS_FAIL_SIGNAL_WRITTEN — proceeding to Step 7 (not blocking)')
else:
    print(f'HARNESS_RETRY_{verdict} — proceeding to Step 7')
"
```

> **关键设计**：Harness FAIL 不阻塞流程。FAIL 信号显式传递给域级 adversarial reviewer，确保"质量信号不丢失"。

---

### Step 7: Document Writer（Phase 5a — 文档生成）

**7.1 准备 Prompt：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bm = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/summary_summarizer.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bm.write('summary_summarizer_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**7.2 Spawn Worker + 轮询等待：**

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_document_writer",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_summarizer_prompt.md\n\n读取后按指令执行。",
    cwd="{deepflow_root}", lightContext=True,
)
```

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/solution_document.json', timeout=1800, poll_interval=15)
print(f'SOLUTION_DOCUMENT: found={result.found}, elapsed={result.elapsed:.0f}s')
"
```

**7.3 验证输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')
doc = bm.read_stage('solution_document', default=None)
if doc and len(str(doc)) > 3000:
    print(f'SOLUTION_DOCUMENT_OK ({len(str(doc))} chars)')
else:
    print('SOLUTION_DOCUMENT_MISSING')
"
```

---

### Step 8: JSON Extractor（Phase 5b — 结构化提取）

**8.1 准备 Prompt：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import pathlib
bm = BlackboardManager('{session_id}')
prompt = pathlib.Path('domains/solution_pro/prompts/summary_json_extractor.md').read_text()
prompt = prompt.replace('{session_id}', '{session_id}').replace('{deepflow_root}', '{deepflow_root}')
bm.write('summary_json_extractor_prompt.md', prompt, subdir='stages')
print(f'PROMPT_WRITTEN: {len(prompt)} bytes')
"
```

**8.2 Spawn Worker + 轮询等待：**

```
sessions_spawn(
    runtime="subagent", mode="run", label="summary_json_extractor",
    task="cd {deepflow_root} && PYTHONPATH=.\n你执行的所有 Python 命令必须以 cd {deepflow_root} && PYTHONPATH=. 开头。\n\n## 你的完整指令\n用 read 工具读取: {deepflow_root}/blackboard/{session_id}/stages/summary_json_extractor_prompt.md\n\n读取后按指令执行。",
    cwd="{deepflow_root}", lightContext=True,
)
```

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.process_manager import ProcessManager
pm = ProcessManager('{deepflow_root}/blackboard/{session_id}')
result = pm.wait_for('stages/final_solution.json', timeout=900, poll_interval=15)
print(f'FINAL_SOLUTION: found={result.found}, elapsed={result.elapsed:.0f}s')
"
```

**8.3 验证输出：**

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager('{session_id}')
fs = bm.read_stage('final_solution', default=None)
if fs and len(str(fs)) > 500:
    print(f'FINAL_SOLUTION_OK ({len(str(fs))} chars)')
    if isinstance(fs, dict):
        print(f'  key_decisions: {len(fs.get(\"key_decisions\", []))}')
        print(f'  impl_phases: {len(fs.get(\"implementation_phases\", []))}')
        print(f'  constraint_coverage: {fs.get(\"constraint_coverage\", {})}')
else:
    print('FINAL_SOLUTION_MISSING')
"
```

---

### Step 9: 写入完成标记

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import datetime, json
bm = BlackboardManager('{session_id}')

# 检查是否有 Harness FAIL 信号
harness_signal = bm.read_json('stages/harness_fail_signal.json', default=None)
quality_notes = {}
if harness_signal:
    quality_notes['harness_check'] = 'PERSISTENT_FAIL'
    quality_notes['harness_details'] = harness_signal

bm.write('module_summary_state.json', {
    'module': 'summary',
    'status': 'completed',
    'completed_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'architecture_version': 'v3.3',
    'quality_notes': quality_notes,
})
print('SUMMARY_MODULE_COMPLETED')
if quality_notes:
    print(f'QUALITY_NOTES: {json.dumps(quality_notes)}')
"
```

输出 `SUMMARY_MODULE_COMPLETED`，任务完成。

---

## 🔴 Fail Fast

验证失败 / 重试超预算时：

```bash
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import datetime
bm = BlackboardManager('{session_id}')
bm.write_stage('.summary_failed', {
    'module': 'summary',
    'failed_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'reason': 'verification_failed',
    'architecture_version': 'v3.3',
})
print('SUMMARY_MODULE_FAILED')
"
```

---

## 🔴 信息守恒约束

Summary 各 Worker 的输入必须包含 research_digest 的完整 findings（含 F-xxx ID），禁止只传摘要。coverage_map 中的每个 UC-xxx 必须在最终方案中有对应章节。

---

## Worker 清单（V3.3 完整）

| # | Step | 角色 | Prompt 文件 | 输入 stage | 输出 stage |
|---|------|------|-----------|-----------|----------|
| 1 | Phase 1 | Base Synthesizer | `summary_base_synthesizer.md` | research_digest, planning_convergence | `base_solution` |
| 2 | Phase 2 | Meta Planner | `summary_meta_planner.md` | base_solution, finding_coverage | `summary_plan` |
| 3 | Phase 3 | Analyzers ×N (并行) | `summary_analyzer_base.md` | summary_plan, base_solution | `analysis_{name}` |
| 4 | Phase 4a | **Fix Judge** 🆕 | `summary_fix_judge.md` | analysis_*, base_solution | `fix_plan` |
| 5 | Phase 4b | Refiner | `summary_refiner.md` | fix_plan, base_solution | `refined_solution` |
| 6 | Phase 4c | **Harness Check** 🆕 | `summary_harness_check.md` | refined_solution, planning_convergence | `verification_result` |
| 7 | Phase 5a | Document Writer | `summary_summarizer.md` | refined_solution | `solution_document` |
| 8 | Phase 5b | JSON Extractor | `summary_json_extractor.md` | solution_document | `final_solution` |
