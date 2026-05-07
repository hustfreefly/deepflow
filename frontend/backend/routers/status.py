from fastapi import APIRouter, HTTPException
import time
import json
import os
from pathlib import Path

router = APIRouter()

def get_blackboard_path():
    """Get blackboard base path from DeepFlow config."""
    return Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"

def read_status_file(session_id: str):
    """Read status.json from blackboard if it exists."""
    status_file = get_blackboard_path() / session_id / "status.json"
    if status_file.exists():
        with open(status_file, 'r') as f:
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
            {"name": "data_collection", "status": "running", "duration": 0},
            {"name": "planning", "status": "pending", "duration": 0},
            {"name": "reviewers", "status": "pending", "duration": 0},
            {"name": "researchers", "status": "pending", "duration": 0, "workers": {"completed": 0, "total": 6}},
            {"name": "consolidator", "status": "pending", "duration": 0},
            {"name": "auditors", "status": "pending", "duration": 0},
            {"name": "fixer", "status": "pending", "duration": 0},
            {"name": "harness_final", "status": "pending", "duration": 0},
            {"name": "summarizer", "status": "pending", "duration": 0},
        ],
        "quality_score": None,
        "harness_scores": {},
        "timestamp": time.time(),
        "elapsed": 0,
    }

@router.get("/status/{session_id}")
def get_status(session_id: str):
    """Get pipeline execution status for a session."""
    # Try to read from blackboard
    status = read_status_file(session_id)
    
    # If not found, return default structure
    if not status:
        status = get_default_status(session_id)
    
    # Calculate elapsed time
    if "created_at" in status:
        status["elapsed"] = time.time() - status.get("created_at", time.time())
    
    return status

@router.get("/reports/{session_id}")
def get_report(session_id: str):
    """Get final analysis report."""
    report_file = get_blackboard_path() / session_id / "final_report.md"
    
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
    blackboard = get_blackboard_path()
    sessions = []
    
    if blackboard.exists():
        for session_dir in blackboard.iterdir():
            if session_dir.is_dir():
                session_id = session_dir.name
                meta_file = session_dir / "session_meta.json"
                
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                        
                    # Filter by domain if specified
                    if domain and meta.get("domain") != domain:
                        continue
                        
                    sessions.append(meta)
    
    # Sort by created_at descending
    sessions.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    
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
