from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time
import json
import os
from pathlib import Path

router = APIRouter()

# Task queue directory (shared with main agent)
TASK_QUEUE_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "frontend" / "task_queue"
TASK_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

# Blackboard path for status updates
BLACKBOARD_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"

class TaskResponse(BaseModel):
    session_id: str
    status: str
    domain: str
    created_at: float
    message: str

def _get_task_path(session_id: str) -> Path:
    """Get task request file path."""
    return TASK_QUEUE_DIR / f"{session_id}_request.json"

def _get_status_path(session_id: str) -> Path:
    """Get status file path in blackboard."""
    session_dir = BLACKBOARD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / "status.json"

def _init_status(session_id: str, domain: str) -> dict:
    """Initialize status.json for a new task."""
    status = {
        "session_id": session_id,
        "domain": domain,
        "status": "queued",
        "current_stage": "init",
        "progress": 0.0,
        "created_at": time.time(),
        "stages": [
            {"name": "data_collection", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "planning", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "reviewers", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 3}},
            {"name": "researchers", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 6}},
            {"name": "consolidator", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "auditors", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 3}},
            {"name": "fixer", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "harness_final", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "summarizer", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
        ],
        "quality_score": None,
        "harness_scores": {},
        "elapsed": 0,
    }
    status_path = _get_status_path(session_id)
    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    return status

@router.post("/tasks", response_model=TaskResponse)
def create_task(request: dict):
    """Create a new analysis task and queue it for execution."""
    domain = request.get("domain", "solution")
    session_prefix = request.get("session_prefix", "")
    
    # Generate session ID
    if session_prefix:
        session_id = f"{session_prefix}_{domain}_{uuid.uuid4().hex[:8]}"
    else:
        topic_or_code = request.get("topic", request.get("code", "task"))[:20]
        session_id = f"{topic_or_code}_{domain}_{uuid.uuid4().hex[:8]}"
    
    # Ensure length <= 50
    if len(session_id) > 50:
        session_id = session_id[:50]
    
    # Save task request to queue
    task_request = {
        "session_id": session_id,
        "domain": domain,
        "created_at": time.time(),
        "parameters": request,
        "status": "queued"
    }
    
    task_path = _get_task_path(session_id)
    with open(task_path, 'w', encoding='utf-8') as f:
        json.dump(task_request, f, ensure_ascii=False, indent=2)
    
    # Initialize status in blackboard
    _init_status(session_id, domain)
    
    return TaskResponse(
        session_id=session_id,
        status="queued",
        domain=domain,
        created_at=task_request["created_at"],
        message="Task queued. Waiting for agent execution."
    )

@router.get("/tasks/{session_id}")
def get_task(session_id: str):
    """Get task details from queue."""
    task_path = _get_task_path(session_id)
    if not task_path.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    
    with open(task_path, 'r', encoding='utf-8') as f:
        return json.load(f)

@router.get("/tasks")
def list_tasks(limit: int = 20):
    """List queued and running tasks."""
    tasks = []
    for task_file in sorted(TASK_QUEUE_DIR.glob("*_request.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        with open(task_file, 'r', encoding='utf-8') as f:
            tasks.append(json.load(f))
    return tasks[:limit]
