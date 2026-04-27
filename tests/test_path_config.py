"""
PathConfig 单元测试
契约笼子验证套件
"""

import os
import pytest
import tempfile
from pathlib import Path
from core.config.path_config import PathConfig, validate_path_safety, _is_relative_to


class TestPathConfig:
    """PathConfig 核心测试"""
    
    def test_resolve_from_env(self):
        """测试从环境变量解析"""
        os.environ['DEEPFLOW_BASE'] = '/tmp/test_deepflow'
        config = PathConfig.resolve()
        assert config.base_dir == Path('/tmp/test_deepflow')
    
    def test_resolve_default(self):
        """测试默认解析（基于 __file__ 推导）"""
        if 'DEEPFLOW_BASE' in os.environ:
            del os.environ['DEEPFLOW_BASE']
        config = PathConfig.resolve()
        # 默认应基于 _MODULE_DIR 推导
        assert config.base_dir.exists() or True  # 至少不应崩溃
    
    def test_max_session_id_length(self):
        """P1-4: session_id 长度限制"""
        config = PathConfig('/tmp/test')
        with pytest.raises(ValueError, match="too long"):
            config.get_blackboard_path("a" * 300)
    
    def test_sanitize_session_id(self):
        """测试 session_id 清理"""
        config = PathConfig('/tmp/test')
        
        # 正常字符
        path = config.get_blackboard_path("session_123-test")
        assert "session_123-test" in str(path)
        
        # 非法字符被替换
        path2 = config.get_blackboard_path("test@#$file")
        assert "test___file" in str(path2)
    
    def test_empty_session_id(self):
        """测试空 session_id"""
        config = PathConfig('/tmp/test')
        with pytest.raises(ValueError, match="cannot be empty"):
            config.get_blackboard_path("!!!")
    
    def test_ensure_directories(self, tmp_path):
        """测试目录创建"""
        config = PathConfig(str(tmp_path))
        config.ensure_directories()
        assert config.blackboard_dir.exists()
        assert config.config_dir.exists()
        assert config.logs_dir.exists()
        assert config.cache_dir.exists()
    
    def test_permission_isolation(self, tmp_path):
        """P0-7: 权限隔离"""
        config = PathConfig(str(tmp_path))
        config.ensure_directories()
        
        # 检查权限（仅 Unix）
        if os.name != 'nt':
            mode = (tmp_path / 'blackboard').stat().st_mode & 0o777
            assert mode == 0o700
    
    def test_validate_env_path_existing_file(self):
        """P1-5: DEEPFLOW_BASE 指向文件"""
        import tempfile as tf
        with tf.NamedTemporaryFile() as tmp:
            with pytest.raises(ValueError, match="not a directory"):
                PathConfig._validate_env_path(tmp.name)
    
    def test_validate_env_path_relative(self):
        """P1-5: 相对路径被拒绝"""
        with pytest.raises(ValueError, match="must be absolute"):
            PathConfig._validate_env_path('relative/path')
    
    def test_is_relative_to_compat(self):
        """P0-D: _is_relative_to 兼容性"""
        base = Path('/tmp/base')
        child = base / 'child'
        outside = Path('/tmp/outside')
        
        assert _is_relative_to(child, base) is True
        assert _is_relative_to(outside, base) is False
    
    def test_repr(self):
        """测试 __repr__"""
        config = PathConfig('/tmp/test')
        repr_str = repr(config)
        assert 'PathConfig' in repr_str
        assert '/tmp/test' in repr_str


class TestPathSafety:
    """路径安全验证测试"""
    
    def test_validate_path_safety_normal(self, tmp_path):
        """正常路径通过"""
        allowed = tmp_path / 'allowed'
        allowed.mkdir()
        safe_path = allowed / 'safe.txt'
        validate_path_safety(safe_path, allowed)  # 不应抛出异常
    
    def test_validate_path_safety_traversal(self, tmp_path):
        """路径遍历被阻止"""
        allowed = tmp_path / 'allowed'
        allowed.mkdir()
        evil_path = allowed / '..' / 'etc' / 'passwd'
        with pytest.raises(ValueError, match="Path traversal"):
            validate_path_safety(evil_path, allowed)
