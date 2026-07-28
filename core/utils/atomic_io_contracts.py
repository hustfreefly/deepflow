"""
atomic_io 契约定义 — Pydantic 模型

契约笼子 Step 1: 先定义输入输出 Schema
"""

from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class AtomicWriteJsonInput(BaseModel):
    """atomic_write_json 的输入契约"""
    model_config = ConfigDict(extra="forbid")
    
    path: Path = Field(description="目标文件路径")
    data: Any = Field(description="要写入的数据（JSON 可序列化）")
    indent: int = Field(default=2, ge=0, le=8, description="JSON 缩进")
    ensure_ascii: bool = Field(default=False, description="是否转义非 ASCII 字符")


class AtomicWriteTextInput(BaseModel):
    """atomic_write_text 的输入契约"""
    model_config = ConfigDict(extra="forbid")
    
    path: Path = Field(description="目标文件路径")
    text: str = Field(description="要写入的文本内容")
    encoding: str = Field(default="utf-8", description="文本编码")


class SafeReadJsonInput(BaseModel):
    """safe_read_json 的输入契约"""
    model_config = ConfigDict(extra="forbid")
    
    path: Path = Field(description="文件路径")
    default: Optional[Any] = Field(default=None, description="文件不存在或解析失败时的默认值")


class AtomicWriteResult(BaseModel):
    """原子写操作的结果（用于日志/审计）"""
    model_config = ConfigDict(extra="forbid")
    
    success: bool = Field(description="是否成功")
    path: Path = Field(description="写入的文件路径")
    bytes_written: int = Field(ge=0, description="写入的字节数")
    error: Optional[str] = Field(default=None, description="错误信息（失败时）")


class SafeReadResult(BaseModel):
    """安全读取的结果（用于日志/审计）"""
    model_config = ConfigDict(extra="forbid")
    
    success: bool = Field(description="是否成功读取")
    data: Optional[Any] = Field(default=None, description="读取的数据")
    error: Optional[str] = Field(default=None, description="错误信息（失败时）")
    used_default: bool = Field(default=False, description="是否使用了默认值")
