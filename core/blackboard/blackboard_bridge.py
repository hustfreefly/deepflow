"""
Blackboard Bridge - Integrates DeepFlow status updates with frontend.
"""
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any

import core.bootstrap

# Blackboard directory
BLACKBOARD_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"


class BlackboardBridge:
    """Bridge between DeepFlow execution and frontend status."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_dir = BLACKBOARD_DIR / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
    
    def _status_path(self) -> Path:
        """Get status.json path."""
        return self.session_dir / "status.json"
    
    def _report_path(self) -> Path:
        """Get report.md path."""
        return self.session_dir / "report.md"
    
    def init_status(self, domain: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize status for new task."""
        status = {
            "session_id": self.session_id,
            "domain": domain,
            "status": "queued",
            "current_stage": "init",
            "progress": 0.0,
            "created_at": time.time(),
            "parameters": parameters,
            "stages": self._init_stages(),
            "quality_score": None,
            "harness_scores": {},
            "elapsed": 0,
        }
        self._write_status(status)
        return status
    
    def _init_stages(self) -> list:
        """Initialize stage list."""
        return [
            {"name": "data_collection", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "planning", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "reviewers", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 3}},
            {"name": "researchers", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 6}},
            {"name": "consolidator", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "auditors", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 3}},
            {"name": "fixer", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "harness_final", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
            {"name": "summarizer", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 1}},
        ]
    
    def _write_status(self, status: Dict[str, Any]):
        """Write status to file."""
        with open(self._status_path(), 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    
    def update_stage(self, stage_name: str, stage_status: str, duration: int = 0, workers_completed: int = 0):
        """Update stage status."""
        status = self.get_status()
        if not status:
            return
        
        for stage in status.get("stages", []):
            if stage["name"] == stage_name:
                stage["status"] = stage_status
                stage["duration"] = duration
                if workers_completed > 0:
                    stage["workers"]["completed"] = workers_completed
                break
        
        self._write_status(status)
    
    def update_progress(self, current_stage: str, progress: float, elapsed: int = 0):
        """Update overall progress."""
        status = self.get_status()
        if not status:
            return
        
        status["current_stage"] = current_stage
        status["progress"] = progress
        status["elapsed"] = elapsed
        
        self._write_status(status)
    
    def update_harness_scores(self, completeness: float, necessity: float, target_alignment: float):
        """Update Harness quality scores."""
        status = self.get_status()
        if not status:
            return
        
        status["harness_scores"] = {
            "completeness": completeness,
            "necessity": necessity,
            "target_alignment": target_alignment
        }
        # Calculate overall quality score
        status["quality_score"] = round((completeness + necessity + target_alignment) / 3, 2)
        
        self._write_status(status)
    
    def complete(self, report_content: Optional[str] = None):
        """Mark task as completed."""
        status = self.get_status()
        if not status:
            return
        
        status["status"] = "completed"
        status["progress"] = 1.0
        status["completed_at"] = time.time()
        
        self._write_status(status)
        
        # Save report if provided
        if report_content:
            with open(self._report_path(), 'w', encoding='utf-8') as f:
                f.write(report_content)
    
    def fail(self, error: str):
        """Mark task as failed."""
        status = self.get_status()
        if not status:
            return
        
        status["status"] = "failed"
        status["error"] = error
        status["failed_at"] = time.time()
        
        self._write_status(status)
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get current status."""
        try:
            with open(self._status_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    def get_report(self) -> Optional[str]:
        """Get report content."""
        try:
            with open(self._report_path(), 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return None


def get_bridge(session_id: str) -> BlackboardBridge:
    """Factory function to get bridge instance."""
    return BlackboardBridge(session_id)
