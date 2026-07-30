"""
PathManager 契约定义

契约论方法：
1. 不变量（Invariants）：PathManager 实例始终满足的条件
2. 前置条件（Preconditions）：方法调用前必须满足的条件
3. 后置条件（Postconditions）：方法调用后保证满足的条件

不变量：
- session_id 已经过 sanitize，不含危险字符
- root 路径存在且可访问
- 所有返回的路径都在 root 范围内（防止路径遍历）

前置条件：
- session_id 非空
- 文件名不含路径分隔符

后置条件：
- 返回的路径经过验证
- 目录创建后保证存在
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from pathlib import Path
import re
import unicodedata


# ========== 输入契约 ==========

class SessionIdInput(BaseModel):
    """session_id 输入契约"""
    value: str = Field(..., min_length=1, max_length=200)
    
    @field_validator('value')
    @classmethod
    def sanitize_session_id(cls, v: str) -> str:
        """
        前置条件：session_id 必须可被 sanitize
        后置条件：返回的字符串只包含安全字符
        """
        # Unicode 规范化（NFC 形式）
        v = unicodedata.normalize('NFC', v)
        
        # 替换危险字符
        sanitized = v.replace('/', '_').replace('\\', '_')
        sanitized = sanitized.replace('..', '_').replace(':', '_')
        sanitized = sanitized.replace(' ', '_').replace('.', '_')
        
        # 检查是否以 .. 开头/结尾（防止路径遍历）
        if sanitized.startswith('..') or sanitized.endswith('..'):
            raise ValueError("session_id cannot start/end with '..'")
        
        # 白名单验证：只允许字母、数字、中文、下划线、连字符
        if not re.match(r'^[\w\u4e00-\u9fff_-]+$', sanitized):
            raise ValueError(f"session_id contains invalid characters: {sanitized}")
        
        return sanitized


class FileNameInput(BaseModel):
    """文件名输入契约"""
    value: str = Field(..., min_length=1, max_length=255)
    
    @field_validator('value')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """
        前置条件：文件名不含路径分隔符
        后置条件：返回的文件名是安全的
        """
        # 不允许路径分隔符
        if '/' in v or '\\' in v:
            raise ValueError(f"filename cannot contain path separators: {v}")
        
        # 不允许 ..
        if '..' in v:
            raise ValueError(f"filename cannot contain '..': {v}")
        
        return v


# ========== 输出契约 ==========

class ValidatedPath(BaseModel):
    """验证后的路径"""
    path: Path
    exists: bool = False
    is_writable: bool = False
    
    class Config:
        arbitrary_types_allowed = True


# ========== 异常契约 ==========

class PathManagerError(Exception):
    """PathManager 基础异常类"""
    pass


class PathValidationError(PathManagerError):
    """路径验证失败"""
    pass


class PathNotFoundError(PathManagerError):
    """路径不存在"""
    pass


class PathNotWritableError(PathManagerError):
    """路径不可写"""
    pass


class PathTraversalError(PathManagerError):
    """路径遍历攻击检测"""
    pass


# ========== 域配置契约 ==========

class DomainConfig(BaseModel):
    """域配置契约"""
    domain: Literal["solution", "ship", "deliver", "research"]
    stages_subdir: str = "stages"
    data_subdir: str = "data"
    runs_subdir: str = ".runs"
    
    # 域特定的子目录
    extra_subdirs: list[str] = Field(default_factory=list)
