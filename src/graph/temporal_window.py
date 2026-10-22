"""Temporal sliding window — manage time-windowed graph snapshots from span streams.

Implements a sliding time window over the span stream to generate discrete
graph snapshots for GNN training. Each window captures the service topology
state within a fixed time interval.

AC-2.4: Support sliding time window (default 5min) for graph snapshots.
"""

from __future__ import annotations

import time
from typing import Generator, List, Optional, Tuple

import numpy as np

from .service_graph import ServiceGraph, SpanRecord


class TemporalWindow:
    """Sliding time window manager for streaming span ingestion.

    Buffers spans within a time window, then produces a ServiceGraph snapshot
    when the window advances. Supports incremental processing via a callback
    or generator interface.

    Attributes:
        window_ms: Window duration in milliseconds (default 300000 = 5 min).
        slide_ms: Slide step in milliseconds (default equals window_ms for
            non-overlapping windows).
        max_nodes: Maximum expected nodes for pre-allocation hint.

    Example:
        >>> window = TemporalWindow(window_ms=300_000)
        >>> for span in span_stream:
        ...     window.ingest(span)
        ...     snapshot = window.try_advance()
        ...     if snapshot:
        ...         process(snapshot)
    """

    def __init__(
        self,
        window_ms: int = 300_000,  # 5 min
        slide_ms: Optional[int] = None,
        max_nodes: int = 1024,
    ) -> None:
        self.window_ms = window_ms
        self.slide_ms = slide_ms if slide_ms is not None else window_ms
        self.max_nodes = max_nodes

        # Current window state
        self._graph = ServiceGraph()
        self._window_id: int = 0
        self._window_start_ms: int = 0
        self._window_end_ms: int = 0
        self._last_advance_ms: int = 0
        self._initialized: bool = False
        self._span_count_total: int = 0

        # Performance tracking
        self._snapshot_times: List[float] = []

    @property
    def window_id(self) -> int:
        return self._window_id

    @property
    def span_count_total(self) -> int:
        return self._span_count_total

    @property
    def avg_snapshot_time_ms(self) -> float:
        if not self._snapshot_times:
            return 0.0
        return sum(self._snapshot_times) / len(self._snapshot_times) * 1000

    def ingest(self, span: SpanRecord) -> None:
        """Ingest a single span into the current window buffer.

        Args:
            span: SpanRecord from the Kafka stream.
        """
        self._span_count_total += 1

        if not self._initialized:
            self._initialize_window(span.timestamp_ms)
            self._initialized = True

        # If span is beyond current window, advance first
        if span.timestamp_ms >= self._window_end_ms:
            self._advance_window(span.timestamp_ms)

        self._graph.update_from_span(span)

    def ingest_batch(self, spans: List[SpanRecord]) -> None:
        """Ingest a batch of spans efficiently.

        Args:
            spans: List of SpanRecord objects.
        """
        for span in spans:
            self.ingest(span)

    def try_advance(self) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Check if the current window should advance and return a snapshot.

        Returns:
            Tuple of (node_features, edge_index, edge_attr) if window advanced,
            None otherwise.
        """
        if not self._initialized:
            return None
        current_ms = self._window_end_ms
        if current_ms - self._last_advance_ms >= self.slide_ms:
            self._last_advance_ms = current_ms
            return self._take_snapshot()
        return None

    def iter_snapshots(
        self, spans: List[SpanRecord]
    ) -> Generator[Tuple[np.ndarray, np.ndarray, np.ndarray], None, None]:
        """Process spans and yield snapshots as windows complete.

        Convenience generator that ingests all spans and yields snapshots
        for each completed window.

        Args:
            spans: List of SpanRecord objects sorted by timestamp.

        Yields:
            Tuple of (node_features, edge_index, edge_attr) per window.
        """
        for span in spans:
            self.ingest(span)
            snapshot = self.try_advance()
            if snapshot is not None:
                yield snapshot

    def get_current_snapshot(self) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Get the current graph state without advancing the window.

        Returns:
            Tuple of (node_features, edge_index, edge_attr) or None if empty.
        """
        if self._graph.node_count == 0:
            return None
        return self._graph.snapshot()

    def reset(self) -> None:
        """Reset all window state for a new stream."""
        self._graph.clear()
        self._window_id = 0
        self._window_start_ms = 0
        self._window_end_ms = 0
        self._last_advance_ms = 0
        self._initialized = False
        self._span_count_total = 0
        self._snapshot_times.clear()

    def _initialize_window(self, timestamp_ms: int) -> None:
        self._window_start_ms = timestamp_ms
        self._window_end_ms = timestamp_ms + self.window_ms
        self._last_advance_ms = timestamp_ms + self.window_ms

    def _advance_window(self, timestamp_ms: int) -> None:
        """Advance to the next window that contains the given timestamp."""
        # Calculate how many slide steps to advance
        while timestamp_ms >= self._window_end_ms:
            self._window_start_ms += self.slide_ms
            self._window_end_ms = self._window_start_ms + self.window_ms
            self._window_id += 1
            self._graph.clear()

    def _take_snapshot(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        start = time.perf_counter()
        result = self._graph.snapshot()
        elapsed = time.perf_counter() - start
        self._snapshot_times.append(elapsed)
        return result