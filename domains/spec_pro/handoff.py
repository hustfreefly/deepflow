"""Spec Pro handoff package: 产出 spec_handoff_package.json 供 Solution Pro 消费。

只有 density_gate_result.passed == True 时 handoff_allowed = True。

契约笼子（2026-07-06）：
  save_handoff_package 增加 HandoffPackage Pydantic 验证。
  验证失败 → raise ValueError，绝不静默降级。
"""
import sys as _sys
_p = __import__('pathlib').Path(__file__).resolve()
# 契约笼子：强制将 .deepflow 根目录插到 sys.path[0]，覆盖脚本目录优先级
# （避免 domains/spec_pro/contracts/ 遮蔽 contracts/shared/）
_root = next((d for d in _p.parents if (d / 'core' / 'blackboard').is_dir()), None)
if _root:
    _root_str = str(_root)
    if _root_str in _sys.path:
        _sys.path.remove(_root_str)
    _sys.path.insert(0, _root_str)

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# 契约笼子：导入 Pydantic 强类型模型
from contracts.shared.handoff_contract import HandoffPackage


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
    """保存 handoff package 到 blackboard（契约笼子验证版）。

    契约笼子（2026-07-06）：
      写入前用 HandoffPackage Pydantic 模型验证 package 合法性。
      验证失败 → raise ValueError（不静默降级）。

    Args:
        package: handoff package dict（保持向后兼容，仍接受 dict 输入）
        blackboard_dir: blackboard session 目录

    Returns:
        输出文件路径

    Raises:
        ValueError: 契约验证失败时抛出，包含具体违反项
    """
    # 契约笼子：Pydantic 验证，失败直接 raise
    # 设计意图：在产出端（spec_pro）就拦截不合法 package，
    #          而不是让消费端（solution_pro）发现错误。
    validated = HandoffPackage(**package)

    output_path = blackboard_dir / "spec" / "spec_handoff_package.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 写入验证后的模型数据（确保序列化一致性）
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(validated.model_dump(), f, indent=2, ensure_ascii=False)
    return output_path
