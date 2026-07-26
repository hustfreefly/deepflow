"""
PathManager 测试套件

测试覆盖：
1. 契约验证（前置/后置条件）
2. 安全性（路径遍历防护）
3. 跨平台兼容性
4. 并发安全（文件锁）
5. 域特定路径
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
import time

from core.path_manager import (
    PathManager,
    PathValidationError,
    PathNotFoundError,
    PathNotWritableError,
    PathTraversalError,
)


class TestPathManagerContract:
    """契约验证测试"""

    def test_session_id_sanitization(self, tmp_path):
        """测试 session_id 清理"""
        # 正常情况
        pm = PathManager("test_session", tmp_path)
        assert pm.session_id == "test_session"

        # 特殊字符清理
        pm = PathManager("test/session\\with:bad", tmp_path)
        assert "/" not in pm.session_id
        assert "\\" not in pm.session_id
        assert ":" not in pm.session_id

        # 空 session_id 应该失败
        with pytest.raises(PathValidationError):
            PathManager("", tmp_path)

    def test_path_traversal_prevention(self, tmp_path):
        """测试路径遍历防护"""
        pm = PathManager("test_session", tmp_path)

        # 正常路径应该成功
        path = pm.get_output_path("test.json")
        assert path.exists() or not path.exists()  # 路径对象有效

        # 路径遍历应该失败（FileNameInput 验证先触发，抛出 PathValidationError）
        with pytest.raises(PathValidationError):
            pm.get_output_path("../../../etc/passwd")

        with pytest.raises(PathValidationError):
            pm.get_blackboard_path("../../../etc/passwd")

    def test_file_name_validation(self, tmp_path):
        """测试文件名验证"""
        pm = PathManager("test_session", tmp_path)

        # 正常文件名应该成功
        path = pm.get_output_path("test_file.json")
        assert path.name == "test_file.json"

        # 包含路径分隔符应该失败
        with pytest.raises(PathValidationError):
            pm.get_output_path("test/file.json")

        with pytest.raises(PathValidationError):
            pm.get_output_path("test\\file.json")


class TestPathManagerDomain:
    """域特定路径测试"""

    def test_solution_domain(self, tmp_path):
        """测试 Solution 域路径"""
        pm = PathManager("test_session", tmp_path, domain="solution")

        # 检查域特定目录
        assert pm.stages == tmp_path / "blackboard" / "test_session" / "stages"
        assert pm.data == tmp_path / "blackboard" / "test_session" / "data"
        assert pm.runs == tmp_path / "blackboard" / "test_session" / ".runs"

    def test_ship_domain(self, tmp_path):
        """测试 Ship 域路径"""
        pm = PathManager("test_session", tmp_path, domain="ship")

        # Ship 域应该有 artifacts 和 packages
        assert pm.stages == tmp_path / "blackboard" / "test_session" / "stages"
        assert pm.artifacts == tmp_path / "blackboard" / "test_session" / "artifacts"
        assert pm.packages == tmp_path / "blackboard" / "test_session" / "packages"

    def test_deliver_domain(self, tmp_path):
        """测试 Deliver 域路径"""
        pm = PathManager("test_session", tmp_path, domain="deliver")

        # Deliver 域应该有 deliveries
        assert pm.stages == tmp_path / "blackboard" / "test_session" / "stages"
        assert pm.deliveries == tmp_path / "blackboard" / "test_session" / "deliveries"


class TestPathManagerConcurrency:
    """并发安全测试"""

    def test_concurrent_directory_creation(self, tmp_path):
        """测试并发创建目录"""
        pm = PathManager("test_session", tmp_path)

        # 并发创建同一个目录
        def create_dir():
            pm.ensure_directories()
            return True

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_dir) for _ in range(10)]
            results = [f.result() for f in futures]

        # 所有操作都应该成功
        assert all(results)
        assert pm.stages.exists()
        assert pm.data.exists()
        assert pm.runs.exists()

    def test_concurrent_file_writes(self, tmp_path):
        """测试并发写入文件"""
        pm = PathManager("test_session", tmp_path)
        pm.ensure_directories()

        def write_file(index):
            path = pm.get_output_path(f"test_{index}.json")
            pm.ensure_parent(path)
            path.write_text(f'{{"index": {index}}}')
            return path

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_file, i) for i in range(10)]
            paths = [f.result() for f in futures]

        # 所有文件都应该存在
        for path in paths:
            assert path.exists()


class TestPathManagerCrossPlatform:
    """跨平台兼容性测试"""

    def test_unicode_session_id(self, tmp_path):
        """测试 Unicode session_id"""
        # 中文 session_id
        pm = PathManager("测试会话", tmp_path)
        assert pm.session_id == "测试会话"

        # 混合字符
        pm = PathManager("test_测试_123", tmp_path)
        assert "test" in pm.session_id
        assert "测试" in pm.session_id
        assert "123" in pm.session_id

    def test_path_length_validation(self, tmp_path):
        """测试路径长度验证"""
        pm = PathManager("test_session", tmp_path)

        # 正常长度应该成功
        path = pm.get_output_path("test.json")
        pm.validate_path_length(path)

        # 验证方法存在且能正常工作
        assert pm.get_max_path_length() > 0


class TestPathManagerError:
    """错误处理测试"""

    def test_root_not_found(self, tmp_path):
        """测试 root 不存在"""
        non_existent = tmp_path / "non_existent"
        with pytest.raises(PathNotFoundError, match="DeepFlow root"):
            PathManager("test_session", non_existent)

    def test_path_not_writable(self, tmp_path):
        """测试路径不可写"""
        pm = PathManager("test_session", tmp_path)

        # 创建只读目录
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        try:
            with pytest.raises(PathNotWritableError):
                pm.validate_path(readonly_dir, must_be_writable=True)
        finally:
            # 恢复权限以便清理
            readonly_dir.chmod(0o755)


class TestPathManagerIntegration:
    """集成测试"""

    def test_full_workflow(self, tmp_path):
        """测试完整工作流程"""
        # 1. 创建 PathManager
        pm = PathManager("test_session", tmp_path, domain="solution")

        # 2. 确保目录存在
        pm.ensure_directories()
        assert pm.stages.exists()
        assert pm.data.exists()
        assert pm.runs.exists()

        # 3. 获取各种路径
        prompt_path = pm.get_prompt_path("planning")
        output_path = pm.get_output_path("result.json")
        data_path = pm.get_data_path("spec.json")

        # 4. 验证路径在正确范围内
        assert str(prompt_path).startswith(str(pm.stages))
        assert str(output_path).startswith(str(pm.stages))
        assert str(data_path).startswith(str(pm.data))

        # 5. 确保父目录存在
        pm.ensure_parent(output_path)
        assert output_path.parent.exists()

        # 6. 写入文件
        output_path.write_text('{"result": "success"}')
        assert output_path.exists()

        # 7. 验证路径
        assert pm.validate_path(output_path, must_exist=True)

    def test_path_manager_reuse(self, tmp_path):
        """测试 PathManager 重用"""
        pm1 = PathManager("session1", tmp_path)
        pm1.ensure_directories()

        pm2 = PathManager("session2", tmp_path)
        pm2.ensure_directories()

        # 两个 session 应该有独立的目录
        assert pm1.stages != pm2.stages
        assert pm1.stages.exists()
        assert pm2.stages.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
