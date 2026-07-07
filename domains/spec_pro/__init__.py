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
import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录

from domains.spec_pro.coordinator import SpecProCoordinator
from domains.spec_pro.models import LivingSpec, QualityLevel, Scenario
from domains.spec_pro.domain_context import build_domain_context

__all__ = [
    "SpecProCoordinator",
    "LivingSpec",
    "QualityLevel",
    "Scenario",
    "build_domain_context",
]
