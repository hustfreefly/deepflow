"""Tests for feature_extractor.py — AC-2.2 and AC-2.3."""

import numpy as np

from src.graph.feature_extractor import (
    FeatureExtractor,
    NODE_FEATURE_DIM,
    EDGE_FEATURE_DIM,
    SERVICE_TYPES,
    PROTOCOLS,
    LANGUAGE_MAP,
)
from src.graph.service_graph import Node, Edge


class TestFeatureExtractorNodeFeatures:
    """AC-2.2: Node feature dimension ≥ 8."""

    def test_node_feature_dimension(self):
        """Node features must have at least 8 dimensions."""
        assert NODE_FEATURE_DIM >= 8

    def test_empty_nodes(self):
        """Empty node list returns empty array."""
        extractor = FeatureExtractor()
        result = extractor.extract_node_features([])
        assert result.shape == (0, NODE_FEATURE_DIM)
        assert result.dtype == np.float32

    def test_single_node_basic(self):
        """Single node produces correct feature shape and values."""
        extractor = FeatureExtractor()
        node = Node(
            service_name="api-gateway",
            service_type="api-gateway",
            language="python",
            replica_count=3,
            cpu_usage=45.0,
            mem_usage=60.0,
            error_rate=0.01,
            avg_response_time_ms=50.0,
            request_count=100,
        )
        result = extractor.extract_node_features([node])
        assert result.shape == (1, NODE_FEATURE_DIM)
        # All values should be in [0, 1]
        assert np.all(result >= 0.0)
        assert np.all(result <= 1.0)

    def test_service_type_one_hot(self):
        """Service type is one-hot encoded."""
        extractor = FeatureExtractor()
        node = Node(service_name="svc", service_type="backend")
        result = extractor.extract_node_features([node])
        # backend maps to index 1 in SERVICE_TYPES
        assert result[0, 1] == 1.0
        # Other service type columns should be 0
        assert result[0, 0] == 0.0  # api-gateway
        assert result[0, 2] == 0.0  # database

    def test_unknown_service_type_falls_back(self):
        """Unknown service type maps to 'other' index."""
        extractor = FeatureExtractor()
        node = Node(service_name="svc", service_type="crazy-new-type")
        result = extractor.extract_node_features([node])
        # 'other' is the last index
        other_idx = len(SERVICE_TYPES) - 1
        assert result[0, other_idx] == 1.0

    def test_cpu_usage_normalized(self):
        """CPU usage is normalized to [0, 1]."""
        extractor = FeatureExtractor()
        node = Node(service_name="svc", cpu_usage=75.0)
        result = extractor.extract_node_features([node])
        # Column 11 is cpu_usage
        assert 0.7 < result[0, 11] < 0.8

    def test_mem_usage_normalized(self):
        """Memory usage is normalized to [0, 1]."""
        extractor = FeatureExtractor()
        node = Node(service_name="svc", mem_usage=100.0)
        result = extractor.extract_node_features([node])
        # Column 12 is mem_usage
        assert result[0, 12] == 1.0

    def test_error_rate_passthrough(self):
        """Error rate is passed through directly (already 0-1)."""
        extractor = FeatureExtractor()
        node = Node(service_name="svc", error_rate=0.05)
        result = extractor.extract_node_features([node])
        assert result[0, 13] == 0.05

    def test_language_encoding(self):
        """Language is numerically encoded."""
        extractor = FeatureExtractor()
        node = Node(service_name="svc", language="go")
        result = extractor.extract_node_features([node])
        # go maps to index 2
        assert result[0, 9] > 0.0

    def test_multiple_nodes(self):
        """Multiple nodes produce correct output shape."""
        extractor = FeatureExtractor()
        nodes = [
            Node(service_name=f"svc-{i}", service_type="backend")
            for i in range(10)
        ]
        result = extractor.extract_node_features(nodes)
        assert result.shape == (10, NODE_FEATURE_DIM)

    def test_all_features_in_range(self):
        """All node features are in [0, 1] range."""
        extractor = FeatureExtractor()
        nodes = [
            Node(
                service_name="api-gateway",
                service_type="api-gateway",
                language="python",
                replica_count=3,
                cpu_usage=45.0,
                mem_usage=60.0,
                error_rate=0.01,
                avg_response_time_ms=50.0,
                request_count=100,
            ),
            Node(
                service_name="backend",
                service_type="backend",
                language="java",
                replica_count=5,
                cpu_usage=70.0,
                mem_usage=80.0,
                error_rate=0.02,
                avg_response_time_ms=200.0,
                request_count=500,
            ),
            Node(
                service_name="database",
                service_type="database",
                language="go",
                replica_count=2,
                cpu_usage=90.0,
                mem_usage=95.0,
                error_rate=0.0,
                avg_response_time_ms=10.0,
                request_count=1000,
            ),
        ]
        result = extractor.extract_node_features(nodes)
        assert result.shape == (3, NODE_FEATURE_DIM)
        assert np.all(result >= 0.0)
        assert np.all(result <= 1.0)


class TestFeatureExtractorEdgeFeatures:
    """AC-2.3: Edge feature dimension ≥ 5."""

    def test_edge_feature_dimension(self):
        """Edge features must have at least 5 dimensions."""
        assert EDGE_FEATURE_DIM >= 5

    def test_empty_edges(self):
        """Empty edge list returns empty arrays."""
        extractor = FeatureExtractor()
        node_list = [Node(service_name="a"), Node(service_name="b")]
        ei, ea = extractor.extract_edge_features(node_list, [])
        assert ei.shape == (2, 0)
        assert ea.shape == (0, EDGE_FEATURE_DIM)

    def test_single_edge_basic(self):
        """Single edge produces correct feature shape."""
        extractor = FeatureExtractor()
        node_list = [
            Node(service_name="api-gateway"),
            Node(service_name="backend"),
        ]
        edge = Edge(
            source="api-gateway",
            target="backend",
            call_count=100,
            latency_p99_ms=200.0,
            avg_latency_ms=150.0,
            protocol="http",
            success_rate=0.99,
            error_count=1,
        )
        ei, ea = extractor.extract_edge_features(node_list, [edge])
        assert ei.shape == (2, 1)
        assert ea.shape == (1, EDGE_FEATURE_DIM)
        assert ei[0, 0] == 0  # api-gateway index
        assert ei[1, 0] == 1  # backend index

    def test_protocol_one_hot(self):
        """Protocol is one-hot encoded."""
        extractor = FeatureExtractor()
        node_list = [
            Node(service_name="a"),
            Node(service_name="b"),
        ]
        edge = Edge(source="a", target="b", protocol="grpc")
        ei, ea = extractor.extract_edge_features(node_list, [edge])
        # grpc maps to index 1 in PROTOCOLS
        assert ea[0, 1] == 1.0
        assert ea[0, 0] == 0.0  # http

    def test_success_rate_in_range(self):
        """Success rate is in [0, 1]."""
        extractor = FeatureExtractor()
        node_list = [
            Node(service_name="a"),
            Node(service_name="b"),
        ]
        edge = Edge(source="a", target="b", success_rate=0.95)
        ei, ea = extractor.extract_edge_features(node_list, [edge])
        assert ea[0, 9] == 0.95

    def test_multiple_edges(self):
        """Multiple edges produce correct output shape."""
        extractor = FeatureExtractor()
        node_list = [
            Node(service_name="api-gateway"),
            Node(service_name="backend"),
            Node(service_name="database"),
            Node(service_name="cache"),
        ]
        edges = [
            Edge(source="api-gateway", target="backend", protocol="http"),
            Edge(source="backend", target="database", protocol="grpc"),
            Edge(source="backend", target="cache", protocol="tcp"),
        ]
        ei, ea = extractor.extract_edge_features(node_list, edges)
        assert ei.shape == (2, 3)
        assert ea.shape == (3, EDGE_FEATURE_DIM)

    def test_all_edge_features_in_range(self):
        """All edge features are in [0, 1] range."""
        extractor = FeatureExtractor()
        node_list = [
            Node(service_name="a"),
            Node(service_name="b"),
        ]
        edge = Edge(
            source="a",
            target="b",
            call_count=500,
            latency_p99_ms=300.0,
            avg_latency_ms=200.0,
            protocol="grpc",
            success_rate=0.98,
            error_count=10,
        )
        ei, ea = extractor.extract_edge_features(node_list, [edge])
        assert ea.shape == (1, EDGE_FEATURE_DIM)
        assert np.all(ea >= 0.0)
        assert np.all(ea <= 1.0)


class TestLogNormalize:
    def test_log_normalize_zero_max(self):
        """Log normalize returns 0 when max is 0."""
        result = FeatureExtractor._log_normalize(5.0, 0.0)
        assert result == 0.0

    def test_log_normalize_equal(self):
        """Log normalize returns 1.0 when value equals max."""
        result = FeatureExtractor._log_normalize(100.0, 100.0)
        assert np.isclose(result, 1.0)

    def test_log_normalize_general(self):
        """Log normalize returns value in [0, 1]."""
        result = FeatureExtractor._log_normalize(50.0, 100.0)
        assert 0.0 < result < 1.0

    def test_log_normalize_zero_value(self):
        """Log normalize of 0 returns 0."""
        result = FeatureExtractor._log_normalize(0.0, 100.0)
        assert result == 0.0


class TestConstants:
    def test_service_types_count(self):
        assert len(SERVICE_TYPES) == 9

    def test_protocols_count(self):
        assert len(PROTOCOLS) == 6

    def test_language_map(self):
        assert "python" in LANGUAGE_MAP
        assert "go" in LANGUAGE_MAP
        assert LANGUAGE_MAP["unknown"] == 10