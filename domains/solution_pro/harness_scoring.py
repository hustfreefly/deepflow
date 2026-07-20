from __future__ import annotations

from typing import Dict, List

"""Unified Solution Pro harness scoring contract."""

"""
This file is part of pipeline (10-stage architecture).
V3.1 纯 Agent Orchestrator 架构（Python orchestrator 层已删除）。
Do not import this file for new workflows.
"""


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


# [TD3 2026-07-13] Deleted dead function: dimension_names (zero callers)

def weights() -> Dict[str, float]:
    return {name: cfg["weight"] for name, cfg in SCORING_DIMENSIONS.items()}


# [TD3 2026-07-13] Deleted dead function: scoring_markdown (zero callers)
