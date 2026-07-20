"""Spec Pro handoff package: 产出 spec_handoff_package.json 供 Solution Pro 消费。

ADR-009 P0（2026-07-12）：MD 直传架构
  - save_handoff_package 自动渲染 living_spec.md + track.json
  - handoff package 包含 living_spec_md_path（下游 LLM 直读 MD）
  - 只有 density_gate_result.passed == True 时 handoff_allowed = True

契约笼子：
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
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# 契约笼子：导入 Pydantic 强类型模型
from contracts.shared.handoff_contract import HandoffPackage

logger = logging.getLogger(__name__)


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
    """保存 handoff package 到 blackboard（契约笼子验证版 + MD 直传）。

    ADR-009 P0（2026-07-12）：
      写入 living_spec.md + spec_track.json，
      将 living_spec_md_path 记录到 package 中。
      下游 Solution Pro 从 package 中读 MD 路径，LLM 直接消费 MD。

    契约笼子：
      写入前用 HandoffPackage Pydantic 模型验证 package 合法性。
      验证失败 → raise ValueError（不静默降级）。

    Args:
        package: handoff package dict
        blackboard_dir: blackboard session 目录

    Returns:
        输出文件路径

    Raises:
        ValueError: 契约验证失败时抛出，包含具体违反项
    """
    # 契约笼子：Pydantic 验证，失败直接 raise
    validated = HandoffPackage(**package)

    spec_dir = blackboard_dir / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)

    # ── ADR-009 P0: 渲染 MD + track.json ──
    living_spec_md_path = None
    try:
        from domains.spec_pro.spec_living_md import render_living_spec_md
        from core.md_track_extractor import extract_track_json, validate_md_structure

        # 渲染 living_spec.md
        md_content = render_living_spec_md(validated.living_spec)
        md_path = spec_dir / "living_spec.md"
        md_path.write_text(md_content, encoding="utf-8")
        living_spec_md_path = str(md_path)

        # 提取并写入 spec_track.json
        passed, warnings = validate_md_structure(md_content, "spec_pro")
        if passed:
            track = extract_track_json(md_content, "spec_pro")
            track_path = spec_dir / "spec_track.json"
            track_path.write_text(
                json.dumps(track, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            logger.warning(f"MD validation warnings: {warnings}")
    except Exception as e:
        logger.warning(f"MD/track generation failed (non-blocking): {e}")

    # 构建输出 package（包含 MD 路径）
    output_data = validated.model_dump()
    if living_spec_md_path:
        output_data["living_spec_md_path"] = living_spec_md_path

    # 写入 JSON（Pydantic 验证后的数据）
    output_path = spec_dir / "spec_handoff_package.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    return output_path
