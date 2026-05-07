"""
Task Queue Consumer - Polls task_queue and spawns DeepFlow.
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Optional
import threading

# Task queue directory
TASK_QUEUE_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "frontend" / "task_queue"
BLACKBOARD_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"

# Consumer state
_consumer_running = False
_consumer_thread: Optional[threading.Thread] = None


def _get_pending_tasks():
    """Get all pending tasks from queue."""
    tasks = []
    for task_file in TASK_QUEUE_DIR.glob("*_request.json"):
        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                task = json.load(f)
            if task.get("status") == "queued":
                tasks.append(task)
        except Exception as e:
            print(f"[Consumer] Error reading {task_file}: {e}")
    return tasks


def _mark_task_running(session_id: str):
    """Mark task as running."""
    task_path = TASK_QUEUE_DIR / f"{session_id}_request.json"
    if task_path.exists():
        with open(task_path, 'r', encoding='utf-8') as f:
            task = json.load(f)
        task["status"] = "running"
        task["started_at"] = time.time()
        with open(task_path, 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False, indent=2)


def _update_status(session_id: str, status_update: dict):
    """Update status.json in blackboard."""
    status_path = BLACKBOARD_DIR / session_id / "status.json"
    if status_path.exists():
        with open(status_path, 'r', encoding='utf-8') as f:
            status = json.load(f)
        status.update(status_update)
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)


def _spawn_deepflow_task(task: dict) -> bool:
    """
    Spawn DeepFlow task via subprocess.
    Note: This is a bridge that will be replaced with sessions_spawn
    when running in Agent environment.
    """
    session_id = task["session_id"]
    domain = task["domain"]
    params = task.get("parameters", {})
    
    try:
        # Mark as running
        _mark_task_running(session_id)
        _update_status(session_id, {
            "status": "running",
            "current_stage": "data_collection",
            "progress": 0.1
        })
        
        # Import here to avoid circular dependency
        # This will be replaced with actual DeepFlow spawn
        print(f"[Consumer] Spawning DeepFlow for {session_id} (domain: {domain})")
        
        # For now, simulate execution with status updates
        # In production, this calls: sessions_spawn(runtime="subagent", ...)
        _simulate_deepflow_execution(session_id, domain, params)
        
        return True
        
    except Exception as e:
        print(f"[Consumer] Error spawning DeepFlow: {e}")
        _update_status(session_id, {
            "status": "failed",
            "error": str(e)
        })
        return False


def _simulate_deepflow_execution(session_id: str, domain: str, params: dict):
    """
    Simulate DeepFlow execution with status updates.
    This is a placeholder - real implementation uses sessions_spawn.
    """
    stages = [
        ("data_collection", 0.1, 1),
        ("planning", 0.2, 1),
        ("reviewers", 0.35, 3),
        ("researchers", 0.55, 6),
        ("consolidator", 0.65, 1),
        ("auditors", 0.75, 3),
        ("fixer", 0.85, 1),
        ("harness_final", 0.95, 1),
        ("summarizer", 1.0, 1),
    ]
    
    for stage_name, progress, worker_count in stages:
        _update_status(session_id, {
            "current_stage": stage_name,
            "progress": progress,
            "stages": _build_stages(stage_name, stages)
        })
        # Simulate work duration
        time.sleep(2)
    
    # Mark complete
    _update_status(session_id, {
        "status": "completed",
        "progress": 1.0,
        "completed_at": time.time()
    })


def _build_stages(current_stage: str, all_stages: list) -> list:
    """Build stage status list."""
    result = []
    found_current = False
    for name, _, count in all_stages:
        if name == current_stage:
            status = "running"
            found_current = True
        elif not found_current:
            status = "completed"
        else:
            status = "pending"
        
        result.append({
            "name": name,
            "status": status,
            "duration": 0,
            "workers": {"completed": count if status == "completed" else (1 if status == "running" else 0), "total": count}
        })
    return result


def _consumer_loop():
    """Main consumer loop - runs in background thread."""
    global _consumer_running
    
    print("[Consumer] Task queue consumer started")
    
    while _consumer_running:
        try:
            # Check for pending tasks
            pending = _get_pending_tasks()
            
            for task in pending:
                if not _consumer_running:
                    break
                print(f"[Consumer] Processing task: {task['session_id']}")
                _spawn_deepflow_task(task)
            
            # Sleep before next poll
            time.sleep(5)
            
        except Exception as e:
            print(f"[Consumer] Error in loop: {e}")
            time.sleep(5)
    
    print("[Consumer] Task queue consumer stopped")


def start_consumer():
    """Start the task queue consumer in background thread."""
    global _consumer_running, _consumer_thread
    
    if _consumer_running:
        print("[Consumer] Already running")
        return
    
    _consumer_running = True
    _consumer_thread = threading.Thread(target=_consumer_loop, daemon=True)
    _consumer_thread.start()
    print("[Consumer] Started")


def stop_consumer():
    """Stop the task queue consumer."""
    global _consumer_running
    _consumer_running = False
    print("[Consumer] Stopping...")


def get_consumer_status() -> dict:
    """Get consumer status."""
    return {
        "running": _consumer_running,
        "thread_alive": _consumer_thread.is_alive() if _consumer_thread else False,
        "queue_dir": str(TASK_QUEUE_DIR),
        "pending_tasks": len(_get_pending_tasks())
    }
