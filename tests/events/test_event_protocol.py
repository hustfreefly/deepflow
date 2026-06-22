"""
Event 协议测试（EventProtocol）。
"""

import pytest

from src.deepflow.events.event_protocol import Event, EventType


class TestEventProtocol:
    """Event 协议测试套件。"""
    
    def test_event_creation(self):
        """Event 应正确创建。"""
        event = Event(
            run_id="test-run",
            event_type="llm_call",
            event_seq=1,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert event.run_id == "test-run"
        assert event.event_type == "llm_call"
        assert event.event_seq == 1
        assert event.timestamp == "2024-01-01T00:00:00Z"
        assert event.worker_id is None
        assert event.metadata == {}
    
    def test_event_to_dict(self):
        """Event.to_dict() 应返回完整字典。"""
        event = Event(
            run_id="test-run",
            event_type="llm_call",
            event_seq=1,
            timestamp="2024-01-01T00:00:00Z",
            worker_id="worker-001",
            metadata={"key": "value"},
        )
        data = event.to_dict()
        assert data["run_id"] == "test-run"
        assert data["worker_id"] == "worker-001"
        assert data["metadata"] == {"key": "value"}
    
    def test_event_from_dict(self):
        """Event.from_dict() 应正确创建实例。"""
        data = {
            "run_id": "test-run",
            "event_type": "llm_call",
            "event_seq": 1,
            "timestamp": "2024-01-01T00:00:00Z",
            "worker_id": "worker-001",
            "metadata": {"key": "value"},
        }
        event = Event.from_dict(data)
        assert event.run_id == "test-run"
        assert event.worker_id == "worker-001"
        assert event.metadata == {"key": "value"}
    
    def test_event_minimal(self):
        """最小化 Event（仅必填字段）应有效。"""
        event = Event(
            run_id="test",
            event_type="phase_start",
            event_seq=0,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert event is not None
        assert event.metadata == {}
    
    def test_event_all_fields(self):
        """完整 Event（所有字段）应有效。"""
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
            gate_name="gate-1",
            gate_result="pass",
            retry_count=2,
            collector_source="deepflow",
            metadata={"key": "value"},
        )
        
        assert event.worker_id == "worker-001"
        assert event.phase_name == "processing"
        assert event.duration_ms == 123
        assert event.model == "gpt-4"
        assert event.gate_name == "gate-1"
        assert event.gate_result == "pass"
        assert event.retry_count == 2
        assert event.collector_source == "deepflow"
        assert event.metadata == {"key": "value"}
    
    def test_event_metadata_default(self):
        """Event.metadata 默认应为空字典，不是可变默认参数。"""
        event1 = Event(
            run_id="test1", event_type="llm_call", event_seq=1,
            timestamp="2024-01-01T00:00:00Z"
        )
        event2 = Event(
            run_id="test2", event_type="llm_call", event_seq=2,
            timestamp="2024-01-01T00:00:00Z"
        )
        
        event1.metadata["key"] = "value1"
        
        # 确保 event2 不受影响
        assert event2.metadata == {}
    
    def test_event_sortable(self):
        """Event 应支持排序（定义 __lt__）。"""
        events = [
            Event("r1", "llm_call", 3, "2024-01-01T00:00:03Z"),
            Event("r1", "llm_call", 1, "2024-01-01T00:00:01Z"),
            Event("r1", "llm_call", 2, "2024-01-01T00:00:02Z"),
        ]
        
        sorted_events = sorted(events)
        assert [e.event_seq for e in sorted_events] == [1, 2, 3]
    
    def test_event_less_than(self):
        """Event.__lt__ 应按排序键比较。"""
        e1 = Event("r1", "llm_call", 1, "2024-01-01T00:00:01Z")
        e2 = Event("r1", "llm_call", 2, "2024-01-01T00:00:02Z")
        
        assert e1 < e2
        assert not (e2 < e1)
    
    def test_event_equal_not_less(self):
        """相同事件不应小于自身。"""
        e1 = Event("r1", "llm_call", 1, "2024-01-01T00:00:01Z")
        e2 = Event("r1", "llm_call", 1, "2024-01-01T00:00:01Z")
        
        assert not (e1 < e2)
        assert not (e2 < e1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
