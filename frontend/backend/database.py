"""
SQLite database for task queue.
Provides persistent storage for tasks with retry support.
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager

# Database path (config-driven)
_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent  # .deepflow/frontend/backend/ → .deepflow/
_CFG_FILE = _DEEPFLOW_ROOT / "config.json"

def _resolve_db_path() -> Path:
    """Resolve DB path from config.json, fallback to default."""
    defaults = {"paths": {"database": "frontend/backend/data/tasks.db"}}
    if _CFG_FILE.exists():
        with open(_CFG_FILE) as f:
            user = json.load(f)
        if "paths" in user:
            defaults["paths"].update(user["paths"])
    return _DEEPFLOW_ROOT / defaults["paths"]["database"]

DB_PATH = _resolve_db_path()
DB_DIR = DB_PATH.parent
DB_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Task:
    """Task model."""
    id: str
    session_id: str
    domain: str
    status: str  # pending, running, completed, failed
    parameters: Dict[str, Any]
    created_at: float
    updated_at: float
    webhook_sent: bool
    webhook_retries: int
    error_message: Optional[str] = None


class TaskDatabase:
    """SQLite database for task queue."""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    parameters TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    webhook_sent INTEGER DEFAULT 0,
                    webhook_retries INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """)
            
            # Index for efficient queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhook ON tasks(webhook_sent, webhook_retries)
            """)
            conn.commit()
    
    def create_task(self, session_id: str, domain: str, parameters: Dict[str, Any]) -> Task:
        """Create a new task."""
        now = time.time()
        task = Task(
            id=session_id,
            session_id=session_id,
            domain=domain,
            status="pending",
            parameters=parameters,
            created_at=now,
            updated_at=now,
            webhook_sent=False,
            webhook_retries=0
        )
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO tasks (id, session_id, domain, status, parameters, created_at, updated_at, webhook_sent, webhook_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.session_id, task.domain, task.status,
                json.dumps(task.parameters), task.created_at, task.updated_at,
                int(task.webhook_sent), task.webhook_retries
            ))
            conn.commit()
        
        return task
    
    def get_task(self, session_id: str) -> Optional[Task]:
        """Get task by session_id."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            
            if row:
                return self._row_to_task(row)
            return None
    
    def get_pending_tasks(self, max_retries: int = 3) -> List[Task]:
        """Get pending tasks that need webhook notification."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks 
                WHERE status = 'pending' 
                AND (webhook_sent = 0 OR webhook_retries < ?)
                ORDER BY created_at ASC
            """, (max_retries,)).fetchall()
            
            return [self._row_to_task(row) for row in rows]
    
    def update_task_status(self, session_id: str, status: str, error_message: Optional[str] = None):
        """Update task status."""
        with self._get_connection() as conn:
            if error_message:
                conn.execute("""
                    UPDATE tasks SET status = ?, error_message = ?, updated_at = ?
                    WHERE session_id = ?
                """, (status, error_message, time.time(), session_id))
            else:
                conn.execute("""
                    UPDATE tasks SET status = ?, updated_at = ?
                    WHERE session_id = ?
                """, (status, time.time(), session_id))
            conn.commit()
    
    def mark_webhook_sent(self, session_id: str, success: bool):
        """Mark webhook as sent and update retry count."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE tasks 
                SET webhook_sent = ?, webhook_retries = webhook_retries + 1, updated_at = ?
                WHERE session_id = ?
            """, (int(success), time.time(), session_id))
            conn.commit()
    
    def get_all_tasks(self, limit: int = 100) -> List[Task]:
        """Get all tasks ordered by creation time."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()
            
            return [self._row_to_task(row) for row in rows]
    
    def get_tasks_by_status(self, status: str) -> List[Task]:
        """Get tasks filtered by status (for cron checker)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC",
                (status,)
            ).fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def count_tasks_by_status(self) -> Dict[str, int]:
        """Count tasks grouped by status (for cron summary)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
            ).fetchall()
            return {row['status']: row['cnt'] for row in rows}
    
    def count_pending_webhooks(self) -> int:
        """Count tasks with webhook_sent=0 (for cron retry check)."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE webhook_sent = 0"
            ).fetchone()
            return row['cnt'] if row else 0
    
    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert database row to Task."""
        return Task(
            id=row['id'],
            session_id=row['session_id'],
            domain=row['domain'],
            status=row['status'],
            parameters=json.loads(row['parameters']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            webhook_sent=bool(row['webhook_sent']),
            webhook_retries=row['webhook_retries'],
            error_message=row['error_message']
        )


# Global database instance
_db: Optional[TaskDatabase] = None


def get_db() -> TaskDatabase:
    """Get or create database instance."""
    global _db
    if _db is None:
        _db = TaskDatabase()
    return _db
