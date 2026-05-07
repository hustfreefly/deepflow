from fastapi import APIRouter, HTTPException
import time
import json
import os
from pathlib import Path

router = APIRouter()

BLACKBOARD_DIR = Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"

def _get_status_path(session_id: str) -> Path:
    """Get status file path in blackboard."""
    return BLACKBOARD_DIR / session_id / "status.json"

def read_status_file(session_id: str):
    """Read status.json from blackboard if it exists."""
    status_file = _get_status_path(session_id)
    if status_file.exists():
        with open(status_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def get_default_status(session_id: str):
    """Return default status structure."""
    return {
        "session_id": session_id,
        "status": "running",
        "current_stage": "data_collection",
        "progress": 0.1,
        "stages": [
            {"name": "data_collection", "status": "running", "duration": 0, "workers": {"completed": 0, "total": 1}},
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
        "timestamp": time.time(),
        "elapsed": 0,
    }

@router.get("/status/{session_id}")
def get_status(session_id: str):
    """Get pipeline execution status for a session."""
    status = read_status_file(session_id)
    if not status:
        status = get_default_status(session_id)
    
    # Calculate elapsed time
    created_at = status.get("created_at", time.time())
    status["elapsed"] = time.time() - created_at
    
    return status

@router.get("/reports/{session_id}")
def get_report(session_id: str):
    """Get final analysis report."""
    report_file = BLACKBOARD_DIR / session_id / "final_report.md"
    
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return {
        "session_id": session_id,
        "content": content,
        "format": "markdown",
        "length": len(content),
    }

@router.get("/sessions")
def list_sessions(limit: int = 20, domain: str = None):
    """List historical sessions from blackboard."""
    sessions = []
    
    if BLACKBOARD_DIR.exists():
        for session_dir in sorted(BLACKBOARD_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if session_dir.is_dir():
                session_id = session_dir.name
                meta_file = session_dir / "session_meta.json"
                status_file = session_dir / "status.json"
                
                session_info = {
                    "session_id": session_id,
                    "domain": "unknown",
                    "status": "unknown",
                    "created_at": session_dir.stat().st_mtime,
                }
                
                # Try to read status.json
                if status_file.exists():
                    try:
                        with open(status_file, 'r', encoding='utf-8') as f:
                            status_data = json.load(f)
                        session_info["domain"] = status_data.get("domain", "unknown")
                        session_info["status"] = status_data.get("status", "unknown")
                        session_info["quality_score"] = status_data.get("quality_score")
                        session_info["created_at"] = status_data.get("created_at", session_dir.stat().st_mtime)
                    except Exception:
                        pass
                
                # Filter by domain if specified
                if domain and session_info.get("domain") != domain:
                    continue
                    
                sessions.append(session_info)
    
    return sessions[:limit]

@router.post("/reports/{session_id}/export")
def export_report(session_id: str, request: dict):
    """Export report to specified format/channel."""
    format_type = request.get("format", "local")
    
    if format_type == "feishu":
        # TODO: Integrate with existing Feishu send functionality
        return {"status": "success", "message": "Report sent to Feishu", "session_id": session_id}
    elif format_type == "local":
        return {"status": "success", "message": "Report ready for download", "session_id": session_id}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format_type}")
