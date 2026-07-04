"""
Ship Pro V8.2 - 入口模块

架构（V8.2 统一 blackboard + 单入口 Dispatcher）：
  Main Agent (depth-0)
    → exec: result = run_ship_pro(project_name=...)
    → sessions_spawn(**result["spawn_params"])
    → 等待完成事件 → 拿到 ShipPackage

  Orchestrator (depth-1, 全权调度)
    → 读取统一 blackboard 中的 Solution Pro 输出
    → exec: design_pipeline() → Designer prompt
    → spawn: Designer LLM → PipelinePlan
    → exec: prepare_runner_spawn() → Worker prompts
    → spawn: Workers (并行/分层, 用 cron wake 不用 sessions_yield)
    → exec: L1 validation
    → spawn: Consolidator
    → exec: ShipPackage validation
    → 输出最终报告

统一 blackboard 结构：
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
    从统一 blackboard 自动发现 Solution Pro 输出
    
    查找路径：
    1. data/frozen_spec.json — 结构化需求/约束（必需）
    2. data/supplemental.json — 补充字段（可选，key_decisions 等）
    
    Note: stages/solution_document.json 是 markdown 文本（方案文档），
          不是结构化 JSON，不用于程序化提取。
    
    Returns:
        合并后的 Solution Pro 输出 dict
    
    Raises:
        FileNotFoundError: 找不到 frozen_spec.json
    """
    from .orchestrator.ship_orchestrator import build_ship_pro_input
    
    frozen_spec = project_blackboard / "data" / "frozen_spec.json"
    supplemental = project_blackboard / "data" / "supplemental.json"
    
    if not frozen_spec.exists():
        raise FileNotFoundError(
            f"统一 blackboard 中找不到 frozen_spec.json: {project_blackboard}\n"
            f"  期望: data/frozen_spec.json（Solution Pro 必需输出）"
        )
    
    # 用 build_ship_pro_input 合并（frozen_spec + 可选补充字段）
    merged = build_ship_pro_input(
        str(frozen_spec),
        str(supplemental) if supplemental.exists() else None,
    )
    return merged


def _get_ship_pro_dir(project_blackboard: Path) -> Path:
    """获取 Ship Pro 在统一 blackboard 中的目录"""
    ship_dir = project_blackboard / "ship_pro"
    ship_dir.mkdir(parents=True, exist_ok=True)
    (ship_dir / "stages").mkdir(exist_ok=True)
    return ship_dir


# ============================================================================
# V8.2 单入口
# ============================================================================

def run_ship_pro(project_name: str, **kwargs) -> dict:
    """
    Ship Pro V8.2 唯一入口 — Main Agent 只调这一个函数
    
    1. 定位统一 blackboard: .deepflow/blackboard/{project_name}/
    2. 自动发现 Solution Pro 输出
    3. 构建 Orchestrator spawn params
    4. 返回 spawn_params — Main Agent 只需 sessions_spawn(**result["spawn_params"])
    
    Args:
        project_name: 项目名称（blackboard 目录名）
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
    
    # 保存合并输入
    input_path = ship_dir / "solution_pro_input.json"
    input_path.write_text(json.dumps(sol_input, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 4. 构建 Orchestrator prompt
    deepflow_root = str(DEEPFLOW_ROOT)
    dispatcher_prompt = _build_orchestrator_prompt(
        project_name=project_name,
        project_blackboard=str(project_bb),
        ship_pro_dir=str(ship_dir),
        deepflow_root=deepflow_root,
        input_summary={
            "req_count": len(sol_input.get("requirements", [])),
            "decision_count": len(sol_input.get("key_decisions", [])),
            "risk_count": len(sol_input.get("risk_mitigations", [])),
        },
    )
    
    # 5. 返回 spawn params
    return {
        "project_name": project_name,
        "project_blackboard": str(project_bb),
        "ship_pro_dir": str(ship_dir),
        "input_summary": {
            "req_count": len(sol_input.get("requirements", [])),
            "decision_count": len(sol_input.get("key_decisions", [])),
            "risk_count": len(sol_input.get("risk_mitigations", [])),
        },
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "ship_pro_orchestrator",
            "task": dispatcher_prompt,
            "cwd": deepflow_root,
            "lightContext": True,
        },
    }


# ============================================================================
# V8 兼容入口（保留，但推荐用 run_ship_pro）
# ============================================================================

def design_pipeline(solution_pro_output_path: str, **kwargs) -> dict:
    """V8 兼容入口 — 推荐用 run_ship_pro()"""
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
    dest_input = session_dir / "solution_pro_input.json"
    shutil.copy2(str(input_path), str(dest_input))

    designer = PipelineDesigner(blackboard_path=session_dir)
    designer_result = designer.design_pipeline(solution_pro_input, auto=kwargs.get("auto", False))

    deepflow_root = str(DEEPFLOW_ROOT)

    # 双模式处理（契约笼子：确定性分支，不依赖 prompt 指令）
    if designer_result.get("mode") == "auto":
        # Auto mode: plan 已生成，直接保存
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
    """V8 兼容入口 — 推荐用 run_ship_pro()"""
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

    worker_spawn_params = []
    for role, prompt in worker_prompts.items():
        params = {
            "runtime": "subagent",
            "mode": "run",
            "label": re.sub(r'[^a-z0-9_-]', '_', f"worker_{role}".lower()),
            "task": prompt,
            "lightContext": True,
        }
        worker_spawn_params.append(params)

    spawn_params_path = session_dir / "stages" / "_worker_spawn_params.json"
    spawn_params_path.write_text(
        json.dumps(worker_spawn_params, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    deepflow_root = kwargs.get("deepflow_root", str(DEEPFLOW_ROOT))
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
            "task": runner_prompt,
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
    
    return f"""你是 Ship Pro Orchestrator — 管线的全权调度者。

## 项目信息
- 项目: {project_name}
- 统一 Blackboard: {project_blackboard}
- Ship Pro 目录: {ship_pro_dir}
- DeepFlow Root: {deepflow_root}
- 需求数: {input_summary['req_count']}
- 架构决策数: {input_summary['decision_count']}
- 风险缓解数: {input_summary['risk_count']}

## 你的职责
你是唯一负责执行 Ship Pro 管线的 Agent。Main Agent 只启动你，后续不再介入。
你必须自主完成所有步骤，遇到问题自行诊断和修复。

## 铁律
- **禁止 sessions_yield()** — 用 cron(action="wake", mode="next-heartbeat") 替代
- 每次 wake 必须输出可见文字（哪怕只是"仍在运行..."）
- 不要 read() Worker task 文件（spawn params 里已有完整 task）

## 执行步骤

### Step 1: PipelineDesigner（设计 Worker 拆分）

exec: python3 -c "
import sys; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro import design_pipeline
result = design_pipeline('{ship_pro_dir}/solution_pro_input.json', blackboard_base_dir='{ship_pro_dir}', auto=True)
import json; print(json.dumps({{'mode': result.get('mode', 'prompt'), 'has_plan': 'plan' in result, 'input_summary': result['input_summary']}}))
"

**双模式处理（契约笼子：检查 mode 字段决定行为）**：

A. `mode=auto`（design_pipeline 已自动调用 LLM 生成 plan）：
   - 直接执行: exec python3 -c "import json; from domains.ship_pro import design_pipeline; r = design_pipeline('{ship_pro_dir}/solution_pro_input.json', blackboard_base_dir='{ship_pro_dir}', auto=True); open('{ship_pro_dir}/stages/pipeline_plan.json','w').write(json.dumps(r['plan'], ensure_ascii=False, indent=2))"
   - 不要 read solution_pro_input.json（已在 Python 内部处理）

B. `mode=prompt`（自动设计失败，回退到 LLM 手动分析）：
   - read {ship_pro_dir}/solution_pro_input.json
   - 按交付物模块（代码内聚性）拆分 Workers（4-6 个）
   - 将 PipelinePlan JSON write 到 {ship_pro_dir}/stages/pipeline_plan.json

PipelinePlan 格式：
```json
{{
  "workers": [
    {{
      "role": "模块名",
      "module_purpose": "模块目的（≥20字）",
      "covered_req_ids": ["REQ-001", ...],
      "depends_on": [],
      "interface_provides": ["method(param) → return"],
      "interface_requires": [],
      "relevant_decisions": ["D1: ..."],
      "relevant_risks": ["RISK-1: ..."],
      "estimated_wps": 5,
      "estimated_effort_hours": 40
    }}
  ],
  "execution_order": [["基础层"], ["并行层1", "并行层2"], ["上层"]],
  "rationale": "拆分理由（≥50字）"
}}
```

约束：每个 REQ-ID 只能分配给一个 Worker。

### Step 2: prepare_runner_spawn（生成 Worker prompts）

exec: python3 -c "
import sys, json; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro import prepare_runner_spawn
plan = open('{ship_pro_dir}/stages/pipeline_plan.json').read()
sol = json.loads(open('{ship_pro_dir}/solution_pro_input.json').read())
result = prepare_runner_spawn('{ship_pro_dir}', plan, sol, deepflow_root='{deepflow_root}')
print(json.dumps(result['plan_summary']))
"

### Step 3: spawn Workers（分层并行）

1. exec: python3 -c "
import json
params = json.loads(open('{ship_pro_dir}/stages/_worker_spawn_params.json').read())
for p in params:
    print(f'{{p[\"label\"]}}: task={{len(p[\"task\"])}}c')
"

2. 按 execution_order 分层 spawn Workers（每层内并行）
3. 用 cron wake 等待每层完成
4. 检查 Worker 输出文件存在

### Step 4: L1 验证

exec: python3 -c "
import sys; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
result = orch.validate_all_worker_outputs_l1('{ship_pro_dir}')
import json; print(json.dumps(result))
"

FAIL → 输出失败详情，不 retry。

### Step 5: Consolidator

exec: python3 -c "
import sys; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
params = orch.prepare_consolidator_spawn_v8('{ship_pro_dir}')
import json; print(json.dumps({{'task_len': len(params['task'])}}))
"

spawn Consolidator → cron wake 等待完成。

### Step 6: ShipPackage 验证

exec: python3 -c "
import sys; sys.path.insert(0, '{deepflow_root}')
from domains.ship_pro.orchestrator.ship_orchestrator import ShipOrchestrator
orch = ShipOrchestrator('{ship_pro_dir}')
result = orch.validate_ship_package_v8('{ship_pro_dir}')
import json; print(json.dumps(result))
"

### Step 7: 最终报告

输出：
- ShipPackage 路径: {ship_pro_dir}/stages/ship_package.json
- WP 总数 / 总工时 / REQ 覆盖率
- L1 验证结果
- Issues
- Pending REQs

## 禁止行为
- ❌ sessions_yield()（用 cron wake）
- ❌ `exec sleep` + `process poll` 轮询等待（用 `cron wake` 每 30s 检查文件存在）
- ❌ read() Worker task 文件
- ❌ 跳过 validate 步骤
- ❌ 自行 retry/degrade
- ❌ 修改管线计划
- ❌ 回调 Main Agent（你全权负责）
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
        output_path = str(session_dir / "stages" / f"worker_{worker.role.replace(' ', '_')}.json")

        prompt = _build_single_worker_prompt(worker, ctx, ctx_path, output_path)

        if len(prompt) > 3072:
            raise ValueError(
                f"契约笼子: Worker '{worker.role}' prompt 超过 3KB ({len(prompt)} bytes)"
            )

        prompts[worker.role] = prompt

    return prompts


def _build_single_worker_prompt(worker, ctx, ctx_path: str, output_path: str) -> str:
    """构建单个 Worker 的 6 段式 prompt"""

    section_1 = f"""你是 {worker.role} 的技术设计师。

## 你的职责
将分配给本模块的需求拆解为可执行的 Work Packages（WP）。你只负责 {worker.role}，不负责其他模块。

## 数据流
read("{ctx_path}") → 理解需求 → 设计 WPs → write("{output_path}", JSON 数组)

## 关键约束
只输出 WP JSON 描述，不写实际代码。"""

    section_2 = f"""
## 模块概述
{ctx.module_overview}"""

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
        req_section = f"""共 {len(ctx.module_reqs)} 个需求（详情见 context.json）：
{req_ids}"""

    decisions_text = "\n".join(f"- {d}" for d in ctx.relevant_decisions[:3]) if ctx.relevant_decisions else "无"
    constraints_text = "\n".join(f"- {c}" for c in ctx.extracted_constraints[:3]) if ctx.extracted_constraints else "无"

    section_3 = f"""
## 本模块需求
{req_section}

## 架构约束
{decisions_text}

## 隐含约束
{constraints_text}"""

    contracts = ctx.interface_contracts
    provides = "\n".join(f"- {p}" for p in contracts.get("provides", [])) or "无"
    requires = "\n".join(f"- {r}" for r in contracts.get("requires", [])) or "无"
    downstream = ", ".join(contracts.get("downstream_consumers", [])) or "无"

    section_4 = f"""
## 接口契约
本模块对外暴露：
{provides}

本模块依赖：
{requires}

下游消费者：{downstream}"""

    example_compact = json.dumps(ctx.output_example, ensure_ascii=False, separators=(',', ':'))
    if len(example_compact) > 400:
        example_compact = example_compact[:400] + "..."
    section_5 = f"""
## 输出规范
write 到 "{output_path}"，JSON 数组，每个 WP：
- description ≥ 100 字
- acceptance_criteria ≥ 2 条
- deliverables ≥ 1 项
示例格式：{example_compact}"""

    section_6 = """
## 禁止行为
1. ❌ 产出 Python/JS/任何实际代码 — 只产出 WP JSON
2. ❌ read() 除 context.json 以外的任何文件
3. ❌ 创建跨越模块边界的 WP
4. ❌ 写"完成开发"这种无法验收的 AC
5. ❌ 将多个独立功能合并为一个 WP"""

    return f"{section_1}{section_2}{section_3}{section_4}{section_5}{section_6}"


def _build_runner_prompt(session_dir: Path, plan, context_paths: dict, deepflow_root: str) -> str:
    """构建 PipelineRunner prompt（V8 兼容，V8.2 用 Dispatcher 替代）"""
    worker_count = len(plan.workers)
    layers = len(plan.execution_order)
    layer_desc = "\n".join(
        f"  Layer {i+1}: {', '.join(layer)}"
        for i, layer in enumerate(plan.execution_order)
    )

    return f"""你是 PipelineRunner。你的唯一职责：按已设计好的管线计划机械执行。

## 管线信息
- Blackboard: {session_dir}
- DeepFlow Root: {deepflow_root}
- Worker 数量: {worker_count}
- 执行层数: {layers}

## 执行顺序
{layer_desc}

## spawn params 位置
{session_dir}/stages/_worker_spawn_params.json

## 你的行为（严格顺序）

### Phase 2: Build
1. exec: 读取 spawn params
2. 按层级 spawn Workers（每层内并行）
3. cron wake 等待当前层全部完成（禁止 sessions_yield）
4. exec L1 验证
5. PASS → 下一层或 Phase 3; FAIL → 输出详情

### Phase 3: Consolidate
1. exec: prepare_consolidator_spawn_v8
2. spawn Consolidator
3. cron wake 等待完成
4. exec: validate_ship_package
5. 输出 ShipPackage 路径

## 禁止行为
- ❌ sessions_yield()
- ❌ read() Worker task 文件
- ❌ 跳过 validate
- ❌ 自行 retry/degrade
- ❌ 修改管线计划"""


# ============================================================================
# Re-exports
# ============================================================================

from .orchestrator.ship_orchestrator import extract_json_from_completion, build_ship_pro_input

__all__ = [
    "run_ship_pro",           # V8.2 唯一入口
    "design_pipeline",        # V8 兼容
    "prepare_runner_spawn",   # V8 兼容
    "extract_json_from_completion",
    "build_ship_pro_input",
]
