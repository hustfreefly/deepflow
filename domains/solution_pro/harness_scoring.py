"""Unified Solution Pro harness scoring contract."""

"""
V1-LEGACY: This file is part of V1 pipeline (10-stage architecture).
V2 uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + ReviewQCOrchestrator.
Do not import this file for new V2 workflows.
"""

from __future__ import annotations

from typing import Dict, List


SCORING_DIMENSIONS = {
    "completeness": {
        "label": "完整性",
        "weight": 0.30,
        "description": "是否覆盖关键需求、边界、数据流、测试、运维和交付物。",
    },
    "necessity": {
        "label": "必要性",
        "weight": 0.20,
        "description": "方案是否贴合实际，避免过度设计、过度审计和无关复杂度。",
    },
    "alignment": {
        "label": "目标一致性",
        "weight": 0.30,
        "description": "所有设计决策是否服务于用户原始目标和 confirmed 需求。",
    },
    "global_impact": {
        "label": "全局影响",
        "weight": 0.20,
        "description": "是否考虑成本、风险、组织、集成、长期演进和跨阶段影响。",
    },
}


DECISION_THRESHOLDS = {
    "PASS": 0.85,
    "WARNING": 0.70,
    "CRITICAL_WARNING": 0.60,
}


VALID_DECISIONS = ["PASS", "WARNING", "CRITICAL_WARNING", "BLOCK_RECOMMENDATION"]


def dimension_names() -> List[str]:
    return list(SCORING_DIMENSIONS.keys())


def weights() -> Dict[str, float]:
    return {name: cfg["weight"] for name, cfg in SCORING_DIMENSIONS.items()}


def scoring_markdown() -> str:
    lines = [
        "## 统一 Harness 评分标准",
        "",
        "所有 Solution Pro 阶段使用同一套 4 维评分，分数范围为 0.0-1.0：",
        "",
    ]
    for name, cfg in SCORING_DIMENSIONS.items():
        lines.append(f"- `{name}` {cfg['label']} ({int(cfg['weight'] * 100)}%): {cfg['description']}")
    lines.extend([
        "",
        "总分公式：",
        "",
        "`overall_score = completeness*0.30 + necessity*0.20 + alignment*0.30 + global_impact*0.20`",
        "",
        "决策阈值：PASS >= 0.85；WARNING >= 0.70；CRITICAL_WARNING >= 0.60；否则 BLOCK_RECOMMENDATION。",
    ])
    return "\n".join(lines)
