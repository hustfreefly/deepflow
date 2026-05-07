from fastapi import APIRouter
import subprocess
import json

router = APIRouter()

def check_openclaw_status():
    """Check if OpenClaw is installed and running."""
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return {"status": "connected", "details": result.stdout.strip()}
        else:
            return {"status": "disconnected", "details": result.stderr.strip()}
    except FileNotFoundError:
        return {"status": "not_installed", "details": "OpenClaw CLI not found"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "details": "OpenClaw status check timed out"}
    except Exception as e:
        return {"status": "error", "details": str(e)}

@router.get("/health")
def health_check():
    """Health check endpoint that also verifies OpenClaw connectivity."""
    openclaw = check_openclaw_status()
    
    return {
        "status": "ok",
        "version": "0.1.0",
        "openclaw": openclaw
    }