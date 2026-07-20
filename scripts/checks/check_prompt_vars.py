# DEPRECATED: orchestrator code deleted (ResearchOrchestrator, PlanningOrchestrator no longer exist)
# This check is no longer functional. The prompt template variable validation
# should be reimplemented against the current solution_pro entry point if needed.
"""Gate: 检查 prompt 中的模板变量是否都被 runner 替换"""
import sys
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent


def main():
    print("⚠️  SKIP: check_prompt_vars is deprecated (orchestrator modules deleted)")
    print("   Removed references: ResearchOrchestrator, PlanningOrchestrator")
    sys.exit(0)


if __name__ == "__main__":
    main()
