"""core.utils — 域无关的公共工具函数。"""

from .atomic_io import atomic_write_json, atomic_write_text, safe_read_json

__all__ = ["atomic_write_json", "atomic_write_text", "safe_read_json"]
