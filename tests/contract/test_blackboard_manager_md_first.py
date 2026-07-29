"""
BlackboardManager MD-first 测试（ADR-009 Phase 2）

验证：
- write_stage(str) → 写入 .md 文件
- write_stage(dict) → 写入 .json 文件
- read_stage 优先读 .md，fallback 到 .json
- stage_exists 检查 .md 和 .json
- list_stages 包含 .md 和 .json
- delete_stage 删除两者
- copy_stage 保留后缀
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from core.blackboard.blackboard_manager import BlackboardManager


@pytest.fixture
def bb():
    """创建临时 BlackboardManager"""
    tmp_dir = tempfile.mkdtemp()
    manager = BlackboardManager("test_md_first", base_dir=Path(tmp_dir))
    manager.init_session()
    yield manager
    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestWriteStageMD:
    """write_stage 支持 str → .md"""

    def test_write_str_creates_md(self, bb):
        """str 数据写入 .md 文件"""
        md_content = "# Test\n\nThis is markdown."
        result = bb.write_stage("test_md", md_content)
        assert result is True
        
        # 验证 .md 文件存在
        md_path = bb._stage_path("test_md", ".md")
        assert md_path.exists()
        
        # 验证 .json 文件不存在
        json_path = bb._stage_path("test_md", ".json")
        assert not json_path.exists()

    def test_write_dict_creates_json(self, bb):
        """dict 数据写入 .json 文件"""
        data = {"key": "value"}
        result = bb.write_stage("test_json", data)
        assert result is True
        
        # 验证 .json 文件存在
        json_path = bb._stage_path("test_json", ".json")
        assert json_path.exists()
        
        # 验证 .md 文件不存在
        md_path = bb._stage_path("test_json", ".md")
        assert not md_path.exists()

    def test_write_md_content_preserved(self, bb):
        """MD 内容完整保留"""
        md_content = "# Title\n\n## Section\n\n- Item 1\n- Item 2\n\n| Col1 | Col2 |\n|------|------|\n| A | B |"
        bb.write_stage("test_md", md_content)
        
        # 读取验证
        result = bb.read_stage("test_md", as_text=True)
        assert result == md_content


class TestReadStageMD:
    """read_stage 优先读 .md，fallback 到 .json"""

    def test_read_md_first(self, bb):
        """同时存在 .md 和 .json 时，优先读 .md"""
        # 写入 .json
        bb.write_stage("test", {"json": "data"})
        # 写入 .md
        bb.write_stage("test", "# MD Content")
        
        # 读取应该返回 MD 内容
        result = bb.read_stage("test", as_text=True)
        assert result == "# MD Content"

    def test_read_json_fallback(self, bb):
        """只有 .json 时，fallback 读 .json"""
        bb.write_stage("test", {"key": "value"})
        
        result = bb.read_stage("test")
        assert result == {"key": "value"}

    def test_read_md_as_text(self, bb):
        """read_stage(as_text=True) 返回原始文本"""
        bb.write_stage("test", "# MD")
        
        result = bb.read_stage("test", as_text=True)
        assert result == "# MD"
        assert isinstance(result, str)

    def test_read_md_as_dict_fails_gracefully(self, bb):
        """read_stage(as_text=False) 读 .md 时返回原始文本（不解析）"""
        bb.write_stage("test", "# MD")
        
        # as_text=False 时，.md 文件仍返回文本（不尝试 JSON 解析）
        result = bb.read_stage("test", as_text=False)
        assert result == "# MD"


class TestStageExistsMD:
    """stage_exists 检查 .md 和 .json"""

    def test_exists_md(self, bb):
        """只有 .md 时返回 True"""
        bb.write_stage("test", "# MD")
        assert bb.stage_exists("test") is True

    def test_exists_json(self, bb):
        """只有 .json 时返回 True"""
        bb.write_stage("test", {"key": "value"})
        assert bb.stage_exists("test") is True

    def test_exists_both(self, bb):
        """两者都存在时返回 True"""
        bb.write_stage("test", "# MD")
        bb.write_stage("test", {"key": "value"})
        assert bb.stage_exists("test") is True

    def test_not_exists(self, bb):
        """都不存在时返回 False"""
        assert bb.stage_exists("nonexistent") is False


class TestListStagesMD:
    """list_stages 包含 .md 和 .json"""

    def test_list_includes_md(self, bb):
        """list_stages 包含 .md 文件"""
        bb.write_stage("md_stage", "# MD")
        bb.write_stage("json_stage", {"key": "value"})
        
        stages = bb.list_stages()
        assert "md_stage" in stages
        assert "json_stage" in stages

    def test_list_dedup(self, bb):
        """同名 .md 和 .json 只出现一次"""
        bb.write_stage("test", "# MD")
        bb.write_stage("test", {"key": "value"})
        
        stages = bb.list_stages()
        assert stages.count("test") == 1


class TestDeleteStageMD:
    """delete_stage 删除 .md 和 .json"""

    def test_delete_both(self, bb):
        """删除同名 .md 和 .json"""
        bb.write_stage("test", "# MD")
        bb.write_stage("test", {"key": "value"})
        
        # 验证两者都存在
        assert bb._stage_path("test", ".md").exists()
        assert bb._stage_path("test", ".json").exists()
        
        # 删除
        bb.delete_stage("test")
        
        # 验证两者都不存在
        assert not bb._stage_path("test", ".md").exists()
        assert not bb._stage_path("test", ".json").exists()


class TestCopyStageMD:
    """copy_stage 保留后缀"""

    def test_copy_md(self, bb):
        """复制 .md 文件保留后缀"""
        bb.write_stage("src", "# MD Content")
        
        result = bb.copy_stage("src", "dst")
        assert result is True
        
        # 验证目标也是 .md
        assert bb._stage_path("dst", ".md").exists()
        assert not bb._stage_path("dst", ".json").exists()

    def test_copy_json(self, bb):
        """复制 .json 文件保留后缀"""
        bb.write_stage("src", {"key": "value"})
        
        result = bb.copy_stage("src", "dst")
        assert result is True
        
        # 验证目标也是 .json
        assert bb._stage_path("dst", ".json").exists()
        assert not bb._stage_path("dst", ".md").exists()


class TestAppendStageMD:
    """append_stage 仅支持 JSON stage"""

    def test_append_json_works(self, bb):
        """JSON stage 可以 append"""
        bb.write_stage("test", {"key": "value"})
        
        result = bb.append_stage("test", {"new_key": "new_value"})
        assert result is True
        
        data = bb.read_stage("test")
        assert data == {"key": "value", "new_key": "new_value"}

    def test_append_md_fails(self, bb):
        """MD stage 不能 append，返回 False"""
        bb.write_stage("test", "# MD")
        
        result = bb.append_stage("test", {"key": "value"})
        assert result is False


class TestBackwardCompatibility:
    """向后兼容性测试"""

    def test_old_api_still_works(self, bb):
        """旧的 dict API 仍然正常工作"""
        # 写入 dict
        bb.write_stage("test", {"key": "value"})
        
        # 读取 dict
        result = bb.read_stage("test")
        assert result == {"key": "value"}
        
        # 存在检查
        assert bb.stage_exists("test")
        
        # 列出 stages
        assert "test" in bb.list_stages()
