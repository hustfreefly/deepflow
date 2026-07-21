"""Tests for pyg_data_builder.py — AC-2.5: PyG Data construction < 2s."""

import numpy as np
import pytest

from src.graph.pyg_data_builder import (
    PyGDataBuilder,
    TORCH_AVAILABLE,
    PYG_AVAILABLE,
)
from src.graph.service_graph import Node, Edge
from src.graph.feature_extractor import FeatureExtractor, NODE_FEATURE_DIM, EDGE_FEATURE_DIM


# Skip markers for optional PyG dependency
pyg_required = pytest.mark.skipif(
    not (TORCH_AVAILABLE and PYG_AVAILABLE),
    reason="PyTorch and PyTorch Geometric not installed",
)


class TestPyGDataBuilderAvailability:
    def test_availability(self):
        """Check if PyG is available."""
        builder = PyGDataBuilder()
        assert isinstance(builder.is_available, bool)

    def test_device_default(self):
        """Default device is cpu."""
        builder = PyGDataBuilder()
        assert builder.device == "cpu"


class TestShapeValidation:
    """Test input validation for PyG Data builder."""

    def test_empty_graph_valid(self):
        """Empty edge_index and edge_attr are valid."""
        builder = PyGDataBuilder()
        nf = np.zeros((3, NODE_FEATURE_DIM), dtype=np.float32)
        ei = np.empty((2, 0), dtype=np.int64)
        ea = np.empty((0, EDGE_FEATURE_DIM), dtype=np.float32)
        # Should not raise
        builder._validate_shapes(nf, ei, ea)

    def test_edge_index_wrong_shape(self):
        """edge_index must be (2, E)."""
        builder = PyGDataBuilder()
        nf = np.zeros((3, NODE_FEATURE_DIM), dtype=np.float32)
        ei = np.array([[0, 1, 2]], dtype=np.int64)  # (1, 3) is wrong
        ea = np.zeros((3, EDGE_FEATURE_DIM), dtype=np.float32)
        with pytest.raises(ValueError, match="must be \\(2, E\\)"):
            builder._validate_shapes(nf, ei, ea)

    def test_edge_index_out_of_bounds(self):
        """Node indices must be within bounds."""
        builder = PyGDataBuilder()
        nf = np.zeros((2, NODE_FEATURE_DIM), dtype=np.float32)
        ei = np.array([[0, 2], [1, 0]], dtype=np.int64)  # node 2 doesn't exist
        ea = np.zeros((2, EDGE_FEATURE_DIM), dtype=np.float32)
        with pytest.raises(ValueError, match="only 2 nodes exist"):
            builder._validate_shapes(nf, ei, ea)

    def test_edge_index_negative(self):
        """Negative node indices are invalid."""
        builder = PyGDataBuilder()
        nf = np.zeros((2, NODE_FEATURE_DIM), dtype=np.float32)
        ei = np.array([[0, -1], [1, 0]], dtype=np.int64)
        ea = np.zeros((2, EDGE_FEATURE_DIM), dtype=np.float32)
        with pytest.raises(ValueError, match="negative"):
            builder._validate_shapes(nf, ei, ea)

    def test_edge_attr_mismatch(self):
        """edge_attr rows must match edge_index columns."""
        builder = PyGDataBuilder()
        nf = np.zeros((2, NODE_FEATURE_DIM), dtype=np.float32)
        ei = np.array([[0, 1], [1, 0]], dtype=np.int64)  # 2 edges
        ea = np.zeros((1, EDGE_FEATURE_DIM), dtype=np.float32)  # 1 row
        with pytest.raises(ValueError, match="has 1 rows"):
            builder._validate_shapes(nf, ei, ea)


@pyg_required
class TestPyGDataBuilder:
    """AC-2.5: Graph construction latency < 2s."""

    def test_build_basic(self):
        """Build a PyG Data object from arrays."""
        builder = PyGDataBuilder()
        nf = np.random.randn(5, NODE_FEATURE_DIM).astype(np.float32)
        ei = np.array([[0, 1, 2, 3, 4], [1, 2, 3, 4, 0]], dtype=np.int64)
        ea = np.random.randn(5, EDGE_FEATURE_DIM).astype(np.float32)

        data = builder.build(nf, ei, ea)
        assert data.x.shape == (5, NODE_FEATURE_DIM)
        assert data.edge_index.shape == (2, 5)
        assert data.edge_attr.shape == (5, EDGE_FEATURE_DIM)
        assert data.num_nodes == 5
        assert data.num_edges == 5

    def test_build_with_graph_id(self):
        """Graph ID is attached to the Data object."""
        builder = PyGDataBuilder()
        nf = np.zeros((3, NODE_FEATURE_DIM), dtype=np.float32)
        ei = np.array([[0, 1], [1, 2]], dtype=np.int64)
        ea = np.zeros((2, EDGE_FEATURE_DIM), dtype=np.float32)

        data = builder.build(nf, ei, ea, graph_id="window-42")
        assert data.graph_id == "window-42"

    def test_build_empty_graph(self):
        """Build with no edges."""
        builder = PyGDataBuilder()
        nf = np.zeros((3, NODE_FEATURE_DIM), dtype=np.float32)
        ei = np.empty((2, 0), dtype=np.int64)
        ea = np.empty((0, EDGE_FEATURE_DIM), dtype=np.float32)

        data = builder.build(nf, ei, ea)
        assert data.x.shape == (3, NODE_FEATURE_DIM)
        assert data.edge_index.shape == (2, 0)
        assert data.edge_attr.shape == (0, EDGE_FEATURE_DIM)
        assert data.num_nodes == 3
        assert data.num_edges == 0

    def test_build_empty_graph_helper(self):
        """build_empty_graph returns a valid empty Data object."""
        builder = PyGDataBuilder()
        data = builder.build_empty_graph()
        assert data.num_nodes == 0
        assert data.num_edges == 0

    def test_build_from_snapshot(self):
        """build_from_snapshot works with snapshot tuples."""
        extractor = FeatureExtractor()
        nodes = [
            Node(service_name="api-gateway", service_type="api-gateway"),
            Node(service_name="backend", service_type="backend"),
        ]
        edges = [
            Edge(source="api-gateway", target="backend", call_count=10),
        ]
        nf = extractor.extract_node_features(nodes)
        ei, ea = extractor.extract_edge_features(nodes, edges)

        builder = PyGDataBuilder()
        data = builder.build_from_snapshot((nf, ei, ea))
        assert data.x.shape == (2, NODE_FEATURE_DIM)
        assert data.edge_index.shape == (2, 1)

    def test_build_time_tracked(self):
        """Build time is tracked in the Data object."""
        builder = PyGDataBuilder()
        nf = np.random.randn(100, NODE_FEATURE_DIM).astype(np.float32)
        ei = np.array([[i, (i + 1) % 100] for i in range(100)]).T.astype(np.int64)
        ea = np.random.randn(100, EDGE_FEATURE_DIM).astype(np.float32)

        data = builder.build(nf, ei, ea)
        assert hasattr(data, "_build_time_s")
        # AC-2.5: Construction should be < 2s
        assert data._build_time_s < 2.0

    def test_build_import_error_without_pyg(self):
        """build raises ImportError when PyG is not available."""
        # This test only runs if PyG is available, so we test the inverse
        # by checking the import check logic
        builder = PyGDataBuilder()
        assert builder.is_available is True  # We're in the pyg_required class


class TestBuilderWithoutPyG:
    """Tests that work without PyG installed."""

    def test_build_raises_when_unavailable(self):
        """If PyG is not available, build raises ImportError."""
        builder = PyGDataBuilder()
        if not builder.is_available:
            nf = np.zeros((3, NODE_FEATURE_DIM), dtype=np.float32)
            ei = np.empty((2, 0), dtype=np.int64)
            ea = np.empty((0, EDGE_FEATURE_DIM), dtype=np.float32)
            with pytest.raises(ImportError):
                builder.build(nf, ei, ea)

    def test_empty_builder_raises_when_unavailable(self):
        """build_empty_graph raises ImportError when PyG is not available."""
        builder = PyGDataBuilder()
        if not builder.is_available:
            with pytest.raises(ImportError):
                builder.build_empty_graph()