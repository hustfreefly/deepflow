from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import health, tasks, status, consumer

app = FastAPI(
    title="DeepFlow Frontend API",
    description="Backend API for DeepFlow Frontend UI",
    version="0.1.0"
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(status.router, prefix="/api", tags=["status"])

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

# Auto-start consumer on startup
@app.on_event("startup")
def startup_event():
    """Auto-start task consumer on startup."""
    consumer.start_consumer()
