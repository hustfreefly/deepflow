#!/usr/bin/env python3
"""
DeepFlow Doctor — Pipeline Scope Filter

从 blackboard 目录自动发现管线运行，按时间窗口过滤事件，
聚焦管线核心执行（gate 门控、Agent 阶段），过滤探索/调试噪音。

用法:
    from pipeline_scope import discover_pipeline_runs, filter_events_by_run

    runs = discover_pipeline_runs()
    # → [{"run_id": "run_20260624_092144_d", "started_at": ..., "completed_at": ..., ...}, ...]

    filtered = filter_events_by_run(events, run)
    # → 只保留 started_at ~ completed_at 窗口内的事件
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# .deepflow 根目录
_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent
_BLACKBOARD_DIR = _DEEPFLOW_ROOT / "blackboard"

# 管线状态文件模式
_PIPELINE_STATE_PATTERNS = [
    "*/ship_output/pipeline_state.json",      # Ship Pro
    "*/pipeline_state.json",                   # Solution Pro (in stages/)
    "*/stages/pipeline_state.json",            # Solution Pro alt
    "*/master_state.json",                     # Solution Pro 2.0 (MasterOrchestrator)
]

# 上海时区 offset
_SHANGHAI_TZ = timezone(timedelta(hours=8))


def discover_pipeline_runs(
    blackboard_dir: str | Path | None = None,
    hours: int = 24,
) -> list[dict]:
    """
    扫描 blackboard 目录，发现所有管线运行。

    返回:
        [{
            "run_id": "run_20260624_092144_d",
            "pipeline_name": "轻量级任务队列系统_...",
            "domain": "ship_pro",
            "started_at": datetime(...),
            "completed_at": datetime(...),
            "status": "completed",
            "agents": {...},
            "state_path": "/path/to/pipeline_state.json",
        }, ...]
    """
    bb_dir = Path(blackboard_dir) if blackboard_dir else _BLACKBOARD_DIR
    if not bb_dir.exists():
        return []

    runs = []
    seen_run_ids = set()

    for pattern in _PIPELINE_STATE_PATTERNS:
        for state_file in bb_dir.glob(pattern):
            try:
                with open(state_file) as f:
                    state = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            run_id = state.get("run_id", "")
            if not run_id:
                # master_state.json 使用 session_id 而非 run_id
                run_id = state.get("session_id", "")
            if not run_id or run_id in seen_run_ids:
                continue
            seen_run_ids.add(run_id)

            # 解析时间
            started_at = _parse_iso(state.get("started_at", ""))
            completed_at = _parse_iso(state.get("completed_at", ""))

            # master_state.json 没有 started_at，尝试从 .completed.json 或文件 mtime 获取
            if not started_at and "master_state" in str(state_file):
                # 尝试读取 companion .completed.json
                completed_file = state_file.parent / "stages" / ".completed.json"
                if completed_file.exists():
                    try:
                        with open(completed_file) as cf:
                            completed_state = json.load(cf)
                        completed_at = _parse_iso(completed_state.get("completed_at", ""))
                    except (json.JSONDecodeError, OSError):
                        pass
                # 用文件 mtime 作为 started_at 的 fallback
                if not started_at:
                    import os
                    mtime = state_file.stat().st_mtime
                    started_at = datetime.fromtimestamp(mtime, tz=_SHANGHAI_TZ) - timedelta(minutes=30)
                    if not completed_at:
                        completed_at = datetime.fromtimestamp(mtime, tz=_SHANGHAI_TZ)

            if not started_at:
                continue

            # 时间过滤
            cutoff = datetime.now(_SHANGHAI_TZ) - timedelta(hours=hours)
            if started_at < cutoff:
                continue

            # 跳过明显已停滞的管线:
            # 1. 有 completed_at 但 duration > 4h 且非 completed/failed
            # 2. 无 completed_at 且 started_at 距今 > 4h（已 abandoned）
            now = datetime.now(_SHANGHAI_TZ)
            if completed_at:
                if state.get("status") not in ("completed", "failed"):
                    duration_hours = (completed_at - started_at).total_seconds() / 3600
                    if duration_hours > 4:
                        continue
            else:
                # 无 completed_at = 可能 abandoned
                if (now - started_at).total_seconds() / 3600 > 4:
                    continue

            # 推断域名
            domain = _infer_domain(state_file, state)

            # 推断管线名称（从路径提取）
            pipeline_name = _extract_pipeline_name(state_file)

            runs.append({
                "run_id": run_id,
                "pipeline_name": pipeline_name,
                "domain": domain,
                "started_at": started_at,
                "completed_at": completed_at or datetime.now(_SHANGHAI_TZ),
                "status": state.get("status", "unknown"),
                "agents": state.get("agents", {}),
                "state_path": str(state_file),
            })

    # 按 started_at 排序（最新在前）
    runs.sort(key=lambda r: r["started_at"], reverse=True)
    return runs


def filter_events_by_run(events: list[dict], run: dict) -> list[dict]:
    """
    过滤事件流，只保留管线执行窗口内的事件。

    参数:
        events: parse_transcript() 返回的事件列表
        run: discover_pipeline_runs() 返回的单个 run dict

    返回:
        过滤后的事件列表
    """
    started = run["started_at"]
    completed = run["completed_at"]

    # 加 30s 缓冲区（捕获启动前准备和完成后收尾）
    buffer = timedelta(seconds=30)
    window_start = started - buffer
    window_end = completed + buffer

    filtered = []
    for ev in events:
        ev_ts = _parse_event_ts(ev.get("ts"))
        if ev_ts is None:
            continue
        if window_start <= ev_ts <= window_end:
            filtered.append(ev)

    return filtered


def filter_events_by_stage(events: list[dict], run: dict, stage: str) -> list[dict]:
    """
    进一步过滤到指定 Agent 阶段的时间窗口。

    通过事件内容中的 Agent 名称/阶段名称来定位。
    """
    # 先按 run 窗口过滤
    run_events = filter_events_by_run(events, run)

    stage_lower = stage.lower()
    stage_keywords = {
        "architect": ["architect", "gate_arch", "ArchitectOutput"],
        "decomposer": ["decomposer", "DecomposerOutput", "work_package"],
        "specifier": ["specifier", "SpecifierOutput", "acceptance_criteria"],
        "reviewer": ["reviewer", "ReviewerOutput", "review_verdict"],
        "packager": ["packager", "ShipPackage", "ship_package"],
    }

    keywords = stage_keywords.get(stage_lower, [stage_lower])
    return [
        ev for ev in run_events
        if _event_matches_stage(ev, keywords)
    ]


def get_run_summary(run: dict) -> str:
    """生成管线运行的简要摘要。"""
    agents = run.get("agents", {})
    passed = sum(1 for a in agents.values() if a.get("state") == "gate_pass")
    failed = sum(1 for a in agents.values() if a.get("state") == "gate_fail")
    total_retries = sum(a.get("retry_count", 0) for a in agents.values())

    duration = ""
    if run.get("completed_at") and run.get("started_at"):
        secs = (run["completed_at"] - run["started_at"]).total_seconds()
        mins = int(secs // 60)
        duration = f"{mins}m{int(secs % 60)}s"

    return (
        f"{run['pipeline_name']} | {run['domain']} | "
        f"{passed}/{len(agents)} gate_pass | "
        f"{failed} gate_fail | {total_retries} retries | "
        f"{duration} | {run['status']}"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_iso(ts_str: str) -> datetime | None:
    """解析 ISO 8601 时间字符串（兼容 UTC 和本地时间）。"""
    if not ts_str:
        return None
    try:
        # 去掉微秒精度差异
        ts_str = ts_str.strip()
        if ts_str.endswith("Z"):
            # UTC
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return dt.astimezone(_SHANGHAI_TZ)
        elif "+" in ts_str[10:] or ts_str.endswith("+08:00"):
            # Already has timezone
            dt = datetime.fromisoformat(ts_str)
            return dt.astimezone(_SHANGHAI_TZ)
        else:
            # Assume local (Shanghai)
            dt = datetime.fromisoformat(ts_str)
            return dt.replace(tzinfo=_SHANGHAI_TZ)
    except (ValueError, TypeError):
        return None


def _parse_event_ts(ts: Any) -> datetime | None:
    """解析事件时间戳（可能是 str 或 int）。"""
    if isinstance(ts, str):
        return _parse_iso(ts)
    if isinstance(ts, (int, float)):
        # Epoch milliseconds
        return datetime.fromtimestamp(ts / 1000, tz=_SHANGHAI_TZ)
    return None


def _infer_domain(state_path: Path, state: dict) -> str:
    """从路径或状态内容推断管线域名。"""
    path_str = str(state_path).lower()
    if "ship_output" in path_str or "ship" in path_str:
        return "ship_pro"
    if "solution" in path_str:
        return "solution_pro"
    if "spec" in path_str:
        return "spec_pro"
    if "research" in path_str:
        return "research_pro"
    if "deliver" in path_str:
        return "deliver_pro"

    # master_state.json → Solution Pro（MasterOrchestrator 使用此格式）
    if state_path.name == "master_state.json":
        modules = state.get("completed_modules", [])
        # 检查已完成模块或 stages/ 目录下的文件来判断域
        if any(m in modules for m in ["planning", "research", "summary"]):
            return "solution_pro"
        # Fallback: 检查 stages/ 子目录下的文件名
        stages_dir = state_path.parent / "stages"
        if stages_dir.exists():
            stage_files = [f.name for f in stages_dir.iterdir()]
            if any("planning" in f or "research" in f or "summary" in f for f in stage_files):
                return "solution_pro"
    # deliver_pro 检查
    if state_path.name == "delivery_state.json":
        return "deliver_pro"

    # 从 agents 推断
    agents = state.get("agents", {})
    if "packager" in agents:
        return "ship_pro"
    if "consolidator" in agents:
        return "solution_pro"
    if "specifier" in agents and "reviewer" not in agents:
        return "spec_pro"

    return "unknown"


def _extract_pipeline_name(state_path: Path) -> str:
    """从路径中提取管线名称。"""
    # .deepflow/blackboard/轻量级任务队列系统_.../ship_output/pipeline_state.json
    parts = state_path.parts
    for i, part in enumerate(parts):
        if part == "blackboard" and i + 1 < len(parts):
            name = parts[i + 1]
            # 截断过长的名称
            if len(name) > 60:
                name = name[:57] + "..."
            return name
    return state_path.parent.parent.name


def _event_matches_stage(ev: dict, keywords: list[str]) -> bool:
    """检查事件是否匹配指定阶段。"""
    searchable = ""
    if ev["type"] == "tool_call":
        searchable = ev.get("input_preview", "")
    elif ev["type"] == "tool_result":
        searchable = ev.get("content_preview", "") + ev.get("error", "")
    elif ev["type"] == "text":
        searchable = ev.get("content", "")

    searchable_lower = searchable.lower()
    return any(kw.lower() in searchable_lower for kw in keywords)
