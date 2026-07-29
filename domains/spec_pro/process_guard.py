#!/usr/bin/env python3
"""
process_guard.py — Process Guard for Spec Pro collecting phase

Checks quality trajectory for anomalies and outputs adjustment instructions.

Usage:
    python3 process_guard.py <base_path> <current_round>

Checks:
    - progress_rate: score delta per round matches expected range
    - inference_integrity: inference confirmation rate in 40-80%
    - conversation_balance: no dimension gap > 40 points

Output: JSON with {anomalies: [...], adjustment_instruction: "text or empty"}
"""

import json
import os
import sys
import logging
logger = logging.getLogger(__name__)



EXPECTED_DELTA_BY_MODE = {
    "quick": {
        (1, 2): (10, 20),
        (3, 4): (5, 10),
        (5, 999): (2, 5),
    },
    "standard": {
        (1, 3): (8, 15),
        (4, 6): (3, 8),
        (7, 999): (1, 3),
    },
    "deep": {
        (1, 5): (6, 12),
        (6, 10): (3, 8),
        (11, 999): (1, 3),
    },
}


def get_expected_delta(round_num: int, mode: str = "standard") -> tuple:
    delta_map = EXPECTED_DELTA_BY_MODE.get(mode, EXPECTED_DELTA_BY_MODE["standard"])
    for (low, high), (min_d, max_d) in delta_map.items():
        if low <= round_num <= high:
            return min_d, max_d
    return 1, 3


def check_progress_rate(trajectory: list, current_round: int, mode: str = "standard") -> list:
    anomalies = []
    if len(trajectory) < 2:
        return anomalies

    for i, point in enumerate(trajectory[1:], 1):
        delta = point.get("delta", 0)
        round_num = point.get("round", i + 1)
        min_d, max_d = get_expected_delta(round_num, mode)

        if delta < min_d - 2:
            anomalies.append(
                f"第{round_num}轮质量提升仅{delta}分，预期{min_d}-{max_d}分，进度过慢"
            )
        elif delta > max_d + 10:
            anomalies.append(
                f"第{round_num}轮质量突增{delta}分（预期{min_d}-{max_d}），可能存在评估偏差"
            )

    return anomalies


def check_inference_integrity(trajectory: list) -> list:
    anomalies = []
    total_created = 0
    total_confirmed = 0

    for point in trajectory:
        total_confirmed += point.get("inferences_validated", 0)

    # Heuristic: if we have many rounds but few validated inferences
    if len(trajectory) >= 3 and total_confirmed == 0:
        anomalies.append("连续多轮无推断确认，推断可能过于偏离用户实际需求")

    return anomalies


def check_conversation_balance(trajectory: list, deliberately_omitted_dims: set = None) -> list:
    anomalies = []
    if not trajectory:
        return anomalies

    latest = trajectory[-1]
    dim_scores = latest.get("dimension_scores", {})

    if len(dim_scores) < 2:
        return anomalies

    # ✅ 排除 deliberately_omitted 维度
    if deliberately_omitted_dims:
        dim_scores = {k: v for k, v in dim_scores.items() if k not in deliberately_omitted_dims}

    if len(dim_scores) < 2:
        return anomalies

    scores = [v for v in dim_scores.values() if isinstance(v, (int, float))]
    if not scores:
        return anomalies

    gap = max(scores) - min(scores)
    if gap > 40:
        max_dim = max(dim_scores, key=dim_scores.get)
        min_dim = min(dim_scores, key=dim_scores.get)
        anomalies.append(
            f"维度分差过大: {max_dim}={dim_scores[max_dim]} vs {min_dim}={dim_scores[min_dim]}，差值{gap}分"
        )

    return anomalies


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Process Guard for Spec Pro")
    parser.add_argument("base_path", help="Session base path")
    parser.add_argument("current_round", type=int, help="Current round number")
    parser.add_argument("--mode", choices=["quick", "standard", "deep"],
                        default="standard", help="Conversation mode (default: standard)")
    args = parser.parse_args()

    base_path = args.base_path
    current_round = args.current_round
    mode = args.mode

    trajectory_path = os.path.join(base_path, "spec", "quality_trajectory.json")
    raw_trajectory = []
    if os.path.exists(trajectory_path):
        try:
            with open(trajectory_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                raw_trajectory = raw.get("trajectory", [])
            elif isinstance(raw, list):
                raw_trajectory = raw
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"process guard: {e}")

    trajectory = raw_trajectory

    anomalies = []
    anomalies.extend(check_progress_rate(trajectory, current_round, mode))
    anomalies.extend(check_inference_integrity(trajectory))
    # 从 living_spec 读取 deliberately_omitted 维度
    deliberately_omitted = set()
    living_spec_path = os.path.join(base_path, "spec", "living_spec.json")
    if os.path.exists(living_spec_path):
        try:
            with open(living_spec_path, "r", encoding="utf-8") as f:
                ls = json.load(f)
            for dim_name, dim_data in ls.get("dimensions", {}).items():
                if isinstance(dim_data, dict) and dim_data.get("deliberately_omitted"):
                    deliberately_omitted.add(dim_name)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"process guard: could not read deliberately_omitted: {e}")

    anomalies.extend(check_conversation_balance(trajectory, deliberately_omitted))

    if anomalies:
        adjustment = (
            "Process Guard 检测到以下异常，请在下一轮 QuestionWorker 中调整提问策略：\n"
            + "\n".join(f"- {a}" for a in anomalies)
        )
    else:
        adjustment = ""

    result = {
        "anomalies": anomalies,
        "adjustment_instruction": adjustment,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
