#!/usr/bin/env python3
"""Solution Pro Full E2E Runner"""
import sys, os, json, time, logging
from pathlib import Path

DEEPFLOW = os.path.expanduser("~/.openclaw/workspace/.deepflow")
os.chdir(DEEPFLOW)
sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("full_e2e")

def main():
    from domains.solution_pro import run_solution_pro

    user_input = "构建 OpenClaw AI Native Loop Engineering Framework"

    logger.info("=" * 50)
    logger.info("FULL E2E PIPELINE STARTING")
    logger.info("=" * 50)

    start = time.time()
    try:
        result = run_solution_pro(user_input=user_input)
        elapsed = time.time() - start
        logger.info(f"E2E COMPLETE: {elapsed:.0f}s, status={result.get('status')}")

        out = Path(DEEPFLOW) / "domains/solution_pro/blackboard_sessions/e2e_full_result.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"E2E FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
