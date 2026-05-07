from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import health, tasks, status

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
