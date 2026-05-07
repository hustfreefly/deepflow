from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time
import json
import os
from pathlib import Path

router = APIRouter()

# In-memory task store (will be replaced with file-based in production)
active_tasks = {}

class SolutionTaskRequest(BaseModel):
    domain: str = "solution"
    topic: str
    solution_type: str = "architecture"
    constraints: Optional[List[str]] = []
    stakeholders: Optional[List[str]] = []
    session_prefix: Optional[str] = ""

class InvestmentTaskRequest(BaseModel):
    domain: str = "investment"
    code: str
    name: str
    industry: str
    analysis_depth: str = "standard"  # quick, standard, deep
    force_rebuild: bool = False
    session_prefix: Optional[str] = ""

class TaskResponse(BaseModel):
    session_id: str
    status: str
    domain: str
    created_at: float
    message: str

@router.post("/tasks", response_model=TaskResponse)
def create_task(request: dict):
    """Create a new analysis task."""
    # Check if another task is running
    for task_id, task in active_tasks.items():
        if task["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Task already running. Please wait for completion."
            )
    
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
    
    # Store task info
    task_info = {
        "session_id": session_id,
        "domain": domain,
        "status": "queued",
        "created_at": time.time(),
        "parameters": request,
        "progress": 0,
        "current_stage": "init",
        "stages": [
            {"name": "data_collection", "status": "pending"},
            {"name": "planning", "status": "pending"},
            {"name": "reviewers", "status": "pending"},
            {"name": "researchers", "status": "pending"},
            {"name": "consolidator", "status": "pending"},
            {"name": "auditors", "status": "pending"},
            {"name": "fixer", "status": "pending"},
            {"name": "harness_final", "status": "pending"},
            {"name": "summarizer", "status": "pending"},
        ]
    }
    
    active_tasks[session_id] = task_info
    
    # TODO: Trigger actual DeepFlow execution
    # For now, simulate starting the task
    task_info["status"] = "running"
    task_info["current_stage"] = "data_collection"
    
    return TaskResponse(
        session_id=session_id,
        status="running",
        domain=domain,
        created_at=task_info["created_at"],
        message="Task started successfully"
    )

@router.get("/tasks/{session_id}")
def get_task(session_id: str):
    """Get task details."""
    if session_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return active_tasks[session_id]
