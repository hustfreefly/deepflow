#!/usr/bin/env python3
"""Solution Pro Full E2E Runner with file-bridge spawn_fn"""
import sys, os, json, time, uuid, logging
from pathlib import Path

DEEPFLOW = os.path.expanduser("~/.openclaw/workspace/.deepflow")
os.chdir(DEEPFLOW)
sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("full_e2e")

QUEUE_DIR = "/tmp/spawn_queue"
os.makedirs(QUEUE_DIR, exist_ok=True)

stats = {"tasks_queued": 0, "tasks_completed": 0, "tasks_timed_out": 0, "start_time": time.time()}

def bridge_spawn_fn(task=None, output_path=None, timeout=600, **kwargs):
    task_id = str(uuid.uuid4())[:8]
    task_file = os.path.join(QUEUE_DIR, f"{task_id}.task.json")
    result_file = os.path.join(QUEUE_DIR, f"{task_id}.result.json")
    
    task_data = {
        "task_id": task_id,
        "task_length": len(task) if task else 0,
        "full_task": task or "",
        "output_path": output_path,
        "timeout": timeout,
        "created_at": time.time(),
    }
    with open(task_file, 'w') as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)
    
    stats["tasks_queued"] += 1
    task_preview = (task or "")[:120].replace('\n', ' ')
    logger.info(f"[BRIDGE] Task {task_id} queued (#{stats['tasks_queued']}, {len(task or '')} chars, output={output_path})")
    
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(result_file):
            try:
                with open(result_file) as f:
                    result = json.load(f)
                elapsed = time.time() - start
                stats["tasks_completed"] += 1
                logger.info(f"[BRIDGE] Task {task_id} done ({elapsed:.0f}s, #{stats['tasks_completed']}/{stats['tasks_queued']})")
                for fp in [task_file, result_file]:
                    if os.path.exists(fp): os.remove(fp)
                return result
            except json.JSONDecodeError:
                time.sleep(3)
                continue
        time.sleep(3)
    
    stats["tasks_timed_out"] += 1
    logger.error(f"[BRIDGE] Task {task_id} TIMEOUT after {timeout}s")
    if os.path.exists(task_file): os.remove(task_file)
    return {"status": "timeout", "error": f"timeout {timeout}s"}

def main():
    from domains.solution_pro.blackboard import BlackboardManager
    from domains.solution_pro.master_orchestrator import MasterOrchestrator
    
    bm = BlackboardManager("ai_loop_v3_full", base_dir=Path(DEEPFLOW) / "domains/solution_pro/blackboard_sessions")
    
    with open(bm.session_dir / "data/living_spec.json") as f:
        living_spec = json.load(f)
    
    config = {
        "topic": "OpenClaw_AI_Native_Loop_Engineering_Framework",
        "solution_type": "architecture",
        "mode": "standard",
        "module_timeouts": {"planning": 2400, "research": 2400, "review_qc": 1800},
    }
    
    user_input = "构建 OpenClaw AI Native Loop Engineering Framework"
    
    master = MasterOrchestrator(blackboard=bm, spawn_fn=bridge_spawn_fn, config=config)
    
    logger.info("=" * 50)
    logger.info("FULL E2E PIPELINE STARTING")
    logger.info("=" * 50)
    
    start = time.time()
    try:
        result = master.run(user_input=user_input, config=config, living_spec=living_spec)
        elapsed = time.time() - start
        logger.info(f"E2E COMPLETE: {elapsed:.0f}s, status={result.get('status')}")
        
        out = bm.session_dir / "stages/e2e_full_result.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"E2E FAILED: {e}")
        import traceback
        traceback.print_exc()
        with open(QUEUE_DIR + "/e2e_error.json", 'w') as f:
            json.dump({"error": str(e), "elapsed": time.time() - start, "stats": stats}, f)

if __name__ == "__main__":
    main()
