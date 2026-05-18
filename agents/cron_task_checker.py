"""
Cron Task Checker - Periodic task processor for DeepFlow.

This module is designed to be called by OpenClaw Cron Job every 30 seconds
to process tasks that may have been missed by webhook notifications.

Features:
- Check for pending tasks in SQLite database
- Retry failed webhook notifications
- Mark stale tasks as failed
- Generate summary report

Usage (from Cron Job):
    python -m agents.cron_task_checker

Exit codes:
    0 - Success (no pending tasks or processed successfully)
    1 - Error (database error, etc.)
    2 - Found pending tasks requiring Main Agent processing
"""
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from frontend.backend.database import get_db, Task

# Constants
MAX_WEBHOOK_RETRIES = 3
STALE_TASK_MINUTES = 30  # Tasks running longer than this are considered stale


def _format_timestamp(ts: str) -> str:
    """Format timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(ts)


def _is_task_stale(task: Task) -> bool:
    """Check if a running task has become stale."""
    if task.status != "running":
        return False
    
    try:
        updated_at = datetime.fromisoformat(task.updated_at)
        stale_threshold = datetime.now() - timedelta(minutes=STALE_TASK_MINUTES)
        return updated_at < stale_threshold
    except (ValueError, TypeError):
        return False


def _mark_stale_tasks_as_failed(db) -> int:
    """Mark stale running tasks as failed."""
    try:
        running_tasks = db.get_tasks_by_status("running")
        
        marked_count = 0
        for task in running_tasks:
            if _is_task_stale(task):
                db.update_task_status(
                    task.session_id,
                    "failed",
                    f"Task timed out after {STALE_TASK_MINUTES} minutes"
                )
                print(f"[CronChecker] Marked stale task as failed: {task.session_id}")
                marked_count += 1
        
        return marked_count
    except (sqlite3.Error, IOError) as e:
        print(f"[CronChecker] Error marking stale tasks: {e}")
        return 0


def _retry_webhook_notification(task: Task) -> bool:
    """
    Attempt to retry webhook notification for a task.
    
    Note: This is a placeholder. In production, this would call the
    same webhook endpoint as tasks_v2.py.
    
    Returns:
        True if retry should be considered successful
    """
    import httpx
    import os
    from pathlib import Path
    
    # Load webhook configuration
    webhook_env = Path.home() / ".openclaw" / ".webhook_env"
    webhook_url = None
    webhook_token = None
    
    if webhook_env.exists():
        with open(webhook_env, 'r') as f:
            for line in f:
                if line.startswith('HOOKS_URL='):
                    webhook_url = line.split('=', 1)[1].strip()
                elif line.startswith('HOOKS_TOKEN='):
                    webhook_token = line.split('=', 1)[1].strip()
    
    if not webhook_url or not webhook_token:
        print(f"[CronChecker] ⚠️  Webhook not configured, cannot retry")
        return False
    
    # Build webhook payload
    payload = {
        "text": f"DeepFlow task retry: {task.session_id}",
        "mode": "now",
        "task_id": task.session_id,
        "domain": task.domain
    }
    
    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {webhook_token}",
                "Content-Type": "application/json"
            },
            timeout=5.0
        )
        
        if response.status_code in (200, 202):
            print(f"[CronChecker] ✓ Webhook retry sent for {task.session_id}")
            return True
        else:
            print(f"[CronChecker] ✗ Webhook retry failed: HTTP {response.status_code}")
            return False
            
    except httpx.TimeoutException:
        print(f"[CronChecker] ✗ Webhook retry timeout")
        return False
    except (httpx.HTTPError, OSError, ConnectionError) as e:
        print(f"[CronChecker] ✗ Webhook retry error: {e}")
        return False


def _process_failed_webhooks(db) -> Dict[str, Any]:
    """Process tasks with failed webhook notifications."""
    stats = {
        "checked": 0,
        "retried": 0,
        "max_retries_reached": 0,
        "marked_failed": 0
    }
    
    try:
        pending_tasks = db.get_tasks_by_status("pending")
        
        for task in pending_tasks:
            if task.webhook_sent or task.webhook_retries >= MAX_WEBHOOK_RETRIES:
                continue
            
            stats["checked"] += 1
            
            if task.webhook_retries + 1 >= MAX_WEBHOOK_RETRIES:
                db.update_task_status(
                    task.session_id,
                    "failed",
                    f"Webhook failed after {MAX_WEBHOOK_RETRIES} retries"
                )
                stats["marked_failed"] += 1
                print(f"[CronChecker] Task {task.session_id} failed after max retries")
            else:
                if _retry_webhook_notification(task):
                    stats["retried"] += 1
        
        return stats
        
    except (sqlite3.Error, IOError) as e:
        print(f"[CronChecker] Error processing failed webhooks: {e}")
        return stats


def _generate_summary(db) -> Dict[str, Any]:
    """Generate task queue summary."""
    try:
        status_counts = db.count_tasks_by_status()
        pending_webhooks = db.count_pending_webhooks()
        
        return {
            "total": sum(status_counts.values()),
            "pending": status_counts.get("pending", 0),
            "running": status_counts.get("running", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "pending_webhooks": pending_webhooks
        }
    except (sqlite3.Error, IOError) as e:
        print(f"[CronChecker] Error generating summary: {e}")
        return {}


def main():
    """Main entry point for cron job."""
    print(f"[CronChecker] {'='*50}")
    print(f"[CronChecker] Starting check at {datetime.now().isoformat()}")
    print(f"[CronChecker] {'='*50}")
    
    try:
        db = get_db()
        
        # Step 1: Mark stale tasks as failed
        stale_count = _mark_stale_tasks_as_failed(db)
        if stale_count > 0:
            print(f"[CronChecker] Marked {stale_count} stale tasks as failed")
        
        # Step 2: Retry failed webhook notifications
        retry_stats = _process_failed_webhooks(db)
        if retry_stats["checked"] > 0:
            print(f"[CronChecker] Checked {retry_stats['checked']} tasks for webhook retry")
            print(f"[CronChecker]   - Retried: {retry_stats['retried']}")
            print(f"[CronChecker]   - Max retries reached: {retry_stats['max_retries_reached']}")
            print(f"[CronChecker]   - Marked failed: {retry_stats['marked_failed']}")
        
        # Step 3: Check for pending tasks
        pending = db.get_pending_tasks(max_retries=MAX_WEBHOOK_RETRIES)
        
        # Step 4: Generate summary
        summary = _generate_summary(db)
        print(f"[CronChecker] {'-'*50}")
        print(f"[CronChecker] Queue Summary:")
        print(f"[CronChecker]   Total tasks: {summary.get('total', 0)}")
        print(f"[CronChecker]   Pending: {summary.get('pending', 0)}")
        print(f"[CronChecker]   Running: {summary.get('running', 0)}")
        print(f"[CronChecker]   Completed: {summary.get('completed', 0)}")
        print(f"[CronChecker]   Failed: {summary.get('failed', 0)}")
        print(f"[CronChecker]   Pending webhooks: {summary.get('pending_webhooks', 0)}")
        
        # Step 5: Report pending tasks requiring Main Agent
        if pending:
            print(f"[CronChecker] {'-'*50}")
            print(f"[CronChecker] ⚠️  Found {len(pending)} pending tasks requiring Main Agent:")
            for task in pending:
                print(f"[CronChecker]   - {task.session_id}")
                print(f"[CronChecker]     Domain: {task.domain}")
                print(f"[CronChecker]     Created: {_format_timestamp(task.created_at)}")
                print(f"[CronChecker]     Webhook retries: {task.webhook_retries}")
            print(f"[CronChecker] {'-'*50}")
            print(f"[CronChecker] These tasks need Main Agent to process via:")
            print(f"[CronChecker]   from agents.webhook_task_processor import process_pending_tasks")
            print(f"[CronChecker]   process_pending_tasks()")
            return 2  # Exit code 2 = pending tasks found
        
        print(f"[CronChecker] {'='*50}")
        print(f"[CronChecker] Check complete - no pending tasks")
        return 0
        
    except (sqlite3.Error, IOError) as e:
        print(f"[CronChecker] ❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
