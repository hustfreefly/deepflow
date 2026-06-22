"""
Dedicated Writer Thread。

专用写入线程，从队列批量消费事件并写入 SQLite。
支持 watchdog 死亡检测与自动恢复。
"""

import logging
import queue
import threading
import time
from typing import Optional, List, Dict, Any

from .emitter import EventEmitter
from .event_protocol import Event
from ..storage.sqlite_engine import SQLiteEngine

logger = logging.getLogger(__name__)


class WriterThread:
    """
    专用写入线程。
    
    特性：
    - 从 EventEmitter 队列批量消费事件
    - 批量 INSERT（默认 50 事件/批）
    - INSERT OR IGNORE 保证幂等
    - Watchdog 死亡检测（DF-001）：90 秒无写入 → 自动重启（最多 3 次）
    - Degraded Mode：SQLite 不可写时只 logging，不抛异常
    
    Args:
        engine: SQLite 引擎
        emitter: 事件发射器
        batch_size: 批量写入大小（默认 50）
        batch_interval_ms: 批量写入间隔（毫秒，默认 100）
        watchdog_interval_s: Watchdog 检测间隔（秒，默认 90）
        max_restarts: 最大自动重启次数（默认 3）
    """
    
    def __init__(
        self,
        engine: SQLiteEngine,
        emitter: EventEmitter,
        batch_size: int = 50,
        batch_interval_ms: int = 100,
        watchdog_interval_s: int = 90,
        max_restarts: int = 3,
    ):
        self._engine = engine
        self._db_path = engine.db_path  # 保存路径，writer 线程内创建自己的 engine
        self._writer_engine: Optional[SQLiteEngine] = None  # writer 线程专用 engine
        self._emitter = emitter
        self._batch_size = batch_size
        self._batch_interval_ms = batch_interval_ms
        self._watchdog_interval_s = watchdog_interval_s
        self._max_restarts = max_restarts
        
        # 线程控制
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None  # 线程 ID（用于避免 self-join）
        self._running = False
        self._start_event = threading.Event()
        
        # 统计与监控
        self._restart_count = 0
        self._last_write_time = 0.0
        self._last_write_time_lock = threading.Lock()
        self._total_written = 0
        self._total_dropped = 0
        
        #Degraded mode
        self._degraded = False
    
    def start(self) -> None:
        """启动 writer thread（daemon 线程）。"""
        if self._running:
            logger.warning("[WriterThread] Already running")
            return
        
        self._running = True
        self._last_write_time = time.time()
        
        self._thread = threading.Thread(
            target=self._run,
            name="DeepFlow-WriterThread",
            daemon=True,
        )
        self._thread_id = self._thread.ident  # 记录线程 ID
        self._thread.start()
        self._start_event.wait(timeout=5.0)  # 等待启动完成
        
        logger.info("[WriterThread] Started")
    
    def stop(self, timeout_s: float = 5.0) -> Dict[str, Any]:
        """
        停止 writer thread，flush 剩余事件。
        
        Args:
            timeout_s: 等待停止的最大时间（秒）
        
        Returns:
            停止统计（已处理事件数、剩余事件数等）
        """
        if not self._running:
            logger.warning("[WriterThread] Not running")
            return {"status": "not_running", "written": 0}
        
        self._running = False
        
        # 等待线程结束
        self._thread.join(timeout=timeout_s)
        
        remaining = self._emitter.get_queue_size()
        
        stats = {
            "status": "stopped",
            "written": self._total_written,
            "remaining": remaining,
            "dropped": self._total_dropped,
            "restart_count": self._restart_count,
        }
        
        if self._thread.is_alive():
            logger.warning("[WriterThread] Stop timeout, thread still alive")
            stats["status"] = "timeout"
        
        logger.info(f"[WriterThread] Stopped: {stats}")
        return stats
    
    def _run(self) -> None:
        """主循环：从队列消费 → 批量 INSERT → Watchdog 检查"""
        # 记录实际线程 ID（用于 watchdog self-join 检测）
        self._thread_id = threading.get_ident()
        
        # 在 writer 线程内创建独立的 engine，避免跨线程连接问题
        self._writer_engine = SQLiteEngine(self._db_path)
        self._writer_engine.apply_pragmas()
        
        self._start_event.set()
        
        logger.info("[WriterThread] Main loop started")
        
        batch: List[Event] = []
        last_flush_time = time.time()
        
        while self._running:
            try:
                # 1. 收集批量事件
                batch = self._collect_batch(batch)
                
                # 2. 检查是否需要 flush
                now = time.time()
                need_flush = False
                
                if len(batch) >= self._batch_size:
                    need_flush = True
                elif batch and (now - last_flush_time) * 1000 >= self._batch_interval_ms:
                    need_flush = True
                
                # 3. 批量写入
                if need_flush and batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush_time = now
                
                # 4. Watchdog 检查（每 10 圈检查一次，约 10*100ms = 1s）
                if int(now * 10) % 10 == 0:
                    self._watchdog_check()
                
                # 5. 短暂休眠（防止忙等）
                time.sleep(0.1)
                
            except Exception as e:
                # 外层异常捕获：记录错误但不中断循环
                logger.error(f"[WriterThread] Main loop error: {e}")
        
        # 退出前 drain 队列 + flush 所有剩余事件
        try:
            # 持续从队列取事件直到队列为空
            while True:
                try:
                    event = self._emitter._queue.get_nowait()
                    batch.append(event)
                except queue.Empty:
                    break
            if batch:
                flushed = self._flush_batch(batch)
                logger.info(f"[WriterThread] Final flush: {len(batch)} events (written: {flushed})")
        except Exception as e:
            logger.error(f"[WriterThread] Final flush error: {e}")
        
        logger.info("[WriterThread] Main loop exited")
    
    def _collect_batch(self, current_batch: List[Event]) -> List[Event]:
        """
        从队列收集批量事件。
        
        Args:
            current_batch: 当前批次
        
        Returns:
            更新后的批次
        """
        try:
            # 非阻塞获取（尝试从队列取事件）
            while len(current_batch) < self._batch_size:
                event = self._emitter._queue.get_nowait()
                current_batch.append(event)
        except queue.Empty:
            pass
        return current_batch
    
    def _flush_batch(self, events: List[Event]) -> int:
        """
        批量写入 SQLite。
        
        使用 INSERT OR IGNORE 保证幂等性。
        
        Args:
            events: 事件列表
        
        Returns:
            成功写入的事件数
        """
        if not events:
            return 0
        
        # 三层 try/except：内层 → 中层 → 外层
        
        try:
            # 中层：转换为字典
            try:
                records = [event.to_dict() for event in events]
            except Exception as e:
                logger.error(f"[WriterThread] Event to dict error: {e}")
                return 0
            
            # 内层：批量插入（使用 writer 线程专用 engine）
            try:
                inserted = self._writer_engine.insert_events(records)
                
                # 更新统计
                with self._last_write_time_lock:
                    self._last_write_time = time.time()
                
                self._total_written += inserted
                dropped = len(events) - inserted
                self._total_dropped += dropped
                
                logger.debug(
                    f"[WriterThread] Flushed {inserted} events "
                    f"(dropped: {dropped}, batch_size: {len(events)})"
                )
                return inserted
                
            except Exception as e:
                # 内层异常：降级到 degraded mode
                logger.error(f"[WriterThread] Batch insert error: {e}")
                self._degraded_mode()
                return 0
                
        except Exception as e:
            # 外层异常：记录并返回 0
            logger.error(f"[WriterThread] Flush batch fatal error: {e}")
            return 0
    
    def _watchdog_check(self) -> None:
        """
        DF-001: Watchdog 死亡检测。
        
        - 90 秒无新事件写入 → 判定死亡
        - 自动重启（最多 3 次）
        - 超过重启次数 → degraded mode
        """
        with self._last_write_time_lock:
            last_write = self._last_write_time
        
        now = time.time()
        idle_time = now - last_write
        
        if idle_time > self._watchdog_interval_s:
            logger.warning(
                f"[WriterThread] Watchdog: no write for {idle_time:.1f}s, "
                f"restarting (attempt {self._restart_count + 1}/{self._max_restarts})"
            )
            
            if self._restart_count >= self._max_restarts:
                logger.error(
                    f"[WriterThread] Watchdog: max restarts ({self._max_restarts}) exceeded, "
                    "entering degraded mode"
                )
                self._degraded_mode()
            else:
                self._restart_count += 1
                self._restart()
    
    def _restart(self) -> None:
        """重启 writer 的 SQLite 连接（保留 emitter 队列）。
        
        当从 writer 线程内部调用时（watchdog 触发），只重建 engine，
        不尝试停止/重启线程（不能 join 自己）。
        """
        logger.info("[WriterThread] Initiating restart (rebuild engine)")
        
        # 重建 writer engine（关闭旧连接，创建新连接）
        if self._writer_engine is not None:
            try:
                self._writer_engine.close()
            except Exception:
                pass
        
        self._writer_engine = SQLiteEngine(self._db_path)
        self._writer_engine.apply_pragmas()
        
        # 重置写入时间
        with self._last_write_time_lock:
            self._last_write_time = time.time()
        
        logger.info("[WriterThread] Engine rebuilt successfully")
        
        logger.info("[WriterThread] Restarted successfully")
    
    def _degraded_mode(self) -> None:
        """
        Degraded Mode：SQLite 不可写时的降级行为。
        
        - 只 logging.warning，不抛异常
        - 继续从 emitter 队列消费（但不写入）
        - 设置 _degraded 标志
        """
        self._degraded = True
        
        logger.warning(
            f"[WriterThread] DEGRADED MODE: SQLite不可写，事件将继续采集但不持久化\n"
            f"  - 已写入: {self._total_written}\n"
            f"  - 估计丢失: {self._total_dropped}\n"
            f"  - 队列剩余: {self._emitter.get_queue_size()}"
        )
        
        # 简单降级：清空队列（实际生产应尝试重连）
        try:
            while True:
                self._emitter._queue.get_nowait()
                self._total_dropped += 1
        except queue.Empty:
            pass
        
        logger.warning("[WriterThread] Degraded mode: queue flushed")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取写入统计。"""
        with self._last_write_time_lock:
            last_write = self._last_write_time
        
        idle_time = time.time() - last_write if last_write > 0 else 0
        
        return {
            "running": self._running,
            "degraded": self._degraded,
            "total_written": self._total_written,
            "total_dropped": self._total_dropped,
            "restart_count": self._restart_count,
            "idle_time_s": idle_time,
            "watchdog_threshold_s": self._watchdog_interval_s,
            "queue_size": self._emitter.get_queue_size(),
        }
