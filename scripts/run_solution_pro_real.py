#!/usr/bin/env python3
"""
Real Solution Pro pipeline runner with file-based spawn bridge.

The spawn bridge works as follows:
1. Python orchestrator calls spawn_fn(task, mode, label)
2. spawn_fn writes a request to /tmp/spawn_bridge/pending.json
3. spawn_fn blocks, polling for result at /tmp/spawn_bridge/result_{label}.json
4. External Agent reads pending.json, executes sessions_spawn, writes result
5. spawn_fn detects result, returns to orchestrator

This bridges Python orchestrators with Agent-level sessions_spawn.
"""

import sys
import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime

# Setup path
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from domains.solution_pro.blackboard import BlackboardManager
from domains.solution_pro.master_orchestrator import MasterOrchestrator

# ============================================================
# Configuration
# ============================================================

BRIDGE_DIR = Path("/tmp/spawn_bridge")
SESSION_ID = f"ai_loop_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LIVING_SPEC_PATH = _root / "domains/solution_pro/blackboard_sessions/ai_loop_v3_full/data/living_spec.json"

# Timeout per stage (seconds)
STAGE_TIMEOUT = 600  # 10 minutes per stage

# ============================================================
# Spawn Bridge
# ============================================================

def spawn_bridge(task: str, mode: str = "run", label: str = "") -> dict:
    """
    File-based spawn bridge.
    
    1. Writes spawn request to pending.json
    2. Polls for result file
    3. Returns result dict
    """
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write request
    request = {
        "task": task,
        "mode": mode,
        "label": label,
        "timestamp": datetime.now().isoformat(),
        "status": "pending",
    }
    
    request_path = BRIDGE_DIR / "pending.json"
    result_path = BRIDGE_DIR / f"result_{label}.json"
    
    # Clean up old result
    if result_path.exists():
        result_path.unlink()
    
    # Write request
    with open(request_path, "w") as f:
        json.dump(request, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"🔄 SPAWN REQUEST: {label}")
    print(f"{'='*60}")
    print(f"Task preview: {task[:200]}...")
    print(f"Waiting for Agent to execute and write result to: {result_path}")
    
    # Poll for result
    start = time.time()
    while time.time() - start < STAGE_TIMEOUT:
        if result_path.exists():
            try:
                with open(result_path) as f:
                    result = json.load(f)
                print(f"✅ Result received for {label}")
                # Clean up
                result_path.unlink()
                return result
            except (json.JSONDecodeError, IOError):
                pass
        time.sleep(2)
    
    # Timeout
    print(f"❌ TIMEOUT waiting for {label} ({STAGE_TIMEOUT}s)")
    return {"status": "timeout", "label": label}


# ============================================================
# Main Execution
# ============================================================

def main():
    print
    print(f"   Session: {SESSION_ID}")
    print(f"   Living Spec: {LIVING_SPEC_PATH.name}")
    print(f"   Bridge: {BRIDGE_DIR}")
    print()
    
    # Load Living Spec
    with open(LIVING_SPEC_PATH) as f:
        living_spec = json.load(f)
    
    print(f"📋 Living Spec loaded:")
    print(f"   Core summary: {living_spec.get('core_summary', '')[:100]}...")
    print(f"   Requirements: {len(living_spec.get('requirement_index', []))}")
    print()
    
    # Create Blackboard
    bb = BlackboardManager(SESSION_ID)
    print(f"📁 Blackboard: {bb.session_dir}")
    
    # Write Living Spec to blackboard
    bb.write("data/living_spec.json", living_spec)
    
    # Write frozen spec (built from living spec)
    frozen_spec = {
        "topic": "OpenClaw AI Native Loop Engineering Framework",
        "solution_type": "architecture",
        "mode": "standard",
        "domain": "ai_agent_framework",
        "constraints": [
            {"req_id": r["id"], "description": r["title"], "priority": r["priority"]}
            for r in living_spec.get("requirement_index", [])
            if r.get("priority") == "P0"
        ],
    }
    bb.write("data/frozen_spec.json", frozen_spec)
    
    # Structured requirements
    structured_req = {
        "version": "1.0",
        "topic": frozen_spec["topic"],
        "requirements": [
            {
                "id": r["id"],
                "category": r.get("category", "capability"),
                "description": r["title"],
                "priority": r["priority"],
                "source": "explicit",
            }
            for r in living_spec.get("requirement_index", [])
        ],
    }
    bb.write("data/structured_requirements.json", structured_req)
    
    # Create MasterOrchestrator with spawn bridge
    master = MasterOrchestrator(blackboard=bb, spawn_fn=spawn_bridge)
    
    # Run pipeline
    print(f"\n🏗️  Starting Pipeline: Planning → Research → ReviewQC\n")
    
    config = {
        "topic": "OpenClaw AI Native Loop Engineering Framework",
        "solution_type": "architecture",
        "mode": "standard",
        "domain": "ai_agent_framework",
    }
    
    try:
        result = master.run(
            user_input="基于OpenClaw构建完整的AI Native Loop Engineering框架",
            config=config,
            living_spec=living_spec,
        )
        
        print(f"\n{'='*60}")
        print(f"🎉 Pipeline Complete!")
        print(f"{'='*60}")
        print(f"Status: {result.get('status', 'UNKNOWN')}")
        
        # Write final result
        result_path = bb.session_dir / "pipeline_result.json"
        with open(result_path, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Result: {result_path}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Write error state
        error_path = BRIDGE_DIR / "error.json"
        with open(error_path, "w") as f:
            json.dump({"error": str(e), "traceback": traceback.format_exc()}, f)
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
