"""
Ship Pro 2.0.0 - 入口模块

架构(2.0.0 统一 blackboard + 单入口 ShipOrchestrator):
  Main Agent (depth-0)
    → exec: result = run_ship_pro(project_name=...)
    → sessions_spawn(**result["spawn_params"])
    → 等待完成事件 → 拿到 ShipPackage

  Orchestrator (depth-1, 全权调度)
    → 读取统一 blackboard 中的 Solution Pro 输出
    → exec: design_pipeline() → Designer prompt
    → spawn: Designer LLM → PipelinePlan
    → exec: prepare_runner_spawn() → Worker prompts
    → spawn: Workers (并行/分层, spawn 后结束当前 turn，cron 会自动唤醒继续)
    → exec: L1 validation
    → spawn: Consolidator
    → exec: ShipPackage validation
    → 输出最终报告

统一 blackboard 结构:
  .deepflow/blackboard/{project_name}/
  ├── data/frozen_spec.json         ← Solution Pro 产出
  ├── stages/solution_document.json ← Solution Pro 产出
  ├── ship_pro/                     ← Ship Pro 写入
  │   ├── solution_pro_input.json   ← 合并后的输入
  │   ├── stages/
  │   │   ├── pipeline_plan.json
  │   │   ├── context_*.json
  │   │   ├── worker_*.json
  │   │   └── ship_package.json
  │   └── ...
  └── ...
"""
import json
import re
from datetime import datetime
from pathlib import Path
from core.trace import start_trace, span, save_to_blackboard  # 全链路追踪:跨域 trace_id
from core.blackboard.context_injector import build_bootstrap_task, auto_bootstrap  # Bootstrap Pattern: 解决 sessions_spawn 8KB 截断


# ============================================================================
# 统一 Blackboard 路径
# ============================================================================

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent
BLACKBOARD_ROOT = DEEPFLOW_ROOT / "blackboard"


def _get_project_blackboard(project_name: str) -> Path:
    """获取项目统一 blackboard 路径"""
    return BLACKBOARD_ROOT / project_name


def _find_solution_pro_output(project_blackboard: Path) -> dict:
    """
    从统一 blackboard 读取 Solution Pro 输出。

    AI Native 架构 (2026-07-15):
      代码只做 I/O + Schema 验证。语义提取由 Agent 层（Orchestrator）完成。
      final_solution.json 是唯一数据源（Agent 层保证产出）。
      MD 是人类可读副本，不做数据传递。不降级、不 fallback。

    Returns:
        final_solution.json 的内容 dict

    Raises:
        ValueError: JSON 不存在或 Schema 验证失败
    """
    import json as _json
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    final_json = project_blackboard / "stages" / "final_solution.json"

    if not final_json.exists():
        raise ValueError(
            f"Solution Pro 契约违反: final_solution.json 不存在\n"
            f"  期望路径: {final_json}\n"
            f"  根因: Solution Pro 未产出结构化 JSON，或 Orchestrator Step 0 未执行语义提取。\n"
            f"  修复: 确保 Orchestrator Step 0（语义提取）已运行，或重新执行 Solution Pro。"
        )

    data = _json.loads(final_json.read_text(encoding="utf-8"))

    # Schema 验证: 必需字段存在且非空（确定性检查，代码做代码该做的事）
    _REQUIRED_FIELDS = [
        "key_decisions", "implementation_phases", "covered_req_ids",
        "constraint_coverage", "semantic_anchors",
    ]
    missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise ValueError(
            f"Solution Pro 契约违反: final_solution.json 缺少必需字段: {missing}\n"
            f"  文件存在但内容不完整。Agent 层语义提取可能失败。"
        )

    _logger.info(
        f"Solution Pro output loaded: {len(data.get('key_decisions', []))} decisions, "
        f"{len(data.get('covered_req_ids', []))} reqs, "
        f"{len(data.get('risk_summary', []))} risks, "
        f"{data.get('constraint_coverage', {}).get('covered', 0)}/{data.get('constraint_coverage', {}).get('total', 0)} constraints"
    )

    data["_solution_source"] = "final_solution_json"
    return data


def _get_ship_pro_dir(project_blackboard: Path) -> Path:
    """获取 Ship Pro 在统一 blackboard 中的目录"""
    ship_dir = project_blackboard / "ship_pro"
    ship_dir.mkdir(parents=True, exist_ok=True)
    (ship_dir / "stages").mkdir(exist_ok=True)
    return ship_dir


# ============================================================================
# 2.0.0 单入口
# ============================================================================

def run_ship_pro(project_name: str, trace_id: str = None, **kwargs) -> dict:
    """
    Ship Pro 2.0.0 唯一入口 - Main Agent 只调这一个函数

    1. 定位统一 blackboard: .deepflow/blackboard/{project_name}/
    2. 自动发现 Solution Pro 输出
    3. 构建 Orchestrator spawn params
    4. 返回 spawn_params - Main Agent 只需 sessions_spawn(**result["spawn_params"])

    Args:
        project_name: 项目名称(blackboard 目录名)
        trace_id: 可选的 trace_id(从 Spec Pro handoff package 继承,实现跨域追踪)
        **kwargs: model 等可选参数

    Returns:
        {
            "project_name": str,
            "project_blackboard": str,
            "ship_pro_dir": str,
            "input_summary": dict,
            "spawn_params": dict,  # Main Agent 直接传给 sessions_spawn
        }
    """
    # 全链路追踪:继承或新建 trace_id,记录 Ship Pro 入口 span
    _trace_id = start_trace(trace_id)
    span("ship_pro_entry", domain="ship_pro", project_name=project_name, trace_id=_trace_id)
    # 全链路追踪:记录 blackboard 定位完成
    span("blackboard_located", domain="ship_pro", project_name=project_name)

    # 1. 定位统一 blackboard
    project_bb = _get_project_blackboard(project_name)
    if not project_bb.exists():
        raise FileNotFoundError(
            f"项目 blackboard 不存在: {project_bb}\n"
            f"  请先运行 Spec Pro / Solution Pro 生成输出"
        )

    # 2. 自动发现 Solution Pro 输出
    sol_input = _find_solution_pro_output(project_bb)

    # 3. 初始化 Ship Pro 目录
    ship_dir = _get_ship_pro_dir(project_bb)

    # 保存合并输入（统一写入 stages/ 目录，保持 gate judge 路径一致）
    input_path = ship_dir / "stages" / "solution_pro_input.json"
    input_path.write_text(json.dumps(sol_input, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4. 构建 Orchestrator prompt
    deepflow_root = str(DEEPFLOW_ROOT)
    orchestrator_prompt = _build_orchestrator_prompt(
        project_name=project_name,
        project_blackboard=str(project_bb),
        ship_pro_dir=str(ship_dir),
        deepflow_root=deepflow_root,
        # AI Native: 字段名由 JSON schema 保证，不做映射/翻译
        input_summary={
            "req_count": len(sol_input.get("covered_req_ids", [])),
            "decision_count": len(sol_input["key_decisions"]),
            "risk_count": len(sol_input.get("risk_summary", [])),
            "constraint_coverage": sol_input.get("constraint_coverage", {}),
        },
    )

    # 全链路追踪:记录追踪数据到 blackboard
    try:
        save_to_blackboard(Path(ship_dir))
    except Exception:
        pass  # 追踪持久化失败不影响主流程

    # ═══════════════════════════════════════════════════════════
    # 契约笼子: Bootstrap Pattern — 解决 sessions_spawn 8KB 截断
    # BUG-002 FIX (2026-07-15): 统一用 auto_bootstrap（写入 + 回读验证 + 绝对路径引用）
    # 旧代码用 build_bootstrap_task（引用 stages/ 但写入 root）→ 路径不匹配
    # ═══════════════════════════════════════════════════════════
    from core.blackboard.context_injector import auto_bootstrap
    bootstrap_task = auto_bootstrap(
        deepflow_root=Path(deepflow_root),
        prompt_dir=ship_dir / "stages",
        task_content=orchestrator_prompt,
        label="ship_orchestrator",
    )
    import logging
    prompt_size = len(orchestrator_prompt.encode('utf-8'))
    logging.getLogger(__name__).info(
        f"Ship Pro Bootstrap: {prompt_size}B → {len(bootstrap_task.encode('utf-8'))}B"
    )

    # 5. 返回 spawn params(包含 trace_id 供下游继承)
    return {
        "project_name": project_name,
        "project_blackboard": str(project_bb),
        "ship_pro_dir": str(ship_dir),
        "trace_id": _trace_id,  # 全链路追踪:trace_id 供下游继承
        # AI Native: 字段名由 JSON schema 保证，不做映射/翻译
        "input_summary": {
            "req_count": len(sol_input.get("covered_req_ids", [])),
            "decision_count": len(sol_input["key_decisions"]),
            "risk_count": len(sol_input.get("risk_summary", [])),
            "constraint_coverage": sol_input.get("constraint_coverage", {}),
        },
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "ship_pro_orchestrator",
            "task": bootstrap_task,
            "cwd": deepflow_root,
            "lightContext": True,
        },
    }


# ============================================================================
# 2.0.0 兼容入口(保留,但推荐用 run_ship_pro)
# ============================================================================

def design_pipeline(solution_pro_output_path: str, **kwargs) -> dict:
    """2.0.0 兼容入口 - 推荐用 run_ship_pro()"""
    from .pipeline_designer import PipelineDesigner, validate_solution_pro_input

    input_path = Path(solution_pro_output_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Solution Pro 输出文件不存在: {input_path}")

    solution_pro_input = json.loads(input_path.read_text(encoding="utf-8"))
    validate_solution_pro_input(solution_pro_input)

    session_prefix = kwargs.get("session_id_prefix", "ship_v8")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{session_prefix}_{timestamp}"

    base_dir = kwargs.get("blackboard_base_dir", str(BLACKBOARD_ROOT))
    session_dir = Path(base_dir) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "stages").mkdir(exist_ok=True)

    import shutil
    dest_input = session_dir / "stages" / "solution_pro_input.json"
    shutil.copy2(str(input_path), str(dest_input))

    designer = PipelineDesigner(blackboard_path=session_dir)
    designer_result = designer.design_pipeline(
        solution_pro_input,
        auto=kwargs.get("auto", False),
        plan_output_dir=kwargs.get("plan_output_dir"),
    )

    deepflow_root = str(DEEPFLOW_ROOT)

    # 双模式处理(契约笼子:确定性分支,不依赖 prompt 指令)
    if designer_result.get("mode") == "auto":
        # Auto mode: plan 已生成,直接保存
        plan_path = session_dir / "stages" / "pipeline_plan.json"
        plan_path.write_text(json.dumps(designer_result["plan"], ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "session_id": session_id,
            "base_path": str(session_dir),
            "solution_pro_input": solution_pro_input,
            "plan": designer_result["plan"],
            "mode": "auto",
            "input_summary": designer_result["input_summary"],
            "deepflow_root": deepflow_root,
        }
    else:
        # Prompt mode: 返回 prompt 供 Orchestrator 分析
        prompt_path = session_dir / "stages" / "_designer_prompt.txt"
        prompt_path.write_text(designer_result["designer_prompt"], encoding="utf-8")
        return {
            "session_id": session_id,
            "base_path": str(session_dir),
            "solution_pro_input": solution_pro_input,
            "designer_prompt": designer_result["designer_prompt"],
            "mode": "prompt",
            "input_summary": designer_result["input_summary"],
            "deepflow_root": deepflow_root,
        }


def prepare_runner_spawn(
    base_path: str,
    designer_output: str,
    solution_pro_input: dict,
    **kwargs
) -> dict:
    """2.0.0 兼容入口 - 推荐用 run_ship_pro()"""
    from .pipeline_designer import PipelineDesigner

    session_dir = Path(base_path)
    designer = PipelineDesigner(blackboard_path=session_dir)

    plan = designer.parse_designer_output(designer_output)

    plan_path = session_dir / "stages" / "pipeline_plan.json"
    plan_path.write_text(
        json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    contexts = designer.generate_worker_contexts(plan, solution_pro_input)
    context_paths = designer.save_contexts(contexts)

    worker_prompts = _build_worker_prompts(plan, contexts, context_paths, session_dir)

    deepflow_root = kwargs.get("deepflow_root", str(DEEPFLOW_ROOT))
    stages_dir = session_dir / "stages"

    worker_spawn_params = []
    for role, prompt in worker_prompts.items():
        label = re.sub(r'[^a-z0-9_-]', '_', f"worker_{role}".lower())
        params = {
            "runtime": "subagent",
            "mode": "run",
            "label": label,
            "task": auto_bootstrap(Path(deepflow_root), stages_dir, prompt, label),
            "lightContext": True,
        }
        worker_spawn_params.append(params)

    spawn_params_path = session_dir / "stages" / "_worker_spawn_params.json"
    spawn_params_path.write_text(
        json.dumps(worker_spawn_params, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    runner_prompt = _build_runner_prompt(
        session_dir=session_dir,
        plan=plan,
        context_paths=context_paths,
        deepflow_root=deepflow_root,
    )

    return {
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "pipeline_runner_v8",
            "task": auto_bootstrap(Path(deepflow_root), stages_dir, runner_prompt, "pipeline_runner"),
            "cwd": deepflow_root,
            "lightContext": True,
        },
        "plan_summary": {
            "worker_count": len(plan.workers),
            "execution_layers": len(plan.execution_order),
            "total_reqs": sum(len(w.covered_req_ids) for w in plan.workers),
            "rationale": plan.rationale[:200],
        },
    }


# ============================================================================
# Orchestrator prompt 构建
# ============================================================================

def _build_orchestrator_prompt(
    project_name: str,
    project_blackboard: str,
    ship_pro_dir: str,
    deepflow_root: str,
    input_summary: dict,
) -> str:
    """构建 Orchestrator 的完整执行指令"""

    return f"""你是 Ship Pro Orchestrator - 管线的全权调度者。

> 引用共享规则：read core/prompts/_shared_subagent_rules.md

## 项目信息
- 项目: {project_name}
- 统一 Blackboard: {project_blackboard}
- Ship Pro 目录: {ship_pro_dir}
- DeepFlow Root: {deepflow_root}
- 需求数: {input_summary['req_count']}
- 架构决策数: {input_summary['decision_count']}
- 风险缓解数: {input_summary['risk_count']}

## 你的职责
你是唯一负责执行 Ship Pro 管线的 Agent。Main Agent 只启动你,后续不再介入。
你必须自主完成所有步骤,遇到问题自行诊断和修复。

## 🔴 CRITICAL: 显式工具调用规则

你**必须**通过实际的 tool call 执行所有操作。在 thinking 中描述意图不等于执行。

**❌ 错误模式（你的本能）：**
- thinking: "Let me read the file" → 不产出 tool call → 平台隐式执行 → 不可靠
- thinking: "Must end turn now" + text: "Ending turn..." → 不产出 tool call → session 可能终止

**✅ 正确模式（你必须做的）：**
- thinking: "我需要读取文件" → 产出 `read(path=...)` tool call
- spawn Workers 后 → 结束当前 turn（cron 会自动唤醒继续）

## 🔴🔴🔴 铁律（违反 = 管线中断）

1. **每次 assistant turn 必须产出至少一个 tool call** — thinking + text 但没有 tool call = session 终止。
2. **spawn 子 Agent 后，结束当前 turn（cron 会自动唤醒继续）。**
3. **禁止在 thinking 中描述操作而不调用工具。**
4. **禁止只输出"waiting for..."而不结束当前 turn。**
5. 被唤醒后，必须输出可见文字。
6. 不要 read() Worker task 文件。

## 工具调用格式示例

以下是你每次 turn 必须产出的格式。自然语言描述 ≠ 执行。

**读取文件:**
```
thinking: "我需要验证 final_solution.json"
→ 产出 tool call: exec(command="python3 -c \"...\"")
```

**启动子 Agent:**
```
thinking: "spawn Workers"
→ 产出 tool call: sessions_spawn(runtime="subagent", mode="run", task="...")
```

**等待子 Agent 完成:**
```
thinking: "等待 Workers 完成"
→ 结束当前 turn（cron 会自动唤醒继续）
```

## 示例：spawn Workers + 结束 turn 的正确流程

以下是你在 Step 3 中必须执行的正确流程：

```
Turn 1: spawn Layer 1 Workers
  → tool call: sessions_spawn(task=..., label="worker_core_scanner", ...)
  → tool call: sessions_spawn(task=..., label="worker_models", ...)
  → 结束当前 turn（cron 会自动唤醒继续）

[平台休眠，等待 Workers 完成]

Turn 2: Layer 1 完成事件到达，你被唤醒
  → text: "Layer 1 完成。继续 Layer 2。"
  → tool call: sessions_spawn(task=..., label="worker_validation_engine", ...)
  → 结束当前 turn（cron 会自动唤醒继续）

[继续直到所有 Layers 完成]
```

注意：spawn 后结束 turn，cron 会自动唤醒继续。

## 执行步骤

## 🔴 exec 错误处理规则

每个 exec 命令执行后，**必须检查输出**：
- 输出包含 `OK` / `PASS` / 正常 JSON → 继续下一步
- 输出包含 `MISSING` / `Error` / `Traceback` → **停止，不要跳到下一步**
  - 如果错误是 `FileNotFoundError` → 回退到产出该文件的 Step 重新执行
  - 如果错误是 `ValueError` / `ValidationError` → 输出错误详情，尝试修复输入数据后重试
  - 如果错误是 `ImportError` / `ModuleNotFoundError` → 输出错误详情，无法自行修复
- exec 返回非零 exit code → 视同错误输出，不要忽略

### Step 0: 数据契约验证 + 语义提取（AI Native 架构）

**设计原则**: 代码只做 I/O + Schema 验证，LLM 做语义理解。final_solution.json 是唯一数据源，MD 是人类可读副本。

**检查**: exec 验证 final_solution.json 是否存在且包含必需字段:

```python
exec: python3 -c "
import json, sys
from pathlib import Path
p = Path('{project_blackboard}/stages/final_solution.json')
if not p.exists():
    print('MISSING'); sys.exit(1)
d = json.loads(p.read_text())
required = ['key_decisions', 'implementation_phases', 'covered_req_ids', 'constraint_coverage', 'semantic_anchors']
missing = [f for f in required if not d.get(f)]
if missing:
    print(f'INCOMPLETE: missing {{missing}}'); sys.exit(1)
print(f'OK: {{len(d.get("key_decisions",[]))}} decisions, {{len(d.get("covered_req_ids",[]))}} reqs, {{len(d.get("risk_summary",[]))}} risks')
"
```

**如果 OK** → 直接进入 Step 1。

**如果 MISSING 或 INCOMPLETE** → 执行语义提取：

1. read {project_blackboard}/stages/final_solution.md
2. read {project_blackboard}/data/frozen_spec.json
3. **用你的语义理解能力**，从 MD + frozen_spec 中提取结构化数据，写入 final_solution.json
4. 必须产出的字段（字段名固定，不能自创）：
   - `key_decisions`: list of {{"decision": str, "rationale": str}}
   - `implementation_phases`: list of {{"phase": str, "description": str, "duration": str}}
   - `risk_summary`: list of {{"risk": str, "impact": str, "mitigation": str}}
   - `constraint_coverage`: {{"total": N, "covered": N, "ratio": 0-1, "details": [...]}}
   - `covered_req_ids`: list of REQ-ID strings
   - `semantic_anchors`: list of {{"name": str, "category": str, "constraint": str}}
   - `full_solution`: MD 文本（完整方案文档内容）
5. write 到 {project_blackboard}/stages/final_solution.json
6. 重新执行上面的验证脚本，确认 OK

**禁止**：
- ❌ 用正则/字符串匹配提取字段（这是代码的活，不是你的）
- ❌ 跳过字段（缺一个 = 下游 raise）
- ❌ 自创字段名（必须用上面的固定字段名）

### Step 1: PipelineDesigner(设计 Worker 拆分)

exec: python3 -c "
import sys, json; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro import design_pipeline
result = design_pipeline('{ship_pro_dir}/stages/solution_pro_input.json', blackboard_base_dir='{ship_pro_dir}', auto=True, plan_output_dir='{ship_pro_dir}/stages')
print(json.dumps({{'mode': result.get('mode', 'prompt'), 'plan_written': result.get('plan_written', False), 'input_summary': result.get('input_summary', {{}})}}))
"

**检查结果**:
- `plan_written=True` → plan 已自动写入 `{ship_pro_dir}/stages/pipeline_plan.json`，直接进入 Step 2。
- `mode=prompt` → auto 设计失败。read `{ship_pro_dir}/stages/solution_pro_input.json`，按交付物模块拆分 Workers(4-6 个)，将 PipelinePlan JSON write 到 `{ship_pro_dir}/stages/pipeline_plan.json`。

### Step 2: prepare_runner_spawn(生成 Worker prompts)

**前置条件检查**: exec python3 -c "from pathlib import Path; p=Path('{ship_pro_dir}/stages/pipeline_plan.json'); print('OK' if p.exists() else f'MISSING: {{p}}')"
如果 MISSING → 回退 Step 1 的 prompt 模式。

exec: python3 -c "
import sys, json; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro import prepare_runner_spawn
plan = open('{ship_pro_dir}/stages/pipeline_plan.json').read()
sol = json.loads(open('{ship_pro_dir}/stages/solution_pro_input.json').read())
result = prepare_runner_spawn('{ship_pro_dir}', plan, sol, deepflow_root='{deepflow_root}')
print(json.dumps(result['plan_summary']))
"

### Step 3: spawn Workers(分层并行)

**前置条件检查**: exec python3 -c "from pathlib import Path; p=Path('{ship_pro_dir}/stages/_worker_spawn_params.json'); print('OK' if p.exists() else f'MISSING: {{p}}')"
如果 MISSING → 回退 Step 2。

1. exec: python3 -c "
import json
params = json.loads(open('{ship_pro_dir}/stages/_worker_spawn_params.json').read())
for p in params:
    print(f'{{p[\"label\"]}}: task={{len(p[\"task\"])}}c')
"

2. 按 execution_order 分层 spawn Workers(每层内并行)
3. **spawn 后结束当前 turn** 等待每层完成（cron 会自动唤醒继续）
4. 检查 Worker 输出文件存在

### Step 4: L1 验证

**前置条件检查**: exec python3 -c "import glob; files=glob.glob('{ship_pro_dir}/stages/worker_outputs/worker_*.json'); print(f'OK: {{len(files)}} workers' if files else 'MISSING: no worker outputs')"
如果 MISSING → 回退 Step 3。

exec: python3 -c "
import sys; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
result = orch.validate_all_worker_outputs_l1('{ship_pro_dir}')
import json; print(json.dumps(result))
"

FAIL → 输出失败详情,不 retry。

### Step 4.5: Worker MUST Judge(L2 语义验证)

L1 通过后,对每个有 MUST 约束的 Worker 执行语义验证。

**Phase A: 准备 + Spawn Judge Agents**

exec: python3 -c "
import sys, json; sys.path.insert(0, '{deepflow_root}')
from pathlib import Path
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
planner_path = Path('{ship_pro_dir}/stages/pipeline_plan.json')
planner = json.loads(planner_path.read_text()) if planner_path.exists() else None
worker_outputs = orch.collect_worker_outputs_from_blackboard('{ship_pro_dir}')
tasks = orch.prepare_worker_judge_tasks(planner or {{}}, worker_outputs)
Path('{ship_pro_dir}/stages/_worker_judge_tasks.json').write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
print(json.dumps({{'task_count': len(tasks), 'names': [t['name'] for t in tasks]}}))
"

如果 task_count > 0，并行 spawn 所有 Worker Judge Agent。**spawn 后结束当前 turn** 等待完成（cron 会自动唤醒继续）。

**Phase B: 检查结果**

Judge 完成后 exec:
```python
exec: python3 -c "
import sys, json; sys.path.insert(0, '{deepflow_root}')
from pathlib import Path
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
judge_results_path = Path('{ship_pro_dir}/stages/worker_judge_results.json')
judge_results = json.loads(judge_results_path.read_text()) if judge_results_path.exists() else {{}}
planner_path = Path('{ship_pro_dir}/stages/pipeline_plan.json')
planner = json.loads(planner_path.read_text()) if planner_path.exists() else {{}}
failures = orch.analyze_worker_must_failures(judge_results, planner)
print(json.dumps({{'total': len(judge_results), 'passed': len(judge_results) - len(failures), 'failed': [f['role'] for f in failures]}}))
"

- 全部 PASS → 进入 Step 5。
- 有 FAIL → 标记为 CONDITIONAL（在最终报告中注明），继续 Step 5。不 retry。

### Step 5: Consolidator

**前置条件检查**: exec python3 -c "from pathlib import Path; p=Path('{ship_pro_dir}/stages/ship_package.json'); print('ALREADY_EXISTS' if p.exists() else 'NEED_CONSOLIDATOR')"

exec: python3 -c "
import sys; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
params = orch.prepare_consolidator_spawn_v8('{ship_pro_dir}')
import json; print(json.dumps({{'task_len': len(params['task'])}}))
"

spawn Consolidator → **结束当前 turn** 等待完成（cron 会自动唤醒继续）。

### Step 5.5: L2/L3 语义验证(契约笼子强制)

在 Consolidator 产出 ship_package 后,**必须**执行语义验证。这不是可选的。

**Phase A: 准备 Judge Tasks**

exec: python3 -c "
import sys, json, os; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
_sol_path = '{ship_pro_dir}/stages/solution_pro_input.json'
_sp_path = '{ship_pro_dir}/stages/ship_package.json'
if not os.path.exists(_sol_path):
    print(json.dumps({{'error': 'solution_pro_input.json not found', 'task_count': 0}})); sys.exit(0)
if not os.path.exists(_sp_path):
    print(json.dumps({{'error': 'ship_package.json not found', 'task_count': 0}})); sys.exit(0)
sol = json.loads(open(_sol_path).read())
sp = json.loads(open(_sp_path).read())
from pathlib import Path as _Path
_planner_path = _Path('{ship_pro_dir}/stages/pipeline_plan.json')
planner = json.loads(_planner_path.read_text()) if _planner_path.exists() else None
tasks = orch.prepare_gate_judge_tasks(sol, sp, planner)
open('{ship_pro_dir}/stages/_gate_judge_tasks.json', 'w').write(json.dumps(tasks, ensure_ascii=False, indent=2))
print(json.dumps({{'task_count': len(tasks), 'names': [t['name'] for t in tasks]}}))
"

**Phase B: Spawn Judge Agent**

用 sessions_spawn 启动 Judge Agent,task 内容:
```
读取 {{ship_pro_dir}}/stages/_gate_judge_tasks.json,逐个执行验证。
每个 task 包含 name、prompt、expected_output。
对每个 task,按 prompt 指示检查 ship_package,输出 JSON verdict。
将所有 verdict 写入 {{ship_pro_dir}}/stages/gate_judge_results.json,格式:
{{"info_conservation": {{"passed": true/false, ...}}, "completeness": {{...}}, "harness_v3": {{...}}}}
```

spawn 后 **结束当前 turn** 等待完成（cron 会自动唤醒继续）。

**Phase C: 检查结果 + 重试**

Judge Agent 完成后:
1. read gate_judge_results.json
2. 检查每个 gate 的 passed 字段
3. 如果任一 gate FAIL → 分析 issues,spawn Worker 修复(最多 1 次重试)
4. 重试后仍 FAIL → 标记为 CONDITIONAL,在最终报告中注明
5. 全部 PASS → 继续 Step 6

**不要跳过这步。跳过 = 契约笼子失效 = 下游 Gate hard raise。**

### Step 6: ShipPackage 验证(L1 结构 + L2/L3 语义)

**前置条件检查**: exec python3 -c "from pathlib import Path; p=Path('{ship_pro_dir}/stages/ship_package.json'); print('OK' if p.exists() else f'MISSING: {{p}}')"
如果 MISSING → 回退 Step 5。

**Step 6a: L1 结构验证**

exec: python3 -c "
import sys; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
result = orch.validate_ship_package_v8('{ship_pro_dir}')
import json; print(json.dumps(result))
"

**Step 6b: L2/L3 语义验证(消费 Judge 结果)**

exec: python3 -c "
import sys, json; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
sol = json.loads(open('{ship_pro_dir}/stages/solution_pro_input.json').read())
sp = json.loads(open('{ship_pro_dir}/stages/ship_package.json').read())
from pathlib import Path as _Path
_planner_path = _Path('{ship_pro_dir}/stages/pipeline_plan.json')
planner = json.loads(_planner_path.read_text()) if _planner_path.exists() else None
judge_results = json.loads(_Path('{ship_pro_dir}/stages/gate_judge_results.json').read_text())
result = orch.verify_ship_package(sol, sp, planner, judge_results)
print(json.dumps({{k: {{'passed': v.passed, 'details': str(v.details)[:200]}} for k, v in result.items()}}))
"

### Step 7: 最终报告

输出:
- ShipPackage 路径: {ship_pro_dir}/stages/ship_package.json
- WP 总数 / 总工时 / REQ 覆盖率
- L1 验证结果(Step 6a)
- L2/L3 语义验证结果(Step 6b):各 Gate PASS/FAIL + conservation_rate/score
- CONDITIONAL 项(如有)
- Issues
- Pending REQs

## 禁止行为
- ❌ spawn 子 Agent 后不结束当前 turn — 这会导致 session 终止，管线中断
- ❌ `exec sleep` + `process poll` 轮询等待
- ❌ read() Worker task 文件
- ❌ 跳过 validate 步骤
- ❌ 自行 retry/degrade
- ❌ 修改管线计划
- ❌ 回调 Main Agent(你全权负责)
"""


# ============================================================================
# 内部函数
# ============================================================================

def _build_worker_prompts(
    plan,
    contexts: dict,
    context_paths: dict,
    session_dir: Path,
) -> dict:
    """为每个 Worker 生成 6 段式 prompt"""
    prompts = {}
    for worker in plan.workers:
        ctx = contexts[worker.role]
        ctx_path = context_paths[worker.role]
        # Fix 3: 统一写入路径为 stages/worker_outputs/
        worker_outputs_dir = session_dir / "stages" / "worker_outputs"
        worker_outputs_dir.mkdir(parents=True, exist_ok=True)
        safe_role = worker.role.replace(' ', '_').replace('/', '_')
        output_path = str(worker_outputs_dir / f"worker_{safe_role}.json")

        prompt = _build_single_worker_prompt(worker, ctx, ctx_path, output_path)

        # 2.0.0: 去掉 3KB 限制(现代模型不需要)
        # 但保留 16KB 上限作为安全检查(防止异常膨胀)
        if len(prompt) > 16384:
            raise ValueError(
                f"契约笼子: Worker '{worker.role}' prompt 异常膨胀 ({len(prompt)} bytes > 16KB)"
            )

        prompts[worker.role] = prompt

    return prompts


def _build_single_worker_prompt(worker, ctx, ctx_path: str, output_path: str) -> str:
    """
    构建单个 Worker 的 prompt(2.0.0: 三层注意力结构)

    AI Native 设计原则(基于 LLM U 型注意力曲线):
    - Tier 1(开头 - 高注意力): 角色 + 上游约束(Semantic Anchors)+ 模块概述
    - Tier 2(中间 - 正常注意力): 需求列表 + 架构约束 + 接口契约 + 输出规范
    - Tier 3(结尾 - 高注意力): 护栏(禁止行为)

    关键变化(vs 2.0.0 旧版):
    - 去掉 3KB 限制(现代模型不需要)
    - Semantic Anchors 从 context.json 提取到 prompt 开头
    - 保留 2.0.0 的所有信息(REQ 表格、架构约束、接口契约、完整示例)
    - 结构调整:最重要的信息放开头/结尾高注意力区
    """

    # ====================================================================
    # Tier 1: 核心任务 + 上游约束(开头 - 高注意力区)
    # ====================================================================

    # 契约笼子:从 context.json 提取 semantic_anchors,放到开头
    anchors = ctx.semantic_anchors if hasattr(ctx, 'semantic_anchors') and ctx.semantic_anchors else []
    if anchors:
        anchor_lines = []
        for a in anchors:
            name = a.get("name", "?")
            cat = a.get("category", "?")
            constraint = a.get("constraint", "无约束描述")
            anchor_lines.append(f"- **{name}** [{cat}]: {constraint}")
        anchors_block = "\n".join(anchor_lines)
    else:
        anchors_block = "(本模块无上游 Semantic Anchors)"

    # 领域上下文注入(D1: domain_analysis 消费)
    domain_context = ""
    if hasattr(ctx, 'domain_analysis') and ctx.domain_analysis:
        da = ctx.domain_analysis
        domain = da.get('domain', '未知')
        end_users = da.get('end_users', '未指定')
        deliverable_form = da.get('deliverable_form', '未指定')
        split_dim = da.get('split_dimension', '未指定')
        key_constraints = ', '.join(da.get('key_constraints', [])) if da.get('key_constraints') else '无'
        domain_context = f"""## 领域上下文(来自 Planner 分析)
- **领域**: {domain}
- **最终用户**: {end_users}
- **交付物形态**: {deliverable_form}
- **拆分维度**: {split_dim}
- **关键约束**: {key_constraints}

根据上述领域信息,推断你的产出模式。"""

    tier_1 = f"""你是 {worker.role} 的技术设计师。

## 核心职责
将分配给本模块的需求拆解为可执行的 Work Packages(WP)。你只负责 {worker.role},不负责其他模块。

## 数据流
read("{ctx_path}") → 理解需求 → 设计 WPs → write("{output_path}", WorkerDeliverable JSON object)

{domain_context}

## 上游约束(Semantic Anchors - 不可违反)

以下约束来自 Spec Pro / Solution Pro,每个 WP 必须遵循:
{anchors_block}

每个 WP 必须在 `anchored_to` 字段中列出遵循的 anchor name。空列表 = 未引用任何约束。

## 产出模式(从你的角色和交付物推断)

- 如果你的交付物是**代码文件**(如 .py/.js/.go)→ 产出 WP 描述(做什么、验收标准),不生成代码
- 如果你的交付物是**内容文件**(如 .md/.pdf/.xlsx)→ WP 描述中标注"此 WP 产出内容文件",description 中写明内容大纲和关键要点
- 如果你的交付物是**混合类型** → 代码部分写描述,内容部分写实际内容

| 领域 | 产出应该是 | 示例 |
|------|-----------|------|
| 软件开发 | WP 描述(不写代码) | "实现用户认证模块,包含 JWT..." |
| 投资分析 | WP 描述(含分析框架) | "行业分析:市场规模、增速、竞争格局,数据源≥3..." |
| 内容创作 | WP 描述(含内容大纲) | "引言:2000字,以案例开头,引出核心论点..." |
| 市场调研 | WP 描述(含调研维度) | "目标市场:规模、CR3、增长率,时间跨度≥3年..." |

## 模块概述
{ctx.module_overview}"""

    # ====================================================================
    # Tier 2: 任务详情(中间 - 正常注意力区)
    # ====================================================================

    # 需求列表:保留完整表格
    if len(ctx.module_reqs) <= 10:
        req_lines = []
        for r in ctx.module_reqs:
            rid = r.get("id", "?")
            desc = r.get("description", "无描述")[:50]
            pri = r.get("priority", "P1")
            req_lines.append(f"| {rid} | {desc} | {pri} |")
        req_table = "\n".join(req_lines)
        req_section = f"""| REQ-ID | 描述 | 优先级 |
|--------|------|--------|
{req_table}"""
    else:
        req_ids = ", ".join(r.get("id", "?") for r in ctx.module_reqs)
        req_section = f"""共 {len(ctx.module_reqs)} 个需求(详情见 context.json):
{req_ids}"""

    decisions_text = "\n".join(f"- {d}" for d in ctx.relevant_decisions[:3]) if ctx.relevant_decisions else "无"
    constraints_text = "\n".join(f"- {c}" for c in ctx.extracted_constraints[:3]) if ctx.extracted_constraints else "无"

    # 接口契约:保留完整详情
    contracts = ctx.interface_contracts
    provides = "\n".join(f"- {p}" for p in contracts.get("provides", [])) or "无"
    requires = "\n".join(f"- {r}" for r in contracts.get("requires", [])) or "无"
    downstream = ", ".join(contracts.get("downstream_consumers", [])) or "无"

    # 输出规范:保留完整示例
    example_compact = json.dumps(ctx.output_example, ensure_ascii=False, separators=(',', ':'))
    if len(example_compact) > 400:
        example_compact = example_compact[:400] + "..."

    tier_2 = f"""

## 本模块需求
{req_section}

## 架构约束
{decisions_text}

## 隐含约束
{constraints_text}

## 接口契约
本模块对外暴露:
{provides}

本模块依赖:
{requires}

下游消费者:{downstream}

## 输出规范
write 到 "{output_path}",**WorkerDeliverable JSON object**(不是数组!),格式:
```json
{{
  "worker_role": "{worker.role}",
  "wp_id_prefix": "{worker.wp_id_prefix}",
  "work_packages": [
    {{
      "id": "{worker.wp_id_prefix}-001",
      "title": "...",
      "description": "≥100 字",
      "acceptance_criteria": ["...", "..."],
      "deliverables": ["..."],
      "dependencies": [],
      "anchored_to": ["anchor_name_1"],
      "covered_req_ids": ["REQ-001"],
      "effort_hours": 40
    }}
  ],
  "metadata": {{}},
  "web_search_logs": []
}}
```
每个 WP 要求:
- description ≥ 100 字
- acceptance_criteria ≥ 2 条
- deliverables ≥ 1 项
- anchored_to - 遵循的 anchor name 列表
示例 WP 格式:{example_compact}"""

    # ====================================================================
    # Tier 3: 护栏(结尾 - 高注意力区)
    # ====================================================================

    tier_3 = """

## 可选工具
- **web_search**: 当你的模块涉及前沿技术、最新 API、或不确定的技术选型时,可以用 web_search 查证。不强制,但鼓励在需要时搜索。

## 禁止行为
1. ❌ 产出 Python/JS/任何实际代码 - 只产出 WP JSON
2. ❌ read() 除 context.json 以外的本地文件(web_search 不受此限制)
3. ❌ 创建跨越模块边界的 WP
4. ❌ 写“完成开发”这种无法验收的 AC
5. ❌ 将多个独立功能合并为一个 WP
6. ❌ 忽略上述 Semantic Anchors(每个 WP 必须有 anchored_to 字段)

## MUST 约束强制包含规则

如果 context.json 中包含 must_constraints 列表，你**必须**：
1. 在每个 WP 的 description 中显式包含约束中的**关键术语**（不能只用同义词替代）
2. 在至少 1 个 WP 的 acceptance_criteria 中引用约束的核心要求
3. 自检：确认约束中的每个关键术语在你的输出中至少出现 1 次

❌ 禁止：用通用表述替代约束中的特定术语
✅ 正确：约束说“天使轮+A轮” → 输出中必须出现“天使轮”和“A轮”字样

## 最终用户视角自检(产出完成后必须检查)

1. 最终用户能直接使用我的产出吗?
2. 我的产出与其他 Worker 的产出能无缝组装吗?
3. 我的产出覆盖了分配给本模块的所有需求吗?

## 文件操作安全规则

### edit 工具使用约束
1. **edit 前必须 read**: 在调用 edit 工具之前，**必须**先 read 目标文件的当前内容
2. 原因: 文件可能已被其他 Agent 修改，你记忆中的内容可能已过时
3. ❌ 禁止: 凭记忆中的文件内容构造 oldText
4. ✅ 正确: read 当前内容 → 确认 oldText 精确匹配 → 再 edit

### 中文路径处理
1. shell 命令中的中文路径**必须**用引号包裹
2. ❌ 禁止: `cat blackboard/国产半导体封装材料VC投资框架/data.json`
3. ✅ 正确: `cat "blackboard/国产半导体封装材料VC投资框架/data.json"`
4. 更优: 在 Python 内用 `Path()` 操作路径，避免 shell 编码问题"""

    return f"{tier_1}{tier_2}{tier_3}"


def _build_runner_prompt(session_dir: Path, plan, context_paths: dict, deepflow_root: str) -> str:
    """构建 PipelineRunner prompt(2.0.0 兼容,2.0.0 用 ShipOrchestrator 替代)"""
    worker_count = len(plan.workers)
    layers = len(plan.execution_order)
    layer_desc = "\n".join(
        f"  Layer {i+1}: {', '.join(layer)}"
        for i, layer in enumerate(plan.execution_order)
    )

    return f"""你是 PipelineRunner。你的唯一职责:按已设计好的管线计划机械执行。

## 管线信息
- Blackboard: {session_dir}
- DeepFlow Root: {deepflow_root}
- Worker 数量: {worker_count}
- 执行层数: {layers}

## 执行顺序
{layer_desc}

## spawn params 位置
{session_dir}/stages/_worker_spawn_params.json

## 你的行为(严格顺序)

### Phase 2: Build
1. exec: 读取 spawn params
2. 按层级 spawn Workers(每层内并行)
3. **结束当前 turn** 等待当前层全部完成（cron 会自动唤醒继续）
4. exec L1 验证
5. PASS → 下一层或 Phase 3; FAIL → 输出详情

### Phase 3: Consolidate
1. exec: prepare_consolidator_spawn_v8
2. spawn Consolidator
3. **结束当前 turn** 等待完成（cron 会自动唤醒继续）
4. exec: validate_ship_package
5. 输出 ShipPackage 路径

## 禁止行为
- ❌ spawn 后不结束当前 turn
- ❌ read() Worker task 文件
- ❌ 跳过 validate
- ❌ 自行 retry/degrade
- ❌ 修改管线计划"""


# ============================================================================
# Re-exports
# ============================================================================

from .orchestrator.ship_orchestrator import extract_json_from_completion, build_ship_pro_input

__all__ = [
    "run_ship_pro",           # 2.0.0 唯一入口
    "design_pipeline",        # 2.0.0 兼容
    "prepare_runner_spawn",   # 2.0.0 兼容
    "extract_json_from_completion",
    "build_ship_pro_input",
]
