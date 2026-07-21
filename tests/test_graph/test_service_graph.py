"""Tests for service_graph.py — AC-2.1: Build ServiceGraph from span stream."""

import numpy as np
import pytest

from src.graph.service_graph import (
    ServiceGraph,
    SpanRecord,
    Node,
    Edge,
)


def make_span(
    service_name="api-gateway",
    caller_service=None,
    service_type="api-gateway",
    language="python",
    duration_ms=50.0,
    status_code=0,
    protocol="http",
    timestamp_ms=1000,
    cpu_usage=45.0,
    mem_usage=60.0,
    replica_count=3,
    **kwargs,
) -> SpanRecord:
    return SpanRecord(
        trace_id=kwargs.get("trace_id", f"trace-{service_name}"),
        span_id=kwargs.get("span_id", f"span-{service_name}-{timestamp_ms}"),
        parent_span_id=kwargs.get("parent_span_id"),
        service_name=service_name,
        service_type=service_type,
        language=language,
        replica_id=kwargs.get("replica_id", f"{service_name}-1"),
        timestamp_ms=timestamp_ms,
        duration_ms=duration_ms,
        status_code=status_code,
        protocol=protocol,
        caller_service=caller_service,
        cpu_usage=cpu_usage,
        mem_usage=mem_usage,
        replica_count=replica_count,
    )


class TestServiceGraph:
    """AC-2.1: Build ServiceGraph from Kafka span stream."""

    def test_empty_graph(self):
        """An empty graph has zero nodes and edges."""
        graph = ServiceGraph()
        assert graph.node_count == 0
        assert graph.edge_count == 0
        assert graph.span_count == 0

    def test_single_span_creates_node(self):
        """Ingesting one span creates a single node."""
        graph = ServiceGraph()
        span = make_span(service_name="api-gateway")
        graph.update_from_span(span)
        assert graph.node_count == 1
        assert graph.edge_count == 0
        assert graph.span_count == 1

    def test_span_pair_creates_edge(self):
        """Two spans with caller relationship create an edge."""
        graph = ServiceGraph()
        # Backend calls database
        span = make_span(
            service_name="database",
            caller_service="backend",
            service_type="database",
            language="java",
        )
        graph.update_from_span(span)
        assert graph.node_count == 2  # backend + database
        assert graph.edge_count == 1
        assert graph.span_count == 1

    def test_multiple_calls_between_same_services(self):
        """Multiple calls between the same services aggregate on one edge."""
        graph = ServiceGraph()
        for i in range(10):
            span = make_span(
                service_name="backend",
                caller_service="api-gateway",
                service_type="backend",
                timestamp_ms=1000 + i,
            )
            graph.update_from_span(span)
        assert graph.edge_count == 1
        assert graph.span_count == 10

    def test_node_metrics_update(self):
        """Node metrics are updated incrementally from spans."""
        graph = ServiceGraph()
        for i in range(5):
            span = make_span(
                service_name="backend",
                cpu_usage=50.0 + i,
                mem_usage=70.0 + i,
                duration_ms=100.0 + i * 10,
                status_code=0 if i < 4 else 500,
                timestamp_ms=1000 + i,
            )
            graph.update_from_span(span)
        node = graph._nodes["backend"]
        assert node.request_count == 5
        assert node.cpu_usage == 54.0  # latest
        assert node.mem_usage == 74.0  # latest
        assert node.error_rate == pytest.approx(0.2)  # 1 error out of 5
        assert node.avg_response_time_ms > 0

    def test_edge_metrics_update(self):
        """Edge metrics are updated incrementally from spans."""
        graph = ServiceGraph()
        for i in range(100):
            span = make_span(
                service_name="backend",
                caller_service="api-gateway",
                duration_ms=10.0 + i,
                status_code=0 if i < 95 else 500,
                timestamp_ms=1000 + i,
            )
            graph.update_from_span(span)
        edge = graph._edges[("api-gateway", "backend")]
        assert edge.call_count == 100
        assert edge.success_rate == 0.95
        assert edge.error_count == 5
        assert edge.latency_p99_ms > 0
        assert edge.avg_latency_ms > 0

    def test_snapshot_returns_arrays(self):
        """snapshot() returns (node_features, edge_index, edge_attr)."""
        graph = ServiceGraph()
        for i in range(3):
            span = make_span(
                service_name="backend",
                caller_service="api-gateway",
                service_type="backend",
                timestamp_ms=1000 + i,
            )
            graph.update_from_span(span)
        nf, ei, ea = graph.snapshot()
        assert isinstance(nf, np.ndarray)
        assert isinstance(ei, np.ndarray)
        assert isinstance(ea, np.ndarray)
        assert nf.shape[0] == 2  # 2 nodes
        assert ei.shape[1] == 1  # 1 edge
        assert ea.shape[0] == 1

    def test_clear_resets_graph(self):
        """clear() resets all state."""
        graph = ServiceGraph()
        span = make_span(service_name="backend")
        graph.update_from_span(span)
        assert graph.node_count == 1
        graph.clear()
        assert graph.node_count == 0
        assert graph.edge_count == 0
        assert graph.span_count == 0

    def test_unknown_service_type_handled(self):
        """Unknown service types are handled gracefully."""
        graph = ServiceGraph()
        span = make_span(service_name="custom-svc", service_type="unknown-xyz")
        graph.update_from_span(span)
        nf, ei, ea = graph.snapshot()
        assert nf.shape[0] == 1
        # Should not crash

    def test_complex_topology(self):
        """Multiple services with complex call relationships."""
        graph = ServiceGraph()
        # api-gateway -> backend -> database
        # api-gateway -> auth -> database
        # backend -> cache
        spans = [
            make_span("backend", "api-gateway", "backend", timestamp_ms=1000),
            make_span("database", "backend", "database", timestamp_ms=1001),
            make_span("auth", "api-gateway", "auth", timestamp_ms=1002),
            make_span("database", "auth", "database", timestamp_ms=1003),
            make_span("cache", "backend", "cache", timestamp_ms=1004),
        ]
        for s in spans:
            graph.update_from_span(s)
        # Should have 4 nodes: api-gateway, backend, database, auth, cache
        assert graph.node_count == 5
        # 5 edges: ab, bd, aa, ad, bc
        assert graph.edge_count == 5
        nf, ei, ea = graph.snapshot()
        assert nf.shape[0] == 5
        assert ei.shape[1] == 5
        assert ea.shape[0] == 5


class TestNode:
    def test_node_defaults(self):
        node = Node(service_name="test")
        assert node.service_name == "test"
        assert node.cpu_usage == 0.0
        assert node.error_rate == 0.0


class TestEdge:
    def test_edge_defaults(self):
        edge = Edge(source="a", target="b")
        assert edge.source == "a"
        assert edge.target == "b"
        assert edge.success_rate == 1.0
        assert edge.call_count == 0


class TestSpanRecord:
    def test_span_creation(self):
        span = SpanRecord(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            service_name="svc",
            service_type="backend",
            language="python",
            replica_id="svc-1",
            timestamp_ms=1000,
            duration_ms=45.0,
            status_code=0,
            protocol="http",
            caller_service=None,
            cpu_usage=30.0,
            mem_usage=50.0,
            replica_count=2,
        )
        assert span.service_name == "svc"
        assert span.duration_ms == 45.0
        assert span.status_code == 0