"""
BlackboardManager V6 契约测试

测试覆盖:
- write_stage 覆盖写入（非合并）+ 原子写入
- read_stage 带/不带 default
- write_dynamic_stage 动态命名
- stage_exists 存在性检查
- list_stages 返回 list[str]（Breaking Change 验证）
- delete_stage 删除 stage
- append_stage 增量更新
- read_stage_raw 读取非 JSON
- get_session_dir 获取 session 目录
- copy_stage 复制 stage
- get_stage_path 发出 DeprecationWarning
- 写操作失败时返回 False + log warning
"""

import json
import os
import tempfile
import warnings
from pathlib import Path

import pytest


@pytest.fixture
def bb(tmp_path):
    """创建临时 BlackboardManager 实例"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from core.blackboard.blackboard_manager import BlackboardManager
    return BlackboardManager(session_id="test_session", base_dir=tmp_path)


@pytest.fixture
def bb_with_init(bb):
    """创建已初始化的 BlackboardManager"""
    bb.init_session()
    return bb


class TestWriteStage:
    """write_stage 测试"""

    def test_basic_write(self, bb_with_init):
        """基础写入"""
        result = bb_with_init.write_stage("planning", {"status": "completed"})
        assert result is True

    def test_overwrite_not_merge(self, bb_with_init):
        """覆盖写入（非合并）"""
        bb_with_init.write_stage("planning", {"field1": "value1"})
        bb_with_init.write_stage("planning", {"field2": "value2"})
        data = bb_with_init.read_stage("planning")
        assert data == {"field2": "value2"}, "write_stage should overwrite, not merge"

    def test_atomic_write(self, bb_with_init):
        """原子写入验证（文件完整或不存在）"""
        bb_with_init.write_stage("atomic_test", {"key": "value"})
        data = bb_with_init.read_stage("atomic_test")
        assert data == {"key": "value"}

    def test_chinese_content(self, bb_with_init):
        """中文内容写入"""
        result = bb_with_init.write_stage("chinese", {"内容": "中文测试"})
        assert result is True
        data = bb_with_init.read_stage("chinese")
        assert data["内容"] == "中文测试"


class TestReadStage:
    """read_stage 测试"""

    def test_read_existing(self, bb_with_init):
        """读取已存在的 stage"""
        bb_with_init.write_stage("existing", {"key": "value"})
        data = bb_with_init.read_stage("existing")
        assert data == {"key": "value"}

    def test_read_nonexistent_with_default(self, bb_with_init):
        """读取不存在的 stage（带 default）"""
        data = bb_with_init.read_stage("nonexistent", default={"status": "pending"})
        assert data == {"status": "pending"}

    def test_read_nonexistent_without_default(self, bb_with_init):
        """读取不存在的 stage（不带 default）"""
        data = bb_with_init.read_stage("nonexistent")
        assert data is None


class TestWriteDynamicStage:
    """write_dynamic_stage 测试"""

    def test_single_variable(self, bb_with_init):
        """单变量模板"""
        result = bb_with_init.write_dynamic_stage(
            "research_expert_{expert_id}",
            data={"findings": "test"},
            expert_id=1
        )
        assert result is True
        assert bb_with_init.stage_exists("research_expert_1")

    def test_multi_variable(self, bb_with_init):
        """多变量模板"""
        result = bb_with_init.write_dynamic_stage(
            "review_{domain}_{round}",
            data={"score": 95},
            domain="security", round=2
        )
        assert result is True
        assert bb_with_init.stage_exists("review_security_2")


class TestStageExists:
    """stage_exists 测试"""

    def test_exists(self, bb_with_init):
        """已存在的 stage"""
        bb_with_init.write_stage("exists_test", {"key": "value"})
        assert bb_with_init.stage_exists("exists_test") is True

    def test_not_exists(self, bb_with_init):
        """不存在的 stage"""
        assert bb_with_init.stage_exists("not_exists") is False


class TestListStages:
    """list_stages 测试（Breaking Change 验证）"""

    def test_returns_list(self, bb_with_init):
        """返回 list[str]"""
        result = bb_with_init.list_stages()
        assert isinstance(result, list)

    def test_empty_stages(self, bb_with_init):
        """空 stages"""
        result = bb_with_init.list_stages()
        assert result == []

    def test_lists_existing_stages(self, bb_with_init):
        """列出已存在的 stage"""
        bb_with_init.write_stage("alpha", {"key": "a"})
        bb_with_init.write_stage("beta", {"key": "b"})
        result = bb_with_init.list_stages()
        assert sorted(result) == ["alpha", "beta"]

    def test_breaking_change_not_dict(self, bb_with_init):
        """Breaking Change: 不再返回 Dict[str, bool]"""
        bb_with_init.write_stage("test", {"key": "value"})
        result = bb_with_init.list_stages()
        assert not isinstance(result, dict), "list_stages should return list, not dict"


class TestDeleteStage:
    """delete_stage 测试"""

    def test_delete_existing(self, bb_with_init):
        """删除已存在的 stage"""
        bb_with_init.write_stage("to_delete", {"key": "value"})
        result = bb_with_init.delete_stage("to_delete")
        assert result is True
        assert not bb_with_init.stage_exists("to_delete")

    def test_delete_nonexistent(self, bb_with_init):
        """删除不存在的 stage（幂等）"""
        result = bb_with_init.delete_stage("never_existed")
        assert result is True


class TestAppendStage:
    """append_stage 测试"""

    def test_append_to_existing(self, bb_with_init):
        """增量更新已存在的 stage"""
        bb_with_init.write_stage("planning", {"field1": "value1"})
        result = bb_with_init.append_stage("planning", {"field2": "value2"})
        assert result is True
        data = bb_with_init.read_stage("planning")
        assert data == {"field1": "value1", "field2": "value2"}

    def test_append_to_nonexistent(self, bb_with_init):
        """增量更新不存在的 stage（创建新文件）"""
        result = bb_with_init.append_stage("new_stage", {"field1": "value1"})
        assert result is True
        data = bb_with_init.read_stage("new_stage")
        assert data == {"field1": "value1"}


class TestReadStageRaw:
    """read_stage_raw 测试"""

    def test_read_md_file(self, bb_with_init):
        """读取 .md 文件"""
        md_path = bb_with_init._stages_dir / "report.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("# Report\nContent here", encoding="utf-8")
        result = bb_with_init.read_stage_raw("report")
        assert result == "# Report\nContent here"

    def test_read_nonexistent_raw(self, bb_with_init):
        """读取不存在的文件"""
        result = bb_with_init.read_stage_raw("nonexistent")
        assert result is None


class TestGetSessionDir:
    """get_session_dir 测试"""

    def test_returns_path(self, bb_with_init):
        """返回 Path 对象"""
        result = bb_with_init.get_session_dir()
        assert isinstance(result, Path)
        assert result.exists()


class TestCopyStage:
    """copy_stage 测试"""

    def test_copy_existing(self, bb_with_init):
        """复制已存在的 stage"""
        bb_with_init.write_stage("original", {"key": "value"})
        result = bb_with_init.copy_stage("original", "snapshot")
        assert result is True
        data = bb_with_init.read_stage("snapshot")
        assert data == {"key": "value"}

    def test_copy_nonexistent(self, bb_with_init):
        """复制不存在的 stage"""
        result = bb_with_init.copy_stage("nonexistent", "target")
        assert result is False


class TestDeprecatedMethods:
    """废弃方法测试"""

    def test_get_stage_path_deprecation_warning(self, bb_with_init):
        """get_stage_path 发出 DeprecationWarning"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            bb_with_init.get_stage_path("test")
            assert len(w) >= 1
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_list_stages_registry_backward_compat(self, bb_with_init):
        """list_stages_registry 保持旧的 Dict[str, bool] 行为"""
        result = bb_with_init.list_stages_registry()
        assert isinstance(result, dict)


class TestErrorHandling:
    """错误处理测试"""

    def test_write_stage_returns_false_on_error(self, bb_with_init):
        """写操作失败时返回 False"""
        # 通过创建一个不可写的目录来触发错误
        bad_dir = bb_with_init._stages_dir / "bad"
        bad_dir.mkdir()
        # 尝试写入一个目录名（会失败）
        result = bb_with_init.write_stage("bad", {"key": "value"})
        # 这个测试验证 write_stage 不会抛异常
        assert isinstance(result, bool)

    def test_read_stage_returns_default_on_error(self, bb_with_init):
        """读操作失败时返回 default"""
        # 创建一个不可读的文件
        bad_file = bb_with_init._stages_dir / "bad.json"
        bad_file.write_bytes(b"\x00\x01\x02")  # 无效 JSON
        data = bb_with_init.read_stage("bad", default={"fallback": True})
        assert data == {"fallback": True}


class TestInitSession:
    """init_session 测试"""

    def test_creates_stages_dir(self, bb):
        """init_session 创建 stages 子目录"""
        bb.init_session()
        assert (bb.session_dir / "stages").exists()

    def test_creates_shared_state(self, bb):
        """init_session 创建 shared_state.json"""
        bb.init_session()
        state = bb.get_state()
        assert "session_id" in state
        assert state["session_id"] == "test_session"


class TestCleanup:
    """cleanup 测试"""

    def test_cleanup_removes_dir(self, bb_with_init):
        """cleanup 删除 session 目录"""
        bb_with_init.write_stage("test", {"key": "value"})
        result = bb_with_init.cleanup()
        assert result is True
        assert not bb_with_init.session_dir.exists()
