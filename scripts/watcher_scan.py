#!/usr/bin/env python3
"""
Watcher Scan V3 — AI Native minimal file scanner.

只做一件事：扫描目录，输出文件状态的 compact JSON。
LLM 负责判断和格式化。

Usage:
    python3 watcher_scan.py <base_path> <config_path> [--state <state_dir>]

Output (JSON):
    {
        "stages": [{"name": "Architect", "seq": 1, "icon": "🏗️", "exists": true, "new": false}],
        "completed": {"exists": false},
        "total": 5,
        "completed_count": 3,
        "has_new": true,
        "elapsed_min": 12
    }
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_path")
    ap.add_argument("config_path")
    ap.add_argument("--state", default=None, help="State directory (default: base_path)")
    ap.add_argument("--run-start-at", default="", help="Run start time for elapsed calc")
    args = ap.parse_args()

    base = Path(args.base_path)
    state_dir = Path(args.state) if args.state else base

    # Load config
    with open(args.config_path) as f:
        cfg = json.load(f)

    # Extract stages from config
    stages = []
    for sd in cfg.get("detection", {}).get("scan_dirs", []):
        scan_path = base / sd["path"] if sd["path"] != "." else base
        for fname, info in sd.get("stage_files", {}).items():
            fpath = scan_path / fname
            exists = fpath.is_file()
            stages.append({
                "name": info["name"],
                "seq": info["seq"],
                "icon": info.get("icon", "📄"),
                "exists": exists,
                "file": fname if exists else None,
            })

    stages.sort(key=lambda x: x["seq"])

    # Check completion
    completed_file = cfg.get("detection", {}).get("completed_file", ".completed")
    completed_path = base / completed_file
    completed_exists = completed_path.is_file()
    completed_data = None
    if completed_exists:
        try:
            with open(completed_path) as f:
                completed_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Check state (what was notified before)
    state_file = state_dir / ".watcher_seen.json"
    seen = set()
    if state_file.is_file():
        try:
            with open(state_file) as f:
                seen = set(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass

    # Mark new stages
    current_exists = {s["name"] for s in stages if s["exists"]}
    new_stages = current_exists - seen
    has_new = len(new_stages) > 0

    for s in stages:
        s["new"] = s["name"] in new_stages

    # Update state
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(sorted(seen | current_exists), f)

    # Elapsed time
    elapsed_min = 0
    if args.run_start_at:
        try:
            start = datetime.fromisoformat(args.run_start_at.replace("Z", "+00:00"))
            if not start.tzinfo:
                start = start.replace(tzinfo=datetime.now().astimezone().tzinfo)
            elapsed_min = int((datetime.now(start.tzinfo) - start).total_seconds() / 60)
        except (ValueError, TypeError):
            pass

    # Run count
    count_file = state_dir / ".watcher_run_count"
    run_count = 0
    if count_file.is_file():
        try:
            with open(count_file) as f:
                run_count = json.load(f).get("count", 0)
        except (json.JSONDecodeError, OSError):
            pass
    run_count += 1
    with open(count_file, "w") as f:
        json.dump({"count": run_count, "run_start_at": args.run_start_at}, f)

    # Output compact JSON
    result = {
        "stages": stages,
        "completed": {
            "exists": completed_exists,
            "status": completed_data.get("status") if completed_data else None,
            "completed_at": completed_data.get("completed_at") if completed_data else None,
        },
        "total": cfg.get("detection", {}).get("total_stages", len(stages)),
        "completed_count": len([s for s in stages if s["exists"]]),
        "has_new": has_new,
        "elapsed_min": elapsed_min,
        "run_count": run_count,
        "pipeline_id": cfg.get("pipeline_id", "unknown"),
        "display_name": cfg.get("display_name", "Pipeline"),
    }

    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
