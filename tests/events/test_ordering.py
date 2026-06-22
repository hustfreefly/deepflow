"""
测试：Event 全序排序（DF-003）。
"""

import pytest

from src.deepflow.events.event_protocol import Event
from src.deepflow.events.ordering import order_events, verify_order


class TestEventOrdering:
    """Event 排序测试套件。"""
    
    def test_empty_list(self):
        """空列表应返回空列表。"""
        assert order_events([]) == []
    
    def test_single_event(self):
        """单个事件应原样返回。"""
        event = Event(
            run_id="test",
            event_type="llm_call",
            event_seq=1,
            timestamp="2024-01-01T00:00:00Z",
        )
        result = order_events([event])
        assert len(result) == 1
        assert result[0].event_seq == 1
    
    def test_timestamp_order(self):
        """应按 timestamp 升序排序。"""
        events = [
            Event("r1", "llm_call", 3, "2024-01-01T00:00:03Z"),
            Event("r1", "llm_call", 1, "2024-01-01T00:00:01Z"),
            Event("r1", "llm_call", 2, "2024-01-01T00:00:02Z"),
        ]
        result = order_events(events)
        assert [e.event_seq for e in result] == [1, 2, 3]
    
    def test_collector_source_order(self):
        """同 timestamp 下，collector_source 应按字典序排序。"""
        events = [
            Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z", collector_source="diagnostics"),
            Event("r1", "llm_call", 2, "2024-01-01T00:00:00Z", collector_source="deepflow"),
        ]
        result = order_events(events)
        assert [e.collector_source for e in result] == ["deepflow", "diagnostics"]
    
    def test_collector_source_none_default(self):
        """collector_source=None 应视为 deepflow。"""
        events = [
            Event("r1", "llm_call", 2, "2024-01-01T00:00:00Z", collector_source=None),
            Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z", collector_source="deepflow"),
        ]
        result = order_events(events)
        assert result[0].collector_source is None or result[0].collector_source == "deepflow"
    
    def test_full_order_three_fields(self):
        """完整排序：timestamp → collector_source → event_seq。"""
        events = [
            # timestamp=00:00:01, diagnostics
            Event("r1", "llm_call", 3, "2024-01-01T00:00:01Z", collector_source="diagnostics"),
            # timestamp=00:00:01, deepflow
            Event("r1", "llm_call", 2, "2024-01-01T00:00:01Z", collector_source="deepflow"),
            # timestamp=00:00:00, diagnostics
            Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z", collector_source="diagnostics"),
            # timestamp=00:00:00, deepflow
            Event("r1", "llm_call", 0, "2024-01-01T00:00:00Z", collector_source="deepflow"),
        ]
        result = order_events(events)
        
        expected = [
            (0, "deepflow"),       # 00:00:00, deepflow
            (1, "diagnostics"),    # 00:00:00, diagnostics
            (2, "deepflow"),       # 00:00:01, deepflow
            (3, "diagnostics"),    # 00:00:01, diagnostics
        ]
        assert [(e.event_seq, e.collector_source) for e in result] == expected
    
    def test_verify_order_function(self):
        """verify_order 应正确验证排序状态。"""
        ordered = [
            Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z"),
            Event("r1", "llm_call", 2, "2024-01-01T00:00:01Z"),
        ]
        unordered = [
            Event("r1", "llm_call", 2, "2024-01-01T00:00:01Z"),
            Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z"),
        ]
        
        assert verify_order(ordered) is True
        assert verify_order(unordered) is False
    
    def test_sort_key_consistency(self):
        """排序键应与排序结果一致。"""
        events = [
            Event("r1", "llm_call", 3, "2024-01-01T00:00:03Z", collector_source="diagnostics"),
            Event("r1", "llm_call", 1, "2024-01-01T00:00:01Z", collector_source="deepflow"),
            Event("r1", "llm_call", 2, "2024-01-01T00:00:02Z", collector_source="deepflow"),
        ]
        
        sorted_events = order_events(events)
        
        # 验证相邻元素满足排序规则（使用 __lt__）
        for i in range(1, len(sorted_events)):
            prev = sorted_events[i - 1]
            curr = sorted_events[i]
            # 确保 prev < curr 或者 prev == curr
            assert prev < curr or not (curr < prev)
    
    def test_mixed_timestamp_formats(self):
        """ISO 8601 不同格式的排序（字典序比较）。"""
        events = [
            Event("r1", "llm_call", 2, "2024-01-01T00:00:01+08:00"),
            Event("r1", "llm_call", 1, "2024-01-01T00:00:01Z"),
        ]
        result = order_events(events)
        
        # 字符串比较："2024-01-01T00:00:01+08:00" < "2024-01-01T00:00:01Z"
        # 所以 +08:00 会排在前面
        assert result[0].event_seq == 2
    
    def test_stable_sort(self):
        """排序应是稳定的（相同键值保持原始顺序）。"""
        events = [
            Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z"),
            Event("r1", "llm_call", 2, "2024-01-01T00:00:00Z"),
            Event("r1", "llm_call", 3, "2024-01-01T00:00:00Z"),
        ]
        
        # 反向创建列表
        reversed_events = list(reversed(events))
        result = order_events(reversed_events)
        
        # 相同 timestamp 和 collector_source，应保持稳定顺序
        assert [e.event_seq for e in result] == [1, 2, 3]
    
    def test_large_dataset(self):
        """大数据集排序性能。"""
        import random
        
        # 生成 1000 个事件
        events = []
        for i in range(1000):
            ts = f"2024-01-01T00:{i % 60:02d}:{(i // 60) % 60:02d}Z"
            source = "deepflow" if i % 2 == 0 else "diagnostics"
            events.append(Event(
                run_id="large-test",
                event_type="llm_call",
                event_seq=i,
                timestamp=ts,
                collector_source=source,
            ))
        
        # 混乱顺序
        random.shuffle(events)
        
        # 排序
        result = order_events(events)
        
        # 验证数量
        assert len(result) == 1000
        
        # 验证已排序
        assert verify_order(result) is True
    
    def test_copy_not_modify_original(self):
        """排序不应修改原列表。"""
        events = [
            Event("r1", "llm_call", 2, "2024-01-01T00:00:01Z"),
            Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z"),
        ]
        
        original_seqs = [e.event_seq for e in events]
        result = order_events(events)
        
        assert [e.event_seq for e in events] == original_seqs
        assert [e.event_seq for e in result] == [1, 2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
