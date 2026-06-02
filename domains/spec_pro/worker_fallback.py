#!/usr/bin/env python3
"""
worker_fallback.py — Worker fallback + trajectory appender

Called by Orchestrator Worker via exec when a sub-Worker times out or for
deterministic file writes (trajectory, conversation_log).

Usage:
    python3 worker_fallback.py <worker_type> <output_path>
    python3 worker_fallback.py append_trajectory <base_path> <round> <score> <level> [<q_count> <inf_validated>]
"""

import json
import os
import sys
from datetime import datetime


FALLBACKS = {
    "parse": {
        "status": "timeout",
        "parsed": {},
        "inferred": [],
        "confidence": 0,
    },
    "question": {
        "questions": [
            {
                "type": "clarification",
                "text": "请再展开说说你的需求？",
                "dimension": "objective",
            }
        ],
        "strategy_note": "fallback",
    },
    "response": {
        "input_guard": {"valid": False},
        "parsed_updates": {},
        "meta_signals": {},
    },
    "assess": {
        "overall_score": 0,
        "level": "C",
        "dimensions": [],
        "top_missing": ["评估超时"],
        "recommendation": "请继续补充信息",
    },
    "structure": {
        "summary_text": "需求收集完成，但结构化输出失败",
    },
    "harness": {
        "final_decision": "WARN",
        "final_reasoning": "Harness Worker 超时，跳过门禁",
    },
}


def cmd_fallback(worker_type: str, output_path: str) -> None:
    """Write fallback JSON for a timed-out worker."""
    fallback = FALLBACKS.get(worker_type)
    if fallback is None:
        print(f"Unknown worker type: {worker_type}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fallback, f, ensure_ascii=False, indent=2)
    print(f"Wrote fallback to {output_path}")


def cmd_append_trajectory(base_path: str, round_num: int, score: float,
                          level: str, q_count: int = 0, inf_validated: int = 0) -> None:
    """Append a trajectory point to quality_trajectory.json."""
    trajectory_path = os.path.join(base_path, "spec", "quality_trajectory.json")

    # Read existing trajectory
    trajectory = []
    if os.path.exists(trajectory_path):
        try:
            with open(trajectory_path, "r", encoding="utf-8") as f:
                trajectory = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Calculate delta
    prev_score = trajectory[-1]["overall_score"] if trajectory else 0
    delta = round(score - prev_score, 1)

    # Read quality report for dimension scores
    quality_report_path = os.path.join(base_path, "spec", "quality_report.json")
    dimension_scores = {}
    if os.path.exists(quality_report_path):
        try:
            with open(quality_report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            for d in report.get("dimensions", []):
                dimension_scores[d["dimension"]] = d["score"]
        except (json.JSONDecodeError, OSError):
            pass

    point = {
        "round": round_num,
        "overall_score": score,
        "level": level,
        "dimension_scores": dimension_scores,
        "delta": delta,
        "questions_asked": q_count,
        "inferences_validated": inf_validated,
    }

    trajectory.append(point)

    os.makedirs(os.path.dirname(trajectory_path), exist_ok=True)  # F5: 确保 spec/ 目录存在
    with open(trajectory_path, "w", encoding="utf-8") as f:
        json.dump(trajectory, f, ensure_ascii=False, indent=2)
    print(f"Appended trajectory point: round={round_num}, score={score}, delta={delta}")


def main():
    if len(sys.argv) < 3:
        print("Usage: worker_fallback.py <worker_type> <output_path>")
        print("       worker_fallback.py append_trajectory <base_path> <round> <score> <level> [<q_count> <inf_validated>]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "append_trajectory":
        base_path = sys.argv[2]
        round_num = int(sys.argv[3])
        score = float(sys.argv[4])
        level = sys.argv[5]
        q_count = int(sys.argv[6]) if len(sys.argv) > 6 else 0
        inf_validated = int(sys.argv[7]) if len(sys.argv) > 7 else 0
        cmd_append_trajectory(base_path, round_num, score, level, q_count, inf_validated)
    else:
        output_path = sys.argv[2]
        cmd_fallback(command, output_path)


if __name__ == "__main__":
    main()
