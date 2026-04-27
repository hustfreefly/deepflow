"""
DeepFlow 路径配置管理模块
版本: 2026-04-27-v3（契约笼子合规）
"""

import os
import platform
import re
import stat
import tempfile
import warnings
from pathlib import Path
from typing import Optional

# ============================================================================
# 模块级常量
# ============================================================================
# P0-1: 避免 __file__ 在类方法中不可用
_MODULE_DIR = Path(__file__).resolve().parent.parent.parent

# ============================================================================
# 兼容性函数
# ============================================================================
# P0-D: 跨 Python 版本的 is_relative_to
def _is_relative_to(path: Path, base: Path) -> bool:
    """
    跨 Python 版本的 is_relative_to 兼容性函数
    
    Python 3.9+: path.is_relative_to(base)
    Python <3.9: path.relative_to(base) 不抛 ValueError → True
    """
    try:
        return path.is_relative_to(base)
    except AttributeError:
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False


# ============================================================================
# 路径安全验证
# ============================================================================
def validate_path_safety(path: Path, allowed_base: Path):
    """
    通用路径安全验证函数
    
    Args:
        path: 待验证的路径
        allowed_base: 允许的基目录
    
    Raises:
        ValueError: 路径不安全
    """
    resolved = path.resolve()
    allowed_resolved = allowed_base.resolve()
    
    # 检查路径遍历
    if not _is_relative_to(resolved, allowed_resolved):
        raise ValueError(f"Path traversal: {path} is outside {allowed_base}")
    
    # 检查符号链接
    if path.is_symlink():
        raise ValueError(f"Symlink detected: {path}")
    
    # 检查权限（Unix）
    if os.name != 'nt':
        stat_info = resolved.stat()
        if stat_info.st_mode & stat.S_IRWXO:  # 其他用户有权限
            warnings.warn(f"Path has world-accessible permissions: {resolved}")


def validate_path_length(path: Path, max_length: int = None):
    """P2-4: 检查路径长度是否超过系统限制"""
    if max_length is None:
        max_length = 260 if platform.system() == 'Windows' else 4096
    
    if len(str(path)) > max_length:
        raise ValueError(
            f"Path exceeds maximum length ({len(str(path))} > {max_length}): {path}"
        )


# ============================================================================
# PathConfig 主类
# ============================================================================
class PathConfig:
    """
    路径配置解析器（安全增强版）
    
    优先级（从高到低）：
    1. 环境变量 (DEEPFLOW_BASE)
    2. 默认值（基于安装位置推导，非 cwd）
    
    安全特性：
    - 路径遍历攻击防护（P0-5）
    - 符号链接攻击防护（P0-6）
    - 多用户权限隔离（P0-7）
    - session_id 长度限制（P1-4）
    """
    
    # P1-4: 最大 session_id 长度（防 DoS）
    MAX_SESSION_ID_LENGTH = 255
    
    @classmethod
    def resolve(cls, base_dir: Optional[str] = None) -> 'PathConfig':
        """解析路径配置"""
        
        # 优先级 1: 显式传入的参数（用于测试）
        if base_dir:
            return cls(base_dir)
        
        # 优先级 2: 环境变量
        env_base = os.environ.get('DEEPFLOW_BASE')
        if env_base:
            # P1-5 修复：增强环境变量验证
            cls._validate_env_path(env_base)
            return cls(env_base)
        
        # 优先级 3: 默认值（基于安装位置，非 cwd）
        # P0-B 修复：使用 __file__ 推导而非 cwd
        default_base = _MODULE_DIR
        return cls(str(default_base))
    
    @staticmethod
    def _validate_env_path(path: str):
        """P1-5: 增强环境变量路径安全性验证"""
        path_obj = Path(path)
        
        # 检查是否为绝对路径
        if not path_obj.is_absolute():
            raise ValueError(
                f"DEEPFLOW_BASE must be absolute path: {path}\n"
                f"Example: export DEEPFLOW_BASE=/opt/deepflow"
            )
        
        # 检查是否包含 ..（防御环境变量注入）
        if '..' in path.split(os.sep):
            raise ValueError(f"DEEPFLOW_BASE contains '..': {path}")
        
        # P1-5 新增：如果路径已存在，验证是目录且可写
        if path_obj.exists():
            if not path_obj.is_dir():
                raise ValueError(f"DEEPFLOW_BASE exists but is not a directory: {path}")
            if not os.access(path, os.W_OK):
                raise ValueError(f"DEEPFLOW_BASE is not writable: {path}")
    
    def __init__(self, base_dir: str):
        # P0-3 修复：验证基目录安全性
        self.base_dir = Path(base_dir).expanduser().resolve()
        self._validate_base_dir()
        
        self.blackboard_dir = self.base_dir / 'blackboard'
        self.config_dir = self.base_dir / 'config'
        self.prompts_dir = self.base_dir / 'prompts'
        self.logs_dir = self.base_dir / 'logs'
        self.cache_dir = self._get_cache_dir()
    
    def _validate_base_dir(self):
        """P0-3: 验证基目录安全性"""
        # 检查是否为绝对路径
        if not self.base_dir.is_absolute():
            raise ValueError(f"DEEPFLOW_BASE must be absolute path: {self.base_dir}")
        
        # 检查目录所有者（Unix 系统）
        if os.name != 'nt':
            try:
                dir_stat = self.base_dir.stat()
                if dir_stat.st_uid != os.getuid():
                    warnings.warn(
                        f"DEEPFLOW_BASE owner mismatch: "
                        f"expected uid={os.getuid()}, got uid={dir_stat.st_uid}"
                    )
            except FileNotFoundError:
                pass  # 目录尚未创建，允许
    
    def _get_cache_dir(self) -> Path:
        """获取缓存目录（跨平台，P0-2 修复）"""
        system = platform.system()  # P0-2 修复：使用 platform.system() 替代 os.uname()
        
        if system == 'Windows':
            cache_base = os.environ.get('LOCALAPPDATA', 
                                       Path.home() / 'AppData' / 'Local')
            return Path(cache_base) / 'deepflow' / 'cache'
        elif system == 'Darwin':  # macOS
            return Path.home() / 'Library' / 'Caches' / 'deepflow'
        else:  # Linux
            cache_base = os.environ.get('XDG_CACHE_HOME', 
                                       Path.home() / '.cache')
            return Path(cache_base) / 'deepflow'
    
    def get_blackboard_path(self, session_id: str) -> Path:
        """
        获取 Blackboard 路径（安全增强版）
        
        防护：
        - P0-1: 路径遍历攻击
        - P0-2: 符号链接攻击
        - P1-4: session_id 长度限制
        """
        # P1-4 修复：限制 session_id 长度
        if len(session_id) > self.MAX_SESSION_ID_LENGTH:
            raise ValueError(f"session_id too long: {len(session_id)} > {self.MAX_SESSION_ID_LENGTH}")
        
        # P0-1 修复：清理 session_id
        safe_session_id = self._sanitize_session_id(session_id)
        
        raw_path = self.blackboard_dir / safe_session_id
        resolved_path = raw_path.resolve()
        
        # P0-1 修复：验证解析后的路径仍在基目录下
        if not _is_relative_to(resolved_path, self.blackboard_dir.resolve()):
            raise ValueError(
                f"Path traversal detected: {session_id} resolves to {resolved_path}, "
                f"which is outside {self.blackboard_dir}"
            )
        
        # P0-2 修复：检查符号链接
        if raw_path.exists() and raw_path.is_symlink():
            raise ValueError(
                f"Symlink detected: {raw_path}. Symlinks are not allowed in blackboard."
            )
        
        # P2-4: 检查路径长度
        validate_path_length(resolved_path)
        
        return resolved_path
    
    @staticmethod
    def _sanitize_session_id(session_id: str) -> str:
        """清理 session_id，只允许安全字符"""
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)
        if not sanitized:
            raise ValueError("session_id cannot be empty after sanitization")
        return sanitized
    
    def ensure_directories(self):
        """确保所有目录存在并设置严格权限（P0-7 修复）"""
        for dir_path in [self.blackboard_dir, self.config_dir, self.logs_dir, self.cache_dir]:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                # P0-7 修复：设置权限为 700（仅所有者可读写执行）
                # P1-6: 权限设置失败降级为警告
                if os.name != 'nt':
                    try:
                        os.chmod(dir_path, 0o700)
                    except OSError:
                        warnings.warn(f"Failed to set permissions on {dir_path}, using default")
            except PermissionError as e:
                raise RuntimeError(f"无法创建目录 {dir_path}: {e}")
            except OSError as e:
                raise RuntimeError(f"文件系统错误 {dir_path}: {e}")
    
    def create_secure_temp_file(self, suffix: str = '.tmp') -> Path:
        """P1-2: 创建安全的临时文件"""
        fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=str(self.cache_dir))
        os.close(fd)
        temp_path = Path(temp_path)
        if os.name != 'nt':
            os.chmod(temp_path, 0o600)  # 仅所有者可读写
        return temp_path
    
    def cleanup_cache(self, max_age_hours: int = 24):
        """P1-2: 清理过期缓存文件"""
        import time
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        
        cache_resolved = self.cache_dir.resolve()
        
        for file_path in self.cache_dir.rglob('*'):
            if file_path.is_file():
                # 额外验证：文件必须在缓存目录下（防御符号链接替换）
                try:
                    file_resolved = file_path.resolve()
                    if not _is_relative_to(file_resolved, cache_resolved):
                        warnings.warn(f"Skipping file outside cache: {file_path}")
                        continue
                except (OSError, RuntimeError):
                    continue
                
                try:
                    if now - file_path.stat().st_mtime > max_age_seconds:
                        file_path.unlink()
                except (OSError, FileNotFoundError):
                    pass
    
    def __repr__(self) -> str:
        return f"PathConfig(base_dir={self.base_dir}, blackboard={self.blackboard_dir})"
