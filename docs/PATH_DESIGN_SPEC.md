# DeepFlow 文件路径规范设计方案
# 版本: 2026-04-27-v3（第二轮修订版）
# 状态: 根据第二轮专家评审修订
# 修订内容: 
#   - 修复第一轮7个P0
#   - 修复第二轮4个P0（P0-A~P0-D）
#   - 修复关键P1（P1-1, P1-4, P1-5）
#   - 添加 _is_relative_to 兼容性函数
#   - 增强环境变量验证
#   - 添加 session_id 长度限制

---

## 1. 问题分析

### 1.1 当前问题

| 场景 | 当前硬编码路径 | 问题 |
|:---|:---|:---|
| 开发环境 | `/Users/allen/.openclaw/workspace/.deepflow/` | 用户名硬编码 |
| Blackboard | `/Users/allen/.openclaw/workspace/.deepflow/blackboard/` | 深度嵌套，不可配置 |
| Prompts | `/Users/allen/.openclaw/workspace/.deepflow/prompts/` | 与安装位置耦合 |
| 数据目录 | `/Users/allen/.openclaw/workspace/.deepflow/data/` | 无法自定义 |

### 1.2 影响范围

**对开源用户：**
- Linux 用户：路径不存在（`/Users/` 是 macOS 特有）
- Windows 用户：路径格式错误（`\` vs `/`）
- Docker 用户：容器内外路径映射复杂
- 多用户服务器：路径冲突

**对 OpenClaw 项目：**
- 子 Agent 工作目录与主 Agent 不同
- `sessions_spawn` 不支持 `env` 参数，无法通过环境变量传递路径
- 文件写入位置不可预测

---

## 2. 设计原则

### 2.1 核心原则

```
1. 约定优于配置（Convention over Configuration）
2. 环境变量可覆盖（Environment Variable Override）
3. 运行时自动推导（Runtime Auto-detection）
4. 跨平台兼容（Cross-platform Compatible）
5. 安全第一（Security First）
```

### 2.2 路径分类

| 类型 | 说明 | 示例 |
|:---|:---|:---|
| **项目根目录** | DeepFlow 安装位置 | `~/.deepflow/` 或 `./` |
| **Blackboard** | 运行时数据 | `${DEEPFLOW_BASE}/blackboard/` |
| **配置目录** | 用户配置 | `${DEEPFLOW_BASE}/config/` |
| **日志目录** | 运行日志 | `${DEEPFLOW_BASE}/logs/` |
| **缓存目录** | 临时文件 | `~/.cache/deepflow/` 或系统临时目录 |

---

## 3. 具体方案

### 3.1 配置层级（简化版）

**修订说明：** 根据专家评审（P0-3, P2-1），简化为2层，移除YAML配置文件支持。

```python
# core/config/path_config.py

import os
import platform
import re
import stat
import tempfile
import warnings
from pathlib import Path
from typing import Optional

# 模块级常量：避免 __file__ 在类方法中不可用的问题（P0-1 修复）
_MODULE_DIR = Path(__file__).resolve().parent.parent.parent

def _is_relative_to(path: Path, base: Path) -> bool:
    """
    跨 Python 版本的 is_relative_to 兼容性函数（P0-D 修复）
    
    Python 3.9+: path.is_relative_to(base)
    Python <3.9: path.relative_to(base) 不抛 ValueError → True
    """
    try:
        # Python 3.9+
        return path.is_relative_to(base)
    except AttributeError:
        # Python <3.9 兼容性
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False

class PathConfig:
    """
    路径配置解析器（安全增强版）
    
    优先级（从高到低）：
    1. 环境变量 (DEEPFLOW_BASE)
    2. 默认值（基于安装位置推导）
    
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
            # P1-3 修复：验证环境变量安全性
            cls._validate_env_path(env_base)
            return cls(env_base)
        
        # 优先级 3: 默认值（基于安装位置）
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
            return Path(cache_base) / 'deepflow' / 'cache'  # P1-3 修复：小写
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
                if os.name != 'nt':
                    os.chmod(dir_path, 0o700)
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
        return f"PathConfig(base_dir={self.base_dir})"


# 通用路径安全验证函数
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
```

### 3.2 环境变量规范

**修订说明：** 根据专家评审（P0-4），`sessions_spawn` 不支持 `env` 参数，环境变量仅在主 Agent 中设置和读取。

| 变量名 | 说明 | 示例 |
|:---|:---|:---|
| `DEEPFLOW_BASE` | 项目根目录（主 Agent 读取） | `/opt/deepflow` 或 `~/.deepflow` |
| `DEEPFLOW_BLACKBOARD` | Blackboard 目录（可选，主 Agent 读取） | `/var/lib/deepflow/blackboard` |
| `DEEPFLOW_LOG_LEVEL` | 日志级别 | `INFO` |

### 3.3 跨平台路径处理

```python
# utils/path_utils.py

from pathlib import Path
import os
import platform
import stat
import warnings

def get_system_paths() -> dict:
    """
    获取当前系统的标准路径
    
    Returns:
        {
            'home': Path,           # 用户主目录
            'config': Path,         # 配置目录
            'cache': Path,          # 缓存目录
            'data': Path,           # 数据目录
            'temp': Path,           # 临时目录
        }
    """
    system = platform.system()
    home = Path.home()
    
    if system == 'Windows':
        return {
            'home': home,
            'config': Path(os.environ.get('APPDATA', home / 'AppData' / 'Roaming')),
            'cache': Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local')),
            'data': Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local')),
            'temp': Path(os.environ.get('TEMP', home / 'AppData' / 'Local' / 'Temp')),
        }
    elif system == 'Darwin':  # macOS
        return {
            'home': home,
            'config': home / 'Library' / 'Application Support',
            'cache': home / 'Library' / 'Caches',
            'data': home / 'Library' / 'Application Support',
            'temp': Path(os.environ.get('TMPDIR', '/tmp')),
        }
    else:  # Linux
        return {
            'home': home,
            'config': Path(os.environ.get('XDG_CONFIG_HOME', home / '.config')),
            'cache': Path(os.environ.get('XDG_CACHE_HOME', home / '.cache')),
            'data': Path(os.environ.get('XDG_DATA_HOME', home / '.local' / 'share')),
            'temp': Path(os.environ.get('TMPDIR', '/tmp')),
        }

def to_posix_path(path: Path) -> str:
    """
    转换为 POSIX 风格路径（用于跨平台兼容）
    
    注意：此函数仅转换分隔符，不处理 Windows 绝对路径前缀（如 C:/）
    """
    return path.as_posix()

def validate_path_length(path: Path, max_length: int = None):
    """P2-4: 检查路径长度是否超过系统限制"""
    if max_length is None:
        max_length = 260 if platform.system() == 'Windows' else 4096
    
    if len(str(path)) > max_length:
        raise ValueError(
            f"Path exceeds maximum length ({len(str(path))} > {max_length}): {path}"
        )
```

---

## 4. 与 OpenClaw 的集成方案

### 4.1 问题场景

```
OpenClaw 工作目录: /Users/allen/.openclaw/workspace/
DeepFlow 安装位置: /Users/allen/.openclaw/workspace/.deepflow/
子 Agent 工作目录: /Users/allen/.openclaw/workspace/（与 OpenClaw 相同）

当前：子 Agent write("blackboard/...") → 写入 /Users/allen/.openclaw/workspace/blackboard/
期望：子 Agent 写入 /Users/allen/.openclaw/workspace/.deepflow/blackboard/
```

### 4.2 关键约束

**根据 OpenClaw 官方文档，sessions_spawn 不支持 `env` 参数。**

可用参数：
- `runtime`, `mode`, `task`, `agentId`, `model`, `timeoutSeconds`, `cleanup`
- `label`, `thread`, `sandbox`, `streamTo`, `runTimeoutSeconds`, `thinking`
- `lightContext`, `resumeSessionId`, `attachments`, `attachAs`

**没有 `env` 参数。子 Agent 无法继承父进程环境变量。**

### 4.3 唯一可行方案：绝对路径嵌入 Task（修订）

```python
# 主 Agent 生成 task 时嵌入绝对路径
from core.config.path_config import PathConfig

config = PathConfig.resolve()
base_dir = str(config.base_dir)  # e.g., "/Users/allen/.openclaw/workspace/.deepflow"

# 生成子 Agent 的 task，包含绝对路径
def build_task_with_absolute_path(session_id: str, task_type: str) -> str:
    output_path = f"{base_dir}/blackboard/{session_id}/stages/{task_type}.json"
    
    task = f"""
    请完成以下任务并将结果写入指定文件：
    
    任务类型: {task_type}
    输出路径: {output_path}
    
    重要：
    1. 使用 write 工具将结果写入上述绝对路径
    2. 不要修改路径
    3. 确保目录存在（mkdir -p）
    """
    return task

# 调用子 Agent
sessions_spawn(
    runtime="subagent",
    mode="run",
    task=build_task_with_absolute_path("session_123", "planning"),
    timeout_seconds=600,
    cleanup="delete",
)
```

### 4.4 路径传递模式

```
┌─────────────────────────────────────────┐
│         主 Agent（Orchestrator）          │
│  1. 读取 DEEPFLOW_BASE 环境变量           │
│  2. 解析为 PathConfig                    │
│  3. 生成绝对路径                         │
├─────────────────────────────────────────┤
│         sessions_spawn                   │
│  task 字符串中包含绝对路径                │
├─────────────────────────────────────────┤
│         子 Agent                         │
│  1. 接收 task 字符串                      │
│  2. 提取绝对路径                          │
│  3. 使用 write 工具写入                   │
└─────────────────────────────────────────┘
```

### 4.5 降级策略

如果主 Agent 未设置 `DEEPFLOW_BASE`：

```python
# 主 Agent 降级处理
def resolve_base_dir() -> str:
    """解析 DeepFlow 基础目录"""
    # 1. 环境变量
    env_base = os.environ.get('DEEPFLOW_BASE')
    if env_base:
        return env_base
    
    # 2. 基于当前工作目录推导
    cwd = Path.cwd()
    # 检查当前目录或其父目录是否包含 deepflow 特征文件
    for parent in [cwd] + list(cwd.parents):
        if (parent / 'domains').exists() and (parent / 'prompts').exists():
            return str(parent)
    
    # 3. 默认目录
    default = Path.home() / '.deepflow'
    return str(default)
```

---

## 5. 迁移路径（从当前硬编码迁移）

### 5.1 迁移策略

**修订说明：** 根据专家评审，移除 YAML 配置阶段，简化为直接替换。

**阶段 1：创建配置系统（不修改现有代码）**
- 新建 `core/config/path_config.py`（包含所有安全修复）
- 新建 `utils/path_utils.py`
- 验证配置系统可用

**阶段 2：新增代码使用配置系统**
- 新模块使用 `PathConfig.resolve()`
- 旧模块保持不动

**阶段 3：逐步替换旧代码**
- 按优先级替换硬编码路径：
  1. task_builder.py（影响子 Agent，最高优先级）
  2. orchestrator_base.py（影响 Blackboard）
  3. investment/solution 领域代码
  4. 测试脚本

**阶段 4：删除兼容性代码**
- 移除旧的硬编码路径
- 更新文档

### 5.2 兼容性保证

```python
# 过渡期兼容代码（带弃用警告）
def get_base_dir() -> str:
    """
    兼容旧版硬编码路径
    
    优先级：
    1. 环境变量 DEEPFLOW_BASE
    2. 基于当前工作目录推导
    3. 旧版硬编码路径（向后兼容，带弃用警告）
    """
    # 新版方式
    env_base = os.environ.get('DEEPFLOW_BASE')
    if env_base:
        return env_base
    
    # 基于工作目录推导
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / 'domains').exists():
            return str(parent)
    
    # 旧版兼容（带弃用警告）
    import warnings
    warnings.warn(
        "Hardcoded path is deprecated. Please set DEEPFLOW_BASE environment variable.",
        DeprecationWarning,
        stacklevel=2
    )
    return "/Users/allen/.openclaw/workspace/.deepflow"
```

---

## 6. 验证方案

### 6.1 自动化验证

```yaml
# 新增验证规则到项目契约

path_contract:
  validation:
    - name: "无硬编码用户路径"
      command: "grep -r '/Users/' --include='*.py' . | wc -l"
      expected: "0"
      
    - name: "无硬编码 Windows 路径"
      command: "grep -r 'C:\\\\Users\\\\' --include='*.py' . | wc -l"
      expected: "0"
      
    - name: "环境变量使用检查"
      command: "grep -r 'DEEPFLOW_BASE' --include='*.py' . | wc -l"
      expected: ">= 10"
      
    - name: "PathConfig 导入检查"
      command: "grep -r 'from core.config' --include='*.py' . | wc -l"
      expected: ">= 5"
      
    - name: "路径安全验证函数检查"
      command: "grep -r 'validate_path_safety' --include='*.py' . | wc -l"
      expected: ">= 1"
```

### 6.2 单元测试

```python
# tests/test_path_config.py

import os
import pytest
import tempfile
from pathlib import Path
from core.config.path_config import PathConfig, validate_path_safety

class TestPathConfig:
    def test_resolve_from_env(self):
        """测试从环境变量解析"""
        os.environ['DEEPFLOW_BASE'] = '/tmp/test_deepflow'
        config = PathConfig.resolve()
        assert config.base_dir == Path('/tmp/test_deepflow')
    
    def test_resolve_default(self):
        """测试默认解析"""
        if 'DEEPFLOW_BASE' in os.environ:
            del os.environ['DEEPFLOW_BASE']
        config = PathConfig.resolve()
        assert config.base_dir.name == '.deepflow'
    
    def test_path_traversal_protection(self):
        """测试路径遍历防护"""
        config = PathConfig('/tmp/test')
        with pytest.raises(ValueError, match="Path traversal"):
            config.get_blackboard_path("../../../etc/passwd")
    
    def test_symlink_protection(self, tmp_path):
        """测试符号链接防护"""
        config = PathConfig(str(tmp_path))
        blackboard = tmp_path / 'blackboard'
        blackboard.mkdir()
        
        # 创建恶意符号链接
        symlink = blackboard / 'evil_link'
        symlink.symlink_to('/etc')
        
        with pytest.raises(ValueError, match="Symlink"):
            config.get_blackboard_path('evil_link')
    
    def test_permission_isolation(self, tmp_path):
        """测试权限隔离"""
        config = PathConfig(str(tmp_path))
        config.ensure_directories()
        
        # 检查权限（仅 Unix）
        if os.name != 'nt':
            import stat
            mode = (tmp_path / 'blackboard').stat().st_mode
            assert mode & 0o777 == 0o700
    
    def test_ensure_directories(self, tmp_path):
        """测试目录创建"""
        config = PathConfig(str(tmp_path))
        config.ensure_directories()
        assert config.blackboard_dir.exists()
        assert config.config_dir.exists()
        assert config.logs_dir.exists()
        assert config.cache_dir.exists()
    
    def test_validate_env_path(self):
        """测试环境变量路径验证"""
        # 绝对路径 - 应该通过
        PathConfig._validate_env_path('/home/user/.deepflow')
        
        # 相对路径 - 应该失败
        with pytest.raises(ValueError, match="must be absolute"):
            PathConfig._validate_env_path('relative/path')
        
        # 包含 .. - 应该失败
        with pytest.raises(ValueError, match="contains '..'"):
            PathConfig._validate_env_path('/home/../etc')

class TestPathUtils:
    def test_get_system_paths(self):
        """测试系统路径获取"""
        from utils.path_utils import get_system_paths
        paths = get_system_paths()
        assert 'home' in paths
        assert 'config' in paths
        assert 'cache' in paths
        assert all(isinstance(p, Path) for p in paths.values())
    
    def test_validate_path_safety(self, tmp_path):
        """测试路径安全验证"""
        allowed = tmp_path / 'allowed'
        allowed.mkdir()
        
        # 安全路径
        safe_path = allowed / 'safe.txt'
        validate_path_safety(safe_path, allowed)  # 不应抛出异常
        
        # 路径遍历
        evil_path = allowed / '..' / 'etc' / 'passwd'
        with pytest.raises(ValueError, match="Path traversal"):
            validate_path_safety(evil_path, allowed)
```

### 6.3 手动验证清单

```markdown
## 发布前验证

- [ ] macOS 本地安装测试
- [ ] Linux (Ubuntu/CentOS) 安装测试
- [ ] Windows (PowerShell/CMD) 安装测试
- [ ] Docker 容器内运行测试
- [ ] 多用户场景测试（路径隔离）
- [ ] OpenClaw Skill 模式测试
- [ ] 独立运行模式测试
- [ ] 路径遍历攻击测试（../../../etc/passwd）
- [ ] 符号链接攻击测试
- [ ] 权限隔离测试（多用户服务器）
```

---

## 7. 实施建议

### 7.1 优先级排序

**修订说明：** 根据专家评审，将安全修复提前到 P0。

| 优先级 | 任务 | 工作量 | 阻塞性 | 修复的 P0 |
|:---|:---|:---:|:---:|:---|
| P0 | 创建 PathConfig 配置系统（含安全修复） | 中 | 是 | P0-1, P0-2, P0-3, P0-5, P0-6, P0-7 |
| P0 | 替换 task_builder.py 路径 | 小 | 是 | - |
| P1 | 添加路径安全验证到所有文件操作 | 中 | 否 | - |
| P1 | 编写单元测试（test_path_config.py） | 中 | 否 | - |
| P2 | 替换 orchestrator_base.py 路径 | 大 | 否 | - |
| P2 | 跨平台缓存目录 | 中 | 否 | - |
| P3 | 删除旧版兼容代码 | 小 | 否 | - |

### 7.2 不做的范围（明确边界）

**不在本方案内：**
- 数据库路径迁移（保持独立）
- 网络存储路径（NAS/S3）
- 加密文件系统路径
- 多实例并发路径隔离（需要锁机制）
- YAML 配置文件支持（根据专家评审已移除）

---

## 8. 安全加固总结

### 8.1 已修复的安全问题

| 问题 | 修复措施 | 代码位置 |
|:---|:---|:---|
| **P0-5 路径遍历** | `is_relative_to()` 检查 + session_id 清理 | `get_blackboard_path()` |
| **P0-6 符号链接** | `is_symlink()` 检查 | `get_blackboard_path()` |
| **P0-7 权限隔离** | `os.chmod(dir_path, 0o700)` | `ensure_directories()` |
| **P1-3 环境变量注入** | 验证绝对路径 + 禁止 `..` | `_validate_env_path()` |
| **P1-2 临时文件** | `mkstemp()` + `chmod 0o600` | `create_secure_temp_file()` |

### 8.2 安全记忆锚点

> "路径不校验，等于开大门"
> "符号链接不检查，等于送钥匙"
> "权限不设限，等于裸奔"

---

## 9. 总结

### 核心设计（修订版）

```
环境变量 > 默认值（基于安装位置推导）
     ↓
统一 PathConfig 接口（含安全防护）
     ↓
主 Agent 解析路径 → 嵌入 task 字符串
     ↓
子 Agent 接收绝对路径 → 直接写入
```

### 关键决策（修订版）

| 决策 | 选择 | 理由 |
|:---|:---|:---|
| 配置方式 | 环境变量 + 默认值 | 简单、可覆盖、无需 YAML 解析 |
| 路径格式 | POSIX (`/`) | 跨平台、Python pathlib 自动处理 |
| 与 OpenClaw 集成 | **绝对路径嵌入 task** | `sessions_spawn` 不支持 `env` |
| 安全策略 | 路径遍历/符号链接/权限三重防护 | 基础安全要求 |
| 迁移策略 | 渐进式 | 降低风险，保持兼容 |

### 与 v1 的主要差异

| 方面 | v1 | v2（修订版） |
|:---|:---|:---|
| 配置层级 | 4层（含 YAML） | 2层（仅环境变量+默认值） |
| OpenClaw 集成 | 方案 A（env，不可行） | 绝对路径嵌入 task |
| 安全防护 | 无 | 路径遍历/符号链接/权限 |
| `__file__` 使用 | 类方法内（bug） | 模块级常量（修复） |
| `os.uname()` | 存在（Windows 崩溃） | 替换为 `platform.system()` |

---

*文档版本: 2026-04-27-v2*
*状态: 根据第一轮专家评审修订完成*
*修订内容: 修复7个P0问题，简化配置层级，强化安全防护*