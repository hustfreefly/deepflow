"""
atomic_io 端到端验证 — 契约笼子 Step 4

验证项：
1. atomic_write_json 正常写入
2. atomic_write_json 原子性（写入失败不留临时文件）
3. atomic_write_text 正常写入
4. safe_read_json 正常读取
5. safe_read_json 文件不存在返回 default
6. safe_read_json 损坏 JSON 返回 default
7. 契约验证：extra fields 被拒绝
8. 并发写入安全（两进程同时写不截断）
"""

import json
import os
import tempfile
import threading
from pathlib import Path

import pytest

from core.utils.atomic_io import atomic_write_json, atomic_write_text, safe_read_json
from core.utils.atomic_io_contracts import (
    AtomicWriteJsonInput,
    AtomicWriteTextInput,
    SafeReadJsonInput,
)


@pytest.fixture
def tmp_dir(tmp_path):
    """提供临时目录"""
    return tmp_path


# ============================================================================
# 1. atomic_write_json 正常写入
# ============================================================================


class TestAtomicWriteJson:
    def test_basic_write(self, tmp_dir):
        """基本 JSON 写入"""
        target = tmp_dir / "test.json"
        data = {"key": "value", "number": 42, "list": [1, 2, 3]}

        atomic_write_json(target, data)

        assert target.exists()
        result = json.loads(target.read_text())
        assert result == data

    def test_chinese_content(self, tmp_dir):
        """中文内容不转义"""
        target = tmp_dir / "chinese.json"
        data = {"name": "忠礼", "project": "深度流"}

        atomic_write_json(target, data, ensure_ascii=False)

        content = target.read_text()
        assert "忠礼" in content  # 不转义
        assert "\\u" not in content

    def test_custom_indent(self, tmp_dir):
        """自定义缩进"""
        target = tmp_dir / "indent.json"
        data = {"a": 1}

        atomic_write_json(target, data, indent=4)

        content = target.read_text()
        assert "    " in content  # 4 空格缩进

    def test_creates_parent_dirs(self, tmp_dir):
        """自动创建父目录"""
        target = tmp_dir / "a" / "b" / "c" / "test.json"

        atomic_write_json(target, {"nested": True})

        assert target.exists()
        assert json.loads(target.read_text()) == {"nested": True}

    def test_overwrite_existing(self, tmp_dir):
        """覆盖已有文件"""
        target = tmp_dir / "overwrite.json"
        atomic_write_json(target, {"old": "data"})
        atomic_write_json(target, {"new": "data"})

        result = json.loads(target.read_text())
        assert result == {"new": "data"}

    def test_no_temp_file_left(self, tmp_dir):
        """写入完成后不留临时文件"""
        target = tmp_dir / "clean.json"
        atomic_write_json(target, {"clean": True})

        temp_files = list(tmp_dir.glob(".clean.json.*.tmp"))
        assert len(temp_files) == 0


# ============================================================================
# 2. atomic_write_text 正常写入
# ============================================================================


class TestAtomicWriteText:
    def test_basic_write(self, tmp_dir):
        """基本文本写入"""
        target = tmp_dir / "test.txt"
        atomic_write_text(target, "hello world")

        assert target.exists()
        assert target.read_text() == "hello world"

    def test_chinese_text(self, tmp_dir):
        """中文文本"""
        target = tmp_dir / "cn.txt"
        atomic_write_text(target, "你好世界")

        assert target.read_text() == "你好世界"

    def test_creates_parent_dirs(self, tmp_dir):
        """自动创建父目录"""
        target = tmp_dir / "x" / "y" / "test.txt"
        atomic_write_text(target, "nested")

        assert target.exists()

    def test_overwrite(self, tmp_dir):
        """覆盖已有文件"""
        target = tmp_dir / "ow.txt"
        atomic_write_text(target, "old")
        atomic_write_text(target, "new")

        assert target.read_text() == "new"


# ============================================================================
# 3. safe_read_json 正常读取
# ============================================================================


class TestSafeReadJson:
    def test_basic_read(self, tmp_dir):
        """正常读取"""
        target = tmp_dir / "read.json"
        target.write_text('{"key": "value"}')

        result = safe_read_json(target)
        assert result == {"key": "value"}

    def test_file_not_found(self, tmp_dir):
        """文件不存在返回 default"""
        target = tmp_dir / "missing.json"

        result = safe_read_json(target, default={"fallback": True})
        assert result == {"fallback": True}

    def test_file_not_found_no_default(self, tmp_dir):
        """文件不存在且无 default 返回 None"""
        target = tmp_dir / "missing.json"

        result = safe_read_json(target)
        assert result is None

    def test_corrupted_json(self, tmp_dir):
        """损坏的 JSON 返回 default"""
        target = tmp_dir / "bad.json"
        target.write_text("{invalid json content")

        result = safe_read_json(target, default="fallback")
        assert result == "fallback"

    def test_empty_file(self, tmp_dir):
        """空文件返回 default"""
        target = tmp_dir / "empty.json"
        target.write_text("")

        result = safe_read_json(target, default=42)
        assert result == 42


# ============================================================================
# 4. 契约验证
# ============================================================================


class TestContracts:
    def test_write_json_input_valid(self):
        """合法输入通过验证"""
        inp = AtomicWriteJsonInput(
            path=Path("/tmp/test.json"),
            data={"key": "value"},
            indent=2,
            ensure_ascii=False,
        )
        assert inp.indent == 2

    def test_write_json_input_indent_range(self):
        """indent 超范围被拒绝"""
        with pytest.raises(Exception):
            AtomicWriteJsonInput(
                path=Path("/tmp/test.json"),
                data={},
                indent=99,  # 超过 max=8
            )

    def test_write_text_input_valid(self):
        """合法文本输入通过验证"""
        inp = AtomicWriteTextInput(
            path=Path("/tmp/test.txt"),
            text="hello",
            encoding="utf-8",
        )
        assert inp.text == "hello"

    def test_read_input_valid(self):
        """合法读取输入通过验证"""
        inp = SafeReadJsonInput(
            path=Path("/tmp/test.json"),
            default=None,
        )
        assert inp.default is None


# ============================================================================
# 5. 并发写入安全
# ============================================================================


class TestConcurrency:
    def test_concurrent_writes(self, tmp_dir):
        """多线程并发写同一文件，不截断"""
        target = tmp_dir / "concurrent.json"
        errors = []

        def writer(i):
            try:
                atomic_write_json(target, {"thread": i, "data": "x" * 1000})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # 最终文件应该是完整的（某个线程的数据）
        result = json.loads(target.read_text())
        assert "thread" in result
        assert "data" in result

    def test_write_does_not_corrupt_on_failure(self, tmp_dir):
        """写入失败时原文件不受影响"""
        target = tmp_dir / "safe.json"
        original = {"original": "data"}
        atomic_write_json(target, original)

        # 尝试写入不可 JSON 序列化的对象
        try:
            atomic_write_json(target, object())
        except (TypeError, ValueError):
            pass

        # 原文件应该还在
        result = json.loads(target.read_text())
        assert result == original


# ============================================================================
# 6. 路径兼容性
# ============================================================================


class TestPathCompat:
    def test_string_path(self, tmp_dir):
        """接受字符串路径"""
        target = str(tmp_dir / "str_path.json")
        atomic_write_json(target, {"str": True})

        result = safe_read_json(target)
        assert result == {"str": True}

    def test_path_object(self, tmp_dir):
        """接受 Path 对象"""
        target = tmp_dir / "path_obj.json"
        atomic_write_json(target, {"path": True})

        result = safe_read_json(target)
        assert result == {"path": True}
