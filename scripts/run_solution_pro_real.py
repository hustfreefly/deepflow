#!/usr/bin/env python3
"""
Real Solution Pro pipeline runner.

Calls run_solution_pro() from the solution_pro package.
"""

import sys
from pathlib import Path

# Setup path
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from domains.solution_pro import run_solution_pro


def main():
    print(f"\n🏗️  Starting Solution Pro Pipeline\n")

    user_input = "基于OpenClaw构建完整的AI Native Loop Engineering框架"

    try:
        result = run_solution_pro(user_input=user_input)

        print(f"\n{'='*60}")
        print(f"🎉 Pipeline Complete!")
        print(f"{'='*60}")
        print(f"Status: {result.get('status', 'UNKNOWN') if isinstance(result, dict) else result}")

        return 0

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
