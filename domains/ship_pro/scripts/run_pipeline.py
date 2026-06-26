#!/usr/bin/env python3
# ---
# id: ship_pro/run_pipeline
# version: "4.0.0"
# component: ship_pro
# updated: "2026-06-26"
# status: active
# ---
"""
Ship Pro V4.0 — Generator + Judge 两阶段闭环管线

替代 V3.1 的 6-Agent 线性管线，压缩为 2 个角色 + FixContext 循环：
  Generator → Judge → (if fail: FixContext → Generator rerun)

CLI:
    python3 run_pipeline.py prepare <input_path> <output_dir>
    python3 run_pipeline.py task <agent_name> <output_dir>
    python3 run_pipeline.py gate <agent_name> <output_dir>
    python3 run_pipeline.py next <output_dir>
    python3 run_pipeline.py fix-context <output_dir>
    python3 run_pipeline.py validate <output_dir>
    python3 run_pipeline.py status <output_dir>
    python3 run_pipeline.py finalize <output_dir> <pass|fail>
    python3 run_pipeline.py increment-retry <output_dir> <agent_name>
"""

import json
import sys
import os
import hashlib
import fcntl
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Auto-discover .deepflow root for imports
# ---------------------------------------------------------------------------
_dp = next(
    (d for d in Path(__file__).resolve().parents if (d / "core" / "blackboard").is_dir()),
    None,
)
if _dp and str(_dp) not in sys.path:
    sys.path.insert(0, str(_dp))

from domains.ship_pro.blackboard import STAGE_PATH_REGISTRY, BlackboardManager

# ---------------------------------------------------------------------------
# V4.0 Constants
# ---------------------------------------------------------------------------

AGENT_ORDER = ["generator", "judge"]

STAGE_PATHS = {
    "input": STAGE_PATH_REGISTRY.get("input", "input.json"),
    "generator": "generator_output.json",
    "judge": "judge_output.json",
    "fix_context": "fix_context.json",
}

PROMPT_FILES = {
    "generator": "generator.md",
    "judge": "judge.md",
}

MAX_ROUNDS = 3

AGENT_TIMEOUTS = {
    "generator": 600,  # 10 min — large output
    "judge": 300,      # 5 min
}

AGENT_MODELS = {
    "generator": "strong",
    "judge": "strong",
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_status(output_dir: Path) -> dict:
    status_file = output_dir / "pipeline_status.json"
    if status_file.exists():
        return _load_json(status_file) or {}
    return {}


def _save_status(output_dir: Path, status: dict) -> None:
    _save_json(output_dir / "pipeline_status.json", status)


def _load_prompt(agent_name: str) -> str:
    prompt_dir = Path(__file__).resolve().parent.parent / "prompts"
    prompt_file = prompt_dir / PROMPT_FILES[agent_name]
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_file}")
    return prompt_file.read_text()


def _compute_prompt_sha(agent_name: str) -> str:
    try:
        content = _load_prompt(agent_name)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    except FileNotFoundError:
        return "unknown"


def _current_round(output_dir: Path) -> int:
    """Determine the current round number from pipeline status."""
    status = _load_status(output_dir)
    return status.get("current_round", 1)


# ---------------------------------------------------------------------------
# Core: prepare_pipeline
# ---------------------------------------------------------------------------

def prepare_pipeline(input_path: str, output_dir: str) -> dict:
    """
    Prepare V4.0 pipeline environment.

    - Copy input to blackboard
    - Generate run_id
    - Initialize pipeline status
    - Return pipeline config (including watcher cron payload)
    """
    run_start_at = datetime.now(timezone.utc).isoformat()
    input_p = Path(input_path)
    output_p = Path(output_dir)

    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Create directories
    output_p.mkdir(parents=True, exist_ok=True)
    bb_dir = output_p / "blackboard"
    bb_dir.mkdir(exist_ok=True)

    # Clean stale state files
    stale_files = [
        ".notified_stages.json", ".cron_run_count", ".watcher_no_output_count",
        ".pipeline_watcher.lock", ".completed", ".watcher_should_remove",
        "pipeline_status.json", "fix_context.json",
    ]
    for sf in stale_files:
        p = bb_dir / sf
        if p.exists():
            p.unlink()
    # Also clean from output_p level
    for sf in ["pipeline_status.json"]:
        p = output_p / sf
        if p.exists():
            p.unlink()

    # Clean old stage outputs
    for stage_name, rel_path in STAGE_PATHS.items():
        if stage_name == "input":
            continue
        p = bb_dir / rel_path
        if p.exists():
            p.unlink()

    # Read & copy input
    with open(input_p) as f:
        input_data = json.load(f)

    with open(bb_dir / STAGE_PATHS["input"], "w") as f:
        json.dump(input_data, f, indent=2, ensure_ascii=False)

    # Generate run_id
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_v4"

    # Pipeline config
    pipeline_config = {
        "run_id": run_id,
        "version": "4.0.0",
        "input_file": str(input_p.resolve()),
        "blackboard_dir": str(bb_dir.resolve()),
        "output_dir": str(output_p.resolve()),
        "max_rounds": MAX_ROUNDS,
        "agent_order": AGENT_ORDER[:],
        "generated_at": datetime.now().isoformat(),
    }
    _save_json(output_p / "pipeline_config.json", pipeline_config)

    # Initialize status
    status = {
        "run_id": run_id,
        "version": "4.0.0",
        "started_at": datetime.now().isoformat(),
        "current_round": 1,
        "current_phase": "generator",  # generator | judge | fixer | done
        "agents": {
            "generator": {"state": "pending", "retry_count": 0},
            "judge": {"state": "pending", "retry_count": 0},
        },
        "rounds": [],  # [{round, generator_state, judge_verdict, fix_applied}]
    }
    _save_status(output_p, status)

    # Watcher integration
    deepflow_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    watcher_config_rel = "domains/ship_pro/config/watcher_config.json"
    watcher_config_abs = os.path.join(deepflow_root, watcher_config_rel)
    pipeline_config["run_start_at"] = run_start_at
    pipeline_config["watcher_config"] = watcher_config_rel
    pipeline_config["watcher_config_abs"] = watcher_config_abs
    pipeline_config["deepflow_root"] = deepflow_root

    try:
        from scripts.pipeline_watcher import render_wrapper_prompt
        wrapper_prompt = render_wrapper_prompt(
            deepflow_root=deepflow_root,
            config_path=watcher_config_abs,
            base_path=str(bb_dir.resolve()),
            run_start_at=run_start_at,
            cron_job_id="__CRON_JOB_ID__",
        )
        pipeline_config["watcher_cron_payload"] = {
            "name": f"deepflow_watcher_{run_id[:16]}",
            "schedule": {"kind": "every", "everyMs": 180000},
            # 🔴 isolated 避免 SessionTakeoverError（current 会和活跃会话冲突）
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


# ---------------------------------------------------------------------------
# Core: get_agent_task
# ---------------------------------------------------------------------------

def get_agent_task(agent_name: str, output_dir: str) -> dict:
    """
    Build complete task prompt for Generator or Judge.

    For Generator on round 2+: injects FixContext into the prompt.
    """
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    if config is None:
        raise FileNotFoundError("Pipeline not prepared. Run 'prepare' first.")

    if agent_name not in AGENT_ORDER:
        raise ValueError(f"Unknown agent: {agent_name}. Must be one of {AGENT_ORDER}")

    bb_dir = config["blackboard_dir"]
    run_id = config["run_id"]
    current_round = _current_round(output_p)

    # Load input
    input_data = _load_json(Path(bb_dir) / STAGE_PATHS["input"])
    if input_data is None:
        raise FileNotFoundError(f"Input data missing: {bb_dir}")

    # Load prompt
    prompt = _load_prompt(agent_name)
    prompt_sha = _compute_prompt_sha(agent_name)

    # Build task
    if agent_name == "generator":
        task = _build_generator_task(
            prompt, input_data, bb_dir, run_id, prompt_sha, current_round, output_p,
        )
    elif agent_name == "judge":
        task = _build_judge_task(
            prompt, input_data, bb_dir, run_id, prompt_sha, current_round, output_p,
        )
    else:
        raise ValueError(f"Unhandled agent: {agent_name}")

    # Update status
    status = _load_status(output_p)
    status["current_phase"] = agent_name
    if agent_name in status.get("agents", {}):
        status["agents"][agent_name]["state"] = "running"
    _save_status(output_p, status)

    return {
        "agent": agent_name,
        "task": task,
        "round": current_round,
        "timeout_seconds": AGENT_TIMEOUTS.get(agent_name, 300),
        "model": AGENT_MODELS.get(agent_name, "strong"),
        "output_file": f"{bb_dir}/{STAGE_PATHS[agent_name]}",
        "prompt_sha": prompt_sha,
    }


def _build_generator_task(
    prompt: str, input_data: dict, bb_dir: str,
    run_id: str, prompt_sha: str, current_round: int, output_p: Path,
) -> str:
    """Build Generator task prompt, with FixContext on round 2+."""
    fix_context_section = ""
    if current_round >= 2:
        fc_path = output_p / "blackboard" / STAGE_PATHS["fix_context"]
        if not fc_path.exists():
            fc_path = output_p / STAGE_PATHS["fix_context"]
        fc = _load_json(fc_path)
        if fc:
            fix_context_section = f"""

## ⚠️ 修复上下文 (Round {current_round})

上一轮 Judge 裁定 **{fc.get('original_verdict', 'fail')}**，以下是定向修复指令。
**只修复以下问题，不要改动其他部分。**

```json
{json.dumps(fc, indent=2, ensure_ascii=False)}
```

### 修复约束
- focus_areas: {json.dumps(fc.get('focus_areas', []))}
- regression_warnings: {json.dumps(fc.get('regression_warnings', []))}
- 每条 instruction 的 risk_id 必须在本轮输出中解决
"""

    output_path = f"{bb_dir}/{STAGE_PATHS['generator']}"

    return f"""## Agent: Generator (V4.0)

{prompt}

## 输入数据

```json
{json.dumps(input_data, indent=2, ensure_ascii=False)}
```
{fix_context_section}

## 运行信息

- run_id: {run_id}
- round: {current_round}
- blackboard_dir: {bb_dir}
- prompt_sha: {prompt_sha}

## ⚠️ 输出文件路径（必须严格遵守）

**输出文件路径**: `{output_path}`

- 文件名必须是 `{STAGE_PATHS['generator']}`
- 输出必须是合法 JSON，符合 GeneratorOutput Pydantic 模型
- 在 _meta 中记录 prompt_sha、model_id、run_id、round
"""


def _build_judge_task(
    prompt: str, input_data: dict, bb_dir: str,
    run_id: str, prompt_sha: str, current_round: int, output_p: Path,
) -> str:
    """Build Judge task prompt, including Generator output reference."""
    gen_output_path = f"{bb_dir}/{STAGE_PATHS['generator']}"
    gen_output = _load_json(Path(gen_output_path))
    if gen_output is None:
        raise FileNotFoundError(f"Generator output not found: {gen_output_path}")

    # For round 2+, include previous judge output for regression detection
    prev_judge_section = ""
    if current_round >= 2:
        judge_path = Path(bb_dir) / STAGE_PATHS["judge"]
        prev_judge = _load_json(judge_path)
        if prev_judge:
            prev_judge_section = f"""

## 上一轮 Judge 报告（回归检测用）

```json
{json.dumps(prev_judge, indent=2, ensure_ascii=False)}
```

**回归检测要求**: 对比上轮报告，检查上轮已修复的问题是否在本轮重新出现。
"""

    output_path = f"{bb_dir}/{STAGE_PATHS['judge']}"

    return f"""## Agent: Judge (V4.0)

{prompt}

## Generator 输出（待审计）

```json
{json.dumps(gen_output, indent=2, ensure_ascii=False)}
```

## 原始输入（参考）

```json
{json.dumps(input_data, indent=2, ensure_ascii=False)}
```
{prev_judge_section}

## 运行信息

- run_id: {run_id}
- round: {current_round}
- blackboard_dir: {bb_dir}
- prompt_sha: {prompt_sha}

## ⚠️ 输出文件路径（必须严格遵守）

**输出文件路径**: `{output_path}`

- 文件名必须是 `{STAGE_PATHS['judge']}`
- 输出必须是合法 JSON，符合 JudgeOutput Pydantic 模型
- 在 _meta 中记录 round、stance、model_id、timestamp
"""


# ---------------------------------------------------------------------------
# Core: check_gate (Pydantic 契约笼子)
# ---------------------------------------------------------------------------

def check_gate(agent_name: str, output_dir: str) -> dict:
    """
    Run Pydantic contract cage on Agent output.

    V4.0: Only generator and judge gates, using new Pydantic models.
    """
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    if config is None:
        raise FileNotFoundError("Pipeline not prepared.")

    bb_dir = config["blackboard_dir"]
    output_file = Path(bb_dir) / STAGE_PATHS[agent_name]

    # Check file exists
    if not output_file.exists():
        return _gate_fail(agent_name, ["output_file_missing"],
                          f"Agent output not found: {output_file}")

    if output_file.is_dir():
        fallback = output_file / "output.json"
        if fallback.exists():
            output_file = fallback
        else:
            return _gate_fail(agent_name, ["output_is_directory"],
                              f"Output is a directory, not a file: {output_file}")

    # Load raw JSON
    try:
        with open(output_file) as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        return _gate_fail(agent_name, ["invalid_json"], f"Invalid JSON: {e}")

    # Pydantic validation (V4.1: 模型已宽容化，接受 LLM 常用变体)
    if agent_name == "generator":
        result = _gate_generator(raw)
    elif agent_name == "judge":
        result = _gate_judge(raw)
    else:
        return _gate_fail(agent_name, ["unknown_agent"], f"No gate for: {agent_name}")

    # Update status
    status = _load_status(output_p)
    decision = result["decision"]
    if agent_name in status.get("agents", {}):
        state_map = {"PASS": "gate_pass", "CONDITIONAL": "gate_conditional", "FAIL": "gate_fail"}
        status["agents"][agent_name]["state"] = state_map.get(decision, "gate_fail")
        status["agents"][agent_name]["gate_decision"] = decision
    _save_status(output_p, status)

    return result


def _gate_generator(raw: dict) -> dict:
    """Pydantic gate for Generator output."""
    try:
        from domains.ship_pro.contracts.ship_generator import GeneratorOutput
        obj = GeneratorOutput.model_validate(raw)
        # Additional checks
        issues = []
        if not obj.work_packages:
            issues.append("work_packages is empty")
        if not obj.modules:
            issues.append("modules is empty")
        if not obj.requirements:
            issues.append("requirements is empty")
        if issues:
            return {
                "agent": "generator",
                "decision": "FAIL",
                "critical_failures": issues,
                "feedback": f"Generator output missing required fields: {', '.join(issues)}",
                "should_retry": True,
                "retry_count": 0,
            }
        return {
            "agent": "generator",
            "decision": "PASS",
            "critical_failures": [],
            "feedback": f"GeneratorOutput valid: {len(obj.work_packages)} WPs, {len(obj.modules)} modules",
            "should_retry": False,
            "retry_count": 0,
            "gate_results": {
                "pydantic_valid": True,
                "wp_count": len(obj.work_packages),
                "module_count": len(obj.modules),
            },
        }
    except Exception as e:
        return {
            "agent": "generator",
            "decision": "FAIL",
            "critical_failures": ["pydantic_validation_failed"],
            "feedback": f"GeneratorOutput Pydantic validation failed: {str(e)[:500]}",
            "should_retry": True,
            "retry_count": 0,
        }


def _gate_judge(raw: dict) -> dict:
    """Pydantic gate for Judge output."""
    try:
        from domains.ship_pro.contracts.judge_v4 import JudgeOutput
        obj = JudgeOutput.model_validate(raw)
        verdict = obj.verdict
        score = obj.overall_score
        risk_count = len(obj.risks)
        critical_risks = [r for r in obj.risks if r.severity == "critical"]
        major_risks = [r for r in obj.risks if r.severity == "major"]

        # ── 契约笼子: score-verdict 一致性校验 ──
        consistency_issues = []
        if score >= 85 and verdict != "pass":
            consistency_issues.append(f"score={score}>=85 但 verdict={verdict}（应为 pass）")
        if score < 50 and verdict != "fail":
            consistency_issues.append(f"score={score}<50 但 verdict={verdict}（应为 fail）")
        if verdict == "pass" and critical_risks:
            consistency_issues.append(f"verdict=pass 但有 {len(critical_risks)} 个 critical risks（矛盾）")
        if verdict == "fail" and not obj.risks and not obj.regressions:
            consistency_issues.append(f"verdict=fail 但无 risks 也无 regressions（矛盾）")

        if consistency_issues:
            return {
                "agent": "judge",
                "decision": "FAIL",
                "critical_failures": ["score_verdict_inconsistency"],
                "feedback": f"JudgeOutput score-verdict 不一致: {'; '.join(consistency_issues)}",
                "should_retry": True,
                "retry_count": 0,
            }

        return {
            "agent": "judge",
            "decision": "PASS",
            "critical_failures": [],
            "feedback": f"JudgeOutput valid: verdict={verdict}, score={score}, {risk_count} risks ({len(critical_risks)} critical, {len(major_risks)} major)",
            "should_retry": False,
            "retry_count": 0,
            "gate_results": {
                "pydantic_valid": True,
                "verdict": verdict,
                "overall_score": score,
                "risk_count": risk_count,
                "critical_risk_count": len(critical_risks),
                "major_risk_count": len(major_risks),
                "fixable_risks": len([r for r in obj.risks if r.fixable]),
                "consumability": obj.consumability_score,
            },
        }
    except Exception as e:
        return {
            "agent": "judge",
            "decision": "FAIL",
            "critical_failures": ["pydantic_validation_failed"],
            "feedback": f"JudgeOutput Pydantic validation failed: {str(e)[:500]}",
            "should_retry": True,
            "retry_count": 0,
        }


def _gate_fail(agent_name: str, failures: list, feedback: str) -> dict:
    return {
        "agent": agent_name,
        "decision": "FAIL",
        "critical_failures": failures,
        "feedback": feedback,
        "should_retry": True,
        "retry_count": 0,
    }


# ---------------------------------------------------------------------------
# Core: next_step (V4.0 状态机)
# ---------------------------------------------------------------------------

def next_step(output_dir: str) -> dict:
    """
    Determine the next pipeline action based on current state.

    V4.0 state machine:
      prepared → spawn generator
      generator_done → spawn judge
      judge_pass → validate (done)
      judge_fail + fixable + round < max → build fix-context → spawn generator
      judge_fail + round >= max → validate (force done)
      judge_fail + no fixable → validate (force done, flag for human)
    """
    output_p = Path(output_dir)
    status = _load_status(output_p)
    config = _load_json(output_p / "pipeline_config.json")
    if not config:
        return {"action": "error", "message": "Pipeline not prepared"}

    bb_dir = config["blackboard_dir"]
    current_round = status.get("current_round", 1)
    max_rounds = config.get("max_rounds", MAX_ROUNDS)
    phase = status.get("current_phase", "generator")

    # Check generator state
    gen_state = status.get("agents", {}).get("generator", {}).get("state", "pending")
    judge_state = status.get("agents", {}).get("judge", {}).get("state", "pending")

    # --- State machine ---

    # 1. Generator not yet run or needs rerun
    if gen_state in ("pending", "running") and judge_state == "pending":
        return {
            "action": "spawn",
            "agent": "generator",
            "round": current_round,
            "reason": "Generator pending" if gen_state == "pending" else "Generator running",
        }

    # 2. Generator gate failed — retry generator
    if gen_state == "gate_fail":
        gen_retries = status.get("agents", {}).get("generator", {}).get("retry_count", 0)
        if gen_retries < 2:
            return {
                "action": "spawn",
                "agent": "generator",
                "round": current_round,
                "reason": f"Generator gate failed, retry {gen_retries + 1}/2",
            }
        else:
            return {
                "action": "fail",
                "reason": "Generator gate failed after max retries",
                "force_finalize": True,
            }

    # 3. Generator passed → spawn Judge
    if gen_state == "gate_pass" and judge_state in ("pending", "running"):
        return {
            "action": "spawn",
            "agent": "judge",
            "round": current_round,
            "reason": "Generator passed, Judge pending",
        }

    # 4. Judge gate failed — retry judge
    if judge_state == "gate_fail":
        judge_retries = status.get("agents", {}).get("judge", {}).get("retry_count", 0)
        if judge_retries < 2:
            return {
                "action": "spawn",
                "agent": "judge",
                "round": current_round,
                "reason": f"Judge gate failed, retry {judge_retries + 1}/2",
            }
        else:
            return {
                "action": "fail",
                "reason": "Judge gate failed after max retries",
                "force_finalize": True,
            }

    # 5. Judge passed structurally — check verdict
    if judge_state == "gate_pass":
        judge_output = _load_json(Path(bb_dir) / STAGE_PATHS["judge"])
        if judge_output is None:
            return {"action": "error", "message": "Judge output missing"}

        verdict = judge_output.get("verdict", "fail")

        # 5a. Pass → done
        if verdict == "pass":
            return {
                "action": "validate",
                "round": current_round,
                "reason": "Judge verdict: pass",
            }

        # 5b. Fail/Conditional — check fixable + round
        fixable_risks = [r for r in judge_output.get("risks", []) if r.get("fixable", True)]

        if not fixable_risks:
            return {
                "action": "validate",
                "round": current_round,
                "reason": "No fixable risks — requires human review",
                "human_review_needed": True,
            }

        if current_round >= max_rounds:
            return {
                "action": "validate",
                "round": current_round,
                "reason": f"Max rounds ({max_rounds}) reached with verdict={verdict}",
                "max_rounds_reached": True,
                "unresolved_risks": len(fixable_risks),
            }

        # 5c. Has fixable risks + under max rounds → fix context + rerun
        return {
            "action": "fix_and_rerun",
            "round": current_round,
            "next_round": current_round + 1,
            "reason": f"Judge verdict={verdict}, {len(fixable_risks)} fixable risks",
            "fixable_count": len(fixable_risks),
            "steps": [
                "1. Run: python3 run_pipeline.py fix-context <output_dir>",
                "2. Run: python3 run_pipeline.py task generator <output_dir>",
                "3. Spawn Generator agent",
            ],
        }

    return {"action": "error", "message": f"Unknown state: phase={phase}, gen={gen_state}, judge={judge_state}"}


# ---------------------------------------------------------------------------
# Core: build_fix_context
# ---------------------------------------------------------------------------

def build_fix_context(output_dir: str) -> dict:
    """
    Build FixContext from Judge output + prepare for Generator rerun.

    1. Read Judge output
    2. Extract fixable risks → FixInstructions
    3. Build FixContext
    4. Write fix_context.json
    5. Advance round counter
    6. Reset generator + judge state for next round
    """
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    if not config:
        raise FileNotFoundError("Pipeline not prepared.")

    bb_dir = config["blackboard_dir"]
    status = _load_status(output_p)
    current_round = status.get("current_round", 1)

    # Load judge output
    judge_path = Path(bb_dir) / STAGE_PATHS["judge"]
    judge_output = _load_json(judge_path)
    if judge_output is None:
        raise FileNotFoundError(f"Judge output not found: {judge_path}")

    verdict = judge_output.get("verdict", "fail")

    # Extract fixable risks → FixInstructions
    from domains.ship_pro.contracts.fix_context import FixContext, FixInstruction, FixRoundResult

    instructions = []
    for risk in judge_output.get("risks", []):
        if risk.get("fixable", True):
            instructions.append(FixInstruction(
                risk_id=risk["id"],
                severity=risk["severity"],
                fix_suggestion=risk.get("fix_suggestion", ""),
                affected_stages=risk.get("affected_stages", []),
            ))

    # ── 契约笼子: 回填上一轮的 fixed/new risk tracking ──
    # 对比上一轮 Judge 的 unresolved_risk_ids 和本轮 Judge 的 risks
    prev_rounds = status.get("rounds", [])
    if prev_rounds:
        last_round = prev_rounds[-1]
        prev_unresolved = set(last_round.get("unresolved_risk_ids", []))
        # 本轮 Judge 报告中仍存在的 risk_ids
        current_risk_ids = set(
            r.get("id", "") for r in judge_output.get("risks", [])
        )
        # fixed = 上轮 unresolved 但本轮不再出现
        newly_fixed = sorted(prev_unresolved - current_risk_ids)
        # new = 本轮出现但上轮 unresolved 中没有的
        newly_introduced = sorted(current_risk_ids - prev_unresolved)
        # 回填上一轮记录
        last_round["fixed_risk_ids"] = newly_fixed
        last_round["new_risk_ids"] = newly_introduced

    # Build history entry for this round
    history = []
    for prev_round in status.get("rounds", []):
        history.append(FixRoundResult(
            round=prev_round.get("round", 0),
            fixed_risk_ids=prev_round.get("fixed_risk_ids", []),
            new_risk_ids=prev_round.get("new_risk_ids", []),
            unresolved_risk_ids=prev_round.get("unresolved_risk_ids", []),
        ))

    # Build regression warnings from history
    regression_warnings = []
    if history:
        last = history[-1]
        if last.new_risk_ids:
            regression_warnings.append(
                f"上轮修复引入了新问题: {', '.join(last.new_risk_ids)}"
            )

    # ── 契约笼子: focus_areas 从 risk_id 提取 ──
    # 不再用 affected_stages（永远是 generator）或 fix_suggestion（太长）
    # 而是用 risk_id 列表作为 focus_areas，Generator 能直接定位要修的 risk
    focus_areas = [inst.risk_id for inst in instructions]

    # Create FixContext
    next_round = current_round + 1
    fix_ctx = FixContext(
        original_verdict=verdict if verdict in ("fail", "conditional") else "fail",
        current_round=next_round,
        max_rounds=config.get("max_rounds", MAX_ROUNDS),
        instructions=instructions,
        history=history,
        focus_areas=focus_areas,
        regression_warnings=regression_warnings,
    )

    # Write fix_context.json
    fc_path = output_p / "blackboard" / STAGE_PATHS["fix_context"]
    _save_json(fc_path, fix_ctx.model_dump())

    # Advance round + reset agent states
    status["current_round"] = next_round
    status["current_phase"] = "generator"
    status["agents"]["generator"]["state"] = "pending"
    status["agents"]["generator"]["retry_count"] = 0
    status["agents"]["judge"]["state"] = "pending"
    status["agents"]["judge"]["retry_count"] = 0

    # Record this round's result (fixed_risk_ids/new_risk_ids 由下一轮 fix-context 回填)
    status.setdefault("rounds", []).append({
        "round": current_round,
        "generator_state": "gate_pass",
        "judge_verdict": verdict,
        "fixable_risks": len(instructions),
        "fixed_risk_ids": [],
        "new_risk_ids": [],
        "unresolved_risk_ids": [r.risk_id for r in instructions],
    })

    _save_status(output_p, status)

    return {
        "fix_context_written": str(fc_path),
        "next_round": next_round,
        "instructions_count": len(instructions),
        "focus_areas": focus_areas,
        "regression_warnings": regression_warnings,
        "status": "ready_for_generator_rerun",
    }


# ---------------------------------------------------------------------------
# Core: validate_pipeline
# ---------------------------------------------------------------------------

def validate_pipeline(output_dir: str) -> dict:
    """
    Final validation: check both Generator and Judge outputs exist and are valid.
    """
    output_p = Path(output_dir)
    config = _load_json(output_p / "pipeline_config.json")
    if not config:
        return {"valid": False, "errors": ["pipeline_config missing"]}

    bb_dir = config["blackboard_dir"]
    errors = []
    warnings = []

    # Check Generator output
    gen_path = Path(bb_dir) / STAGE_PATHS["generator"]
    if not gen_path.exists():
        errors.append("generator_output_missing")
    else:
        try:
            from domains.ship_pro.contracts.ship_generator import GeneratorOutput
            gen = GeneratorOutput.model_validate(_load_json(gen_path))
            if not gen.work_packages:
                errors.append("no_work_packages")
        except Exception as e:
            errors.append(f"generator_validation: {str(e)[:200]}")

    # Check Judge output
    judge_path = Path(bb_dir) / STAGE_PATHS["judge"]
    if not judge_path.exists():
        errors.append("judge_output_missing")
    else:
        try:
            from domains.ship_pro.contracts.judge_v4 import JudgeOutput
            judge = JudgeOutput.model_validate(_load_json(judge_path))
            if judge.verdict != "pass":
                warnings.append(f"judge_verdict={judge.verdict}")
            critical = [r for r in judge.risks if r.severity == "critical"]
            if critical:
                warnings.append(f"{len(critical)} unresolved critical risks")

            # ── 契约笼子: 写最终 round 记录 ──
            status = _load_status(output_p)
            current_round = status.get("current_round", 1)
            rounds = status.get("rounds", [])
            # 如果最后一轮的 round 不等于 current_round，说明 validate 路径没写 round
            if not rounds or rounds[-1]["round"] != current_round:
                # 回填上一轮的 fixed_risk_ids
                if rounds:
                    prev_unresolved = set(rounds[-1].get("unresolved_risk_ids", []))
                    current_risk_ids = set(r.id for r in judge.risks)
                    rounds[-1]["fixed_risk_ids"] = sorted(prev_unresolved - current_risk_ids)
                    rounds[-1]["new_risk_ids"] = sorted(current_risk_ids - prev_unresolved)
                # 写最终 round
                rounds.append({
                    "round": current_round,
                    "generator_state": "gate_pass",
                    "judge_verdict": judge.verdict,
                    "fixable_risks": len([r for r in judge.risks if r.fixable]),
                    "fixed_risk_ids": [],
                    "new_risk_ids": [],
                    "unresolved_risk_ids": [r.id for r in judge.risks],
                })
                status["rounds"] = rounds
                _save_status(output_p, status)
        except Exception as e:
            errors.append(f"judge_validation: {str(e)[:200]}")

    status = _load_status(output_p)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "rounds_completed": status.get("current_round", 1) - 1,
        "final_verdict": _load_json(judge_path).get("verdict", "unknown") if judge_path.exists() else "unknown",
    }


# ---------------------------------------------------------------------------
# Core: status + finalize
# ---------------------------------------------------------------------------

def get_pipeline_status(output_dir: str) -> dict:
    """Show current pipeline state."""
    output_p = Path(output_dir)
    status = _load_status(output_p)
    config = _load_json(output_p / "pipeline_config.json")

    if not status:
        return {"status": "not_prepared"}

    result = {
        "run_id": status.get("run_id"),
        "version": status.get("version", "unknown"),
        "current_round": status.get("current_round", 1),
        "current_phase": status.get("current_phase"),
        "started_at": status.get("started_at"),
        "agents": status.get("agents", {}),
        "rounds": status.get("rounds", []),
    }

    # Check if completed
    if (output_p / ".completed").exists():
        result["status"] = "completed"
    elif status.get("status"):
        result["status"] = status["status"]
    else:
        result["status"] = "running"

    return result


def _finalize_pipeline(output_dir: Path, overall_pass: bool) -> None:
    """Mark pipeline as completed."""
    status = _load_status(output_dir)
    status["status"] = "passed" if overall_pass else "failed"
    status["completed_at"] = datetime.now().isoformat()
    status["current_phase"] = "done"
    _save_status(output_dir, status)

    # Write .completed marker
    completed_file = output_dir / "blackboard" / ".completed"
    _save_json(completed_file, {
        "completed_at": datetime.now().isoformat(),
        "overall_pass": overall_pass,
        "rounds": status.get("current_round", 1),
    })


# ---------------------------------------------------------------------------
# Core: increment_retry (atomic, flock-based)
# ---------------------------------------------------------------------------

def _increment_retry(output_dir: Path, agent_name: str) -> dict:
    """Atomically increment retry count."""
    status = _load_status(output_dir)
    max_retries = 2  # V4 default

    lock_file = output_dir / ".retry.lock"
    with open(lock_file, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            status = _load_status(output_dir)
            agent_status = status.get("agents", {}).get(agent_name, {})
            current = agent_status.get("retry_count", 0)
            new_count = current + 1
            allowed = new_count <= max_retries

            agent_status["retry_count"] = new_count
            status.setdefault("agents", {})[agent_name] = agent_status
            _save_status(output_dir, status)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

    return {
        "agent": agent_name,
        "retry_count": new_count,
        "max_retries": max_retries,
        "allowed": allowed,
    }


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

    elif cmd == "next":
        if len(sys.argv) < 3:
            print("用法: python3 run_pipeline.py next <output_dir>")
            sys.exit(1)
        result = next_step(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "fix-context":
        if len(sys.argv) < 3:
            print("用法: python3 run_pipeline.py fix-context <output_dir>")
            sys.exit(1)
        result = build_fix_context(sys.argv[2])
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

    elif cmd == "finalize":
        if len(sys.argv) < 4:
            print("用法: python3 run_pipeline.py finalize <output_dir> <pass|fail>")
            sys.exit(1)
        _finalize_pipeline(Path(sys.argv[2]), overall_pass=sys.argv[3].lower() in ("pass", "true", "1"))
        status = _load_status(Path(sys.argv[2]))
        print(json.dumps({
            "ok": True,
            "status": status.get("status"),
            "completed_at": status.get("completed_at"),
        }, indent=2))

    elif cmd == "increment-retry":
        if len(sys.argv) < 4:
            print("用法: python3 run_pipeline.py increment-retry <output_dir> <agent_name>")
            sys.exit(1)
        result = _increment_retry(Path(sys.argv[2]), sys.argv[3])
        print(json.dumps(result, indent=2))

    else:
        print(f"未知命令: {cmd}")
        print("可用命令: prepare, task, gate, next, fix-context, validate, status, finalize, increment-retry")
        sys.exit(1)


if __name__ == "__main__":
    _cli_main()
