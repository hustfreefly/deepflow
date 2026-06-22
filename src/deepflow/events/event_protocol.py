"""
事件协议定义。

定义了 DeepFlow 系统中 8 种事件类型及其数据结构。
"""

from dataclasses import dataclass, field
from typing import Optional, Literal

# 8 种事件类型
EventType = Literal[
    "phase_start", "phase_end",
    "worker_start", "worker_end",
    "gate_check", "retry",
    "error", "llm_call"
]


@dataclass
class Event:
    """
    DeepFlow 事件数据结构。
    
    Attributes:
        run_id: 运行ID，唯一标识一次执行流程
        event_type: 事件类型（8种之一）
        event_seq: 事件序号，同一run_id内递增
        timestamp: 时间戳，ISO 8601 格式
        worker_id: 工作者ID（可选）
        phase_name: 阶段名称（可选）
        duration_ms: 持续时间（毫秒，可选）
        tokens_in: 输入token数（可选）
        tokens_out: 输出token数（可选）
        cost: 成本（可选）
        model: 模型名称（可选）
        status: 状态（可选）
        error_type: 错误类型（可选）
        error_message: 错误消息（可选）
        gate_name: 网关名称（可选）
        gate_result: 网关检查结果（可选）
        retry_count: 重试次数（可选）
        collector_source: 采集来源（deepflow/diagnostics，可选）
        metadata: 元数据字典（可选，默认空dict）
    """
    
    # 必填字段
    run_id: str
    event_type: EventType
    event_seq: int
    timestamp: str  # ISO 8601
    
    # 可选字段
    worker_id: Optional[str] = None
    phase_name: Optional[str] = None
    duration_ms: Optional[int] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost: Optional[float] = None
    model: Optional[str] = None
    status: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    gate_name: Optional[str] = None
    gate_result: Optional[str] = None
    retry_count: Optional[int] = None
    collector_source: Optional[str] = None
    metadata: Optional[dict] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典（用于数据库插入）。"""
        return {
            "run_id": self.run_id,
            "event_type": self.event_type,
            "event_seq": self.event_seq,
            "timestamp": self.timestamp,
            "worker_id": self.worker_id,
            "phase_name": self.phase_name,
            "duration_ms": self.duration_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost": self.cost,
            "model": self.model,
            "status": self.status,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "gate_name": self.gate_name,
            "gate_result": self.gate_result,
            "retry_count": self.retry_count,
            "collector_source": self.collector_source,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """从字典创建 Event 实例。"""
        return cls(
            run_id=data["run_id"],
            event_type=data["event_type"],
            event_seq=data["event_seq"],
            timestamp=data["timestamp"],
            worker_id=data.get("worker_id"),
            phase_name=data.get("phase_name"),
            duration_ms=data.get("duration_ms"),
            tokens_in=data.get("tokens_in"),
            tokens_out=data.get("tokens_out"),
            cost=data.get("cost"),
            model=data.get("model"),
            status=data.get("status"),
            error_type=data.get("error_type"),
            error_message=data.get("error_message"),
            gate_name=data.get("gate_name"),
            gate_result=data.get("gate_result"),
            retry_count=data.get("retry_count"),
            collector_source=data.get("collector_source"),
            metadata=data.get("metadata", {}),
        )
    
    def __lt__(self, other: "Event") -> bool:
        """
        全序排序比较：timestamp → collector_source → event_seq。
        
        - timestamp: ISO 8601 字符串比较（字典序等价于时间序）
        - collector_source: deepflow < diagnostics（字典序）
        - event_seq: 整数比较
        """
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        if self.collector_source != other.collector_source:
            if self.collector_source is None:
                return True
            if other.collector_source is None:
                return False
            return self.collector_source < other.collector_source
        return self.event_seq < other.event_seq
