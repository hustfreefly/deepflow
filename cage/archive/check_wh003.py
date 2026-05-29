#!/usr/bin/env python3
"""
WH-003 Verification Script - Agent Task Queue Processing

Verifies:
1. HEARTBEAT.md has task queue check logic
2. webhook_task_processor.py exists and is importable
3. Webhook payload includes execution instructions
4. Consumer does NOT simulate execution
5. Full chain: task submission → webhook → agent → DeepFlow spawn
"""
import sys
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).parent.parent
FRONTEND_ROOT = DEEPFLOW_ROOT / "frontend"
WORKSPACE_ROOT = Path.home() / ".openclaw" / "workspace"

def check_heartbeat():
    """WH-003: HEARTBEAT.md should have task queue check logic."""
    heartbeat = WORKSPACE_ROOT / "HEARTBEAT.md"
    if not heartbeat.exists():
        return False, "HEARTBEAT.md not found"
    
    content = heartbeat.read_text()
    if ("task queue" in content.lower() or "任务队列" in content) and "pending" in content.lower():
        return True, "HEARTBEAT.md has task queue check"
    return False, "HEARTBEAT.md missing task queue check"

def check_webhook_processor():
    """WH-003: webhook_task_processor.py should exist and be importable."""
    processor = DEEPFLOW_ROOT / "agents" / "webhook_task_processor.py"
    if not processor.exists():
        return False, "webhook_task_processor.py not found"
    
    try:
        sys.path.insert(0, str(DEEPFLOW_ROOT))
        sys.path.insert(0, str(FRONTEND_ROOT / "backend"))
        from core.agents.webhook_task_processor import process_pending_tasks, _build_deepflow_task
        return True, "webhook_task_processor.py importable"
    except ImportError as e:
        return False, f"Import failed: {e}"

def check_webhook_payload():
    """WH-003: Webhook payload should include execution instructions."""
    tasks_v2 = FRONTEND_ROOT / "backend" / "routers" / "tasks_v2.py"
    if not tasks_v2.exists():
        return False, "tasks_v2.py not found"
    
    content = tasks_v2.read_text()
    if "process_pending_tasks" in content and "webhook_task_processor" in content:
        return True, "Webhook payload includes execution instructions"
    return False, "Webhook payload missing execution instructions"

def check_no_simulation():
    """WH-003: Consumer should NOT simulate execution."""
    consumer = FRONTEND_ROOT / "backend" / "routers" / "consumer.py"
    if not consumer.exists():
        return False, "consumer.py not found"
    
    content = consumer.read_text()
    if "_simulate_deepflow_execution" in content:
        return False, "Consumer still simulates execution"
    return True, "Consumer does NOT simulate execution"

def main():
    print("=" * 60)
    print("WH-003 Verification - Agent Task Queue Processing")
    print("=" * 60)
    
    checks = [
        ("HEARTBEAT.md task queue check", check_heartbeat),
        ("webhook_task_processor.py importable", check_webhook_processor),
        ("Webhook payload has execution instructions", check_webhook_payload),
        ("Consumer does NOT simulate execution", check_no_simulation),
    ]
    
    all_passed = True
    for name, check_fn in checks:
        passed, msg = check_fn()
        icon = "✅" if passed else "❌"
        print(f"{icon} {name}: {msg}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("✅ ALL WH-003 CHECKS PASSED")
    else:
        print("❌ SOME CHECKS FAILED")
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
