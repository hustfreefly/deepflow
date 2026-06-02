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
注意：核心逻辑已移至 utils.py::append_conversation_log，此处为 CLI 入口（P1-2 去重）。
"""

import json
import sys
import argparse

# 复用 utils.py 的实现（P1-2 去重）
from domains.spec_pro.utils import append_conversation_log


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

    # 调用 utils.py 的统一实现（P1-2 去重）
    append_conversation_log(
        log_path=log_path,
        round_num=args.round_num,
        phase=args.phase,
        questions=questions,
        user_response=user_response,
        parsed_updates_summary=args.parsed_summary,
        quality_before=args.quality_before,
        quality_after=args.quality_after,
        inferences_created=args.inferences_created,
        inferences_confirmed=args.inferences_confirmed,
        inferences_rejected=args.inferences_rejected,
    )

    # 读取更新后的日志以获取 total_entries
    with open(log_path, "r", encoding="utf-8") as f:
        log = json.load(f)
    print(json.dumps({"status": "ok", "total_entries": len(log)}))


if __name__ == "__main__":
    main()
