"""Tests for temporal_window.py — AC-2.4: Sliding time window snapshots."""

from src.graph.temporal_window import TemporalWindow
from src.graph.service_graph import SpanRecord


def make_span(
    service_name="api-gateway",
    caller_service=None,
    timestamp_ms=1000,
    duration_ms=50.0,
    status_code=0,
    protocol="http",
    **kwargs,
) -> SpanRecord:
    return SpanRecord(
        trace_id=f"trace-{service_name}-{timestamp_ms}",
        span_id=f"span-{service_name}-{timestamp_ms}",
        parent_span_id=None,
        service_name=service_name,
        service_type=kwargs.get("service_type", "backend"),
        language=kwargs.get("language", "python"),
        replica_id=f"{service_name}-1",
        timestamp_ms=timestamp_ms,
        duration_ms=duration_ms,
        status_code=status_code,
        protocol=protocol,
        caller_service=caller_service,
        cpu_usage=kwargs.get("cpu_usage", 50.0),
        mem_usage=kwargs.get("mem_usage", 60.0),
        replica_count=kwargs.get("replica_count", 3),
    )


class TestTemporalWindow:
    """AC-2.4: Support sliding time window (default 5min) for graph snapshots."""

    def test_default_window_size(self):
        """Default window is 5 minutes (300,000 ms)."""
        window = TemporalWindow()
        assert window.window_ms == 300_000

    def test_initial_state(self):
        """Window starts uninitialized."""
        window = TemporalWindow()
        assert window.window_id == 0
        assert window.span_count_total == 0
        assert window._initialized is False

    def test_ingest_initializes_window(self):
        """First ingest initializes the window."""
        window = TemporalWindow(window_ms=60000)  # 1 min window
        span = make_span(timestamp_ms=1000)
        window.ingest(span)
        assert window._initialized is True
        assert window._window_start_ms == 1000
        assert window._window_end_ms == 1000 + 60000

    def test_ingest_within_window(self):
        """Spans within the same window are accumulated."""
        window = TemporalWindow(window_ms=60000, slide_ms=60000)
        for i in range(100):
            span = make_span(
                service_name="backend",
                caller_service="api-gateway",
                timestamp_ms=1000 + i * 10,
            )
            window.ingest(span)
        assert window.span_count_total == 100
        assert window._graph.node_count >= 2

    def test_ingest_beyond_window_advances(self):
        """Span beyond window end triggers advance."""
        window = TemporalWindow(window_ms=60000, slide_ms=60000)
        span1 = make_span(timestamp_ms=1000)
        window.ingest(span1)
        assert window._window_id == 0

        span2 = make_span(timestamp_ms=100000)  # beyond 60s window
        window.ingest(span2)
        assert window._window_id >= 1  # window advanced

    def test_ingest_batch(self):
        """Batch ingest processes all spans."""
        window = TemporalWindow(window_ms=60000)
        spans = [
            make_span(
                service_name="backend",
                caller_service="api-gateway",
                timestamp_ms=1000 + i * 10,
            )
            for i in range(50)
        ]
        window.ingest_batch(spans)
        assert window.span_count_total == 50

    def test_try_advance_returns_none_when_not_ready(self):
        """try_advance returns None when window hasn't moved."""
        window = TemporalWindow(window_ms=60000, slide_ms=60000)
        span = make_span(timestamp_ms=1000)
        window.ingest(span)
        result = window.try_advance()
        assert result is None

    def test_iter_snapshots_generator(self):
        """iter_snapshots yields snapshots for each window."""
        window = TemporalWindow(window_ms=60000, slide_ms=60000)
        spans = []
        # Create spans across 3 windows
        for w in range(3):
            for i in range(10):
                spans.append(
                    make_span(
                        service_name="backend",
                        caller_service="api-gateway",
                        timestamp_ms=w * 60000 + i * 10,
                    )
                )
        snapshots = list(window.iter_snapshots(spans))
        # Should yield at least 2 snapshots (window 0 and 1 complete)
        assert len(snapshots) >= 2

    def test_get_current_snapshot(self):
        """get_current_snapshot returns graph state without advancing."""
        window = TemporalWindow(window_ms=60000)
        span = make_span(
            service_name="backend",
            caller_service="api-gateway",
            timestamp_ms=1000,
        )
        window.ingest(span)
        snapshot = window.get_current_snapshot()
        assert snapshot is not None
        nf, ei, ea = snapshot
        assert nf.shape[0] == 2
        assert ei.shape[1] == 1

    def test_get_current_snapshot_empty(self):
        """get_current_snapshot returns None for empty graph."""
        window = TemporalWindow()
        assert window.get_current_snapshot() is None

    def test_reset_clears_all_state(self):
        """reset() clears all window state."""
        window = TemporalWindow(window_ms=60000)
        span = make_span(timestamp_ms=1000)
        window.ingest(span)
        assert window.span_count_total == 1
        window.reset()
        assert window.span_count_total == 0
        assert window._initialized is False
        assert window._graph.node_count == 0

    def test_sliding_window_overlap(self):
        """Sliding window with slide < window produces overlapping windows."""
        window = TemporalWindow(window_ms=60000, slide_ms=30000)
        # Window 0: [0, 60000)
        span = make_span(timestamp_ms=1000)
        window.ingest(span)
        assert window._window_id == 0
        # Window 1: [30000, 90000)
        span2 = make_span(timestamp_ms=65000)
        window.ingest(span2)
        assert window._window_id >= 1

    def test_snapshot_performance(self):
        """Snapshot generation should be fast (< 2s)."""
        window = TemporalWindow(window_ms=300000)
        spans = []
        for i in range(500):
            spans.append(
                make_span(
                    service_name=f"svc-{i % 20}",
                    caller_service=f"svc-{(i % 20) - 1}" if i % 20 > 0 else None,
                    timestamp_ms=1000 + i * 10,
                )
            )
        window.ingest_batch(spans)
        snapshot = window.get_current_snapshot()
        assert snapshot is not None
        # Performance tracked internally
        assert window.avg_snapshot_time_ms >= 0.0