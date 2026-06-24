"""
Spec Pro 确定性工具函数
======================

用途：让 Orchestrator 通过 exec 调用确定性逻辑（merge、fallback 检查、log）。
这些操作不应交给 LLM 推理。

契约: cage/active/spec_pro_v2.0.yaml (L3 writer_protocol, L2 failure_handling)

使用方式:
  python3 domains/spec_pro/utils.py merge <response_path> <living_spec_path>
  python3 domains/spec_pro/utils.py fallback <worker_name> <output_path>
  python3 domains/spec_pro/utils.py log <execution_log_path> <event> <data_json>
"""

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List
import logging
logger = logging.getLogger(__name__)



# ============================================================================
# Fallback 数据 (从 worker_fallback.py 导入, P0-4 去重)
# ============================================================================

from domains.spec_pro.worker_fallback import FALLBACKS as _FALLBACKS_SHORT

# 短名 → 长名映射
FALLBACKS: Dict[str, Dict[str, Any]] = {
    "parse_worker": _FALLBACKS_SHORT["parse"],
    "question_worker": _FALLBACKS_SHORT["question"],
    "response_worker": _FALLBACKS_SHORT["response"],
    "assess_worker": _FALLBACKS_SHORT["assess"],
    "structure_worker": _FALLBACKS_SHORT["structure"],
    "harness_worker": _FALLBACKS_SHORT["harness"],
}


# ============================================================================
# Merge: 委托给 merge_spec.py 唯一实现 (F1: 消除分叉)
# ============================================================================

def merge_response_to_living_spec(
    response_path: str,
    living_spec_path: str,
) -> Dict[str, Any]:
    """
    按 writer_protocol 将 ResponseWorker 的 parsed_updates 合并到 living_spec.json。

    委托给 merge_spec.merge_spec() — 唯一权威实现。
    保留此函数签名以兼容 utils.py CLI 和其他调用方。
    """
    from domains.spec_pro.merge_spec import merge_spec as _canonical_merge
    return _canonical_merge(response_path, living_spec_path)


# ============================================================================
# Fallback: 检查 Worker 输出文件，缺失则写入 fallback
# ============================================================================

def check_worker_fallback(worker_name: str, output_path: str) -> Dict[str, Any]:
    """
    检查 Worker 输出文件是否存在且非空。
    如果缺失，写入 fallback 数据并返回。

    Args:
        worker_name: Worker 标识名 (parse_worker, question_worker, etc.)
        output_path: Worker 应写入的文件路径

    Returns:
        {"status": "ok"} 或 {"status": "fallback", "data": {...}} 或 {"status": "error", ...}
    """
    if worker_name not in FALLBACKS:
        return {"status": "error", "message": f"Unknown worker: {worker_name}"}

    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                json.loads(content)  # 验证 JSON 有效性
                return {"status": "ok"}
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"data read: {e}")  # 文件损坏，视为缺失

    # 写入 fallback
    fallback_data = FALLBACKS[worker_name]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fallback_data, f, ensure_ascii=False, indent=2)

    return {"status": "fallback", "data": fallback_data}


# ============================================================================
# Log: 追加执行日志
# ============================================================================

def append_execution_log(log_path: str, event: str, data: Dict[str, Any]) -> None:
    """追加事件到 execution_log.json。"""
    log = {"events": []}
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"data append: {e}")

    log["events"].append({
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "data": data,
    })

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ============================================================================
# 质量轨迹追加
# ============================================================================

def append_trajectory(
    trajectory_path: str,
    round_num: int,
    quality_report: Dict[str, Any],
    questions_asked: int = 0,
    inferences_validated: int = 0,
) -> Dict[str, Any]:
    """
    追加质量轨迹记录。

    Returns:
        本轮轨迹点
    """
    trajectory = []
    if os.path.exists(trajectory_path):
        try:
            with open(trajectory_path, "r", encoding="utf-8") as f:
                trajectory = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"trajectory read: {e}")

    overall_score = quality_report.get("overall_score", 0)
    level = quality_report.get("level", "C")

    # 计算维度分数映射
    dimension_scores = {}
    for dim in quality_report.get("dimensions", []):
        dim_key = dim.get("dimension", "")
        dimension_scores[dim_key] = dim.get("score", 0)

    # 计算 delta
    prev_score = trajectory[-1]["overall_score"] if trajectory else 0
    delta = overall_score - prev_score

    point = {
        "round": round_num,
        "overall_score": overall_score,
        "level": level,
        "dimension_scores": dimension_scores,
        "delta": delta,
        "questions_asked": questions_asked,
        "inferences_validated": inferences_validated,
    }
    trajectory.append(point)

    os.makedirs(os.path.dirname(trajectory_path), exist_ok=True)
    with open(trajectory_path, "w", encoding="utf-8") as f:
        json.dump(trajectory, f, ensure_ascii=False, indent=2)

    return point


# ============================================================================
# 对话日志追加
# ============================================================================

def append_conversation_log(
    log_path: str,
    round_num: int,
    phase: str,
    questions: List[Dict],
    user_response: str,
    parsed_updates_summary: str = "",
    quality_before: float = 0,
    quality_after: float = 0,
    inferences_created: int = 0,
    inferences_confirmed: int = 0,
    inferences_rejected: int = 0,
) -> None:
    """追加对话日志记录。"""
    log = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"conversation log read: {e}")

    delta = quality_after - quality_before

    entry = {
        "round": round_num,
        "timestamp": datetime.now().isoformat(),
        "phase": phase,
        "questions": questions,
        "user_response": user_response[:500],  # 截断500字
        "parsed_updates_summary": parsed_updates_summary,
        "quality_before": quality_before,
        "quality_after": quality_after,
        "quality_delta": delta,
        "inferences_created": inferences_created,
        "inferences_confirmed": inferences_confirmed,
        "inferences_rejected": inferences_rejected,
    }
    log.append(entry)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ============================================================================
# Process Guard 检查 (已删除 — 使用 process_guard.py 作为唯一入口)
# ============================================================================

# ============================================================================
# CLI 入口
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 utils.py <command> [args...]")
        print("Commands: merge, fallback, log, trajectory, conversation_log, process_guard")
        return 1

    command = sys.argv[1]

    try:
        if command == "merge":
            if len(sys.argv) < 4:
                print("Usage: python3 utils.py merge <response_path> <living_spec_path>")
                return 1
            result = merge_response_to_living_spec(sys.argv[2], sys.argv[3])
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif command == "fallback":
            if len(sys.argv) < 4:
                print("Usage: python3 utils.py fallback <worker_name> <output_path>")
                return 1
            result = check_worker_fallback(sys.argv[2], sys.argv[3])
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif command == "log":
            if len(sys.argv) < 5:
                print("Usage: python3 utils.py log <log_path> <event> <data_json>")
                return 1
            data = json.loads(sys.argv[4])
            append_execution_log(sys.argv[2], sys.argv[3], data)
            print(json.dumps({"status": "logged"}, ensure_ascii=False))

        elif command == "trajectory":
            if len(sys.argv) < 5:
                print("Usage: python3 utils.py trajectory <path> <round> <quality_report_json>")
                return 1
            round_num = int(sys.argv[3])
            quality = json.loads(sys.argv[4])
            result = append_trajectory(sys.argv[2], round_num, quality)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif command == "conversation_log":
            if len(sys.argv) < 4:
                print("Usage: python3 utils.py conversation_log <path> <entry_json>")
                return 1
            entry = json.loads(sys.argv[3])
            append_conversation_log(sys.argv[2], **entry)
            print(json.dumps({"status": "logged"}, ensure_ascii=False))

        else:
            print(f"Unknown command: {command}")
            return 1

        return 0

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
