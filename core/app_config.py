"""
DeepFlow Configuration Loader

Loads config.json and merges with defaults.
All modules should use load_config() instead of hardcoding values.
"""
import json
from pathlib import Path
from typing import Dict, Any

# Resolve deepflow root (this file is in .deepflow/core/)
DEEPFLOW_ROOT = Path(__file__).parent.parent
CONFIG_FILE = DEEPFLOW_ROOT / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "backend": {
        "host": "127.0.0.1",
        "port": 17789,
        "health_path": "/api/health"
    },
    "frontend": {
        "host": "127.0.0.1",
        "port": 17788
    },
    "cron": {
        "interval": "2m",
        "timeout_seconds": 1800,
        "name": "DeepFlow Task Processor"
    },
    "paths": {
        "blackboard": "blackboard",
        "database": "frontend/backend/data/tasks.db",
        "task_queue": "frontend/task_queue"
    },
    "webhook": {
        "url": "http://127.0.0.1:18789/hooks/wake",
        "env_file": "~/.openclaw/.webhook_env"
    }
}


def _merge(defaults: dict, overrides: dict) -> dict:
    """Deep merge: overrides take precedence."""
    result = defaults.copy()
    for k, v in overrides.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json, merged with defaults."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding='utf-8') as f:
            user_cfg = json.load(f)
        return _merge(DEFAULT_CONFIG, user_cfg)
    return DEFAULT_CONFIG.copy()


def resolve_path(path_str: str) -> Path:
    """Resolve a path string relative to DEEPFLOW_ROOT, expanding ~."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = DEEPFLOW_ROOT / p
    return p
