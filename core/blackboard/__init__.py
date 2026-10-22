"""
core.blackboard — DeepFlow 统一黑板系统

提供:
- BlackboardManager: 统一文件读写 + Registry 集成
- DomainRegistry: 域路径注册表基类
- generate_session_id: 统一 session_id 生成器
"""

from core.blackboard.blackboard_manager import BlackboardManager
from core.blackboard.registry_base import DomainRegistry
from core.blackboard.session_id import generate_session_id, generate_run_id

__all__ = [
    "BlackboardManager",
    "DomainRegistry",
    "generate_session_id",
    "generate_run_id",
]
