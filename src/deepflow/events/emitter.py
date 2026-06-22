"""
Event Emitter（Fire-and-Forget 模式）。

提供非阻塞事件发射，队列满时只记录 warning，不阻断调用方。
"""

import queue
import threading
import logging
import time
from typing import Optional

from .event_protocol import Event

logger = logging.getLogger(__name__)


class EventEmitter:
    """
    事件发射器（Fire-and-Forget）。
    
    特性：
    - emit() 立即返回（<1ms 延迟）
    - 队列满时 warning 丢弃，不阻断调用方
    - 线程安全
    - 支持关闭（stop()）后的新 emit()
    
    Args:
        maxsize: 队列最大长度（默认1000）
        name: 发射器名称（用于日志）
    """
    
    def __init__(self, maxsize: int = 1000, name: str = "emitter"):
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=maxsize)
        self._closed = False
        self._close_lock = threading.Lock()
        self._name = name
        self._emit_count = 0
        self._drop_count = 0
        self._count_lock = threading.Lock()
    
    def emit(self, event: Event) -> bool:
        """
        Fire-and-forget 事件发射。
        
        - 队列未满：立即入队，返回 True
        - 队列满：记录 warning，返回 False（不阻断调用方）
        - 已关闭：记录 debug，返回 False
        
        Args:
            event: 要发射的事件
        
        Returns:
            True: 事件成功入队
            False: 事件被丢弃（队列满或已关闭）
        """
        # 检查关闭状态（无锁快速路径）
        if self._closed:
            logger.debug(f"[{self._name}] Already closed, event dropped: {event.event_type}")
            return False
        
        try:
            self._queue.put_nowait(event)
            with self._count_lock:
                self._emit_count += 1
            return True
        except queue.Full:
            # 队列满，记录 warning 并丢弃
            with self._count_lock:
                self._drop_count += 1
                drop_count = self._drop_count
            
            logger.warning(
                f"[{self._name}] Queue full, event dropped "
                f"({drop_count} total drops): {event.event_type} "
                f"(run_id={event.run_id}, seq={event.event_seq})"
            )
            return False
    
    def emit_nowait(self, event: Event) -> bool:
        """
        非阻塞发射（别名 emit()）。
        
        保留此方法以便与可能的同步版本区分。
        """
        return self.emit(event)
    
    def try_emit(self, event: Event, timeout_ms: int = 10) -> bool:
        """
        尝试发射（超时回退）。
        
        Args:
            event: 要发射的事件
            timeout_ms: 等待空位的最大时间（毫秒）
        
        Returns:
            True: 事件成功入队
            False: 超时或已关闭
        """
        if self._closed:
            return False
        
        try:
            self._queue.put(event, block=True, timeout=timeout_ms / 1000.0)
            with self._count_lock:
                self._emit_count += 1
            return True
        except queue.Full:
            with self._count_lock:
                self._drop_count += 1
            logger.warning(
                f"[{self._name}] Emit timeout, event dropped: {event.event_type}"
            )
            return False
    
    def get_queue_size(self) -> int:
        """获取当前队列长度（不精确，仅用于监控）。"""
        return self._queue.qsize()
    
    def get_stats(self) -> dict:
        """获取统计信息。"""
        with self._count_lock:
            return {
                "emit_count": self._emit_count,
                "drop_count": self._drop_count,
                "queue_size": self._queue.qsize(),
            }
    
    def close(self, timeout_s: float = 1.0, force: bool = False) -> int:
        """
        关闭发射器。
        
        Args:
            timeout_s: 等待队列清空的最大时间（秒）
            force: 是否强制清空队列（不等待消费）
        
        Returns:
            剩余未处理的事件数（0 表示成功清空）
        """
        with self._close_lock:
            self._closed = True
        
        if force:
            # 强制清空队列
            try:
                while True:
                    self._queue.get_nowait()
            except queue.Empty:
                pass
            return 0
        
        # 等待队列清空
        start_time = time.time()
        remaining = 0
        while self._queue.qsize() > 0:
            if time.time() - start_time > timeout_s:
                remaining = self._queue.qsize()
                logger.warning(
                    f"[{self._name}] Close timeout, {remaining} events remaining"
                )
                return remaining
            time.sleep(0.01)
            remaining = self._queue.qsize()  # 更新剩余数量
        
        return 0
    
    @property
    def is_closed(self) -> bool:
        """检查是否已关闭。"""
        return self._closed
