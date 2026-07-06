"""Spec Pro handoff package: 产出 spec_handoff_package.json 供 Solution Pro 消费。

只有 density_gate_result.passed == True 时 handoff_allowed = True。
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def build_handoff_package(
    living_spec: dict,
    quality_report: dict,
    density_gate_result: dict,
    semantic_anchors: Optional[list] = None,
) -> dict:
    """构建 spec_handoff_package.json。

    Args:
        living_spec: 完整 living_spec 数据
        quality_report: 质量报告数据
        density_gate_result: {"passed": bool, "issues": list[str]}
        semantic_anchors: 语义锚点列表（可选，默认从 living_spec 提取）

    Returns:
        handoff package dict
    """
    handoff_allowed = density_gate_result.get("passed", False)

    package: Dict[str, Any] = {
        "schema_version": "2.0.0",
        "handoff_allowed": handoff_allowed,
        "living_spec": living_spec,
        "quality_report": quality_report,
        "density_gate_result": density_gate_result,
        "semantic_anchors": semantic_anchors or living_spec.get("semantic_anchors", []),
    }

    if not handoff_allowed:
        package["block_reason"] = density_gate_result.get(
            "issues", ["density gate failed"]
        )

    return package


def save_handoff_package(package: dict, blackboard_dir: Path) -> Path:
    """保存 handoff package 到 blackboard。

    Args:
        package: handoff package dict
        blackboard_dir: blackboard session 目录

    Returns:
        输出文件路径
    """
    output_path = blackboard_dir / "spec" / "spec_handoff_package.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(package, f, indent=2, ensure_ascii=False)
    return output_path
