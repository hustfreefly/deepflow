#!/usr/bin/env python3
"""CLI: 构建 spec_handoff_package.json。

用法:
    python3 build_handoff_cli.py <blackboard_session_dir>

前提: density gate 必须已通过（check_density_cli.py 输出 PASSED/WARN）。
      如果 density gate 未通过，此脚本输出 BLOCKED 并退出码 1。

输出:
    HANDOFF_CREATED: <path> — 成功
    BLOCKED — density gate 未通过
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
from domains.spec_pro.handoff import build_handoff_package, save_handoff_package


def main():
    if len(sys.argv) < 2:
        print("用法: python3 build_handoff_cli.py <blackboard_session_dir>", file=sys.stderr)
        sys.exit(2)

    session_dir = Path(sys.argv[1])
    spec_path = session_dir / "spec" / "living_spec.json"
    report_path = session_dir / "spec" / "quality_report.json"

    if not spec_path.exists():
        print(f"ERROR: {spec_path} 不存在", file=sys.stderr)
        sys.exit(2)

    # 读取数据
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            living_spec_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: 读取 living_spec.json 失败: {e}", file=sys.stderr)
        sys.exit(2)

    quality_report_data = {}
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                quality_report_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass  # 非关键，允许空

    # 解析 + density gate
    try:
        spec = LivingSpec(**living_spec_data)
    except Exception as e:
        print(f"ERROR: LivingSpec 解析失败: {e}", file=sys.stderr)
        sys.exit(2)

    density_result = gate_living_spec_density(spec)

    if not density_result["passed"]:
        print("BLOCKED — density gate 未通过:")
        for issue in density_result["issues"]:
            print(f"  ISSUE: {issue}")
        sys.exit(1)

    # 构建 handoff package
    package = build_handoff_package(
        living_spec=living_spec_data,
        quality_report=quality_report_data,
        density_gate_result=density_result,
        semantic_anchors=living_spec_data.get("semantic_anchors", []),
    )

    output_path = save_handoff_package(package, session_dir)
    print(f"HANDOFF_CREATED: {output_path}")
    print(f"  density_score: {density_result['score']}")
    print(f"  handoff_allowed: {package['handoff_allowed']}")


if __name__ == "__main__":
    main()
