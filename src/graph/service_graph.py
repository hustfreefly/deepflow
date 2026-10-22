"""Service graph data model — nodes, edges, and incremental update from Kafka span streams.

Core data structures for representing a microservice topology graph.
Supports incremental updates from streaming trace spans and time-windowed
snapshot generation.

AC-2.1: Build ServiceGraph(node_features, edge_index, edge_attr) from Kafka span stream.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class SpanRecord:
    """A single trace span from Kafka span stream.

    Attributes:
        trace_id: Distributed trace identifier.
        span_id: Unique span identifier.
        parent_span_id: Parent span ID (None for root spans).
        service_name: Name of the emitting microservice.
        service_type: Service category (api-gateway, backend, database, cache, queue).
        language: Programming language of the service.
        replica_id: Instance/replica identifier.
        timestamp_ms: Span start timestamp in milliseconds.
        duration_ms: Span duration in milliseconds.
        status_code: HTTP/gRPC status code (0=success).
        protocol: Communication protocol (http, grpc, tcp).
        caller_service: Upstream caller service name (None for entry spans).
        cpu_usage: CPU usage percentage at span time.
        mem_usage: Memory usage percentage at span time.
        replica_count: Total replicas of the service.
    """

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    service_name: str
    service_type: str
    language: str
    replica_id: str
    timestamp_ms: int
    duration_ms: float
    status_code: int
    protocol: str
    caller_service: Optional[str]
    cpu_usage: float
    mem_usage: float
    replica_count: int


@dataclass
class Node:
    """A node in the service topology graph, representing a microservice.

    Attributes:
        service_name: Unique service identifier.
        service_type: Service category string.
        language: Programming language.
        replica_count: Number of replicas at last observation.
        cpu_usage: Latest CPU usage (0-100).
        mem_usage: Latest memory usage (0-100).
        error_rate: Fraction of errored spans (0-1).
        avg_response_time_ms: Average response time in ms.
        request_count: Total requests seen in current window.
        last_seen_ms: Timestamp of last observed span.
    """

    service_name: str
    service_type: str = "unknown"
    language: str = "unknown"
    replica_count: int = 0
    cpu_usage: float = 0.0
    mem_usage: float = 0.0
    error_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    request_count: int = 0
    last_seen_ms: int = 0


@dataclass
class Edge:
    """A directed edge in the service topology graph, representing a call relationship.

    Attributes:
        source: Source service name (caller).
        target: Target service name (callee).
        call_count: Number of calls in current window.
        latency_p99_ms: P99 latency in milliseconds.
        avg_latency_ms: Average latency in milliseconds.
        protocol: Communication protocol.
        success_rate: Fraction of successful calls (0-1).
        error_count: Number of errored calls.
        last_seen_ms: Timestamp of last observed call.
    """

    source: str
    target: str
    call_count: int = 0
    latency_p99_ms: float = 0.0
    avg_latency_ms: float = 0.0
    protocol: str = "unknown"
    success_rate: float = 1.0
    error_count: int = 0
    last_seen_ms: int = 0


class ServiceGraph:
    """In-memory service topology graph with incremental span-based updates.

    Maintains a directed graph of microservices (nodes) and call relationships
    (edges). Supports incremental updates from streaming span records and
    snapshot extraction for downstream GNN processing.

    Use update_from_span() to ingest spans incrementally, then snapshot() to
    obtain current graph state for a time window.

    >>> graph = ServiceGraph()
    >>> span = SpanRecord(...)
    >>> graph.update_from_span(span)
    >>> node_features, edge_index, edge_attr = graph.snapshot()
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[Tuple[str, str], Edge] = {}
        self._span_count: int = 0
        self._window_start_ms: int = 0
        self._window_end_ms: int = 0
        # Per-node latency accumulators
        self._node_latency_sum: Dict[str, float] = {}
        # Per-node success accumulators
        self._node_success_count: Dict[str, int] = {}
        # Per-edge latency accumulators for p99 (sorted list)
        self._edge_latencies: Dict[Tuple[str, str], List[float]] = {}

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    @property
    def span_count(self) -> int:
        return self._span_count

    def update_from_span(self, span: SpanRecord) -> None:
        """Ingest a single span record and incrementally update the graph.

        Updates node metrics and edge statistics atomically. Thread-safe
        for single-threaded use; multi-thread support requires external
        locking.

        Args:
            span: A SpanRecord from the Kafka span stream.
        """
        self._span_count += 1

        # Update or create the target node
        node = self._get_or_create_node(span.service_name, span)
        self._update_node_from_span(node, span)

        # Update the edge if this span has a caller
        if span.caller_service:
            self._get_or_create_node(span.caller_service, span)
            edge = self._get_or_create_edge(
                span.caller_service, span.service_name, span
            )
            self._update_edge_from_span(edge, span)

    def snapshot(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the current graph state as (node_features, edge_index, edge_attr).

        Returns:
            Tuple of:
                node_features: (N, D_node) float32 array of node features.
                edge_index: (2, E) int64 array of edge connectivity.
                edge_attr: (E, D_edge) float32 array of edge features.
        """
        from .feature_extractor import FeatureExtractor

        extractor = FeatureExtractor()
        node_list = list(self._nodes.values())
        edge_list = list(self._edges.values())

        node_features = extractor.extract_node_features(node_list)
        edge_index, edge_attr = extractor.extract_edge_features(node_list, edge_list)

        return node_features, edge_index, edge_attr

    def clear(self) -> None:
        """Reset all graph state for a new time window."""
        self._nodes.clear()
        self._edges.clear()
        self._span_count = 0
        self._node_latency_sum.clear()
        self._node_success_count.clear()
        self._edge_latencies.clear()

    def _get_or_create_node(self, service_name: str, span: SpanRecord) -> Node:
        if service_name not in self._nodes:
            self._nodes[service_name] = Node(
                service_name=service_name,
                service_type=span.service_type
                if span.service_name == service_name
                else "unknown",
                language=span.language
                if span.service_name == service_name
                else "unknown",
                replica_count=span.replica_count
                if span.service_name == service_name
                else 0,
            )
        return self._nodes[service_name]

    def _update_node_from_span(self, node: Node, span: SpanRecord) -> None:
        # Update latest metrics
        node.cpu_usage = span.cpu_usage
        node.mem_usage = span.mem_usage
        node.replica_count = span.replica_count
        node.last_seen_ms = span.timestamp_ms
        node.request_count += 1

        # Accumulate for average response time
        if node.service_name not in self._node_latency_sum:
            self._node_latency_sum[node.service_name] = 0.0
        self._node_latency_sum[node.service_name] += span.duration_ms

        node.avg_response_time_ms = (
            self._node_latency_sum[node.service_name] / node.request_count
        )

        # Track success/error
        if node.service_name not in self._node_success_count:
            self._node_success_count[node.service_name] = 0
        if span.status_code == 0:
            self._node_success_count[node.service_name] += 1
        node.error_rate = 1.0 - (
            self._node_success_count[node.service_name] / node.request_count
        )

    def _get_or_create_edge(self, source: str, target: str, span: SpanRecord) -> Edge:
        key = (source, target)
        if key not in self._edges:
            self._edges[key] = Edge(
                source=source,
                target=target,
                protocol=span.protocol,
            )
        return self._edges[key]

    def _update_edge_from_span(self, edge: Edge, span: SpanRecord) -> None:
        edge.call_count += 1
        edge.last_seen_ms = span.timestamp_ms
        edge.protocol = span.protocol  # Latest protocol

        # Track latency for p99
        key = (edge.source, edge.target)
        if key not in self._edge_latencies:
            self._edge_latencies[key] = []
        self._edge_latencies[key].append(span.duration_ms)

        latencies = self._edge_latencies[key]
        edge.avg_latency_ms = sum(latencies) / len(latencies)
        edge.latency_p99_ms = (
            float(np.percentile(latencies, 99))
            if len(latencies) >= 100
            else max(latencies)
        )

        # Track success rate
        edge.error_count += 1 if span.status_code != 0 else 0
        edge.success_rate = (edge.call_count - edge.error_count) / edge.call_count

    def _calculate_node_id(self, service_name: str) -> str:
        return hashlib.md5(service_name.encode()).hexdigest()[:16]
