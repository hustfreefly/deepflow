"""
测试：EventEmitter 基础功能。
"""

import time
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.deepflow.events.event_protocol import Event
from src.deepflow.events.emitter import EventEmitter


class TestEventEmitter:
    """EventEmitter 测试套件。"""
    
    def test_emit_immediate_return(self):
        """emit() 应立即返回（<1ms 延迟）。"""
        emitter = EventEmitter(maxsize=1000)
        
        event = Event(
            run_id="test-run",
            event_type="llm_call",
            event_seq=1,
            timestamp="2024-01-01T00:00:00Z",
        )
        
        # 测量 emit() 耗时
        start = time.perf_counter()
        result = emitter.emit(event)
        elapsed = time.perf_counter() - start
        
        # 应立即返回（<1ms）
        assert elapsed < 0.001, f"emit() took too long: {elapsed * 1000:.2f}ms"
        assert result is True, "emit() should return True"
    
    def test_emit_queue_full_warning(self, caplog):
        """队列满时应 warning 丢弃，不阻断。"""
        emitter = EventEmitter(maxsize=5)
        
        # 填满队列
        for i in range(5):
            event = Event(
                run_id="test",
                event_type="llm_call",
                event_seq=i,
                timestamp="2024-01-01T00:00:00Z",
            )
            emitter.emit(event)
        
        assert emitter.get_queue_size() == 5
        
        # 第 6 个事件应被丢弃
        event = Event(
            run_id="test",
            event_type="llm_call",
            event_seq=100,
            timestamp="2024-01-01T00:00:01Z",
        )
        
        # 应记录 warning
        with caplog.at_level("WARNING"):
            result = emitter.emit(event)
        
        assert result is False, ".emit() on full queue should return False"
        assert emitter.get_queue_size() == 5, "Queue size should not change"
        assert "Queue full" in caplog.text, "Should log queue full warning"
    
    def test_multithread_emit_safety(self):
        """多线程并发 emit() 应线程安全。"""
        emitter = EventEmitter(maxsize=10000)
        
        num_threads = 10
        events_per_thread = 100
        
        def emit_events(thread_id: int):
            for i in range(events_per_thread):
                event = Event(
                    run_id=f"thread-{thread_id}",
                    event_type="llm_call",
                    event_seq=i,
                    timestamp="2024-01-01T00:00:00Z",
                )
                emitter.emit(event)
        
        # 多线程并发发射
        threads = []
        for thread_id in range(num_threads):
            t = threading.Thread(target=emit_events, args=(thread_id,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # 验证统计
        stats = emitter.get_stats()
        assert stats["emit_count"] == num_threads * events_per_thread
        
        # 验证队列长度
        assert emitter.get_queue_size() == num_threads * events_per_thread
        
        # 验证所有事件可取出
        count = 0
        while not emitter._queue.empty():
            try:
                emitter._queue.get_nowait()
                count += 1
            except queue.Empty:
                break
        
        assert count == num_threads * events_per_thread
    
    def test_close_flush(self):
        """close() 应清空队列并返回剩余事件数。"""
        emitter = EventEmitter(maxsize=100)
        
        # 发射一些事件
        for i in range(10):
            event = Event(
                run_id="test",
                event_type="llm_call",
                event_seq=i,
                timestamp="2024-01-01T00:00:00Z",
            )
            emitter.emit(event)
        
        # 关闭并获取剩余事件（force=True 强制清空）
        remaining = emitter.close(timeout_s=1.0, force=True)
        assert emitter.is_closed is True
        assert remaining == 0  # force=True 应清空队列
    
    def test_emit_after_close(self, caplog):
        """已关闭的 emitter emit() 应返回 False。"""
        emitter = EventEmitter(maxsize=100)
        emitter.close()
        
        event = Event(
            run_id="test",
            event_type="llm_call",
            event_seq=1,
            timestamp="2024-01-01T00:00:00Z",
        )
        
        result = emitter.emit(event)
        
        assert result is False
        assert emitter.is_closed is True
    
    def test_try_emit_timeout(self):
        """try_emit() 超时回退应正常工作。"""
        # 小队列触发超时
        emitter = EventEmitter(maxsize=1)
        
        event1 = Event(
            run_id="test", event_type="llm_call", event_seq=1,
            timestamp="2024-01-01T00:00:00Z"
        )
        event2 = Event(
            run_id="test", event_type="llm_call", event_seq=2,
            timestamp="2024-01-01T00:00:01Z"
        )
        
        # 第一个成功
        assert emitter.try_emit(event1, timeout_ms=100) is True
        
        # 第二个应超时（队列满）
        result = emitter.try_emit(event2, timeout_ms=10)
        assert result is False
    
    def test_stats_collection(self):
        """统计信息应正确收集。"""
        emitter = EventEmitter(maxsize=10)
        
        # 发射 5 个成功
        for i in range(5):
            emitter.emit(Event(
                run_id="test", event_type="llm_call", event_seq=i,
                timestamp="2024-01-01T00:00:00Z"
            ))
        
        stats = emitter.get_stats()
        assert stats["emit_count"] == 5
        assert stats["drop_count"] == 0
        assert stats["queue_size"] == 5
    
    def test_event_protocol_compat(self):
        """Emit 应支持完整的 Event 协议。"""
        emitter = EventEmitter(maxsize=100)
        
        # 创建完整事件
        event = Event(
            run_id="full-test",
            event_type="llm_call",
            event_seq=999,
            timestamp="2024-06-22T20:14:00+08:00",
            worker_id="worker-001",
            phase_name="processing",
            duration_ms=123,
            tokens_in=100,
            tokens_out=50,
            cost=0.001,
            model="gpt-4",
            status="success",
            error_type=None,
            error_message=None,
            gate_name=None,
            gate_result=None,
            retry_count=None,
            collector_source="deepflow",
            metadata={"key": "value"},
        )
        
        result = emitter.emit(event)
        assert result is True
        
        retrieved = emitter._queue.get_nowait()
        assert retrieved.run_id == event.run_id
        assert retrieved.metadata == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
