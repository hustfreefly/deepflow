#!/usr/bin/env python3
"""CLI: 构建 spec_handoff_package.json。

用法:
    python3 build_handoff_cli.py <blackboard_session_dir> [--extract-anchors]

参数:
    --extract-anchors    验证 living_spec.semantic_anchors 格式（Pydantic 强校验）。
                         格式不合法 → 输出 ANCHOR_VALIDATION_FAILED 并退出码 1。
                         CLI 环境无 LLM，故只做格式验证，不做语义提取。

前提: density gate 必须已通过（check_density_cli.py 输出 PASSED/WARN）。
      如果 density gate 未通过，此脚本输出 BLOCKED 并退出码 1。

输出:
    HANDOFF_CREATED: <path> — 成功
    ANCHORS_VALIDATED: <count> — semantic anchors 通过 Pydantic 验证
    BLOCKED — density gate 未通过
    ANCHOR_VALIDATION_FAILED — semantic anchors 格式不合法
"""
import sys
import json
from pathlib import Path

# 自动发现 .deepflow 根目录
_p = Path(__file__).resolve()
_r = next((d for d in _p.parents if (d / "core" / "blackboard").is_dir()), None)
if _r and str(_r) not in sys.path:
    sys.path.insert(0, str(_r))

from domains.spec_pro.contracts.living_spec import LivingSpec, SemanticAnchor
from domains.spec_pro.contracts.gate import gate_living_spec_density
from domains.spec_pro.handoff import build_handoff_package, save_handoff_package
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


def validate_semantic_anchors(anchors: list) -> list:
    """Validate semantic anchors format using SemanticAnchor Pydantic model.

    CLI 环境无 LLM，只做格式验证。语义提取由主 Agent 在确认阶段完成（prompt Step 4）。

    Args:
        anchors: raw anchor dicts from living_spec.json

    Returns:
        validated anchor dicts (model_dump format)

    Raises:
        ValueError: any anchor fails Pydantic validation
    """
    if not anchors:
        return []

    validated = []
    for i, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            raise ValueError(
                f"semantic_anchors[{i}] 必须是 dict，实际类型: {type(anchor).__name__}"
            )
        try:
            model = SemanticAnchor(**anchor)
            validated.append(model.model_dump())
        except Exception as e:
            raise ValueError(
                f"semantic_anchors[{i}] Pydantic 验证失败: {e}\n"
                f"原始数据: {json.dumps(anchor, ensure_ascii=False)[:200]}"
            ) from e

    return validated


def main():
    # Parse args: positional session_dir + optional flags
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    extract_anchors = "--extract-anchors" in flags

    if len(args) < 1:
        print(
            "用法: python3 build_handoff_cli.py <blackboard_session_dir> [--extract-anchors]",
            file=sys.stderr,
        )
        sys.exit(2)

    session_dir = Path(args[0])
    report_path = session_dir / "spec" / "quality_report.json"

    # 读取 living_spec（MD 优先，JSON fallback）
    try:
        living_spec_data = _read_living_spec(session_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: 读取 living_spec 失败: {e}", file=sys.stderr)
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

    # === Track B: 输入要素守恒 Gate fail-closed 校验 ===
    # 守恒 Gate 由确认阶段 Agent（LLM）执行，结果写入 spec/input_conservation_gate.json。
    # CLI 在此做 fail-closed 校验：文件缺失 / verdict 非 PASS / MUST 要素 MISSING → BLOCKED。
    conservation_path = session_dir / "spec" / "input_conservation_gate.json"
    if not conservation_path.exists():
        print(
            "BLOCKED — input_conservation_gate.json 不存在。\n"
            "  守恒 Gate 未执行。确认阶段必须执行要素提取 + 判定并写入该文件。\n"
            "  用户铁律：需求对齐是硬性要求，不存在降级或静默方案。",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with open(conservation_path, "r", encoding="utf-8") as f:
            conservation_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"BLOCKED — input_conservation_gate.json 读取失败: {e}", file=sys.stderr)
        sys.exit(1)

    verdict = str(conservation_data.get("verdict", "")).upper()
    if verdict != "PASS":
        must_missing = conservation_data.get("must_missing", [])
        print(
            f"BLOCKED — 守恒 Gate verdict={verdict}。\n"
            f"  MUST 要素缺失: {len(must_missing)} 个",
            file=sys.stderr,
        )
        for m in must_missing:
            elem_desc = m.get("element", m) if isinstance(m, dict) else str(m)
            print(f"    - {elem_desc}", file=sys.stderr)
        sys.exit(1)

    # 二次校验：即使 verdict=PASS，也检查 elements 中是否存在 MUST+MISSING
    elements = conservation_data.get("elements", [])
    must_missing_elements = [
        e for e in elements
        if isinstance(e, dict)
        and str(e.get("criticality", "")).upper() == "MUST"
        and str(e.get("status", "")).upper() == "MISSING"
    ]
    if must_missing_elements:
        print(
            f"BLOCKED — 守恒 Gate verdict=PASS 但存在 MUST 要素 MISSING（数据不一致）:\n"
            f"  {len(must_missing_elements)} 个 MUST 要素 MISSING",
            file=sys.stderr,
        )
        for e in must_missing_elements:
            print(f"    - {e.get('element', '?')}", file=sys.stderr)
        sys.exit(1)

    conservation_rate = conservation_data.get("conservation_rate", 0.0)
    print(f"CONSERVATION_GATE_PASS: verdict=PASS, rate={conservation_rate:.2f}")

    # Fix 1: Semantic Anchor 格式验证（程序化集成 extract_semantic_anchors 的验证路径）
    # 语义提取由主 Agent 在确认阶段 Step 4 完成（需要 LLM）；
    # CLI 环境无 LLM，此步只做 Pydantic 格式验证，确保下游消费到合法数据。
    raw_anchors = living_spec_data.get("semantic_anchors", [])
    if extract_anchors:
        try:
            validated_anchors = validate_semantic_anchors(raw_anchors)
            print(f"ANCHORS_VALIDATED: {len(validated_anchors)} 个 semantic anchors 通过 Pydantic 验证")
        except ValueError as e:
            print(f"ANCHOR_VALIDATION_FAILED: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 非 --extract-anchors 模式：仍做轻量格式检查（不阻断，只警告）
        validated_anchors = raw_anchors
        for i, anchor in enumerate(raw_anchors):
            if not isinstance(anchor, dict):
                print(f"WARNING: semantic_anchors[{i}] 不是 dict，跳过验证", file=sys.stderr)

    # 构建 handoff package
    package = build_handoff_package(
        living_spec=living_spec_data,
        quality_report=quality_report_data,
        density_gate_result=density_result,
        semantic_anchors=validated_anchors,
    )

    output_path = save_handoff_package(package, session_dir)
    print(f"HANDOFF_CREATED: {output_path}")
    print(f"  density_score: {density_result['score']}")
    print(f"  handoff_allowed: {package['handoff_allowed']}")
    print(f"  semantic_anchors: {len(validated_anchors)}")


if __name__ == "__main__":
    main()
