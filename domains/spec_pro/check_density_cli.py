#!/usr/bin/env python3
"""CLI: 检查 Living Spec 密度 Gate。

用法:
    python3 check_density_cli.py <blackboard_session_dir>

输出:
    PASSED — 密度达标
    FAILED — 密度不达标，后跟 issues 列表（每行一条）
    WARN — 通过但有 warnings

退出码:
    0 = PASSED/WARN, 1 = FAILED, 2 = 错误
"""
import sys
import json
from pathlib import Path

# 自动发现 .deepflow 根目录
_p = Path(__file__).resolve()
_r = next((d for d in _p.parents if (d / "core" / "blackboard").is_dir()), None)
if _r and str(_r) not in sys.path:
    sys.path.insert(0, str(_r))

from domains.spec_pro.contracts.living_spec import LivingSpec
from domains.spec_pro.contracts.gate import gate_living_spec_density
from domains.spec_pro.spec_living_md import parse_living_spec_md


def _read_living_spec(session_dir: Path) -> dict:
    """读取 living_spec：MD 优先，JSON fallback。"""
    # 1. Try MD first
    md_path = session_dir / "spec" / "living_spec.md"
    if md_path.exists():
        try:
            md_content = md_path.read_text(encoding="utf-8")
            return parse_living_spec_md(md_content)
        except Exception as e:
            print(f"WARNING: MD parse failed, falling back to JSON: {e}", file=sys.stderr)

    # 2. Fallback to JSON
    json_path = session_dir / "spec" / "living_spec.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Neither {md_path} nor {json_path} exists")

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 check_density_cli.py <blackboard_session_dir>", file=sys.stderr)
        sys.exit(2)

    session_dir = Path(sys.argv[1])

    try:
        data = _read_living_spec(session_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: 读取 living_spec 失败: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        spec = LivingSpec(**data)
    except Exception as e:
        print(f"ERROR: LivingSpec 解析失败: {e}", file=sys.stderr)
        sys.exit(2)

    result = gate_living_spec_density(spec)

    passed = result["passed"]
    issues = result["issues"]
    score = result["score"]
    warnings = result["warnings"]

    # 输出结果（Agent 可解析的格式）
    if passed and warnings:
        print("WARN")
        for w in warnings:
            print(f"  WARNING: {w}")
        print(f"  score: {score}")
    elif passed:
        print("PASSED")
        print(f"  score: {score}")
    else:
        print("FAILED")
        for issue in issues:
            print(f"  ISSUE: {issue}")
        print(f"  score: {score}")

    # 输出完整 JSON 到 stderr（供程序化消费）
    print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
