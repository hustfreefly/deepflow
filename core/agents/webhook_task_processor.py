"""
Webhook Task Processor - Main Agent handler for DeepFlow tasks.

This module is designed to be called by the Main Agent when it receives
a webhook notification. It reads the SQLite task queue and spawns DeepFlow.

Usage (from Main Agent):
    from core.agents.webhook_task_processor import process_pending_tasks
    await process_pending_tasks()
"""
import json
import time
import sqlite3
import sys
from pathlib import Path
import logging
logger = logging.getLogger(__name__)

from typing import Optional, Dict, Any, List, Callable

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from frontend.backend.database import get_db, Task

# DeepFlow imports
from core.quality.entry_harness import EntryHarness

# OpenClaw tool (injected by Main Agent or resolved at runtime)
_spawn_fn: Optional[callable] = None


def set_spawn_fn(spawn_fn: Callable) -> None:
    """Set the spawn function (called by Main Agent)."""
    global _spawn_fn
    _spawn_fn = spawn_fn


def _resolve_spawn_fn() -> Optional[Callable]:
    """Resolve spawn function (fallback for testing)."""
    global _spawn_fn
    if _spawn_fn:
        return _spawn_fn
    
    # Try Agent environment first
    try:
        from openclaw import sessions_spawn
        _spawn_fn = sessions_spawn
        return _spawn_fn
    except ImportError as e:
        logger.debug(f"optional import: {e}")
    
    # Fallback: use subprocess to call openclaw CLI
    # This allows the processor to work in exec environment
    print("[Processor] ⚠️ Not in Agent environment, using CLI fallback")
    return _cli_spawn_fn


def _cli_spawn_fn(runtime: str, mode: str, task: str, timeout_seconds: int = 1800,
                  agentId: str = "main", label: str = None) -> dict:
    """
    Fallback spawn function that uses openclaw CLI instead of SDK.
    This allows webhook_task_processor to work in exec environment.
    
    WH-003: Agent reads task queue and spawns DeepFlow via CLI.
    """
    import subprocess
    # Write task to temp file for CLI to read
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"task": task, "timeout": timeout_seconds}, f)
        task_file = f.name
    
    try:
        # Use openclaw CLI to spawn agent
        cmd = ["openclaw", "agent", "--agent", "main", "--task-file", task_file]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
        return {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Task timed out after {timeout_seconds}s"}
    finally:
        import os
        os.unlink(task_file)


def _build_deepflow_task(task: Task) -> str:
    """Build task description for DeepFlow."""
    domain = task.domain
    params = task.parameters
    session_id = task.session_id
    
    if domain == "solution":
        topic = params.get("topic", "Unknown task")
        solution_type = params.get("solution_type", "architecture")
        constraints = params.get("constraints", [])
        stakeholders = params.get("stakeholders", [])
        
        return f"""Execute DeepFlow Solution Pro for session: {session_id}

Topic: {topic}
Solution Type: {solution_type}
Constraints: {', '.join(constraints) if constraints else 'None'}
Stakeholders: {', '.join(stakeholders) if stakeholders else 'None'}
Session ID: {session_id}

Steps:
1. Initialize EntryHarness with domain='solution'
2. Call harness.validate_and_start() with context
3. Run orchestrator.run_pipeline()
4. Results will be written to blackboard/{session_id}/

Context for EntryHarness:
```python
{{
    "topic": "{topic}",
    "solution_type": "{solution_type}",
    "constraints": {constraints},
    "stakeholders": {stakeholders},
    "session_prefix": "{session_id.split('_')[0] if '_' in session_id else 'task'}"
}}
```
"""
    
    elif domain == "investment":
        code = params.get("code", "Unknown")
        name = params.get("name", "Unknown")
        analysis_type = params.get("analysis_type", "value")
        
        return f"""Execute DeepFlow Investment Analysis for session: {session_id}

Stock Code: {code}
Stock Name: {name}
Analysis Type: {analysis_type}
Session ID: {session_id}

Steps:
1. Initialize EntryHarness with domain='investment'
2. Call harness.validate_and_start() with context
3. Run orchestrator.run_pipeline()
4. Results will be written to blackboard/{session_id}/

Context for EntryHarness:
```python
{{
    "code": "{code}",
    "name": "{name}",
    "analysis_type": "{analysis_type}"
}}
```
"""
    
    else:
        return f"""Execute DeepFlow for session: {session_id}

Domain: {domain}
Parameters: {json.dumps(params, indent=2)}

Run the appropriate DeepFlow pipeline.
"""


def _update_task_status(session_id: str, status: str, error: Optional[str] = None):
    """Update task status in database."""
    try:
        db = get_db()
        db.update_task_status(session_id, status, error)
        print(f"[Processor] Task {session_id} status: {status}")
    except (sqlite3.Error, IOError) as e:
        print(f"[Processor] Failed to update task status: {e}")


def _spawn_deepflow_task(task: Task) -> bool:
    """Spawn DeepFlow task using sessions_spawn."""
    spawn_fn = _resolve_spawn_fn()
    
    if not spawn_fn:
        print("[Processor] ❌ No spawn function available")
        _update_task_status(task.session_id, "failed", "No spawn function available")
        return False
    
    # Update status to running
    _update_task_status(task.session_id, "running")
    
    # Build task description
    task_desc = _build_deepflow_task(task)
    
    print(f"[Processor] Spawning DeepFlow for {task.session_id}...")
    
    try:
        # Spawn DeepFlow orchestrator
        # Note: This is a synchronous call that returns immediately with session info
        # The actual DeepFlow execution happens asynchronously
        result = spawn_fn(
            runtime="subagent",
            mode="run",
            task=task_desc,
            timeout_seconds=1800,  # 30 minutes for full DeepFlow pipeline
            agentId="main",  # Use main agent as the execution context
            label=f"deepflow-{task.session_id[:8]}"
        )
        
        print(f"[Processor] ✓ Spawned DeepFlow: {result}")
        return True
        
    except (RuntimeError, TimeoutError) as e:
        error_msg = f"Failed to spawn DeepFlow: {str(e)}"
        print(f"[Processor] ❌ {error_msg}")
        _update_task_status(task.session_id, "failed", error_msg)
        return False


def process_pending_tasks(max_tasks: int = 1) -> List[str]:
    """
    Process pending tasks from the queue.
    
    Args:
        max_tasks: Maximum number of tasks to process (default 1 for sequential)
    
    Returns:
        List of processed session_ids
    """
    print(f"[Processor] Checking for pending tasks...")
    
    try:
        db = get_db()
        pending = db.get_pending_tasks(max_retries=3)
        
        if not pending:
            print("[Processor] No pending tasks")
            return []
        
        print(f"[Processor] Found {len(pending)} pending tasks")
        
        processed = []
        for task in pending[:max_tasks]:
            print(f"[Processor] Processing task: {task.session_id}")
            
            success = _spawn_deepflow_task(task)
            if success:
                processed.append(task.session_id)
            
            # Small delay between tasks
            if len(processed) < max_tasks:
                time.sleep(0.5)
        
        return processed
        
    except (sqlite3.Error, IOError) as e:
        print(f"[Processor] Error processing tasks: {e}")
        return []


def process_single_task(session_id: str) -> bool:
    """
    Process a specific task by session_id.
    
    Args:
        session_id: The session ID to process
    
    Returns:
        True if successfully spawned, False otherwise
    """
    print(f"[Processor] Processing specific task: {session_id}")
    
    try:
        db = get_db()
        task = db.get_task(session_id)
        
        if not task:
            print(f"[Processor] Task not found: {session_id}")
            return False
        
        if task.status != "pending":
            print(f"[Processor] Task already processed: {task.status}")
            return False
        
        return _spawn_deepflow_task(task)
        
    except (sqlite3.Error, IOError) as e:
        print(f"[Processor] Error processing task: {e}")
        return False


# For direct execution (testing)
if __name__ == "__main__":
    print("Webhook Task Processor")
    print("=" * 50)
    
    # Check if running in Agent environment
    spawn_fn = _resolve_spawn_fn()
    if not spawn_fn:
        print("\n⚠️  Not running in Agent environment")
        print("This module must be called from the Main Agent with spawn_fn injected")
        sys.exit(1)
    
    # Process pending tasks
    processed    = process_pending_tasks()
    
    print(f"\nProcessed {len(processed)} tasks")
    for sid in processed:
        print(f"  - {sid}")
