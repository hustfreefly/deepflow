"""
Task API v2 - Webhook integration with SQLite queue.
"""
import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from database import get_db, Task

router = APIRouter()

# Webhook configuration (loaded from environment or config.json)
import sys
from pathlib import Path

_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent
_CFG_FILE = _DEEPFLOW_ROOT / "config.json"

def _load_webhook_cfg() -> dict:
    """Load webhook config from config.json + env file."""
    defaults = {
        "token": None,
        "url": "http://127.0.0.1:18789/hooks/wake",
    }
    # Load from config.json if exists
    if _CFG_FILE.exists():
        with open(_CFG_FILE) as f:
            cfg = json.load(f)
        wh = cfg.get("webhook", {})
        if wh.get("url"):
            defaults["url"] = wh["url"]
    # Read token from env file
    env_file = Path.home() / ".openclaw" / ".webhook_env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("HOOKS_TOKEN="):
                    defaults["token"] = line.split("=", 1)[1]
                    break
    return defaults


class TaskRequest(BaseModel):
    """Task creation request."""
    domain: str
    session_prefix: Optional[str] = None
    # Solution domain fields
    topic: Optional[str] = None
    solution_type: Optional[str] = "architecture"
    constraints: Optional[list] = []
    stakeholders: Optional[list] = []
    # Investment domain fields
    code: Optional[str] = None
    name: Optional[str] = None
    analysis_type: Optional[str] = "value"


class TaskResponse(BaseModel):
    """Task creation response."""
    session_id: str
    status: str
    message: str
    webhook_sent: bool


async def notify_webhook_with_retry(session_id: str, max_retries: int = 3, retry_delay: float = 1.0) -> bool:
    """Notify OpenClaw webhook with retry logic."""
    wh_cfg = _load_webhook_cfg()
    
    if not wh_cfg["token"]:
        print(f"[Webhook] No token configured, skipping webhook for {session_id}")
        return False
    
    webhook_url = wh_cfg["url"]
    token = wh_cfg["token"]
    
    # WH-003: Webhook payload must instruct Agent to process pending task queue
    # The Agent receives this as a user message and must execute Python to spawn DeepFlow
    payload = {
        "text": f"[DeepFlow AUTO] 新任务已入队: {session_id}。请在当前 Agent 环境执行以下 Python 代码处理任务:\n\n```python\nimport sys; sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')\nfrom core.agents.webhook_task_processor import process_pending_tasks\nprocessed = process_pending_tasks(max_tasks=1)\nprint(f'Processed: {{processed}}')\n```\n\n处理完成后请回复用户任务状态。",
        "mode": "now"  # Trigger immediately
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code in (200, 202):
                    print(f"[Webhook] ✓ Notification sent for {session_id} (attempt {attempt + 1})")
                    return True
                else:
                    print(f"[Webhook] ✗ Failed: HTTP {response.status_code} (attempt {attempt + 1})")
                    
        except httpx.TimeoutException:
            print(f"[Webhook] ✗ Timeout (attempt {attempt + 1})")
        except httpx.HTTPError as e:
            print(f"[Webhook] ✗ HTTP Error: {e} (attempt {attempt + 1})")
        except (OSError, ConnectionError) as e:
            print(f"[Webhook] ✗ Connection Error: {e} (attempt {attempt + 1})")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
    
    return False


@router.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Create a new task and notify webhook."""
    # Generate session ID (sanitize prefix to alphanumeric + underscore only)
    import re
    if request.session_prefix:
        session_id = f"{request.session_prefix}_{request.domain}_{uuid.uuid4().hex[:8]}"
    else:
        # Use topic or code as prefix, sanitize non-ASCII to underscore
        prefix = request.topic or request.code or "task"
        prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', prefix)[:20]
        prefix = prefix.strip('_') or 'task'
        session_id = f"{prefix}_{request.domain}_{uuid.uuid4().hex[:8]}"
    
    # Ensure length <= 50
    if len(session_id) > 50:
        session_id = session_id[:50]
    
    # Prepare parameters
    parameters = {
        "domain": request.domain,
        "session_prefix": request.session_prefix,
        "topic": request.topic,
        "solution_type": request.solution_type,
        "constraints": request.constraints,
        "stakeholders": request.stakeholders,
        "code": request.code,
        "name": request.name,
        "analysis_type": request.analysis_type,
    }
    
    # Remove None values
    parameters = {k: v for k, v in parameters.items() if v is not None}
    
    # Create task in database
    db = get_db()
    task = db.create_task(session_id, request.domain, parameters)
    
    # Send webhook notification in background
    background_tasks.add_task(
        _send_webhook_and_update,
        session_id,
        task
    )
    
    return TaskResponse(
        session_id=session_id,
        status="queued",
        message="Task queued. Agent will process shortly.",
        webhook_sent=False  # Will be updated by background task
    )


async def _send_webhook_and_update(session_id: str, task: Task):
    """Send webhook and update task status."""
    db = get_db()
    
    # Send webhook
    success = await notify_webhook_with_retry(session_id)
    
    # Update task
    db.mark_webhook_sent(session_id, success)
    
    if not success:
        # Webhook failed, but task is still queued
        # Cron job will pick it up
        print(f"[Webhook] Task {session_id} will be processed by cron job")


@router.get("/tasks/{session_id}")
def get_task(session_id: str):
    """Get task details."""
    db = get_db()
    task = db.get_task(session_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "session_id": task.session_id,
        "domain": task.domain,
        "status": task.status,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "webhook_sent": task.webhook_sent,
        "webhook_retries": task.webhook_retries,
        "error_message": task.error_message
    }


@router.get("/tasks")
def list_tasks(limit: int = 50):
    """List recent tasks."""
    db = get_db()
    tasks = db.get_all_tasks(limit)
    
    return [
        {
            "session_id": t.session_id,
            "domain": t.domain,
            "status": t.status,
            "created_at": t.created_at,
        }
        for t in tasks
    ]
