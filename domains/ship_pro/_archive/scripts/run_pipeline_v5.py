#!/usr/bin/env python3
# ---
# id: ship_pro/run_pipeline_v5
# version: "5.0.0"
# component: ship_pro_v5
# updated: "2026-06-28"
# status: active
# ---
"""
Ship Pro V5.0 — 双 Phase 多 Agent 管线 CLI

Phase 1 (Blueprint): Parser → Explorer → Architect(2步) → 3 Critic(并行) → Consolidator
Phase 2 (Delivery):  AC Writer → 确定性代码 → 3 Judge(并行) → Consolidator

CLI:
    python3 run_pipeline_v5.py prepare <input_path> <output_dir>
    python3 run_pipeline_v5.py task <agent_name> <output_dir>
    python3 run_pipeline_v5.py gate <agent_name> <output_dir>
    python3 run_pipeline_v5.py run-code <module_name> <output_dir>
    python3 run_pipeline_v5.py next <output_dir>
    python3 run_pipeline_v5.py fix-context <output_dir> [--phase 1|2]
    python3 run_pipeline_v5.py validate <output_dir>
    python3 run_pipeline_v5.py status <output_dir>
    python3 run_pipeline_v5.py finalize <output_dir> <pass|fail>
    python3 run_pipeline_v5.py increment-retry <output_dir> <agent_name>
"""

import json
import sys
import os
import hashlib
import fcntl
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Auto-discover .deepflow root
# ---------------------------------------------------------------------------
_dp = next(
    (d for d in Path(__file__).resolve().parents if (d / "core" / "blackboard").is_dir()),
    None,
)
if _dp and str(_dp) not in sys.path:
    sys.path.insert(0, str(_dp))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ROUNDS = 3
MAX_GATE_RETRIES = 2

# V5 Prompt 目录（相对于 ship_pro 域）
PROMPT_DIR_NAME = "v5/prompts"

# 确定性代码模块
CODE_MODULES = ["propagator", "depgraph", "numeric_checker"]

# ---------------------------------------------------------------------------
# Agent Registry — 声明式配置
# ---------------------------------------------------------------------------

AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ── Phase 1: Blueprint ──
    "p1_parser": {
        "prompt_file": "p1_parser.md",
        "phase": 1,
        "deps": [],               # 无上游依赖（消费原始输入）
        "output": "p1_parser.json",
        "parallel_group": None,
        "timeout": 120,
    },
    "p1_explorer": {
        "prompt_file": "p1_explorer.md",
        "phase": 1,
        "deps": ["p1_parser"],
        "output": "p1_explorer.json",
        "parallel_group": None,
        "timeout": 180,
    },
    "p1_architect_step1": {
        "prompt_file": "p1_architect_step1.md",
        "phase": 1,
        "deps": ["p1_parser", "p1_explorer"],
        "output": "p1_architect_step1.json",
        "parallel_group": None,
        "timeout": 300,
    },
    "p1_architect_step2": {
        "prompt_file": "p1_architect_step2.md",
        "phase": 1,
        "deps": ["p1_architect_step1"],
        "output": "p1_architect_step2.json",
        "parallel_group": None,
        "timeout": 300,
    },
    "p1_coverage_critic": {
        "prompt_file": "p1_coverage_critic.md",
        "phase": 1,
        "deps": ["p1_architect_step2"],  # 实际是 architect 的合并输出
        "output": "p1_coverage_critic.json",
        "parallel_group": "p1_critics",
        "timeout": 180,
    },
    "p1_granularity_critic": {
        "prompt_file": "p1_granularity_critic.md",
        "phase": 1,
        "deps": ["p1_architect_step2"],
        "output": "p1_granularity_critic.json",
        "parallel_group": "p1_critics",
        "timeout": 180,
    },
    "p1_feasibility_critic": {
        "prompt_file": "p1_feasibility_critic.md",
        "phase": 1,
        "deps": ["p1_architect_step2"],
        "output": "p1_feasibility_critic.json",
        "parallel_group": "p1_critics",
        "timeout": 180,
    },
    "p1_consolidator": {
        "prompt_file": "p1_consolidator.md",
        "phase": 1,
        "deps": ["p1_coverage_critic", "p1_granularity_critic", "p1_feasibility_critic"],
        "output": "p1_consolidator.json",
        "parallel_group": None,
        "timeout": 300,
    },
    # ── Phase 2: Delivery ──
    "p2_ac_writer": {
        "prompt_file": "p2_ac_writer.md",
        "phase": 2,
        "deps": ["p1_consolidator", "p1_parser"],  # Phase 1 Blueprint + 原始解析结果（含平台约束）
        "output": "p2_ac_writer.json",
        "parallel_group": None,
        "timeout": 300,
    },
    "p2_consistency_judge": {
        "prompt_file": "p2_consistency_judge.md",
        "phase": 2,
        "deps": ["p2_ac_writer"],   # + propagator/depgraph 的确定性输出
        "output": "p2_consistency_judge.json",
        "parallel_group": "p2_judges",
        "timeout": 180,
    },
    "p2_quality_judge": {
        "prompt_file": "p2_quality_judge.md",
        "phase": 2,
        "deps": ["p2_ac_writer"],
        "output": "p2_quality_judge.json",
        "parallel_group": "p2_judges",
        "timeout": 180,
    },
    "p2_completeness_judge": {
        "prompt_file": "p2_completeness_judge.md",
        "phase": 2,
        "deps": ["p2_ac_writer"],
        "output": "p2_completeness_judge.json",
        "parallel_group": "p2_judges",
        "timeout": 180,
    },
    "p2_consolidator": {
        "prompt_file": "p2_consolidator.md",
        "phase": 2,
        "deps": ["p2_consistency_judge", "p2_quality_judge", "p2_completeness_judge"],
        "output": "p2_consolidator.json",
        "parallel_group": None,
        "timeout": 300,
    },
}

# Phase 1 agent 顺序（串行 agents 按顺序，并行 agents 一起返回）
PHASE1_ORDER = [
    "p1_parser",
    "p1_explorer",
    "p1_architect_step1",
    "p1_architect_step2",
    ["p1_coverage_critic", "p1_granularity_critic", "p1_feasibility_critic"],
    "p1_consolidator",
]

PHASE2_ORDER = [
    "p2_ac_writer",
    # 确定性代码模块（由 run-code 命令执行，不是 LLM Agent）
    # "code:propagator", "code:depgraph", "code:numeric_checker"
    ["p2_consistency_judge", "p2_quality_judge", "p2_completeness_judge"],
    "p2_consolidator",
]

# Phase → Gate 契约映射
PHASE_GATE = {
    1: {
        "gate_agent": "p1_consolidator",
        "contract": "v5_blueprint",
        "output_name": "blueprint",
    },
    2: {
        "gate_agent": "p2_consolidator",
        "contract": "v5_ship_package",
        "output_name": "ship_package",
    },
}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_status(output_dir: Path) -> dict:
    return _load_json(output_dir / "pipeline_status.json") or {}


def _save_status(output_dir: Path, status: dict) -> None:
    _save_json(output_dir / "pipeline_status.json", status)


def _get_prompt_dir() -> Path:
    """获取 V5 prompt 目录"""
    return Path(__file__).resolve().parent.parent / "v5" / "prompts"


def _load_prompt(agent_name: str) -> str:
    """Load prompt via core.prompt_registry."""
    from core.prompt_registry import read_prompt
    return read_prompt(f"ship_pro/{agent_name}")


def _compute_prompt_sha(agent_name: str) -> str:
    try:
        content = _load_prompt(agent_name)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    except FileNotFoundError:
        return "unknown"


def _read_bb(bb_dir: Path, filename: str) -> Optional[dict]:
    """从 blackboard 读取 agent 输出"""
    path = bb_dir / filename
    return _load_json(path)


def _current_phase(status: dict) -> int:
    """获取当前 phase (1 or 2)"""
    return status.get("current_phase", 1)


def _current_round(status: dict) -> int:
    """获取当前 phase 的 round"""
    phase = _current_phase(status)
    return status.get(f"phase{phase}_round", 1)


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def prepare_pipeline(input_path: str, output_dir: str) -> dict:
    """初始化 V5 管线环境"""
    input_p = Path(input_path)
    output_p = Path(output_dir)

    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_p.mkdir(parents=True, exist_ok=True)
    bb_dir = output_p / "blackboard"
    bb_dir.mkdir(exist_ok=True)

    # 清理旧状态
    stale_files = [
        ".completed", "pipeline_status.json", "pipeline_config.json",
        "fix_context_p1.json", "fix_context_p2.json",
    ]
    for sf in stale_files:
        p = output_p / sf
        if p.exists():
            p.unlink()
        p2 = bb_dir / sf
        if p2.exists():
            p2.unlink()

    # 清理旧 agent 输出
    for agent_name, reg in AGENT_REGISTRY.items():
        p = bb_dir / reg["output"]
        if p.exists():
            p.unlink()
    # 清理确定性代码模块输出
    for mod in CODE_MODULES:
        p = bb_dir / f"code_{mod}.json"
        if p.exists():
            p.unlink()

    # 复制输入
    with open(input_p) as f:
        input_data = json.load(f)
    _save_json(bb_dir / "input.json", input_data)

    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_v5"

    # Pipeline config
    deepflow_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    pipeline_config = {
        "run_id": run_id,
        "version": "5.0.0",
        "input_file": str(input_p.resolve()),
        "blackboard_dir": str(bb_dir.resolve()),
        "output_dir": str(output_p.resolve()),
        "max_rounds": MAX_ROUNDS,
        "deepflow_root": deepflow_root,
        "generated_at": datetime.now().isoformat(),
    }
    _save_json(output_p / "pipeline_config.json", pipeline_config)

    # Initialize status
    status = {
        "run_id": run_id,
        "version": "5.0.0",
        "started_at": datetime.now().isoformat(),
        "current_phase": 1,
        "phase1_round": 1,
        "phase2_round": 1,
        "phase1_state": "running",     # running | gate_check | fix | done | failed
        "phase2_state": "pending",    # pending | running | gate_check | fix | done | failed
        "agents": {},
    }
    # 初始化所有 agent 状态
    for agent_name in AGENT_REGISTRY:
        status["agents"][agent_name] = {"state": "pending", "retry_count": 0}
    # 确定性代码模块状态
    for mod in CODE_MODULES:
        status["agents"][f"code_{mod}"] = {"state": "pending", "retry_count": 0}

    _save_status(output_p, status)

    return pipeline_config


# ---------------------------------------------------------------------------
# task — 构建 Agent prompt
# ---------------------------------------------------------------------------

def get_agent_task(agent_name: str, output_dir: str) -> dict:
    """构建 Agent 的完整 task prompt"""
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    if not config:
        raise FileNotFoundError("Pipeline not prepared. Run 'prepare' first.")

    registry = AGENT_REGISTRY.get(agent_name)
    if not registry:
        raise ValueError(f"Unknown agent: {agent_name}. Available: {list(AGENT_REGISTRY.keys())}")

    bb_dir = Path(config["blackboard_dir"])
    run_id = config["run_id"]
    status = _load_status(output_p)
    phase = registry["phase"]
    current_round = status.get(f"phase{phase}_round", 1)

    # 加载 prompt
    prompt = _load_prompt(agent_name)
    prompt_sha = _compute_prompt_sha(agent_name)

    # 收集上游依赖数据
    dep_data = {}
    for dep_agent in registry["deps"]:
        dep_reg = AGENT_REGISTRY.get(dep_agent)
        if dep_reg:
            dep_output = _read_bb(bb_dir, dep_reg["output"])
            if dep_output:
                dep_data[dep_agent] = dep_output
            else:
                # 也检查 consolidated 输出
                pass

    # 加载原始输入
    input_data = _read_bb(bb_dir, "input.json")

    # 构建 task
    task = _build_task_prompt(
        agent_name=agent_name,
        prompt=prompt,
        input_data=input_data,
        dep_data=dep_data,
        bb_dir=str(bb_dir),
        run_id=run_id,
        prompt_sha=prompt_sha,
        current_round=current_round,
        output_p=output_p,
        registry=registry,
        status=status,
    )

    # 更新状态
    status["agents"][agent_name]["state"] = "running"
    _save_status(output_p, status)

    return {
        "agent": agent_name,
        "task": task,
        "phase": phase,
        "round": current_round,
        "timeout_seconds": registry["timeout"],
        "model": "strong",
        "output_file": f"{bb_dir}/{registry['output']}",
        "parallel_group": registry["parallel_group"],
        "prompt_sha": prompt_sha,
    }


def _build_task_prompt(
    agent_name: str,
    prompt: str,
    input_data: dict,
    dep_data: dict,
    bb_dir: str,
    run_id: str,
    prompt_sha: str,
    current_round: int,
    output_p: Path,
    registry: dict,
    status: dict,
) -> str:
    """构建完整的 worker task prompt"""

    # 上游数据部分
    dep_sections = []
    for dep_agent, data in dep_data.items():
        dep_sections.append(f"""### {dep_agent} 输出

```json
{json.dumps(data, indent=2, ensure_ascii=False)}
```""")

    dep_text = "\n\n".join(dep_sections) if dep_sections else "（无上游 LLM Agent 数据）"

    # 确定性代码模块输出（Phase 2 的 Judge 需要）
    code_data_section = ""
    if registry["phase"] == 2 and agent_name.startswith("p2_"):
        code_outputs = []
        for mod in CODE_MODULES:
            code_out = _read_bb(Path(bb_dir), f"code_{mod}.json")
            if code_out:
                code_outputs.append(f"""### 确定性模块: {mod}

```json
{json.dumps(code_out, indent=2, ensure_ascii=False)}
```""")
        if code_outputs:
            code_data_section = "\n\n## 确定性代码模块输出\n\n" + "\n\n".join(code_outputs)

    # Fix Context（如果 round >= 2）
    fix_context_section = ""
    phase = registry["phase"]
    if current_round >= 2:
        fc_path = output_p / f"fix_context_p{phase}.json"
        fc = _load_json(fc_path)
        if fc:
            fix_context_section = f"""

## ⚠️ 修复上下文 (Round {current_round})

上一轮 Consolidator 裁定 **{fc.get('original_verdict', 'fail')}**，以下是定向修复指令。
**只修复以下问题，不要改动其他部分。**

```json
{json.dumps(fc, indent=2, ensure_ascii=False)}
```

### 修复约束
- focus_areas: {json.dumps(fc.get('focus_areas', []), ensure_ascii=False)}
- regression_warnings: {json.dumps(fc.get('regression_warnings', []), ensure_ascii=False)}
"""

    output_path = f"{bb_dir}/{registry['output']}"

    return f"""## Agent: {agent_name} (V5.0 Phase {phase})

{prompt}

## 原始输入

```json
{json.dumps(input_data, indent=2, ensure_ascii=False)}
```

## 上游 Agent 输出

{dep_text}
{code_data_section}
{fix_context_section}

## 运行信息

- run_id: {run_id}
- phase: {phase}
- round: {current_round}
- agent: {agent_name}
- blackboard_dir: {bb_dir}
- prompt_sha: {prompt_sha}

## ⚠️ 输出文件路径（必须严格遵守）

**输出文件路径**: `{output_path}`

- 文件名必须是 `{registry['output']}`
- 输出必须是合法 JSON
- 不要包含 markdown 代码块标记
- 不要添加解释性文字
"""


# ---------------------------------------------------------------------------
# gate — Pydantic 契约门控
# ---------------------------------------------------------------------------

def check_gate(agent_name: str, output_dir: str) -> dict:
    """对 Agent 输出执行 Pydantic 契约门控"""
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    if not config:
        raise FileNotFoundError("Pipeline not prepared.")

    bb_dir = Path(config["blackboard_dir"])
    registry = AGENT_REGISTRY.get(agent_name)
    if not registry:
        return _gate_fail(agent_name, ["unknown_agent"], f"Unknown agent: {agent_name}")

    output_file = bb_dir / registry["output"]

    # 文件存在性检查
    if not output_file.exists():
        return _gate_fail(agent_name, ["output_missing"],
                          f"Agent output not found: {output_file}")

    # JSON 解析
    try:
        with open(output_file) as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        return _gate_fail(agent_name, ["invalid_json"], f"Invalid JSON: {e}")

    # Phase 特定门控
    phase = registry["phase"]

    if phase == 1:
        result = _gate_phase1(agent_name, raw)
    elif phase == 2:
        result = _gate_phase2(agent_name, raw)
    else:
        result = _gate_basic(agent_name, raw)

    # 更新状态
    status = _load_status(output_p)
    if agent_name in status.get("agents", {}):
        state_map = {"PASS": "gate_pass", "CONDITIONAL": "gate_conditional", "FAIL": "gate_fail"}
        status["agents"][agent_name]["state"] = state_map.get(result["decision"], "gate_fail")
        status["agents"][agent_name]["gate_decision"] = result["decision"]
    _save_status(output_p, status)

    return result


def _gate_phase1(agent_name: str, raw: dict) -> dict:
    """Phase 1 Gate: Blueprint 质量校验"""
    # 使用 V5 的 gate.py
    try:
        v5_dir = Path(__file__).resolve().parent.parent / "v5"
        if str(v5_dir.parent) not in sys.path:
            sys.path.insert(0, str(v5_dir.parent))
        from ship_pro.v5.contracts.gate import gate_blueprint
        passed, issues = gate_blueprint(raw)

        if passed:
            return {
                "agent": agent_name,
                "decision": "PASS",
                "critical_failures": [],
                "feedback": f"Blueprint gate passed: {len(issues)} info/warnings",
                "should_retry": False,
                "issues": issues,
            }
        else:
            blockers = [i for i in issues if i.get("severity") == "blocker"]
            warnings = [i for i in issues if i.get("severity") == "warning"]
            return {
                "agent": agent_name,
                "decision": "FAIL" if blockers else "CONDITIONAL",
                "critical_failures": [i["message"] for i in blockers],
                "feedback": f"Blueprint gate: {len(blockers)} blockers, {len(warnings)} warnings",
                "should_retry": bool(blockers),
                "issues": issues,
            }
    except ImportError:
        return _gate_basic(agent_name, raw)


def _gate_phase2(agent_name: str, raw: dict) -> dict:
    """Phase 2 Gate: Ship Package 质量校验"""
    try:
        v5_dir = Path(__file__).resolve().parent.parent / "v5"
        if str(v5_dir.parent) not in sys.path:
            sys.path.insert(0, str(v5_dir.parent))
        from ship_pro.v5.contracts.gate import gate_ship_package
        passed, issues = gate_ship_package(raw)

        if passed:
            return {
                "agent": agent_name,
                "decision": "PASS",
                "critical_failures": [],
                "feedback": f"Ship Package gate passed",
                "should_retry": False,
                "issues": issues,
            }
        else:
            blockers = [i for i in issues if i.get("severity") == "blocker"]
            return {
                "agent": agent_name,
                "decision": "FAIL" if blockers else "CONDITIONAL",
                "critical_failures": [i["message"] for i in blockers],
                "feedback": f"Ship Package gate: {len(blockers)} blockers",
                "should_retry": bool(blockers),
                "issues": issues,
            }
    except ImportError:
        return _gate_basic(agent_name, raw)


def _gate_basic(agent_name: str, raw: dict) -> dict:
    """基础门控（fallback：检查基本结构）"""
    if not raw:
        return _gate_fail(agent_name, ["empty_output"], "Output is empty")
    if not isinstance(raw, dict):
        return _gate_fail(agent_name, ["not_dict"], "Output is not a dict")
    return {
        "agent": agent_name,
        "decision": "PASS",
        "critical_failures": [],
        "feedback": "Basic gate passed",
        "should_retry": False,
    }


def _gate_fail(agent_name: str, failures: list, feedback: str) -> dict:
    return {
        "agent": agent_name,
        "decision": "FAIL",
        "critical_failures": failures,
        "feedback": feedback,
        "should_retry": True,
    }


# ---------------------------------------------------------------------------
# run-code — 确定性代码模块执行
# ---------------------------------------------------------------------------

def run_code_module(module_name: str, output_dir: str) -> dict:
    """执行确定性代码模块（非 LLM，本地 Python 执行）"""
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    if not config:
        raise FileNotFoundError("Pipeline not prepared.")

    bb_dir = Path(config["blackboard_dir"])

    if module_name == "propagator":
        return _run_propagator(bb_dir)
    elif module_name == "depgraph":
        return _run_depgraph(bb_dir)
    elif module_name == "numeric_checker":
        return _run_numeric_checker(bb_dir)
    else:
        raise ValueError(f"Unknown code module: {module_name}. Available: {CODE_MODULES}")


def _run_propagator(bb_dir: Path) -> dict:
    """约束传播：从 Blueprint 提取约束并传播到 WP"""
    blueprint = _read_bb(bb_dir, "p1_consolidator.json")
    if not blueprint:
        return {"error": "Blueprint not found", "constraints": [], "source": "fallback"}

    try:
        v5_dir = Path(__file__).resolve().parent.parent / "v5"
        sys.path.insert(0, str(v5_dir))
        from code.propagator import propagate_constraints
        result = propagate_constraints(blueprint)
    except ImportError:
        # Fallback: 简单提取
        constraints = []
        # work_package_details 是 WP 对象列表，work_packages 可能只是 ID 列表
        wp_list = blueprint.get("work_package_details") or blueprint.get("work_packages", [])
        for wp in wp_list:
            if not isinstance(wp, dict):
                continue
            for mod_id in wp.get("source_modules", []):
                constraints.append({
                    "wp_id": wp.get("id"),
                    "module_id": mod_id,
                    "constraint": f"Must implement {mod_id} responsibilities",
                })
        result = {"constraints": constraints, "source": "fallback"}

    _save_json(bb_dir / "code_propagator.json", result)
    return result


def _run_depgraph(bb_dir: Path) -> dict:
    """依赖图构建：从 WP 依赖关系构建 DAG"""
    # 优先使用 AC Writer 的输出（含 WP + 依赖）
    ac_output = _read_bb(bb_dir, "p2_ac_writer.json")
    if not ac_output:
        # Fallback: 使用 Blueprint
        ac_output = _read_bb(bb_dir, "p1_consolidator.json")

    if not ac_output:
        return {"error": "No WP data found", "dependencies": [], "source": "fallback"}

    work_packages = ac_output.get("work_package_details") or ac_output.get("work_packages", [])

    try:
        v5_dir = Path(__file__).resolve().parent.parent / "v5"
        sys.path.insert(0, str(v5_dir))
        from code.depgraph import build_dependency_graph
        # 过滤掉非 dict 的条目
        wp_dicts = [wp for wp in work_packages if isinstance(wp, dict)]
        result = build_dependency_graph(wp_dicts)
    except ImportError:
        # Fallback: 简单构建
        wp_dicts = [wp for wp in work_packages if isinstance(wp, dict)]
        edges = []
        for wp in wp_dicts:
            for dep in wp.get("dependencies", []):
                edges.append({"from": dep, "to": wp.get("id")})
        wp_ids = [wp.get("id") for wp in wp_dicts]
        result = {
            "execution_order": wp_ids,
            "parallel_groups": [wp_ids],
            "critical_path": wp_ids,
            "edges": edges,
            "has_cycle": False,
            "source": "fallback",
        }

    _save_json(bb_dir / "code_depgraph.json", result)
    return result


def _run_numeric_checker(bb_dir: Path) -> dict:
    """数值一致性检查"""
    # 收集所有包含数值的输出
    package_draft = {}
    ac_output = _read_bb(bb_dir, "p2_ac_writer.json")
    propagator = _read_bb(bb_dir, "code_propagator.json")

    if ac_output:
        package_draft["acceptance_criteria"] = ac_output.get("acceptance_criteria", [])
        package_draft["work_packages"] = ac_output.get("work_packages", [])
    if propagator:
        package_draft["constraints"] = propagator.get("constraints", [])

    try:
        v5_dir = Path(__file__).resolve().parent.parent / "v5"
        sys.path.insert(0, str(v5_dir))
        from code.numeric_checker import extract_numeric_claims, find_numeric_conflicts
        claims = extract_numeric_claims(package_draft)
        conflicts = find_numeric_conflicts(claims)
        result = {"claims": claims, "conflicts": conflicts}
    except ImportError:
        result = {"claims": [], "conflicts": [], "source": "fallback"}

    _save_json(bb_dir / "code_numeric_checker.json", result)
    return result


# ---------------------------------------------------------------------------
# next — V5 状态机
# ---------------------------------------------------------------------------

def next_step(output_dir: str) -> dict:
    """
    V5 状态机决策

    Phase 1 流程:
      p1_parser → p1_explorer → p1_architect_step1 → p1_architect_step2
      → 3 critics (并行) → p1_consolidator → gate1
      → pass: 进入 Phase 2
      → fail + fixable + round < max: fix-context → 重跑失败部分
      → fail + round >= max: Phase 1 失败

    Phase 2 流程:
      code:propagator → code:depgraph → code:numeric_checker
      → p2_ac_writer → 3 judges (并行) → p2_consolidator → gate2
      → pass: validate → finalize
      → fail + fixable + round < max: fix-context → 重跑
      → fail + round >= max: Phase 2 失败
    """
    output_p = Path(output_dir)
    status = _load_status(output_p)
    if not status:
        return {"action": "error", "message": "Pipeline not prepared"}

    config = _load_json(output_p / "pipeline_config.json")
    max_rounds = config.get("max_rounds", MAX_ROUNDS) if config else MAX_ROUNDS

    phase = _current_phase(status)

    if phase == 1:
        return _next_phase1(status, max_rounds, output_p)
    elif phase == 2:
        return _next_phase2(status, max_rounds, output_p)
    else:
        return {"action": "error", "message": f"Invalid phase: {phase}"}


def _next_phase1(status: dict, max_rounds: int, output_p: Path) -> dict:
    """Phase 1 状态机"""
    agents = status.get("agents", {})
    current_round = status.get("phase1_round", 1)
    phase_state = status.get("phase1_state", "running")

    # 顺序检查 Phase 1 agents
    sequential = ["p1_parser", "p1_explorer", "p1_architect_step1", "p1_architect_step2"]

    for agent in sequential:
        state = agents.get(agent, {}).get("state", "pending")
        if state in ("pending", "running"):
            return {
                "action": "spawn",
                "agent": agent,
                "phase": 1,
                "round": current_round,
                "reason": f"{agent} is {state}",
            }
        if state == "gate_fail":
            retries = agents.get(agent, {}).get("retry_count", 0)
            if retries < MAX_GATE_RETRIES:
                return {
                    "action": "spawn",
                    "agent": agent,
                    "phase": 1,
                    "round": current_round,
                    "reason": f"{agent} gate failed, retry {retries + 1}/{MAX_GATE_RETRIES}",
                }
            else:
                return {
                    "action": "fail",
                    "phase": 1,
                    "reason": f"{agent} gate failed after {MAX_GATE_RETRIES} retries",
                }

    # 检查 3 个 critic（并行组）
    critics = ["p1_coverage_critic", "p1_granularity_critic", "p1_feasibility_critic"]
    pending_critics = [c for c in critics if agents.get(c, {}).get("state", "pending") in ("pending", "running")]
    if pending_critics:
        return {
            "action": "spawn_parallel",
            "agents": pending_critics,
            "parallel_group": "p1_critics",
            "phase": 1,
            "round": current_round,
            "reason": f"{len(pending_critics)} critics pending",
        }

    failed_critics = [c for c in critics if agents.get(c, {}).get("state") == "gate_fail"]
    if failed_critics:
        # Critic gate 失败 → 重试
        retriable = []
        for c in failed_critics:
            retries = agents.get(c, {}).get("retry_count", 0)
            if retries < MAX_GATE_RETRIES:
                retriable.append(c)
        if retriable:
            return {
                "action": "spawn_parallel",
                "agents": retriable,
                "parallel_group": "p1_critics",
                "phase": 1,
                "round": current_round,
                "reason": f"{len(retriable)} critics need retry",
            }
        # 全部 critic 重试耗尽 → 跳过（允许继续，critic 不是必须的）

    # Consolidator
    cons_state = agents.get("p1_consolidator", {}).get("state", "pending")
    if cons_state in ("pending", "running"):
        return {
            "action": "spawn",
            "agent": "p1_consolidator",
            "phase": 1,
            "round": current_round,
            "reason": "Consolidator pending",
        }
    if cons_state == "gate_fail":
        retries = agents.get("p1_consolidator", {}).get("retry_count", 0)
        if retries < MAX_GATE_RETRIES:
            return {
                "action": "spawn",
                "agent": "p1_consolidator",
                "phase": 1,
                "round": current_round,
                "reason": f"Consolidator gate failed, retry {retries + 1}",
            }
        else:
            if current_round < max_rounds:
                return {
                    "action": "fix_and_rerun",
                    "phase": 1,
                    "round": current_round,
                    "reason": "Consolidator gate failed after retries, need fix cycle",
                }
            return {
                "action": "fail",
                "phase": 1,
                "reason": f"Phase 1 failed after {max_rounds} rounds",
            }

    # Consolidator passed → Phase 1 完成
    if cons_state in ("gate_pass", "gate_conditional"):
        return {
            "action": "phase_complete",
            "phase": 1,
            "next_phase": 2,
            "reason": "Phase 1 Blueprint complete, proceed to Phase 2",
        }

    return {"action": "error", "message": f"Unexpected Phase 1 state: {cons_state}"}


def _next_phase2(status: dict, max_rounds: int, output_p: Path) -> dict:
    """Phase 2 状态机"""
    agents = status.get("agents", {})
    current_round = status.get("phase2_round", 1)

    # 确定性代码模块
    for mod in CODE_MODULES:
        code_agent = f"code_{mod}"
        state = agents.get(code_agent, {}).get("state", "pending")
        if state == "pending":
            return {
                "action": "run_code",
                "module": mod,
                "phase": 2,
                "round": current_round,
                "reason": f"Code module {mod} pending",
            }

    # AC Writer
    ac_state = agents.get("p2_ac_writer", {}).get("state", "pending")
    if ac_state in ("pending", "running"):
        return {
            "action": "spawn",
            "agent": "p2_ac_writer",
            "phase": 2,
            "round": current_round,
            "reason": "AC Writer pending",
        }
    if ac_state == "gate_fail":
        retries = agents.get("p2_ac_writer", {}).get("retry_count", 0)
        if retries < MAX_GATE_RETRIES:
            return {
                "action": "spawn",
                "agent": "p2_ac_writer",
                "phase": 2,
                "round": current_round,
                "reason": f"AC Writer gate failed, retry {retries + 1}",
            }

    # 3 Judges（并行组）
    judges = ["p2_consistency_judge", "p2_quality_judge", "p2_completeness_judge"]
    pending_judges = [j for j in judges if agents.get(j, {}).get("state", "pending") in ("pending", "running")]
    if pending_judges:
        return {
            "action": "spawn_parallel",
            "agents": pending_judges,
            "parallel_group": "p2_judges",
            "phase": 2,
            "round": current_round,
            "reason": f"{len(pending_judges)} judges pending",
        }

    failed_judges = [j for j in judges if agents.get(j, {}).get("state") == "gate_fail"]
    if failed_judges:
        retriable = [j for j in failed_judges
                     if agents.get(j, {}).get("retry_count", 0) < MAX_GATE_RETRIES]
        if retriable:
            return {
                "action": "spawn_parallel",
                "agents": retriable,
                "parallel_group": "p2_judges",
                "phase": 2,
                "round": current_round,
                "reason": f"{len(retriable)} judges need retry",
            }

    # Consolidator
    cons_state = agents.get("p2_consolidator", {}).get("state", "pending")
    if cons_state in ("pending", "running"):
        return {
            "action": "spawn",
            "agent": "p2_consolidator",
            "phase": 2,
            "round": current_round,
            "reason": "Phase 2 Consolidator pending",
        }
    if cons_state == "gate_fail":
        retries = agents.get("p2_consolidator", {}).get("retry_count", 0)
        if retries < MAX_GATE_RETRIES:
            return {
                "action": "spawn",
                "agent": "p2_consolidator",
                "phase": 2,
                "round": current_round,
                "reason": f"Phase 2 Consolidator gate failed, retry {retries + 1}",
            }
        if current_round < max_rounds:
            return {
                "action": "fix_and_rerun",
                "phase": 2,
                "round": current_round,
                "reason": "Phase 2 Consolidator failed after retries, need fix cycle",
            }
        return {
            "action": "fail",
            "phase": 2,
            "reason": f"Phase 2 failed after {max_rounds} rounds",
        }

    if cons_state in ("gate_pass", "gate_conditional"):
        return {
            "action": "validate",
            "phase": 2,
            "reason": "Phase 2 complete, ready for final validation",
        }

    return {"action": "error", "message": f"Unexpected Phase 2 state: {cons_state}"}


# ---------------------------------------------------------------------------
# fix-context — 构建修复上下文
# ---------------------------------------------------------------------------

def build_fix_context(output_dir: str, phase: Optional[int] = None) -> dict:
    """构建 FixContext：基于 Judge/Critic 的输出，指导下一轮修复"""
    output_p = Path(output_dir)
    status = _load_status(output_p)
    config = _load_json(output_p / "pipeline_config.json")
    bb_dir = Path(config["blackboard_dir"])

    if phase is None:
        phase = _current_phase(status)

    current_round = status.get(f"phase{phase}_round", 1)

    if phase == 1:
        # Phase 1: 从 3 个 Critic 的输出构建 fix context
        critic_outputs = []
        for critic in ["p1_coverage_critic", "p1_granularity_critic", "p1_feasibility_critic"]:
            reg = AGENT_REGISTRY[critic]
            data = _read_bb(bb_dir, reg["output"])
            if data:
                critic_outputs.append({"agent": critic, "output": data})

        fix_context = {
            "phase": 1,
            "original_verdict": "fail",
            "current_round": current_round,
            "max_rounds": MAX_ROUNDS,
            "instructions": [],
            "focus_areas": [],
            "regression_warnings": [],
            "critic_feedback": critic_outputs,
        }

        # 从 critic 输出中提取 issues
        for co in critic_outputs:
            issues = co["output"].get("issues", [])
            for issue in issues:
                fix_context["instructions"].append({
                    "source": co["agent"],
                    "severity": issue.get("severity", "warning"),
                    "message": issue.get("message", ""),
                    "fix_suggestion": issue.get("fix_suggestion", ""),
                })
                if issue.get("severity") in ("blocker", "critical"):
                    fix_context["focus_areas"].append(issue.get("message", ""))

    else:
        # Phase 2: 从 3 个 Judge 的输出构建 fix context
        judge_outputs = []
        for judge in ["p2_consistency_judge", "p2_quality_judge", "p2_completeness_judge"]:
            reg = AGENT_REGISTRY[judge]
            data = _read_bb(bb_dir, reg["output"])
            if data:
                judge_outputs.append({"agent": judge, "output": data})

        fix_context = {
            "phase": 2,
            "original_verdict": "fail",
            "current_round": current_round,
            "max_rounds": MAX_ROUNDS,
            "instructions": [],
            "focus_areas": [],
            "regression_warnings": [],
            "judge_feedback": judge_outputs,
        }

        for jo in judge_outputs:
            issues = jo["output"].get("issues", jo["output"].get("risks", []))
            for issue in issues:
                fix_context["instructions"].append({
                    "source": jo["agent"],
                    "severity": issue.get("severity", "warning"),
                    "message": issue.get("message", issue.get("description", "")),
                    "fix_suggestion": issue.get("fix_suggestion", ""),
                    "fixable": issue.get("fixable", True),
                })

    # 保存
    fc_path = output_p / f"fix_context_p{phase}.json"
    _save_json(fc_path, fix_context)

    # 更新状态
    status[f"phase{phase}_round"] = current_round + 1
    status[f"phase{phase}_state"] = "fix"
    # 重置需要重跑的 agent 状态
    if phase == 1:
        # Phase 1 fix: 重跑 consolidator（或受影响的 agent）
        for agent in ["p1_consolidator"]:
            status["agents"][agent]["state"] = "pending"
            status["agents"][agent]["retry_count"] = 0
    else:
        # Phase 2 fix: 重跑 AC Writer + Judges
        for agent in ["p2_ac_writer", "p2_consistency_judge", "p2_quality_judge",
                       "p2_completeness_judge", "p2_consolidator"]:
            status["agents"][agent]["state"] = "pending"
            status["agents"][agent]["retry_count"] = 0

    _save_status(output_p, status)

    return fix_context


# ---------------------------------------------------------------------------
# validate — 最终验证
# ---------------------------------------------------------------------------

def validate_pipeline(output_dir: str) -> dict:
    """最终验证：检查所有输出完整性"""
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    bb_dir = Path(config["blackboard_dir"])

    results = {
        "phase1_agents": {},
        "phase2_agents": {},
        "code_modules": {},
        "final_output": None,
        "overall": "pass",
    }

    # Phase 1 检查
    for agent in [a for a, r in AGENT_REGISTRY.items() if r["phase"] == 1]:
        reg = AGENT_REGISTRY[agent]
        exists = (bb_dir / reg["output"]).exists()
        results["phase1_agents"][agent] = "ok" if exists else "missing"
        if not exists:
            results["overall"] = "degraded"

    # Phase 2 检查
    for agent in [a for a, r in AGENT_REGISTRY.items() if r["phase"] == 2]:
        reg = AGENT_REGISTRY[agent]
        exists = (bb_dir / reg["output"]).exists()
        results["phase2_agents"][agent] = "ok" if exists else "missing"
        if not exists:
            results["overall"] = "degraded"

    # Code modules 检查
    for mod in CODE_MODULES:
        exists = (bb_dir / f"code_{mod}.json").exists()
        results["code_modules"][mod] = "ok" if exists else "missing"

    # Final output 检查
    final_path = bb_dir / "p2_consolidator.json"
    if final_path.exists():
        results["final_output"] = str(final_path)
    else:
        results["overall"] = "fail"

    return results


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------

def finalize_pipeline(output_dir: str, result: str) -> dict:
    """标记管线完成"""
    output_p = Path(output_dir)
    status = _load_status(output_p)
    status["completed_at"] = datetime.now().isoformat()
    status["final_result"] = result
    _save_status(output_p, status)

    # 写 .completed
    completed = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": result,
        "version": "5.0.0",
    }
    _save_json(output_p / "blackboard" / ".completed", completed)

    return completed


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def get_status(output_dir: str) -> dict:
    """获取管线状态"""
    output_p = Path(output_dir)
    status = _load_status(output_p)
    config = _load_json(output_p / "pipeline_config.json")

    if not status:
        return {"error": "Pipeline not prepared"}

    bb_dir = Path(config["blackboard_dir"]) if config else output_p / "blackboard"

    # 统计 agent 状态
    agents_summary = {}
    for agent_name, agent_state in status.get("agents", {}).items():
        agents_summary[agent_name] = {
            "state": agent_state.get("state", "unknown"),
            "retry_count": agent_state.get("retry_count", 0),
            "gate_decision": agent_state.get("gate_decision", "N/A"),
        }

    return {
        "run_id": status.get("run_id"),
        "version": status.get("version"),
        "current_phase": _current_phase(status),
        "phase1_round": status.get("phase1_round", 1),
        "phase2_round": status.get("phase2_round", 1),
        "phase1_state": status.get("phase1_state", "unknown"),
        "phase2_state": status.get("phase2_state", "unknown"),
        "agents": agents_summary,
        "completed": (bb_dir / ".completed").exists(),
    }


# ---------------------------------------------------------------------------
# increment-retry
# ---------------------------------------------------------------------------

def increment_retry(output_dir: str, agent_name: str) -> dict:
    """原子递增 agent 的 retry count"""
    output_p = Path(output_dir)
    status = _load_status(output_p)

    if agent_name not in status.get("agents", {}):
        return {"error": f"Unknown agent: {agent_name}"}

    agent = status["agents"][agent_name]
    agent["retry_count"] = agent.get("retry_count", 0) + 1
    agent["state"] = "pending"  # 重置为 pending，允许重新 spawn

    _save_status(output_p, status)

    return {
        "agent": agent_name,
        "retry_count": agent["retry_count"],
        "allowed": agent["retry_count"] <= MAX_GATE_RETRIES,
        "state": "pending",
    }


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "prepare":
            if len(sys.argv) < 4:
                print("Usage: run_pipeline_v5.py prepare <input_path> <output_dir>")
                sys.exit(1)
            result = prepare_pipeline(sys.argv[2], sys.argv[3])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "task":
            if len(sys.argv) < 4:
                print("Usage: run_pipeline_v5.py task <agent_name> <output_dir>")
                sys.exit(1)
            result = get_agent_task(sys.argv[2], sys.argv[3])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "gate":
            if len(sys.argv) < 4:
                print("Usage: run_pipeline_v5.py gate <agent_name> <output_dir>")
                sys.exit(1)
            result = check_gate(sys.argv[2], sys.argv[3])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "run-code":
            if len(sys.argv) < 4:
                print("Usage: run_pipeline_v5.py run-code <module_name> <output_dir>")
                sys.exit(1)
            result = run_code_module(sys.argv[2], sys.argv[3])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "next":
            if len(sys.argv) < 3:
                print("Usage: run_pipeline_v5.py next <output_dir>")
                sys.exit(1)
            result = next_step(sys.argv[2])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "fix-context":
            if len(sys.argv) < 3:
                print("Usage: run_pipeline_v5.py fix-context <output_dir> [--phase 1|2]")
                sys.exit(1)
            phase = None
            if "--phase" in sys.argv:
                idx = sys.argv.index("--phase")
                phase = int(sys.argv[idx + 1])
            result = build_fix_context(sys.argv[2], phase)
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "validate":
            if len(sys.argv) < 3:
                print("Usage: run_pipeline_v5.py validate <output_dir>")
                sys.exit(1)
            result = validate_pipeline(sys.argv[2])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "finalize":
            if len(sys.argv) < 4:
                print("Usage: run_pipeline_v5.py finalize <output_dir> <pass|fail>")
                sys.exit(1)
            result = finalize_pipeline(sys.argv[2], sys.argv[3])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "status":
            if len(sys.argv) < 3:
                print("Usage: run_pipeline_v5.py status <output_dir>")
                sys.exit(1)
            result = get_status(sys.argv[2])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif command == "increment-retry":
            if len(sys.argv) < 4:
                print("Usage: run_pipeline_v5.py increment-retry <output_dir> <agent_name>")
                sys.exit(1)
            result = increment_retry(sys.argv[2], sys.argv[3])
            print(json.dumps(result, indent=2, ensure_ascii=False))

        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
