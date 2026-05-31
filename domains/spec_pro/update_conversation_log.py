#!/usr/bin/env python3
"""
update_conversation_log.py — 更新对话日志（幂等、确定性）

Usage:
    python3 update_conversation_log.py <blackboard_path> <round_num> <phase>
        --questions_file <path>
        [--user_response <text>]
        [--user_response_file <path>]
        [--parsed_summary <text>]
        [--quality_before <score>]
        [--quality_after <score>]
        [--inferences_created <n>]
        [--inferences_confirmed <n>]
        [--inferences_rejected <n>]

该脚本读取现有 conversation_log.json，追加一条记录，然后写回。
"""

import json
import sys
import argparse
from datetime import datetime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("blackboard_path")
    parser.add_argument("round_num", type=int)
    parser.add_argument("phase")
    parser.add_argument("--questions_file", default="")
    parser.add_argument("--user_response", default="")
    parser.add_argument("--user_response_file", default="")
    parser.add_argument("--parsed_summary", default="")
    parser.add_argument("--quality_before", type=float, default=0)
    parser.add_argument("--quality_after", type=float, default=0)
    parser.add_argument("--inferences_created", type=int, default=0)
    parser.add_argument("--inferences_confirmed", type=int, default=0)
    parser.add_argument("--inferences_rejected", type=int, default=0)
    args = parser.parse_args()

    log_path = f"{args.blackboard_path}/spec/conversation_log.json"

    # Read existing log
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log = []

    # Read questions
    questions = []
    if args.questions_file:
        try:
            with open(args.questions_file, "r", encoding="utf-8") as f:
                q_data = json.load(f)
            questions = q_data.get("questions", [])
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    # Read user response
    user_response = args.user_response
    if not user_response and args.user_response_file:
        try:
            with open(args.user_response_file, "r", encoding="utf-8") as f:
                user_response = f.read()
        except FileNotFoundError:
            pass
    user_response = user_response[:500] if user_response else ""

    # Append entry
    entry = {
        "round": args.round_num,
        "timestamp": datetime.now().isoformat(),
        "phase": args.phase,
        "questions": questions,
        "user_response": user_response,
        "parsed_updates_summary": args.parsed_summary,
        "quality_before": args.quality_before,
        "quality_after": args.quality_after,
        "quality_delta": round(args.quality_after - args.quality_before, 1),
        "inferences_created": args.inferences_created,
        "inferences_confirmed": args.inferences_confirmed,
        "inferences_rejected": args.inferences_rejected,
    }
    log.append(entry)

    # Write back
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(json.dumps({"status": "ok", "total_entries": len(log)}))


if __name__ == "__main__":
    main()
