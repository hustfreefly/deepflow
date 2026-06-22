# DeepFlow Event System
# Event Emitter and Writer Thread Core Architecture (WP-003)

"""
DeepFlow 事件系统模块。

提供：
- 事件协议定义（Event Protocol）
- Fire-and-forget 事件发射器（EventEmitter）
- 专用写入线程（WriterThread）
- 事件全序排序（Event Ordering）
- Watchdog 死亡检测与自动恢复（DF-001, DF-003）
"""

from .event_protocol import Event, EventType
from .emitter import EventEmitter
from .writer_thread import WriterThread
from .ordering import order_events

__all__ = [
    "Event",
    "EventType",
    "EventEmitter",
    "WriterThread",
    "order_events",
]
