"""
Status API v2 - Read from Blackboard.
"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException

router = APIRouter()

# Blackboard directory
# Configuration
_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # routers/ → backend/ → frontend/ → .deepflow/
_CFG_FILE = _DEEPFLOW_ROOT / "config.json"

def _load_cfg() -> dict:
    defaults = {
        "paths": {"blackboard": "blackboard"}
    }
    if _CFG_FILE.exists():
        with open(_CFG_FILE) as f:
            user = json.load(f)
        if "paths" in user:
            defaults["paths"].update(user["paths"])
    return defaults

_cfg = _load_cfg()
BLACKBOARD_DIR = _DEEPFLOW_ROOT / _cfg["paths"]["blackboard"]

# Valid session_id pattern: alphanumeric, underscore, hyphen
SESSION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def _validate_session_id(session_id: str) -> None:
    """Validate session_id format to prevent path traversal."""
    if not SESSION_ID_PATTERN.match(session_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid session ID format. Only alphanumeric, underscore, and hyphen allowed."
        )


def _get_status_path(session_id: str) -> Path:
    """Get status.json path for session."""
    _validate_session_id(session_id)
    status_path = BLACKBOARD_DIR / session_id / "status.json"
    
    # Ensure path is within BLACKBOARD_DIR (defense in depth)
    try:
        status_path.relative_to(BLACKBOARD_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    
    return status_path


def _get_report_path(session_id: str) -> Path:
    """Get report.md path for session."""
    _validate_session_id(session_id)
    report_path = BLACKBOARD_DIR / session_id / "report.md"
    
    # Ensure path is within BLACKBOARD_DIR (defense in depth)
    try:
        report_path.relative_to(BLACKBOARD_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    
    return report_path


@router.get("/status/{session_id}")
def get_status(session_id: str) -> Dict[str, Any]:
    """Get task execution status from Blackboard."""
    status_path = _get_status_path(session_id)
    
    if not status_path.exists():
        # Check if task exists in database
        from database import get_db
        db = get_db()
        task = db.get_task(session_id)
        
        if task:
            # Task exists but not started yet
            return {
                "session_id": session_id,
                "status": task.status,
                "current_stage": "waiting",
                "progress": 0.0,
                "stages": [],
                "message": "Task queued, waiting for agent"
            }
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        with open(status_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        
        # Map Blackboard format → Frontend expected format
        # Blackboard uses: phases[], current_phase, status
        # Frontend expects: stages[], current_stage, progress
        phases = raw.get('phases', [])
        current_phase_idx = raw.get('current_phase', 0)
        total_phases = raw.get('total_phases', len(phases))
        
        # Build stages array in frontend format
        stages = []
        for p in phases:
            stage_name = p.get('stage', p.get('name', f'phase_{p.get("phase", "?")}') )
            stage_status = p.get('status', 'pending')
            stages.append({
                'name': stage_name,
                'status': stage_status,
                'duration': 0,
                'workers': {'completed': 1 if stage_status == 'completed' else 0, 'total': 1}
            })
        
        # Calculate progress
        completed_count = sum(1 for s in stages if s['status'] == 'completed')
        progress = completed_count / max(len(stages), 1)
        
        # Determine current stage
        if raw.get('status') == 'completed':
            current_stage = stages[-1]['name'] if stages else 'summarizer'
        elif stages:
            for s in stages:
                if s['status'] == 'running':
                    current_stage = s['name']
                    break
            else:
                # Find first pending stage
                for s in stages:
                    if s['status'] == 'pending':
                        current_stage = s['name']
                        break
                else:
                    current_stage = stages[-1]['name'] if stages else ''
        else:
            current_stage = 'waiting'
        
        return {
            'session_id': raw.get('session_id', session_id),
            'status': raw.get('status', 'running'),
            'current_stage': current_stage,
            'progress': progress,
            'stages': stages,
            'topic': raw.get('topic', ''),
            'solution_type': raw.get('solution_type', ''),
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid status file")


@router.get("/reports/{session_id}")
def get_report(session_id: str) -> dict:
    """Get final report as JSON.
    
    Frontend expects: {session_id, content, format, length}
    Checks multiple possible report filenames:
    - report.md (standard)
    - final_solution.md (Solution Pro)
    - final_report.md (alternative)
    """
    _validate_session_id(session_id)
    session_dir = BLACKBOARD_DIR / session_id
    
    report_content = None
    found_file = None
    
    # Try multiple report filenames
    for filename in ('report.md', 'final_solution.md', 'final_report.md'):
        report_path = session_dir / filename
        try:
            report_path.relative_to(BLACKBOARD_DIR)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session ID")
        
        if report_path.exists():
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    report_content = f.read()
                found_file = filename
                break
            except (IOError, OSError) as e:
                raise HTTPException(status_code=500, detail=f"Error reading report: {e}")
    
    if report_content:
        return {
            "session_id": session_id,
            "content": report_content,
            "format": "markdown",
            "length": len(report_content),
            "source_file": found_file,
        }
    
    # No report found
    status_path = session_dir / "status.json"
    if status_path.exists():
        raise HTTPException(status_code=404, detail="Report not yet generated")
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions")
def list_sessions(limit: int = 50) -> list:
    """List sessions from SQLite ONLY (source of truth for frontend tasks).
    
    Blackboard sessions are NOT included here — they contain legacy data.
    Use /api/v2/sessions/{id}/stages to access specific session's pipeline data.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from database import get_db
    
    sessions = []
    try:
        db = get_db()
        for db_status in ('completed', 'failed', 'running'):
            for task in db.get_tasks_by_status(db_status):
                sessions.append({
                    "session_id": task.session_id,
                    "domain": task.domain,
                    "status": task.status,
                    "created_at": task.created_at,
                    "completed_at": task.updated_at,
                    "progress": 1.0 if task.status == 'completed' else 0.0,
                    "topic": task.parameters.get("topic", task.parameters.get("code", "")),
                    "code": task.parameters.get("code", ""),
                    "name": task.parameters.get("name", ""),
                })
    except Exception as e:
        print(f"[Status] Error reading SQLite: {e}")
    
    # Sort by created_at descending
    def _parse_ts(v):
        if v is None: return 0
        if isinstance(v, (int, float)): return v
        try: return float(v)
        except (ValueError, TypeError): return 0
    sessions.sort(key=lambda s: _parse_ts(s.get("created_at")), reverse=True)
    return sessions[:limit]


@router.get("/active-task")
def get_active_task() -> Optional[dict]:
    """Get the currently active task.
    
    Priority: Blackboard status.json > SQLite task info.
    Returns real pipeline progress if available, otherwise queued state.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from database import get_db
    
    try:
        db = get_db()
        # Check pending, waiting_agent, running
        tasks = []
        for status in ('running', 'waiting_agent', 'pending'):
            tasks = db.get_tasks_by_status(status)
            if tasks:
                break
        
        if not tasks:
            return None
        
        task = tasks[0]
        params = task.parameters
        
        # Try to get real pipeline progress from Blackboard
        session_dir = BLACKBOARD_DIR / task.session_id
        status_json_path = session_dir / "status.json"
        
        pipeline_info = {}
        if status_json_path.exists():
            try:
                with open(status_json_path, 'r', encoding='utf-8') as f:
                    bb_status = json.load(f)
                pipeline_info = {
                    "progress": bb_status.get("progress", 0),
                    "current_stage": bb_status.get("current_stage", ""),
                    "stages": bb_status.get("stages", []),
                    "blackboard_status": bb_status.get("status", ""),
                }
            except (json.JSONDecodeError, IOError):
                pass
        
        return {
            "session_id": task.session_id,
            "domain": task.domain,
            "status": task.status,
            "topic": params.get("topic", ""),
            "code": params.get("code", ""),
            "name": params.get("name", ""),
            "created_at": task.created_at,
            **pipeline_info,
        }
    except Exception as e:
        print(f"[Status] Error getting active task: {e}")
        return None


@router.get("/sessions/{session_id}/stages")
def get_session_stages(session_id: str) -> dict:
    """Get all pipeline stage output files for a session.
    
    Returns stage metadata from stages/*.json files.
    Each stage includes: status, stage name, data content, harness assessment.
    """
    _validate_session_id(session_id)
    session_dir = BLACKBOARD_DIR / session_id
    
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    stages_dir = session_dir / "stages"
    data_dir = session_dir / "data"
    
    stages = {}
    if stages_dir.exists():
        for stage_file in sorted(stages_dir.glob("*.json")):
            try:
                with open(stage_file, 'r', encoding='utf-8') as f:
                    stage_data = json.load(f)
                stage_name = stage_file.stem
                stages[stage_name] = {
                    "status": stage_data.get("status", "unknown"),
                    "stage": stage_data.get("stage", stage_name),
                    "data": stage_data.get("data", {}),
                    "harness_self_assessment": stage_data.get("harness_self_assessment"),
                }
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {stage_file}: {e}")
    
    data_files = {}
    if data_dir.exists():
        for data_file in sorted(data_dir.glob("*.json")):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data_files[data_file.stem] = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {data_file}: {e}")
    
    return {
        "session_id": session_id,
        "stages": stages,
        "data": data_files,
        "stage_order": ["data_collection", "planning", "reviewers", "research", "consolidator", "audit", "fix", "fixer_expert", "harness_final", "summarizer"],
    }


@router.get("/sessions/{session_id}/stages")
def get_session_stages(session_id: str) -> dict:
    """Get all pipeline stage output files for a session.
    
    Returns stage metadata from stages/*.json files.
    Each stage includes: status, stage name, data content, harness assessment.
    """
    _validate_session_id(session_id)
    session_dir = BLACKBOARD_DIR / session_id
    
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    stages_dir = session_dir / "stages"
    data_dir = session_dir / "data"
    
    stages = {}
    if stages_dir.exists():
        for stage_file in sorted(stages_dir.glob("*.json")):
            try:
                with open(stage_file, 'r', encoding='utf-8') as f:
                    stage_data = json.load(f)
                stage_name = stage_file.stem
                stages[stage_name] = {
                    "status": stage_data.get("status", "unknown"),
                    "stage": stage_data.get("stage", stage_name),
                    "data": stage_data.get("data", {}),
                    "harness_self_assessment": stage_data.get("harness_self_assessment"),
                }
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {stage_file}: {e}")
    
    data_files = {}
    if data_dir.exists():
        for data_file in sorted(data_dir.glob("*.json")):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data_files[data_file.stem] = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {data_file}: {e}")
    
    # Define canonical stage order
    stage_order = [
        "data_collection", "planning",
        "review_business", "review_technical", "review_risk",
        "research_expert_1", "research_expert_2", "research_expert_3",
        "consolidator", "audit", "fix", "fixer_expert", "harness_final", "summarizer"
    ]
    
    return {
        "session_id": session_id,
        "stages": stages,
        "data": data_files,
        "stage_order": stage_order,
    }


@router.get("/sessions/{session_id}/stages")
def get_session_stages(session_id: str) -> dict:
    """Get all pipeline stage output files for a session."""
    _validate_session_id(session_id)
    session_dir = BLACKBOARD_DIR / session_id
    
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    stages_dir = session_dir / "stages"
    data_dir = session_dir / "data"
    
    stages = {}
    if stages_dir.exists():
        for stage_file in sorted(stages_dir.glob("*.json")):
            try:
                with open(stage_file, 'r', encoding='utf-8') as f:
                    stage_data = json.load(f)
                stage_name = stage_file.stem
                stages[stage_name] = {
                    "status": stage_data.get("status", "unknown"),
                    "stage": stage_data.get("stage", stage_name),
                    "data": stage_data.get("data", {}),
                    "harness_self_assessment": stage_data.get("harness_self_assessment"),
                }
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {stage_file}: {e}")
    
    data_files = {}
    if data_dir.exists():
        for data_file in sorted(data_dir.glob("*.json")):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data_files[data_file.stem] = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {data_file}: {e}")
    
    # Canonical stage order
    stage_order = [
        "data_collection", "planning",
        "review_business", "review_technical", "review_risk",
        "research_expert_1", "research_expert_2", "research_expert_3",
        "consolidator", "audit", "fix", "fixer_expert", "harness_final", "summarizer"
    ]
    
    return {
        "session_id": session_id,
        "stages": stages,
        "data": data_files,
        "stage_order": stage_order,
    }


@router.get("/sessions/{session_id}/stages")
def get_session_stages(session_id: str) -> dict:
    """Get all pipeline stage output files for a session.
    
    Returns stage metadata from stages/*.json files.
    Each stage includes: status, stage name, data content, harness assessment.
    """
    _validate_session_id(session_id)
    session_dir = BLACKBOARD_DIR / session_id
    
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    stages_dir = session_dir / "stages"
    data_dir = session_dir / "data"
    
    stages = {}
    if stages_dir.exists():
        for stage_file in sorted(stages_dir.glob("*.json")):
            try:
                with open(stage_file, 'r', encoding='utf-8') as f:
                    stage_data = json.load(f)
                stage_name = stage_file.stem
                stages[stage_name] = {
                    "status": stage_data.get("status", "unknown"),
                    "stage": stage_data.get("stage", stage_name),
                    "data": stage_data.get("data", {}),
                    "harness_self_assessment": stage_data.get("harness_self_assessment"),
                }
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {stage_file}: {e}")
    
    data_files = {}
    if data_dir.exists():
        for data_file in sorted(data_dir.glob("*.json")):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data_files[data_file.stem] = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {data_file}: {e}")
    
    return {
        "session_id": session_id,
        "stages": stages,
        "data": data_files,
        "stage_order": ["data_collection", "planning", "reviewers", "research", "consolidator", "audit", "fix", "fixer_expert", "harness_final", "summarizer"],
    }


@router.get("/sessions/{session_id}/stages")
def get_session_stages(session_id: str) -> dict:
    """Get all pipeline stage output files for a session.
    
    Returns stage metadata from stages/*.json files.
    Each stage includes: status, stage name, data content, harness assessment.
    """
    _validate_session_id(session_id)
    session_dir = BLACKBOARD_DIR / session_id
    
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    
    stages_dir = session_dir / "stages"
    data_dir = session_dir / "data"
    
    stages = {}
    if stages_dir.exists():
        for stage_file in sorted(stages_dir.glob("*.json")):
            try:
                with open(stage_file, 'r', encoding='utf-8') as f:
                    stage_data = json.load(f)
                stage_name = stage_file.stem
                stages[stage_name] = {
                    "status": stage_data.get("status", "unknown"),
                    "stage": stage_data.get("stage", stage_name),
                    "data": stage_data.get("data", {}),
                    "harness_self_assessment": stage_data.get("harness_self_assessment"),
                }
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {stage_file}: {e}")
    
    data_files = {}
    if data_dir.exists():
        for data_file in sorted(data_dir.glob("*.json")):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data_files[data_file.stem] = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Stages] Error reading {data_file}: {e}")
    
    # Canonical stage order
    stage_order = [
        "data_collection", "planning",
        "review_business", "review_technical", "review_risk",
        "research_expert_1", "research_expert_2", "research_expert_3",
        "consolidator", "audit", "fix", "fixer_expert", "harness_final", "summarizer"
    ]
    
    return {
        "session_id": session_id,
        "stages": stages,
        "data": data_files,
        "stage_order": stage_order,
    }

@router.get("/system-info")
def get_system_info() -> dict:
    """Get system configuration info for Settings panel."""
    import subprocess
    from pathlib import Path
    
    # Config
    _DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    _CFG_FILE = _DEEPFLOW_ROOT / "config.json"
    config = {
        "frontend_port": 17788,
        "backend_port": 17789,
        "webhook_url": "",
    }
    if _CFG_FILE.exists():
        with open(_CFG_FILE) as f:
            cfg = json.load(f)
        config["frontend_port"] = cfg.get("ports", {}).get("frontend", 17788)
        config["backend_port"] = cfg.get("ports", {}).get("backend", 17789)
        config["webhook_url"] = cfg.get("webhook", {}).get("url", "")
    
    # OpenClaw version
    try:
        result = subprocess.run(["openclaw", "--version"], capture_output=True, text=True, timeout=5)
        oc_version = result.stdout.strip() or "unknown"
    except (subprocess.SubprocessError, OSError):
        oc_version = "unknown"
    
    # Session count
    session_count = 0
    if BLACKBOARD_DIR.exists():
        session_count = len([d for d in BLACKBOARD_DIR.iterdir() if d.is_dir()])
    
    return {
        "openclaw": {"status": "connected", "version": oc_version},
        "backend": {"version": "v2.0", "host": "127.0.0.1", "port": config["backend_port"]},
        "blackboard": {"path": str(BLACKBOARD_DIR), "session_count": session_count},
        "config": config,
    }


@router.get("/system-info")
def get_system_info() -> dict:
    """Get system configuration info for Settings panel."""
    import subprocess
    
    # Config
    config = {
        "frontend_port": 17788,
        "backend_port": 17789,
        "webhook_url": "",
    }
    if _CFG_FILE.exists():
        with open(_CFG_FILE) as f:
            cfg = json.load(f)
        config["frontend_port"] = cfg.get("ports", {}).get("frontend", 17788)
        config["backend_port"] = cfg.get("ports", {}).get("backend", 17789)
        config["webhook_url"] = cfg.get("webhook", {}).get("url", "")
    
    # OpenClaw version
    try:
        result = subprocess.run(["openclaw", "--version"], capture_output=True, text=True, timeout=5)
        oc_version = result.stdout.strip() or "unknown"
    except (subprocess.SubprocessError, OSError):
        oc_version = "unknown"
    
    # Session count
    session_count = 0
    if BLACKBOARD_DIR.exists():
        session_count = len([d for d in BLACKBOARD_DIR.iterdir() if d.is_dir()])
    
    return {
        "openclaw": {"status": "connected", "version": oc_version},
        "backend": {"version": "v2.0", "host": "127.0.0.1", "port": config["backend_port"]},
        "blackboard": {"path": str(BLACKBOARD_DIR), "session_count": session_count},
        "config": config,
    }
