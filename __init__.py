"""
DeepFlow — V1.0 多 Agent 管线引擎

配置驱动、质量门控、韧性管理。
版本: 1.0.0
日期: 2026-04-18
"""

__version__ = "1.0.0"
__author__ = "小满 🦞"

# Phase 1 模块导出
try:
    from .observability import Observability
    from .blackboard_manager import BlackboardManager
    from .config_loader import (
        ConfigLoader, DomainConfig, PipelineTemplate,
        AgentConfig, QualityDimension, DomainQualityConfig,
        DeliveryConfig, ResilienceConfig, PipelineStage,
    )
except ImportError:
    from observability import Observability
    from blackboard_manager import BlackboardManager
    from config_loader import (
        ConfigLoader, DomainConfig, PipelineTemplate,
        AgentConfig, QualityDimension, DomainQualityConfig,
        DeliveryConfig, ResilienceConfig, PipelineStage,
    )

__all__ = [
    # 可观测性
    "Observability",
    # 数据总线
    "BlackboardManager",
    # 配置加载
    "ConfigLoader",
    "DomainConfig",
    "PipelineTemplate",
    "AgentConfig",
    "QualityDimension",
    "DomainQualityConfig",
    "DeliveryConfig",
    "ResilienceConfig",
    "PipelineStage",
]
