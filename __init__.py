"""
DeepFlow — V1.0 多 Agent 管线引擎

配置驱动、质量门控、韧性管理。
版本: 1.0.0
日期: 2026-04-18
"""

__version__ = "1.0.0"
__author__ = "小满 🦞"

# 模块导出（重构后路径：core/）
from core.quality.observability import Observability
from core.blackboard.blackboard_manager import BlackboardManager
from core.config_loader import ConfigLoader
from core.orchestrator.orchestrator_base import DomainConfig

__all__ = [
    # 可观测性
    "Observability",
    # 数据总线
    "BlackboardManager",
    # 配置加载
    "ConfigLoader",
    # 编排器基础
    "DomainConfig",
]
