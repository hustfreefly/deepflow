"""
Task Queue Consumer - Polls task_queue and SQLite, triggers DeepFlow execution.

WH-003 Fix: Consumer uses subprocess to trigger OpenClaw Agent execution.
Cron Job (isolated, every 2m) is the primary trigger.
Consumer thread provides redundant fallback (polls every 5s).
"""
import asyncio
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional
import threading

# ── Configuration (from config.json, no hardcoded values) ──
_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # .deepflow/
_CFG_FILE = _DEEPFLOW_ROOT / "config.json"

def _load_cfg() -> dict:
    """Load config.json with defaults."""
    defaults = {
        "backend": {"host": "127.0.0.1", "port": 17789},
        "paths": {
            "blackboard": "blackboard",
            "task_queue": "frontend/task_queue"
        },
        "webhook": {
            "url": "http://127.0.0.1:18789/hooks/wake",
            "env_file": "~/.openclaw/.webhook_env"
        }
    }
    if _CFG_FILE.exists():
        with open(_CFG_FILE) as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and k in defaults:
                defaults[k].update(v)
            else:
                defaults[k] = v
    return defaults

_CFG = _load_cfg()
_TASK_QUEUE_DIR = _DEEPFLOW_ROOT / _CFG["paths"]["task_queue"]
_BLACKBOARD_DIR = _DEEPFLOW_ROOT / _CFG["paths"]["blackboard"]
_BACKEND_HOST = _CFG["backend"]["host"]
_BACKEND_PORT = _CFG["backend"]["port"]
_WEBHOOK_URL = _CFG["webhook"]["url"]
_WEBHOOK_ENV = Path(_CFG["webhook"]["env_file"]).expanduser()

# Consumer state
_consumer_running = False
_consumer_thread: Optional[threading.Thread] = None


def _resolve_path(name: str) -> Path:
    """Resolve a relative path against DEEPFLOW_ROOT."""
    return _DEEPFLOW_ROOT / name


def _get_pending_tasks():
    """Get all pending tasks from file queue AND SQLite database.
    
    Note: waiting_agent tasks are handled by Cron Job, not Consumer.
    Consumer only handles pending tasks to avoid duplicate processing.
    """
    tasks = []
    
    # File-based queue (v1 legacy)
    for task_file in _TASK_QUEUE_DIR.glob("*_request.json"):
        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                task = json.load(f)
            if task.get("status") == "queued":
                tasks.append(task)
        except Exception as e:
            print(f"[Consumer] Error reading {task_file}: {e}")
    
    # SQLite queue (v2) - only pending, not waiting_agent
    try:
        from database import get_db
        db = get_db()
        for db_task in db.get_tasks_by_status('pending'):
            task = {
                "session_id": db_task.session_id,
                "domain": db_task.domain,
                "parameters": db_task.parameters,
                "status": "pending",
                "source": "sqlite"
            }
            tasks.append(task)
    except Exception as e:
        print(f"[Consumer] Error reading SQLite queue: {e}")
    
    return tasks


def _mark_task_waiting_agent(session_id: str, source: str = "file"):
    """Mark task as waiting_agent (waiting for Agent to pick up)."""
    # Mark file-based task (v1 legacy)
    if source != "sqlite":
        task_path = _TASK_QUEUE_DIR / f"{session_id}_request.json"
        if task_path.exists():
            with open(task_path, 'r', encoding='utf-8') as f:
                task = json.load(f)
            task["status"] = "waiting_agent"
            task["started_at"] = time.time()
            with open(task_path, 'w', encoding='utf-8') as f:
                json.dump(task, f, ensure_ascii=False, indent=2)
    
    # Mark SQLite task (v2)
    try:
        from database import get_db
        db = get_db()
        db.update_task_status(session_id, "waiting_agent", None)
        print(f"[Consumer] Marked SQLite task {session_id[:30]} as waiting_agent")
    except Exception as e:
        print(f"[Consumer] Error marking SQLite task waiting_agent: {e}")


def _update_status(session_id: str, status_update: dict):
    """Update status.json in blackboard."""
    status_path = _BLACKBOARD_DIR / session_id / "status.json"
    if status_path.exists():
        with open(status_path, 'r', encoding='utf-8') as f:
            status = json.load(f)
        status.update(status_update)
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)


def is_backend_alive() -> bool:
    """跨平台端口检测，不写死端口。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    result = s.connect_ex((_BACKEND_HOST, _BACKEND_PORT))
    s.close()
    return result == 0


def _spawn_deepflow_task(task: dict) -> bool:
    """
    Trigger DeepFlow execution via OpenClaw webhook.
    
    WH-003 Fix: Consumer triggers Agent via webhook instead of waiting for heartbeat.
    The Agent (running in Agent Run environment) will use sessions_spawn
    to launch the actual DeepFlow pipeline.
    """
    session_id = task["session_id"]
    domain = task["domain"]
    params = task.get("parameters", {})
    source = task.get("source", "file")
    
    try:
        # Mark as waiting_agent (not running - Agent hasn't started yet)
        _mark_task_waiting_agent(session_id, source)
        _update_status(session_id, {
            "status": "waiting_agent",
            "current_stage": "waiting",
            "progress": 0.0
        })
        
        print(f"[Consumer] Triggering Agent execution for {session_id} (domain: {domain}, source: {source})")
        
        # Send webhook to wake the Agent
        # The Agent receives this as a message and should process pending tasks
        _send_webhook(session_id, domain, params)
        
        return True
        
    except Exception as e:
        print(f"[Consumer] Error spawning DeepFlow: {e}")
        _update_status(session_id, {
            "status": "failed",
            "error": str(e)
        })
        if source == "sqlite":
            try:
                from database import get_db
                db = get_db()
                db.update_task_status(session_id, "failed", str(e))
            except Exception:
                pass
        return False


def _send_webhook(session_id: str, domain: str, params: dict) -> bool:
    """
    Send webhook to wake the Agent.
    WH-002: Token read from environment file, not hardcoded.
    """
    import httpx
    
    # Read token from env file
    token = None
    if _WEBHOOK_ENV.exists():
        with open(_WEBHOOK_ENV, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('HOOKS_TOKEN='):
                    token = line.split('=', 1)[1]
                    break
    
    if not token:
        print(f"[Consumer] No webhook token configured, skipping webhook for {session_id}")
        return False
    
    payload = {
        "text": f"[DeepFlow] 新任务已入队: {session_id}。请在终端执行:\n\ncd /Users/allen/.openclaw/workspace/.deepflow && python3 -c \"import sys; sys.path.insert(0,'.'); from agents.webhook_task_processor import process_pending_tasks; process_pending_tasks(max_tasks=1)\"\n\n处理完成后请回复任务状态。",
        "mode": "now"
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = httpx.post(_WEBHOOK_URL, json=payload, headers=headers, timeout=10.0)
        if response.status_code in (200, 202):
            print(f"[Consumer] Webhook sent for {session_id[:30]} (HTTP {response.status_code})")
            return True
        else:
            print(f"[Consumer] Webhook failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"[Consumer] Webhook error: {e}")
        return False


def _notify_agent_for_execution(session_id: str, domain: str, params: dict) -> bool:
    """
    Notify OpenClaw Agent to execute DeepFlow for this task.
    The Agent (running in Agent Run environment) will use sessions_spawn
    to launch the actual DeepFlow pipeline.
    
    WH-003: Agent reads task queue and spawns DeepFlow via sessions_spawn.
    Consumer cannot spawn agents itself (no OpenClaw SDK in FastAPI process).
    """
    try:
        from database import get_db
        db = get_db()
        db.update_task_status(session_id, "waiting_agent", None)
        print(f"[Consumer] Task {session_id[:30]} marked as waiting_agent")
        print(f"[Consumer] Agent will process this task when it runs")
        # The actual execution happens when the Agent processes pending tasks
        # via webhook_task_processor.py or HEARTBEAT.md task queue check
        return True
    except Exception as e:
        print(f"[Consumer] Error notifying agent: {e}")
        return False


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
        "queue_dir": str(_TASK_QUEUE_DIR),
        "pending_tasks": len(_get_pending_tasks())
    }
