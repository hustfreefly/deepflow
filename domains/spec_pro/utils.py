"""
Spec Pro 确定性工具函数
======================

用途：让 Orchestrator 通过 exec 调用确定性逻辑（merge、fallback 检查、log）。
这些操作不应交给 LLM 推理。

契约: cage/spec_pro_v2.0.yaml (L3 writer_protocol, L2 failure_handling)

使用方式:
  python3 core/spec_pro/utils.py merge <response_path> <living_spec_path>
  python3 core/spec_pro/utils.py fallback <worker_name> <output_path>
  python3 core/spec_pro/utils.py log <execution_log_path> <event> <data_json>
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List


# ============================================================================
# Fallback 数据
# ============================================================================

FALLBACKS: Dict[str, Dict[str, Any]] = {
    "parse_worker": {
        "status": "timeout",
        "parsed": {},
        "inferred": [],
        "confidence": 0,
    },
    "question_worker": {
        "questions": [
            {
                "type": "clarification",
                "text": "请再展开说说你的需求？",
                "dimension": "objective",
            }
        ],
        "strategy_note": "fallback",
    },
    "response_worker": {
        "input_guard": {"valid": False},
        "parsed_updates": {},
        "meta_signals": {},
    },
    "assess_worker": {
        "overall_score": 0,
        "level": "C",
        "dimensions": [],
        "top_missing": ["评估超时"],
        "recommendation": "请继续补充信息",
    },
    "structure_worker": {
        "summary_text": "需求收集完成，但结构化输出失败",
    },
    "harness_worker": {
        "final_decision": "WARN",
        "final_reasoning": "Harness Worker 超时，跳过门禁",
    },
}


# ============================================================================
# Merge: 确定性合并 response → living_spec
# ============================================================================

def merge_response_to_living_spec(
    response_path: str,
    living_spec_path: str,
) -> Dict[str, Any]:
    """
    按 writer_protocol 将 ResponseWorker 的 parsed_updates 合并到 living_spec.json。

    规则:
    1. confirmed 层: 追加新项，不删除已有项
    2. inferred 层:
       - status=confirmed → 移入 confirmed 层
       - status=rejected → 标记 rejected（保留记录）
       - 新增推断 → 追加
    3. guardrails: 追加新项
    4. 矛盾处理: 新信息与已有 confirmed 矛盾时，保留两者并标注 contradiction

    Returns:
        dict: 合并摘要
    """
    # 读取 response
    if not os.path.exists(response_path):
        return {
            "status": "error",
            "message": f"Response file not found: {response_path}",
        }

    with open(response_path, "r", encoding="utf-8") as f:
        response = json.load(f)

    parsed_updates = response.get("parsed_updates", {})
    inference_responses = response.get("inference_responses", [])
    new_inferences = response.get("new_inferences", [])

    # 读取或创建 living_spec
    if os.path.exists(living_spec_path):
        with open(living_spec_path, "r", encoding="utf-8") as f:
            living_spec = json.load(f)
    else:
        living_spec = _create_default_living_spec()

    confirmed = living_spec.setdefault("confirmed", {})
    inferred = living_spec.setdefault("inferred", [])
    guardrails = living_spec.setdefault("guardrails", {"always_do": [], "ask_first": [], "never_do": []})

    stats = {
        "confirmed_appended": 0,
        "inferences_confirmed": 0,
        "inferences_rejected": 0,
        "inferences_new": 0,
        "guardrails_appended": 0,
    }

    # --- 1. 合并 parsed_updates 到 confirmed 层 ---
    _merge_dict_append(confirmed, parsed_updates, stats)

    # --- 2. 处理推断确认/拒绝 ---
    for inf_resp in inference_responses:
        inf_id = inf_resp.get("id")
        action = inf_resp.get("action")
        # 在 inferred 列表中找到对应项
        for inf in inferred:
            if inf.get("id") == inf_id:
                if action == "confirm":
                    # 移入 confirmed 层
                    _move_inference_to_confirmed(inf, confirmed, stats)
                elif action == "reject":
                    inf["status"] = "rejected"
                    stats["inferences_rejected"] += 1
                elif action == "modify":
                    modified = inf_resp.get("modified_content", "")
                    if modified:
                        inf["content"] = modified
                        inf["status"] = "pending"
                break

    # --- 3. 追加新增推断 ---
    for new_inf in new_inferences:
        if new_inf not in inferred:
            inferred.append(new_inf)
            stats["inferences_new"] += 1

    # --- 3.5. 合并 guardrails ---
    meta_signals = parsed_updates.get("meta_signals", {})
    new_guardrails = meta_signals.get("new_guardrails", {})
    direct_guardrails = response.get("guardrails", {})
    for key in ["always_do", "ask_first", "never_do"]:
        new_items = new_guardrails.get(key, []) or direct_guardrails.get(key, [])
        existing = set(str(x) for x in guardrails[key])
        for item in new_items:
            if str(item) not in existing:
                guardrails[key].append(item)
                existing.add(str(item))
                stats["guardrails_appended"] += 1

    # --- 4. 更新 meta ---
    meta = living_spec.get("meta", {})
    meta["updated_at"] = datetime.now().isoformat()
    meta["conversation_rounds"] = meta.get("conversation_rounds", 0) + 1
    living_spec["meta"] = meta

    # --- 5. 写回 ---
    with open(living_spec_path, "w", encoding="utf-8") as f:
        json.dump(living_spec, f, ensure_ascii=False, indent=2)

    return {
        "status": "merged",
        "stats": stats,
    }


def _merge_dict_append(
    confirmed: Dict[str, Any],
    updates: Dict[str, Any],
    stats: Dict[str, int],
) -> None:
    """合并 updates 到 confirmed，追加不覆盖。"""
    for key, value in updates.items():
        if value is None or value == "" or value == [] or value == {}:
            continue

        if key not in confirmed:
            confirmed[key] = value
            stats["confirmed_appended"] += 1
        elif isinstance(confirmed[key], list) and isinstance(value, list):
            # 列表去重追加
            existing_strs = {json.dumps(x, ensure_ascii=False, sort_keys=True) if isinstance(x, dict) else str(x) for x in confirmed[key]}
            added = 0
            for item in value:
                item_key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
                if item_key not in existing_strs:
                    confirmed[key].append(item)
                    existing_strs.add(item_key)
                    added += 1
            if added:
                stats["confirmed_appended"] += added
        elif isinstance(confirmed[key], dict) and isinstance(value, dict):
            # 递归合并
            for sub_key, sub_value in value.items():
                if sub_key not in confirmed[key] or confirmed[key][sub_key] is None:
                    confirmed[key][sub_key] = sub_value
                    stats["confirmed_appended"] += 1
                elif isinstance(confirmed[key][sub_key], list) and isinstance(sub_value, list):
                    existing = set(str(x) for x in confirmed[key][sub_key])
                    for item in sub_value:
                        if str(item) not in existing:
                            confirmed[key][sub_key].append(item)
                            existing.add(str(item))
                            stats["confirmed_appended"] += 1
        else:
            # 标量值：仅在原值为空时更新
            if not confirmed[key]:
                confirmed[key] = value
                stats["confirmed_appended"] += 1


def _move_inference_to_confirmed(
    inference: Dict[str, Any],
    confirmed: Dict[str, Any],
    stats: Dict[str, int],
) -> None:
    """将确认的推断移入 confirmed 层对应维度。"""
    inference["status"] = "confirmed"
    dimension = inference.get("dimension", "")
    content = inference.get("content", "")

    # 根据维度映射到 confirmed 字段
    dimension_map = {
        "objective": "objective",
        "pain_points": "pain_points",
        "success_metrics": "success_metrics",
        "users": "users",
        "key_scenarios": "key_scenarios",
        "capabilities": "capabilities",
        "quality_attributes": "quality_attributes",
        "constraints": "constraints",
        "integration": "integration",
        "risks": "risks_and_assumptions",
    }

    target_key = dimension_map.get(dimension)
    if target_key and content:
        target = confirmed.get(target_key)
        if isinstance(target, list):
            if content not in target:
                target.append(content)
        elif isinstance(target, dict):
            confirmed[target_key] = content
        stats["inferences_confirmed"] += 1


def _create_default_living_spec() -> Dict[str, Any]:
    """创建默认 living_spec 结构。"""
    now = datetime.now().isoformat()
    return {
        "meta": {
            "engine": "spec_pro",
            "version": "2.1",
            "spec_version": 1,
            "scenario": "genesis",
            "created_at": now,
            "updated_at": now,
            "conversation_rounds": 0,
            "quality_score": 0,
            "quality_level": "C",
        },
        "confirmed": {
            "objective": "",
            "pain_points": [],
            "success_metrics": [],
            "users": [],
            "key_scenarios": [],
            "capabilities": {"always_do": [], "should_do": [], "never_do": []},
            "quality_attributes": [],
            "constraints": {},
            "integration": {"existing_systems": [], "requirements": []},
            "risks_and_assumptions": {"risks": [], "assumptions": [], "dependencies": []},
        },
        "inferred": [],
        "guardrails": {"always_do": [], "ask_first": [], "never_do": []},
        "route_recommendation": None,
        "solution_pro_hints": None,
    }


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
        except (json.JSONDecodeError, OSError):
            pass  # 文件损坏，视为缺失

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
        except (json.JSONDecodeError, OSError):
            pass

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
        except (json.JSONDecodeError, OSError):
            pass

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
        except (json.JSONDecodeError, OSError):
            pass

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
# Process Guard 检查
# ============================================================================

def check_process_guard(trajectory_path: str) -> Dict[str, Any]:
    """
    检查质量轨迹是否健康。

    Returns:
        {healthy: bool, issues: [...], adjustments: [...]}
    """
    result = {"healthy": True, "issues": [], "adjustments": []}

    if not os.path.exists(trajectory_path):
        return result

    try:
        with open(trajectory_path, "r", encoding="utf-8") as f:
            trajectory = json.load(f)
    except (json.JSONDecodeError, OSError):
        return result

    if len(trajectory) < 2:
        return result  # 至少2轮才能检查进度

    # --- progress_rate ---
    for i in range(1, len(trajectory)):
        delta = trajectory[i]["delta"]
        round_num = trajectory[i]["round"]
        if round_num <= 3:
            expected_range = (8, 15)
        elif round_num <= 6:
            expected_range = (3, 8)
        else:
            expected_range = (1, 3)

        if delta < expected_range[0] and trajectory[i]["overall_score"] < 75:
            result["issues"].append(
                f"第{round_num}轮进度不足 (delta={delta}, 期望>={expected_range[0]})"
            )
            result["adjustments"].append("需要更深入地追问当前维度")

    # --- inference_integrity ---
    total_confirmed = sum(t.get("inferences_validated", 0) for t in trajectory)
    total_inferences = sum(t.get("questions_asked", 0) for t in trajectory)
    if total_inferences > 0:
        rate = total_confirmed / total_inferences
        if rate < 0.2 or rate > 0.9:
            result["issues"].append(
                f"推断确认率异常 ({rate:.1%}, 期望40-80%)"
            )
            result["adjustments"].append("调整推断置信度阈值")

    # --- conversation_balance ---
    if trajectory:
        latest = trajectory[-1]
        dim_scores = latest.get("dimension_scores", {})
        if dim_scores:
            scores = [s for s in dim_scores.values() if s > 0]
            if scores and (max(scores) - min(scores)) > 40:
                result["issues"].append(
                    f"维度间分差过大 ({max(scores)} - {min(scores)} = {max(scores) - min(scores)})"
                )
                min_dim = min(dim_scores, key=dim_scores.get)
                result["adjustments"].append(f"优先关注薄弱维度: {min_dim}")

    if result["issues"]:
        result["healthy"] = False

    return result


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

        elif command == "process_guard":
            if len(sys.argv) < 3:
                print("Usage: python3 utils.py process_guard <trajectory_path>")
                return 1
            result = check_process_guard(sys.argv[2])
            print(json.dumps(result, ensure_ascii=False, indent=2))

        else:
            print(f"Unknown command: {command}")
            return 1

        return 0

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
