#!/usr/bin/env python3
# ---
# id: ship_pro/run_pipeline
# version: "2.0.0"
# component: ship_pro
# updated: "2026-06-22"
# status: active
# ---
"""
Ship Pro V3.1 — Dynamic Pipeline Orchestrator

Provides "next step" information for the main Agent's dynamic spawn loop.
Does NOT call sessions_spawn directly. Instead:

1. prepare_pipeline() — set up blackboard, detect format, generate run_id
2. get_agent_task()   — build complete task prompt for a single Agent
3. check_gate()       — run quality gate on Agent output
4. get_feedback_task()— generate feedback message for retry
5. validate_pipeline()— verify final output completeness
6. status()           — show current pipeline state

CLI:
    python3 run_pipeline.py prepare <input_path> <output_dir>
    python3 run_pipeline.py task <agent_name> <output_dir>
    python3 run_pipeline.py gate <agent_name> <output_dir>
    python3 run_pipeline.py feedback <agent_name> <output_dir>
    python3 run_pipeline.py validate <output_dir>
    python3 run_pipeline.py status <output_dir>
"""

import json
import sys
import os
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

# Import STAGE_PATH_REGISTRY for path resolution
import core.bootstrap
from domains.ship_pro.blackboard import STAGE_PATH_REGISTRY, BlackboardManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_ORDER = ["architect", "decomposer", "specifier", "reviewer", "packager"]

GATE_CONFIG = {
    "architect":  {"max_retries": 2, "gate_fn": "gate_architect"},
    "decomposer": {"max_retries": 2, "gate_fn": "gate_decomposer"},
    "specifier":  {"max_retries": 2, "gate_fn": "gate_specifier"},
    "reviewer":   {"max_retries": 5, "gate_fn": "gate_reviewer"},
    "packager":   {"max_retries": 2, "gate_fn": "gate_packager"},
}

AGENT_MODELS = {
    "architect":  "strong",
    "decomposer": "strong",
    "specifier":  "strong",
    "reviewer":   "different",  # avoid collusion
    "packager":   "fast",
}

AGENT_TIMEOUTS = {
    "architect":  300,
    "decomposer": 300,
    "specifier":  300,
    "reviewer":   300,
    "packager":   180,
}

AGENT_DEPENDENCIES = {
    "architect":  [],
    "decomposer": ["architect"],
    "specifier":  ["architect", "decomposer"],
    "reviewer":   ["architect", "decomposer", "specifier"],
    "packager":   ["architect", "specifier", "reviewer"],
}

STATUS_FILE = "pipeline_state.json"  # V3.2: 统一状态文件（Phase 3 单一化）


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_format(data: dict) -> str:
    """
    Detect input format type.
    Format A: final_solution exists (complete solution)
    Format B: project + architecture exist (flat domain description)
    Format C: pipeline_summary or executive_summary exists
    Format D: other (minimal input)
    """
    if "final_solution" in data:
        return "A"
    elif "project" in data and "architecture" in data:
        return "B"
    elif "pipeline_summary" in data or "executive_summary" in data:
        return "C"
    else:
        return "D"


def _load_prompt(agent_name: str) -> str:
    """Load Agent prompt template from prompts/ directory."""
    prompt_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompt_dir / f"{agent_name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_file}")
    return prompt_file.read_text()


def _compute_prompt_sha(agent_name: str) -> str:
    """Compute SHA256 of prompt file."""
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{agent_name}.md"
    if not prompt_path.exists():
        return "unknown"
    return hashlib.sha256(prompt_path.read_bytes()).hexdigest()


def _load_status(output_dir: Path) -> dict:
    """Load pipeline status from output_dir."""
    status_path = output_dir / STATUS_FILE
    if status_path.exists():
        with open(status_path) as f:
            return json.load(f)
    return {}


def _save_status(output_dir: Path, status: dict) -> None:
    """Save pipeline status to output_dir (Pydantic validated)."""
    # V3.2: Pydantic 契约笼子验证状态
    try:
        from domains.ship_pro.contracts.pipeline_state import PipelineState
        PipelineState(**status)
    except Exception:
        pass  # 降级: 允许写入，但记录警告
    status_path = output_dir / STATUS_FILE
    with open(status_path, "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    status_path = output_dir / STATUS_FILE
    with open(status_path, "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


def _load_blackboard_file(blackboard_dir: str, stage_name: str) -> Optional[dict]:
    """Load a JSON file from blackboard using STAGE_PATH_REGISTRY, return None if not found."""
    rel_path = STAGE_PATH_REGISTRY.get(stage_name, stage_name)
    path = Path(blackboard_dir) / rel_path
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _get_upstream_outputs(agent_name: str, blackboard_dir: str) -> dict:
    """
    Collect upstream Agent outputs for a given agent.
    Returns dict of {agent_name: output_data}.
    """
    deps = AGENT_DEPENDENCIES.get(agent_name, [])
    upstream = {}
    for dep in deps:
        data = _load_blackboard_file(blackboard_dir, dep)
        if data is not None:
            upstream[dep] = data
    return upstream


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def prepare_pipeline(input_path: str, output_dir: str) -> dict:
    """
    Prepare pipeline environment.

    - Copy input file to blackboard
    - Detect input format
    - Generate run_id
    - Initialize pipeline status
    - Return pipeline config
    """
    # Record pipeline start time for watcher timeout detection
    run_start_at = datetime.now(timezone.utc).isoformat()

    input_p = Path(input_path)
    output_p = Path(output_dir)

    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Create directories
    output_p.mkdir(parents=True, exist_ok=True)
    bb_dir = output_p / "blackboard"
    bb_dir.mkdir(exist_ok=True)

    # Clean up stale state files from previous runs (prevents Watcher false positives)
    stale_files = [
        ".notified_stages.json", ".cron_run_count", ".watcher_no_output_count",
        ".pipeline_watcher.lock", ".completed", ".watcher_should_remove",
    ]
    for sf in stale_files:
        p = bb_dir / sf
        if p.exists():
            p.unlink()
    # Also clean old stage output files (registry paths)
    for stage_name, rel_path in STAGE_PATH_REGISTRY.items():
        if stage_name == "input":
            continue
        p = bb_dir / rel_path
        if p.exists():
            p.unlink()

    # Read input
    with open(input_p) as f:
        input_data = json.load(f)

    # Detect format
    fmt = _detect_format(input_data)

    # Generate run_id
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fmt.lower()}"

    # Copy input to blackboard using registry path
    with open(bb_dir / STAGE_PATH_REGISTRY["input"], "w") as f:
        json.dump(input_data, f, indent=2, ensure_ascii=False)

    # Build pipeline config
    pipeline_config = {
        "run_id": run_id,
        "input_format": fmt,
        "input_file": str(input_p.resolve()),
        "blackboard_dir": str(bb_dir.resolve()),
        "output_dir": str(output_p.resolve()),
        "execution_order": AGENT_ORDER[:],
        "gate_config": {k: dict(v) for k, v in GATE_CONFIG.items()},
        "generated_at": datetime.now().isoformat(),
    }

    # Write pipeline config
    with open(output_p / "pipeline_config.json", "w") as f:
        json.dump(pipeline_config, f, indent=2, ensure_ascii=False)

    # Initialize status
    status = {
        "run_id": run_id,
        "started_at": datetime.now().isoformat(),
        "agents": {},
        "current_agent": None,
        "skipped_agents": [],
    }
    for agent in AGENT_ORDER:
        status["agents"][agent] = {
            "state": "pending",       # pending | running | gate_pass | gate_conditional | gate_fail | skipped | done
            "retry_count": 0,
            "max_retries": GATE_CONFIG[agent]["max_retries"],
            "gate_decision": None,
            "last_gate_feedback": None,
        }
    _save_status(output_p, status)

    # Watcher integration: provide complete cron payload for main Agent
    deepflow_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    watcher_config_rel = "domains/ship_pro/config/watcher_config.json"
    watcher_config_abs = os.path.join(deepflow_root, watcher_config_rel)
    pipeline_config["run_start_at"] = run_start_at
    pipeline_config["watcher_config"] = watcher_config_rel
    pipeline_config["watcher_config_abs"] = watcher_config_abs
    pipeline_config["deepflow_root"] = deepflow_root

    # Render the wrapper prompt so main Agent can directly create the cron job
    try:
        from scripts.pipeline_watcher import render_wrapper_prompt
        wrapper_prompt = render_wrapper_prompt(
            deepflow_root=deepflow_root,
            config_path=watcher_config_abs,
            base_path=str(bb_dir.resolve()),
            run_start_at=run_start_at,
            cron_job_id="__CRON_JOB_ID__",  # main Agent backfills after cron creation
        )
        pipeline_config["watcher_cron_payload"] = {
            "name": f"deepflow_watcher_{run_id[:16]}",
            "schedule": {"kind": "every", "everyMs": 180000},
            "sessionTarget": "isolated",
            "payload": {
                "kind": "agentTurn",
                "message": wrapper_prompt,
                "timeoutSeconds": 60,
                "lightContext": True,
            },
            "delivery": {"mode": "announce"},
            "enabled": True,
        }
    except ImportError:
        pipeline_config["watcher_cron_payload"] = None

    return pipeline_config


def get_agent_task(agent_name: str, output_dir: str) -> dict:
    """
    Build complete task prompt for a single Agent.

    - Load prompt template
    - Inject input data
    - Inject upstream Agent output paths
    - Include run metadata
    """
    output_p = Path(output_dir)
    pipeline_config_path = output_p / "pipeline_config.json"
    if not pipeline_config_path.exists():
        raise FileNotFoundError(f"Pipeline not prepared. Run 'prepare' first: {pipeline_config_path}")

    with open(pipeline_config_path) as f:
        config = json.load(f)

    if agent_name not in AGENT_ORDER:
        raise ValueError(f"Unknown agent: {agent_name}. Must be one of {AGENT_ORDER}")

    bb_dir = config["blackboard_dir"]
    run_id = config["run_id"]
    fmt = config["input_format"]

    # Load original input
    input_data = _load_blackboard_file(bb_dir, "input")
    if input_data is None:
        raise FileNotFoundError(f"Input data missing from blackboard: {bb_dir}")

    # Load prompt
    prompt = _load_prompt(agent_name)
    prompt_sha = _compute_prompt_sha(agent_name)

    # Format hint (Architect only)
    format_hint = ""
    if agent_name == "architect":
        format_hint = f"\n\n**输入格式已预检测为 Format {fmt}**。请按照 Format {fmt} 的提取规则处理。"

    # Upstream outputs summary (paths + brief info)
    upstream_info_parts = []
    deps = AGENT_DEPENDENCIES.get(agent_name, [])
    for dep in deps:
        dep_file = f"{bb_dir}/{STAGE_PATH_REGISTRY[dep]}"
        upstream_info_parts.append(f"- {dep} 输出: `{dep_file}`")

    upstream_section = ""
    if upstream_info_parts:
        upstream_section = "\n\n## 上游 Agent 输出路径\n\n" + "\n".join(upstream_info_parts)

    # Build full task prompt
    task = f"""## Agent: {agent_name.title()}

{prompt}
{format_hint}

## 输入数据

```json
{json.dumps(input_data, indent=2, ensure_ascii=False)}
```
{upstream_section}

## 运行信息

- run_id: {run_id}
- blackboard_dir: {bb_dir}
- prompt_sha: {prompt_sha}

## ⚠️ 输出文件路径（必须严格遵守）

**输出文件路径**: `{bb_dir}/{STAGE_PATH_REGISTRY[agent_name]}`

- 文件名必须是 `{STAGE_PATH_REGISTRY[agent_name]}`（根据 STAGE_PATH_REGISTRY）
- 禁止使用其他文件名
- 如果文件名不正确，下游 Agent 将无法读取你的输出

## 输出要求

1. 输出必须是合法的 JSON
2. 写入到上述指定路径
3. 在 _meta 中记录 prompt_sha、model_id、run_id、round
"""

    # Update status: mark agent as running
    status = _load_status(output_p)
    if agent_name in status.get("agents", {}):
        status["agents"][agent_name]["state"] = "running"
        status["current_agent"] = agent_name
    _save_status(output_p, status)

    return {
        "agent": agent_name,
        "task": task,
        "timeout_seconds": AGENT_TIMEOUTS.get(agent_name, 300),
        "model": AGENT_MODELS.get(agent_name, "strong"),
        "depends_on": deps,
        "output_file": f"{bb_dir}/{STAGE_PATH_REGISTRY[agent_name]}",
        "prompt_sha": prompt_sha,
    }


def check_gate(agent_name: str, output_dir: str) -> dict:
    """
    Run quality gate check on an Agent's output.

    Reads the Agent output from blackboard, runs the corresponding gate function,
    and returns the gate result with decision and feedback.
    """
    output_p = Path(output_dir)
    pipeline_config_path = output_p / "pipeline_config.json"
    if not pipeline_config_path.exists():
        raise FileNotFoundError(f"Pipeline not prepared: {pipeline_config_path}")

    with open(pipeline_config_path) as f:
        config = json.load(f)

    bb_dir = config["blackboard_dir"]
    gate_fn_name = GATE_CONFIG.get(agent_name, {}).get("gate_fn")

    # Load agent output
    output_file = Path(bb_dir) / STAGE_PATH_REGISTRY[agent_name]
    if not output_file.exists():
        return {
            "agent": agent_name,
            "decision": "FAIL",
            "critical_failures": ["output_file_missing"],
            "feedback": f"Agent output file not found: {output_file}. Agent must write output before gate check.",
            "should_retry": True,
            "retry_count": 0,
            "skippable": False,
        }

    if output_file.is_dir():
        # Agent wrote to a directory instead of a file — try to find output.json inside
        fallback = output_file / "output.json"
        if fallback.exists():
            output_file = fallback
        else:
            return {
                "agent": agent_name,
                "decision": "FAIL",
                "critical_failures": ["output_is_directory"],
                "feedback": f"Agent output is a directory, not a file: {output_file}. Agent must write JSON to this exact path (not create a directory).",
                "should_retry": True,
                "retry_count": 0,
                "skippable": False,
            }

    with open(output_file) as f:
        agent_output = json.load(f)

    # If no gate function, auto-pass (should not happen after contract cage hardening)
    if gate_fn_name is None:
        _update_gate_status(output_p, agent_name, "PASS", "No code gate configured. Auto-pass.")
        return {
            "agent": agent_name,
            "decision": "PASS",
            "critical_failures": [],
            "feedback": "No code gate configured. Auto-pass.",
            "should_retry": False,
            "retry_count": 0,
            "skippable": False,
        }

    # Import and run gate function
    from domains.ship_pro.eval.gates import gate_architect, gate_decomposer, gate_specifier, gate_reviewer, gate_packager

    gate_fns = {
        "gate_architect": gate_architect,
        "gate_decomposer": gate_decomposer,
        "gate_specifier": gate_specifier,
        "gate_reviewer": gate_reviewer,
        "gate_packager": gate_packager,
    }

    gate_fn = gate_fns.get(gate_fn_name)
    if gate_fn is None:
        return {
            "agent": agent_name,
            "decision": "FAIL",
            "critical_failures": ["unknown_gate_fn"],
            "feedback": f"Unknown gate function: {gate_fn_name}",
            "should_retry": False,
            "retry_count": 0,
            "skippable": False,
        }

    # Run gate with appropriate arguments
    if gate_fn_name == "gate_architect":
        result = gate_fn(agent_output)
    elif gate_fn_name == "gate_decomposer":
        # Decomposer needs blueprint (architect output)
        blueprint = _load_blackboard_file(bb_dir, "architect")
        if blueprint is None:
            return {
                "agent": agent_name,
                "decision": "FAIL",
                "critical_failures": ["architect_output_missing"],
                "feedback": "Decomposer gate requires architect output for module coverage check.",
                "should_retry": False,
                "retry_count": 0,
                "skippable": False,
            }
        result = gate_fn(agent_output, blueprint)
    elif gate_fn_name == "gate_specifier":
        result = gate_fn(agent_output)
    elif gate_fn_name == "gate_reviewer":
        result = gate_fn(agent_output)
    elif gate_fn_name == "gate_packager":
        result = gate_fn(agent_output)
    else:
        result = gate_fn(agent_output)

    # Determine retry info
    status = _load_status(output_p)
    agent_status = status.get("agents", {}).get(agent_name, {})
    retry_count = agent_status.get("retry_count", 0)
    max_retries = GATE_CONFIG.get(agent_name, {}).get("max_retries", 2)

    decision = result["decision"]
    critical_failures = [k for k, v in result.get("critical_results", {}).items() if not v]
    should_retry = decision == "FAIL" and retry_count < max_retries
    should_skip = decision == "FAIL" and retry_count >= max_retries

    # Update status
    _update_gate_status(output_p, agent_name, decision, result["feedback"])

    return {
        "agent": agent_name,
        "decision": decision,
        "critical_failures": critical_failures,
        "feedback": result["feedback"],
        "should_retry": should_retry,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "skippable": should_skip,
        "gate_results": {
            "critical": result.get("critical_results", {}),
            "major": result.get("major_results", {}),
            "minor": result.get("minor_results", {}),
        },
    }


def get_feedback_task(agent_name: str, output_dir: str) -> dict:
    """
    Generate feedback correction task for an Agent that failed its gate.

    Reads the latest gate result from pipeline status and constructs
    a feedback message with specific failures and correction guidance.
    """
    output_p = Path(output_dir)
    pipeline_config_path = output_p / "pipeline_config.json"
    if not pipeline_config_path.exists():
        raise FileNotFoundError(f"Pipeline not prepared: {pipeline_config_path}")

    with open(pipeline_config_path) as f:
        config = json.load(f)

    status = _load_status(output_p)
    agent_status = status.get("agents", {}).get(agent_name, {})

    gate_feedback = agent_status.get("last_gate_feedback", "No feedback available.")
    retry_count = agent_status.get("retry_count", 0)
    gate_decision = agent_status.get("gate_decision", "FAIL")

    bb_dir = config["blackboard_dir"]
    output_file = f"{bb_dir}/{STAGE_PATH_REGISTRY[agent_name]}"

    # Build feedback task
    feedback_task = f"""## Gate 检查未通过 — 需要修正

**Agent**: {agent_name}
**Gate 结果**: {gate_decision}
**当前重试次数**: {retry_count}/{GATE_CONFIG.get(agent_name, {}).get('max_retries', 2)}

### Gate 反馈

{gate_feedback}

### 修正要求

1. 读取你之前的输出文件: `{output_file}`
2. 根据上述 Gate 反馈，修复所有 Critical 级别的问题
3. 将修正后的完整 JSON 重新写入同一路径: `{output_file}`
4. 确保输出仍然是合法 JSON
5. 在 _meta.round 中递增轮次号

### 注意事项

- 只修复 Gate 指出的问题，不要改动已经通过检查的部分
- 如果 Critical failures 涉及字段为空，必须填充有效值（不能留 null 或空数组）
- 修正后不需要通知任何人，Gate 会再次自动检查
"""

    return {
        "agent": agent_name,
        "feedback_task": feedback_task,
        "retry_count": retry_count,
        "gate_decision": gate_decision,
    }


def validate_pipeline(output_dir: str) -> dict:
    """
    Validate final pipeline output.

    - Check all expected files exist
    - Run eval_code_checks on packager output
    - Generate summary report
    """
    output_p = Path(output_dir)
    pipeline_config_path = output_p / "pipeline_config.json"
    if not pipeline_config_path.exists():
        raise FileNotFoundError(f"Pipeline not prepared: {pipeline_config_path}")

    with open(pipeline_config_path) as f:
        config = json.load(f)

    bb_dir = Path(config["blackboard_dir"])
    status = _load_status(output_p)

    # Check file existence using STAGE_PATH_REGISTRY
    expected_files = {
        "input": bb_dir / STAGE_PATH_REGISTRY["input"],
        "architect": bb_dir / STAGE_PATH_REGISTRY["architect"],
        "decomposer": bb_dir / STAGE_PATH_REGISTRY["decomposer"],
        "specifier": bb_dir / STAGE_PATH_REGISTRY["specifier"],
        "reviewer": bb_dir / STAGE_PATH_REGISTRY["reviewer"],
        "packager": bb_dir / STAGE_PATH_REGISTRY["packager"],
    }

    file_check = {}
    missing_files = []
    for name, path in expected_files.items():
        exists = path.exists()
        file_check[name] = {"exists": exists, "path": str(path)}
        if not exists:
            missing_files.append(name)

    # Run eval_code_checks on packager output if it exists
    packager_eval = None
    packager_path = bb_dir / STAGE_PATH_REGISTRY["packager"]
    if packager_path.exists():
        try:
            from domains.ship_pro.eval.eval_code_checks import check_schema_compliance, check_dependency_graph

            with open(packager_path) as f:
                package_data = json.load(f)

            schema_result = check_schema_compliance(package_data)
            dep_result = check_dependency_graph(package_data.get("work_packages", []))

            # Defensive: ensure results are dicts, not strings
            def _ensure_dict(val):
                if isinstance(val, dict):
                    return val
                return {"raw": str(val)}

            packager_eval = {
                "schema_compliance": _ensure_dict(schema_result),
                "dependency_graph": _ensure_dict(dep_result),
            }
        except Exception as e:
            packager_eval = {"error": str(e)}

    # Build summary
    agent_summary = {}
    for agent in AGENT_ORDER:
        agent_status = status.get("agents", {}).get(agent, {})
        agent_summary[agent] = {
            "state": agent_status.get("state", "unknown"),
            "retry_count": agent_status.get("retry_count", 0),
            "gate_decision": agent_status.get("gate_decision", None),
        }

    skipped = status.get("skipped_agents", [])
    all_pass = all(
        s.get("gate_decision") in ("PASS", "CONDITIONAL", None)
        for s in status.get("agents", {}).values()
    ) and len(missing_files) == 0

    report = {
        "run_id": config["run_id"],
        "validated_at": datetime.now().isoformat(),
        "overall_pass": all_pass,
        "missing_files": missing_files,
        "file_check": file_check,
        "agent_summary": agent_summary,
        "skipped_agents": skipped,
        "packager_eval": packager_eval,
    }

    # Write report
    report_path = output_p / "validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # ── Finalize: set pipeline status + completed_at ──
    _finalize_pipeline(output_p, overall_pass=all_pass)

    return report


def _finalize_pipeline(output_dir: Path, overall_pass: bool) -> None:
    """
    Finalize pipeline state: set status + completed_at.

    Called automatically by validate_pipeline() after all checks complete.
    This is the ONLY place that transitions status from 'running' to 'completed'/'failed'.
    """
    status = _load_status(output_dir)
    if not status:
        return

    status["status"] = "completed" if overall_pass else "failed"
    status["completed_at"] = datetime.now().isoformat()
    _save_status(output_dir, status)


def get_pipeline_status(output_dir: str) -> dict:
    """
    Get current pipeline status summary.
    """
    output_p = Path(output_dir)
    status = _load_status(output_p)

    pipeline_config_path = output_p / "pipeline_config.json"
    config = {}
    if pipeline_config_path.exists():
        with open(pipeline_config_path) as f:
            config = json.load(f)

    # Determine current position in execution order
    current = status.get("current_agent")
    completed = []
    pending = []
    skipped = status.get("skipped_agents", [])

    for agent in AGENT_ORDER:
        agent_state = status.get("agents", {}).get(agent, {}).get("state", "pending")
        if agent_state in ("gate_pass", "done"):
            completed.append(agent)
        elif agent_state == "skipped":
            pass  # tracked separately
        elif agent == current:
            pass  # it's the current one
        else:
            pending.append(agent)

    return {
        "run_id": status.get("run_id", config.get("run_id", "unknown")),
        "started_at": status.get("started_at"),
        "current_agent": current,
        "completed": completed,
        "pending": pending,
        "skipped": skipped,
        "agents": status.get("agents", {}),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_gate_status(output_dir: Path, agent_name: str, decision: str, feedback: str) -> None:
    """Update pipeline status after a gate check."""
    status = _load_status(output_dir)
    agent_status = status.get("agents", {}).get(agent_name, {})

    max_retries = GATE_CONFIG.get(agent_name, {}).get("max_retries", 2)

    if decision == "PASS" or decision == "CONDITIONAL":
        agent_status["state"] = "gate_pass" if decision == "PASS" else "gate_conditional"
    elif decision == "FAIL":
        retry_count = agent_status.get("retry_count", 0)
        if retry_count >= max_retries:
            # Mark as skipped — upgrade mechanism
            agent_status["state"] = "skipped"
            if agent_name not in status.get("skipped_agents", []):
                status.setdefault("skipped_agents", []).append(agent_name)
        else:
            agent_status["state"] = "gate_fail"
            agent_status["retry_count"] = retry_count + 1

    agent_status["gate_decision"] = decision
    agent_status["last_gate_feedback"] = feedback
    status.setdefault("agents", {})[agent_name] = agent_status
    _save_status(output_dir, status)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "prepare":
        if len(sys.argv) < 4:
            print("用法: python3 run_pipeline.py prepare <input_path> <output_dir>")
            sys.exit(1)
        result = prepare_pipeline(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "task":
        if len(sys.argv) < 4:
            print("用法: python3 run_pipeline.py task <agent_name> <output_dir>")
            sys.exit(1)
        result = get_agent_task(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "gate":
        if len(sys.argv) < 4:
            print("用法: python3 run_pipeline.py gate <agent_name> <output_dir>")
            sys.exit(1)
        result = check_gate(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "feedback":
        if len(sys.argv) < 4:
            print("用法: python3 run_pipeline.py feedback <agent_name> <output_dir>")
            sys.exit(1)
        result = get_feedback_task(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "validate":
        if len(sys.argv) < 3:
            print("用法: python3 run_pipeline.py validate <output_dir>")
            sys.exit(1)
        result = validate_pipeline(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "status":
        if len(sys.argv) < 3:
            print("用法: python3 run_pipeline.py status <output_dir>")
            sys.exit(1)
        result = get_pipeline_status(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "update-status":
        if len(sys.argv) < 5:
            print("用法: python3 run_pipeline.py update-status <output_dir> <agent_name> <PASS|CONDITIONAL|FAIL> [feedback]")
            sys.exit(1)
        output_dir = Path(sys.argv[2])
        agent_name = sys.argv[3]
        decision = sys.argv[4].upper()
        feedback = sys.argv[5] if len(sys.argv) > 5 else ""
        _update_gate_status(output_dir, agent_name, decision, feedback)
        # Advance current_agent to next stage
        status = _load_status(output_dir)
        config_path = output_dir / "pipeline_config.json"
        if config_path.exists():
            config = json.load(open(config_path))
            order = config.get("execution_order", [])
            if agent_name in order:
                idx = order.index(agent_name)
                status["current_agent"] = order[idx + 1] if idx < len(order) - 1 else None
        _save_status(output_dir, status)
        print(json.dumps({"ok": True, "agent": agent_name, "decision": decision, "next_agent": status.get("current_agent")}, indent=2))

    elif cmd == "finalize":
        if len(sys.argv) < 4:
            print("用法: python3 run_pipeline.py finalize <output_dir> <pass|fail>")
            sys.exit(1)
        _finalize_pipeline(Path(sys.argv[2]), overall_pass=sys.argv[3].lower() in ("pass", "true", "1"))
        status = _load_status(Path(sys.argv[2]))
        print(json.dumps({"ok": True, "status": status.get("status"), "completed_at": status.get("completed_at")}, indent=2))

    else:
        print(f"未知命令: {cmd}")
        print("可用命令: prepare, task, gate, feedback, validate, status, update-status, finalize")
        sys.exit(1)


if __name__ == "__main__":
    _cli_main()
