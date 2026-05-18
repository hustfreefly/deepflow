from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
from routers import health, tasks, status, consumer

# Import v2 routers (Webhook integration)
try:
    from routers import tasks_v2, status_v2
    V2_ROUTERS_AVAILABLE = True
except ImportError:
    V2_ROUTERS_AVAILABLE = False

# Import Spec Pro upload router
try:
    from routers import upload as upload_router
    UPLOAD_ROUTER_AVAILABLE = True
except ImportError:
    UPLOAD_ROUTER_AVAILABLE = False

app = FastAPI(
    title="DeepFlow Frontend API",
    description="Backend API for DeepFlow Frontend UI",
    version="0.2.0"
)

# ── Configuration (loaded once, no hardcoded ports) ──
_DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent
_CFG_FILE = _DEEPFLOW_ROOT / "config.json"

def _load_cfg() -> dict:
    defaults = {
        "backend": {"host": "127.0.0.1", "port": 17789},
        "frontend": {"host": "127.0.0.1", "port": 17788},
    }
    if _CFG_FILE.exists():
        with open(_CFG_FILE) as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and k in defaults:
                defaults[k].update(v)
            else:
                defaults[k] = v
    return defaults

_cfg = _load_cfg()
_FRONTEND_PORT = _cfg["frontend"]["port"]

# CORS: configured frontend port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{_FRONTEND_PORT}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api", tags=["health"])

# Use v2 routers if available (Webhook integration)
if V2_ROUTERS_AVAILABLE:
    print("[Startup] Using v2 routers with Webhook integration")
    app.include_router(tasks_v2.router, prefix="/api/v2", tags=["tasks-v2"])
    app.include_router(status_v2.router, prefix="/api/v2", tags=["status-v2"])
    # Keep v1 routers for backward compatibility
    app.include_router(tasks.router, prefix="/api", tags=["tasks"])
    app.include_router(status.router, prefix="/api", tags=["status"])
else:
    print("[Startup] Using v1 routers (legacy)")
    app.include_router(tasks.router, prefix="/api", tags=["tasks"])
    app.include_router(status.router, prefix="/api", tags=["status"])

# Register Spec Pro upload router
if UPLOAD_ROUTER_AVAILABLE:
    print("[Startup] Spec Pro upload router enabled")
    app.include_router(upload_router.router, prefix="/api/v2", tags=["upload"])

@app.get("/")
def root():
    return {"message": "DeepFlow Frontend API", "version": "0.1.0"}

@app.get("/api/consumer/status")
def consumer_status():
    """Get task queue consumer status."""
    return consumer.get_consumer_status()

@app.post("/api/consumer/start")
def start_consumer():
    """Start task queue consumer."""
    consumer.start_consumer()
    return {"status": "started"}

@app.post("/api/consumer/stop")
def stop_consumer():
    """Stop task queue consumer."""
    consumer.stop_consumer()
    return {"status": "stopped"}

@app.on_event("startup")
def startup_event():
    """Auto-start task consumer on startup."""
    _backend_port = _cfg["backend"]["port"]
    print(f"[Startup] Backend port: {_backend_port}, Frontend port: {_FRONTEND_PORT}")
    consumer.start_consumer()
