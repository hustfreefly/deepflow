#!/usr/bin/env python3
"""
DeepFlow Pipeline Loop Runner — 端到端循环执行 + 检查 + 修复

设计理念:
  1. 确定性检查 (Python) — 状态判断、完成检测、进度分析
  2. LLM 执行 (Orchestrator) — spawn/yield 循环
  3. Loop 机制 (本脚本 + 主 Agent) — 检查→续接→验证

用法:
  python3 scripts/loop_runner.py check <domain> <base_path> [--round N]
    → 检查管线状态，输出 JSON 决策

  python3 scripts/loop_runner.py resume-prompt <domain> <base_path> [--round N]
    → 生成续接 prompt addendum（主 Agent 拼接到原 prompt 前面）

  python3 scripts/loop_runner.py report <domain> <base_path>
    → 生成最终报告（成功/失败/部分完成）

输出 JSON:
  {
    "action": "done" | "resume" | "fix" | "abort",
    "round": 3,
    "max_rounds": 5,
    "completed_phases": [1,2,3],
    "next_phase": 4,
    "total_phases": 10,
    "issues": [...],
    "reason": "..."
  }
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Bootstrap
DEEPFLOW_HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEEPFLOW_HOME))

SHANGHAI_TZ = timezone(timedelta(hours=8))
MAX_ROUNDS = 5

# ── Domain Definitions ──────────────────────────────────────────

DOMAINS = {
    "solution_pro": {
        "total_phases": 10,
        "completion_file": ".completed",
        "progress_file": ".stage_progress",
        "stage_dir": "stages",
        "phases": [
            (1, "data_collection", "serial", ["data/collection.json"]),
            (2, "planning", "serial", ["planning.json"]),
            (3, "reviewers", "parallel", ["reviewer_technical.json", "reviewer_business.json", "reviewer_risk.json"]),
            (4, "research", "parallel", ["research_expert_1.json", "research_expert_2.json", "research_expert_3.json"]),
            (5, "consolidator", "serial", ["consolidator.json"]),
            (6, "audit", "serial", ["audit.json"]),
            (7, "fix", "serial", ["fix.json"]),
            (8, "fixer_expert", "serial", ["fixer_expert.json"]),
            (9, "harness_final", "serial", ["harness_final.json"]),
            (10, "summarizer", "serial", ["final_result.json"]),
        ],
        "final_artifact": "final_result.json",
    },
    "ship_pro": {
        "total_phases": 5,
        "completion_file": "completed",
        "progress_file": "stage_progress",
        "stage_dir": "blackboard",
        "phases": [
            (1, "architect", "serial", ["architect"]),
            (2, "decomposer", "serial", ["decomposer"]),
            (3, "specifier", "serial", ["specifier"]),
            (4, "reviewer", "serial", ["reviewer"]),
            (5, "packager", "serial", ["packager"]),
        ],
        "final_artifact": "ship_package.json",
    },
    "spec_pro": {
        "total_phases": 6,
        "completion_file": None,  # Spec Pro 用 harness_result.json 判断
        "progress_file": None,
        "stage_dir": "spec",
        "phases": [
            (1, "parse", "serial", ["parsed_input.json"]),
            (2, "guide", "serial", ["questions.json"]),
            (3, "response", "serial", ["parsed_response.json"]),
            (4, "assess", "serial", ["quality_trajectory.json"]),
            (5, "structure", "serial", ["living_spec.json"]),
            (6, "harness", "serial", ["harness_result.json"]),
        ],
        "final_artifact": "living_spec.json",
    },
}


# ── State Checker ───────────────────────────────────────────────

def check_state(domain: str, base_path: str, round_num: int = 1) -> dict:
    """检查管线状态，输出决策 JSON。"""
    domain_def = DOMAINS.get(domain)
    if not domain_def:
        return {"action": "abort", "reason": f"Unknown domain: {domain}"}

    base = Path(base_path)
    if not base.exists():
        return {"action": "abort", "reason": f"Base path not found: {base_path}"}

    stage_dir = base / domain_def["stage_dir"]
    total = domain_def["total_phases"]
    phases = domain_def["phases"]

    # ── Check completion ──
    is_completed = False
    completed_data = None

    if domain_def["completion_file"]:
        # Check both exact name and .json variant
        comp_name = domain_def["completion_file"]
        comp_file = stage_dir / comp_name
        if not comp_file.exists():
            comp_file = stage_dir / f"{comp_name}.json"
        if comp_file.exists():
            try:
                with open(comp_file) as f:
                    completed_data = json.load(f)
                status = completed_data.get("status", "")
                # Accept "completed" status OR all phases listed
                comp_phases = completed_data.get("completed_phases", [])
                stages_done = completed_data.get("stages_completed", 0)
                if status == "completed" or len(comp_phases) == total or stages_done == total:
                    is_completed = True
            except (json.JSONDecodeError, OSError):
                pass

    # ── Check existing stage files (recursive + flexible naming) ──
    existing_files = set()
    if stage_dir.exists():
        for item in stage_dir.rglob("*.json"):
            if item.is_file() and not item.name.startswith("."):
                # Add both filename and relative path
                existing_files.add(item.name)
                rel = str(item.relative_to(stage_dir))
                existing_files.add(rel)
                # Also add without .json.json double extension (common bug)
                if item.name.endswith(".json.json"):
                    existing_files.add(item.name.replace(".json.json", ".json"))
                if rel.endswith(".json.json"):
                    existing_files.add(rel.replace(".json.json", ".json"))
                # Also add dot-separated variant (reviewers.business.json → reviewer_business.json)
                stem = item.stem  # e.g. "reviewers.business"
                if "." in stem:
                    alt = stem.replace(".", "_") + ".json"
                    existing_files.add(alt)

    # ── Determine completed phases ──
    completed_phases = []
    for phase_num, stage_name, mode, expected_files in phases:
        phase_complete = all(
            ef in existing_files
            for ef in expected_files
        )
        if phase_complete:
            completed_phases.append(phase_num)

    # ── Determine next phase ──
    next_phase = None
    for phase_num, stage_name, mode, expected_files in phases:
        if phase_num not in completed_phases:
            next_phase = phase_num
            break

    # ── Check final artifact ──
    has_final = False
    final_artifact = domain_def["final_artifact"]
    if final_artifact:
        # Check multiple possible locations
        for check_dir in [stage_dir, base, base / "ship_output"]:
            if (check_dir / final_artifact).exists():
                has_final = True
                break

    # ── Decision ──
    result = {
        "domain": domain,
        "base_path": base_path,
        "round": round_num,
        "max_rounds": MAX_ROUNDS,
        "total_phases": total,
        "completed_phases": completed_phases,
        "completed_count": len(completed_phases),
        "next_phase": next_phase,
        "has_final_artifact": has_final,
        "is_completed": is_completed,
        "issues": [],
    }

    if is_completed or (len(completed_phases) == total and has_final):
        result["action"] = "done"
        result["reason"] = f"All {total} phases completed"
    elif next_phase is None:
        # All phase files exist but .completed not written
        result["action"] = "fix"
        result["reason"] = "All stage files exist but .completed not written"
        result["issues"].append({
            "type": "missing_completion_marker",
            "detail": f"{domain_def['completion_file']} not found in {stage_dir}",
        })
    elif round_num >= MAX_ROUNDS:
        result["action"] = "abort"
        result["reason"] = f"Max rounds ({MAX_ROUNDS}) reached, phases {completed_phases} done, next={next_phase}"
    else:
        result["action"] = "resume"
        result["reason"] = f"Completed {len(completed_phases)}/{total} phases, next=Phase {next_phase}"
        if completed_phases:
            gap = set(range(1, total + 1)) - set(completed_phases)
            if gap and min(gap) < max(completed_phases):
                result["issues"].append({
                    "type": "phase_gap",
                    "detail": f"Missing phases in sequence: {sorted(gap)}",
                })

    # ── Check for known issues ──
    # Stale files (created before run_start_at)
    # TODO: add stale detection if needed

    return result


# ── Resume Prompt Builder ───────────────────────────────────────

def build_resume_prompt(domain: str, base_path: str, round_num: int, state: dict) -> str:
    """生成续接 prompt addendum。"""
    completed = state["completed_phases"]
    next_phase = state["next_phase"]
    total = state["total_phases"]
    domain_def = DOMAINS[domain]
    phases = domain_def["phases"]

    # Build phase completion table
    phase_lines = []
    for phase_num, stage_name, mode, expected_files in phases:
        status = "✅ 已完成（跳过）" if phase_num in completed else ("⏳ 当前" if phase_num == next_phase else "⬜ 待执行")
        phase_lines.append(f"  Phase {phase_num}: {stage_name} ({mode}) — {status}")

    phase_table = "\n".join(phase_lines)

    remaining = [p for p in phases if p[0] not in completed]
    remaining_names = [f"Phase {p[0]}({p[1]})" for p in remaining]

    prompt = f"""# 🔴 RESUME — 第 {round_num} 轮续接

## 上下文
你是第 {round_num} 个 orchestrator 实例。前 {round_num - 1} 个实例在完成部分 phase 后停止了。

## 当前进度
已完成: {completed} ({len(completed)}/{total} phases)
下一个: Phase {next_phase}

{phase_table}

## 🔴 你的任务
**只执行未完成的 phases**: {', '.join(remaining_names)}

## 🔴 规则
1. **跳过已完成的 phases** — 不要重新 spawn Phase {completed}
2. **从 Phase {next_phase} 开始执行** — 立即开始
3. **必须执行到最后一个 phase** — 不能中途停止
4. **每个 phase 完成后立即验证文件存在** — 用 `bb.read_stage()` 检查
5. **全部完成后写 .completed** — 这是你结束 turn 的唯一条件

## 🔴 自检
每次 yield 返回后问自己: "还有未执行的 phase 吗？"
- 有 → 立即继续下一个 phase
- 没有 → 写 .completed，然后结束

"""
    return prompt


# ── Report Builder ──────────────────────────────────────────────

def build_report(domain: str, base_path: str, state: dict) -> str:
    """生成最终报告。"""
    action = state["action"]
    completed = state["completed_phases"]
    total = state["total_phases"]
    round_num = state["round"]

    if action == "done":
        return f"✅ {domain} 完成 | {len(completed)}/{total} phases | {round_num} 轮"
    elif action == "abort":
        return f"❌ {domain} 中止 | {len(completed)}/{total} phases | {round_num} 轮 | {state['reason']}"
    else:
        return f"⚠️ {domain} 部分完成 | {len(completed)}/{total} phases | {round_num} 轮"


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pipeline Loop Runner")
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check")
    p_check.add_argument("domain")
    p_check.add_argument("base_path")
    p_check.add_argument("--round", type=int, default=1)

    p_resume = sub.add_parser("resume-prompt")
    p_resume.add_argument("domain")
    p_resume.add_argument("base_path")
    p_resume.add_argument("--round", type=int, default=1)

    p_report = sub.add_parser("report")
    p_report.add_argument("domain")
    p_report.add_argument("base_path")
    p_report.add_argument("--round", type=int, default=1)

    args = parser.parse_args()

    if args.command == "check":
        state = check_state(args.domain, args.base_path, args.round)
        print(json.dumps(state, ensure_ascii=False, indent=2))

    elif args.command == "resume-prompt":
        state = check_state(args.domain, args.base_path, args.round)
        if state["action"] == "resume":
            prompt = build_resume_prompt(args.domain, args.base_path, args.round, state)
            print(prompt)
        else:
            print(f"# 不需要续接: {state['action']} — {state['reason']}", file=sys.stderr)
            print(json.dumps(state, ensure_ascii=False, indent=2))

    elif args.command == "report":
        state = check_state(args.domain, args.base_path, args.round)
        report = build_report(args.domain, args.base_path, state)
        print(report)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
