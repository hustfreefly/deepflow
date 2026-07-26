"""
PathManager - DeepFlow 统一路径管理器

契约论实施，专家评审修复：
- 统一安全验证（_safe_join）
- 并发安全（文件锁）
- 跨平台兼容（pathlib + Unicode 规范化）
- 统一异常类型（PathManagerError 基类）
"""

from .path_manager import PathManager
from .contracts import (
    PathManagerError,
    PathValidationError,
    PathNotFoundError,
    PathNotWritableError,
    PathTraversalError,
    SessionIdInput,
    FileNameInput,
    DomainConfig,
)

__all__ = [
    "PathManager",
    "PathManagerError",
    "PathValidationError",
    "PathNotFoundError",
    "PathNotWritableError",
    "PathTraversalError",
    "SessionIdInput",
    "FileNameInput",
    "DomainConfig",
]
