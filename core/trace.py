"""
DeepFlow Cross-Domain Trace — 全链路追踪

设计意图：三个域（Spec/Solution/Ship Pro）共享同一个 trace_id，
实现跨域请求追踪。trace_id 在 Spec Pro 生成，通过 blackboard 传递。

零外部依赖，线程安全。
"""
import uuid
import time
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class TraceContext:
    """全局追踪上下文（单例）"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._spans: List[Dict[str, Any]] = []
                    cls._instance._trace_id: Optional[str] = None
        return cls._instance

    def start_trace(self, trace_id: Optional[str] = None) -> str:
        """开始新追踪，生成或接受 trace_id"""
        self._trace_id = trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        self._spans = []
        self.span("trace_start", domain="platform")
        return self._trace_id

    @property
    def trace_id(self) -> Optional[str]:
        return self._trace_id

    def span(self, name: str, domain: str = "unknown", **metadata: Any) -> Dict[str, Any]:
        """记录一个 span（事件/阶段）"""
        span_data = {
            "trace_id": self._trace_id,
            "span_id": f"span-{uuid.uuid4().hex[:8]}",
            "name": name,
            "domain": domain,
            "timestamp": time.time(),
            "metadata": metadata,
        }
        with self._lock:
            self._spans.append(span_data)
        return span_data

    def end_trace(self) -> Dict[str, Any]:
        """结束追踪，返回汇总"""
        self.span("trace_end", domain="platform")
        return {
            "trace_id": self._trace_id,
            "total_spans": len(self._spans),
            "spans": self._spans,
            "duration": (self._spans[-1]["timestamp"] - self._spans[0]["timestamp"])
                        if len(self._spans) >= 2 else 0,
        }

    def save_to_blackboard(self, blackboard_dir: Path) -> Path:
        """持久化追踪数据到 blackboard"""
        trace_file = blackboard_dir / "trace.json"
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(self.end_trace(), f, indent=2, ensure_ascii=False)
        return trace_file


# 便捷 API（模块级函数，直接调用单例）
_ctx = TraceContext()


def start_trace(trace_id: Optional[str] = None) -> str:
    """开始新追踪，返回 trace_id"""
    return _ctx.start_trace(trace_id)


def get_trace_id() -> Optional[str]:
    """获取当前 trace_id"""
    return _ctx.trace_id


def span(name: str, domain: str = "unknown", **metadata: Any) -> Dict[str, Any]:
    """记录一个 span"""
    return _ctx.span(name, domain, **metadata)


def end_trace() -> Dict[str, Any]:
    """结束追踪，返回汇总"""
    return _ctx.end_trace()


def save_to_blackboard(blackboard_dir: Path) -> Path:
    """持久化追踪数据到 blackboard"""
    return _ctx.save_to_blackboard(blackboard_dir)
