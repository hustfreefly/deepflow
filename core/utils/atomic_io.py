"""
原子 I/O 工具 — 消除散落在各域的重复实现。

契约笼子 Step 3: 基于 Pydantic 契约实现代码

替代 20+ 处重复实现：
- deliver_pro/orchestrator.py (5+ 处)
- deliver_pro/wp_runner.py (2 处)
- deliver_pro/blackboard.py (2 处)
- solution_pro/pulse.py (5+ 处)
- solution_pro/blackboard.py (1 处)
- core/blackboard/blackboard_manager.py (3 处)

用法：
    from core.utils.atomic_io import atomic_write_json, atomic_write_text, safe_read_json

    # 替代手写 tempfile+fsync+rename
    atomic_write_json(path, data)
    atomic_write_text(path, content)
    data = safe_read_json(path, default={})
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .atomic_io_contracts import (
    AtomicWriteJsonInput,
    AtomicWriteTextInput,
    SafeReadJsonInput,
)


def atomic_write_json(
    path: Path | str,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """原子写 JSON（temp + fsync + replace）。

    契约：AtomicWriteJsonInput → None
    异常：写入失败时 raise，不静默留下半成品文件。

    Args:
        path: 目标文件路径
        data: JSON 可序列化数据
        indent: JSON 缩进（默认 2）
        ensure_ascii: 是否转义非 ASCII（默认 False，保留中文）
    """
    # 契约验证
    validated = AtomicWriteJsonInput(
        path=Path(path), data=data, indent=indent, ensure_ascii=ensure_ascii
    )
    target = validated.path
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        content = json.dumps(
            validated.data,
            ensure_ascii=validated.ensure_ascii,
            indent=validated.indent,
        ).encode("utf-8")
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(
    path: Path | str,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """原子写文本。

    契约：AtomicWriteTextInput → None
    异常：写入失败时 raise。

    Args:
        path: 目标文件路径
        text: 文本内容
        encoding: 文本编码（默认 utf-8）
    """
    # 契约验证
    validated = AtomicWriteTextInput(path=Path(path), text=text, encoding=encoding)
    target = validated.path
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        os.write(fd, validated.text.encode(validated.encoding))
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def safe_read_json(path: Path | str, default: Any = None) -> Any:
    """安全读取 JSON（不存在或解析失败返回 default）。

    契约：SafeReadJsonInput → Any
    异常：永不 raise，失败时返回 default。

    Args:
        path: 文件路径
        default: 文件不存在或 JSON 解析失败时的返回值

    Returns:
        解析后的数据，或 default
    """
    # 契约验证
    validated = SafeReadJsonInput(path=Path(path), default=default)
    target = validated.path

    if not target.exists():
        return validated.default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return validated.default


# ============================================================================
# 便捷别名（兼容现有代码的迁移路径）
# ============================================================================

# 某些域用 _atomic_write_json 作为方法名，提供模块级函数便于替换
_atomic_write_json = atomic_write_json
