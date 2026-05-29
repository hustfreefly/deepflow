"""
Spec Pro — 上下文工程引擎
=========================

苏格拉底式对话需求引擎，基于 OpenClaw 多Agent协作架构。

Public API:
    SpecProCoordinator: 主Agent侧协调器（流程控制 + 状态管理）
    LivingSpec:         Living Spec 数据结构
    QualityLevel:       质量等级枚举 (S/A/B/C)
    Scenario:           场景枚举 (genesis/supplement/refine/pivot)

契约: cage/active/spec_pro_v2.0.yaml
"""

from domains.spec_pro.coordinator import SpecProCoordinator
from domains.spec_pro.models import LivingSpec, QualityLevel, Scenario

__all__ = ["SpecProCoordinator", "LivingSpec", "QualityLevel", "Scenario"]
