"""
事件全序排序（DF-003）。

支持双 Collector（deepflow / diagnostics）的全序排序。
"""

from typing import List
from .event_protocol import Event


def order_events(events: List[Event]) -> List[Event]:
    """
    全序排序：timestamp → collector_source → sequence。
    
    排序规则（逐级比较）：
    1. timestamp（ISO 8601 字符串比较 → 时间序）
    2. collector_source（字典序：deepflow < diagnostics）
    3. event_seq（整数比较）
    
    Args:
        events: 事件列表（可能来自多个 source）
    
    Returns:
        排序后的事件列表（新列表）
    
    Examples:
        >>> e1 = Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z", collector_source="diagnostics")
        >>> e2 = Event("r1", "llm_call", 2, "2024-01-01T00:00:00Z", collector_source="deepflow")
        >>> ordered = order_events([e1, e2])
        >>> ordered[0].collector_source
        'deepflow'
        
        >>> e1 = Event("r1", "llm_call", 1, "2024-01-01T00:00:00Z")
        >>> e2 = Event("r1", "llm_call", 2, "2024-01-01T00:00:01Z")
        >>> ordered = order_events([e2, e1])
        >>> ordered[0].event_seq
        1
    """
    if not events:
        return []
    
    # 创建副本避免修改原列表
    sorted_events = list(events)
    
    # Python 的 sort 是稳定的，逐级比较
    sorted_events.sort(key=_event_sort_key)
    
    return sorted_events


def _event_sort_key(event: Event) -> tuple:
    """
    生成排序键（用于 sorted() / sort()）。
    
    规则：
    1. timestamp: 原样返回（ISO 8601 字符串比较等价于时间序）
    2. collector_source: None 视为 "deepflow"（最小值）
    3. event_seq: 原样返回
    """
    # collector_source: None → "deepflow"
    collector = event.collector_source
    if collector is None:
        collector = "deepflow"
    
    return (event.timestamp, collector, event.event_seq)


def verify_order(events: List[Event]) -> bool:
    """
    验证事件列表是否已排序（用于测试）。
    
    Args:
        events: 事件列表
    
    Returns:
        True: 已排序
        False: 未排序
    """
    for i in range(1, len(events)):
        prev = events[i - 1]
        curr = events[i]
        
        prev_key = _event_sort_key(prev)
        curr_key = _event_sort_key(curr)
        
        if prev_key > curr_key:
            return False
    
    return True
