"""Gate: 检查 HarnessCheckV2 是否可导入"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

def main():
    try:
        from domains.solution_pro.schemas.schemas import HarnessCheckV2
        print(f"✅ PASS: HarnessCheckV2 可导入 — {HarnessCheckV2}")
        sys.exit(0)
    except ImportError as e:
        print(f"❌ FAIL: HarnessCheckV2 不可导入 — {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
