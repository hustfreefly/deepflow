"""
ProcessManager 契约定义

契约笼方法：Pydantic models → JSON Schema → 代码实现
所有数据结构必须通过契约验证，确保稳健性。
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from pathlib import Path
import time


# ========== 1. WaitResult 契约 ==========

class WaitResultContract(BaseModel):
    """wait_for 返回结果契约"""
    found: bool = Field(..., description="文件是否找到")
    path: str = Field(..., description="文件路径（相对 session_dir）")
    elapsed: float = Field(..., ge=0, description="等待时间（秒）")
    timeout: int = Field(..., ge=0, description="超时时间（秒）")
    file_size: Optional[int] = Field(None, ge=0, description="文件大小（字节）")
    file_mtime: Optional[float] = Field(None, description="文件修改时间")
    exists_but_empty: bool = Field(False, description="文件存在但为空")
    exists_but_invalid_json: bool = Field(False, description="文件存在但 JSON 无效")
    
    @field_validator('elapsed')
    @classmethod
    def round_elapsed(cls, v):
        return round(v, 1)


# ========== 2. ModuleWaitResult 契约 ==========

class ModuleWaitResultContract(BaseModel):
    """wait_for_module 返回结果契约"""
    found: bool = Field(..., description="模块是否完成")
    run_id: Optional[str] = Field(None, description="运行 ID")
    attempt: int = Field(0, ge=1, description="尝试次数")
    elapsed: float = Field(0, ge=0, description="等待时间（秒）")
    reason: str = Field("", description="失败原因：'' | 'timeout' | 'stall'")
    files: dict = Field(default_factory=dict, description="文件详情")
    
    @field_validator('elapsed')
    @classmethod
    def round_elapsed(cls, v):
        return round(v, 1)
    
    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v):
        allowed = {"", "timeout", "stall"}
        if v not in allowed:
            raise ValueError(f"reason must be one of {allowed}, got '{v}'")
        return v


# ========== 3. RunRecord 契约（单源状态）==========

class RunRecordContract(BaseModel):
    """运行记录契约（单源状态）"""
    module: str = Field(..., description="模块名")
    run_id: str = Field(..., description="运行 ID")
    attempt: int = Field(..., ge=1, description="尝试次数")
    status: Literal["running", "completed", "failed", "stalled"] = Field(
        ..., description="状态"
    )
    started_at: float = Field(..., description="开始时间")
    last_heartbeat: float = Field(..., description="最后心跳时间")
    completed_at: Optional[float] = Field(None, description="完成时间")
    output_files: dict = Field(default_factory=dict, description="输出文件注册")
    previous: Optional[dict] = Field(None, description="前次运行信息")
    final_status: Optional[str] = Field(None, description="最终状态（用于历史记录）")


# ========== 4. 原子写契约 ==========

class AtomicWriteContract(BaseModel):
    """原子写操作契约"""
    target_path: str = Field(..., description="目标文件路径")
    content: str = Field(..., description="文件内容")
    encoding: str = Field("utf-8", description="文件编码")
    
    @field_validator('target_path')
    @classmethod
    def validate_path(cls, v):
        if not v:
            raise ValueError("target_path cannot be empty")
        if '..' in v:
            raise ValueError("target_path cannot contain '..'")
        return v


# ========== 5. Watchdog 告警契约 ==========

class WatchdogAlertContract(BaseModel):
    """Watchdog 告警契约"""
    alert_type: Literal["stall", "timeout", "failure"] = Field(
        ..., description="告警类型"
    )
    session_id: str = Field(..., description="Session ID")
    module: Optional[str] = Field(None, description="模块名")
    run_id: Optional[str] = Field(None, description="运行 ID")
    message: str = Field(..., description="告警消息")
    timestamp: float = Field(default_factory=time.time, description="告警时间")
    details: dict = Field(default_factory=dict, description="详细信息")


# ========== 6. 文件验证契约 ==========

class FileValidationContract(BaseModel):
    """文件验证契约"""
    path: str = Field(..., description="文件路径")
    min_size: int = Field(0, ge=0, description="最小文件大小")
    validate_json: bool = Field(False, description="是否验证 JSON")
    validate_schema: Optional[str] = Field(None, description="JSON Schema 名称")
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, v):
        if not v:
            raise ValueError("path cannot be empty")
        return v


# ========== 7. Stall 检测契约 ==========

class StallDetectionContract(BaseModel):
    """Stall 检测契约"""
    module: str = Field(..., description="模块名")
    heartbeat_threshold: int = Field(1800, ge=60, description="心跳超时阈值（秒）")
    file_mtime_threshold: int = Field(900, ge=60, description="文件 mtime 超时阈值（秒）")
    expected_files: list[str] = Field(default_factory=list, description="期望文件列表")


# ========== 8. 超时告警契约 ==========

class TimeoutAlertContract(BaseModel):
    """超时告警契约"""
    path: str = Field(..., description="等待的文件路径")
    elapsed: float = Field(..., ge=0, description="等待时间（秒）")
    timeout: int = Field(..., ge=0, description="超时时间（秒）")
    session_id: str = Field(..., description="Session ID")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
