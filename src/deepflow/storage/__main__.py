"""
Main entry point for running the benchmark module.

支持命令:
    python -m deepflow.storage.benchmark --inserts=10000
"""

from deepflow.storage.benchmark import main

if __name__ == "__main__":
    main()
